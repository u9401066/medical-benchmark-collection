# 醫學問答評測：Bonsai 27B vs Inkling 2 Mini（RTX 4090）

產生時間：2026-11-23 15:22（medbench 0.1.0，prompt v1）  
受測系統：**Bonsai 27B PQ2_0**、**Inkling 2 Mini UD-IQ4_XS**

## 摘要

以 1228 題公開醫學題庫（medqa_usmle 428 題、medqa_twmle 400 題、pubmedqa 400 題）在單張 RTX 4090 上做零樣本（zero-shot）評測，同一份題目、提示詞、思考強度與逐題種子；取樣參數各用模型作者的建議值（見 1.4）。

各系統作答的題目不完全相同（有抽樣執行），所有正確率與配對比較都限於**每個系統都作答的 1228 題**；吞吐與能耗仍是各自整次執行的數字。

- **Bonsai 27B PQ2_0**：整體正確率 78.1% [75.7%–80.3%]（959/1228）；解碼中位數 82.2 tok/s；每題中位延遲 13.0 s；吞吐 606 題/小時；GPU 能耗 0.56 Wh/題。
- **Inkling 2 Mini UD-IQ4_XS**：整體正確率 86.6% [84.6%–88.4%]（1064/1228）；解碼中位數 36.3 tok/s；每題中位延遲 13.6 s；吞吐 762 題/小時；GPU 能耗 0.31 Wh/題。
- 配對比較（Bonsai 27B PQ2_0 − Inkling 2 Mini UD-IQ4_XS）：差 -8.6 個百分點，bootstrap 95% CI [-10.7, -6.4]，McNemar 精確檢定 p = <0.001（不一致題 44 vs 149）。

## 1. 方法

### 1.1 資料集

全部從 Hugging Face 固定 revision 下載，下載後比對 SHA-256，題數不符即中止。

| 資料集 | 來源（repo@revision / 檔案） | 題數 | SHA-256（原始 parquet） |
|---|---|---:|---|
| MedQA-USMLE（英文，4 選 1） | `bigbio/med_qa@484a6c066f` / `med_qa_en_4options_source/test-00000-of-00001.parquet` | 428 | `b50b49fad2642c10…` |
| MedQA-TWMLE（繁體中文，台灣醫師國考，4 選 1） | `bigbio/med_qa@484a6c066f` / `med_qa_tw_source/test-00000-of-00001.parquet` | 400 | `9756921fcff39ee4…` |
| PubMedQA-L（英文，摘要閱讀，yes/no/maybe） | `qiaojin/PubMedQA@9001f2853f` / `pqa_labeled/train-00000-of-00001.parquet` | 400 | `3d56bd1abc118845…` |

- MedQA-USMLE：test split 全部 1,273 題（4 選項版本），依 `meta_info` 分 Step 1 與 Step 2&3。
- MedQA-TWMLE：test split 全部 1,413 題。題幹以「承上題」等開頭、需要前一題情境的題目另列子集（本評測一律單題作答，不提供前題）。
- PubMedQA-L：專家標註 1,000 題，提供題目＋摘要內文（不含 long answer 結論段），答 yes/no/maybe；另報告 macro-F1。

### 1.2 作答協定

- 單一 user 訊息、零樣本、不給範例；模型思考（reasoning）開啟，effort 一律 **medium**。
- 只評分最終回答（`content`），不看思考內容。解析規則：取最後一個 `Answer: X`（MCQ 為 A–D，PubMedQA 為 yes/no/maybe）；找不到視為答錯並計入「無答案」。
- 每題用由題目 ID 雜湊得到的固定 seed；各系統的取樣參數見 1.4。
- 被截斷（`finish_reason=length`）照樣解析，另外計數。HTTP/串流錯誤會重試 2 次，仍失敗記為錯誤且算答錯。

提示詞範本（`medbench/prompts.py`，版本 v1）：

<details><summary>MCQ_EN (MedQA-USMLE, MedMCQA)</summary>

```text
Answer the following multiple-choice question about medicine. Exactly one option is correct.

{question}

{options}

Think it through, then give your final answer on the last line in the form "Answer: X", where X is one of {letters}.
```

</details>

<details><summary>MCQ_ZH_TW (MedQA-TWMLE)</summary>

```text
請回答以下醫學單選題，只有一個正確選項。

{question}

{options}

請先思考，最後一行以「Answer: X」的格式作答，X 為 {letters} 其中之一。
```

</details>

<details><summary>YESNO_EN (PubMedQA)</summary>

```text
Read the abstract (without its conclusion) and answer the research question with yes, no or maybe.

Abstract:
{context}

Question: {question}

Think it through, then give your final answer on the last line in the form "Answer: yes", "Answer: no" or "Answer: maybe".
```

