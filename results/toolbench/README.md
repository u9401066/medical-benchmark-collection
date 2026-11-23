# Tool-calling benchmarks (2026-11-23): Bonsai 27B vs Inkling 2 Mini

Raw output of [llama-mcp-router](https://github.com/u9401066/llama-mcp-router) `benchmarks/run_bench.py` (v0.12.0, commit
`e454f9d`): does the model's **first tool call** pick the right PubMed / Zotero tool? Temperature 0, effort medium. The router
repo does not keep `benchmarks/results/`, so the files are kept here.

| folder | model / server | queries | tools offered |
|---|---|---|---|
| `bonsai_heldout`, `bonsai_hard` | Bonsai 27B PQ2_0 on the production llama-server (:8081, 4 slots), bench default `--concurrency 2` | held-out 52 / hard 110 | 41 PubMed (from the server's MCP `/tools`) / 61 PubMed + Zotero |
| `inkling-iq4xs_heldout` | Inkling 2 Mini UD-IQ4_XS, test server :8091 (4 slots, 65,536 tokens, `-ub 256`), `--concurrency 1` | held-out 52 | 41 |
| `inkling-q3kxl_heldout`, `inkling-q3kxl_hard` | Inkling 2 Mini UD-Q3_K_XL, test server :8091 (4 slots, 131,072 tokens, `-ub 64`), `--concurrency 1` | held-out 52 / hard 110 | 41 / 61 |

Inkling runs at concurrency 1 because two 40k-token prompts at once did not fit its 65,536-token pool. The hard set with
IQ4_XS failed (its compute buffer needed 2.7 GB more than was free), so there is no `inkling-iq4xs_hard`.

Commands (in the llama-mcp-router repo; `--llm` is the server under test, Clef-Flash on :8000 for the 2-pass selector):

```bash
python benchmarks/run_bench.py --queries benchmarks/data/queries_heldout.jsonl --clef-url http://127.0.0.1:8000 \
  --concurrency 1 --only "all,clef 2-pass" --llm http://127.0.0.1:8091 --out benchmarks/results/<name>_heldout
python benchmarks/run_bench.py --queries benchmarks/data/queries_hard.jsonl --tools benchmarks/data/pubmed_zotero_tools.json \
  --concurrency 1 --only all --llm http://127.0.0.1:8091 --out benchmarks/results/<name>_hard
```

Inputs (sha256, first 16 hex): `queries_heldout.jsonl` 3dd8785629f895a3, `queries_hard.jsonl` 7107bb6bd9bf9d10,
`pubmed_zotero_tools.json` bc43ecae2ab70260.

## Paired results

`python scripts/toolbench_compare.py results/toolbench/bonsai_heldout results/toolbench/inkling-q3kxl_heldout results/toolbench/bonsai_hard results/toolbench/inkling-q3kxl_hard`

| A | B | selector | n | A correct | B correct | only A | only B | McNemar p | A s/query (median) | B s/query (median) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bonsai_heldout | inkling-q3kxl_heldout | all | 52 | 51 (98.1%, 90–100%) | 46 (88.5%, 77–95%) | 5 | 0 | 0.0625 | 1.94 | 1.48 |
| bonsai_heldout | inkling-q3kxl_heldout | clef 2-pass | 52 | 51 (98.1%, 90–100%) | 47 (90.4%, 79–96%) | 5 | 1 | 0.219 | 4.50 | 5.84 |
| bonsai_hard | inkling-q3kxl_hard | all | 110 | 101 (91.8%, 85–96%) | 96 (87.3%, 80–92%) | 5 | 0 | 0.0625 | 2.57 | 1.39 |
| pooled | | all | 162 | 152 (93.8%) | 142 (87.7%) | 10 | 0 | 0.00195 | | |

`python scripts/toolbench_compare.py results/toolbench/bonsai_heldout results/toolbench/inkling-iq4xs_heldout`

| A | B | selector | n | A correct | B correct | only A | only B | McNemar p | A s/query (median) | B s/query (median) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bonsai_heldout | inkling-iq4xs_heldout | all | 52 | 51 (98.1%, 90–100%) | 48 (92.3%, 82–97%) | 3 | 0 | 0.25 | 1.94 | 1.48 |
| bonsai_heldout | inkling-iq4xs_heldout | clef 2-pass | 52 | 51 (98.1%, 90–100%) | 48 (92.3%, 82–97%) | 4 | 1 | 0.375 | 4.50 | 3.41 |

Where Inkling Q3_K_XL is wrong it mostly **looks before it acts**: its first call is `pubmed_read_session`,
`pubmed_list_pipelines`, `pubmed_load_pipeline`, `pubmed_list_resolver_presets`, `zotero_list_collections` or
`zotero_get_collection` instead of the requested action (export, schedule, save, import; 10 of 14 misses on the hard set, 3 of
6 on held-out, plus one that fetched a paper's details before looking for related ones). In an agent loop this usually costs an
extra step rather than a wrong result, but this benchmark scores only the first call. The other misses: no tool call for a
figure (image) request (both sets), `configure_institutional_access` instead of `get_institutional_link` (held-out), and a
literature search for 3 of the hard set's 12 general questions that need no tool (Bonsai answered all 12 without one).
Seconds per query are not comparable one to one (Bonsai ran on production at concurrency 2, Inkling alone at 1).
