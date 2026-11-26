from medbench.moex_legacy import listing


def test_big5_archive_links_and_unlinked_answer_are_separate():
    page = ('<meta charset=big5><a href="類科.pdf">本考試所有測驗題標準答案</a>'
            '<a href="1001.pdf" title="甲類　試題檔">試題</a>'
            '<a href="" title="甲類　答案檔">答案</a><a href="https://example.org/q.pdf">試題</a>')
    rows = listing(page.encode("cp950"), "https://www.moex.gov.tw/other/106110/query.html")
    assert [r["asset_type"] for r in rows] == ["A", "Q", "S"]
    assert rows[0]["source_url"].endswith("/%E9%A1%9E%E7%A7%91.pdf") and not rows[-1]["source_url"]
