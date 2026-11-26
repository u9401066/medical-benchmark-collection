import csv
from pathlib import Path

from medbench.vienna_catalogue import build


def test_original_catalogue_preserves_line_break_locations(tmp_path):
    source = Path(__file__).resolve().parents[1] / "datasets/discovery/vienna"
    (tmp_path / "annotated-datasets.tsv").write_bytes((source / "annotated-datasets.tsv").read_bytes())
    assert build(tmp_path) == 475
    assert (tmp_path / "records.tsv").read_bytes() == (source / "records.tsv").read_bytes()
    with (tmp_path / "records.tsv").open(encoding="utf-8", newline="") as stream:
        data = {r["original_lines"]: r for r in csv.DictReader(stream, delimiter="\t")}
    assert data["14-15"]["name"] == "MIMICSQL"
    assert "clinical documents" in data["91-92"]["name"]
