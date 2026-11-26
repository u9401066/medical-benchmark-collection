"""Cross-reference manually sourced decisions against official paper IDs and archived answer grids."""
from __future__ import annotations

import argparse
import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .moex_archive import atomic, read_tsv
from .moex_coverage import paper_id


def _digest(value):
    return bool(re.fullmatch(r"[0-9a-f]{64}", value or ""))


def _official(url):
    parsed = urlsplit(url or "")
    host = parsed.hostname or ""
    return parsed.scheme == "https" and parsed.username is None and any(
        host == domain or host.endswith("." + domain) for domain in ("exam.gov.tw", "moex.gov.tw")
    )


def _item_sources(decisions):
    for section in ("clinical_items", "boundary_items"):
        for record in decisions.get(section, []):
            yield record, "decision_on_this_item", None
            for other in record.get("other_items_in_same_correction_sheet", []):
                # These rows are from the grid itself. An appeal concerning item
                # 46 does not create an appeal ruling on items 1, 17 or 18.
                same_paper = {k: record[k] for k in ("scope", "exam", "exam_code", "category_code", "subject",
                              "subject_code", "original_asset", "corrected_asset", "parent_listing") if k in record}
                item = {**same_paper, **other, "id": f"{record['id']}-sheet-{other['question']:03d}"}
                yield item, "other_item_on_same_correction_sheet", record["id"]


def _identity(item, document, subjects):
    n = item.get("question")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or not _digest(document.get("sha256")) or not _official(document.get("url")):
        return None, "missing_item_number_or_source_digest"
    candidates = set()
    if all(item.get(k) for k in ("exam_code", "category_code", "subject_code")):
        candidates.add(paper_id(item))
    if item.get("paper_id"):
        candidates.add(item["paper_id"])
    if item.get("paper_item_id"):
        pid, sep, number = item["paper_item_id"].rpartition("-")
        if not sep or not number.isdigit() or int(number) != n:
            return None, "conflicting_identifiers"
        candidates.add(pid)
    for label, typ in (("original_asset", "S"), ("corrected_asset", "M")):
        asset = item.get(label)
        if not asset:
            continue
        query = parse_qs(urlsplit(asset.get("url", "")).query)
        required = ("code", "c", "s", "t", "q")
        if not _official(asset.get("url")) or not _digest(asset.get("sha256")) or any(len(query.get(k, [])) != 1 for k in required):
            return None, "incomplete_reviewed_asset_identity"
        pid = "-".join(query[k][0] for k in ("code", "c", "s"))
        if query["t"][0] != typ or asset.get("asset_id") != f"moex-{pid}-{typ}-{query['q'][0]}":
            return None, "conflicting_identifiers"
        candidates.add(pid)
    if not candidates:
        return None, "no_official_paper_identifier"
    if len(candidates) != 1:
        return None, "conflicting_identifiers"
    pid = candidates.pop()
    if len(subjects.get(pid, [])) != 1:
        return None, "official_subject_absent_or_ambiguous"
    scope = subjects[pid][0]["scope"]
    if ((item.get("scope") == "human_medical" and scope != "medical") or
            ((item.get("scope") or "").startswith("boundary") and scope != "boundary")):
        return None, "scope_mismatch"
    return pid, "identified"


def _document_rows(item, relation, documents):
    refs = []
    if relation == "decision_on_this_item":
        for role, doc_id in (("preliminary", item.get("preliminary_source")), ("decision", item.get("source"))):
            if not doc_id:
                continue
            doc = documents.get(doc_id, {})
            refs.append({**doc, "document_id": doc_id, "role": role,
                         "locator": item.get("locator", doc.get("locator")) if role == "decision" else doc.get("locator")})
    else:
        asset = item.get("corrected_asset", {})
        refs.append({**asset, "role": "correction_table", "kind": "official_correction_sheet",
                     "locator": f"更正表，第 {item['question']} 題及其備註"})
    return refs


