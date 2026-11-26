"""Compare clinical score reports made against the same frozen assignment."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import random
import re

from .clinical_score import ABSTENTIONS, OPTION_OUTCOMES, indexed
from .json_io import unique_keys, write_new


IDENTITY = ("family_id", "lang", "content_sha256", "outcome", "historical_relation")
PASS = {"pass": True, "fail": False, "pending": None}
METRICS = (
    "clinical_pass",
    "structured_match",
    "obsolete_choice_reuse",
    "inappropriate_abstention",
    "no_valid_option_recognition",
    "insufficient_information_recognition",
    "fabricated_citation",
)


@dataclass(frozen=True)
class Pair:
    family: str
    left: bool | None
    right: bool | None

    def __post_init__(self):
        if not isinstance(self.family, str) or not self.family:
            raise ValueError("A pair must identify its case family")
        if any(
            value is not None and type(value) is not bool
            for value in (self.left, self.right)
        ):
            raise ValueError(
                "Both arms must record a binary outcome or an unresolved judgment"
            )


def pair_reports(left, right):
    gold = left.get("gold_sha256")
    if (
        not isinstance(gold, str)
        or not re.fullmatch(r"[0-9a-f]{64}", gold)
        or gold != right.get("gold_sha256")
    ):
        raise ValueError("Reports need the same frozen assignment SHA-256")
    for field in ("export_as_of", "split"):
        if left.get(field) != right.get(field):
            raise ValueError(f"Reports refer to different {field}")
    left_rows, right_rows = (
        indexed(left["items"], "left report"),
        indexed(right["items"], "right report"),
    )
    if (
        left_rows.keys() != right_rows.keys()
        or len(left_rows) != left["assigned"]
        or len(right_rows) != right["assigned"]
    ):
        raise ValueError("Reports must retain the same set of assigned IDs")
    pairs = []
    for key in sorted(left_rows):
        a, b = left_rows[key], right_rows[key]
        if any(a[k] != b[k] for k in IDENTITY):
            raise ValueError(f"{key}: reports use different item versions or metadata")
        pairs.append((a, b))
    return pairs


def cluster_interval(pairs, seed, replicates):
    # Variant-weighted estimator. Sample whole families, retaining all language siblings and both arms.
    families = defaultdict(list)
    for pair in pairs:
        families[pair.family].append(int(pair.right) - int(pair.left))
    groups = [(sum(values), len(values)) for _, values in sorted(families.items())]
    if len(groups) < 2:
        return None
    generator = random.Random(seed)
    differences = []
    for _ in range(replicates):
        drawn = generator.choices(groups, k=len(groups))
        differences.append(
            sum(value for value, _ in drawn) / sum(count for _, count in drawn)
        )
    differences.sort()
    last = replicates - 1
    return [differences[int(last * 0.025)], differences[int(last * 0.975)]]


def summarize(pairs, seed, replicates):
    matrix = Counter()
    families = {p.family for p in pairs}
    lower = upper = 0
    for p in pairs:
        left = "pending" if p.left is None else str(int(p.left))
        right = "pending" if p.right is None else str(int(p.right))
        matrix[left + "/" + right] += 1
        lower += int(p.right is True) - int(p.left is not False)
        upper += int(p.right is not False) - int(p.left is True)
    n = len(pairs)
    pending = sum(p.left is None or p.right is None for p in pairs)
    observed = (matrix["0/1"] - matrix["1/0"]) / n if n and not pending else None
    return {
        "assigned_pairs": n,
        "case_families": len(families),
        "pending_pairs": pending,
        "left_confirmed": sum(p.left is True for p in pairs),
        "right_confirmed": sum(p.right is True for p in pairs),
        "left_false_right_true": matrix["0/1"],
        "left_true_right_false": matrix["1/0"],
        "pair_counts_left_right": dict(matrix),
        "right_minus_left": observed,
        "bounds_over_unresolved_reviews": [lower / n, upper / n] if n else None,
        "family_bootstrap_95": None
        if observed is None
        else cluster_interval(pairs, seed, replicates),
    }


def compare(left, right, seed=20261126, replicates=2000):
    if replicates < 100:
        raise ValueError("Use at least 100 bootstrap replicates")
    paired = pair_reports(left, right)
    metrics = {name: [] for name in METRICS}
    for a, b in paired:
        family = a["family_id"]
        outcome = a["outcome"]
        metrics["clinical_pass"].append(
            Pair(family, PASS[a["clinical_result"]], PASS[b["clinical_result"]])
        )
        if outcome != "free_text":
            structured = Pair(family, a["target_match"], b["target_match"])
            metrics["structured_match"].append(structured)
            if outcome in ("no_valid_option", "insufficient_information"):
                metrics[outcome + "_recognition"].append(structured)
        if a["historical_relation"] == "obsolete":
            metrics["obsolete_choice_reuse"].append(
                Pair(
                    family, a["selected_obsolete_option"], b["selected_obsolete_option"]
                )
            )
        if outcome in OPTION_OUTCOMES:
            metrics["inappropriate_abstention"].append(
                Pair(
                    family,
                    a["response_type"] in ABSTENTIONS,
                    b["response_type"] in ABSTENTIONS,
                )
            )
        metrics["fabricated_citation"].append(
            Pair(family, a.get("fabricated_citation"), b.get("fabricated_citation"))
        )
    return {
        "gold_sha256": left["gold_sha256"],
        "split": left["split"],
        "export_as_of": left["export_as_of"],
        "score_dates": {"left": left["score_as_of"], "right": right["score_as_of"]},
        "seed": seed,
        "bootstrap_replicates": replicates,
        **{name: summarize(pairs, seed, replicates) for name, pairs in metrics.items()},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261126)
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        left, right = [
            json.loads(p.read_bytes(), object_pairs_hook=unique_keys)
            for p in (args.left, args.right)
        ]
        summary = compare(left, right, args.seed, args.replicates)
        text = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            write_new(args.out, text.encode("utf-8"))
        else:
            print(text, end="")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
