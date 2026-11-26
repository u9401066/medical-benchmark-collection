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

## 同一題本的兩組回答如何盲審

用同一份凍結題本跑出兩份 `predictions.jsonl`。準備盲審時，程式按題將兩份回答放在一起，並獨立調換每題的呈現順序。給醫師 `packet.json` 即可。題文、原始回答、參考答案、評分準則和來源定位都在表內。獨立的 `key.json` 用來對回兩份原始作答和選樣紀錄。管理者另外保存每份作答所用的模型版本。模型在原文中的自稱和文字風格仍可能暴露身分。若察覺，請在審查理由中記下線索，原文位置才可追溯。

```powershell
$assignmentSha = (Get-Content data/run/assignment.sha256 -Raw).Trim()
python -m medbench.clinical_blind prepare --gold data/curated/clinical-dev.jsonl --expected-gold-sha256 $assignmentSha --left data/run/old/predictions.jsonl --right data/run/updated/predictions.jsonl --key data/paired-review/private/key.json --packet data/paired-review/for-review/packet.json
```

工時有限時，可事先依「答案時效、缺資料、科別」等研究設計定義病例家族層別，並保存計畫與抽樣種子。每個家族只分配到一層，全部層別須涵蓋整份凍結題本。每層不放回抽選 `n` 個家族，選中的同家族翻譯、同病例變體與兩組回覆一併分派。用 `--plan data/sampling-plan.json --sample-seed 34965` 傳入 JSON 陣列。下列欄位中的家族 ID 應取自題本。省略計畫時全批分派。

```json
[
  {"name": "changed_rule", "family_ids": ["case-family-1", "case-family-2"], "n": 1},
  {"name": "stable_control", "family_ids": ["case-family-3"], "n": 1}
]
```

複製一份 JSON 作回填，或以 `R-` 開頭的匿名號碼逐筆提供決議，讓編者代為記錄。可獨立完成兩項判定。

1. **臨床達標。** 填 `clinical_verdict` 為 `pass`、`fail` 或 `undetermined`，並在 `clinical_reason` 記理由、在 `reviewer` 和 `date` 留下具名審查者及日期。解析失敗但留有原文時，`clinical_reviewable` 為 `false`，這類可逐句審查。
2. **詳解及引文。** 依上節完成主張及引用定位，填入 `reviewer`、`date`，記下實際使用的 `minutes`。逐句盤點完成後，設 `inventory_complete` 為 `true` 並將 `state` 改為 `complete`。未完成的列可保留 `pending`。

送回時可以只附已處理的匿名列。保留每列 `context`、配對編號和位置，這些欄位會逐項核對。管理者使用原來兩份作答和同一份對照檔，將裁決對回原始回答指紋。

```powershell
python -m medbench.clinical_blind intake --gold data/curated/clinical-dev.jsonl --expected-gold-sha256 $assignmentSha --left data/run/old/predictions.jsonl --right data/run/updated/predictions.jsonl --key data/paired-review/private/key.json --reviews data/paired-review/returned.json --out data/paired-review/private/report.json
```

輸出含具名臨床審查、逐句判定、原始分派與回填檔的指紋、兩組全題本分母和配對差異。漏答、逾時及未抽中但仍待裁決的題留在各自分母。技術失敗已定為未達標，待裁決的臨床項目保留差異上下界。私有報告另記各層的抽選比例，供分析使用。依比例不同的層別抽審後，單純計算已審平均只能描述那批已審回答。推估母集的平均差異須按原抽樣設計加權並處理未完成的審查。[臨床與引用比較](temporal-evaluation.md#同一份題本如何比較兩個模型) · [盲審與回填程式](../medbench/clinical_blind.py)

## 報告怎麼讀

報告的 `evidence_review` 列出有原文的回答數、完成審查數、多少份具有參考主張，以及參考與額外主張各狀態的計數。參考主張支持比例的分母包含已審回答中的遺漏和無法判定主張。未進入人工審查的回答須另報覆蓋率。工時報告列出實際有記錄的份數、總分鐘數和中位數。

`confirmed_fabricated_response_share` 是至少含一筆已證實虛構引用的回答數除以全部已完成審查的回答數。只要有回答仍含待查引用，且該份回答尚無任何一筆確定虛構，這個比例就是已確認的下限，`fabricated_response_rate_among_audited` 會留空。兩個比例都以回答為單位，同一回答有多筆已證實虛構的引文也只計一次。人工標註需要就聲稱虛構的原件實際查核，程式只驗證定位與紀錄完整性。詳解審查結果獨立於臨床達標裁決。[判分程式](../medbench/clinical_score.py) · [原句和來源核對規則](../medbench/evidence_audit.py)
