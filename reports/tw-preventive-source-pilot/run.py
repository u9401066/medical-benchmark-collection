"""Rebuild and evaluate a dated source-retrieval pilot from official HPA passages."""

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(1, str(HERE))
from medbench.json_io import unique_keys, write_new  # noqa: E402

FAMILY = "mbc-tw-adult-0001"
REFERENCE = "2024-12-31"
BRIDGE = "2025-01-02"
CURRENT = "2026-11-26"
# Only translate terms stated in the query. No eligibility ages or intervals are supplied.
GLOSSARY = {
    "adult preventive health service": "成人預防保健",
    "polio": "小兒麻痺",
    "health promotion administration": "國民健康署",
    "publicly funded": "公費",
}
ARMS = ("lexical", "dated_lexical", "dated_glossary", "dated_effective_glossary")
ORDER = "hpa-adult-order"


def read(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    result = set(re.findall(r"[a-z]+|[0-9]+", normalized))
    for run in re.findall(r"[\u3400-\u9fff]+", normalized):
        if len(run) == 1:
            result.add(run)
        else:
            result.update(run[i : i + 2] for i in range(len(run) - 1))
    return result


def source_specs():
    docs = {}
    for row in read(HERE / "corpus.json"):
        source = next(
            s
            for s in read(ROOT / "drafts" / (row["draft"] + ".json"))["evidence"]
            if s["id"] == row["source"]
        )
        sid = source["id"]
        if sid in docs:
            raise ValueError(f"Duplicate source ID {sid}")
        # An undated live table is only demonstrated available at the observation.
        available = (
            row.get("version_date")
            or source.get("published_on")
            or source["retrieved_on"]
        )
        docs[sid] = {
            "source": sid,
            "title": source["title"],
            "url": source["url"],
            "available_on": date.fromisoformat(available).isoformat(),
            "locator": source["locator"],
            "passage_sha256": source["passage_sha256"],
            "cache": row["cache"],
            "effective_from": source.get("effective_from"),
            "format": row.get("format", "html"),
            "original": source,
            "xpath": row.get("xpath")
            or source.get("watch_xpath")
            or source.get("passage_xpath"),
        }
    return docs


def public_fields(source):
    return {
        k: source[k]
        for k in (
            "source",
            "title",
            "url",
            "available_on",
            "effective_from",
            "locator",
            "passage_sha256",
        )
    }


def build_index(cache=None):
    from lxml import html
    from medbench.evidence_watch import fetch, passage_hash

    index = []
    for sid, source in source_specs().items():
        if cache is None:
            raw, charset = fetch(source["url"])
        else:
            raw, charset = (cache / source["cache"]).read_bytes(), "utf-8"
        if source["format"] == "pdf":
            from gazette import extract

            passage = extract(raw, source["original"])
        else:
            page = html.fromstring(
                raw, parser=html.HTMLParser(encoding=charset, no_network=True)
            )
            xpath = source["xpath"]
            if passage_hash(page, xpath) != source["passage_sha256"]:
                raise ValueError(
                    f"{sid}: the source passage changed. Review it before rebuilding."
                )
            passage = " ".join(page.xpath(xpath)[0].text_content().split())
        index.append(
            {
                **public_fields(source),
                "terms": sorted(terms(source["title"] + " " + passage)),
            }
        )
    return index


def assignments():
    for suffix in ("0001", "0002"):
        case = read(ROOT / "drafts" / ("mbc-tw-adult-" + suffix + ".json"))
        for variant in case["variants"]:
            current = variant["clinical_update"]
            accepted = [ORDER, "hpa-adult-faq", "hpa-adult-service"]
            if suffix == "0001":
                accepted.append("hpa-adult-expansion")
            yield variant, REFERENCE, variant["question"], ["hpa-adult-2024"]
            if suffix == "0001":
                # Implementation predates the January explanatory article.
                before = (
                    "2024 年 12 月 31 日"
                    if variant["lang"] == "zh-TW"
                    else "December 31, 2024"
                )
                after = (
                    "2025 年 1 月 2 日"
                    if variant["lang"] == "zh-TW"
                    else "January 2, 2025"
                )
                if variant["question"].count(before) != 1:
                    raise ValueError("Historical prompt date locator changed")
                yield (
                    variant,
                    BRIDGE,
                    variant["question"].replace(before, after),
                    [ORDER],
                )
            yield variant, CURRENT, current["question"], sorted(accepted)


def rank(question, cutoff, index, arm):
    if arm not in ARMS:
        raise ValueError(f"Unknown retrieval arm {arm}")
    if arm in {"dated_glossary", "dated_effective_glossary"}:
        question += " " + " ".join(
            zh for en, zh in GLOSSARY.items() if en in question.casefold()
        )
    q = terms(question)
    scores = []
    for doc in index:
        if arm != "lexical" and doc["available_on"] > cutoff:
            continue
        if arm == "dated_effective_glossary" and doc.get("effective_from") and doc["effective_from"] > cutoff:
            continue
        tokens = set(doc["terms"])
        overlap = len(q & tokens)
        if overlap:
            scores.append((overlap / math.sqrt(len(tokens) * len(q)), doc["source"]))
    return [sid for _, sid in sorted(scores, key=lambda pair: (-pair[0], pair[1]))]


def counts(rows):
    result = Counter()
    for row in rows:
        result["assigned"] += 1
        accepted, ranking = set(row["accepted_sources"]), row["ranking"]
        result["with_candidate"] += bool(ranking)
        result["future_at_1"] += row["future_at_1"]
        result["not_yet_effective_at_1"] += row["not_yet_effective_at_1"]
        result["missing_rankings"] += row["missing_ranking"]
        result["answerable_in_corpus"] += bool(accepted)
        result["supported_at_1"] += bool(accepted.intersection(ranking[:1]))
        result["supported_at_3"] += bool(accepted.intersection(ranking[:3]))
        result["unanswerable_with_candidate"] += bool(not accepted and ranking)
    return dict(result)


def judgments(rankings, sources):
    """Score every assigned question against the documents present in this shelf."""
    rows = []
    known = set()
    for item, cutoff, prompt, accepted in assignments():
        key = item["id"] + "@" + cutoff
        known.add(key)
        accepted = sorted(set(accepted) & sources.keys())
        if any(sources[k]["available_on"] > cutoff for k in accepted):
            raise ValueError("Future reference in dated source rubric")
        ranked = rankings.get(key, [])
        if not isinstance(ranked, list) or not all(
            isinstance(k, str) and k in sources for k in ranked
        ):
            raise ValueError(f"{key}: expected a ranking of known source IDs")
        if len(set(ranked)) != len(ranked):
            raise ValueError(f"{key}: duplicate source in ranking")
        top = sources[ranked[0]] if ranked else {}
        rows.append(
            {
                "id": key,
                "lang": item["lang"],
                "cutoff": cutoff,
                "prompt_sha256": sha(prompt),
                "accepted_sources": accepted,
                "ranking": ranked,
                "missing_ranking": key not in rankings,
                "future_at_1": bool(top and top["available_on"] > cutoff),
                "not_yet_effective_at_1": bool(
                    top.get("effective_from") and top["effective_from"] > cutoff
                ),
            }
        )
    if rankings.keys() - known:
        raise ValueError("Ranking outside the assigned task IDs")
    return {
        "by_language": {
            lang: counts([r for r in rows if r["lang"] == lang])
            for lang in ("zh-TW", "en-US")
        },
        "rows": rows,
    }


def evaluate(index):
    sources = source_specs()
    if len(index) != len(sources) or {d["source"] for d in index} != sources.keys():
        raise ValueError("Index differs from registered source inventory")
    for doc in index:
        fields = public_fields(sources[doc["source"]])
        if (
            {k: v for k, v in doc.items() if k != "terms"} != fields
            or not doc["terms"]
            or doc["terms"] != sorted(set(doc["terms"]))
        ):
            raise ValueError(
                "Index differs from registered source version or term format"
            )
    comparisons = {}
    for name in ("with_order", "without_order"):
        shelf = [doc for doc in index if name == "with_order" or doc["source"] != ORDER]
        available = {doc["source"]: doc for doc in shelf}
        comparisons[name] = {}
        for arm in ARMS:
            rankings = {
                item["id"] + "@" + cutoff: rank(prompt, cutoff, shelf, arm)
                for item, cutoff, prompt, _ in assignments()
            }
            comparisons[name][arm] = judgments(rankings, available)
    return {
        "family": FAMILY,
        "rubric_status": "pending_clinician_review",
        "sources": len(sources),
        "index_sha256": sha(
            json.dumps(index, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        ),
        "comparisons": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--build-index",
        action="store_true",
        help="Read registered passages and emit the term index",
    )
    actions.add_argument(
        "--verify",
        action="store_true",
        help="Recompute and compare to the published results",
    )
    actions.add_argument(
        "--tasks",
        action="store_true",
        help="Export exam prompts with no target passages or answers",
    )
    actions.add_argument(
        "--score-rankings",
        type=Path,
        help="Score supplied JSONL rankings on the full corpus",
    )
    parser.add_argument(
        "--cache", type=Path, help="Directory of saved HTML for --build-index"
    )
    parser.add_argument("--index", type=Path, default=HERE / "index.json")
    parser.add_argument(
        "--out", type=Path, help="Write to a new file (default: standard output)"
    )
    args = parser.parse_args()
    if args.cache and not args.build_index:
        parser.error("--cache applies to --build-index")
    if args.verify and args.out:
        parser.error("--verify compares without writing")
    if args.tasks:
        result = [
            {
                "id": item["id"] + "@" + cutoff,
                "lang": item["lang"],
                "cutoff": cutoff,
                "question": question,
                "options": item["options"],
                "retrieval_task": (
                    "請依相關性排列可支持本題判斷的文件段落 ID。"
                    if item["lang"] == "zh-TW"
                    else "Rank source passage IDs that support the decision in this question."
                ),
            }
            for item, cutoff, question, _ in assignments()
        ]
    elif args.score_rankings:
        rankings = {}
        for line in args.score_rankings.read_bytes().splitlines():
            if line.strip():
                row = json.loads(line, object_pairs_hook=unique_keys)
                if row["id"] in rankings:
                    raise ValueError("Repeated task ID")
                rankings[row["id"]] = row["ranking"]
        result = judgments(rankings, source_specs())
    elif args.build_index:
        result = build_index(args.cache)
    else:
        result = evaluate(read(args.index))
        if args.verify:
            if result != read(HERE / "results.json"):
                raise SystemExit("Published retrieval results no longer match")
            print(
                f"{result['sources']} sources, {sum(1 for _ in assignments())} tasks, 2 shelves, {len(ARMS)} retrieval conditions verified"
            )
            return
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        write_new(args.out, content.encode("utf-8"))
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
