"""Bind a clinician's rationale and citation findings to a frozen answer and its sources."""

import math
from datetime import date
from urllib.parse import urlsplit

from .curation import distinct_references, has_text


CLAIM_STATUSES = {"supported", "contradicted", "unverified"}
CITATION_STATUSES = {"verified", "misattributed", "unresolved", "confirmed_fabricated"}


def has_answer_text(prediction):
    return bool(
        prediction
        and prediction["response_type"] not in {"timeout", "request_error"}
        and has_text(prediction.get("text"))
    )


def worksheet(item, prediction, prediction_sha256):
    question = next(
        (m["content"] for m in item.get("messages", []) if m.get("role") == "user"),
        None,
    )
    claims = item.get("claims", [])
    return {
        "id": item["id"],
        "content_sha256": item["content_sha256"],
        "prediction_sha256": prediction_sha256,
        "context": {
            "question": question,
            "lang": item["lang"],
            "jurisdiction": item["jurisdiction"],
            "clinical_as_of": item["clinical_as_of"],
            "response": prediction["text"],
            "reference_claims": claims,
            "evidence": item["evidence"],
        },
        "state": "pending",
        "reviewer": None,
        "date": None,
        "minutes": None,
        "inventory_complete": False,
        "reference_claims": [
            {
                "index": i,
                "status": None,
                "span": None,
                "evidence_ids": [],
                "source_locators": {},
                "note": "",
            }
            for i in range(1, len(claims) + 1)
        ],
        "additional_claims": [],
        "citations": [],
        "additional_evidence": [],
    }


def span_key(span, text):
    if not isinstance(span, dict):
        raise ValueError("A finding requires a response span")
    start, end = span.get("start"), span.get("end")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(text)
        or not has_text(span.get("quote"))
        or text[start:end] != span["quote"]
    ):
        raise ValueError(
            "Response span must match the exact Unicode text at [start, end)"
        )
    return start, end


def http_url(url):
    if not has_text(url):
        return False
    parsed = urlsplit(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def validate(review, item, prediction, prediction_sha256, as_of):
    """Return the completed audit, or None for a worksheet still under review."""
    key = item["id"]
    if review.get("use") == "public_development_review_practice":
        raise ValueError(
            f"{key}: a practice worksheet cannot enter a scored assignment"
        )
    if not has_answer_text(prediction):
        raise ValueError(f"{key}: no recorded answer text for an evidence audit")
    if (
        review.get("content_sha256") != item["content_sha256"]
        or review.get("prediction_sha256") != prediction_sha256
    ):
        raise ValueError(
            f"{key}: evidence audit refers to a different draft or prediction"
        )
    if (
        "context" in review
        and review["context"]
        != worksheet(item, prediction, prediction_sha256)["context"]
    ):
        raise ValueError(f"{key}: evidence worksheet context changed")
    if review.get("state") == "pending":
        return None
    if (
        review.get("state") != "complete"
        or not has_text(review.get("reviewer"))
        or review.get("inventory_complete") is not True
    ):
        raise ValueError(
            f"{key}: completed audit needs a reviewer and a full inventory"
        )
    if (
        not date.fromisoformat(item["export_as_of"])
        <= date.fromisoformat(review["date"])
        <= as_of
    ):
        raise ValueError(f"{key}: evidence review date is outside the scoring window")
    minutes = review.get("minutes")
    if minutes is not None and (
        type(minutes) not in (int, float) or not math.isfinite(minutes) or minutes <= 0
    ):
        raise ValueError(f"{key}: recorded review minutes must be positive and finite")

    for field in (
        "reference_claims",
        "additional_claims",
        "citations",
        "additional_evidence",
    ):
        entries = review.get(field)
        if not isinstance(entries, list) or not all(
            isinstance(x, dict) for x in entries
        ):
            raise ValueError(f"{key}: {field} must be an array of records")
    sources = {s["id"] for s in item["evidence"]}
    if len(sources) != len(item["evidence"]):
        raise ValueError(f"{key}: ambiguous source IDs")
    for source in review["additional_evidence"]:
        eid = source.get("id")
        if (
            not has_text(eid)
            or eid in sources
            or not http_url(source.get("url"))
            or not all(
                has_text(source.get(k)) for k in ("version", "locator", "available_on")
            )
            or any(
                date.fromisoformat(source[key])
                > date.fromisoformat(item["clinical_as_of"])
                for key in ("available_on", "effective_from")
                if key in source
            )
        ):
            raise ValueError(
                f"{key}: supplemental clinical evidence needs a distinct ID and a dated source locator"
            )
        sources.add(eid)

    reference = review["reference_claims"]
    indexes = [entry.get("index") for entry in reference]
    expected = list(range(1, len(item.get("claims", [])) + 1))
    if not all(type(i) is int for i in indexes) or sorted(indexes) != expected:
        raise ValueError(f"{key}: assess each reference claim exactly once")
    text = prediction["text"]
    for entries, is_reference in (
        (reference, True),
        (review["additional_claims"], False),
    ):
        spans = set()
        for entry in entries:
            status = entry.get("status")
            refs = entry.get("evidence_ids")
            if not has_text(entry.get("note")) or not distinct_references(
                refs, sources
            ):
                raise ValueError(
                    f"{key}: claim findings need a note and known evidence IDs"
                )
            locators = entry.get("source_locators", {})
            if (
                not isinstance(locators, dict)
                or set(locators) != set(refs)
                or not all(map(has_text, locators.values()))
            ):
                raise ValueError(
                    f"{key}: locate the passage used for each cited source at this claim"
                )
            if is_reference and status == "omitted":
                if entry.get("span") is not None or refs:
                    raise ValueError(
                        f"{key}: an omitted claim cannot have a response span or matched evidence"
                    )
                continue
            if status not in CLAIM_STATUSES or (status != "unverified" and not refs):
                raise ValueError(
                    f"{key}: supported and contradicted claims need located evidence"
                )
            span = span_key(entry.get("span"), text)
            # One sentence can address more than one frozen reference claim.
            if not is_reference and span in spans:
                raise ValueError(f"{key}: duplicate additional claim span")
            spans.add(span)
    cited_spans = set()
    for entry in review["citations"]:
        span = span_key(entry.get("span"), text)
        if (
            span in cited_spans
            or entry.get("status") not in CITATION_STATUSES
            or not has_text(entry.get("note"))
        ):
            raise ValueError(f"{key}: duplicate or incomplete citation finding")
        if not http_url(entry.get("check_url")) or not has_text(
            entry.get("check_locator")
        ):
            raise ValueError(
                f"{key}: record the verification URL and location or search performed"
            )
        if entry["status"] == "confirmed_fabricated" and (
            entry.get("verification_basis") != "affirmative_primary_confirmation"
            or not has_text(entry.get("confirmation_excerpt"))
        ):
            raise ValueError(
                f"{key}: confirmed fabrication requires affirmative primary evidence and a short excerpt"
            )
        cited_spans.add(span)
    return review
