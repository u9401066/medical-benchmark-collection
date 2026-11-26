import csv
import io
from zipfile import ZipFile

from scripts.tw_society_live_register import public_rows, write_snapshot


def test_ods_projection_preserves_missing_ids_and_keeps_search_alias_results(tmp_path):
    xml = """<doc xmlns:t="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
        xmlns:p="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><t:table t:name="Sheet 1">
        <t:table-row>"""
    for label in ["團體名稱", "團體類型", "團體狀態", "立案證書字號", "成立日期", "會址", "理事長"]:
        xml += f"<t:table-cell><p:p>{label}</p:p></t:table-cell>"
    xml += """</t:table-row><t:table-row>
        <t:table-cell><p:p>測試協會</p:p></t:table-cell>
        <t:table-cell><p:p>社會團體</p:p></t:table-cell>
        <t:table-cell><p:p>已准籌</p:p></t:table-cell>
        <t:table-cell t:number-columns-repeated="2"/>
        <t:table-cell><p:p>private-address</p:p></t:table-cell>
        <t:table-cell><p:p>private-chair</p:p></t:table-cell>
        </t:table-row></t:table></doc>"""
    binary = io.BytesIO()
    with ZipFile(binary, "w") as archive:
        archive.writestr("content.xml", xml.encode())
    sheet, records = public_rows(binary.getvalue())
    assert records == [{"團體名稱": "測試協會", "團體類型": "社會團體", "團體狀態": "已准籌",
                        "立案證書字號": "", "成立日期": ""}]
    path = tmp_path / "registry.tsv"
    write_snapshot(path, "學會", "https://example.test/", "digest", sheet, records)
    assert "private" not in path.read_text(encoding="utf-8")
    with path.open(encoding="utf-8", newline="") as stream:
        row, = csv.DictReader(stream, delimiter="\t")
    assert row["literal_name_match"] == "no"
    assert row["locator"] == "Sheet 1 row 2"
    assert row["registry_id"] == row["established_date"] == ""
