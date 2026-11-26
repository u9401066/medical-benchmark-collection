from medbench import moex_items
from medbench.twmed import Row


def test_practical_instructions_and_rubric_belong_to_one_task(monkeypatch):
    rows = [Row(p, y, 12, line) for p, y, line in (
        (0, 10, "類科：牙體技術師"), (0, 20, "題目：請依說明完成"), (0, 30, "一件作品。（100 分）"),
        (0, 40, "一、注意事項："), (0, 50, "①使用指定材料。"), (1, 10, "二、評分標準："),
        (1, 20, "①尺寸。（50 分）"), (1, 30, "②完成度。（50 分）"))]
    monkeypatch.setattr(moex_items, "pdf_rows", lambda path: (rows, [], []))
    paper = moex_items.extract_paper("106110-111-1005", {"Q": "q"}, {"Q"})
    item, = paper["items"]
    assert item["section"] == "practical" and item["pages"] == [1, 2]
    assert item["question"].endswith("100 分）") and "指定材料" in item["instructions"]
    assert item["rule"]["kind"] == "published_rubric" and item["rule"]["pages"] == [2]
    assert "②完成度" in item["rule"]["text"] and "requires_performance" in item["flags"]
    assert moex_items._practical_item(rows + [Row(1, 40, 12, "題目：第二項任務")], "multi") is None