</details>

### 1.3 統計方法

- 正確率 95% 信賴區間：Wilson score interval。
- 兩系統配對比較：只用兩邊都有作答紀錄的同一批題目；McNemar 精確檢定（雙尾二項檢定，看不一致題）；正確率差的 95% CI 用配對 bootstrap（10,000 次，seed 0）。
- 速度：每題時間從送出請求到串流結束（含排隊與 prefill）；TTFT 為第一個（思考或回答）token 的時間；解碼速度 = (completion tokens − 1) / (最後 token 時間 − 第一 token 時間)。
- 資源：每秒取樣一次 `nvidia-smi`（VRAM、使用率、功耗、溫度）、`/proc/meminfo`、`/proc/stat` 與伺服器行程 RSS。每段執行前先記錄 15 秒閒置作為功耗基準；能耗以梯形積分計算。

### 1.4 受測系統與硬體

硬體：NVIDIA GeForce RTX 4090, 24564 MiB, 570.211.01；CPU 13th Gen Intel(R) Core(TM) i7-13700；RAM 54.9 GiB；Linux-5.15.0-190-generic-x86_64-with-glibc2.35。

| 項目 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---|---|
| 模型 | Ternary-Bonsai-2-27B-Abliterated-v2（Qwen3.8-27B 架構，dense 27B） | Inkling-2-Mini（Thinking Machines Lab；MoE 26.2B 總參數、每 token 啟用 3.4B，中間 12 層重複 3 次，等效 5.4B） |
| 權重 / 量化 | PQ2_0 三元（ternary）權重 + MTP 頭，GGUF 7.1 GiB（7,303 MiB） | Unsloth UD-IQ4_XS（Dynamic 3.0 imatrix），GGUF 14.65 GiB |
| 推論引擎 | PrismML llama.cpp fork prism-b10787（llama-server）+ MTP 推測解碼 | Unsloth llama.cpp prebuilt b12631-mix-acc0843（上游 b12631 + looped-layer / DSpark 修補，CUDA 12.8），不用推測解碼 |
| 放置方式 | 全部層在 GPU（-ngl 99），KV 131,072 tokens / 4 slots，flash-attn | 全部層在 GPU（-ngl all），KV q8_0、65,536 tokens 由 4 個 slot 共用（--kv-unified），-ub 256，flash-attn |
| 取樣參數 | temperature 1.0、top_p 0.95、top_k 20、min_p 0.05（模型 GGUF 內建預設），逐題 seed | temperature 1.0、top_p 1.0、top_k 0、min_p 0（模型作者建議，不截斷），逐題 seed |
| 併發請求數 | 3 | 4 |
| 請求額外參數 | `{"max_tokens": 16384, "temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.05, "chat_template_kwargs": {"reasoning_effort": "medium"}}` | `{"max_tokens": 16384, "temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.0, "chat_template_kwargs": {"reasoning_effort": "medium"}}` |
| 執行期間 | 10-20 16:51→10-20 17:59；10-21 06:14→10-21 11:11 | 11-23 10:40→11-23 12:14；11-23 12:15→11-23 12:17 |

## 2. 正確率

| 資料集 | n | 多數類別基準 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---:|---:|---:|---:|
| medqa_usmle | 428 | 26.9%（A） | 84.8% [81.1%–87.9%] | 92.1% [89.1%–94.3%] |
| medqa_twmle | 400 | 27.3%（C） | 79.2% [75.0%–82.9%] | 94.5% [91.8%–96.3%] |
| pubmedqa | 400 | 51.2%（yes） | 69.8% [65.1%–74.0%] | 73.0% [68.4%–77.1%] |
| **全部** | 1228 | — | **78.1% [75.7%–80.3%]** | **86.6% [84.6%–88.4%]** |

多數類別基準 = 永遠回答該資料集最常見的正確答案時的正確率（隨機猜測的參考線）。中括號為 95% Wilson 信賴區間。

### 2.1 子集

| 資料集 | 子集 | n | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---|---:|---:|---:|
| medqa_usmle | step1 | 231 | 85.7% [80.6%–89.6%] | 95.2% [91.7%–97.3%] |
| medqa_usmle | step2&3 | 197 | 83.8% [78.0%–88.3%] | 88.3% [83.1%–92.1%] |
| medqa_twmle | standalone | 392 | 79.8% [75.6%–83.5%] | 94.9% [92.3%–96.7%] |
| medqa_twmle | depends_on_previous (承上題) | 8 | 50.0% [21.5%–78.5%] | 75.0% [40.9%–92.9%] |
| pubmedqa | gold=yes | 205 | 81.0% [75.1%–85.8%] | 78.0% [71.9%–83.2%] |
| pubmedqa | gold=no | 148 | 64.2% [56.2%–71.5%] | 75.0% [67.5%–81.3%] |
| pubmedqa | gold=maybe | 47 | 38.3% [25.8%–52.6%] | 44.7% [31.4%–58.8%] |
| pubmedqa | macro_f1 | — | 0.606 | 0.646 |

