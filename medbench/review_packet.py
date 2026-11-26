"""Prepare dated clinician worksheets and validate decisions against the exact reviewed content."""

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path

from .curation import SPLITS, decisions, digest, has_text, records
from .json_io import unique_keys, write_new


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def snapshot(folder, ledger, cutoff, watch):
    queue = records(folder, ledger, "queue", cutoff, watch)
    drafts = {}
    variants = {}
    result = {}
    for row in queue:
        source = row["source"]
        if source not in drafts:
            drafts[source] = read_json(folder / source)
            variants.update((item["id"], item) for item in drafts[source]["variants"])
        draft = drafts[source]
        if row["content_sha256"] != digest(draft):
            raise ValueError(f"{source}: draft changed while preparing the snapshot")
        variant = variants[row["id"]]
        result[row["id"]] = {
            "item": row,
            "editor_question": draft.get("review", {}).get("question_for_reviewer"),
            "population": draft.get("clinical_scope", {}),
            "question": variant["question"],
            "options": variant.get("options", {}),
            "answer": variant["answer"],
            "rationale": variant.get("rationale"),
            "historical_basis": variant.get("historical_basis"),
            "rubric": variant.get("rubric", []),
            "clinical_update": variant.get("clinical_update"),
            "evidence": draft.get("evidence", []),
        }
    return result


def review_content(context):
    item = {
        k: v
        for k, v in context["item"].items()
        if k
        not in {"decision", "rights_status", "clinical_status", "source_watch_status"}
    }
    return {**context, "item": item, "options": list(context["options"].items())}


def prepare(folder, ledger, cutoff, watch=None, families=()):
    entries = snapshot(folder, ledger, cutoff, watch)
    unknown = set(families) - {row["item"]["family_id"] for row in entries.values()}
    if unknown:
        raise ValueError(f"Unknown case families: {', '.join(sorted(unknown))}")
    return {
        "prepared_on": cutoff.isoformat(),
        "reviews": [
            {
                "context": context,
                "previous_decision": ledger.get(key),
                "review": {
                    "decision": None,
                    "reviewer": None,
                    "date": None,
                    "reason": None,
                    "evidence_locator": None,
                    "checked": [],
                    "approved_uses": [],
                },
            }
            for key, context in entries.items()
            if not families or context["item"]["family_id"] in families
        ],
    }


def candidate(packet, folder, log, raw, as_of, watch=None):
    """Build a reviewable complete log in memory, leaving the authoritative log untouched."""
    ledger = decisions(log, raw=raw)
    prepared = date.fromisoformat(packet["prepared_on"])
    if prepared > as_of or as_of > date.today():
        raise ValueError(
            "Packet and submission dates must be in order and no later than today"
        )
    current = snapshot(folder, ledger, as_of, watch)
    seen = set()
    accepted = []
    for sheet in packet["reviews"]:
        old = sheet["context"]
        key = old["item"]["id"]
        if key in seen or key not in current:
            raise ValueError(f"{key}: unknown or repeated worksheet")
        seen.add(key)
        assessment = sheet["review"]
        if assessment.get("decision") is None:
            continue
        case = current[key]
        if review_content(old) != review_content(case):
            raise ValueError(
                f"{key}: the reviewed content changed. Prepare a fresh worksheet."
            )
        if sheet["previous_decision"] != ledger.get(key):
            raise ValueError(
                f"{key}: a decision has been recorded since this worksheet was prepared"
            )
        item = case["item"]
        choice = assessment["decision"]
        if choice not in {"approve", "revise", "withdraw"}:
            raise ValueError(f"{key}: invalid clinician decision")
        if not all(
            has_text(assessment.get(k))
            for k in ("reviewer", "reason", "evidence_locator")
        ):
            raise ValueError(
                f"{key}: add clinician name, reason and exact evidence location"
            )
        reviewed = date.fromisoformat(assessment["date"])
        if not prepared <= reviewed <= as_of:
            raise ValueError(f"{key}: review date lies outside the review window")
        checks = assessment["checked"]
        uses = assessment["approved_uses"]
        if (
            not isinstance(checks, list)
            or not all(isinstance(c, str) for c in checks)
            or set(checks) - {"clinical", "language", "temporal"}
            or len(set(checks)) != len(checks)
            or not isinstance(uses, list)
        ):
            raise ValueError(f"{key}: invalid review checks or approved uses")
        if choice == "approve":
            expected_use = next(
                (use for use, split in SPLITS.items() if split == item["split"]), None
            )
            if (
                uses != [expected_use]
                or expected_use is None
                or item["rights_status"] != "cleared"
            ):
                raise ValueError(
                    f"{key}: the requested use requires documented rights and the assigned split"
                )
            update = case["clinical_update"]
            required = {"clinical", "language"}
            if update:
                required.add("temporal")
                if (
                    item["source_watch_status"] not in {"unchanged", "not_configured"}
                    or update["outcome"] == "conflicting_evidence"
                    or not date.fromisoformat(update["as_of"])
                    <= reviewed
                    <= as_of
                    < date.fromisoformat(update["review_due"])
                ):
                    raise ValueError(
                        f"{key}: resolve the evidence, source observation and review dates before approving"
                    )
            if not required <= set(checks) or not case["evidence"]:
                raise ValueError(
                    f"{key}: verify the required checks and cite source evidence"
                )
        elif uses:
            raise ValueError(f"{key}: only approvals can grant a use")
        accepted.append(
            {
                "variant_id": key,
                "revision": item["revision"],
                "content_sha256": item["content_sha256"],
                **{
                    k: assessment[k]
                    for k in (
                        "decision",
                        "reviewer",
                        "date",
                        "reason",
                        "evidence_locator",
                        "checked",
                        "approved_uses",
                    )
                },
            }
        )
    if not accepted:
        raise ValueError("The worksheet contains no signed decisions")
    result = raw
    if result and not result.endswith(b"\n"):
        result += b"\n"
    result += "".join(
        json.dumps(d, ensure_ascii=False) + "\n" for d in accepted
    ).encode("utf-8")
    revised = decisions(log, raw=result)
    required = {}
    for event in accepted:
        if event["decision"] == "approve":
            key = event["variant_id"]
            prefix = "clinical-" if current[key]["clinical_update"] else ""
            required.setdefault(prefix + event["approved_uses"][0], set()).add(key)
    for mode, expected in required.items():
        exported = records(folder, revised, mode, as_of, watch)
        missing = expected - {row["id"] for row in exported}
        if missing:
            raise ValueError(
                f"Current curation rules did not accept these approvals: {sorted(missing)}"
            )
    return result


