# 臺灣公費大腸癌篩檢回答理由審閱說明

這份公開開發練習請醫師核對模型對臺灣公費篩檢政策的陳述。共有 12 份回答，繁中、英文各 6 份，全部針對 2026-11-26 的政策。相同題目的兩次回答分開編號。發行時完成的醫師審閱為 **0/12**，題目及編者參考主張也仍待核准。[開啟逐題審閱本](review-worksheet.md) · [空白結構化審閱表](review-worksheet.jsonl)

## 醫師如何填寫

1. 請在空白結構化審閱表的副本工作。依隨機代號逐份閱讀題目、選項、作答規則與完整回答。先讀理由，再對照編者主張及其官方來源定位。原回答即使缺少指定欄位，仍可就其臨床陳述與引用提出意見。
2. 在 `reference_claims` 內按編號判斷回答是否提及該主張。內容有證據支持填 `supported`，與證據牴觸填 `contradicted`，現有資料無法核實填 `unverified`。完全未提及填 `omitted`，保留空的 `span`、`evidence_ids`，並以 `note` 說明。
3. 對實際出現的陳述填入原文 `span` 與判斷理由。判為支持或牴觸時，請在 `evidence_ids` 列出依據，並在 `source_locators` 以各證據 ID 為鍵填入實際使用的表列或段落。編者清單以外的實質陳述列入 `additional_claims`。若回答自行引用來源，列入 `citations` 並記錄查核網址、位置及結果。查找未果可標 `unresolved`。標記 `confirmed_fabricated` 需在 `verification_basis` 填 `affirmative_primary_confirmation`，並在 `confirmation_excerpt` 記下一手來源能明確證實的短摘錄。新增證據供本題核對時，請附來源網址、版本、定位及適用日期。
4. 全份檢視完才由實際審閱者填寫 `reviewer`、`date`，設 `inventory_complete` 為 `true`、`state` 為 `complete`。可在 `minutes` 記錄實際花費的分鐘數。若質疑題幹、編者主張或來源適用性，請留下原句、疑義及替代依據，交給協調者修訂草稿。

### 練習定位

偏移量以解碼後的 `context.response` 為準，從 0 起算 Unicode 字元，包含原回答的空格及換行。`start` 包含首字元、`end` 指向末字元之後，必須滿足 `response[start:end] == quote`。請以完整回答字串計算；擷取單獨的 `reason`、重排 JSON 或直接在 JSONL 檔案上量位移，都會改變位置。

| 代號 | start | end | quote |
|---|---:|---:|---|
| R-17163 | 80 | 106 | 最早40歲可接受每兩年一次的定量免疫法糞便潛血檢查。 |
| R-77546 | 301 | 353 | it does not specify the minimum age for FIT testing. |

上表只示範如何定位，沒有代填判讀結果或醫師欄位。

## 協調者交付與核對

交付時可提供本說明、逐題審閱本與空白 JSONL。解碼檔由協調者另行保管。兩種作答條件已混排，審閱本省略模型與協議名稱。原始報告與解碼檔在專案中公開，回答的欄位風格也可能透露條件，因此這只是遮蔽識別資訊的審閱練習。醫師回傳的結果可協助修訂題目與審閱方式；正式臨床評分仍須依核准且凍結的題本另行分派。[協調者解碼檔](review-key.jsonl) · [審查與核准流程](../../docs/editorial-workflow.md)

解碼檔的 `response_index` 以 0 起算，可定位原始報告中的 `responses` 陣列；`response_sha256` 可核對完整回答的 UTF-8 雜湊。與填寫版分開保存的公開空白包可在專案根目錄執行下列命令驗證或重建。

```sh
python reports/tw-fit-date-probe/prepare_review.py --check
python reports/tw-fit-date-probe/prepare_review.py --out-dir data/fit-review-blank
```
