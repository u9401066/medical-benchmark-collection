### Selection (no LLM): 52 tool requests, 0 no-tool requests

| selector | recall on tool requests | tools sent (tool requests) | tools sent (no-tool requests) | no-tool requests sent zero tools | schema KB (avg, all) | selector ms (median) |
|---|---|---|---|---|---|---|
| all | 100.0% | 41.0 | - | - | 136.9 | 0 |
| clef 2-pass | 100.0% | 5.8 | - | - | 19.5 | 152 |

### First tool call by the 27B model

| selector | correct (all) | tool requests | no-tool requests (answered without a tool call) | EN | 中文 | prompt tokens (avg, all rounds) | seconds/query (avg) | 2nd round (catalog used) |
|---|---|---|---|---|---|---|---|---|
| all | 92.3% | 92.3% | - | 90.6% | 95.0% | 39709 | 2.2 | - |
| clef 2-pass | 92.3% | 92.3% | - | 90.6% | 95.0% | 5453 | 3.9 | - |