### 2.2 配對比較

**Bonsai 27B PQ2_0（A） vs Inkling 2 Mini UD-IQ4_XS（B）**

| 資料集 | n | A | B | A − B（95% CI） | 都對 | 只有 A 對 | 只有 B 對 | 都錯 | McNemar p |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|
| medqa_twmle | 400 | 79.2% | 94.5% | -15.2 [-19.5, -11.2] | 309 | 8 | 69 | 14 | <0.001 |
| medqa_usmle | 428 | 84.8% | 92.1% | -7.2 [-10.7, -4.0] | 349 | 14 | 45 | 20 | <0.001 |
| pubmedqa | 400 | 69.8% | 73.0% | -3.2 [-7.0, +0.5] | 257 | 22 | 35 | 86 | 0.111 |
| **全部** | 1228 | 78.1% | 86.6% | -8.6 [-10.7, -6.4] | 915 | 44 | 149 | 120 | <0.001 |

### 2.3 失敗模式

| 資料集 | 指標 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---|---:|---:|
| medqa_usmle | 無可解析答案 | 0 | 0 |
| medqa_usmle | 達 max_tokens 截斷 | 0 | 0 |
| medqa_usmle | 請求錯誤 | 0 | 0 |
| medqa_usmle | 未作答 | 0 | 0 |
| medqa_twmle | 無可解析答案 | 0 | 0 |
| medqa_twmle | 達 max_tokens 截斷 | 0 | 0 |
| medqa_twmle | 請求錯誤 | 0 | 0 |
| medqa_twmle | 未作答 | 0 | 0 |
| pubmedqa | 無可解析答案 | 0 | 0 |
| pubmedqa | 達 max_tokens 截斷 | 0 | 0 |
| pubmedqa | 請求錯誤 | 0 | 0 |
| pubmedqa | 未作答 | 0 | 0 |

### 2.4 答案分佈與混淆

選擇題預測答案分佈（檢查位置偏誤；none = 無可解析答案）：

| 資料集 | 系統 | A | B | C | D | none |
|---|---|---:|---:|---:|---:|---:|
| medqa_usmle | 正確答案 | 115 | 114 | 108 | 91 | 0 |
| medqa_usmle | Bonsai 27B PQ2_0 | 105 | 122 | 120 | 81 | 0 |
| medqa_usmle | Inkling 2 Mini UD-IQ4_XS | 110 | 117 | 109 | 92 | 0 |
| medqa_twmle | 正確答案 | 97 | 104 | 109 | 90 | 0 |
| medqa_twmle | Bonsai 27B PQ2_0 | 97 | 111 | 114 | 78 | 0 |
| medqa_twmle | Inkling 2 Mini UD-IQ4_XS | 101 | 104 | 104 | 91 | 0 |

PubMedQA 混淆矩陣（列 = 正確答案，欄 = 模型回答）：

**Bonsai 27B PQ2_0**

| 正確 \ 回答 | yes | no | maybe | none |
|---|---:|---:|---:|---:|
| yes | 166 | 11 | 28 | 0 |
| no | 15 | 95 | 38 | 0 |
| maybe | 25 | 4 | 18 | 0 |

**Inkling 2 Mini UD-IQ4_XS**

| 正確 \ 回答 | yes | no | maybe | none |
|---|---:|---:|---:|---:|
| yes | 160 | 12 | 33 | 0 |
| no | 9 | 111 | 28 | 0 |
| maybe | 17 | 9 | 21 | 0 |

## 3. 速度

