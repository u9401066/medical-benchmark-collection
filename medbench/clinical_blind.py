"""Prepare and score blinded clinician reviews of two frozen clinical runs."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hmac
import json
from pathlib import Path
import random
import secrets

from . import evidence_audit
from .clinical_compare import compare
from .clinical_run import assignment, sha
from .clinical_score import FAILURES, indexed, prediction_digest, read_jsonl, score
from .curation import has_text
from .json_io import unique_keys, write_new


PROTOCOL = "clinical-blind-v1"
ARMS = ("left", "right")


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def read_json(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def read_pair(gold, gold_hash, left, right):
    items, digest = assignment(gold, gold_hash)
    predictions, hashes = {}, {}
    for arm, path in zip(ARMS, (left, right), strict=True):
        raw = path.read_bytes()
        rows = list(read_jsonl(path, raw))
        score(items, rows)  # Apply the same version and response checks as the scorer.
        predictions[arm] = indexed(rows, arm)
        hashes[arm] = sha(raw)
    return items, predictions, {"gold_sha256": digest, "predictions_sha256": hashes}


def draw_families(items, plan, seed):
    frame = {item["family_id"] for item in items}
    if plan is None:
        plan = [{"name": "all", "family_ids": sorted(frame), "n": len(frame)}]
    seen_families, seen_names = set(), set()
    if not isinstance(plan, list) or not plan:
        raise ValueError("A sampling plan needs at least one stratum")
    for row in plan:
        name, families, n = row["name"], row["family_ids"], row["n"]
        if (
            not has_text(name)
            or name in seen_names
            or not isinstance(families, list)
            or not families
            or not all(map(has_text, families))
            or len(set(families)) != len(families)
            or seen_families.intersection(families)
            or type(n) is not int
            or not 1 <= n <= len(families)
        ):
            raise ValueError(
                "Each stratum needs a unique name, distinct families and a valid sample size"
            )
        seen_names.add(name)
        seen_families.update(families)
    if seen_families != frame:
        raise ValueError(
            "Sampling strata must partition the complete assignment by case family"
        )
    rng = random.Random(seed)
    return [
        {
            "name": row["name"],
            "family_ids": sorted(row["family_ids"]),
            "n": row["n"],
            "selected_family_ids": sorted(
                rng.sample(sorted(row["family_ids"]), row["n"])
            ),
            "inclusion_probability": row["n"] / len(row["family_ids"]),
        }
        for row in sorted(plan, key=lambda row: row["name"])
    ]


def assemble(items, predictions, key):
    secret = bytes.fromhex(key["secret"])
    if len(secret) != 32:
        raise ValueError("The private blind key requires 32 secret bytes")
    chosen = {f for row in key["strata"] for f in row["selected_family_ids"]}

    def tag(purpose, item_id):
        return hmac.digest(secret, f"{purpose}:{item_id}".encode("utf-8"), "sha256")

    sampled = [item for item in items if item["family_id"] in chosen]
    sampled.sort(key=lambda item: tag("order", item["id"]))
    packet, links = [], {}
    counts = Counter()
    for item in sampled:
        item_id = item["id"]
        pair_id = "P-" + tag("pair", item_id).hex()[:24]
        order = ARMS if tag("position", item_id)[0] % 2 == 0 else ARMS[::-1]
        available = 0
        for position, arm in enumerate(order, 1):
            answer = predictions[arm].get(item_id)
            if not evidence_audit.has_answer_text(answer):
                continue
            available += 1
            digest = prediction_digest(answer)
            raw = evidence_audit.worksheet(item, answer, digest)
            context = raw["context"]
            context["rubric"] = item.get("rubric", [])
            context["expected_response"] = {
                "outcome": item["outcome"],
                "valid_options": item["valid_options"],
                "selection_rule": item.get("selection_rule"),
            }
            context["reference_answer"] = "\n".join(
                m["content"] for m in item["messages"][1:]
            )
            review_id = "R-" + tag(arm, item_id).hex()[:24]
            if review_id in links:
                raise ValueError("Duplicate blinded review ID")
            clinical_reviewable = answer["response_type"] not in FAILURES
            packet.append(
                {
                    "id": review_id,
                    "pair_id": pair_id,
                    "position": position,
                    "clinical_reviewable": clinical_reviewable,
                    "context": context,
                    "clinical_verdict": None,
                    "clinical_reason": "",
                    **{
                        field: value
                        for field, value in raw.items()
                        if field
                        not in {"id", "content_sha256", "prediction_sha256", "context"}
                    },
                }
            )
            links[review_id] = (arm, item_id, item["content_sha256"], digest)
        counts[available] += 1
    summary = {
        "assigned_variants": len(items),
        "sampled_case_families": len(chosen),
        "sampled_variants": len(sampled),
        "pairs_with_two_recorded_answers": counts[2],
        "pairs_with_one_recorded_answer": counts[1],
        "pairs_with_no_recorded_answers": counts[0],
        "reviewable_answers": len(packet),
    }
    return packet, links, summary


def publish_bytes(path, data):
    """Resume an interrupted publish without replacing an existing artifact."""
    try:
        write_new(path, data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(
                f"{path}: choose a new path for a different artifact"
            ) from None


def prepare(items, predictions, identity, key_path, packet_path, plan, seed):
    protocol = {
        "protocol": PROTOCOL,
        **identity,
        "sample_seed": seed,
        "strata": draw_families(items, plan, seed),
    }
    if key_path.is_file():
        key = read_json(key_path)
        if {k: v for k, v in key.items() if k != "secret"} != protocol:
            raise ValueError(
                "The private key belongs to different inputs or a different sampling plan"
            )
    else:
        if packet_path.exists():
            raise ValueError(
                "A packet already exists. Supply its matching private key or choose a fresh path."
            )
        key = {**protocol, "secret": secrets.token_hex(32)}
    packet, _, summary = assemble(items, predictions, key)
    publish_bytes(key_path, json_bytes(key))
    publish_bytes(packet_path, json_bytes(packet))
    return summary


def intake(items, predictions, identity, key, reviewed, score_as_of=None):
    if key.get("protocol") != PROTOCOL or any(
        key.get(k) != v for k, v in identity.items()
    ):
        raise ValueError(
            "The private key belongs to different frozen inputs or a different protocol"
        )
    plan = [
        {k: stratum[k] for k in ("name", "family_ids", "n")}
        for stratum in key["strata"]
    ]
    if draw_families(items, plan, key["sample_seed"]) != key["strata"]:
        raise ValueError("The private key has an inconsistent selection record")
    packet, links, summary = assemble(items, predictions, key)
    template = indexed(packet, "blind packet")
    clinical = {arm: [] for arm in ARMS}
    evidence = {arm: [] for arm in ARMS}
    readonly = ("pair_id", "position", "clinical_reviewable", "context")
    if not isinstance(reviewed, list):
        raise ValueError("Review submissions must be an array of packet rows")
    for review_id, row in indexed(reviewed, "submitted review").items():
        original = template.get(review_id)
        if (
            original is None
            or row.keys() != original.keys()
            or any(row[k] != original[k] for k in readonly)
        ):
            raise ValueError(
                f"{review_id}: unknown review or changes to its read-only material"
            )
        arm, item_id, content_hash, digest = links[review_id]
        locator = {"id": item_id, "prediction_sha256": digest}
        if row["clinical_verdict"] is not None:
            if not original["clinical_reviewable"]:
                raise ValueError(
                    f"{review_id}: only the evidence review can be completed for this response"
                )
            clinical[arm].append(
                {
                    **locator,
                    "reviewer": row["reviewer"],
                    "date": row["date"],
                    "verdict": row["clinical_verdict"],
                    "reason": row["clinical_reason"],
                }
            )
        if row["state"] != "pending":
            evidence[arm].append(
                {
                    **locator,
                    "content_sha256": content_hash,
                    **{
                        k: row[k]
                        for k in (
                            "reviewer",
                            "date",
                            "minutes",
                            "state",
                            "inventory_complete",
                            "reference_claims",
                            "additional_claims",
                            "citations",
                            "additional_evidence",
                        )
                    },
                }
            )
    arms = {}
    for arm in ARMS:
        report = score(
            items,
            predictions[arm].values(),
            clinical[arm],
            score_as_of=score_as_of,
            evidence_reviews=evidence[arm],
        )
        report["gold_sha256"] = identity["gold_sha256"]
        arms[arm] = {
            "clinical_reviews": clinical[arm],
            "evidence_reviews": evidence[arm],
            "score": report,
        }
    return {
        "protocol": PROTOCOL,
        **identity,
        "review_assignment_sha256": sha(json_bytes(packet)),
        "sample_seed": key["sample_seed"],
        "strata": key["strata"],
        "coverage": summary,
        "arms": arms,
        "paired": compare(arms["left"]["score"], arms["right"]["score"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "intake"):
        sub = actions.add_parser(action)
        for field in ("gold", "left", "right", "key"):
            sub.add_argument("--" + field, required=True, type=Path)
        sub.add_argument("--expected-gold-sha256", required=True)
        if action == "prepare":
            sub.add_argument("--packet", required=True, type=Path)
            sub.add_argument(
                "--plan", type=Path, help="JSON file listing the sampling strata"
            )
            sub.add_argument("--sample-seed", type=int, default=20261126)
        else:
            sub.add_argument("--reviews", required=True, type=Path)
            sub.add_argument("--score-as-of", type=date.fromisoformat)
            sub.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        paths = [args.gold, args.key]
        if args.action == "prepare":
            paths.extend(p for p in (args.packet, args.plan) if p is not None)
        else:
            paths.extend((args.reviews, args.out))
        # Keeping two legitimate arms in the same file is useful for test/retest controls.
        predictions = {args.left.resolve(), args.right.resolve()}
        others = [p.resolve() for p in paths]
        if set(others) & predictions or len(set(others)) != len(others):
            raise ValueError(
                "Keep inputs, the private key, and published artifacts at distinct paths"
            )
        items, predictions, identity = read_pair(
            args.gold, args.expected_gold_sha256, args.left, args.right
        )
        if args.action == "prepare":
            plan = read_json(args.plan) if args.plan else None
            summary = prepare(
                items,
                predictions,
                identity,
                args.key,
                args.packet,
                plan,
                args.sample_seed,
            )
            print(json_bytes(summary).decode("utf-8"), end="")
        else:
            submitted = args.reviews.read_bytes()
            result = intake(
                items,
                predictions,
                identity,
                read_json(args.key),
                json.loads(submitted, object_pairs_hook=unique_keys),
                args.score_as_of,
            )
            result["returned_reviews_sha256"] = sha(submitted)
            publish_bytes(args.out, json_bytes(result))
    except (KeyError, ValueError, TypeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
