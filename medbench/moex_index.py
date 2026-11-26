"""Inventory the Ministry of Examination's published exam menus and paper links."""
from __future__ import annotations

import argparse
import csv
import errno
import hashlib
import html
import os
import re
import subprocess
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

from .twmed import MOEX, SEARCH, UA, Moex


FORM = "ctl00$holderContent$"
STATISTICS = re.compile(r'共\s*([\d,]+)\s*考試\s*([\d,]+)\s*類科\s*([\d,]+)\s*科目')
RESULT_LIMIT = re.compile(r"查詢的結果大於\s*([\d,]+)\s*筆")
EXAM_BLOCK = re.compile(r'<td\s+class="level1">')
LABEL = re.compile(r'<label\b[^>]*\bfor="ctl00_holderContent_chk_(\d+)_([^_"<>]+)(?:_([^"<>]+))?"[^>]*>(.*?)</label>', re.S)
LINK = re.compile(r'\bhref="([^"]*wHandExamQandA_File\.ashx\?[^"]+)"', re.I)
ROLE = {"Q": "question", "S": "answer", "M": "correction", "A": "exam_answers", "B": "accessible_exam_questions"}
MEDICAL = re.compile(
    r"醫師|醫士|牙醫|中醫|藥師|藥劑|護士|護理|助產|醫事|醫檢|營養|心理師|臨床心理|諮商心理|"
    r"物理治療|職能治療|呼吸治療|語言治療|聽力|驗光|牙體|法醫|公共衛生|衛生行政|衛生技術|"
    r"衛生檢驗|衛生稽查|衛生統計|醫政|醫務|醫療|藥事|藥政|藥學|防疫醫|流行病|齒科|齒模")
BOUNDARY = re.compile(
    r"獸醫|動物防疫|動物用藥|社會工作|社工|食品|食安|工礦衛生|工業衛生|職業衛生|"
    r"環境衛生|勞工衛生|環保衛生|安全衛生|職業安全|衛生工程|心理|健康|體育|消防|救護|"
    r"鑑識|輔導|毒理|生物醫|醫學工程|醫藥|製藥|藥物|中藥|生藥|放射|輻射|保健|疾病管制|衛生教育|"
    r"檢驗員|衛生環保|口腔衛生")
NONHUMAN = re.compile(r"獸醫|動物防疫|動物用藥")
SUBJECT_HINT = re.compile(r"臨床|醫學|醫療|法醫|藥理|藥物|流行病|衛生|護理|解剖|生理學|病理|食品安全|急救|緊急救護")


def classify(category: str, subject: str = "") -> str:
    if NONHUMAN.search(category):
        return "boundary"
    if MEDICAL.search(category):
        return "medical"
    if not category or BOUNDARY.search(category) or SUBJECT_HINT.search(subject):
        return "boundary"
    return "outside"


BASE = ["year_roc", "exam_code", "exam_name"]
CAT = BASE + ["category_code", "category_name"]
SUB = CAT + ["subject_code", "subject_name", "scope"]
ASSET = ["asset_id", *SUB, "asset_type", "asset_role", "source_url"]
EXAM_ASSET = ["asset_id", *BASE, "asset_type", "asset_role", "source_url"]
COVERAGE = ["year_roc", "year_ad", "status", "menu_exams", "official_exams", "parsed_exams",
            "official_categories", "parsed_categories", "official_subjects", "parsed_subjects", "detail",
            "category_codes_without_heading", "confirmed_empty_exams", "accounted_exams"]


@dataclass
class Inventory:
    exams: dict[str, str] = field(default_factory=dict)
    categories: dict[tuple[str, str], str] = field(default_factory=dict)
    subjects: dict[tuple[str, str, str], str] = field(default_factory=dict)
    assets: dict[tuple[str, str, str, str, str], str] = field(default_factory=dict)
    totals: tuple[int, ...] = ()