| 資料集 | 指標 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---|---:|---:|
| medqa_usmle | 輸入 tokens（平均） | 270 | 285 |
| medqa_usmle | 輸出 tokens（中位/平均） | 1415 / 1819 | 566 / 817 |
| medqa_usmle | TTFT 中位（s） | 0.49 | 0.39 |
| medqa_usmle | 每題延遲 中位 / P90（s） | 17.8 / 41.2 | 15.9 / 45.7 |
| medqa_usmle | 單請求解碼中位（tok/s） | 81.9 | 36.5 |
| medqa_usmle | 伺服器端 prefill / 解碼中位（tok/s） | 1209 / 82.0 | 896 / 36.4 |
| medqa_usmle | 推測解碼草稿接受率 | 60.0% | — |
| medqa_twmle | 輸入 tokens（平均） | 156 | 184 |
| medqa_twmle | 輸出 tokens（中位/平均） | 1092 / 1452 | 472 / 688 |
| medqa_twmle | TTFT 中位（s） | 0.41 | 0.30 |
| medqa_twmle | 每題延遲 中位 / P90（s） | 14.1 / 34.2 | 12.8 / 34.6 |
| medqa_twmle | 單請求解碼中位（tok/s） | 81.8 | 36.9 |
| medqa_twmle | 伺服器端 prefill / 解碼中位（tok/s） | 825 / 81.9 | 826 / 36.8 |
| medqa_twmle | 推測解碼草稿接受率 | 58.6% | — |
| pubmedqa | 輸入 tokens（平均） | 420 | 430 |
| pubmedqa | 輸出 tokens（中位/平均） | 689 / 756 | 426 / 488 |
| pubmedqa | TTFT 中位（s） | 0.46 | 0.50 |
| pubmedqa | 每題延遲 中位 / P90（s） | 8.8 / 14.9 | 12.5 / 23.3 |
| pubmedqa | 單請求解碼中位（tok/s） | 83.0 | 35.4 |
| pubmedqa | 伺服器端 prefill / 解碼中位（tok/s） | 1583 / 83.1 | 1068 / 35.3 |
| pubmedqa | 推測解碼草稿接受率 | 64.7% | — |

「單請求解碼」以用戶端收到的串流計時（含網路與排隊）；「伺服器端」為伺服器在串流最後回報的 llama.cpp 格式 timings（prompt_n/prompt_ms、predicted_n/predicted_ms、draft_n/draft_n_accepted；沒有回報時顯示 —）。

| 資料集 | 指標 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---|---:|---:|
| 全部 | 實際執行時間 | 6.08 h | 1.61 h |
| 全部 | 總輸出 tokens | 1,661,611 | 819,857 |
| 全部 | 總吞吐（tok/s，含併發） | 237.2 | 141.3 |
| 全部 | 題/小時 | 606 | 762 |

## 4. 資源耗用

| 指標 | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---:|---:|
| GPU VRAM 平均 / 峰值（整張卡） | 20.7 GiB / 20.7 GiB | 23.4 GiB / 23.5 GiB |
| GPU 使用率平均 | 88% | 82% |
| GPU 功耗 閒置 / 平均 / 峰值（W） | 48 / 341 / 366 | 90 / 239 / 300 |
| GPU 能耗總計（Wh） | 2075 | 385 |
| GPU 能耗（扣閒置，Wh） | 1782 | 240 |
| GPU 能耗 / 題（Wh） | 0.56 | 0.31 |
| GPU 能耗 / 答對一題（Wh） | 0.72 | 0.36 |
| 伺服器行程 RSS 平均 / 峰值 | 25.6 GiB / 26.5 GiB | 22.4 GiB / 25.8 GiB |
| 系統 RAM 使用 平均 / 峰值 | 30.6 GiB / 32.1 GiB | 26.8 GiB / 30.1 GiB |
| CPU 使用率平均（全機） | 12% | 10% |
| GPU 溫度峰值（°C） | 71 | 65 |
| 同時有其他使用者請求的時間比例 | 0.0% | 0.0% |

註：VRAM、功耗與系統 RAM 為整機量測，包含同時常駐的其他服務（見第 5 節）；能耗只計 GPU，不含 CPU 與其他元件。

## 5. 測試環境與設定細節

- **主機**：llm01，KVM 虛擬機，12 個 vCPU（宿主 CPU 為 Intel i7-13700）、RAM 55 GiB（另有 16 GiB swap）、單張 RTX 4090 24 GB 以 PCIe 直通（Gen4 x16，driver 570.211.01）、Ubuntu 22.04。
- **同卡常駐的決策模型**：Clef-Flash（9B，Q4_K_M，約 6.4 GiB VRAM）在所有量測期間都常駐同一張卡。它是 llama-mcp-router 選工具與 Sentinel 檢查推理用的模型，正式環境不能拿掉，所以受測的聊天模型只能使用約 17.6 GiB。
- **Bonsai 27B**（現行正式模型）：
  - 醫學題庫的結果來自 2026-10-20/21 在正式服務上的全量執行：3,686 題、3 併發；PrismML llama.cpp `prism-b10787`、MTP 推測解碼、131,072 tokens 由 4 個 slot 共用。
  - 本報告只取 Inkling 也有作答的 1,228 題做比較。
  - 工具呼叫、slot 掃描、多輪快取與 agent 測試都在 2026-11-23 重新量測。
