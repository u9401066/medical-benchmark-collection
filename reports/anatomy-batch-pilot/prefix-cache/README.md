# 獨立題目共用固定前綴的快取實測

以同一部 CPU 工作機、Qwen2.5 1.5B Q4_K_M 和 llama.cpp b12776 作答。四個英文解剖學目標題各跑短前綴、長前綴的冷與暖條件，共 16 次計時的目標請求。每次目標前另送一次相同前綴的校準題，共 32 次推論。題幹、選項及校準題各自在自己的請求。前綴命中只會省下相同 token 序列的輸入計算。[原始請求結果與 token 指紋](results.json) · [llama.cpp 固定版伺服器說明](https://github.com/ggml-org/llama.cpp/blob/e38ea719b/tools/server/README.md)

## 計時結果

每列為四個目標請求的中位數。prefill 時間指伺服器處理輸入的時間，端到端時間為本機用戶端送出請求到讀取完整回覆。兩個時間欄均以毫秒表示。輸出固定為簡短的 JSON 選項，16 次目標都生成 7 個 tokens。

| 共同前綴 | 快取條件 | 重用 tokens | 重新處理 tokens | Prefill（ms） | 生成（ms） | 端到端（ms） |
|---|---|---:|---:|---:|---:|---:|
| 短 | 冷 | 0 | 122.5 | 1,018.2 | 396.3 | 1,433.6 |
| 短 | 暖 | 41 | 81.5 | 570.2 | 362.5 | 941.7 |
| 長 | 冷 | 0 | 368.5 | 2,482.6 | 392.5 | 2,864.6 |
| 長 | 暖 | 287 | 81.5 | 659.7 | 394.7 | 1,040.5 |

按同一目標題配對後，暖快取的端到端時間比冷條件少 347.7 ms（短）與 1,824.1 ms（長），兩者都是逐題差值的中位數。暖條件的前置校準題本身分別花費中位數 944.6 與 2,750.4 ms。若實際上要為每題另外做一次同樣的預熱，暖條件兩次請求合計的逐題中位數為 1,918.6 與 3,791.0 ms。可否縮短整批時間取決於有幾道題能重用同一前綴、請求排程和快取保留時間。上述合計只包含兩次請求時間。[16 組逐筆計時](results.json)

## 實驗控制與重跑

短與長前綴由相同系統提示和 8 或 192 個可重建的中性單詞組成。程式以固定後端的 `/apply-template` 與 `/tokenize` 產生輸入，再將確切 token ID 送入 `/completion`。同一目標在冷暖條件使用相同 token 陣列。單一 slot，每組先清除 slot 再跑校準題，冷條件在目標題前另清一次，暖條件保留。測量時停用跨 slot 共用的 RAM 提示快取。16 次校準和 8 次冷目標皆命中 0 個 tokens，8 次暖目標均命中實際共同序列的完整長度。每輪四個目標與四種條件各出現一次。各目標輪過四個次序位置，各條件在其中兩個位置交替。伺服器使用 4 個 CPU 執行緒、4,096 context、GPU offload 0、temperature 0 及固定 seed。結果適用於這個模型、後端、快取設定及短輸出。準確率、長文生成、多 slot 競爭與 GPU 效能需各自實測。[執行程式](run.py) · [既有解剖學題本與硬體](../README.md#環境與資料)

從作者的 anatomy test CSV 重建題本後即可離線得到同一組計數和中位數。`--verify-tokens` 可再啟動私有 loopback 伺服器，核對完整輸入的模板及 token 指紋。`--run` 啟動新推論，產生實測時間會變動的新結果檔。

```sh
python scripts/prepare_mmlu_anatomy.py anatomy_test.csv --split test --out data/anatomy-test.jsonl
python reports/anatomy-batch-pilot/prefix-cache/run.py --items data/anatomy-test.jsonl --verify reports/anatomy-batch-pilot/prefix-cache/results.json
python reports/anatomy-batch-pilot/prefix-cache/run.py --items data/anatomy-test.jsonl --verify reports/anatomy-batch-pilot/prefix-cache/results.json --verify-tokens --server path/to/llama-server --model path/to/model.gguf
python reports/anatomy-batch-pilot/prefix-cache/run.py --items data/anatomy-test.jsonl --run data/anatomy-prefix-rerun.json --server path/to/llama-server --model path/to/model.gguf
```
