"""List draft variants for human review or export reviewed examples for a specific use."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path


def digest(draft):
    content = {k: v for k, v in draft.items() if k != "review"}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def decisions(path):
    if not path.is_file():
        return {}
    latest = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        reviewed = date.fromisoformat(event["date"])
        if event["decision"] not in {"approve", "revise", "withdraw"} or not all(
            str(event.get(k) or "").strip() for k in ("reviewer", "reason", "evidence_locator", "variant_id", "content_sha256")
        ) or not isinstance(event["revision"], int) or event["revision"] < 1:
            raise ValueError("Incomplete review event")
        if event["decision"] == "approve" and not {"clinical", "language"} <= set(event.get("checked", [])):
            raise ValueError("Approval must cover clinical content and the variant's language")
        key = event["variant_id"]
        if key in latest and reviewed < date.fromisoformat(latest[key]["date"]):
            raise ValueError("Review events must be recorded in date order for " + key)
        latest[key] = event
    return latest


def records(folder, events, mode):
    if mode not in {"queue", "train", "evaluation", "development"}:
        raise ValueError("Unknown curation mode")
    seen, families = set(), {}
    result = []
    for path in sorted(folder.glob("*.json")):
        draft = json.loads(path.read_text(encoding="utf-8"))
        signature = digest(draft)
        family = draft.get("family_id", draft["concept_id"])
        split = draft["split"]
        if family in families and families[family] != split:
            raise ValueError("The same case family appears in multiple splits: " + family)
        families[family] = split
        for variant in draft["variants"]:
            vid = variant["id"]
            if vid in seen:
                raise ValueError("Duplicate variant ID: " + vid)
            seen.add(vid)
            event = events.get(vid)
            status = "pending"
            if event:
                status = event["decision"] if (event["content_sha256"] == signature
                          and event["revision"] == draft["revision"]) else "stale_review"
            row = {"id": vid, "family_id": family, "revision": draft["revision"], "content_sha256": signature,
                   "lang": variant["lang"], "source": path.name, "split": split, "kind": draft["kind"],
                   "decision": status}
            if mode == "queue":
                result.append(row)
                continue
            expected_split = {"train": "train", "evaluation": "heldout_evaluation", "development": "public_development"}[mode]
            if (status != "approve" or split != expected_split or mode not in event.get("approved_uses", [])
                    or mode not in draft.get("permitted_uses", []) or not draft.get("evidence")):
                continue
            prompt = variant["question"]
            if variant.get("options"):
                prompt += "\n" + "\n".join(f"{k}. {v}" for k, v in variant["options"].items())
            answer = variant["answer"] + ("\n" + variant["rationale"] if variant.get("rationale") else "")
            row.update(reviewer=event["reviewer"], decision_date=event["date"], decision_reason=event["reason"],
                       evidence=draft["evidence"], rubric=variant.get("rubric", []),
                       messages=[{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
            result.append(row)
    if events.keys() - seen:
        raise ValueError("Review record references a variant missing from the draft collection")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("queue", "train", "evaluation", "development"))
    parser.add_argument("--drafts", type=Path, default=Path("drafts"))
    parser.add_argument("--decisions", type=Path, default=Path("docs/review/decisions.jsonl"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = records(args.drafts, decisions(args.decisions), args.mode)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        from .moex_archive import atomic
        atomic(args.out, text.encode())
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