- **Inkling 2 Mini**：
  - Thinking Machines Lab 2026-11-20 發布，Apache-2.0。MoE 架構，總參數 26.2B、每個 token 啟用 3.4B。
  - 24 層中的第 6–17 層每個 token 重複執行 3 次，等於 48 次層運算。其中只有 8 次是全域注意力，其餘是 1,024 token 的滑動視窗。
  - 原生 context 為 1,048,576 tokens。
  - 權重採用 Unsloth 的 UD-IQ4_XS（14.7 GiB）；專家權重為 NVFP4 格式，注意力權重為 Q8_0。
  - 推論引擎是 Unsloth 預編譯的 llama.cpp `b12631-mix-acc0843`（上游 b12631 加上 Inkling 修補）。
- **Inkling 的評測方式**：
  - 在維護時段執行：暫停正式的 Bonsai，在測試埠 :8091 啟動受測伺服器，用 `scripts/gpu_window.sh` 搭配 `scripts/jobs/inkling2mini*.sh`，結束時自動恢復正式服務。
  - 醫學題庫：每個題庫平均間隔抽 400 題（`--sample 400`）；IQ4_XS 另外多跑了 28 題 USMLE。
  - 4 併發；IQ4_XS 伺服器設定為 65,536 tokens 由 4 個 slot 共用、`-ub 256`。
- **取樣參數**：各自採用模型作者的建議值。
  - Bonsai：temperature 1.0、top_p 0.95、top_k 20、min_p 0.05。
  - Inkling：temperature 1.0、top_p 1.0、top_k 0、min_p 0。
  - 思考強度兩者都是 medium（Inkling 的刻度為 0.7）。
- **程式版本**：Inkling 兩次執行的 manifest 記錄的是 medqa-bench `ed1ce39`。執行時另有一處尚未提交的 runner 修改，只多記錄每段執行的 base_url、併發與抽樣數，提示詞與解析都沒變；這處修改已在 `88db398` 提交。
- **正式服務停機時段**（UTC，2026-11-23）：10:16–10:23、10:27–12:17、12:18–12:36、12:36–12:48、13:10–15:12、15:14 起（部署 IQ4_XS）。

## 6. 討論

### 6.1 正確率：Inkling 2 Mini 顯著較高，台灣國考差距最大

- **整體**（共同的 1,228 題）：Inkling 86.6%，Bonsai 78.1%。配對差 +8.6 個百分點（95% CI 6.4–10.7）；答案不一致的題目中，只有 Inkling 答對 149 題、只有 Bonsai 答對 44 題，McNemar p < 0.001。
- **各題庫**：
  - MedQA-TWMLE（繁體中文台灣國考）：94.5% vs 79.2%，+15.2，p < 0.001。
  - MedQA-USMLE：92.1% vs 84.8%，+7.2，p < 0.001。
  - PubMedQA：73.0% vs 69.8%，+3.2，p = 0.11，不顯著。
- **Inkling 想得比較短**：每題平均輸出 817 / 688 / 488 tokens（USMLE / TWMLE / PubMedQA），Bonsai 為 1,819 / 1,452 / 756，大約只有一半。兩者在這 1,228 題中都沒有「無答案」或被截斷的情況。
- **同一模型的較小量化 UD-Q3_K_XL**：
  - 已完成 814 題（USMLE 400、TWMLE 400、PubMedQA 14），15:12 為了部署 IQ4_XS 提前停止。
  - 與 IQ4_XS 配對：92.1% vs 92.6%，差 −0.5（p = 0.58）。量化從 IQ4_XS 降到 Q3_K_XL 沒有可量測的損失；TWMLE 可能略低（3 : 10，p = 0.09）。
  - 與 Bonsai 配對：+10.1 個百分點（p < 0.001）。
- **作為量級參考**：Med-PaLM 2 在 MedQA 的最高成績為 86.5%（作答條件不同，不能直接比較）。

### 6.2 工具呼叫：Bonsai 第一步就選對工具的比例較高

測試集來自 llama-mcp-router 的 `benchmarks/run_bench.py`，評分方式是看模型的第一次工具呼叫是否選對工具（溫度 0）。原始結果與比較程式在 `results/toolbench/`。

| 題組（提供的工具數） | Bonsai 27B | Inkling IQ4_XS | Inkling Q3_K_XL | 配對（Bonsai 對、Inkling 錯 : 反之） |
|---|---:|---:|---:|---|
| held-out 52 題，41 個工具全給 | 51（98.1%） | 48（92.3%） | 46（88.5%） | IQ4 3 : 0（p = 0.25）；Q3 5 : 0（p = 0.06） |
| held-out 52 題，Clef 兩段式選工具 | 51（98.1%） | 48（92.3%） | 47（90.4%） | IQ4 4 : 1（p = 0.38）；Q3 5 : 1（p = 0.22） |
| hard 110 題，61 個工具（含 12 題不需工具） | 101（91.8%） | — | 96（87.3%） | Q3 5 : 0（p = 0.06） |
| 合併 162 題（全給工具） | 152（93.8%） | — | 142（87.7%） | Q3 10 : 0（**p = 0.002**） |

