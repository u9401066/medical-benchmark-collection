"""Run or replay the six public, paired-date Taiwan FIT draft variants."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from medbench.batch_probe import unique_keys  # noqa: E402
from medbench.curation import digest, rights_status  # noqa: E402
from medbench.moex_archive import atomic  # noqa: E402


SEED = 20261126
PROTOCOL = {
    "temperature": 0,
    "seed": SEED,
    "max_tokens": 256,
    "response_format": {"type": "json_object"},
    "stream": False,
}
CONSTRAINED_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "fit_date_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "choice": {
                    "type": "string",
                    "enum": [
                        "A",
                        "B",
                        "C",
                        "D",
                        "no_valid_option",
                        "insufficient_information",
                        "abstain",
                    ],
                },
                "reason": {"type": "string", "minLength": 1},
            },
            "required": ["choice", "reason"],
            "additionalProperties": False,
        },
    },
}
SUFFIX = {
    "zh-TW": "請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。",
    "en-US": "Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.",
}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assignment():
    rows = []
    for number in (1, 2, 3):
        path = ROOT / "drafts" / f"mbc-tw-fit-{number:04d}.json"
        draft = json.loads(path.read_bytes())
        if (
            draft["split"] != "public_development"
            or "development" not in draft["permitted_uses"]
            or rights_status(
                draft.get("source_rights"), "development", date(2026, 11, 26)
            )
            != "cleared"
        ):
            raise ValueError(f"Missing public development permission: {path.name}")
        variants = draft["variants"]
        identities = {(v["lang"], v["id"]) for v in variants}
        if len(variants) != 2 or identities != {
            (lang, f"{path.stem}-{lang}") for lang in SUFFIX
        }:
            raise ValueError(f"Expected two paired language variants: {path.name}")
        for variant in variants:
            if (
                variant.get("historical_basis", {}).get("comparison")
                != "same_decision_single_option"
                or variant["historical_basis"]["as_of"] != "2024-12-31"
                or variant["clinical_update"]["as_of"] != "2026-11-26"
                or variant["clinical_update"]["jurisdiction"] != "TW"
            ):
                raise ValueError(
                    f"Expected the paired Taiwan policy dates: {variant['id']}"
                )
            for period, question in (
                ("historical", variant["question"]),
                ("current", variant["clinical_update"]["question"]),
            ):
                options = variant["options"]
                message = (
                    question
                    + "\n"
                    + "\n".join(f"{k}. {v}" for k, v in options.items())
                    + "\n\n"
                    + SUFFIX[variant["lang"]]
                )
                rows.append(
                    (
                        {
                            "id": variant["id"],
                            "period": period,
                            "draft_sha256": digest(draft),
                            "prompt_sha256": sha(message),
                        },
                        message,
                        list(options),
                    )
                )
    random.Random(SEED).shuffle(rows)
    return rows


def parse(raw, finish, labels):
    if finish != "stop":
        return None
    try:
        obj = json.loads(raw, object_pairs_hook=unique_keys)
        if (
            isinstance(obj, dict)
            and isinstance(obj.get("reason"), str)
            and obj["reason"].strip()
            and obj.get("choice")
            in [*labels, "no_valid_option", "insufficient_information", "abstain"]
        ):
            return obj["choice"]
    except (TypeError, ValueError):
        pass
    return None


def parameters_for(model, constrain):
    return {
        **PROTOCOL,
        "model": model,
        "response_format": CONSTRAINED_FORMAT
        if constrain
        else PROTOCOL["response_format"],
    }


def verify(report, *, constrain=False):
    parameters = report.get("parameters")
    if (
        not isinstance(parameters, dict)
        or not isinstance(parameters.get("model"), str)
        or not parameters["model"].strip()
    ):
        raise ValueError("Missing protocol parameters or model ID")
    if json.dumps(parameters, sort_keys=True) != json.dumps(
        parameters_for(parameters["model"], constrain), sort_keys=True
    ):
        raise ValueError("Reported inference parameters differ from the fixed protocol")
    expected = assignment()
    if len(report["responses"]) != len(expected):
        raise ValueError("Incomplete assignment")
    counts, pairs = Counter(), defaultdict(dict)
    for (meta, _, labels), row in zip(expected, report["responses"], strict=True):
        for k, value in meta.items():
            if row[k] != value:
                raise ValueError(f"Wrong prompt, order, or draft version: {meta['id']}")
        if sha(row["raw"]) != row["response_sha256"]:
            raise ValueError("Response hash mismatch")
        choice = parse(row["raw"], row["finish_reason"], labels)
        if row["choice"] != choice:
            raise ValueError("Stored choice differs from the response")
        counts[(row["period"], choice)] += 1
        pairs[row["id"]][row["period"]] = choice
    for variant_id, choices in sorted(pairs.items()):
        print(variant_id, choices["historical"], choices["current"])
    print(
        "Assigned",
        len(expected),
        "parsed",
        sum(n for (_, choice), n in counts.items() if choice is not None),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", type=Path, metavar="NEW_REPORT")
    mode.add_argument("--verify", type=Path, metavar="REPORT")
    parser.add_argument("--url", default="http://127.0.0.1:18138")
    parser.add_argument("--model", default="qwen2.5-1.5b-local")
    parser.add_argument(
        "--constrain",
        action="store_true",
        help="Run or verify the strict JSON Schema condition",
    )
    args = parser.parse_args()
    if args.verify:
        verify(
            json.loads(args.verify.read_bytes(), object_pairs_hook=unique_keys),
            constrain=args.constrain,
        )
        return
    if args.run.exists():
        parser.error("Choose a new report path to preserve the recorded run")
    parameters = parameters_for(args.model, args.constrain)
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": parameters,
        "responses": [],
    }
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=120) as client:
        for metadata, message, labels in assignment():
            response = client.post(
                "/v1/chat/completions",
                json={**parameters, "messages": [{"role": "user", "content": message}]},
            )
            response.raise_for_status()
            data = response.json()
            item = data["choices"][0]
            raw, finish = item["message"]["content"], item["finish_reason"]
            report["responses"].append(
                {
                    **metadata,
                    "raw": raw,
                    "response_sha256": sha(raw),
                    "finish_reason": finish,
                    "choice": parse(raw, finish, labels),
                    "usage": data.get("usage"),
                }
            )
    verify(report, constrain=args.constrain)
    atomic(
        args.run,
        (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


if __name__ == "__main__":
    main()
