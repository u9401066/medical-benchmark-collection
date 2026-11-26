# 解剖學題的批次作答先導實驗

在同一部工作機以 Qwen2.5 1.5B 比較五種作答條件。效能指標是整份固定題單所花的時間，以及每小時能產生多少個符合格式且答對來源題庫的答案。另保留逐題答案，觀察總分相同時是否仍有題目改答。本研究使用 MMLU 作者的解剖學題庫答案。臨床醫師審定的時效評測另行建置。[MMLU 作者及資料](https://github.com/hendrycks/test)

## 實測結果

每列都分配 12 題。「有效」指回傳可辨識的選項字母，「答對」依作者答案計分。「翻轉」是相對單題基準改選的題數，分母只含兩種條件均有有效答案的配對。秒數是整批實測耗時。

| 解剖學 split | 作答方式 | 有效 | 答對 | 秒 | 翻轉 |
|---|---|---:|---:|---:|---:|
| Validation | 單題依序 | 12 | 8 | 25.58 | 基準 |
| Validation | 單題依序重跑 | 11 | 7 | 29.42 | 0/11 |
| Validation | 獨立請求併發 2 | 11 | 7 | 20.96 | 0/11 |
| Validation | 同提示 2 題 | 10 | 6 | 28.49 | 0/10 |
| Validation | 同提示 2 題，輪替鄰題與位置 | 12 | 8 | 22.56 | 2/12 |
| Test | 單題依序 | 12 | 9 | 38.96 | 基準 |
| Test | 單題依序重跑 | 12 | 8 | 33.05 | 1/12 |
| Test | 獨立請求併發 2 | 12 | 8 | 25.58 | 1/12 |
| Test | 同提示 2 題 | 12 | 9 | 30.21 | 2/12 |
| Test | 同提示 2 題，輪替鄰題與位置 | 12 | 8 | 30.50 | 2/12 |

獨立請求併發 2 在兩批均最快。Test 的符合格式且答對題數折合每小時由 832 增至 1,126 題，但該批 12 題由答對 9 題降為 8 題。單題重跑也在同一題改答。Test 雙題共用提示仍答對 9 題，其中一題由對改錯、另一題由錯改對。Validation 輪替鄰題與位置後，有兩題改選另一個錯誤選項，總分同樣看不出來。[Validation 逐請求結果](validation-results.json) · [Test 逐請求結果](test-results.json)

Validation 有 4 筆格式不符的回覆，涉及 2 個題號。這些回覆給了正確字母並附上對應的完整選項文字。雙題共用提示有 2 筆，單題重跑及獨立併發各 1 筆。事後若只額外接受這種精確格式，Validation 五種條件都會答對 8/12。Test 沒有這類回覆。上表保留原訂的純字母判分。[Validation 原始回覆](validation-responses.json) · [Test 原始回覆](test-responses.json)

## 測量方法

- 兩次分別從作者的 anatomy validation 14 題、test 135 題隨機抽 12 題，各跑五種條件。選項順序保留原樣，提示只含題號、題幹與選項。每一條件的 12 題都進入分母。使用同一組英文 JSON 輸出規則，要求每個 ID 回一個原選項的字母。
- 五種條件為單題依序、單題依序重跑、獨立請求併發 2、每個提示放 2 題，以及換同批題目並輪替位置後再跑每提示 2 題。每個 split 內用固定 seed `20261126` 抽題及打亂條件順序。兩種共用提示均一次只送一個請求，輪替組會讓每題換一位同伴並互換首末位置。
- 每個 split 啟動獨立伺服器，先用一道不相關的數字題暖機，暖機不計時。每題輸出上限 64 tokens，雙題共用 128。取樣使用 temperature 0、相同 seed 與 JSON object 模式。模型用同一程序連續跑完該 split 的五種條件，保留後端預設的提示快取行為。每條件以牆鐘計整批耗時，包含用戶端請求與回覆解析；p95 是請求延遲，雙題時一個請求涵蓋兩題。
- 只有兩個條件都取得有效標籤的題目才能算翻轉率。任何兩個不同的有效選項都算翻轉，包括兩次都錯。缺答、重複 ID 和未提供的選項都保留在主分母。保留原回覆與逐請求指紋以供重新判讀。單題重跑可衡量相同提示自身的變動幅度。

## 環境與資料

2026-11-26 於 Windows 工作機使用 Intel Core i9-13980HX。llama.cpp 為官方 b12776 Windows x64 CPU 發行，commit `e38ea719b`，ZIP SHA-256 為 `bba23437a597b7b346acb87dbac2e5452c7b188cec67ca6315bec513a067ace8`。本機 Qwen2.5 1.5B 的 GGUF 量化為 Q4_K_M，檔案 986,048,512 bytes，SHA-256 為 `183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4`。使用 4 條 CPU 執行緒、2 個伺服器 slot、總 context 4,096、GPU offload 0 層。[llama.cpp 官方發行](https://github.com/ggml-org/llama.cpp/releases/tag/b12776)

來源為作者 TAR 的 `data/val/anatomy_val.csv`（2,784 bytes）及 `data/test/anatomy_test.csv`（29,844 bytes）。準備程式逐一驗證成員的 SHA-256、列數和選項，按該 split 的原始列序編 ID。此次 HF 固定版本 parquet 的連線中斷，實驗結果只對應這兩個作者 CSV。[作者原始資料包](https://people.eecs.berkeley.edu/~hendrycks/data.tar) · [來源檔校驗與正規化](../../scripts/prepare_mmlu_anatomy.py)

## 重跑

下載作者資料包，或提供已取出的同版 CSV。使用相同 GGUF 在本機執行以下指令。要重現第二個 split，重新啟動伺服器並將資料準備指令的 `--split` 改為 `test`，輸出至不同目錄。

```sh
llama-server -m model.gguf --alias qwen2.5-1.5b-local --host 127.0.0.1 --port 18137 --ctx-size 4096 --parallel 2 --threads 4 --threads-batch 4 --n-gpu-layers 0 --no-webui
```

```sh
python scripts/prepare_mmlu_anatomy.py data.tar --split val --out data/anatomy-val.jsonl
python -m medbench.batch_probe --items data/anatomy-val.jsonl --subject anatomy --url http://127.0.0.1:18137 --model qwen2.5-1.5b-local --sample 12 --pack-size 2 --concurrency 2 --seed 20261126 --tokens-per-item 64 --out data/val-report.json --raw data/val-responses.json
```

要核對已公開的數字，使用同版來源執行下列步驟即可。離線驗證器會重建題序、核對題本和回覆的雜湊、重算判分及翻轉，再列出上述事後格式分析。牆鐘時間及 token 數來自原始測量紀錄。

```sh
python scripts/verify_batch_probe.py --items data/anatomy-val.jsonl --report reports/anatomy-batch-pilot/validation-results.json --raw reports/anatomy-batch-pilot/validation-responses.json
python scripts/prepare_mmlu_anatomy.py data.tar --split test --out data/anatomy-test.jsonl
python scripts/verify_batch_probe.py --items data/anatomy-test.jsonl --report reports/anatomy-batch-pilot/test-results.json --raw reports/anatomy-batch-pilot/test-responses.json
```

單一模型、單一英文科目及每個條件的一次計時，只能呈現這些題目在這部機器的觀察值。發現翻轉時，鄰題內容、題位、同一回覆中前題的輸出與後端數值行為皆可能有影響。下次應固定鄰題後只換順序、固定位置後只換鄰題，另輪替條件順序並重複計時，再估計可接受的準確率差。這次未量測功耗、成本金額或 GPU 吞吐。[批次實驗規劃](../../docs/roadmap.md#批次作答的速度與題間干擾)