- IQ4_XS 跑 hard 題組時失敗：61 個工具的 schema 約 50k tokens，在 65,536 context 下 compute buffer 不夠。
- **Inkling 的錯誤多半是「先查看再動手」**：第一步先呼叫 `read_session`、`list_pipelines`、`list_resolver_presets` 或 `list_collections`，而不是直接執行使用者要求的匯出、排程、儲存或匯入（hard 題組 14 個錯誤中有 10 個屬於這類）。在 agent 多步驟流程裡，這通常只是多一步，不是做錯；但這個測試只看第一步。
- 其他錯誤：圖片類請求沒有呼叫工具；3 題一般知識問題（本來不需要工具）卻去搜尋文獻。
- 41 個工具的 schema 在 Inkling 的 tokenizer 下約 39.6k tokens，Bonsai 為 30.6k。正式環境的 router 用 Clef 兩段式選工具，平常每次只送約 6 個工具（約 5.5k tokens）。

### 6.3 中文輸出：Inkling 幾乎沒有簡體字，但回答精簡、思考是英文

以 MedQA-TWMLE 共同的 400 題計算（`scripts/zh_quality.py --common`，用 OpenCC 判定簡體專用字；考題本身出現過的字不計）：

| 指標 | Bonsai 27B | Inkling IQ4_XS | Inkling Q3_K_XL |
|---|---:|---:|---:|
| 回答含 3 個以上簡體專用字的比例 | 22.2% | 0.2% | 0.0% |
| 回答中簡體字占繁簡可區分字的平均比例 | 3.3% | 0.2% | 0.1% |
| 回答主要是英文的比例 | 10.0% | 10.5% | 12.5% |
| 回答的漢字數（中位數） | 230 | 60 | 63 |
| 思考內容主要是英文的比例 | 98.0% | 99.8% | 99.8% |

- 對以繁體中文為主的使用者，Inkling 明顯較乾淨；Bonsai 的回答約五分之一會混入簡體字（例如 agent 測試中的「机械」）。
- 模型卡也提醒 Inkling 的中文能力與醫療用途有限制：它的回答精簡，需要詳細解釋時要在提示中明確要求。

### 6.4 速度與 slot 數

以下是同一支測試程式（`scripts/slot_sweep.py`）在同一張卡、Clef 常駐的條件下量測的結果。每個請求最多輸出 1,024 tokens，思考強度 medium。

| 設定 | 併發 1：每請求 tok/s | 併發 2：每請求 / 總計 | 併發 4：每請求 / 總計 | prefill（5k tokens） | GPU 峰值 |
|---|---:|---:|---:|---:|---:|
| Bonsai 27B，4 slots，131k，MTP | 145.7 | 111.9 / 215 | 73.5 / 271 | 2,764 | 20.7 GiB |
| Bonsai 27B，8 slots（每 slot 16k） | 149.0 | 61.5 / 133 | 41.7 / 158 | 2,727 | 22.3 GiB |
| Inkling IQ4_XS，4 slots，65k，`-ub 256`，全 GPU | 81.3 | 58.6 / 111 | 37.6 / 140 | 2,375 | 23.1 GiB |
| Inkling IQ4_XS，2 slots，65k，`-ub 256` | 80.6 | 59.4 / 116 | — | 2,461 | 22.7 GiB |
| Inkling Q3_K_XL，4 slots，131k，`-ub 64`，全 GPU | 82.5 | 60.0 / 109 | 37.1 / 136 | 1,214 | 23.4 GiB |
| **Inkling IQ4_XS，4 slots，131k，`-ub 64`，3 層專家在 CPU（部署設定）** | **56.0** | — | — | **393** | 22.3 GiB |

- **單請求生成速度**：Bonsai 約為 Inkling 的 1.8 倍（MTP 推測解碼，接受率約 60%）。Inkling 自帶的 DSpark 草稿模型接受率只有 35–38%，單請求沒有加速，併發時總吞吐反而下降（113 vs 140 tok/s），所以沒有啟用。
- **每題延遲差不多**：Inkling 的輸出只有一半，所以醫學題每題的中位延遲相近（13.6 vs 13.0 s，各自在 4 / 3 併發下）。題 / 小時 762 vs 606，每題 GPU 能耗 0.31 vs 0.56 Wh。
- **slot 建議：4 個**（131k context 由 4 個 slot 共用，`--kv-unified`）。
  - 8 slots：Bonsai 用 `-np 8` 時每個 slot 只剩 16k，19k 的提示會被拒絕；Inkling IQ4_XS 開 8 slots 在 8 併發時直接當機。
  - 2 slots：單一或兩個請求的速度和 4 slots 一樣，但同時能服務的人變少。
  - 4 併發時，Inkling 每個請求約 37 tok/s，Bonsai 約 74 tok/s。
