"""Score structured responses against one approved, dated clinical assignment (JSONL)."""

import argparse
from collections import Counter
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

from .curation import OUTCOMES, SPLITS, has_text, rights_status
from .moex_archive import atomic


OPTION_OUTCOMES = {"single_valid_option", "multiple_valid_options"}
ABSTENTIONS = {"no_valid_option", "insufficient_information", "abstain"}
FAILURES = {"missing", "timeout", "parse_error"}
RESPONSES = ABSTENTIONS | {"select", "free_text", "timeout", "parse_error"}
VERDICTS = {"pass", "fail", "undetermined"}


def indexed(rows, label):
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not has_text(row.get("id")):
            raise ValueError(f"{label}: every record requires an id")
        key = row["id"]
        if key in result:
            raise ValueError(f"{label}: duplicate id {key}")
        result[key] = row
    return result


def is_label_list(labels):
    return isinstance(labels, list) and all(map(has_text, labels)) and len(set(labels)) == len(labels)


def validate_gold(row, score_as_of):
    key = row["id"]
    if (row.get("answer_basis") != "clinical_as_of" or row.get("decision") != "approve"
            or row.get("clinical_status") != "current"
            or row.get("split") not in (SPLITS["development"], SPLITS["evaluation"])
            or row.get("source_watch_status") not in ("unchanged", "not_configured")):
        raise ValueError(f"{key}: expected an approved clinical-development or clinical-evaluation export")
    if not all(has_text(row.get(k)) for k in ("family_id", "lang", "jurisdiction", "reviewer", "content_sha256")):
        raise ValueError(f"{key}: incomplete gold provenance")
    if not re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"]):
        raise ValueError(f"{key}: invalid content_sha256")
    sources = row.get("evidence")
    if not isinstance(sources, list) or not sources or not all(
            isinstance(s, dict) and all(has_text(s.get(k)) for k in ("id", "url", "version", "locator"))
            for s in sources):
        raise ValueError(f"{key}: missing approved sources with version and locator")
    expected_watch = "unchanged" if any("watch_xpath" in s for s in sources) else "not_configured"
    if row["source_watch_status"] != expected_watch:
        raise ValueError(f"{key}: source watch is inconsistent with the cited evidence")
    dates = [date.fromisoformat(row[k]) for k in ("clinical_as_of", "decision_date", "export_as_of", "review_due")]
    if not dates[0] <= dates[1] <= dates[2] < dates[3]:
        raise ValueError(f"{key}: approval is outside the clinical validity window")
    if dates[2] > score_as_of:
        raise ValueError(f"{key}: assignment was exported after the scoring date")
    if any(field in row for field in ("rights_status", "source_rights", "offered_option_labels")):
        use = "development" if row["split"] == SPLITS["development"] else "evaluation"
        if row.get("rights_status") != "cleared" or rights_status(row.get("source_rights"), use, dates[2]) != "cleared":
            raise ValueError(f"{key}: rights not cleared for this assignment")
    outcome, labels, rule = row.get("outcome"), row.get("valid_options"), row.get("selection_rule")
    if outcome not in OUTCOMES - {"conflicting_evidence"} or not is_label_list(labels):
        raise ValueError(f"{key}: invalid clinical scoring target")
    if outcome == "single_valid_option":
        valid = len(labels) == 1 and rule in (None, "any_one")
    elif outcome == "multiple_valid_options":
        valid = len(labels) >= 2 and rule in ("any_one", "all_required")
    else:
        valid = not labels and rule is None
    if not valid:
        raise ValueError(f"{key}: incompatible outcome, selection_rule and valid_options")
    if "offered_option_labels" in row:
        offered = row["offered_option_labels"]
        if (not is_label_list(offered) or not set(labels).issubset(offered)
                or (outcome == "free_text" and offered) or (outcome == "no_valid_option" and not offered)):
            raise ValueError(f"{key}: offered_option_labels contradict the clinical target")


def prediction_digest(row):
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_prediction(row, gold):
    key = row["id"]
    kind = row.get("response_type")
    if row.get("content_sha256") != gold["content_sha256"] or kind not in RESPONSES:
        raise ValueError(f"{key}: wrong gold version or unsupported response_type")
    if kind not in FAILURES and not has_text(row.get("text")):
        raise ValueError(f"{key}: include the actual output in text")
    if kind == "select":
        labels = row.get("selected_options")
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ValueError(f"{key}: selected_options must be a list of strings")
    elif row.get("selected_options", []) != []:
        raise ValueError(f"{key}: only a selection can contain selected_options")


def selection_status(gold, selected):
    if not selected or not is_label_list(selected) or gold["outcome"] == "free_text":
        return "invalid"
    offered = gold.get("offered_option_labels")
    if offered is not None:
        return "offered" if set(selected).issubset(offered) else "invalid"
    # In older exports only the accepted labels are certain to have appeared.
    return "offered" if set(selected).issubset(gold["valid_options"]) else "unverified"


def matches(gold, prediction):
    """Return None when the full free text needs human interpretation."""
    kind = prediction["response_type"] if prediction else "missing"
    outcome = gold["outcome"]
    if outcome in OPTION_OUTCOMES:
        if kind != "select":
            return False
        selected = prediction["selected_options"]
        if gold.get("selection_rule") == "all_required":
            return set(selected) == set(gold["valid_options"])
        return len(selected) == 1 and selected[0] in gold["valid_options"]
    if outcome == "free_text" and kind == "free_text":
        return None
    return kind == outcome


