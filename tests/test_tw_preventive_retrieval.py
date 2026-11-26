"""Regression checks for dated retrieval, coverage gaps and source identity."""

import importlib.util
from hashlib import sha256
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parents[1] / "reports" / "tw-preventive-source-pilot"
spec = importlib.util.spec_from_file_location(
    "tw_preventive_retrieval", HERE / "run.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_published_index_and_results_replay_both_corpora():
    result = pilot.evaluate(pilot.read(HERE / "index.json"))
    assert result == pilot.read(HERE / "results.json")
    assert result["sources"] == 7
    for shelf, expected in (("with_order", 5), ("without_order", 4)):
        for arm in pilot.ARMS:
            trial = result["comparisons"][shelf][arm]
            assert len(trial["rows"]) == 10
            for counts in trial["by_language"].values():
                assert counts["assigned"] == 5
                assert counts["answerable_in_corpus"] == expected
                if arm.startswith("dated"):
                    assert counts["future_at_1"] == 0
                if arm == "dated_effective_glossary":
                    assert counts["not_yet_effective_at_1"] == 0


def test_announcement_is_public_before_it_is_in_force_and_missing_is_distinct_from_abstention():
    docs = pilot.source_specs()
    by_date = {
        day: item["id"] + "@" + day
        for item, day, _, _ in pilot.assignments()
        if item["id"] == "mbc-tw-adult-0001-zh-TW"
    }
    ore = pilot.ORDER
    submitted = {
        by_date[pilot.REFERENCE]: [ore],
        by_date[pilot.BRIDGE]: [ore],
        by_date[pilot.CURRENT]: [],
    }
    report = pilot.judgments(submitted, docs)
    rows = {row["id"]: row for row in report["rows"]}
    before = rows[by_date[pilot.REFERENCE]]
    assert not before["future_at_1"] and before["not_yet_effective_at_1"]
    assert ore not in before["accepted_sources"]
    after = rows[by_date[pilot.BRIDGE]]
    assert not after["not_yet_effective_at_1"] and after["accepted_sources"] == [ore]
    assert not rows[by_date[pilot.CURRENT]]["missing_ranking"]
    assert report["by_language"]["en-US"]["missing_rankings"] == 5
    jan_before_release = pilot.judgments(
        {by_date[pilot.BRIDGE]: ["hpa-adult-expansion"]}, docs
    )
    assert next(
        r for r in jan_before_release["rows"] if r["id"] == by_date[pilot.BRIDGE]
    )["future_at_1"]


def test_query_expansion_only_uses_terms_in_prompt_and_no_source_gets_a_free_tie():
    docs = [
        {
            "source": "foo",
            "available_on": "2024-12-01",
            "terms": sorted(pilot.terms("小兒麻痺")),
        }
    ]
    assert pilot.rank("polio", "2024-12-31", docs, "dated_lexical") == []
    assert pilot.rank("polio", "2024-12-31", docs, "dated_glossary") == ["foo"]
    assert pilot.rank("unrelated question", "2024-12-31", docs, "dated_glossary") == []
    assert pilot.rank("polio", "2024-01-01", docs, "dated_glossary") == []


@pytest.mark.parametrize(
    "bad", [["absent-source"], ["hpa-adult-2024", "hpa-adult-2024"], "hpa-adult-2024"]
)
def test_invalid_rankings_never_enter_metrics(bad):
    item, day, _, _ = next(pilot.assignments())
    with pytest.raises(ValueError):
        pilot.judgments({item["id"] + "@" + day: bad}, pilot.source_specs())


def test_gazette_extraction_binds_the_original_pdf_and_exact_cell_order():
    import pymupdf
    from gazette import extract

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((20, 40), "Effective date")
        page.insert_text((20, 100), "Confirmed row")
        data = pdf.tobytes()
    source = {
        "source_sha256": sha256(data).hexdigest(),
        "passage_regions": [
            {"page": 1, "rect": [10, 15, 160, 50]},
            {"page": 1, "rect": [10, 75, 160, 110]},
        ],
        "passage_sha256": sha256(b"Effectivedate\nConfirmedrow").hexdigest(),
    }
    assert extract(data, source) == "Effectivedate\nConfirmedrow"
    with pytest.raises(ValueError, match="source hash"):
        extract(data + b" ", source)
    with pytest.raises(ValueError, match="passage hash"):
        extract(data, {**source, "passage_regions": source["passage_regions"][::-1]})
