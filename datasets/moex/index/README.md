# 考選部歷年考試索引

索引從考選部考畢試題查詢平臺的年度選單開始。平臺同時列出醫事與其他國家考試，早年的醫師、護士與藥劑生也曾列在「專門職業及技術人員高等暨普通考試」之下。先取得一年內所有場次與類科，再按類科及科目判讀範圍，才能找到混合場次裡的醫事試卷。[考選部考畢試題查詢平臺](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx)

| 檔案 | 用途 |
|---|---|
| [coverage.tsv](coverage.tsv) | 每年選單場次數、官方宣告與實際解析的場次／類科／科目數、驗證狀態及差異原因 |
| [exams.tsv](exams.tsv) | 年度選單的全部場次及結果頁擷取狀態 |
| [categories.tsv](categories.tsv) | 全部已擷取類科、其原名、初篩分類及科目數 |
| [subjects.tsv](subjects.tsv) | 初篩為醫事或待複核的科目，包含官方識別碼 |
| [assets.tsv](assets.tsv) | 前表各科目所列附件。每列保留直接來源網址及官方檔案種類 |
| [exam_assets.tsv](exam_assets.tsv) | 屬於整場考試的附件，例如整場標準答案（A）、盲用電腦專用試題（B） |
| [exam_coverage.tsv](exam_coverage.tsv) | 年度頁有缺漏時的逐場核對紀錄，含可重訪的場次網址 |
| [pages.tsv](pages.tsv) | 官方回應 HTML 的來源、查詢方式、快取檔名、位元組數與 SHA-256 |

`medical` 涵蓋醫事人員證照、早年醫事職稱及衛生行政、衛生技術、公職醫事等明確對象。`boundary` 保留需要人工判讀的獸醫、社工、消防救護、食品、勞工衛生等相鄰類科，以及其他類科中具醫學關聯的科目。`outside` 類科也列入年度分母。初篩作用於整份試卷，同一醫事類科的國文等共同科目也會列入，題目是否適合做醫學評測仍需另外審查。

請將 `exam_code`、`category_code`、`subject_code` 當成字串。舊碼含前導零、英文字母、連字號或星號，例如 `02-7`、`700*`。`asset_id` 中的特殊符號使用百分比編碼。Q 是試題、S 是答案、M 是更正答案，每個來源連結各占一列。同一連結在網頁的手機版和桌面版各出現一次時合併。索引列出附件後，原件下載與內容檢核進度可由歸檔紀錄另行追蹤。

`accounted_exams` 統計已取得場次結果，以及官方選單明示未公布或逐場查詢明示查無結果的場次。後兩種另列在 `confirmed_empty_exams`，場次明細保留判讀依據。`verified` 表示所有年度選單場次均有交代，且實際擷取的場次、類科標題、科目三項計數均與官方結果頁相符。若全年查詢無法取得，可依選單逐場查詢，再加總各場官方分母。`unresolved` 保留已取回的可辨識資料與數量差異。原始快取在 `data/moex/index/`。完整重新整理可指定一個新的快取目錄，以保留既有快照。

部分早期試卷在科目列中提供類科代碼，卻沒有顯示該代碼的類科標題。這些代碼保留在 `categories.tsv`，名稱留空並記入 `heading_status`。年度統計以頁面可見標題數核對，另列 `category_codes_without_heading`。缺少類科名的科目保留在待複核範圍。

~~~bash
python -m medbench.moex_index
python -m medbench.moex_index --years 1992,2024
python -m medbench.moex_index --diagnose-only --years 2024
python -m medbench.moex_index --export-only
~~~

線上收集使用系統的 `curl` 及其 TLS 信任庫，兩次請求之間至少一秒。指定年份使用西元年。離線匯出讀取快取內所有年份，輸出固定排序的 UTF-8 TSV。