def _paper_record(folder, subject, pid):
    if not subject["year_roc"].isdigit() or not re.fullmatch(r"[0-9A-Za-z]+", subject["exam_code"]):
        raise ValueError(f"Invalid identifiers in subject index for {pid}")
    shard = folder / subject["year_roc"] / (subject["exam_code"] + ".jsonl.gz")
    if not shard.exists():
        return None
    with gzip.open(shard, "rt", encoding="utf-8") as data:
        found = [p for line in data if (p := json.loads(line))["paper_id"] == pid]
    if len(found) > 1:
        raise ValueError(f"Duplicate ledger paper {pid}")
    return found[0] if found else None


def _archive_evidence(item, assets):
    matched = {}
    for label, role in (("original_asset", "S"), ("corrected_asset", "M")):
        reviewed = item.get(label)
        result = {"reviewed_source": reviewed}
        listed = [r for r in assets if r["asset_type"] == role]
        result["current_sources"] = [{k: r.get(k, "") for k in ("asset_id", "source_url", "status", "sha256")}
                                     for r in sorted(listed, key=lambda r: r["source_url"])]
        if reviewed:
            current = [r for r in listed if r.get("asset_id") == reviewed["asset_id"] and r["source_url"] == reviewed["url"]]
            state = "not_in_current_manifest"
            if len(current) > 1:
                state = "ambiguous_archive_source"
            elif current:
                if current[0]["status"] != "verified":
                    state = "awaiting_verified_file"
                elif current[0]["sha256"] == reviewed["sha256"]:
                    state = "matches_reviewed_bytes"
                else:
                    state = "different_bytes"
        else:
            state = "no_documented_key_digest"
        result["version_comparison"] = state
        matched[role] = result
    return matched


def _grid_comparison(case, ledger, reference):
    if any(r["version_comparison"] == "different_bytes" for r in reference.values()):
        return "archive_version_changed", None
    if any(r["version_comparison"] != "matches_reviewed_bytes" for r in reference.values()):
        return "awaiting_matching_archived_keys", None
    if not ledger:
        return "paper_ledger_pending", None
    for role, r in reference.items():
        source = r["reviewed_source"]
        candidates = [s for s in ledger["sources"] if s.get("asset_type") == role and s.get("source_url") == source["url"]]
        if len(candidates) != 1 or candidates[0].get("sha256") != source["sha256"] or candidates[0].get("status") != "verified":
            return "paper_ledger_out_of_date", None
    rows = [it for it in ledger["items"] if it.get("section") == "objective" and it.get("number") == case["question"]]
    if len(rows) != 1:
        return "item_ledger_absent_or_ambiguous", None
    it = rows[0]
    excerpt = {k: it.get(k) for k in ("id", "section", "number", "pages", "key_evidence", "rule")}
    evidence = it.get("key_evidence", {})
    if not all(role in evidence for role in ("S", "M")) or it.get("rule", {}).get("kind") == "unresolved":
        return "ledger_rule_unresolved", excerpt
    def norm(token):
        return unicodedata.normalize("NFKC", token).strip().upper()
    actual_start = norm(evidence["S"]["token"])
    if case.get("original_key") and actual_start != norm(case["original_key"]):
        return "original_key_conflict", excerpt
    rule = it["rule"]
    kind = case["ruling"]
    if kind == "original_key_upheld":
        equal = (rule["kind"] == "single" and norm(evidence["M"]["token"]) == actual_start and rule.get("choices") == [actual_start])
        if not equal:
            return "rule_conflict", excerpt
        other_changes = any(i.get("number") != case["question"] and i.get("key_evidence", {}).get("M", {}).get("note")
                            for i in ledger["items"])
        return ("upheld_on_sheet_with_other_corrections" if other_changes else "upheld_in_archived_keys"), excerpt
    if kind == "universal_award":
        return ("agrees" if rule["kind"] == "all_credit" else "rule_conflict"), excerpt
    if kind in {"explicit_accepted_responses", "accepted_alternatives"}:
        choices = case.get("accepted_responses") or case.get("accepted_options") or []
        if not choices or rule["kind"] != "any_of":
            return "rule_conflict", excerpt
        # The ruling may name fewer combinations than the grid. Keep their
        # intersection visible without treating omitted combinations as rejected.
        stated = set(choices)
        parsed = set(rule.get("choices", []))
        if stated == parsed:
            return "agrees_on_listed_responses", excerpt
        return "additional_responses_require_review" if stated <= parsed or parsed <= stated else "rule_conflict", excerpt
    return "ruling_type_requires_review", excerpt


