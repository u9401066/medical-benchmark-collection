"""Index individual renditions inside the ministry's whole-exam accessibility ZIPs."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import PurePosixPath
import re
import unicodedata
import zipfile

from .moex_archive import read_tsv
from .moex_bundle import decoded_name
from .moex_coverage import paper_id, write


def norm(text):
    return "".join(unicodedata.normalize("NFKC", text).split())


def members(source, blob, categories, subjects):
    exam = source["exam_code"]
    with zipfile.ZipFile(blob) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            try:
                name = decoded_name(info)
            except UnicodeError:
                name = info.filename
            path = PurePosixPath(name)
            category = subject = code = ""
            scope = "unresolved"
            mapping = "unmatched_directory"
            pid = ""
            # Observed official directories are <level>_<category code>_<name>/<printed code>_<subject>/file.
            for i, parent in enumerate(path.parts[:-2]):
                m = re.fullmatch(r"(.+)_([A-Za-z0-9]+)_(.+)", parent)
                if not m:
                    continue
                category = m[3]
                code = m[2]
                record = categories.get((exam, code))
                if not record or norm(record["category_name"].split("_")[-1]) != norm(category):
                    break
                scope = record["scope"]
                label = path.parts[i + 1].partition("_")
                subject = label[2] if label[1] else ""
                candidates = subjects.get((exam, code, norm(subject)), [])
                if len(candidates) == 1:
                    pid = paper_id(candidates[0])
                    scope = candidates[0]["scope"]
                    mapping = "matched_subject"
                elif scope == "outside":
                    mapping = "outside_category"
                else:
                    mapping = "subject_needs_review"
                break
            with z.open(info) as f:
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            yield {"exam_code": exam, "year_roc": source["year_roc"], "package_url": source["source_url"],
                   "package_sha256": source["sha256"], "member": name, "bytes": info.file_size,
                   "sha256": h.hexdigest(), "extension": path.suffix.lower().lstrip("."),
                   "category_code": code, "category_in_zip": category, "subject_in_zip": subject,
                   "scope": scope, "paper_id": pid, "mapping": mapping}


def catalog(index, exam_manifest, cache, out):
    categories = {(r["exam_code"], r["category_code"]): r for r in read_tsv(index / "categories.tsv")}
    subjects = defaultdict(list)
    for r in read_tsv(index / "subjects.tsv"):
        subjects[r["exam_code"], r["category_code"], norm(r["subject_name"])].append(r)
    rows = []
    packages = []
    for r in read_tsv(exam_manifest):
        if r["asset_type"] != "B":
            continue
        counts = Counter()
        detail = ""
        if r["status"] != "verified":
            status = r["status"]
        elif r["format"] != "zip":
            status = "other_format"
        else:
            try:
                content = list(members(r, cache / r["local_path"], categories, subjects))
                counts.update(v["scope"] for v in content)
                rows.extend(content)
                status = "inventoried"
            except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, EOFError) as error:
                status, detail = "needs_review", str(error)
        packages.append({**r, "package_state": status, "members": sum(counts.values()),
                         **{key: counts[key] for key in ("medical", "boundary", "outside", "unresolved")}, "detail": detail})
    write(out / "accessible-members.tsv",
          ["year_roc", "exam_code", "package_url", "package_sha256", "member", "extension", "bytes", "sha256",
           "category_code", "category_in_zip", "subject_in_zip", "scope", "paper_id", "mapping"], rows)
    write(out / "accessible-packages.tsv", ["year_roc", "exam_code", "source_url", "sha256", "package_state",
          "members", "medical", "boundary", "outside", "unresolved", "detail"], packages)
