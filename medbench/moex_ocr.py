"""Create unreviewed page transcripts for scans in a verified MOEX file manifest."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from .moex_archive import atomic
from .twmed import sha256_file


VERSION = 1
MODEL_REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
MODEL_SHA256 = {"chi_tra": "529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b",
                "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
                "chi_tra_vert": "1df02a4b210e5c217b783819538b63e9dfe6904e2b5e53b62664f1b9f7a989d0"}
CONFIDENCE_THRESHOLD = 60


def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def compressed(lines):
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as z:
        for line in lines:
            z.write(encoded(line) + b"\n")
    return buf.getvalue()


def tesseract_path():
    command = shutil.which("tesseract")
    if command:
        return command
    path = Path(os.environ.get("ProgramFiles", "")) / "Tesseract-OCR" / "tesseract.exe"
    return str(path) if path.is_file() else None


def read_layouts(path):
    profiles = {}
    if not path.is_file():
        return profiles
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            profiles[row["asset_id"]] = row
            digest = row.get("source_sha256")
            if digest:
                if not re.fullmatch("[0-9a-f]{64}", digest):
                    raise ValueError(f"Invalid layout source digest for {row['asset_id']}")
                other = profiles.get(digest)
                if other and (other["language"], other["psm"]) != (row["language"], row["psm"]):
                    raise ValueError(f"Conflicting OCR profiles for source digest {digest}")
                profiles[digest] = row
    return profiles


def parse_tsv(raw, rect, pixel_size):
    """Keep Tesseract reading order and map each word to the displayed PDF page."""
    sx, sy = rect.width / pixel_size[0], rect.height / pixel_size[1]
    lines = defaultdict(list)
    for row in csv.DictReader(io.StringIO(raw), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row["level"] != "5" or not row["text"].strip():
            continue
        x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
        conf = float(row["conf"])
        lines[(row["block_num"], row["par_num"], row["line_num"])].append({
            "text": row["text"], "confidence": conf if conf >= 0 else None,
            "bbox_pt": [round(rect.x0 + x * sx, 2), round(rect.y0 + y * sy, 2),
                        round(rect.x0 + (x + w) * sx, 2), round(rect.y0 + (y + h) * sy, 2)]})
    return [{"line_id": ".".join(key), "words": words} for key, words in lines.items()]


def native_lines(page, tessdata, language, dpi):
    textpage = page.get_textpage_ocr(language=language, dpi=dpi, full=True, tessdata=str(tessdata))
    lines = defaultdict(list)
    for x0, y0, x1, y1, text, block, line, _ in page.get_text("words", textpage=textpage):
        import pymupdf
        box = pymupdf.Rect(x0, y0, x1, y1) * page.rotation_matrix
        lines[(block, line)].append({"text": text, "confidence": None, "bbox_pt": [round(v, 2) for v in box]})
    return [{"line_id": f"{block}.{line}", "words": words} for (block, line), words in lines.items()]


def scan_page(page, tessdata, settings, exe):
    import pymupdf
    dpi = settings["dpi"]
    native = page.get_text("text").strip()
    base = {"pdf_page": page.number + 1, "page_rect_pt": list(page.rect), "pdf_rotation": page.rotation}
    # A page with a long text layer has a separate archival extraction path.
    if len(re.sub(r"\s+", "", native)) >= 30:
        return {**base, "status": "existing_text_layer", "native_text_length": len(native)}
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    png = pix.tobytes("png")
    base.update(rendered_png_sha256=hashlib.sha256(png).hexdigest(), pixels=[pix.width, pix.height])
    if exe:
        # The model directory can contain only pinned traineddata, without the
        # tsv config shipped by the executable. Set the output option directly.
        command = [exe, "stdin", "stdout", "--tessdata-dir", str(tessdata), "-l", settings["language"],
                   "--dpi", str(dpi), "--psm", str(settings["psm"]), "-c", "tessedit_create_tsv=1"]
        result = subprocess.run(command, input=png, capture_output=True, timeout=240,
                                env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", "replace")[:400])
        raw = result.stdout.decode("utf-8-sig")
        if not raw.startswith("level\tpage_num\t"):
            raise ValueError("Tesseract did not return a TSV grid")
        lines = parse_tsv(raw, page.rect, (pix.width, pix.height))
    else:
        lines = native_lines(page, tessdata, settings["language"], dpi)
    words = [w for line in lines for w in line["words"]]
    low = sum(w["confidence"] is not None and w["confidence"] < CONFIDENCE_THRESHOLD for w in words)
    return {**base, "status": "ocr_draft" if words else "no_text_recognized", "review": "pending_human_review",
            "reading_order": "engine_order_unverified", "low_confidence_word_count": low if exe else None,
            "word_count": len(words), "lines": lines,
            "text": "\n".join(" ".join(w["text"] for w in line["words"]) for line in lines)}


def settings_for(tessdata, language, revision, dpi, psm, engine):
    import pymupdf
    langs = language.split("+")
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z_0-9]*", lang) for lang in langs):
        raise ValueError("Invalid Tesseract language specification")
    models = {lang: sha256_file(tessdata / f"{lang}.traineddata") for lang in langs}
    if revision == MODEL_REVISION and any(MODEL_SHA256.get(lang) != digest for lang, digest in models.items()):
        raise ValueError("Traineddata does not match the pinned official revision")
    exe = tesseract_path() if engine != "pymupdf" else None
    if engine == "tsv" and not exe:
        raise RuntimeError("Tesseract CLI is required for TSV confidence output")
    engine_version = subprocess.check_output([exe, "--version"], encoding="utf-8", errors="replace").splitlines()[0] if exe else None
    return {"version": VERSION, "engine": "tesseract_tsv" if exe else "pymupdf_get_textpage_ocr",
            "engine_version": engine_version, "pymupdf": pymupdf.VersionBind,
            "mupdf": getattr(pymupdf, "mupdf_version", getattr(pymupdf, "VersionFitz", None)),
            "dpi": dpi, "colorspace": "grayscale", "psm": psm if exe else None, "language": language,
            "model_revision": revision, "traineddata_sha256": models,
            "low_confidence_threshold": CONFIDENCE_THRESHOLD if exe else None}, exe


def build(manifest, archive, out, cache, tessdata, language=None, revision=MODEL_REVISION, dpi=300,
          psm=None, engine="auto", years=None, papers=None, roles=("Q",), limit=None, layouts=None):
    import pymupdf
    settings_cache = {}
    archive = archive.resolve()
    summary = Counter()
    with manifest.open(encoding="utf-8-sig", newline="") as stream:
        rows = sorted(csv.DictReader(stream, delimiter="\t"), key=lambda r: (r["paper_id"], r["asset_type"], r["source_url"]))
    handled = 0
    for row in rows:
        if row["asset_type"] not in roles or (years and row["year_roc"] not in years) or (papers and row["paper_id"] not in papers):
            continue
        if row["status"] != "verified" or row.get("format", "").lower() != "pdf":
            summary["not_verified_pdf"] += 1
            continue
        if limit is not None and handled >= limit:
            break
        handled += 1
        source = {k: row[k] for k in ("paper_id", "asset_type", "source_url", "sha256")}
        asset_id = row.get("asset_id") or (row["paper_id"] + "-" + row["asset_type"] + "-" + hashlib.sha256(row["source_url"].encode()).hexdigest()[:12])
        if not (re.fullmatch(r"[A-Za-z0-9_-]+", asset_id) and row["year_roc"].isdigit()):
            raise ValueError("Invalid archive identifier")
        path = (archive / row["local_path"]).resolve()
        if not path.is_relative_to(archive) or not path.is_file() or sha256_file(path) != row["sha256"]:
            summary["source_hash_or_path_error"] += 1
            continue
        profiles = layouts or {}
        profile = profiles.get(asset_id, {})
        if profile.get("source_sha256") not in {None, "", row["sha256"]}:
            profile = {}
        profile = profile or profiles.get(row["sha256"], {})
        combo = (language or profile.get("language", "chi_tra"), psm or int(profile.get("psm", 3)))
        if combo not in settings_cache:
            settings_cache[combo] = settings_for(tessdata, combo[0], revision, dpi, combo[1], engine)
        settings, exe = settings_cache[combo]
        fingerprint = hashlib.sha256(encoded([source["sha256"], settings])).hexdigest()
        records = []
        try:
            with pymupdf.open(path) as doc:
                for page in doc:
                    stored = cache / fingerprint / f"{page.number + 1:04d}.json.gz"
                    record = None
                    if stored.is_file():
                        try:
                            with gzip.open(stored, "rt", encoding="utf-8") as data:
                                saved = json.load(data)
                            if saved.get("pdf_page") == page.number + 1 and saved.get("status") in {
                                "existing_text_layer", "ocr_draft", "no_text_recognized"
                            }:
                                record = saved
                        except (OSError, EOFError, ValueError, AttributeError):
                            pass
                    if record is None:
                        try:
                            record = scan_page(page, tessdata, settings, exe)
                        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as err:
                            record = {"pdf_page": page.number + 1, "status": "ocr_error", "error": str(err)[:400]}
                        if record["status"] != "ocr_error":
                            atomic(stored, compressed([record]))
                    summary[record["status"]] += 1
                    records.append({"asset_id": asset_id, "source": source, "settings": settings, **record})
        except (RuntimeError, ValueError, OSError):
            summary["unreadable_pdf_or_cache"] += 1
            continue
        target = out / row["year_roc"] / (asset_id + ".jsonl.gz")
        has_scans = any(r["status"] != "existing_text_layer" for r in records)
        # A revised PDF may now include a text layer. Replace a previous public
        # transcript with page statuses tied to the new digest in that case.
        if has_scans or target.exists():
            content = compressed(records)
            if not target.exists() or target.read_bytes() != content:
                atomic(target, content)
            summary["assets_with_scan_pages" if has_scans else "previous_scan_now_has_text_layer"] += 1
    return dict(sorted(summary.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("datasets/moex/archive/files.tsv"))
    parser.add_argument("--archive", type=Path, default=Path("data/moex/archive"))
    parser.add_argument("--cache", type=Path, default=Path("data/moex/ocr-pages"))
    parser.add_argument("--out", type=Path, default=Path("datasets/moex/ocr"))
    parser.add_argument("--tessdata", type=Path, default=Path("data/moex/tessdata"))
    parser.add_argument("--language", help="Override the asset layout profile language")
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--psm", type=int, choices=(3, 5, 6), help="Override the Tesseract CLI segmentation mode")
    parser.add_argument("--layouts", type=Path, default=Path("datasets/moex/ocr/layouts.tsv"))
    parser.add_argument("--engine", choices=("auto", "tsv", "pymupdf"), default="auto")
    parser.add_argument("--year", action="append", help="ROC year, repeatable")
    parser.add_argument("--paper", action="append")
    parser.add_argument("--role", choices=("Q", "S", "M"), action="append")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not 100 <= args.dpi <= 600 or (args.limit is not None and args.limit < 0):
        parser.error("dpi must be 100–600 and limit nonnegative")
    layouts = read_layouts(args.layouts)
    result = build(args.manifest, args.archive, args.out, args.cache, args.tessdata, args.language, args.model_revision,
                   args.dpi, args.psm, args.engine, args.year, args.paper, args.role or ["Q"], args.limit, layouts)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
