# 考選部試題與答案逐題紀錄

每個民國年度下的 `<考試代碼>.jsonl.gz` 對應一場考試。解壓縮後，每行是一份考卷，`paper_id` 可連到檔案清冊。這批資料供研究與人工校核，與正式計分的 [twmed-v1](../../twmed/README.md) 分開維護。

- `sources` 保留各附件的類型、官方網址、下載狀態及已驗證檔案的 SHA-256。Q 是題本，S 是原標準答案，M 是更正答案。`roles_not_listed_in_current_manifest` 表示本次清冊未列出該類附件。考選部另行發布的公告須再核對，進度記在 `separate_correction_notices`。
- `items` 的識別碼保留考試、類科、科目與題號。申論使用獨立的 `essay` 區段，以區分同卷的「申論第一題」和「測驗第一題」。`pages` 從 PDF 第 1 頁起算，測驗題的 `start_y_pt` 是第一頁題幹起始處距該頁上緣的點數。圖像與表格仍須開啟來源 PDF 判讀，相關線索記在 `flags`。
- `key_evidence.S`、`key_evidence.M` 分別保留來源表格中的原始答案符號及所在頁。如有逐題備註，`note` 保存原文字串與頁碼。`rule` 描述這批 PDF 支持的作答規則。已知有 M 且尚未取得時，S 可供查核，題目規則標為 `unresolved`。已取得完整 M 而 S 尚待補件時，可讀出 M 的答案，原答案保留空缺。
- `status` 屬於整份卷。沒有辨識出題目的卷為 `unresolved`，已辨識題目但有待處理問題的卷為 `partial`，其餘為 `extracted`。即使完整辨識了各題，申論、未辨識的更正敘述等仍可有逐題的 `unresolved`。當題號、附件、卷碼或規則無法對應時，請查閱 `issues`、`source_pages` 與官方檔案。

| `rule.kind` | 判讀方式 |
|---|---|
| `single` | 檔案指定的單一選項。 |
| `replacement` | 原、改兩鍵顯示已換成另一個選項，或更正備註明載改答。 |
| `any_of` | 每個字串都是備註明列的受理作答。例如 `["A", "D", "AD"]` 表示只選 A、只選 D、同時選 A 與 D 都給分。若只列 A、D 兩種作答，其他組合記為 `requires_review`。 |
| `all_of` | 複選題標準鍵或更正備註所列的正確選項集合。這個欄位不計算部分給分，`partial_credit` 另外標記待核。 |
| `all_credit` | 備註明載無條件一律給分。 |
| `conditional_credit` | 給分另有限制，例如排除未作答者。限制原文在該題的 `note`。 |
| `published_rubric` | 實作卷的評分標準全文，附試題原頁及起始位置；`instructions` 留有操作條件。 |
| `unresolved` | 作答規則尚待資料補齊或人工判讀。 |

單選疑義題可能有數個同等適當答案，互相排斥且無法同時成立的組合另有規定。複選題若經決議更正為單一正解，包含該選項的作答與未包含者採不同給分方式。逐題欄位只記來源實際載明的規則，未載明的組合與部分給分須核對該次決議、施測日期與適用的法規版本。[國家考試試題疑義處理辦法第 4 條](https://law.exam.gov.tw/LawContent.aspx?id=FL016791) · [閱卷規則第 19 條之 2](https://law.exam.gov.tw/LawContent.aspx?id=GL000010)

## 重建與續跑

安裝專案的 `build` extra，備妥清冊中已驗證的原檔後，在儲存庫根目錄執行。程式重驗輸入檔雜湊，只重建清冊狀態、來源、解析器版本或 PyMuPDF 版本發生變化的紀錄。

```powershell
python -m medbench.moex_items --manifest datasets/moex/archive/files.tsv --cache data/moex/archive --out datasets/moex/items
python -m medbench.moex_items --manifest data/moex/archive/files.tsv --paper 113180-101-0103
```

以 `--year 115` 限定民國年度，也可用 `--paper` 重複指定考卷。同場考試分批重建時會保留現有的其他卷。年度目錄與 gzip 檔內容順序固定，檔案不含建置時間戳。
