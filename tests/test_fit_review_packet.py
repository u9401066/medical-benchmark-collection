from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from medbench.clinical_score import validate_gold
from medbench.evidence_audit import span_key


PACKET = Path(__file__).resolve().parents[1] / "reports" / "tw-fit-date-probe"


def test_public_packet_binds_all_current_answers_and_preserves_pending_state():
    sheets, keys = (
        [json.loads(line) for line in (PACKET / name).read_bytes().splitlines()]
        for name in ("review-worksheet.jsonl", "review-key.jsonl")
    )
    assert len(sheets) == len(keys) == len({s["id"] for s in sheets}) == 12
    observations = Counter()
    opaque_view = (PACKET / "review-worksheet.md").read_text("utf-8")
    for sheet, key in zip(sheets, keys, strict=True):
        assert sheet["id"] == key["id"] and re.fullmatch(r"R-\d{5}", sheet["id"])
        assert (
            sheet["state"] == "pending" and sheet["reviewer"] is sheet["date"] is None
        )
        assert sheet["inventory_complete"] is False and not any(
            x["status"] for x in sheet["reference_claims"]
        )
        assert sheet["use"] == "public_development_review_practice"
        assert sheet["prediction_sha256"] == key["prediction_sha256"]
        assert not any(
            k in sheet
            for k in ("model", "parameters", "response_format", "parsed_choice")
        )
        for identity in (key["model"], key["response_format"]):
            assert identity not in json.dumps(sheet) and identity not in opaque_view
        report = (PACKET / key["report"]).read_bytes()
        assert hashlib.sha256(report).hexdigest() == key["report_sha256"]
        original = json.loads(report)["responses"][key["response_index"]]
        assert original["id"] == key["variant_id"] and original["period"] == "current"
        context = sheet["context"]
        assert original["raw"] == context["response"] and original["raw"] in opaque_view
        assert (
            hashlib.sha256(context["response"].encode()).hexdigest()
            == original["response_sha256"]
            == key["response_sha256"]
        )
        assert (
            hashlib.sha256(context["question"].encode()).hexdigest()
            == original["prompt_sha256"]
        )
        assert len(context["reference_claims"]) == len(sheet["reference_claims"]) > 0
        assert all(s["locator"] and s["url"] for s in context["evidence"])
        observations[(key["response_format"], key["variant_id"])] += 1
        if original["choice"] is None:
            assert context["lang"] == "en-US" and context["response"]
        with pytest.raises(ValueError, match="approved"):
            validate_gold(sheet, date(2026, 11, 26))
    assert len(observations) == 12 and all(v == 1 for v in observations.values())
    assert sum(k["parsed_choice"] is None for k in keys) == 3
    by_id = {s["id"]: s["context"]["response"] for s in sheets}
    examples = re.findall(
        r"^\| (R-\d+) \| (\d+) \| (\d+) \| (.*?) \|$",
        (PACKET / "review-guide.md").read_text("utf-8"),
        re.M,
    )
    assert len(examples) == 2
    for code, start, end, quote in examples:
        span_key({"start": int(start), "end": int(end), "quote": quote}, by_id[code])


def test_rebuild_is_reproducible_and_preserves_completed_work(tmp_path):
    tool = [sys.executable, "-B", str(PACKET / "prepare_review.py")]
    subprocess.run([*tool, "--check"], check=True, capture_output=True)
    out = tmp_path / "new"
    subprocess.run([*tool, "--out-dir", str(out)], check=True, capture_output=True)
    for p in out.iterdir():
        assert p.read_bytes() == (PACKET / p.name).read_bytes()
    worksheet = out / "review-worksheet.jsonl"
    worksheet.write_bytes(b"review in progress")
    attempted = subprocess.run([*tool, "--out-dir", str(out)], capture_output=True)
    assert attempted.returncode != 0 and worksheet.read_bytes() == b"review in progress"
