# 安寧照護問答的參考依據、作答及風險附表

2026-11-26 核對 BMC Palliative Care 論文 PMID `43067661` 的五份 DOCX 附件。研究以 30 道面向高齡者代理決策者的問題，評估五個模型設定的正確性、安全性及可讀性。發布版本讓讀者能逐題核對研究如何定義可接受回答、使用哪些證據，以及挑出哪些風險例。出版頁列 CC BY-NC-ND 4.0。本庫記錄定位及重算結果，題目、答案與引文由原發布頁提供。[研究原文、授權及附表](https://doi.org/10.1186/s12904-026-02360-1)

| 出版附件編號 | 原件定位及用途 | SHA-256 |
|---|---|---|
| 1 | 內標 S2 的模型及提問設定表，1 表、18 個資料列。[原件](https://pmc-oa-opendata.s3.amazonaws.com/PMC13789279.1/12904_2026_2360_MOESM1_ESM.docx) | `1f98cbb5ed5ea1656c9c4576f679557d413d777618c4d29241829835f91525ae` |
| 2 | 第 1 表的第 2–31 列為編號題、預期回答與參考對照。第 2 表第 2–29 列為引用紀錄。[原件](https://pmc-oa-opendata.s3.amazonaws.com/PMC13789279.1/12904_2026_2360_MOESM2_ESM.docx) | `0c192b41dd7e28d7b9dc09a158faddfa7aca5c4686639ced0a8a873b98a33e73` |
| 3 | 內標 S1 的模型配對比較。第 1 表提供二元安全性配對統計。[原件](https://pmc-oa-opendata.s3.amazonaws.com/PMC13789279.1/12904_2026_2360_MOESM3_ESM.docx) | `0a8a28f06ece8dd8a6a392922f3009242f12767b15bc1a52c7a074b0ef281e51` |
| 4 | 內標 Supplementary Material 3 的質性分析。第 1 表定義風險面向，第 2 表列各模型摘錄數，第 3 表以題號及模型列風險例。[原件](https://pmc-oa-opendata.s3.amazonaws.com/PMC13789279.1/12904_2026_2360_MOESM4_ESM.docx) | `f242fa89fac57cc3083a5d68f7786b4a7b7dda114e3d1b5eb6a13f63ccf9f03c` |
| 5 | 第 1 表為總覽。第 2–151 表各為一個 `record_id`、`question_id` 及模型標籤，後接 `answer_text:` 段落及作答文字。[原件](https://pmc-oa-opendata.s3.amazonaws.com/PMC13789279.1/12904_2026_2360_MOESM5_ESM.docx) | `86be772b572ab06e0fa83eccc9df02ed2cbd08e29e4a56dc0beb4d988ce1dd1e` |

以題號連接題本、作答及質性分析。例如附件 2 的 `Q01` 對應附件 5 的 `Q1`。30 題共有 120 筆題目與參考的連結，引用表的 28 個 ID 中有 27 個被題本用到。逐一檢查 Word 排列中的回答段，確認 150 筆都有文字，且每題恰有五份、每個模型標籤 30 份。這是同題配對的五組作答，每組每題各一次。

附件 4 的 28 個案例均可對回附件 5 的一則作答，並與附件 4 所列的各模型件數一致。為比對題號，程式把質性表的 `ChatGPT-5.3 Instant` 對到作答檔的 `GPT-5.3 mini instant`。此處保留兩種原始標籤供查核。質性例是依內容摘選，28 件描述的是摘錄範圍。估安全事件的比例應使用有完整判定的分母及附件 3 所定義的配對比較。[聚合計數](aggregate.json) · [本庫配對盲審](../../../docs/rationale-review.md#同一題本的兩組回答如何盲審)

安裝 `.[report]` 後，將下列路徑改為原發布頁的附件 2、4、5。程式核對三個檔案的 SHA-256、題號、參考 ID 與逐題作答，輸出聚合 JSON。

```sh
python scripts/audit_end_of_life_responses.py path/to/12904_2026_2360_MOESM2_ESM.docx path/to/12904_2026_2360_MOESM4_ESM.docx path/to/12904_2026_2360_MOESM5_ESM.docx
```
