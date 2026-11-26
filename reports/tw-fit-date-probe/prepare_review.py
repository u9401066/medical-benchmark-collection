"""Prepare or verify the public FIT clinician-review exercise without running inference."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from medbench.batch_probe import unique_keys  # noqa: E402
from medbench.clinical_score import prediction_digest  # noqa: E402
from medbench.evidence_audit import worksheet  # noqa: E402
from run import assignment, verify  # noqa: E402


def prepare():
    questions = {
        meta["id"]: message
        for meta, message, _ in assignment()
        if meta["period"] == "current"
    }
    references = {}
    for path in sorted((ROOT / "drafts").glob("mbc-tw-fit-*.json")):
        draft = json.loads(path.read_bytes(), object_pairs_hook=unique_keys)
        sources = {s["id"]: s for s in draft["evidence"]}
        for v in draft["variants"]:
            u = v["clinical_update"]
            references[v["id"]] = {
                "lang": v["lang"],
                "jurisdiction": u["jurisdiction"],
                "clinical_as_of": u["as_of"],
                "messages": [{"role": "user", "content": questions[v["id"]]}],
                "claims": u["claims"],
                "evidence": [sources[k] for k in u["evidence_ids"]],
            }

    assignments = []
    for filename, constrained in (
        ("responses.json", False),
        ("responses-constrained.json", True),
    ):
        data = (HERE / filename).read_bytes()
        report = json.loads(data, object_pairs_hook=unique_keys)
        verify(report, constrain=constrained)
        for i, row in enumerate(report["responses"]):
            if row["period"] == "current":
                source = {
                    "report": filename,
                    "report_sha256": hashlib.sha256(data).hexdigest(),
                    "response_index": i,
                    "variant_id": row["id"],
                    "model": report["parameters"]["model"],
                    "response_format": report["parameters"]["response_format"]["type"],
                    "prompt_sha256": row["prompt_sha256"],
                    "response_sha256": row["response_sha256"],
                    "parsed_choice": row["choice"],
                }
                assignments.append((row, source))

    rng = random.Random(2026112605)
    codes = rng.sample(range(10000, 100000), len(assignments))
    rng.shuffle(assignments)
    sheets, keys = [], []
    for code, (row, source) in zip(codes, assignments, strict=True):
        review_id = f"R-{code}"
        item = {
            **references[row["id"]],
            "id": review_id,
            "content_sha256": row["draft_sha256"],
        }
        choice = row["choice"]
        response_type = "parse_error" if choice is None else choice
        prediction = {
            "id": review_id,
            "content_sha256": row["draft_sha256"],
            "text": row["raw"],
        }
        if choice in ("A", "B", "C", "D"):
            prediction.update(response_type="select", selected_options=[choice])
        else:
            prediction["response_type"] = response_type
        signature = prediction_digest(prediction)
        sheet = worksheet(item, prediction, signature)
        sheet["use"] = "public_development_review_practice"
        sheets.append(sheet)
        keys.append(
            {
                "id": review_id,
                **source,
                "draft_sha256": row["draft_sha256"],
                "prediction_sha256": signature,
            }
        )
    return {"review-worksheet.jsonl": sheets, "review-key.jsonl": keys}


def handout(sheets):
    lines = [
        "# 臺灣公費篩檢回答理由審閱表",
        "",
        "12 份原始回答均待審。請以題號記錄意見。下列參考主張為編者草稿，來源定位可供覆核。",
        "請先閱讀[填寫說明與定位練習](review-guide.md)。",
    ]
    for sheet in sheets:
        context = sheet["context"]
        lines.extend(
            [
                "",
                f"## {sheet['id']}",
                "",
                f"語言 `{context['lang']}`，適用地區 {context['jurisdiction']}，依據日期 {context['clinical_as_of']}。",
                "",
                "**題目及作答規則**",
                "",
                "```text",
                context["question"],
                "```",
                "",
                "**回答原文**",
                "",
                "```text",
                context["response"],
                "```",
                "",
                "**編者參考主張**",
                "",
            ]
        )
        for i, claim in enumerate(context["reference_claims"], 1):
            refs = "、".join(claim["evidence_ids"])
            lines.append(f"{i}. {claim['text']}（{refs}）")
        lines.extend(["", "**核對來源**", ""])
        for source in context["evidence"]:
            lines.append(
                f"- `{source['id']}`　{source['version']}　{source['locator']} "
                f"[{source['title']}]({source['url']})"
            )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--out-dir", type=Path, help="Write a new worksheet and coordinator key"
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check the published blank worksheet and key",
    )
    args = parser.parse_args()
    packet = prepare()
    folder = HERE if args.check else args.out_dir
    payloads = {
        folder / name: "".join(
            json.dumps(row, ensure_ascii=False) + "\n" for row in rows
        ).encode()
        for name, rows in packet.items()
    }
    payloads[folder / "review-worksheet.md"] = handout(
        packet["review-worksheet.jsonl"]
    ).encode()
    if args.check:
        for path, content in payloads.items():
            if path.read_bytes() != content:
                parser.exit(1, f"Published exercise differs: {path.name}\n")
    else:
        payloads[folder / "review-guide.md"] = (HERE / "review-guide.md").read_bytes()
        if any(path.exists() for path in payloads):
            parser.error("Choose a folder without an existing worksheet or key")
        folder.mkdir(parents=True, exist_ok=True)
        for path, content in payloads.items():
            with path.open("xb") as output:
                output.write(content)
    print(f"{len(packet['review-worksheet.jsonl'])} pending worksheets")


if __name__ == "__main__":
    main()
