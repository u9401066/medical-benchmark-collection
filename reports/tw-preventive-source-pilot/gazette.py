"""Extract the dated MOHW order and its adult preventive care table cells."""

from hashlib import sha256
from unicodedata import normalize


def extract(raw: bytes, source: dict) -> str:
    """Return the pinned UTF-8 passage, in the evidence record's region order."""
    import pymupdf

    if sha256(raw).hexdigest() != source["source_sha256"]:
        raise ValueError("Gazette PDF does not match the registered source hash")
    paragraphs = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:
        for region in source["passage_regions"]:
            page = document[region["page"] - 1]
            text = page.get_text("text", clip=region["rect"], sort=True)
            paragraphs.append("".join(normalize("NFKC", text).split()))
    passage = "\n".join(paragraphs)
    if sha256(passage.encode("utf-8")).hexdigest() != source["passage_sha256"]:
        raise ValueError("Gazette passage does not match the registered passage hash")
    return passage