def build(index, manifest, items, decisions, out):
    """Write items.jsonl and scope.json. Inputs/outputs are Path objects."""
    data = json.loads(decisions.read_text(encoding="utf-8"))
    docs = data["source_documents"]
    subjects, archives = defaultdict(list), defaultdict(list)
    for row in read_tsv(index / "subjects.tsv"):
        subjects[paper_id(row)].append(row)
    for row in read_tsv(manifest):
        archives[row["paper_id"]].append(row)
    ledgers = {}
    results = []
    for item, relation, parent in _item_sources(data):
        refs = _document_rows(item, relation, docs)
        source = next((ref for ref in refs if ref["role"] != "preliminary"), {})
        pid, mapping = _identity(item, source, subjects)
        case = {k: v for k, v in item.items() if k not in {"other_items_in_same_correction_sheet", "original_asset", "corrected_asset"}}
        result = {"decision_id": item["id"], "relation": relation, "related_case_id": parent, "scope": item["scope"],
                  "paper_id": pid, "item_id": f"{pid}-{item['question']:03d}" if pid else None, "question": item["question"],
                  "mapping": mapping, "ruling": case, "documents": refs}
        evidence = _archive_evidence(item, archives.get(pid, []))
        result["answer_sources"] = evidence
        if pid:
            subj = result["official_subject"] = subjects[pid][0]
            if pid not in ledgers:
                ledgers[pid] = _paper_record(items, subj, pid)
            status, excerpt = _grid_comparison(item, ledgers[pid], evidence)
            result.update(grid_comparison=status, ledger_item=excerpt)
        else:
            result.update(grid_comparison="unmapped", ledger_item=None)
        results.append(result)
    if len({r["decision_id"] for r in results}) != len(results):
        raise ValueError("Duplicate curated decision or companion ID")
    results.sort(key=lambda r: r["decision_id"])
    text = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in results)
    atomic(out / "items.jsonl", text.encode("utf-8"))
    summary = {"curation_as_of": data.get("as_of"), "default_item_notice_status": "not_reviewed_against_independent_notices",
               "records": len(results), "mapping": dict(Counter(r["mapping"] for r in results)),
               "grid_comparison": dict(Counter(r["grid_comparison"] for r in results)),
               "relation": dict(Counter(r["relation"] for r in results)),
               "aggregate_only_documents": {key: doc for key, doc in docs.items() if doc.get("kind") == "aggregate_only"}}
    atomic(out / "scope.json", (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    base = Path("datasets/moex")
    parser.add_argument("--index", type=Path, default=base / "index")
    parser.add_argument("--manifest", type=Path, default=base / "archive/files.tsv")
    parser.add_argument("--items", type=Path, default=base / "items")
    parser.add_argument("--decisions", type=Path, default=base / "notices/decisions.json")
    parser.add_argument("--out", type=Path, default=base / "rulings")
    args = parser.parse_args()
    summary = build(args.index, args.manifest, args.items, args.decisions, args.out)
    print(json.dumps({k: v for k, v in summary.items() if k != "aggregate_only_documents"}, sort_keys=True))


if __name__ == "__main__":
    main()