- **多輪對話快取**：Bonsai 從第 2 輪起每輪只重讀約 30 tokens；插入 3 個其他對話後再回到原對話，快取仍完整命中（`--cache-ram 24576`）。Inkling 的結果會在上線後補上。

### 6.5 VRAM 與 context 上限：IQ4_XS 要更長的 context 必須把部分專家放到 CPU

- **Inkling 的 KV 開銷**：每個 token 在 8 次全域注意力運算上的 q8_0 KV 約 17 KB。131,072 tokens 約 2.1 GiB；原生的 1,048,576 tokens 約 17 GiB，在 24 GB 卡上不可能。
- **全部放 GPU 的上限**：在 Clef 旁邊，IQ4_XS 的 14.2 GiB 權重全放 GPU 只容得下約 65k tokens，而且併發長提示仍會當機。原因是量化 KV 在 attention 的 dense 路徑上會暫時轉成 F16，131k 時執行期額外需要約 1.1 GiB；Unsloth 表示正在修正。
- **專家放 CPU 的代價**：只移非迴圈層（第 20–22、0–5、18 層，每個 token 只跑一次），迴圈層不動。實測：

| context | 專家在 CPU 的層數 | 空出 VRAM | 單請求 tok/s | prefill（5k tokens） |
|---|---:|---:|---:|---:|
| 131,072 | 3（20、21、22） | 1,771 MiB | 56 | 393 |
| 196,608 | 6 | 2,053 MiB | 43 | 237 |
| 262,144 | 10 | 2,885 MiB | 32 | 155 |
| 參考：Q3_K_XL 131,072，全 GPU | 0 | — | 82.5 | 1,214 |

- **prefill 掉得特別多**：每個 64-token 的批次都要經 PCIe 把這幾層的全部專家（每層約 0.6 GB）搬上 GPU。部署規則是「速度不低於 131k 方案 80% 的最長 context」，所以 196k 和 262k 都沒有選上。

### 6.6 量化版本的選擇（同一個模型）

| 量化 | 檔案大小 | 在 Clef 旁 131k context | 醫學題正確率 | 速度（單請求 / prefill） |
|---|---:|---|---|---|
| UD-Q4_K_XL | 17.6 GB | 全放 GPU 放不下；3 層專家放 CPU 時只測了 65k | 未測（Unsloth KLD top-1 98.0% vs IQ4_XS 97.7%） | 55 / — |
| **UD-IQ4_XS（部署中）** | 14.7 GB | 3 層專家放 CPU | 86.6%（1,228 題） | 56 / 393 |
| UD-Q3_K_XL | 13.6 GB | 全部在 GPU | 與 IQ4_XS 差 −0.5（814 題，p = 0.58） | 82.5 / 1,214 |

- 依使用者指示部署 IQ4_XS，context 開到在穩定前提下最長的 131,072。
- 若更在意速度，Q3_K_XL 在同樣 131k context 下快 1.5 倍、prefill 快 3 倍，正確率沒有可量測的差異。工具呼叫 Q3 略低（held-out 46–47 vs 48 / 52，樣本小）。
- 切換只需改 `config/inkling.env` 的 `INKLING_MODEL`，並移除 `INKLING_CPU_MOE_LAYERS`。

### 6.7 部署與上線驗證

- **部署設定**：UD-IQ4_XS、131,072 tokens 由 4 個 slot 共用、`-ub 64`、第 20–22 層專家放 CPU（`config/inkling.env`；`config/llm.env` 設 `LLM_MODEL=inkling`，由 `scripts/start_bonsai.sh` 轉到 `start_inkling.sh`）。
- **選擇過程**：`scripts/jobs/inkling2mini-iq4xs-maxctx.sh` 先探測 131k / 196k / 262k，取速度不低於 131k 方案 80% 的最長 context，再做完整穩定性測試，通過才寫入正式設定。完整穩定性測試包括：
  - 82% context 的併發長提示壓力測試（1 / 2 / 4 個同時）；
  - 1 / 2 / 4 併發掃描；
  - 再做一次壓力測試與 4 併發。
