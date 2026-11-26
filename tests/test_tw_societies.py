import shutil

from medbench import tw_societies as societies
from scripts.tw_society_name_search import candidate_home, society_site_label


def test_event_and_login_links_remain_distinct_from_society_homepages():
    assert not candidate_home("https://soc.kktix.cc/event")
    assert not candidate_home("https://member.soc.org.tw/login")
    assert not candidate_home("https://some.org.tw.atlaq.com/")
    assert not candidate_home("https://1199333010204.tw66.com.tw/")
    assert candidate_home("https://www.soc.org.tw/about") == "https://www.soc.org.tw/"
    assert not society_site_label(
        "台灣測驗學會", ["2026 台灣測驗學會年會", "台灣測驗學會"]
    )
    assert society_site_label("台灣測驗學會", ["臺灣測驗學會"])


def test_published_society_tables_reproduce_from_attributed_sources(tmp_path):
    root = societies.ROOT
    for name in (
        "registry-screen.tsv",
        "aliases.tsv",
        "live-registry.tsv",
        "live-physician-associations.tsv",
    ):
        shutil.copyfile(root / name, tmp_path / name)
    observations = societies.source_tables(root)
    rows = societies.build(tmp_path, observations)
    societies.exam_sources(tmp_path, observations)
    identifiers = {r["society_id"] for r in rows}
    assert len(identifiers) == len(rows)
    assert all(
        r["society_id"] in identifiers
        for r in societies.records(tmp_path / "exam-sources.tsv")
    )
    societies.write_directory(tmp_path, rows)
    societies.coverage(tmp_path, rows)
    for name in (
        "societies.tsv",
        "exam-sources.tsv",
        "by-specialty.md",
        "coverage.tsv",
    ):
        assert (tmp_path / name).read_text(encoding="utf-8") == (root / name).read_text(
            encoding="utf-8"
        )


def test_register_screen_distinguishes_professional_names():
    assert societies.registry_scope("台灣高血壓學會") == "name_candidate"
    assert societies.registry_scope("中華亞太小動物中醫學會") == "animal_related"
    assert societies.registry_scope("中華民國野生動物診療醫學會") == "animal_related"
    assert societies.registry_scope("臺灣運動物理治療學會") == "name_candidate"
    assert societies.registry_scope("中華民國火藥學會") == "outside_medical_scope"
    assert societies.registry_scope("台灣藥師佛佛學會") == "outside_medical_scope"
    assert societies.registry_scope("臺灣西班牙語學會") == "other_society_name"
    assert societies.registry_scope("台灣兒童程式教育學會") == "adjacent_name"
    assert societies.registry_scope("台灣血栓暨止血學會") == "name_candidate"
    assert societies.classification("台灣母胎醫學會")[0] == "婦產、生殖與周產期"
    assert societies.classification("中華民國風溼病醫學會")[0] == "感染、免疫與風濕"
    assert not societies.registry_scope("醫學院同學會")


def test_exam_and_directory_share_an_identifier_for_documented_aliases():
    aliases = {"內科醫學會": "台灣內科醫學會"}
    assert societies.society_id("內科醫學會", aliases) == societies.society_id(
        "社團法人臺灣內科醫學會", aliases
    )
    assert societies.society_id("台灣臨床醫學會", aliases) != societies.society_id(
        "台灣內科醫學會", aliases
    )


def test_directory_preserves_identity_and_multiple_exam_sources(tmp_path):
    societies.write_table(
        tmp_path / "registry-screen.tsv",
        ["dataset_id", "seq", "name", "screen"],
        [
            dict(
                dataset_id="13603",
                seq="7",
                name="臺灣臨床測驗學會",
                screen="name_candidate",
            )
        ],
    )
    source = dict(
        name="社團法人台灣臨床測驗學會",
        source_id="test",
        website="https://soc.example/",
        source_url="https://directory.example/",
        locator="row 1",
        source_file="example.tsv",
        website_check="directory_only",
        exam_url="https://soc.example/date",
        exam_evidence="announcement",
    )
    original = {
        **source,
        "name": "臺灣臨床測驗學會",
        "website_check": "identity_verified",
        "website_evidence": "頁首顯示學會名稱",
        "destination_url": "https://soc.example/",
        "exam_url": "https://soc.example/questions",
        "exam_evidence": "public_questions",
    }
    other = {
        **source,
        "name": "臺灣臨床測驗研究學會",
    }
    form = {
        **other,
        "exam_url": "https://soc.example/assessment-form",
        "exam_evidence": "public_assessment_form",
    }
    obs = [source, original, other, form]
    rows = societies.build(tmp_path, obs)
    assert len(rows) == 2
    matched = next(r for r in rows if r["website"])
    assert (
        matched["registry_refs"] == "13603#7"
        and matched["website_source"] == "https://soc.example/"
    )
    assert matched["exam_url"] == original["exam_url"]
    form_only = next(r for r in rows if not r["website"])
    assert form_only["website_status"] == "directory"
    assert form_only["exam_url"] == form["exam_url"]
    societies.exam_sources(tmp_path, obs)
    assert {
        r["exam_url"] for r in societies.records(tmp_path / "exam-sources.tsv")
    } == {original["exam_url"], source["exam_url"], form["exam_url"]}
    societies.write_directory(tmp_path, rows)
    assert "公開臨床評量表" in (tmp_path / "by-specialty.md").read_text(
        encoding="utf-8"
    )
    societies.coverage(tmp_path, rows)
    assert (
        sum(
            int(r["public_exam_or_sample"])
            for r in societies.records(tmp_path / "coverage.tsv")
        )
        == 1
    )
