"""Export the Ministry of the Interior's public society search, omitting personal fields."""

import argparse
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener
from xml.etree import ElementTree as ET


ENTRY = "https://grouptw.moi.gov.tw/SearchGroup"
NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
PUBLIC = ["團體名稱", "團體類型", "團體狀態", "立案證書字號", "成立日期"]
COLUMNS = ["seq", "name", "organization_type", "status", "registry_id", "established_roc",
           "established_date", "literal_name_match", "locator", "source_url", "ods_sha256"]


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.inputs = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.inputs = {}
            self.forms.append((attrs.get("action"), self.inputs))
        if tag == "input" and self.inputs is not None and attrs.get("name"):
            self.inputs[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.inputs = None


def fetch(term):
    url = ENTRY + "?" + urlencode(dict(IsQuery="true", tab="little", Q_Type="社會團體", Q_Name=term))
    client = build_opener(HTTPCookieProcessor(CookieJar()))
    with client.open(url, timeout=90) as response:
        html = response.read().decode("utf-8-sig")
    count = re.search(r"查詢結果共\s*<span>([\d,]+)</span>", html)
    if not count:
        raise ValueError("Unable to determine the official search count")
    forms = Forms()
    forms.feed(html)
    action, fields = next((a, f) for a, f in forms.forms if f.get("Type") == "ods")
    if urljoin(url, action) != ENTRY + "/Download" or fields.get("Q_Name") != term:
        raise ValueError("Unexpected public download form")
    fields["IsAll"] = "true"  # The form's 全選所有 checkbox.
    request = Request(urljoin(url, action), data=urlencode(fields).encode(), headers={"Referer": url})
    with client.open(request, timeout=120) as response:
        ods = response.read()
    return url, int(count[1].replace(",", "")), ods


def public_rows(ods):
    with zipfile.ZipFile(io.BytesIO(ods)) as archive:
        content = ET.fromstring(archive.read("content.xml"))
    sheets = content.findall(".//table:table", NS)
    if len(sheets) != 1:
        raise ValueError("Expected one ODS worksheet")
    sheet = sheets[0]
    sheet_name = sheet.attrib[f"{{{NS['table']}}}name"]
    rows = sheet.findall("table:table-row", NS)

    def text_at(cell):
        return " ".join("".join(p.itertext()) for p in cell.findall("text:p", NS)).strip()

    def expanded_cells(row):
        for cell in row.findall("table:table-cell", NS):
            repeat = int(cell.get(f"{{{NS['table']}}}number-columns-repeated", "1"))
            for _ in range(repeat):
                yield cell

    headers = [text_at(c) for c in expanded_cells(rows[0])]
    indices = {headers.index(label): label for label in PUBLIC}
    records = []
    for row in rows[1:]:
        if row.get(f"{{{NS['table']}}}number-rows-repeated", "1") != "1":
            raise ValueError("Unexpected repeated row in ODS export")
        # Only extract the explicitly listed public registry facts.
        values = {indices[i]: text_at(cell) for i, cell in enumerate(expanded_cells(row)) if i in indices}
        if values.get("團體名稱"):
            records.append(values)
        else:
            raise ValueError("Unexpected blank name in ODS export")
    return sheet_name, records


def write_snapshot(path, term, source_url, digest, sheet, records):
    rendered = io.StringIO(newline="")
    table = csv.DictWriter(rendered, COLUMNS, delimiter="\t", lineterminator="\n")
    table.writeheader()
    for n, row in enumerate(records, 1):
        roc = row["成立日期"]
        iso = ""
        if roc:
            parts = re.fullmatch(r"(\d+)年(\d+)月(\d+)日", roc)
            if not parts:
                raise ValueError(f"Unexpected date in row {n + 1}")
            year, month, day = map(int, parts.groups())
            iso = date(year + 1911, month, day).isoformat()
        table.writerow(dict(seq=n, name=row["團體名稱"], organization_type=row["團體類型"],
                            status=row["團體狀態"], registry_id=row["立案證書字號"],
                            established_roc=roc, established_date=iso,
                            literal_name_match="yes" if term in row["團體名稱"] else "no",
                            locator=f"{sheet} row {n + 1}", source_url=source_url, ods_sha256=digest))
    path.write_bytes(rendered.getvalue().encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--term", default="學會")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url, expected, ods = fetch(args.term)
    digest = hashlib.sha256(ods).hexdigest()
    sheet, rows = public_rows(ods)
    if len(rows) != expected:
        raise ValueError(f"Public search reports {expected} but ODS contains {len(rows)} rows")
    write_snapshot(args.output, args.term, url, digest, sheet, rows)
    print(f"{len(rows)} rows, {len(ods)} ODS bytes, SHA-256 {digest}")
    print(dict(Counter(r["團體狀態"] for r in rows)))


if __name__ == "__main__":
    main()
