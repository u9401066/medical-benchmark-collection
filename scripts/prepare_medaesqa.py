"""Build a text-free sentence/citation index from the pinned OSF MedAESQA release."""

import argparse
import gzip
import hashlib
import io
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile


SOURCE_SHA256 = "a062742c1678b4379121ad030a06bda574afd376f331df41575938dd9849c383"
DEFAULT_OUTPUT = Path("datasets/discovery/medaesqa/sentences.jsonl.gz")


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def unique_object(pairs):
    """Reject duplicate JSON object keys, including repeated model keys in an answer map."""
    mapping = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("Repeated key in source JSON object")
        mapping[key] = value
    return mapping


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def locate(answer, sentence):
    """Count exact, overlapping matches. Only assign offsets for a unique full match."""
    start = answer.find(sentence)
    if start == -1:
        return 0, None, None
    count = 1
    pos = answer.find(sentence, start + 1)
    while pos != -1:
        count += 1
        pos = answer.find(sentence, pos + 1)
    if count > 1:
        return count, None, None
    return count, start, start + len(sentence)


def citation_metadata(assessments):
    if assessments is None:
        return None
    if not isinstance(assessments, list):
        raise ValueError("citation_assessment must be a list or null")
    result = []
    for assessment in assessments:
        pmid = require_text(assessment["cited_pmid"], "cited_pmid")
        relation = require_text(assessment["evidence_relation"], "evidence_relation")
        snippet = assessment["evidence_support"]
        if snippet is not None:
            require_text(snippet, "evidence_support")
        result.append({
            "cited_pmid": pmid,
            "evidence_relation": relation,
            "has_evidence_excerpt": snippet is not None,
        })
    return result


def build_index(questions):
    rows = []
    question_ids = set()
    models = set()
    accurate = Counter()
    for question in questions:
        qid = require_text(question["question_id"], "question_id")
        if qid in question_ids:
            raise ValueError("Repeated question_id")
        question_ids.add(qid)
        for model, answer in question["machine_generated_answers"].items():
            models.add(require_text(model, "model key"))
            text = require_text(answer["answer"], "machine answer")
            answer_sha = sha256_text(text)
            accurate[require_text(answer["is_answer_accurate"], "is_answer_accurate")] += 1
            sentence_ids = set()
            for position, annotated in enumerate(answer["answer_sentences"]):
                sid = require_text(annotated["answer_sentence_id"], "answer_sentence_id")
                if sid in sentence_ids:
                    raise ValueError("Repeated answer_sentence_id within an answer")
                sentence_ids.add(sid)
                sentence = require_text(annotated["answer_sentence"], "answer_sentence")
                count, start, end = locate(text, sentence)
                relevance = annotated["answer_sentence_relevance"]
                if relevance is not None:
                    require_text(relevance, "answer_sentence_relevance")
                rows.append({
                    "question_id": qid,
                    "model_key": model,
                    "answer_sentence_id": sid,
                    "sentence_index": position,
                    "answer_sha256": answer_sha,
                    "sentence_sha256": sha256_text(sentence),
                    "match_count": count,
                    "start": start,
                    "end": end,
                    "answer_sentence_relevance": relevance,
                    "citation_assessment": citation_metadata(annotated["citation_assessment"]),
                })
    return rows, {
        "questions": len(question_ids), "model_keys": len(models),
        "answers_by_is_answer_accurate": dict(sorted(accurate.items())),
    }


def audit(rows):
    matches = Counter()
    relevance = Counter()
    relations = Counter()
    excerpts = 0
    grouped_relations = defaultdict(set)
    for row in rows:
        matches[row["match_count"]] += 1
        relevance[row["answer_sentence_relevance"]] += 1
        for citation in row["citation_assessment"] or []:
            key = (
                row["question_id"], row["model_key"],
                row["answer_sentence_id"], citation["cited_pmid"],
            )
            label = citation["evidence_relation"]
            grouped_relations[key].add(label)
            relations[label] += 1
            excerpts += citation["has_evidence_excerpt"]
    return {
        "sentences": len(rows),
        "exact_match_counts": dict(sorted(matches.items())),
        "sentence_relevance": {str(label) if label is not None else "null": n for label, n in relevance.items()},
        "citations": sum(relations.values()),
        "evidence_relations": dict(sorted(relations.items())),
        "nonempty_evidence_excerpts": excerpts,
        "distinct_sentence_pmid": len(grouped_relations),
        "distinct_sentence_pmid_with_supporting": sum("supporting" in v for v in grouped_relations.values()),
        "distinct_sentence_pmid_only_supporting": sum(v == {"supporting"} for v in grouped_relations.values()),
        "distinct_sentence_pmid_with_mixed_labels": sum(len(v) > 1 for v in grouped_relations.values()),
    }


def encode(rows):
    lines = (json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows)
    raw = "".join(lines).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as out:
        out.write(raw)
    return buffer.getvalue(), hashlib.sha256(raw).hexdigest()


def prepare(source, output, check=False):
    if source.resolve() == output.resolve():
        raise ValueError("Output must differ from the source")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Input SHA-256 differs from the pinned OSF release")
    rows, summary = build_index(json.loads(raw, object_pairs_hook=unique_object))
    compressed, stream_hash = encode(rows)
    if check:
        # Compare canonical bytes across zlib versions which can encode the same stream differently.
        if hashlib.sha256(gzip.decompress(output.read_bytes())).hexdigest() != stream_hash:
            raise ValueError("Published index differs from the rebuilt records")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temp = Path(stream.name)
        try:
            temp.write_bytes(compressed)
            os.replace(temp, output)
        finally:
            temp.unlink(missing_ok=True)
    return {
        "source_sha256": SOURCE_SHA256, "jsonl_sha256": stream_hash,
        **summary, **audit(rows),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="medaesqa_v1.json from OSF revision 1")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Compare records to an existing index")
    args = parser.parse_args()
    try:
        report = prepare(args.source, args.out, args.check)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(report, indent=2))
