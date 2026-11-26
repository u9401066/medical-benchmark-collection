# 醫師如何逐句核對模型詳解與引用

同一份回答可能選對選項、漏掉重要條件，也可能引到一篇確實存在卻無法支持該句的論文。這個流程讓醫師把「選了什麼」、「理由有何根據」及「引用能否核實」分別留下可查的紀錄。正式評估使用已核准的開發或保留評估題本。公開開發的練習回答可用來試填。[臨床判分與分母](temporal-evaluation.md)

醫師也可以直接在對話中回覆一筆。例如開啟 R-17163，貼出想核對的那一句，再寫下「符合、牴觸或尚待查證」、對應的官方表列或段落，以及出題時還需要交代的條件。編者可代為轉錄原句定位與意見，保留審閱人及日期。整份回答尚未看完時留下個別意見即可，該列繼續列為待審。[可直接閱讀的 12 份回答](../reports/tw-fit-date-probe/review-worksheet.md) · [原句定位練習](../reports/tw-fit-date-probe/review-guide.md)

## 產生與送回審查表

先保存推論前就已凍結的題本 SHA-256，並把每筆模型原始回答保存在預測列的 `text`。在儲存庫根目錄執行下列指令，可對每份有原文的作答產生一列 JSONL。逾時及漏答繼續留在原分派分母。格式解析失敗但仍存有原文的作答也可以審理由。

```sh
python -m medbench.clinical_score --gold data/clinical-dev.jsonl --predictions data/predictions.jsonl --worksheet --out data/rationale-worksheet.jsonl
python -m medbench.clinical_score --gold data/clinical-dev.jsonl --predictions data/predictions.jsonl --evidence-reviews data/rationale-worksheet.jsonl --out data/rationale-report.json
```

兩步都可加上 `--expected-gold-sha256` 及分派時保存的指紋。審查表保留題目、日期、地區、模型原文、參考主張、來源版本及定位。核對每份回答後，填入具名 `reviewer`、ISO 日期 `date`、實際耗時 `minutes`（沒有紀錄時留空）。確認已檢閱全文、額外主張及所有明示引用後，將 `inventory_complete` 設為 `true`，並將 `state` 改為 `complete`。未填完的列可保留 `pending`。題本、回答指紋或工作表內容對不上當次分派時，計分會中止。

## 一個判定如何定位

| 欄位 | 醫師填寫內容 |
|---|---|
| `reference_claims` | 逐一核對凍結題本所列的主張。每個 `index` 從 1 起算，評為有來源支持 `supported`、與來源抵觸 `contradicted`、仍無法判定 `unverified` 或回答未提及 `omitted`。同一句可以回答多個參考主張。 |
| `additional_claims` | 回答中額外提出、可查證的醫學或政策主張。逐項指回原句，用同樣的前三種狀態記錄。 |
| `span` | 使用原回答 `text` 的 Unicode 字元索引。從 0 起算，包含 `start`、不含 `end`。`quote` 須逐字等於 `text[start:end]`，保留空白、標點及換行。未提及的主張填 `null`。 |
| `evidence_ids` 與 `source_locators` | 有支持或抵觸判定時，填寫所用來源的 ID，以及每個 ID 對應的具體表列、建議編號或段落。用 `note` 說明該依據如何適用到題目的族群、地區及日期。引用新來源時，在 `additional_evidence` 登錄獨立 ID、URL、版本、定位及可確認公開的日期 `available_on`。用來判定臨床主張的來源必須在題目截止日已可取得。 |
| `citations` | 逐一定位模型原文中提出的書目或來源。登錄 `span`、`status`、實際查驗網址 `check_url`、位置或檢索方式 `check_locator`、理由 `note`。沒有提出引用時可留空陣列。 |

書目身分查證分為可確認 `verified`、錯引或錯置 `misattributed`、尚無法核實 `unresolved` 及已證實虛構 `confirmed_fabricated`。若作者在更正公告中明確指出某引文出於捏造，可用最後一項，登錄 `verification_basis=affirmative_primary_confirmation`，並在 `confirmation_excerpt` 保存足以複查的短原句。查無 PMID、DOI 無法解析或網站無法開啟時，單憑這些觀察應選 `unresolved`。書目可在審查當日核實，臨床主張仍依題目指定日期判讀。

## 報告怎麼讀

報告的 `evidence_review` 列出有原文的回答數、完成審查數、多少份具有參考主張，以及參考與額外主張各狀態的計數。參考主張支持比例的分母包含已審回答中的遺漏和無法判定主張。未進入人工審查的回答須另報覆蓋率。工時報告列出實際有記錄的份數、總分鐘數和中位數。

`confirmed_fabricated_response_share` 是至少含一筆已證實虛構引用的回答數除以全部已完成審查的回答數。只要有回答仍含待查引用，且該份回答尚無任何一筆確定虛構，這個比例就是已確認的下限，`fabricated_response_rate_among_audited` 會留空。兩個比例都以回答為單位，同一回答有多筆已證實虛構的引文也只計一次。人工標註需要就聲稱虛構的原件實際查核，程式只驗證定位與紀錄完整性。詳解審查結果獨立於臨床達標裁決。[判分程式](../medbench/clinical_score.py) · [原句和來源核對規則](../medbench/evidence_audit.py)
