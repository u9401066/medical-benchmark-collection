### Selection (no LLM): 98 tool requests, 12 no-tool requests

| selector | recall on tool requests | tools sent (tool requests) | tools sent (no-tool requests) | no-tool requests sent zero tools | schema KB (avg, all) | selector ms (median) |
|---|---|---|---|---|---|---|
| all | 66.3% | 41.0 | 41.0 | 0/12 | 179.9 | 0 |

### First tool call by the 27B model

| selector | correct (all) | tool requests | no-tool requests (answered without a tool call) | EN | 中文 | prompt tokens (avg, all rounds) | seconds/query (avg) | 2nd round (catalog used) |
|---|---|---|---|---|---|---|---|---|
| all | 60.0% | 58.2% | 75.0% | 62.0% | 54.8% | 30799 | 4.9 | - |
