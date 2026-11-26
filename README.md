# Medical Benchmark Collection

本專案蒐集醫學 AI 評測，記錄每個資料集的來源、版本與可評估的任務。除了既有題庫，也將與臨床醫師共同編寫新題，製作符合臺灣臨床用語的繁體中文版及美式英文版。改編題保留原題對照，並記錄支持答案的證據、適用地區及審查狀態。[評測目錄](datasets/catalog.md) · [編題與臨床審查流程](docs/editorial-workflow.md)

## 現有評測工具

醫師可以從雙語審查目錄選一題，核對歷史與現行答案、詳解或引文。完整題庫判分另有兩組配對比較，按病例家族估計差異，並保留尚待裁決的上下界。[雙語審查本](docs/review/queue-2026-11-26.md) · [版本審核與匯出](docs/editorial-workflow.md#審查紀錄與資料匯出) · [配對比較](docs/temporal-evaluation.md#同一份題本如何比較兩個模型)

當期工作保留原考期答案，並由醫師依指定日期、地區及證據另審現行答案和詳解。臺灣公費大腸癌篩檢題測量模型是否沿用已失效的選項。美國乳房攝影題比較同一病例在兩個機構指引下的篩檢間隔。每週檢查來源段落，並依 PMID 整理待查的評測研究。[臺灣公費篩檢審題單](docs/review/tw-fit-controls.md) · [美國指引分歧審題單](docs/review/us-mammography-interval.md) · [目標與交接](docs/roadmap.md) · [臨床時效維護](docs/editorial-workflow.md#臨床時效維護) · [臨床判分與評估](docs/temporal-evaluation.md)

首輪批次實驗以 Qwen2.5 1.5B 在 CPU 上回答兩組各 12 題的英文解剖學題。兩組都以獨立併發 2 最快。Test 組單題與雙題共用提示的總分均為 9/12，逐題比較卻有一題由對改錯、另一題由錯改對。[實測數字與逐題回覆](reports/anatomy-batch-pilot/README.md) · [後續實驗](docs/roadmap.md#批次作答的速度與題間干擾)

第二輪將目標題位置與鄰題分開輪替。同一模型的六題單獨重跑時都維持原選項，搭配指定鄰題 B 並移至第二位時，有兩題改選。臺灣成人預防保健另有可直接複審的雙語題及來源檢索任務，可檢查模型是否引用詢問日已公布、已生效且適用於該族群的依據。[題位與鄰題實驗](reports/anatomy-batch-pilot/position-neighbor/README.md) · [雙語審題單](docs/review/tw-adult-preventive.md) · [政策來源檢索](reports/tw-preventive-source-pilot/README.md)

同一模型回答臺灣公費篩檢的歷史與現行問法時，限定 JSON Schema 後，美式英文可解析回覆從 0/6 增為 6/6。兩種設定下，各 12 份作答都沒有可解析且符合該日期編者擬答的選項。24 份原始作答均保留，供醫師核對回答理由與雙語用詞。[日期與輸出格式實測](reports/tw-fit-date-probe/README.md)

臺灣醫學會已按科別整理，附官網核對狀態、部定專科及次專科的來源，以及學會公開甄審試題、樣題與答案的入口。[依科別找學會](datasets/tw-societies/by-specialty.md) · [直接找考試資料](datasets/tw-societies/exam-sources.tsv)

醫師可直接從 12 份臺灣公費篩檢作答開始試審，逐句核對模型是否把家族史或年齡條件用對。另一次配對實驗中，直接附國健署服務表後，6 個版本有 4 個選到編者擬答，缺少有效選項的兩個版本仍都選錯。若要擴大測量模型詳解與引文，可使用 MedAESQA 索引定位原研究的 5,162 句回答。[醫師試審入口](reports/tw-fit-date-probe/review-guide.md) · [附原文的逐題結果](reports/tw-fit-date-probe/grounding.md) · [MedAESQA 資料與計數方法](datasets/discovery/medaesqa/README.md)

開放式材料已收錄麻醉專科口試病例與核醫臨床評量表的來源。原創雙語病例可檢查模型能否指出缺少哪項檢驗，並在檢驗值補齊後重新判讀。[學會附件與評量面向](datasets/tw-societies/sources/clinical-assessments.tsv) · [雙語開放題審題單](docs/review/tw-mets-missing-triglycerides.md)

本庫也收錄文獻查核、臨床對話、報告判讀與醫療代理任務。來源先登錄作者、任務與可用範圍；可改編的材料再整理為可追溯的草稿。醫師逐一審查答案、用語與證據，定版後可按用途匯出訓練案例、開發案例及獨立評測。[多來源目錄](datasets/discovery/README.md) · [複審與資料匯出](docs/editorial-workflow.md#審查紀錄與資料匯出)

臺灣考選部歷年試卷已分批建檔。2026-11-26 暫停收集，已發布的試卷、這台工作機額外收到的原件，以及恢復時第一個步驟都記在交接頁。[暫停與續作紀錄](datasets/moex/RESUME.md) · [年度覆蓋、官方原檔與更正答案](datasets/moex/README.md)

`medbench` 提供可重現的醫學問答評測流程，適用於任何 OpenAI 相容（`/v1/chat/completions` 串流）的本地 LLM 伺服器（llama.cpp、Strata、vLLM…）。安裝後可用 `medbench datasets` 列出目前能執行的題庫。

- **固定資料**：14 個題庫。8 個公開學術題庫（英文、繁體／簡體中文）從 Hugging Face 固定 revision 下載並比對 SHA-256；另有自建的台灣醫事人員國考繁體中文題庫 **twmed**（2024–2026，32,528 題，依職類分 6 組，見 [datasets/twmed](datasets/twmed/README.md)）。題庫組：`@core`（原本 3 個，3,686 題）、`@academic`、`@zh-tw`、`@all`。
- **同一協定**：零樣本、單一 user 訊息、思考開啟、逐題固定 seed、只評分最終回答（提示詞 v1.1；原 3 個題庫的提示詞與 v1 逐字相同）。
- **可續跑**：每題完成就寫入 `predictions.jsonl`；中斷後重跑同一指令會跳過已完成題、重試失敗題。
- **完整紀錄**：設定、程式 git 版本、伺服器 `/props`、資料雜湊、主機資訊、執行時段寫進 `manifest.json`；完整思考與回答在 `raw.jsonl`。
- **統計**：Wilson 95% CI、McNemar 精確檢定、配對 bootstrap 差異 CI、子集分析、PubMedQA macro-F1。
- **速度與資源**：TTFT、延遲、單請求解碼速度、總吞吐；每秒取樣 VRAM／GPU 使用率／功耗／溫度、伺服器 RSS、系統 RAM、CPU，計算能耗（Wh/題，含扣除閒置功耗），並記錄共用伺服器上其他使用者的請求。
- **報告**：`medbench report` 產生正式 Markdown 報告（方法、結果、配對比較、速度、資源、重現步驟）。

最新報告：[reports/REPORT.docx](reports/REPORT.docx)（Word，給技術人員分享：含測試環境、模型檔案雜湊、參考基準、圖表）、[reports/REPORT.md](reports/REPORT.md)（Markdown）、數據 [reports/REPORT.json](reports/REPORT.json)、環境紀錄 [reports/environment.json](reports/environment.json)

## 2026-11-23：Bonsai 27B vs Inkling 2 Mini

報告：[reports/inkling2mini/REPORT.docx](reports/inkling2mini/REPORT.docx)（Word）、[REPORT.md](reports/inkling2mini/REPORT.md)、討論與部署
[notes.md](reports/inkling2mini/notes.md)、環境 [environment.json](reports/inkling2mini/environment.json)。Inkling 每個題庫抽 400 題（`--sample 400`），
比較只用兩邊都作答的 1,228 題（`medbench report` / `docx` 會自動限縮並註明）。

| | Bonsai 27B PQ2_0 | Inkling 2 Mini UD-IQ4_XS |
|---|---:|---:|
| 醫學題（1,228 題） | 78.1% | **86.6%**（+8.6，p < 0.001） |
| MedQA-TWMLE（繁中，400 題） | 79.2% | **94.5%** |
| 第一次選對工具（[results/toolbench](results/toolbench/README.md)） | **98.1%**（held-out 52 題） | 92.3%（Q3_K_XL 合併 162 題 87.7% vs 93.8%，p = 0.002） |
| 回答含簡體字（TWMLE 400 題） | 22.2% | **0.2%** |
| 單請求生成 / prefill（同條件掃描） | **146 / 2,764 tok/s** | 81 / 2,375（65k 全 GPU）；部署的 131k（3 層專家在 CPU）56 / 393 |

量測腳本：`scripts/gpu_window.sh` + `scripts/jobs/inkling2mini*.sh`（維護時段）、`slot_sweep.py`、`stress_long.py`、`slot_table.py`、
`prefix_cache.py`、`zh_quality.py --common`、`toolbench_compare.py`；結果在 `results/slots/`、`results/toolbench/`。

**Agent 模式加速（2026-11-24）**：[reports/inkling2mini/AGENT-SPEED.md](reports/inkling2mini/AGENT-SPEED.md)。

- 同一個最高思考等級的文獻任務，從 1,278 s 仍未完成，變成 285 s 完成。
- 改動：
  - 引擎 b12651、全 GPU、2 slot 各自 131k；
  - llama-mcp-router v0.13／v0.14（`stable_prefix` 讓新 session 只重算幾百 tokens）；
  - 決策模型移到 CPU。
- 錄製與重播：`agent_capture_proxy.py`、`agent_replay.py`、`stable_prefix_check.py`、`scripts/jobs/inkling2mini-agent-speed{,2,3}.sh`；結果在 `results/speed/`。

## 結果摘要（2026-10-21，RTX 4090 KVM 虛擬機）

零樣本、思考 effort medium、相同取樣參數與逐題 seed，3,686 題全部作答：

| | Bonsai 27B PQ2_0（llama.cpp，正式服務） | Strata Qwen3.8-Flash-Next 125B IQ3_S |
|---|---:|---:|
| MedQA-USMLE（1,273） | 84.8% [82.7–86.6] | **94.3%** [92.9–95.4] |
| MedQA-TWMLE 繁中（1,413） | 77.5% [75.2–79.6] | **89.8%** [88.1–91.3] |
| PubMedQA-L（1,000） | 71.3% [68.4–74.0] | **77.5%** [74.8–80.0] |
| **整體（3,686）** | 78.3% [77.0–79.6] | **88.0%** [86.9–89.0] |
| 配對差（McNemar） | | +9.7 個百分點 [8.5–10.9]，p < 0.001 |
| 無答案 / 截斷 | 5 / 4（重複迴圈） | 0 / 0 |
| 單請求解碼中位 | 81.8 tok/s（3 併發） | 87.6 tok/s（1 併發） |
| 平均輸出 tokens / 題 | 1,408 | 937 |
| 每題中位延遲 | 13.7 s | 10.6 s |
| 吞吐 | **606 題/小時**（6.1 h） | 308 題/小時（12.0 h） |
| VRAM（整張卡，含 Clef 6.5 GiB） | 20.7 GiB | 23.4 GiB |
| 伺服器 RSS / CPU | 25.6 GiB（多為提示快取）/ 12% | 43 GiB / 96% |
| GPU 能耗 / 題、/ 答對一題 | 0.56 / 0.72 Wh | 0.67 / 0.76 Wh |

中括號為 95% Wilson CI。Strata 正確率較高、沒有退化輸出、每題想得較短；代價是需要整台機器（必須暫停 Bonsai）、總吞吐只有一半。詳見報告第 5–7 節（設定細節、討論、限制）。

## 資料集

`medbench datasets` 列出全部題庫與題庫組。`--datasets` 可混用名稱與 `@組名`，例如 `--datasets @core,twmed_md`。

| 名稱 | 內容 | 題數 | 來源（固定 revision） | 授權 |
|---|---|---:|---|---|
| **@core** | | **3,686** | | |
| `medqa_usmle` | MedQA 美國醫師執照考試，英文，4 選 1（Step 1：679；Step 2&3：594） | 1,273 | `bigbio/med_qa@484a6c0` `med_qa_en_4options_source/test` | MedQA repo 標示 MIT，BigBio 資料卡標示 unknown |
| `medqa_twmle` | MedQA 台灣醫師國考，繁體中文，4 選 1（24 題為「承上題」） | 1,413 | `bigbio/med_qa@484a6c0` `med_qa_tw_source/test` | MedQA repo 標示 MIT，BigBio 資料卡標示 unknown |
| `pubmedqa` | PubMedQA-L 專家標註，英文摘要閱讀，yes/no/maybe（552/338/110） | 1,000 | `qiaojin/PubMedQA@9001f28` `pqa_labeled` | MIT |
| **@academic**（= @core 加上下列） | | **14,834** | | |
| `medmcqa` | MedMCQA validation，印度 AIIMS／NEET-PG 入學考，英文，4 選 1（另報 single／multi 子集） | 4,183 | `openlifescienceai/medmcqa@91c6572` | Apache-2.0 |
| `mmlu_med` | MMLU 醫學 6 科 test：解剖、臨床知識、大學生物、大學醫學、醫學遺傳、專業醫學（各科子集） | 1,089 | `cais/mmlu@c30699e`（6 檔） | MIT |
| `medxpertqa` | MedXpertQA Text test，專家級醫學推理，英文，**10 選 1**（Reasoning／Understanding、診斷／治療／基礎科學子集） | 2,450 | `TsinghuaC3I/MedXpertQA@7e7c465` `Text/test.jsonl` | MIT |
| `medqa_mcmle` | MedQA 中國大陸醫師資格考，**簡體中文**，4 選 1 | 3,426 | `bigbio/med_qa@484a6c0` `med_qa_zh_4options_source/test` | MedQA repo 標示 MIT，BigBio 資料卡標示 unknown |
| **@zh-tw**（繁體中文） | | **38,092** | | |
| `medqa_twmle` | 同上 | 1,413 | | |
| `tmmlu_med` | TMMLU+ 醫學 8 科 test：基礎醫學、藥理、藥學、臨床心理、牙醫、中醫臨床、驗光、職能治療（各科子集） | 4,151 | `ikala/tmmluplus@639a64d`（8 檔） | MIT |
| `twmed_md` | **自建**：考選部專技高考 2024–2026 醫師（一）（二） | 2,872 | [datasets/twmed](datasets/twmed/README.md) | 不受著作權保護（著作權法 §9 I ⑤） |
| `twmed_dent` | 自建：牙醫師（一）（二） | 2,645 | 同上 | 同上 |
| `twmed_tcm` | 自建：中醫師（一）（二） | 2,821 | 同上 | 同上 |
| `twmed_rx` | 自建：藥師（一）（二） | 2,518 | 同上 | 同上 |
| `twmed_rn` | 自建：護理師、助產師 | 3,072 | 同上 | 同上 |
| `twmed_allied` | 自建：醫檢、放射、物理／職能／呼吸／語言治療、營養、心理、聽力、驗光、牙體技術、公衛、法醫 | 18,600 | 同上 | 同上 |

- 三個 MedQA 子集下載自同一個 BigBio 版本。題目再散布與翻譯的授權範圍仍待確認。[MedQA 原始儲存庫](https://github.com/jind11/MedQA) · [BigBio 資料卡（固定版本）](https://huggingface.co/datasets/bigbio/med_qa/blob/484a6c066fe8e75c83edea0c88b5169316714fcd/README.md)
- `@all` 是全部 14 個題庫（51,513 題，`medqa_twmle` 只算一次）。twmed 各組都另報年份與職類子集。
  2026 年的題目在多數模型的訓練截止日之後，可以和 2024 年的題目比較，作為資料汙染的參考。
- 現行文字評測流程排除了 HEAD-QA（當時僅找到自動轉換分支，且含圖片題）及 MMLU-Pro health（改編自 MMLU 醫學題，和 `mmlu_med` 重複）。
- twmed 的建置：`medbench twmed-build`（需要 `[build]` extra 的 PyMuPDF，會連考選部，每秒最多 1 個請求）。
  篩選規則、排除統計、法律依據與引用方式見 [datasets/twmed/README.md](datasets/twmed/README.md)。
  題庫檔在 repo 內，所以 `twmed_*` 要在 repo checkout（或 editable 安裝）中使用。

**新題庫試跑（2026-11-23，驗證流程用）**：正式服務上的 Inkling 2 Mini UD-IQ4_XS，每個新題庫平均間隔抽 20 題（`--sample 20`，2 個併發）。
220 題全部有可解析答案：0 題無答案、0 題截斷、0 個錯誤，包括 10 選 1、簡體與繁體作答。每庫只有 20 題，95% CI 很寬，**不代表模型的真實水準**。
結果在 `results/inkling2mini-iq4xs-prod-medium/`，日後用同一設定、不加 `--sample` 即可接著跑完整題庫。

| 題庫 | 正確 | | 題庫 | 正確 |
|---|---:|---|---|---:|
| medmcqa | 11/20 | | twmed_md | 19/20 |
| mmlu_med | 18/20 | | twmed_dent | 19/20 |
| medxpertqa（10 選 1） | 4/20 | | twmed_tcm | 13/20 |
| medqa_mcmle（簡中） | 15/20 | | twmed_rx | 19/20 |
| tmmlu_med | 15/20 | | twmed_rn | 17/20 |
| | | | twmed_allied | 13/20 |

引用：
- Jin et al., *What Disease does this Patient Have?*（MedQA），Applied Sciences 2021。
- Jin et al., *PubMedQA*，EMNLP 2019。
- Pal et al., *MedMCQA*，CHIL 2022。
- Hendrycks et al., *MMLU*，ICLR 2021。
- Zuo et al., *MedXpertQA*，ICML 2025。
- Tam et al., *TMMLU+*，2024。
- 考選部考畢試題查詢平臺。

## 安裝與使用

```bash
git clone https://github.com/u9401066/medical-benchmark-collection
cd medical-benchmark-collection
uv venv
source .venv/bin/activate   # Windows PowerShell 請用 .\.venv\Scripts\Activate.ps1
uv pip install -e '.[test,report]'   # report 包含產生 Word 報告需要的 python-docx、matplotlib
pytest -q

medbench datasets                                                   # 列出題庫與題庫組
medbench prepare                                                    # 下載、驗證、正規化到 data/（預設 @core；--datasets @all 全部）
medbench run --config configs/inkling2mini-iq4xs-prod-medium.json --datasets @academic,@zh-tw --sample 20   # 新題庫試跑
medbench run --config configs/bonsai27b-pq2-medium.json --sample 10 --out results/pilot-bonsai   # 先試跑
medbench run --config configs/bonsai27b-pq2-medium.json             # 全部 3,686 題，可中斷續跑
medbench score results/bonsai27b-pq2-medium results/strata-flashnext-iq3s-medium
medbench report results/bonsai27b-pq2-medium results/strata-flashnext-iq3s-medium --notes reports/notes.md
medbench env                                                       # 記錄主機環境到 reports/environment.json
medbench docx results/bonsai27b-pq2-medium results/strata-flashnext-iq3s-medium --notes reports/notes.md   # Word 報告
```

### 設定檔（`configs/*.json`）

| 欄位 | 說明 |
|---|---|
| `name` / `label` | 結果資料夾名稱 / 報告中的名稱 |
| `base_url`、`model`、`headers` | OpenAI 相容伺服器 |
| `concurrency` | 同時送出的請求數 |
| `request` | 併入每個請求的參數（`max_tokens`、取樣參數、`reasoning_effort` 或 `chat_template_kwargs`） |
| `server_info` | 執行前讀取並存進 manifest 的端點（例如 `/props`） |
| `processes` | 用來計算 RSS 的伺服器行程命令列片段 |
| `slots_path` | 伺服器忙碌槽位端點（預設 `/slots`；設為 `null` 停用） |
| `system` | 報告用的模型／量化／引擎描述 |

### 輸出（`results/<name>/`）

| 檔案 | 內容 |
|---|---|
| `manifest.json` | 設定、medbench 版本與 git commit、prompt 版本、資料雜湊、主機、伺服器資訊、每段執行的時間 |
| `predictions.jsonl` | 每題：答案、對錯、TTFT、延遲、tokens、解碼速度、finish reason、伺服器 timings |
| `raw.jsonl(.gz)` | 每題完整思考與回答 |
| `resources.csv` | 每秒：VRAM、GPU 使用率／功耗／溫度、系統 RAM、伺服器 RSS、CPU、我方進行中請求、伺服器忙碌槽位 |
| `summary.json` | `medbench score` 的結果 |

## 作答與評分協定

- 提示詞見 [medbench/prompts.py](medbench/prompts.py)（`PROMPT_VERSION = "v1.1"`），四種範本（英文 MCQ、繁中 MCQ、簡中 MCQ、PubMedQA），都要求最後一行 `Answer: X`；選項可到 A–J。v1.1 只新增簡中範本與 D 以後的選項，原 3 個題庫的提示詞與 v1 逐字相同（測試鎖定）。
- 只解析最終回答（`content`）的最後一個 `Answer: X`／`答案：X`；思考內容不評分。解析不到 = 答錯，另計「無答案」。
- 逐題 seed = SHA-256(題目 ID) 前 31 bits；同一題在每個系統用同一 seed。
- `finish_reason=length`（截斷）仍解析並另外計數；請求錯誤重試 2 次，續跑時再重試。

## 一次佔滿 GPU 的模型：維護時段腳本

[scripts/strata_window.sh](scripts/strata_window.sh) 會暫停正式服務、啟動受測伺服器、跑 medbench，**無論成功、失敗或被中斷都會停掉受測伺服器並恢復正式服務**：

```bash
PARALLEL=1 STRATA_CONFIG=configs/engine/strata-iq3_s-32k.json scripts/strata_window.sh configs/strata-flashnext-iq3s-medium.json
```

## 限制

- 公開題庫多年前就已釋出，可能出現在模型訓練資料中（資料汙染），分數宜視為相對比較而非絕對能力；twmed 的 2026 年子集較新，可作為對照。
- twmed 只收純文字題（有圖、表格、公式的題目已排除），所以偏向記憶與文字推理，不代表國考的完整難度分佈。
- 單次取樣（非多次平均）；溫度 1.0 下單題結果有隨機性，配對檢定已反映此不確定性。
- 共用伺服器上的速度會受其他使用者影響；`resources.csv` 的 `server_busy` 與 `inflight` 可量化此影響。
- 零樣本、無外部工具（無檢索、無 MCP），測的是模型本身的醫學知識與推理。
