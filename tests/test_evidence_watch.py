import gzip
import hashlib
import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError

import pytest

from medbench import evidence_watch
from medbench.evidence_watch import check


URL = "https://agency.example/guidance"
XPATH = "//p[@id='eligibility']"


def test_gzipped_html_passage_matches_uncompressed_source(monkeypatch, tmp_path):
    body = "<html><p id='eligibility'>資格 45</p></html>".encode()
    expected = hashlib.sha256("資格 45".encode()).hexdigest()
    (tmp_path / "draft.json").write_text(json.dumps({
        "concept_id": "case", "evidence": [{"url": URL, "watch_xpath": XPATH, "passage_sha256": expected}]
    }))
    response = BytesIO(gzip.compress(body))
    response.geturl = lambda: URL
    response.headers = Message()
    response.headers["Content-Encoding"] = "GZip"
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    monkeypatch.setattr(evidence_watch, "urlopen", lambda *a, **kw: response)
    row, = check(tmp_path)["sources"]
    assert row["status"] == "unchanged" and row["observed_sha256"] == expected


@pytest.mark.parametrize(("content", "encoding", "message"), [
    (b"x" * 65, "identity", "response exceeds"),
    (gzip.compress(b"x" * 65), "gzip", "Decoded source exceeds"),
    (gzip.compress(b"short")[:-4], "gzip", "Invalid gzip"),
    (b"other", "br", "Unsupported"),
])
def test_encoding_and_size_failures_never_reach_html_parser(monkeypatch, content, encoding, message):
    monkeypatch.setattr(evidence_watch, "MAX_HTML_BYTES", 64)
    response = BytesIO(content)
    response.headers = {"Content-Encoding": encoding}
    with pytest.raises(ValueError, match=message):
        evidence_watch.read_html_body(response)


def test_fetch_retries_timeouts_and_passes_through_definitive_failures(monkeypatch):
    delays = []
    content = BytesIO(b"page")
    content.geturl = lambda: URL
    content.headers = Message()
    content.headers["Content-Type"] = "text/html; charset=utf-8"
    replies = iter([TimeoutError(), content, HTTPError(URL, 404, "missing", {}, None)])

    def open_url(*args, **kwargs):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(evidence_watch, "urlopen", open_url)
    monkeypatch.setattr(evidence_watch.time, "sleep", delays.append)
    assert evidence_watch.fetch(URL) == (b"page", "utf-8")
    with pytest.raises(HTTPError):
        evidence_watch.fetch(URL)
    assert delays == [1]


def test_tracks_only_reviewed_passage_and_preserves_affected_families(tmp_path):
    expected = hashlib.sha256("資格 45".encode()).hexdigest()
    for concept in ("first", "second", "third"):
        draft = {
            "concept_id": concept,
            "evidence": [
                {"url": URL, "watch_xpath": XPATH, "passage_sha256": expected},
            ],
        }
        if concept in {"first", "third"}:
            draft["family_id"] = "shared"
        (tmp_path / f"{concept}.json").write_text(json.dumps(draft), encoding="utf-8")

    def scan(fragment):
        calls = []

        def download(url):
            calls.append(url)
            return (
                "<html><nav>unrelated</nav>" + fragment + "</html>"
            ).encode(), "utf-8"

        rows = check(tmp_path, download)["sources"]
        assert (
            calls == [URL]
            and len(rows) == 1
            and rows[0]["concepts"] == ["first", "second", "third"]
            and rows[0]["family_ids"] == ["second", "shared"]
        )
        return rows[0]

    assert scan("<p id='eligibility'>資格  \n 45</p>")["status"] == "unchanged"
    assert scan("<p id='eligibility'>資格 50</p>")["status"] == "changed"
    for fragment in (
        "<p>missing</p>",
        "<p id='eligibility'></p>",
        "<p id='eligibility'>資格 45</p><p id='eligibility'>資格 50</p>",
    ):
        assert scan(fragment)["status"] == "unavailable"

    def offline(_):
        raise TimeoutError("timed out")

    assert check(tmp_path, offline)["sources"][0]["status"] == "unavailable"
