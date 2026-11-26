import hashlib
import zipfile

from medbench.moex_accessible import members, norm


def test_only_unambiguous_category_and_subject_renditions_get_paper_ids(tmp_path):
    blob = tmp_path / "B.zip"
    folder = "高考_101_護理師/30110(1301)_內外科護理學/"
    with zipfile.ZipFile(blob, "w") as z:
        z.writestr(folder + "30110.doc", b"doc")
        z.writestr(folder + "30110.txt", b"text")
        z.writestr("高考_103_社會工作師/10370_共同科目/10370.docx", b"other")
        z.writestr("高考_101_不同類科/30110_內外科護理學/file.pdf", b"ambiguous")
    source = {"exam_code": "115100", "year_roc": "115", "source_url": "official", "sha256": "zip hash"}
    categories = {("115100", "101"): {"category_name": "高考_護理師", "scope": "medical"},
                  ("115100", "103"): {"category_name": "高考_社會工作師", "scope": "boundary"}}
    subjects = {("115100", "101", norm("內外科護理學")): [
        {"exam_code": "115100", "category_code": "101", "subject_code": "0103", "scope": "medical"}]}
    a, b, c, d = list(members(source, blob, categories, subjects))
    assert a["paper_id"] == b["paper_id"] == "115100-101-0103"
    assert a["sha256"] == hashlib.sha256(b"doc").hexdigest() and b["extension"] == "txt"
    assert c["scope"] == "boundary" and c["mapping"] == "subject_needs_review"
    assert d["paper_id"] == "" and d["scope"] == "unresolved"