def label_text(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def no_results(page: str, code: str) -> bool:
    selected = re.search(r'<option\b[^>]*selected="selected"[^>]*value="' + re.escape(code) + r'"', page)
    return bool(selected and re.search(r'id="ctl00_holderContent_lblStatistics"[^>]*>\s*查無結果\s*<', page))


def asset_id(*parts: str) -> str:
    return "moex-" + "-".join(quote(part, safe="").replace("-", "%2D") for part in parts)


def parse_result(page: str) -> Inventory:
    """Count every result before applying the medical scope, deduplicating mobile and desktop links."""
    result = Inventory()
    stats = STATISTICS.search(page)
    if stats:
        result.totals = tuple(int(n.replace(",", "")) for n in stats.groups())
    for block in EXAM_BLOCK.split(page)[1:]:
        labels = list(LABEL.finditer(block))
        title = re.search(r'<td style="vertical-align:text-top;">(.*?)</td>', block, re.S)
        code_match = re.search(r'wHandExamQandA_File\.ashx\?t=A&amp;code=(\d+)', block)
        code = labels[0][1] if labels else (code_match[1] if code_match else "")
        if not code or not title:
            raise ValueError("exam header without a stable identity")
        result.exams[code] = label_text(title[1])
        for label in labels:
            exam, cat, subject, raw_text = label.groups()
            cat, subject = html.unescape(cat), html.unescape(subject) if subject else ""
            if exam != code:
                raise ValueError(f"label belongs to a different exam than {code}")
            if subject:
                result.subjects[code, cat, subject] = label_text(raw_text)
            else:
                result.categories[code, cat] = label_text(raw_text)
        for href in LINK.findall(block):
            url = urljoin(MOEX, html.unescape(href))
            parsed = urlsplit(url)
            if (parsed.scheme, parsed.netloc, parsed.path) != ("https", "wwwq.moex.gov.tw", "/exam/wHandExamQandA_File.ashx"):
                raise ValueError("unexpected official asset target")
            params = parse_qs(parsed.query)
            fields = [params.get(k, [""])[0] for k in ("code", "c", "s", "t", "q")]
            linked_exam, cat, subject, asset_type, seq = fields
            if linked_exam != code or not asset_type or bool(cat) != bool(subject):
                raise ValueError(f"invalid attachment identity in {url}")
            if subject and (code, cat, subject) not in result.subjects:
                raise ValueError(f"attachment without matching subject in {url}")
            key = (code, cat, subject, asset_type, seq)
            if key in result.assets and result.assets[key] != url:
                raise ValueError(f"multiple URLs for the same identifier {key}")
            result.assets[key] = url
    return result


def save_tsv(path: Path, columns: list[str], rows) -> None:
    temp = path.with_suffix(f".{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    for attempt in range(6):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.25)


@contextmanager
def export_lock(cache: Path, out: Path):
    # On exit the OS releases the lock, including when a collector is interrupted.
    target = hashlib.sha256(os.fsencode(out.resolve())).hexdigest()[:16]
    with (cache / f".export-{target}.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            if not lock.tell():
                lock.write(b"1")
                lock.flush()
            lock.seek(0)
            while True:
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    time.sleep(0.25)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def combine(result: Inventory, extra: Inventory) -> None:
    for name in ("exams", "categories", "subjects", "assets"):
        target, additions = getattr(result, name), getattr(extra, name)
        for key, value in additions.items():
            if key in target and target[key] != value:
                raise ValueError(f"conflicting annual and individual listing: {key}")
            target[key] = value


def export(cache: Path, out: Path) -> None:
    """Emit partial snapshots with explicit unknown coverage when pages are missing or disagree."""
    with export_lock(cache, out):
        write_inventory(cache, out)


def write_inventory(cache: Path, out: Path) -> None:
    coverage, exams, categories, subjects, assets, exam_assets, pages, per_exam = [], [], [], [], [], [], [], []

    def read_page(path: Path, roc: str, action: str, url: str = SEARCH) -> str:
        raw = path.read_bytes()
        pages.append([roc, action, url, path.name, len(raw), hashlib.sha256(raw).hexdigest()])
        return raw.decode("utf-8-sig")

    years = options(read_page(cache / "search.html", "", "GET"), "wUctlExamYearStart$ddlExamYear")
    for year, roc in sorted(years.items()):
        menu_path, page_path = (cache / f"{kind}-{year}.html" for kind in ("year", "subjects"))
        menu = options(read_page(menu_path, roc, "POST btnYear"), "ddlExamCode") if menu_path.exists() else None
        result = Inventory()
        detail = ""
        if menu and any(code[:3] != roc.zfill(3) for code in menu):
            raise ValueError(f"{menu_path}: exam code prefix does not match ROC year {roc}")
        if page_path.exists():
            try:
                annual_html = read_page(page_path, roc, "POST btnSearch")
                result = parse_result(annual_html)
                limit = RESULT_LIMIT.search(annual_html)
                if limit:
                    detail = "annual query exceeded official " + limit[1] + "-record limit"
            except ValueError as exc:
                detail = str(exc)
        individual_totals = []
        discrepant_exams = []
        empty_exams = {code: "unpublished in official exam menu" for code, title in (menu or {}).items()
                       if "未公布試題" in title or "未公佈試題" in title}
        for code in sorted(menu or {}):
            individual = cache / f"exam-{year}-{code}.html"
            fallback = cache / f"exam-post-{year}-{code}.html"
            action, url = "GET", official_exam_url(year, code)
            if fallback.exists():
                individual, action, url = fallback, "POST btnSearch (single exam)", SEARCH
            if not individual.exists():
                continue
            try:
                single_html = read_page(individual, roc, action, url)
                extra = parse_result(single_html)
                if not extra.exams and no_results(single_html, code):
                    empty_exams.setdefault(code, "no results on official exam page")
                    per_exam.append([roc, code, official_exam_url(year, code), 0, 0, 0, 0, empty_exams[code]])
                    individual_totals.append((0, 0, 0))
                    continue
                if set(extra.exams) != {code} or not extra.totals:
                    raise ValueError(f"unexpected individual listing for {code}")
                combine(result, extra)
                individual_totals.append(extra.totals)
                ncat, nsub = len(extra.categories), len(extra.subjects)
                if extra.totals != (1, ncat, nsub):
                    discrepant_exams.append(code)
                per_exam.append([roc, code, official_exam_url(year, code), extra.totals[1], ncat, extra.totals[2], nsub,
                                 "verified" if extra.totals == (1, ncat, nsub) else "official totals differ from rows"])
            except ValueError as exc:
                per_exam.append([roc, code, official_exam_url(year, code), "", "", "", "", str(exc)])
        if not result.totals and menu and len(individual_totals) == len(menu):
            result.totals = tuple(map(sum, zip(*individual_totals)))
            detail = (detail + ". " if detail else "") + "official totals aggregated from each individual exam"
        counts = (len(result.exams), len(result.categories), len(result.subjects))
        empty_exams = {code: reason for code, reason in empty_exams.items() if code not in result.exams}
        accounted = set(result.exams) | set(empty_exams)
        matches = menu is not None and accounted == set(menu) and counts == result.totals
        if not matches and not detail:
            if menu is None:
                detail = "missing official year menu"
            elif not page_path.exists():
                detail = "subject page not yet collected"
            elif accounted != set(menu):
                detail = "exam menu/result difference: " + ",".join(sorted(accounted ^ set(menu)))
            else:
                detail = "official results totals missing or different"
        if discrepant_exams:
            detail = (detail + ". " if detail else "") + "Individual exam totals differ: " + ",".join(discrepant_exams)
        totals = result.totals or ("", "", "")
        counts_by_cat = Counter(k[:2] for k in result.subjects)
        missing_category_names = set(counts_by_cat) - result.categories.keys()
        coverage.append([roc, year, "verified" if matches else "unresolved", len(menu) if menu is not None else "",
                         totals[0], counts[0], totals[1], counts[1], totals[2], counts[2], detail, len(missing_category_names),
                         len(empty_exams), len(accounted)])
        for code, title in sorted({**(menu or {}), **result.exams}.items()):
            exams.append([roc, code, title, "listed" if code in result.exams else empty_exams.get(code, "unresolved")])
        for code, cat in sorted(result.categories.keys() | missing_category_names):
            name = result.categories.get((code, cat), "")
            heading = "subject code only; no category heading" if (code, cat) in missing_category_names else "listed"
            categories.append([roc, code, result.exams[code], cat, name, classify(name), counts_by_cat[code, cat], heading])
        asset_types = defaultdict(list)
        for code, cat, sub, kind, seq in result.assets:
            if sub:
                asset_types[code, cat, sub].append(kind)
        selected = {}
        for (code, cat, sub), name in sorted(result.subjects.items()):
            category_name = result.categories.get((code, cat), "")
            scope = classify(category_name, name)
            if scope != "outside":
                fields = [roc, code, result.exams[code], cat, category_name, sub, name, scope]
                kinds = asset_types[code, cat, sub]
                subjects.append([*fields, ",".join(sorted(set(kinds))), len(kinds),
                                 "listed" if kinds else "no subject attachment listed", official_exam_url(year, code)])
                selected[code, cat, sub] = fields
        for (code, cat, sub, kind, seq), url in sorted(result.assets.items()):
            role = ROLE.get(kind, "other")
            if not cat:
                exam_assets.append([asset_id(code, kind, seq or "na"), roc, code, result.exams[code], kind, role, url])
            elif (code, cat, sub) in selected:
                file_id = asset_id(code, cat, sub, kind, seq or "na")
                assets.append([file_id, *selected[code, cat, sub], kind, role, url])
    out.mkdir(parents=True, exist_ok=True)
    for name, columns, rows in [("exams", BASE + ["status"], exams), ("categories", CAT + ["scope", "subject_count", "heading_status"], categories),
                                ("subjects", SUB + ["listed_asset_types", "asset_count", "asset_status", "source_page_url"], subjects),
                                ("assets", ASSET, assets), ("exam_assets", EXAM_ASSET, exam_assets),
                                ("pages", ["year_roc", "request", "source_url", "cache_file", "bytes", "sha256"], pages),
                                ("exam_coverage", ["year_roc", "exam_code", "source_url", "official_categories",
                                 "parsed_categories", "official_subjects", "parsed_subjects", "detail"], per_exam),
                                ("coverage", COVERAGE, coverage)]:
        save_tsv(out / f"{name}.tsv", columns, rows)


def options(page: str, field: str) -> dict[str, str]:
    select = re.search(r'<select\b[^>]*\bname="' + re.escape(FORM + field) + r'"[^>]*>(.*?)</select>', page, re.S)
    if not select:
        raise ValueError(f"missing official select {field}")
    return {v: html.unescape(t).strip() for v, t in re.findall(
        r'<option\b[^>]*\bvalue="(\d+)"[^>]*>(.*?)</option>', select[1], re.S)}


class OfficialPages:
    def __init__(self, folder: Path, delay: float):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.delay = max(1.0, delay)
        self.last_request = 0.0

    def page(self, name: str, form: dict[str, str] | None = None, url: str = SEARCH) -> str:
        path = self.folder / (name + ".html")
        if path.exists():
            return path.read_text(encoding="utf-8-sig")
        time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        annual_query = name.startswith("subjects-")
        # Large annual results also have individually addressable exam pages.
        args = ["curl", "--silent", "--show-error", "--fail", "--compressed", "--max-time", "90",
                "--user-agent", UA, "--retry", "0" if annual_query else "2", "--retry-delay", "4"]
        if form is not None:
            args.extend(["--data-binary", "@-"])
        response = subprocess.run([*args, url], input=urlencode(form).encode("ascii") if form else None,
                                  capture_output=True, check=False)
        if response.returncode:
            raise RuntimeError(response.stderr.decode(errors="replace").strip())
        page = response.stdout.decode("utf-8-sig")
        if "ctl00_holderContent_ddlExamCode" not in page or "</html>" not in page.lower():
            raise ValueError(f"unexpected or incomplete official response for {name}")
        temp = path.with_suffix(f".{os.getpid()}.tmp")
        temp.write_bytes(response.stdout)
        temp.replace(path)
        return page


def form_for(page: str, year: str, exam: str | None = None) -> dict[str, str]:
    f = {k: html.unescape(v) for k, v in Moex._hidden(page).items()}
    f.update({FORM + "wUctlExamYearStart$ddlExamYear": year,
              FORM + "wUctlExamYearEnd$ddlExamYear": year})
    if exam is None:
        f[FORM + "btnYear"] = "依考試年度設定考試簡稱"
    else:
        f.update({FORM + "ddlExamCode": exam, FORM + "btnSearch": "查詢"})
    return f


def official_exam_url(year, code) -> str:
    return SEARCH + "?" + urlencode({"e": code, "y": year})


def diagnose(pages: OfficialPages, selected: set[int] | None, out: Path | None = None) -> None:
    """Resolve missing or inconsistent annual results by requesting individually listed official exams."""
    initial = pages.page("search")
    years = options(initial, "wUctlExamYearStart$ddlExamYear")
    for year in sorted(years):
        if selected and int(year) not in selected:
            continue
        annual = pages.page("year-" + year, form_for(initial, year))
        codes = options(annual, "ddlExamCode")
        full = pages.folder / f"subjects-{year}.html"
        if full.exists():
            try:
                r = parse_result(full.read_text(encoding="utf-8-sig"))
                if set(r.exams) == set(codes) and r.totals == (len(r.exams), len(r.categories), len(r.subjects)):
                    continue
            except ValueError:
                pass
        for code in sorted(codes):
            try:
                if not (pages.folder / f"exam-post-{year}-{code}.html").exists():
                    try:
                        page = pages.page(f"exam-{year}-{code}", url=official_exam_url(year, code))
                        if code not in parse_result(page).exams and not no_results(page, code):
                            raise ValueError("exam deep link returned no identifiable result")
                    except (RuntimeError, ValueError, OSError):
                        pages.page(f"exam-post-{year}-{code}", form_for(annual, year, code))
                print(f"{year}: individual exam {code}", flush=True)
            except (RuntimeError, ValueError, OSError) as exc:
                print(f"{year}: {code}: {exc}", flush=True)
        if out is not None:
            export(pages.folder, out)


def collect(pages: OfficialPages, selected: set[int] | None = None, out: Path | None = None) -> None:
    initial = pages.page("search")
    years = options(initial, "wUctlExamYearStart$ddlExamYear")
    errors = []
    for year in sorted(years, reverse=True):
        if selected and int(year) not in selected:
            continue
        try:
            annual = pages.page("year-" + year, form_for(initial, year))
            exams = options(annual, "ddlExamCode")
            print(f"{year} menu: {len(exams)} exams", flush=True)
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append((year, str(exc)))
    completed = 0
    for year in sorted(years):
        if (selected and int(year) not in selected) or not (pages.folder / f"year-{year}.html").exists():
            continue
        try:
            annual = pages.page("year-" + year)
            subjects = pages.page("subjects-" + year, form_for(annual, year, ""))
            count = subjects.count('class="exam-title"')
            print(f"{year} subject page: {len(subjects)} chars, {count} rows", flush=True)
            completed += 1
            if out is not None and (completed == 1 or completed % 5 == 0):
                export(pages.folder, out)
        except (RuntimeError, ValueError, OSError) as exc:
            errors.append((year, str(exc)))
    for year, error in errors:
        print(f"{year}: {error}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/moex/index"))
    parser.add_argument("--years", help="comma-separated Gregorian years or ranges, e.g. 1992-1995,2024; defaults to all official options")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--out", type=Path, default=Path("datasets/moex/index"))
    parser.add_argument("--export-only", action="store_true", help="regenerate tables from cached official pages without network")
    parser.add_argument("--diagnose-only", action="store_true", help="fetch individual exam pages for missing or inconsistent annual listings")
    args = parser.parse_args()
    selected = None
    if args.years:
        selected = set()
        for part in args.years.split(","):
            match = re.fullmatch(r"(\d{4})(?:-(\d{4}))?", part.strip())
            if not match or int(match[2] or match[1]) < int(match[1]):
                parser.error("--years expects Gregorian years or ascending ranges")
            selected.update(range(int(match[1]), int(match[2] or match[1]) + 1))
    if not args.export_only:
        pages = OfficialPages(args.cache, args.delay)
        if not args.diagnose_only:
            collect(pages, selected, args.out)
            export(args.cache, args.out)
        diagnose(pages, selected, args.out)
    export(args.cache, args.out)


if __name__ == "__main__":
    main()
