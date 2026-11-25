# Inkling 2 Mini 在 agent 模式（最高思考等級）的加速研究

- 日期：2026-11-24（llm01，伺服器時鐘為台灣時間）；2026-11-25 補充 `-b 256` 測試窗（第 5 節）與 router v0.15（9.3 節）
- 範圍：Web UI 的 agent 模式（DeepSeek Harness + 41 個 PubMed MCP 工具），思考等級 xhigh（`reasoning_effort: max`），prefill 與 decode 都要變快
- 相關報告：同一模型的醫學題評估見 [REPORT.md](REPORT.md)；agent 端的修正也寫在 [llama-mcp-router README](https://github.com/u9401066/llama-mcp-router#v013-long-agent-runs-at-high-reasoning-effort--what-made-them-slow)

## 摘要

基準是一次錄下的真實 agent 任務：在最高思考等級找 3 篇 sugammadex 與 neostigmine 的試驗並整理成表。它跑了 24 次模型請求、1,278 s 仍未完成：

- 682 s 在重算 prompt（prefill 只有 375 tok/s）；
- 589 s 在生成，其中 542 s 是 7 次自動壓縮對話。

慢的原因分成三層，三層都處理了：

| 層 | 問題 | 處理 | 效果 |
|---|---|---|---|
| agent 端（router v0.13） | 思考等級沒傳到模型；41 個工具的 schema 占 64.6k tokens；`find_tools` 中途改變工具清單；壓縮門檻太低 | 傳遞思考等級、精簡 schema、固定工具清單、調高壓縮門檻 | schema 64.6k → 30.8k tokens；壓縮門檻 49,152 → 91,750 tokens |
| agent 端（router v0.14） | 每個新 session 的系統提示最後一行（工作目錄）不同，SWA 模型的 context checkpoint 用不上，**每個新 session 都重算整個 35k 前綴** | `stable_prefix`：把含 session 路徑的系統提示行移到第一則使用者訊息 | 新 session 首次請求重算 35,346 → **455 tokens**，13.6 s → **0.34 s** |
| 引擎 | b12631、`-ub 64`、3 層專家在 CPU（因為 Clef 決策模型占用 VRAM） | b12651、全部放 GPU、2 個 slot 各自 131k（`--no-kv-unified`）、`-ub 256`；決策模型改用 CPU 上的 Laya | prefill 375 → **2,524 tok/s**；decode 60 → **86 tok/s** |

**端對端結果**：同一個任務在正式環境重跑（router v0.14 上線後，effort max），**285 s 完成**。

| | 錄製的基準（未完成） | 上線後（完成） |
|---|---:|---:|
| 模型請求數 | 24 | 21 |
| 重算的 prompt tokens | 255,926 | 43,121（另沿用 cache 1,366,171） |
| prefill 時間（速度） | 682 s（375 tok/s） | 22 s（1,956 tok/s） |
| 生成 tokens | 27,226 | 15,436 |
| 生成時間（速度） | 589 s（46.2 tok/s） | 204 s（75.8 tok/s） |
| 壓縮次數 | 7 | 0 |
| 總時間 | 1,278 s，仍未完成 | **285 s，完成**（含約 59 s 工具呼叫與 agent 本身） |

沒有幫助的嘗試（細節見第 6 節）：

- Inkling 自帶的 MTP 草稿模型（DSpark，接受率 38–67%）；
- ngram 投機解碼；
- 4 個 slot 共用 KV 時加大或縮小 `-b`；
- 3 個 slot（VRAM 不足）；
- Clef 放 CPU（選工具要 20 s）；
- 2 個 slot 時把 `-b` 從 2048 降到 256（2026-11-25 第四個測試窗，第 5 節）。

2026-11-25 的後續（router v0.15，9.3 節）：llama-server 重啟後由 router 先把共用前綴算進空的 slot（新 session 第一個請求 13 s → 0.4 s）；
單一工具結果上限 16,000 字元（DSH 不截斷 MCP 結果，曾一次讀進 48k 字元而觸發壓縮）。同一任務的總時間現在主要取決於外部 API（約 280 s 在工具呼叫）。

## 1. 測試環境與版本

| 項目 | 內容 |
|---|---|
| 主機 | llm01：Intel i7-13700（KVM 虛擬機，12 vCPU）、RAM 56 GB（可見 54.9 GiB）、Ubuntu 22.04、kernel 5.15 |
| GPU | NVIDIA RTX 4090 24 GB（24,564 MiB），driver 570.211.01，CUDA 12.8，PCIe Gen4 x16 |
| 模型 | [unsloth/Inkling-2-Mini-GGUF](https://huggingface.co/unsloth/Inkling-2-Mini-GGUF) `Inkling-2-Mini-UD-IQ4_XS.gguf`（revision 45fd087）：MoE 26.2B／啟用 3.4B；48 個有效層（24 層中 6–17 層重複 3 次）；8 層全域注意力 + 40 層滑動視窗（SWA，視窗 1024） |
| 引擎 | [unslothai/llama.cpp](https://github.com/unslothai/llama.cpp/releases) 預編譯版 `b12651-mix-c7059d6`（cuda12-newer，commit d426a3774）；之前是 `b12631-mix-acc0843` |
| Agent | DeepSeek Harness（`@deepseek-ai/dsh` 0.2.0-rc.2），由 router 以 bwrap 沙箱啟動 |
| Router | [u9401066/llama-mcp-router](https://github.com/u9401066/llama-mcp-router) v0.13.0 → [v0.14.0](https://github.com/u9401066/llama-mcp-router/releases/tag/v0.14.0)（Web UI、OpenAI API、agent 模式、MCP 工具選擇） |
| MCP 工具 | [pubmed-search-mcp](https://pypi.org/project/pubmed-search-mcp/) 的 41 個工具 |
| 決策模型（工具選擇） | 原本 Clef-Flash Q4_K_M（GPU）；現在 [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya)（CPU，`:8000`） |
| 量測程式 | [u9401066/medqa-bench](https://github.com/u9401066/medqa-bench)：`scripts/agent_capture_proxy.py`、`scripts/agent_replay.py`、`scripts/gpu_window.sh`、`scripts/jobs/inkling2mini-agent-speed{,2,3}.sh`、`scripts/stable_prefix_check.py` |

## 2. 方法

1. **錄製**：`agent_capture_proxy.py` 放在 router 與 llama-server 之間，記下 agent 每次模型請求的完整內容（messages、tools、參數）與 llama-server 回報的 timings。
   - 結果：[results/speed/agent/trace-xhigh.jsonl](../../results/speed/agent/trace-xhigh.jsonl)（24 次請求）、`trace-xhigh.timings.jsonl`。
   - 公開前已把工具結果中論文通訊作者的 email 換成 `redacted@example.org`（47 處，每處只差幾個 tokens；量測是在遮蔽前做的）。
2. **重播**：`agent_replay.py` 依錄下的歷史逐次送出請求（teacher forcing）。
   - 每台伺服器看到相同的 prompt 與相同的 cache 機會，包括錄製時發生的整段重算。
   - 模型照常生成（effort max），量速度後丟棄答案。
   - 每次重播在第一則系統訊息前加亂數，避免吃到上一次的 cache。
   - 「模擬任務時間」＝ 錄下的 prompt tokens ÷ 量到的 prefill 速度 ＋ 錄下的輸出 tokens ÷ 量到的 decode 速度，讓不同設定在同樣工作量上比較。
   - `--parallel 2`：兩個使用者同時跑。
3. **GPU 測試窗**：`gpu_window.sh` 暫停正式服務、執行 job、恢復正式服務。
   - 測試伺服器開在 `:8091`；每個設定記錄 GPU 記憶體峰值（每 0.5 s 取樣）。
4. **長 prompt 壓力測試**：1／2／4 個同時的長 prompt 填滿 95% KV，確認不會 CUDA OOM（2026-11-24 正式環境曾在 2 × 64k 當機）。
5. **正式環境驗證**：llama-server 的 `print_timing` 與 slot 選擇紀錄（journal）；`agent_smoke.py` 經 router 跑真實 agent 任務；`stable_prefix_check.py` 做受控測試。

測試時段（正式服務停用）：

| 時段 | 內容 |
|---|---|
| 16:04–16:35 | 測試窗 1（`inkling2mini-agent-speed.sh`） |
| 16:42–17:25 | 測試窗 2（`inkling2mini-agent-speed2.sh`） |
| 17:25–17:30 | 測試窗 3（`inkling2mini-agent-speed3.sh`） |
| 17:34:34–17:35:06 | 部署新引擎設定（約 32 s） |
| 17:54–17:56 | `stable_prefix` 受控測試（正式伺服器的一個 slot，約 25 s GPU 時間，服務未停） |
| 17:59:02–17:59:25 | router v0.14.0 上線，`:8081` 交回 systemd（約 23 s） |

## 3. 基準：時間花在哪裡

錄製當時的正式設定：

- 引擎 b12631，131k context 由 4 個 slot 共用，`-ub 64`；
- 第 20–22 層的專家放在 CPU，因為 Clef-Flash 決策模型也在 GPU 上。

| 原因 | 錄製中的影響 |
|---|---|
| prefill 太慢 | 375 tok/s：`-ub 64` 加上 CPU 專家，每個 micro-batch 都要經 PCIe 搬專家 |
| agent 的請求沒帶思考等級 | llama-server 用預設 effort |
| 工具 schema 原樣送出（標題、`anyOf` 別名、regex、排版） | 41 個工具 = 64.6k tokens |
| `find_tools` 中途改變工具清單 | Inkling 的模板把工具放在最前面，清單一變，後面全部重算：35.6k 與 53.5k tokens |
| DSH 自動壓縮門檻太低 | 門檻 = min(0.8 × 131,072, 131,072 − 16,384 − 65,536) = 49,152 tokens，但工具 + 系統提示 + 保留的 18k 已經超過：24 次請求中壓縮 7 次，每次重算 26–30k tokens 並思考 45–120 s（共 542 s） |
| 新 session 用不到前一個 session 的 cache | 見第 4.2 節（錄製時尚未發現，是部署後分析正式紀錄才找到） |

錄製的 1–8 號請求（17k–53k tokens 的 prompt，含 2 次整段重算）共 398 s；第 5 節用這 8 個請求比較引擎設定。

## 4. Agent 端修正

### 4.1 router v0.13（已部署）

| 設定 | 內容 | 驗證 |
|---|---|---|
| 思考等級傳遞 | 聊天的 `reasoning_effort`（或 `enable_thinking: false` → `none`）帶到這一輪 agent 的每次模型請求；`AgentConfig.reasoning_effort: "max"` 為預設 | 正式紀錄中的 agent 請求都帶 effort |
| `compact_tools: true` | 移除 schema 中模型用不到的部分 | 64.6k → 30.8k tokens（−52%）；第一次工具呼叫正確率：held-out 47/52 vs 47/52（90.4% vs 90.4%）、困難題 66/110 vs 68/110（p = 0.50）；見 [results/speed/schema-compact](../../results/speed/schema-compact) |
| plugin `policy: all` | 第一個請求就給全部 MCP 工具，不用 `find_tools` | 工具清單在 session 內不變，所有 session 的前綴相同 |
| 壓縮設定 | `compaction-basic`：`headroomTokens 8192`、`thresholdRatio 0.7`、`maxTokens 16384` → 門檻 91,750；`compaction_effort: "low"` | 同一壓縮請求（14 號）effort max vs low：實際 40.2 s vs 34.8 s，輸出 1,592 → 1,153 tokens（[window/compaction-*.json](../../results/speed/agent/window)） |

### 4.2 router v0.14 `stable_prefix`：讓所有 session 共用同一段 cache

**現象**：部署 v0.13 與新引擎後，正式紀錄中仍常見 35k、45k、67k、85k tokens 的整段重算。發生在每個新 session 的第一個請求，以及 slot 從一個 session 換到另一個 session 時，每次約 17 s。

**根因**（讀 llama.cpp b12651 的 `tools/server/server-context.cpp`、`server-slot-sched.cpp`、`common/parsers/inkling.cpp`）：

1. Inkling 有 40 層滑動視窗注意力。llama-server 不能在任意位置截斷這種 cache，只能退回到「context checkpoint」。
   - Inkling 的訊息分隔符包含 `<|message_user|>`，所以 llama-server 會在**第一則使用者訊息開始處 P** 建立 checkpoint。
   - 其他 checkpoint 建在最後一則使用者訊息、prompt 結尾前 4 tokens 等處。
2. 新請求只能使用 `pos_max ≤ 共同前綴長度（LCP）` 的 checkpoint。
3. Inkling 模板的順序是：工具 → DSH 系統提示 → 「Thinking effort level」系統訊息 → 第一則使用者訊息。
   - DSH 系統提示的最後一行是 `Your working directory is <root>/<user>/<session-id>/workspace.`，每個 session 都不同。
   - 所以兩個 session 在 P 之前約 36 tokens 就分岔，P 的 checkpoint 用不上，整段 35k 前綴（工具 + 系統提示）重算。
4. `--swa-full`（保留完整 SWA cache，可任意截斷）需要約 87 KB/token：2 × 131k 要 22.8 GB，不可行。

**修正**（[llama-mcp-router v0.14.0](https://github.com/u9401066/llama-mcp-router/releases/tag/v0.14.0)，`AgentConfig.stable_prefix: true`）：

- router 轉送 agent 的模型請求時，把系統／developer 訊息中含 session 目錄或 session id 的行，移到下一則使用者訊息的開頭；若後面沒有使用者訊息，就插入一則。
- 規則固定，同一個 session 的每個請求都被同樣改寫，所以 session 內的 cache 也不受影響。
- 模型仍看得到工作目錄，只是位置在第一則使用者訊息。

**驗證 1：受控測試**（[scripts/stable_prefix_check.py](../../scripts/stable_prefix_check.py)，[results/speed/stable-prefix/result.json](../../results/speed/stable-prefix/result.json)）。

- 錄製的第 1 個請求（17,256 tokens）換成不同 session id，送到同一個 slot，`max_tokens 1`；在正式伺服器上執行，當時 router 尚未升級，改寫由腳本進行。

| 第二個 session 的請求 | 重算 tokens | 沿用 cache（`cache_n`） | prompt 時間 |
|---|---:|---:|---:|
| 原樣（DSH 送出的形式） | 17,256 | 0 | 6,766 ms |
| `stable_prefix` 改寫後 | 542 | 16,714 | 437 ms |
| `stable_prefix`，第三個 session | 542 | 16,714 | 430 ms |

- 18:12 以遮蔽 email 後的 trace 與正式化的腳本重跑：結果相同（542／16,714 tokens，393／378 ms）。

用 `/apply-template` + `/tokenize` 核對：

- 原樣時 LCP = 16,722 < P = 16,758，所以 checkpoint 用不上；
- 改寫後 LCP = 16,736 ≥ P = 16,714，可以用。

**驗證 2：正式環境**（router 0.14.0 上線後，經 `:8001` 的真實 agent，effort max；[results/speed/stable-prefix/production-after.json](../../results/speed/stable-prefix/production-after.json)）：

| 情境 | slot 選擇 | 重算 tokens | 沿用 | prompt 時間 | 整輪時間 |
|---|---|---:|---:|---:|---:|
| 重啟後第一個 session | 空 slot 0（LRU） | 35,346 | 0 | 13.6 s | 17.7 s |
| 第二個新 session | slot 0（LCP 相似度 0.988） | **455** | 34,887 | **0.34 s** | **3.5 s** |
| slot 0 忙碌時的新 session | 空 slot 1（LRU） | 35,338 | 0 | 14.0 s | 17.8 s |

- 冷的 slot（重啟後還沒跑過 agent）仍要算一次完整前綴；之後兩個 slot 都帶有共同前綴，任一新 session 都能沿用。
- slot 被一般聊天（沒有工具、前綴不同）占用時，llama-server 會先把原本的 agent 狀態存到 RAM prompt cache（`--cache-ram 24576`），之後 agent session 選到這個 slot 時再載回來。
  - 例外：如果存起來的狀態長度超過共同前綴的 4 倍（`f_keep < 0.25`），就不會載回。
- session 內的後續請求本來就能沿用（`f_keep` 1.000），每輪只算新增的工具結果（e2e 中 166–7,000 tokens，0.2–3 s）。

## 5. 引擎設定（三個 GPU 測試窗）

重播 1–8 號請求，effort max，單一使用者（錄製值 398 s）：

| 設定 | prefill tok/s | decode tok/s | 模擬任務 s | 實際 s | GPU 峰值 MiB |
|---|---:|---:|---:|---:|---:|
| b12651，正式配置（CPU 專家、`-ub 64`），只有 1–4 號請求 | 286 | 60.4 | 104.6 | 108.0 | 16,918 |
| b12631，全 GPU，4 slot 共用 131k，`-ub 256` | 1,611 | 71.6 | 112.9 | 108.8 | 18,164 |
| b12651，全 GPU，4 slot 共用，`-ub 64` | 1,107 | 85.4 | 146.7 | 146.3 | 18,844 |
| b12651，全 GPU，4 slot 共用，`-ub 256` | 1,801 | 85.0 | 99.5 | 95.9 | 20,758 |
| b12651，全 GPU，4 slot 共用，`-ub 512` | 2,078 | 84.6 | 89.6 | 89.9 | 21,630 |
| b12651，全 GPU，4 slot 共用，`-ub 1024` | 2,104 | 84.6 | 88.7 | 86.2 | 23,372 |
| **b12651，全 GPU，2 slot 各自 131k（`--no-kv-unified`），`-ub 256`（已部署）** | **2,524** | **86.2** | **77.6** | **74.2** | **23,172** |
| UD-Q3_K_XL + Clef 留在 GPU，4 slot 共用，`-ub 128` | 1,526 | 85.4 | 113.0 | 113.8 | 22,699 |
| UD-Q3_K_XL + Clef 留在 GPU，4 slot 共用，`-ub 64` | 1,105 | 86.1 | 146.7 | 148.1 | 22,769 |

觀察：

- **新引擎**：b12651 對比 b12631（同為 `-ub 256`、全 GPU），decode +19%（71.6 → 85.0），prefill +12%。
- **全部放 GPU 是 prefill 最大的來源**：放 CPU 的專家每個 micro-batch 都要經 PCIe 搬一次。
  - 這需要把 Clef 移出 GPU，見第 7 節。
- **2 個 slot 各自 131k 比 4 個 slot 共用 131k 快**（77.6 vs 89.6 s），兩個 agent 同時跑時差距更大（見下表）。
  - 推測原因：共用 KV（unified）時，注意力的範圍是所有序列共用的 cache 區段；各自 KV 時只看自己的序列。
  - 每個 agent 也拿到完整的 131k context，不會互相擠壓。
- `-ub` 從 256 加到 1024，prefill 增加有限，VRAM 卻多 2.6 GB。
  - 2 slot × 131k 時只放得下 `-ub 256`：`-ub 512` 啟動時 CUDA OOM，要多配置 5.5 GB。

兩個 agent 同時跑（`--parallel 2`）：

| 設定 | 兩者合計 prefill tok/s | 合計 decode tok/s | 實際 s（兩個 agent） |
|---|---:|---:|---|
| 4 slot 共用，`-ub 512` | 711 | 8.2 | 385.1／385.2 |
| 4 slot 共用，`-ub 512 -b 512` | 704 | 9.3 | 387.9／388.7 |
| 4 slot 共用，`-ub 1024` | 各自 753／1,029 | 各自 14.5／10.7 | 285.4／329.5 |
| **2 slot 各自 131k，`-ub 256`（已部署）** | 1,971 | 23.1 | **116.5／138.6** |

壓力測試（全部通過，沒有 OOM）：

- 已部署設定，2 × 約 125k tokens 同時送入：111.5 s，GPU 峰值 23,172 MiB；
- 4 slot 共用 131k、`-ub 1024`，1／2／4 個同時：68.8／156.5／161.4 s。

3 個 slot 各自 131k（`-ub 128`）：啟動時 CUDA OOM（要多 2.5 GB），所以 **2 個 slot 是這張卡在 IQ4_XS + 131k 下的上限**。

### 第四個測試窗（2026-11-25）：`-b 256` 沒有改善

假設：`-b 2048` 時，一個 slot 的長 prefill 每一步最多 2,048 tokens（約 1 s），另一個 slot 的 decode 要等它（第 10 節第 2 點）；
`-b 256` 每步最多 256 tokens，decode 應該更流暢。同一個測試窗內、已部署設定（b12651、2 slot 各自 131k、`-ub 256`）只改 `-b`：

| `-b` | 單一 agent：實際 s／decode tok/s | 兩個 agent 同時：實際 s | 兩個同時：各自 decode tok/s | 兩個同時：合計 prefill／decode tok/s | GPU 峰值 MiB |
|---:|---|---|---|---|---:|
| **2048（已部署）** | **75.6／85.2** | **142.6／119.1** | 25.0／31.5 | **1,922／24.7** | 23,174 |
| 256 | 78.5／85.4 | 146.6／133.5 | 32.4／23.4 | 1,869／21.8 | 23,112 |

- 單一 agent 沒有差別；兩個同時時 `-b 256` 反而略慢（合計 decode 24.7 → 21.8 tok/s），各自 decode 的差異方向也不一致。
- 推測：`-b 2048` 一次 `llama_decode` 呼叫裡本來就分成 8 個 256-token 的 micro-batch（`-ub 256`），`-b 256` 只是把它拆成 8 次呼叫，
  多了每次呼叫的排程與取樣開銷，GPU 的總工作量不變。
- `-b 256` 的 2 × 約 125k tokens 壓力測試通過（GPU 峰值 23,112 MiB）。
- 結論：**維持 `-b 2048`**。已部署設定兩次量測一致（window2：116.5／138.6 s；window4：142.6／119.1 s，兩個 agent 誰先誰後不同）。

結果檔：[results/speed/agent/window4](../../results/speed/agent/window4)（`summary.md`）；job：[scripts/jobs/inkling2mini-batch.sh](../../scripts/jobs/inkling2mini-batch.sh)。

結果檔：[results/speed/agent/window](../../results/speed/agent/window)、[window2](../../results/speed/agent/window2)、[window3](../../results/speed/agent/window3)，各有 `summary.md`；伺服器紀錄在 [results/logs](../../results/logs)。

## 6. 投機解碼：MTP（DSpark）與 ngram 都沒有幫助

| 設定（4 slot 共用，`-ub 512`；ngram 為 `-ub 1024`） | 草稿接受率 | decode tok/s | 模擬任務 s | GPU 峰值 MiB |
|---|---:|---:|---:|---:|
| 無草稿（對照） | — | 84.6 | 89.6 | 21,630 |
| DSpark，每步 2 個草稿 token | 66.5% | 81.1 | 92.6 | 22,876 |
| DSpark，每步 3 個（Unsloth 預設） | 57.2% | 86.2 | 91.0 | 22,894 |
| DSpark，每步 5 個 | 38.5% | 79.0 | 93.4 | 22,926 |
| ngram-mod（`-ub 1024` 對照 84.6 / 88.7 s） | 53.7% | 86.2 | 88.2 | 23,372 |

- DSpark 是 Inkling 2 Mini 自帶的 MTP 草稿頭（由官方 `mtp.safetensors` 轉成 GGUF）。
- 接受率不差，但 decode 沒有變快，可能的原因：
  - 這是 MoE 模型，decode 的瓶頸是讀取被啟用的專家權重；
  - 驗證多個草稿 token 時，每個 token 會啟用不同的專家，讀取量幾乎隨 token 數增加；
  - 不像 dense 模型那樣「一次讀權重、驗證多個 token」。
- 草稿模型本身還多占約 1.2 GB VRAM，2 slot × 131k 時沒有空間放。
- ngram 的差異在量測誤差內。

## 7. 決策模型（工具選擇）移到 CPU

全部放 GPU 需要空出 Clef-Flash 占用的 VRAM：

| 決策模型 | 位置 | 選工具召回率 | 中位延遲 | 備註 |
|---|---|---:|---:|---|
| Clef-Flash Q4_K_M（2-pass） | GPU | 100%（52 題） | 256 ms | 會迫使 Inkling 把專家放到 CPU |
| Clef-Flash Q4_K_M（2-pass） | CPU | 75%（8 題） | 20,022 ms | 太慢 |
| **Laya + BM25（已部署）** | CPU | 92.3%（52 題） | 1,231 ms | 常駐 RAM 約 5.2 GiB |

- agent 模式用 `policy: all`，不經決策模型；決策模型只影響 `chat:` 一般對話（帶工具）的工具選擇。
- Clef 在 GPU 上約需 6.5 GB VRAM，與 IQ4_XS 全 GPU + 2 × 131k 放不下。
- 結果檔：[results/speed/laya-cpu](../../results/speed/laya-cpu)、[results/speed/clef-cpu](../../results/speed/clef-cpu)。
- 代價：
  - llama-cot-sentinel 的 `med:` 路由用 Clef 當 critic，所以暫時關閉；
  - `chat:` 對話選工具多約 1 s。

## 8. 部署設定與回復方式

llama-server（`:8081`，systemd 管理；部署腳本在私有部署 repo 中，參數如下）：

```bash
llama-server -m Inkling-2-Mini-UD-IQ4_XS.gguf -ngl all --fit off -fa on \
  -c 262144 -np 2 --no-kv-unified \
  --cache-type-k q8_0 --cache-type-v q8_0 --cache-ram 24576 \
  -b 2048 -ub 256 -n -1 --jinja \
  --temp 1.0 --top-p 1.0 --top-k 0 --min-p 0.0 \
  --chat-template-kwargs '{"reasoning_effort":"medium"}' \
  --mcp-servers-config mcp.json --cors-origins <Web UI 的來源> --allow-unauthenticated-tools
```

- `-c 262144 -np 2 --no-kv-unified`：每個 slot 各自 131,072 tokens；
- `--cache-idle-slots` 為預設開啟，`--ctx-checkpoints` 為預設 32；
- 閒置時 GPU 使用 22.9 GB；
- llama-cot-sentinel 的 `med:` 路由暫停。

router（`:8001`）的 agent 設定：

```json
{
  "reasoning_effort": "max",
  "compaction_effort": "low",
  "compact_tools": true,
  "stable_prefix": true,
  "files": { "agent.patch.yml": "… compaction-basic: headroomTokens 8192, thresholdRatio 0.7, maxTokens 16384 … llama-mcp-router plugin: policy: all …" }
}
```

回復方式：

| 想要 | 做法 |
|---|---|
| 回到 router v0.13 的行為 | `"stable_prefix": false` 後重啟 router |
| 第 3 個以上的同時 agent（犧牲速度） | `-np 4`、`-c 131072`、拿掉 `--no-kv-unified`、`-ub 512`（4 slot 共用 131k，第 5 節的 u4-ub512：模擬 89.6 s，兩人同時各約 385 s） |
| 讓 Clef 與 Sentinel 回到 GPU | 改用 UD-Q3_K_XL、131k 由 4 slot 共用、`-ub 128`（模擬 113.0 s，比部署設定慢 46%），決策模型改回 Clef；先重啟 `:8081` 再重啟決策模型 |
| 舊引擎 | 把 llama-server 換回 `b12631-mix-acc0843` |

## 9. 正式環境驗證

### 9.1 部署 v0.13 與新引擎後、v0.14 之前（17:35–17:59 的真實流量）

- prefill 中位數約 2,020 tok/s（之前約 380）。
- 仍有 35k、45k、67k、85k tokens 的整段重算 → 找到 4.2 節的根因。
- 一個 slot 做長 prefill 時，另一個 slot 的 decode 只剩約 1.2 tok/s（見第 10 節）。

### 9.2 v0.14 上線後

- 短任務的 session 對照見 4.2 節。

端對端任務（錄製的同一個任務，18:03:20–18:08:05；[results/speed/agent/e2e-after-v014.json](../../results/speed/agent/e2e-after-v014.json)）：

- 21 次模型請求全部在 slot 1，總時間 285.3 s，任務完成：找到 3 篇文獻並寫出 `pulmonary.md`。
- 第一個請求只重算 **532 tokens**：沿用 slot 1 上另一個 session 留下的共同前綴。
- 之後每輪重算 7–6,996 tokens（0.1–3.1 s），沒有任何整段重算，也沒有觸發壓縮。
- decode 74–83 tok/s。前兩個請求是 59 tok/s，因為當時 slot 0 有另一個測試 session 同時在生成。
- 時間分配：
  - prefill 22.1 s（8%）；
  - 生成 203.8 s（71%）；
  - 其餘約 59 s 是 PubMed 工具呼叫與 agent 本身。
- 生成成為主要瓶頸。這是最高思考等級的本質：15,436 個輸出 tokens 中大部分是思考。

### 9.3 router v0.15 與新的 DSH 設定（2026-11-25）

DSH 設定（`agent.patch.yml`）的修正：模型名稱 `inkling`（系統提示原本寫著 bonsai）、停用用不到的功能（DeepSeek 網路搜尋、goal、workflow、subagent fork、
MCP resources）讓它們的說明離開 prompt、`get_fulltext` 內文上限 6,000 字元。同一任務在測試 router 上跑（正式的 llama-server）：

| | 9.2（v0.14） | 新 DSH 設定、v0.14 | 新 DSH 設定、v0.15 |
|---|---:|---:|---:|
| 總時間 | 285.3 s | 585.4 s | 598.9 s |
| 模型請求 | 21 | 26 | 26 |
| 重算 prompt tokens（時間） | 43,121（22.1 s） | 84,567（42.4 s） | 95,095（46.0 s） |
| 生成 tokens（時間，速度） | 15,436（203.8 s，75.8 tok/s） | 20,556（268.9 s，76.4 tok/s） | 20,840（266.6 s，78.2 tok/s） |
| 壓縮 | 0 | 1 | **0** |
| 工具呼叫與 agent 本身 | 約 59 s | 約 274 s | 約 286 s（30 次工具呼叫共 279.6 s） |

- **總時間變長不是模型變慢**：模型時間（prefill + 生成）約 226／311／313 s，prefill 與 decode 速度都相同；多出來的是外部 API：
  Semantic Scholar 的速率限制（每次冷卻 30 s）與 Europe PMC 逾時。這兩次的 agent 也做了更多事（讀全文、核對、改稿），生成 tokens 多約 35%。
- **新發現：DSH 不會截斷 MCP 工具結果**。v0.14 那次 agent 用 `read_session` 一次讀進 48,076 與 39,056 字元
  （讀的是 JSON 跳脫過、含 metadata 的 `payload.json`），context 46k → 72k → 90k tokens 而觸發壓縮（生成 4,291 tokens、58 s）。
  v0.15 加上 `tool_result_max_chars: 16000`（固定的頭 + 說明 + 尾，之後每個請求都一樣，不影響前綴快取）與 `read-fulltext` skill 後沒有壓縮；
  DSH 自己的 tool-result pruner 在第 20 個請求免費修剪舊的工具結果（重算 46,457 tokens 中 34,588 用快取，20.8 s，沒有額外的摘要呼叫）。
- **冷 slot 預熱**（v0.15 `warmup`）：2026-11-25 第四個測試窗結束、llama-server 重啟後，router 在 40 s 內依序把共用前綴算進兩個 slot
  （各 34,592 tokens，13.2 s 與 13.4 s，背景優先序）；接著的新 session 第一個請求只重算 **509 tokens（34,588 沿用），0.4 s**。
  - 上線時發現並修正兩個問題：DSH 的第一個請求是 system + 3 則 user 訊息（v0.15.1）；llama-server 讀 `max_completion_tokens` 優先於 `max_tokens`，
    錄下的請求帶著 DSH 的 16,384，預熱會生成上千個思考 token（v0.15.2，在 b12651 上實測確認）。
- 可再加快的選項（未變更，取捨在涵蓋率）：設定 `SEMANTIC_SCHOLAR_API_KEY`，或 `PUBMED_SEARCH_DISABLED_SOURCES=semantic_scholar`。

## 10. 限制與後續

1. **最多 2 個 slot**：第 3 個同時的 agent 要排隊。
   - 需要更多人同時用時，可以改回 4 slot 共用（見第 8 節），但每個人都會變慢。
2. **一個 slot 做長 prefill 時，另一個 slot 的 decode 幾乎停住**：
   - 原因：每一步要等對方的 prefill 才輪到一個 decode token。
   - `stable_prefix` 之後新 session 只需重算幾百 tokens，這種長 prefill 大幅減少；v0.15 的預熱與工具結果上限又再減少冷 slot 與長工具結果的情況。
   - `-b 256` 已實測沒有改善（第 5 節第四個測試窗），4 slot 共用時的 `-b 512` 也沒有。剩下的方向是 llama.cpp 上游的排程改進（例如 decode 優先的 batch 組成）。
3. **冷 slot**：已由 router v0.15 的預熱處理（9.3 節）；預熱在 llama-server 重啟後約 30 s 內開始，期間來的第一個 session 仍要自己算前綴。
4. **`stable_prefix` 依賴 DSH 系統提示的格式**（含 session 路徑的行）。升級 DSH 後要用 `scripts/stable_prefix_check.py` 重測一次。
5. **決策模型**：
   - Laya 在 CPU 上選工具約 1.2 s，召回率 92.3%（Clef 在 GPU 時為 100%）；
   - Sentinel `med:` 暫停。
6. **只量測了一個任務的錄製**（24 個請求，主要看 1–8 號）。
   - 其他類型的任務（大量讀全文、長篇寫作）比例會不同，但這幾個改動都不依賴任務內容。
7. **值得追蹤的上游變化**：
   - Unsloth 的新預編譯版（`gh release list -R unslothai/llama.cpp`；目前最新仍是 b12651）；
   - llama.cpp 對 MoE 模型投機解碼的改進（屆時重測 DSpark）；
   - SWA checkpoint 策略的改進（例如在系統提示結束處也建立 checkpoint，就不需要 `stable_prefix`）。

## 11. 重現

```bash
git clone https://github.com/u9401066/medqa-bench && cd medqa-bench && uv sync

# 1. 錄製：在 router 與 llama-server 之間放錄製代理，在 Web UI 以最高思考等級跑 agent 任務
.venv/bin/python scripts/agent_capture_proxy.py --help

# 2. 重播：對任一 llama-server 比較設定（1–8 號請求、effort max）
.venv/bin/python scripts/agent_replay.py --trace results/speed/agent/trace-xhigh.jsonl \
    --url http://127.0.0.1:8091 --requests 1-8 --effort max --out results/speed/agent/<設定>.json
.venv/bin/python scripts/agent_replay.py ... --parallel 2     # 兩個使用者同時

# 3. GPU 測試窗（會暫停正式服務；job 內含每個設定的參數）
env PAUSE_CLEF=1 "TEST_PATTERN=--port 809[14]" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-agent-speed2.sh

# 3b. -b 2048 vs -b 256（第四個測試窗；job 結束時寫 window4/summary.md）
env "TEST_PATTERN=--port 8091" bash scripts/gpu_window.sh scripts/jobs/inkling2mini-batch.sh

# 4. 新 session 是否沿用前一個 session 的 cache（約 30 s 的單一 slot 時間；需要 llama-mcp-router >= 0.14，用它的 Python 執行）
~/llama-mcp-router/.venv/bin/python scripts/stable_prefix_check.py --url http://127.0.0.1:8081 \
    --out results/speed/stable-prefix/result.json
```