def rate(count, total):
    return {"numerator": count, "denominator": total, "rate": count / total if total else None}


def score(gold_rows, predictions, reviews=(), *, score_as_of=None):
    today = date.today()
    score_as_of = score_as_of or today
    if score_as_of > today:
        raise ValueError("Scoring date cannot be in the future")
    gold = indexed(gold_rows, "gold")
    answers = indexed(predictions, "predictions")
    judgments = indexed(reviews, "reviews")
    unknown = (answers.keys() | judgments.keys()) - gold.keys()
    if unknown:
        raise ValueError(f"IDs outside the assignment: {sorted(unknown)}")
    for item in gold.values():
        validate_gold(item, score_as_of)
    snapshots = {(r["export_as_of"], r["split"]) for r in gold.values()}
    if len(snapshots) > 1:
        raise ValueError("Keep one export date and one split per assignment")

    rows, pending = [], []
    for key, item in gold.items():
        prediction = answers.get(key)
        kind, digest = "missing", None
        if prediction is not None:
            validate_prediction(prediction, item)
            kind, digest = prediction["response_type"], prediction_digest(prediction)
        selection = selection_status(item, prediction["selected_options"]) if kind == "select" else None
        match = False if selection == "invalid" else matches(item, prediction)
        review = judgments.get(key)
        verdict = None
        if review is not None:
            verdict = review.get("verdict")
            if (kind in FAILURES or review.get("prediction_sha256") != digest or verdict not in VERDICTS
                    or not has_text(review.get("reviewer")) or not has_text(review.get("reason"))):
                raise ValueError(f"{key}: invalid review or wrong prediction_sha256")
            if not date.fromisoformat(item["export_as_of"]) <= date.fromisoformat(review["date"]) <= score_as_of:
                raise ValueError(f"{key}: review date must lie between the assignment export and scoring dates")
        if match is False or verdict == "fail":
            clinical = "fail"
        elif verdict == "pass":
            clinical = "pass"
        else:
            clinical = "pending"
            pending.append(key)
        rows.append({
            "id": key, "family_id": item["family_id"], "lang": item["lang"],
            "rights_status": item.get("rights_status", "legacy_undocumented"),
            "content_sha256": item["content_sha256"], "prediction_sha256": digest,
            "outcome": item["outcome"], "response_type": kind, "selection_status": selection, "target_match": match,
            "review_verdict": verdict, "clinical_result": clinical,
        })

    assigned = len(rows)
    deterministic = [r for r in rows if r["outcome"] != "free_text"]
    selectable = [r for r in rows if r["outcome"] in OPTION_OUTCOMES]
    selections = [r for r in rows if r["selection_status"] == "offered"]
    selection_counts = Counter(r["selection_status"] for r in rows if r["response_type"] == "select")
    clinical_passes = sum(r["clinical_result"] == "pass" for r in rows)
    counts = Counter(r["response_type"] for r in rows)
    metrics = {
        "structured_target_match": rate(sum(r["target_match"] for r in deterministic), len(deterministic)),
        "inappropriate_abstention": rate(sum(r["response_type"] in ABSTENTIONS for r in selectable), len(selectable)),
        "selection_coverage": None if selection_counts["unverified"] else rate(len(selections), assigned),
        "selected_answer_error": (None if selection_counts["unverified"]
                                  else rate(sum(r["target_match"] is False for r in selections), len(selections))),
        "confirmed_clinical_pass_share": rate(clinical_passes, assigned),
        "clinical_pass_rate": None if pending else rate(clinical_passes, assigned),
    }
    for outcome in ("no_valid_option", "insufficient_information"):
        eligible = [r for r in rows if r["outcome"] == outcome]
        metrics[outcome + "_recognition"] = rate(sum(r["target_match"] for r in eligible), len(eligible))
    snapshot = next(iter(snapshots), (None, None))
    return {"assigned": assigned, "split": snapshot[1], "export_as_of": snapshot[0], "score_as_of": score_as_of.isoformat(),
            "case_families": len({r["family_id"] for r in rows}), "response_counts": dict(counts),
            "selection_counts": {key: selection_counts[key] for key in ("offered", "invalid", "unverified")},
            "reviewed": len(judgments), "pending_clinical_review": pending, "metrics": metrics, "items": rows}


def read_jsonl(path, raw=None):
    with (path.open("rb") if raw is None else io.BytesIO(raw)) as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except ValueError as exc:
                    raise ValueError(f"{path}:{number}: {exc}") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--score-as-of", type=date.fromisoformat, help="Include reviews through this date (default: today)")
    parser.add_argument("--expected-gold-sha256", help="Verify the exact assignment bytes frozen before inference")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        raw = args.gold.read_bytes()
        assignment_digest = hashlib.sha256(raw).hexdigest()
        if args.expected_gold_sha256 is not None and args.expected_gold_sha256.lower() != assignment_digest:
            raise ValueError("Gold SHA-256 does not match the frozen assignment")
        report = score(read_jsonl(args.gold, raw), read_jsonl(args.predictions),
                       read_jsonl(args.reviews) if args.reviews else (), score_as_of=args.score_as_of)
        report["gold_sha256"] = assignment_digest
        payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            if args.out.resolve() in {p.resolve() for p in (args.gold, args.predictions, args.reviews) if p}:
                raise ValueError("Choose an output path distinct from the input files")
            atomic(args.out, payload.encode("utf-8"))
        else:
            print(payload, end="")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
