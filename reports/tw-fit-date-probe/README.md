# 臺灣公費大腸癌篩檢的成對日期作答

這批保留模型對同一政策新舊問法的實際回覆，供醫師核對題目與閱卷方式。三道草稿屬同一病例家族，每題有臺灣繁中與美式英文版本，適用地區都是臺灣。每個語言版本各問 2024-12-31 和 2026-11-26，合計 12 個獨立請求。六個版本均待醫師審定，屬公開開發材料。[原題與編者擬答](../../docs/review/tw-fit-controls.md)

## 如何閱讀這一批

0001 與 0002 都問一般族群公費篩檢的最低年齡。依編者核對的國健署資料，舊制可選 B（50 歲）。新制起始年齡為 45 歲，0001 未提供此選項，0002 則有 C（45 歲）。0003 改問 60 歲民眾的例行間隔，歷史與現行問法均有 D（每兩年）。這個對照可用來辨識只因看見新日期就任意改答的情況。[國健署歷史說明](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770) · [現行服務表](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)

## 第一輪的原始作答

在第一輪，模型能自由產生 JSON 物件。12 份回覆都完整結束，只有 6 份具備規定的 `choice` 與非空白的 `reason`，全部來自繁中題。兩道起始年齡題的新舊問法都選 A（40 歲），間隔題的新舊問法都選 B（三年）。國健署現行一般資格從 45 歲開始，例行間隔為兩年。英文六份分別使用 `option`、`one_option` 或 `answer` 等欄名，部分同時選了代號又稱資料不足。這些原文可交醫師核對，未依格式解析的作答保留在分母。[第一輪原始回覆](responses.json) · [國健署服務表](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)

依編者擬答，兩道起始年齡題的四個現行語言版本都有已失效的舊選項 B。這一輪四份回覆中，按規定欄位明確選 B 的有 0 份，其中兩份是格式未通過的英文回答。兩份可解析的繁中回答都選了另一個錯誤年齡。僅看舊選項沿用次數會漏掉這兩類問題。正式臨床指標仍待醫師審定題本。

## 只改輸出格式的對照

第二輪在相同的模型與硬體重新啟動伺服器，使用 llama.cpp 支援的 JSON Schema 限制欄位。每筆請求的題號、語言、日期、順序、提示 SHA-256 與後端回報的輸入 token 數都與第一輪一致。兩輪都依相同規則解析 `choice` 與非空白的 `reason`，也都允許指出無有效選項、資訊不足或棄答。每個條件各分派 12 題。[後端協議](https://github.com/ggml-org/llama.cpp/blob/b12776/tools/server/README.md#post-v1chatcompletions-openai-compatible-chat-completions-api) · [第二輪原始回覆](responses-constrained.json)

| 實測項目 | JSON 物件 | 指定 JSON Schema |
|---|---:|---:|
| 繁中可解析 | 6/6 | 6/6 |
| 美式英文可解析 | 0/6 | 6/6 |
| 全體能解析且與該日期的編者擬答一致 | 0/12 | 0/12 |
| 現行問題中明確選到已失效的舊選項 | 0/4（2 份無法解析） | 1/4（全部可解析） |

以 0002 英文版為例，指定格式後，模型對 2024 年問法選 C（45 歲），對 2026 年問法選 B（50 歲），與政策變更的方向相反。0003 在兩種語言、兩個日期都選了 B（三年），漏掉仍有效的兩年間隔。這個對照顯示格式限制能讓這批英文選擇送審，仍須核對日期、答案與理由。JSON 物件模式下無法唯一判讀的回答繼續標為解析失敗。兩輪的選項一致數僅對照公開開發草稿，尚無經醫師裁決的臨床成績或微調效果。

## 模型與提示

使用同機既有 Qwen2.5 1.5B Q4_K_M、llama.cpp b12776、4 條 CPU 執行緒、1 個 slot、總 context 4096，GPU offload 0 層。模型與發行檔指紋列在同機的解剖學先導報告。12 次請求用 seed `20261126` 打亂順序，各自開新對話。伺服器接收題幹、選項及該語言的 JSON 作答規則。模型可回一個選項、無有效選項、資訊不足或棄答，並簡述理由。全程閉卷，temperature 0，每次輸出上限 256 tokens。[模型與後端指紋](../anatomy-batch-pilot/README.md#環境與資料) · [完整提示建構與執行程式](run.py)

從本報告所屬的 Git 版本，在專案根目錄執行下列前兩行，可離線重建分派與提示、比對草稿及逐筆回覆指紋、解析各回覆的選擇。要重新推論，在一個終端機啟動伺服器，另一個終端機執行對應的作答指令，每個條件開始前重新啟動伺服器。每個條件只跑一次，一個病例家族無法估計模型在其他醫療政策或其他科別的表現。

```sh
python reports/tw-fit-date-probe/run.py --verify reports/tw-fit-date-probe/responses.json
python reports/tw-fit-date-probe/run.py --constrain --verify reports/tw-fit-date-probe/responses-constrained.json
llama-server -m model.gguf --alias qwen2.5-1.5b-local --host 127.0.0.1 --port 18138 --ctx-size 4096 --parallel 1 --threads 4 --threads-batch 4 --n-gpu-layers 0 --no-webui
python reports/tw-fit-date-probe/run.py --run data/tw-fit-date-new.json
python reports/tw-fit-date-probe/run.py --constrain --run data/tw-fit-date-constrained-new.json
```
