### Selection (no LLM): 98 tool requests, 12 no-tool requests

| selector | recall on tool requests | tools sent (tool requests) | tools sent (no-tool requests) | no-tool requests sent zero tools | schema KB (avg, all) | selector ms (median) |
|---|---|---|---|---|---|---|
| all | 100.0% | 61.0 | 61.0 | 0/12 | 161.2 | 0 |

### First tool call by the 27B model

| selector | correct (all) | tool requests | no-tool requests (answered without a tool call) | EN | 中文 | prompt tokens (avg, all rounds) | seconds/query (avg) | 2nd round (catalog used) |
|---|---|---|---|---|---|---|---|---|
| all | 87.3% | 88.8% | 75.0% | 84.8% | 93.5% | 47918 | 2.1 | - |
