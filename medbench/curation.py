"""List draft variants for human review or export reviewed examples for a specific use."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


SPLITS = {"train": "train", "evaluation": "heldout_evaluation", "development": "public_development"}
MODES = ("queue", *SPLITS, *("clinical-" + use for use in SPLITS))
OUTCOMES = {"single_valid_option", "multiple_valid_options", "no_valid_option",
            "insufficient_information", "conflicting_evidence", "free_text"}


def digest(draft):
    content = {k: v for k, v in draft.items() if k != "review"}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def decisions(path, as_of=None):
    if not path.is_file():
        return {}
    latest = {}
    last_date = {}
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
        if key in last_date and reviewed < last_date[key]:
            raise ValueError("Review events must be recorded in date order for " + key)
        last_date[key] = reviewed
        if as_of is None or reviewed <= as_of:
            latest[key] = event
    return latest


def has_text(value):
    return isinstance(value, str) and bool(value.strip())


def distinct_references(values, allowed):
    return (isinstance(values, list)
            and all(has_text(value) and value in allowed for value in values)
            and len(set(values)) == len(values))


def validate_historical_option(reference, offered, assessed):
    """Validate an explicitly comparable, earlier single answer on the same option set."""
    if not isinstance(reference, dict) or not all(
        has_text(reference.get(k)) for k in ("label", "as_of", "url", "locator")
    ):
        raise ValueError("A historical option requires a label, date, source URL and locator")
    url = urlsplit(reference["url"])
    if (reference["label"] not in offered or date.fromisoformat(reference["as_of"]) >= assessed
            or url.scheme not in {"http", "https"} or not url.hostname):
        raise ValueError("The historical option must be sourced, offered and strictly earlier")


def rights_status(record, use, as_of):
    """Check the documented permission for this use independently of clinical review."""
    if record is None:
        return "not_documented"
    if not isinstance(record, dict):
        return "incomplete"
    status = record.get("status")
    if status in ("pending", "denied"):
        return status
    origin = record.get("origin")
    if (status != "cleared" or origin not in ("project_original", "third_party")
            or not all(has_text(record.get(k)) for k in ("attribution", "scope"))):
        return "incomplete"
    try:
        checked = date.fromisoformat(record["checked_on"])
        if origin == "third_party":
            if not all(has_text(record.get(k)) for k in ("version", "license", "source_url", "terms_url")):
                return "incomplete"
            for key in ("source_url", "terms_url"):
                url = urlsplit(record[key])
                if url.scheme not in ("http", "https") or not url.hostname:
                    return "incomplete"
    except (KeyError, TypeError, ValueError):
        return "incomplete"
    if checked > as_of:
        return "future_check"
    uses = record.get("allowed_uses")
    if not uses or not distinct_references(uses, SPLITS):
        return "incomplete"
    return "cleared" if use in uses else "use_not_cleared"


def clinical_sources(draft, variant):
    """Validate the proposed judgment independently of whether anyone has approved it."""
    update = variant["clinical_update"]
    vid = variant["id"]
    if not isinstance(update, dict) or not all(
        has_text(update.get(k)) for k in ("as_of", "review_due", "jurisdiction", "question", "answer", "rationale")
    ):
        raise ValueError(f"{vid}: incomplete clinical_update")
    assessed, due = date.fromisoformat(update["as_of"]), date.fromisoformat(update["review_due"])
    if due <= assessed:
        raise ValueError(f"{vid}: review_due must be later than as_of")
    historical = variant.get("historical_basis")
    if historical is not None:
        if not isinstance(historical, dict) or not all(has_text(historical.get(k)) for k in ("as_of", "url", "locator")):
            raise ValueError(f"{vid}: historical_basis requires as_of, URL, and locator")
        source_url = urlsplit(historical["url"])
        if (date.fromisoformat(historical["as_of"]) > assessed
                or source_url.scheme not in {"http", "https"} or not source_url.hostname):
            raise ValueError(f"{vid}: invalid historical source date or URL")
        if "comparison" in historical:
            if historical["comparison"] != "same_decision_single_option":
                raise ValueError(f"{vid}: unknown historical comparison")
            validate_historical_option({**historical, "label": variant.get("answer")},
                                       variant.get("options") or {}, assessed)
    outcome = update.get("outcome")
    labels = update.get("valid_options")
    options = variant.get("options", {})
    if outcome not in OUTCOMES or not distinct_references(labels, options):
        raise ValueError(f"{vid}: invalid clinical outcome or valid_options")
    rule = update.get("selection_rule")
    if outcome == "single_valid_option":
        if rule not in (None, "any_one") or len(labels) != 1 or update["answer"] != labels[0]:
            raise ValueError(f"{vid}: single option answer must match valid_options")
    elif outcome == "multiple_valid_options":
        if len(labels) < 2 or rule not in {"any_one", "all_required"}:
            raise ValueError(f"{vid}: multiple valid options require selection_rule any_one or all_required")
        if rule == "any_one" and update["answer"] not in labels:
            raise ValueError(f"{vid}: any_one requires one explicitly chosen representative answer")
        if rule == "all_required":
            selected = update["answer"].split(", ")
            if len(selected) != len(labels) or not distinct_references(selected, labels):
                raise ValueError(f"{vid}: all_required answer must contain every valid option exactly once")
    elif rule is not None:
        raise ValueError(f"{vid}: selection_rule requires an option-selection outcome")
    elif labels or (outcome == "no_valid_option" and not options) or (outcome == "free_text" and options):
        raise ValueError(f"{vid}: outcome is incompatible with the question options")
    elif update["answer"].strip() in options:
        raise ValueError(f"{vid}: abstention cannot select an option")

    evidence = {}
    for source in draft.get("evidence", []):
        eid = source.get("id")
        if eid is not None:
            if not has_text(eid) or eid in evidence:
                raise ValueError(f"{vid}: invalid or duplicate evidence id")
            evidence[eid] = source
    ids = update.get("evidence_ids")
    if not ids or not distinct_references(ids, evidence):
        raise ValueError(f"{vid}: evidence_ids must identify distinct sources in draft.evidence")
    if "claims" in update:
        claims = update["claims"]
        if not isinstance(claims, list) or not claims:
            raise ValueError(f"{vid}: claims must be a nonempty list when provided")
        for claim in claims:
            if not isinstance(claim, dict) or not has_text(claim.get("text")):
                raise ValueError(f"{vid}: each claim requires nonempty text")
            refs = claim.get("evidence_ids")
            if not refs or not distinct_references(refs, ids):
                raise ValueError(f"{vid}: claim evidence_ids must refer to distinct sources cited by this clinical_update")
    sources = [evidence[k] for k in ids]
    for source in sources:
        if not all(has_text(source.get(k)) for k in ("url", "locator", "version")):
            raise ValueError(f"{vid}: current evidence requires a URL, locator, and version")
        url = urlsplit(source["url"])
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise ValueError(f"{vid}: current evidence URL must identify an HTTP(S) source")
        if "published_on" in source and date.fromisoformat(source["published_on"]) > assessed:
            raise ValueError(f"{vid}: cited source was published after clinical as_of")
        if "watch_xpath" in source and not (
            has_text(source["watch_xpath"]) and isinstance(source.get("passage_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", source["passage_sha256"])
        ):
            raise ValueError(f"{vid}: watched evidence requires an XPath and a lowercase SHA-256")
    return sources


def watch_index(report, as_of):
    if report is None or report.get("checked_on") != as_of.isoformat():
        return {}
    index = {}
    for entry in report["sources"]:
        key = (entry["url"], entry["watch_xpath"], entry["expected_sha256"])
        if key in index:
            raise ValueError(f"Duplicate watch result for {key}")
        index[key] = entry
    return index


def source_watch_status(sources, index):
    watched = [s for s in sources if "watch_xpath" in s]
    if not watched:
        return "not_configured"
    statuses = set()
    for source in watched:
        key = (source["url"], source["watch_xpath"], source["passage_sha256"])
        result = index.get(key)
        if result is None:
            statuses.add("watch_required")
        elif result.get("status") == "changed":
            statuses.add("watch_changed")
        elif result.get("status") != "unchanged" or result.get("observed_sha256") != key[2]:
            statuses.add("watch_unavailable")
    return next((s for s in ("watch_changed", "watch_unavailable", "watch_required") if s in statuses), "unchanged")


def clinical_status(update, status, event, as_of):
    if update is None:
        return "not_assessed"
    assessed = date.fromisoformat(update["as_of"])
    if as_of < assessed:
        return "future_assessment"
    if as_of >= date.fromisoformat(update["review_due"]):
        return "review_due"
    if update["outcome"] == "conflicting_evidence":
        return "needs_adjudication"
    if status != "approve":
        return status
    if not assessed <= date.fromisoformat(event["date"]) <= as_of:
        return "temporal_review_missing"
    if not {"clinical", "language", "temporal"} <= set(event.get("checked", [])):
        return "temporal_review_missing"
    return "current"


def records(folder, events, mode, as_of=None, watch_report=None):
    if mode not in MODES:
        raise ValueError("Unknown curation mode")
    as_of = as_of or date.today()
    watched = watch_index(watch_report, as_of)
    seen, families, temporal_families = set(), {}, set()
    result = []
    for path in sorted(folder.glob("*.json")):
        draft = json.loads(path.read_text(encoding="utf-8"))
        signature = digest(draft)
        family = draft.get("family_id", draft["concept_id"])
        split = draft["split"]
        use = mode.removeprefix("clinical-") if mode != "queue" else next(
            (kind for kind, expected in SPLITS.items() if expected == split), None)
        rights = rights_status(draft.get("source_rights"), use, as_of)
        if family in families and families[family] != split:
            raise ValueError("The same case family appears in multiple splits: " + family)
        families[family] = split
        if any("clinical_update" in v or "historical_basis" in v for v in draft["variants"]) or any(
            "watch_xpath" in source for source in draft.get("evidence", [])
        ):
            temporal_families.add(family)
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
                   "decision": status, "rights_status": rights}
            update = variant.get("clinical_update")
            sources = clinical_sources(draft, variant) if "clinical_update" in variant else []
            row["clinical_status"] = clinical_status(update, status, event, as_of)
            row["source_watch_status"] = source_watch_status(sources, watched)
            if row["clinical_status"] == "current" and row["source_watch_status"] not in {"not_configured", "unchanged"}:
                row["clinical_status"] = row["source_watch_status"]
            if update is not None:
                row.update(clinical_as_of=update["as_of"], review_due=update["review_due"],
                           jurisdiction=update["jurisdiction"], outcome=update["outcome"])
                if "selection_rule" in update:
                    row["selection_rule"] = update["selection_rule"]
            if mode == "queue":
                result.append(row)
                continue
            if status != "approve" or split != SPLITS[use] or not draft.get("evidence"):
                continue
            permissions = (event.get("approved_uses"), draft.get("permitted_uses"))
            if not all(isinstance(uses, list) and use in uses for uses in permissions):
                continue
            current_target = mode.startswith("clinical-") or (use == "train" and update is not None)
            if current_target and (row["clinical_status"] != "current" or rights != "cleared"):
                continue
            target = update if current_target else variant
            prompt = target["question"]
            if variant.get("options"):
                prompt += "\n" + "\n".join(f"{k}. {v}" for k, v in variant["options"].items())
            answer = target["answer"] + ("\n" + target["rationale"] if target.get("rationale") else "")
            row.update(reviewer=event["reviewer"], decision_date=event["date"], decision_reason=event["reason"],
                       answer_basis="clinical_as_of" if current_target else (
                           "source_version" if update is not None else "source_version_unassessed"),
                       evidence=sources if current_target else draft["evidence"], rubric=target.get("rubric", []),
                       messages=[{"role": "user", "content": prompt}, {"role": "assistant", "content": answer}])
            if current_target:
                row["source_rights"] = draft["source_rights"]
                row.update(valid_options=update["valid_options"], offered_option_labels=list(variant.get("options") or {}),
                           export_as_of=as_of.isoformat())
                historical = variant.get("historical_basis") or {}
                if historical.get("comparison") == "same_decision_single_option" and use in ("development", "evaluation"):
                    row["historical_option"] = {k: historical[k] for k in ("as_of", "url", "locator")}
                    row["historical_option"]["label"] = variant["answer"]
                if "claims" in update:
                    row["claims"] = update["claims"]
            elif update is not None:
                row["clinical_outcome"] = row.pop("outcome")
                if "selection_rule" in row:
                    row["clinical_selection_rule"] = row.pop("selection_rule")
            result.append(row)
    if events.keys() - seen:
        raise ValueError("Review record references a variant missing from the draft collection")
    if mode == "train":
        # A sibling translation can be stored in a later file; all family members need a current judgment.
        result = [row for row in result if row["answer_basis"] == "clinical_as_of" or row["family_id"] not in temporal_families]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--drafts", type=Path, default=Path("drafts"))
    parser.add_argument("--decisions", type=Path, default=Path("docs/review/decisions.jsonl"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="Evaluate clinical validity and use decisions recorded by this date (default: today).")
    parser.add_argument("--watch-report", type=Path, help="JSON report for evidence passages monitored on --as-of.")
    args = parser.parse_args()
    if not args.drafts.is_dir():
        parser.error(f"Draft folder does not exist: {args.drafts}")
    as_of = args.as_of or date.today()
    report = json.loads(args.watch_report.read_text(encoding="utf-8")) if args.watch_report else None
    rows = records(args.drafts, decisions(args.decisions, as_of), args.mode, as_of, report)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        from .moex_archive import atomic
        atomic(args.out, text.encode())
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