- **本報告產出時（15:25 UTC）**：131k 設定的穩定性測試仍在進行，正式服務暫停中，測試通過後自動上線。
- **Sentinel（`med:`）**：llama-cot-sentinel 0.2.0 已支援 Inkling 的格式。Inkling 的思考段以特殊 token `<|end_message|>` 結束，llama-server 會從文字中移除它，所以改用 token id 判斷。已在正式環境更新，對 Inkling 實測 2 個臨床問題：思考與回答正確分開，回答為繁體中文。
- **agent 端到端（基準）**：Bonsai 完成「找 2 篇 remimazolam ICU 鎮靜 RCT 存成 CSV」花 64.6 秒（7 次模型請求、輸出 4,667 tokens、126.8 tok/s）。Inkling 會在上線後用同一個任務量測（`llmapi_server/scripts/agent_smoke.py`）。

### 6.8 結論

1. **醫學知識與繁體中文：Inkling 2 Mini 明顯勝出**。醫學題 +8.6 個百分點（台灣國考 +15.2），回答幾乎沒有簡體字，每題耗能約一半。
2. **工具呼叫與速度：Bonsai 勝出**。第一次選對工具的比例高約 6 個百分點（合併 162 題，p = 0.002）；單請求生成快 1.8 倍；prefill 是 131k 設定 Inkling 的 2.3 倍（Q3_K_XL）到 7 倍（IQ4_XS）。
3. **部署建議**：
   - 4 個 slot、131,072 tokens 共用。
   - IQ4_XS 需要把 3 層專家放 CPU；Q3_K_XL 可全放 GPU、速度較好。
   - 回復 Bonsai 只需 `config/llm.env` 設 `LLM_MODEL=bonsai` 並重啟 :8081。
4. **加速的後續方向**：
   - Unsloth 已合併、但尚未發布預編譯版的 Inkling CUDA 最佳化（unslothai/llama.cpp#411–#418），在 Ada 等 GPU 上的實測為生成約 +20–25%、4 個序列 +40–60%、prefill +8–18%。
   - 專家放 CPU 時的 MoE 快取去重（unslothai/llama.cpp#421）實測快 1.9 倍。
   - 新版發布後應重跑本報告的 slot 掃描與壓力測試。

## 7. 限制

- **樣本數**：Inkling 的醫學題是每個題庫 400 題的抽樣（共 1,228 題），信賴區間比全量寬；Q3_K_XL 的 PubMedQA 只有 14 題。
- **執行時間不同**：Bonsai 的醫學題結果早一個月（同一主機、同一 driver、同一提示詞與解析器），而且是在正式服務上跑的；Inkling 在測試埠獨占執行。
- **取樣與併發不同**：兩者的取樣參數各自採用作者建議值，所以差異包含取樣設定的影響。醫學題的速度數字分別是 3 與 4 併發，直接比較速度請看 6.4 的同條件掃描。
- **工具呼叫測試**：每組 52–110 題，只看第一次呼叫，不代表完整 agent 任務的成功率。
- **引擎版本**：Inkling 依賴 Unsloth 快速更新中的預編譯引擎（非主線 llama.cpp），模型發布才 3 天，已知問題（記憶體、速度、過度思考）仍在修正，結果可能隨版本改變。
- **用途**：本評測是知識型選擇題，不代表臨床安全性；模型卡也提醒 Inkling 不應直接用於醫療決策。Sentinel（`med:`）是研究工具，不是經驗證的安全裝置。

## 重現步驟

```bash
git clone https://github.com/u9401066/medqa-bench && cd medqa-bench
uv venv && uv pip install -e '.[test]'
medbench prepare                       # 下載、驗證 SHA-256、正規化成 data/*.jsonl
medbench run --config configs/bonsai27b-pq2-medium.json   # 可中斷續跑
# Inkling 2 Mini UD-IQ4_XS：run in a maintenance window: production (Bonsai on :8081) paused, Clef-Flash stays on the GPU
INKLING_CTX=65536 INKLING_DRAFT=none INKLING_HOST=127.0.0.1 INKLING_PORT=8091 INKLING_SLOTS=4 INKLING_UBATCH=256 LLM_IGNORE_PAUSE=1 bash llmapi_server/scripts/start_inkling.sh &
medbench run --config configs/inkling2mini-iq4xs-medium.json   # 可中斷續跑
medbench score results/bonsai27b-pq2-medium results/inkling2mini-iq4xs-medium
medbench report results/bonsai27b-pq2-medium results/inkling2mini-iq4xs-medium --out reports/inkling2mini/REPORT.md --notes reports/inkling2mini/notes.md
```

每個 `results/<run>/` 內含 `manifest.json`（設定、git 版本、伺服器 /props、資料雜湊、主機資訊、執行時段）、`predictions.jsonl`（逐題答案與時間）、`raw.jsonl.gz`（完整思考與回答）、`resources.csv`（每秒資源）、`summary.json`。
