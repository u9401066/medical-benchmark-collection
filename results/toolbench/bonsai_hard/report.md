### Selection (no LLM): 98 tool requests, 12 no-tool requests

| selector | recall on tool requests | tools sent (tool requests) | tools sent (no-tool requests) | no-tool requests sent zero tools | schema KB (avg, all) | selector ms (median) |
|---|---|---|---|---|---|---|
| all | 100.0% | 61.0 | 61.0 | 0/12 | 161.2 | 0 |

### First tool call by the 27B model

| selector | correct (all) | tool requests | no-tool requests (answered without a tool call) | EN | 中文 | prompt tokens (avg, all rounds) | seconds/query (avg) | 2nd round (catalog used) |
|---|---|---|---|---|---|---|---|---|
| all | 91.8% | 90.8% | 100.0% | 89.9% | 96.8% | 36481 | 4.9 | - |
