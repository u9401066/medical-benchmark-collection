import io
import hashlib
import zipfile

from medbench.moex_bundle import archived, bundle_path, fetch_batch, groups, match_bundle


def row(cat="004", subject="c024", kind="Q"):
    return {"exam_name": "專技高考", "exam_code": "081010", "category_name": "醫師", "category_code": cat,
            "subject_name": "生理學", "subject_code": subject, "asset_type": kind,
            "source_url": f"https://wwwq.moex.gov.tw/exam/file?t={kind}&c={cat}&s={subject}"}


def bundle(page, *members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("考畢試題/考畢試題.html", page.encode())
        for member in members:
            z.writestr("考畢試題/" + member, b"%PDF-1.4\n%%EOF")
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


def test_official_zip_requires_exam_category_subject_code_and_role():
    question = "081010_c024_生理學.pdf"
    answer = "081010_ANSc024_生理學.pdf"
    html = f"""<ul class='link_1'><li><div>專技高考</div></li></ul>
<ul class='link_2'><li><div>醫師</div></li></ul>
<ul class='link_3'><li><div>生理學</div><a href='{question}'>試題</a><a href='{answer}'>答案</a></li></ul>"""
    q, s = row(), row(kind="S")
    with bundle(html, question, answer) as z:
        assert set(match_bundle(z, [q, s])) == {q["source_url"], s["source_url"]}
        assert not match_bundle(z, [{**q, "category_name": "牙醫師"}])
        assert not match_bundle(z, [{**q, "subject_code": "c025"}])
        assert not match_bundle(z, [{**q, "exam_name": "普通考試"}])
        assert not match_bundle(z, [q, {**q, "source_url": q["source_url"] + "&q=2"}])
    with bundle(html.replace(">試題</a>", ">答案</a>"), question, answer) as z:
        assert q["source_url"] not in match_bundle(z, [q, s])


def test_each_batch_limits_eight_and_avoids_repeated_subject_codes_across_categories():
    papers = [row(subject=str(n).zfill(4)) for n in range(10)]
    papers.extend([row(cat="005", subject="0000"), row(cat="005", subject="0000", kind="S")])
    batches = list(groups(papers))
    assert sum(len(b) for b in batches) == len(papers)
    for b in batches:
        subject_codes = {r["subject_code"] for r in b}
        assert len(subject_codes) <= 8
        assert len(subject_codes) == len({(r["category_code"], r["subject_code"]) for r in b})


def test_receipt_resolves_to_exact_original_zip_and_member(tmp_path):
    q = row()
    filename = "081010_c024_生理學.pdf"
    page = f"""<ul class='link_1'><div>專技高考</div><ul class='link_2'><div>醫師</div>
<ul class='link_3'><div>生理學</div><a href='{filename}'>試題</a>"""
    with bundle(page, filename) as z:
        original = z.fp.getvalue()

    class Source:
        def download(self, rows):
            return original, "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx?e=081010&y=1992"

    receipts, error = fetch_batch([q], tmp_path, Source())
    result = receipts[q["source_url"]]
    assert not error and archived(tmp_path, q["source_url"])
    sha = hashlib.sha256(original).hexdigest()
    path = bundle_path(tmp_path, sha)
    assert result["bundle_sha256"] == sha and path.read_bytes() == original
    with zipfile.ZipFile(path) as z:
        assert hashlib.sha256(z.read(result["bundle_member"])).hexdigest() == result["sha256"]
    path.unlink()
    assert not archived(tmp_path, q["source_url"])


def test_mismatching_prior_digest_rechecks_individual_official_url(tmp_path, monkeypatch):
    q = {**row(), "prior_sha256": "0" * 64}
    filename = "081010_c024_生理學.pdf"
    page = f"""<ul class='link_1'><div>專技高考</div><ul class='link_2'><div>醫師</div>
<ul class='link_3'><div>生理學</div><a href='{filename}'>試題</a>"""
    with bundle(page, filename) as z:
        original = z.fp.getvalue()

    class Source:
        client = None

        def download(self, rows):
            return original, "https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx?e=081010&y=1992"

        def wait(self):
            pass

    calls = []
    def direct(row, cache, client):
        calls.append(row["source_url"])
        return {"retrieval_method": "direct"}
    monkeypatch.setattr("medbench.moex_bundle.archive.acquire", direct)
    receipts, _ = fetch_batch([q], tmp_path, Source())
    assert calls == [q["source_url"]]
    assert receipts[q["source_url"]]["retrieval_method"] == "direct"