def markdown(packet):
    """Render a portable working copy for the public development draft review."""
    all_rows = [sheet["context"] for sheet in packet["reviews"]]
    entries = [c for c in all_rows if c["item"]["split"] == "public_development"]
    families = {c["item"]["family_id"] for c in entries}
    statuses = Counter(c["item"]["decision"] for c in entries)
    out = [
        f"# 雙語病例審查本（{packet['prepared_on']}）",
        "",
        f"本次公開開發審查涵蓋 {len(families)} 個病例家族、{len(entries)} 個語言版本。具名核准 {statuses['approve']} 筆。",
        "可在對話中回覆「題號、修訂版、核准／修訂／撤回、原句或理由、來源定位」。只完成一種語言時，請註明該語言。",
        "審查臨床內容時，核對族群、地區、日期、可接受答案與詳解。建議修訂可直接貼出希望取代的文字。",
        "",
        "| 病例 | 語言版本 |",
        "|---|---|",
    ]
    by_concept = {}
    for c in entries:
        row = c["item"]
        by_concept.setdefault(Path(row["source"]).stem, []).append(
            f"[{row['lang']}](#{row['id'].lower()})"
        )
    out.extend(
        f"| {concept} | {' · '.join(links)} |" for concept, links in by_concept.items()
    )
    out.append("")
    for c in entries:
        row = c["item"]
        now = c["clinical_update"]
        out += [
            f"## {row['id']}",
            "",
            f"修訂 {row['revision']} · `{row['content_sha256'][:12]}` · `{row['decision']}` · 家族 `{row['family_id']}`",
            "",
        ]
        if c["editor_question"]:
            out += [c["editor_question"], ""]
        if c["historical_basis"]:
            history = c["historical_basis"]
            out += [
                f"**歷史判讀日 {history['as_of']}**",
                "",
                c["question"],
                "兩個時點共用下方選項。" if c["options"] else "",
                "",
                f"編者擬答 **{c['answer']}**。{c['rationale'] or ''} [{history['locator']}]({history['url']})",
                "",
            ]
        target = now or c
        if now:
            out += [f"**臨床判讀日 {now['as_of']}，地區 {now['jurisdiction']}**", ""]
        out += [target["question"], ""]
        if c["options"]:
            out += [
                f"- {label}．{option}" for label, option in c["options"].items()
            ] + [""]
        out += [f"**編者擬答**　{target['answer']}", ""]
        if target.get("rationale"):
            out += [target["rationale"], ""]
        evidence_by_id = {s.get("id"): s for s in c["evidence"] if s.get("id")}
        for claim in target.get("claims", []):
            refs = " · ".join(
                f"[{eid}]({evidence_by_id[eid]['url']})"
                for eid in claim["evidence_ids"]
            )
            out.append(f"- {claim['text']} {refs}")
        out += [f"- {line}" for line in target.get("rubric", [])]
        if target.get("claims") or target.get("rubric"):
            out.append("")
        for source in c["evidence"]:
            if not now or source.get("id") in now["evidence_ids"]:
                out.append(
                    f"- {source['locator']} [{source.get('title', source['url'])}]({source['url']})"
                )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "candidate"))
    parser.add_argument("--drafts", type=Path, default=Path("drafts"))
    parser.add_argument(
        "--decisions", type=Path, default=Path("docs/review/decisions.jsonl")
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--watch-report", type=Path)
    parser.add_argument("--family", action="append", default=[])
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.drafts.is_dir() or args.as_of > date.today():
            raise ValueError(
                "Use an existing draft folder and a date no later than today"
            )
        if args.out.resolve() == args.decisions.resolve():
            raise ValueError(
                "Choose a separate output for the worksheet or candidate log"
            )
        report = read_json(args.watch_report) if args.watch_report else None
        raw = args.decisions.read_bytes() if args.decisions.is_file() else b""
        if args.action == "prepare":
            if args.packet:
                raise ValueError(
                    "Use --packet only when validating completed worksheets"
                )
            forms = prepare(
                args.drafts,
                decisions(args.decisions, args.as_of, raw=raw),
                args.as_of,
                report,
                args.family,
            )
            payload = (
                markdown(forms)
                if args.markdown
                else json.dumps(forms, ensure_ascii=False, indent=2) + "\n"
            )
            output = payload.encode("utf-8")
        else:
            if not args.packet or args.markdown or args.family:
                raise ValueError("Candidate validation requires a completed --packet")
            output = candidate(
                read_json(args.packet),
                args.drafts,
                args.decisions,
                raw,
                args.as_of,
                report,
            )
        write_new(args.out, output)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
