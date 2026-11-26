# 考選部公告、附件與試題疑義決議

本資料保留公告發布日、原文網址、原附件與雜湊。一般新聞、法規、訴願人的主張和典試委員會已核定的逐題決議，對計分有不同意義。個別題目的資料保留原答案、決議及證據位置。

| 檔案 | 內容 |
|---|---|
| [notices.tsv](notices.tsv) | 公告來源、發布日、標題、索引與內文連結，以及讀取時的 HTML SHA-256 |
| [attachments.tsv](attachments.tsv) | 公告實際連結的附件、上層網頁、格式、位元組數與 SHA-256。保留同一案件的 PDF 和 Word 版 |
| [decisions.json](decisions.json) | 已逐項核對的題號、原答、更正條件與頁／段落。含官方 HTML 直接宣布給分的實例 |
| [coverage.tsv](coverage.tsv) | 民國 81–115 年逐年列出考試總數、候選場次、取回回應、有對應場次內容、官方傳回找不到頁面及尚待取得的數量 |
| [index.json](index.json) | 年度選單 SHA-256、各公告頻道的查詢詞與實際筆數、逐頁 SHA-256、各場次可讀性與附件命中紀錄 |
| [全文掃描進度](fulltext/coverage.json) | 全部標題的官方分母、實取筆數、已讀與待讀正文、附件取得及文字抽取狀態。獨立於上述逐題證據 |
| [全文文章清單](fulltext/articles.tsv) · [全文附件清單](fulltext/attachments.tsv) | 每篇公告及其直接附件的網址、原件 SHA-256、搜尋狀態；附件陽性線索保留頁碼或段落 |
| [考選周刊索引](weekly.json) | 紙本周刊數位典藏的標題查詢、各頁分母、命中文章的出刊日與原始掃描 PDF 的查核狀態 |

## 2026-11-26 的來源覆蓋

一般公告與歷史爭訟的索引合計核對 8 份結果頁。「考試公告」當時提供 8 筆，「緊急通告」顯示零筆。「最新消息」的搜尋欄位是標題關鍵字；試題、答案、給分、送分各命中 10、1、1、0 筆，同一公告可能出現數次。重要考選行政爭訟案例目錄共 58 筆，兩頁分別取回 30 和 28 筆。篩出 4 篇與本批有關的公告和案例，連結的兩份附件皆已取得。[考試公告](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=2&menu_id=41) · [最新消息](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=3&menu_id=42) · [緊急通告](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=1&menu_id=5) · [重要考選行政爭訟案例](https://wwwc.moex.gov.tw/main/examlaws/wfrmExamLaws.aspx?kind=7&menu_id=1933)

各年場次另從考畢試題年度選單取得；人類醫事職類同時比對考試名稱及已取得的官方類科，故民國 81 年名稱籠統的「專門職業及技術人員高等暨普通考試」也納入。檢查每場試務資訊頁的實際連結與附件標題，核對該頁回連的考畢試題場次代碼，再找「試題疑義、試題更正、標準答案、一律給分」等字樣。較早年度的試務頁常被導向官方找不到頁面；這些場次的試卷與 Q/S/M 仍須回考畢試題平臺核對。未命中標題或讀不到歷史公告，只能說明本次取得的內容。[分年分母與完成數](coverage.tsv) · [官方類科與範圍](../index/categories.tsv) · [考畢試題平臺](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx)

全文掃描另外逐頁盤點一般公告頻道的完整標題，再讀取每篇正文，涵蓋未在標題出現「醫事」「更正」的文章。最新消息已從 7 頁取得 630 筆標題，發布日期落在 2022-11-28 至 2026-11-26；考試公告 8 筆、緊急通告 0 筆。正文內文、頁面列示的附件、正文直接連結的文件及圖片分別處理；搜尋詞涵蓋疑義、更正答案、重新評閱和給分。PDF 使用原生文字層，Word 與開放文件依段落查找。備有繁中 OCR 時，掃描圖頁與圖片另作辨識並標示 OCR 段數。檔案無法取得、格式無法解析、圖片讀不到文字時保留相應狀態。關鍵詞命中只表示值得複核。是否更改計分，仍須對回考試、科目、題號及原始決議。已核對的逐題案例見 `decisions.json`。

考選部另有《考選周刊》數位典藏，1985-07-15 創刊，2007-01-25 第 1,103 期後停刊。考選部記載曾將各期內容掃描建檔；整合系統可依期別、分類及作者或標題關鍵字查詢。本批一般新聞統計只含上述現存網站期間。早期試務頁傳回找不到頁面，並無法判斷同一事項當年是否刊於紙本、是否有單獨公告或後續是否刪文。[考選部典藏沿革](https://wwwc.moex.gov.tw/main/content/wfrmContent.aspx?menu_id=671) · [考選周刊整合查詢](https://wwwc.moex.gov.tw/main/ExamWeekly/wfrmExamWeekly.aspx?menu_id=922)

35 年共列 879 場，以考試名稱或人類醫事類科篩得的 400 場均已核對試務頁回應。58 場有可辨識的試務頁，342 場由官方傳回找不到頁面。在 58 個有效頁面的連結標題中未找到直接的改答或給分公告。[分年明細](coverage.tsv)

《考選周刊》索引顯示 15,334 篇文章。本批用六個標題詞逐頁查核，共命中 17 篇不重複文章。已取得 2004-06-17 醫師國考試題分析與 2006-09-21 第二次醫事考試放榜報導的掃描 PDF。兩篇標題反映更正趨勢，取得的影像版面仍須人工定位，故沒有據此登錄個別題目。其餘文章依醫事相關性及一般試題疑義程序決定是否取件。[查詢和檔案指紋](weekly.json) · [2004 年原刊](https://wwwc.moex.gov.tw/main/ExamWeekly/wHandExamWeekly_File.ashx?weekly_id=13587) · [2006 年原刊](https://wwwc.moex.gov.tw/main/ExamWeekly/wHandExamWeekly_File.ashx?weekly_id=15111)

## 逐題核對

- **民國 83 年、86 年醫師考試的兩個待查案例**。考選部 2011 年出版的《各種考試事件參考案例暨處理情形彙編》有兩處無法逐題對應。案例 6-9（PDF 第 12 頁）記載 83 年第一次「基礎醫學（一）」更正答案，未寫題號，同科更正表列第 49 與 79 題。案例 6-8（第 11 頁）寫 86 年「公共衛生學」第 86 題可答 B 或 C，但同年醫師試卷的更正表只有 80 題，且其第 68 題接受 B 或 BC。兩筆均保留原件差異及查核線索。[官方出版目錄](https://wwwc.moex.gov.tw/Main/Publication/wfrmPublication.aspx?kind=1&menu_id=62&pub_id=171) · [彙編原件](https://wwwc.moex.gov.tw/Main/Publication/wHandPub_File.ashx?file_id=64) · [83 年更正表](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=083020&c=004&s=c084&q=1) · [86 年更正表](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=086260&c=239&s=7004&q=1)
- **民國 90 年第一次醫事人員檢覈筆試，醫師第二階段**。考試院（90）考台訴決字第057號記載外科學等科第 10 題原為 B，疑義會議接受 B 或 A。婦產科學等科第 13 題維持 A。案件過程中曾出現一律給分的主張。決定 PDF 第 3 頁「事實」與 Word 第 21 段可對照案情。場次 `090040` 的外科更正表載 A 或 B，婦產科更正表第 13 題列 A，備註只有第 7 及 29 題。兩科的索引都只有考題與更正表。[官方案件與附件](https://wwwc.moex.gov.tw/main/ExamLaws/wfrmExamLaws.aspx?kind=7&menu_id=1933&laws_id=230) · [該場試卷](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx?e=090040&y=2001)
- **民國 99 年第二次醫師（一）醫學（二）第 4 題**。彙編案例 6-10（PDF 第 13 頁）記載首次疑義會議維持 D，後續研商改為 C 或 D，並列有 100 年 1 月 21 日選題二字第1003100049號公告。同場更正表第 1 頁也記作答 C 或 D 者均給分。索引未列獨立原答案表，原答及處理先後來自機關彙編。[彙編原件](https://wwwc.moex.gov.tw/Main/Publication/wHandPub_File.ashx?file_id=64) · [醫學（二）更正表](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=099130&c=101&s=200&q=1)
- **民國 111 年牙體技術師考試**。考試院 111 考臺訴決字第 143 號第 3 頁記載，9 月 13 日疑義會議決議「牙體技術學（四）」第 46 題維持 C。原 S 表與更正 M 表第 46 題均為 C；同張 M 表另載第 1 題可答 A、B 或 AB，第 17 題可答 B、C 或 BC，第 18 題一律給分。已分別記錄各題可接受的作答組合。訴願決定日期為 12 月 5 日，舊發布頁的公告日期待查。[官方決定書](https://ws.exam.gov.tw/Download.ashx?icon=..pdf&n=MTExLTE0My5wZGY%3D&u=LzAwMS9VcGxvYWQvMS9yZWxmaWxlLzkyODcvNDYzMDUvYjAyMDc4NWYtMmY1NS00ZDgyLTkzMmItYjlmMDcyMmRjY2M4LnBkZg%3D%3D) · [官方更正表](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=111110&c=109&s=0804&q=1)
- **民國 112 年第二次社工師考試，跨域邊界例**。7 月 31 日公告啟動討論，8 月 2 日公告「社會工作」測驗第 34 題一律給分。可用場次 `112110`、類科 `103`、科目 `0301` 查回原答案 C 與更正答案表第 1 頁的備註。這筆收在 `boundary_items`。兩份公告提供理由與決議日期，原 S/M 表提供題號與給分條件。[初次說明](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=3&menu_id=42&news_id=5976) · [正式決議](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=3&menu_id=42&news_id=5979) · [原試卷與答案檔清單](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx?y=2023&e=112110)
- **總體統計**。115 年 11 月 19 日說明回顧 114 年國家考試。1,533 題有疑義，其中 191 題更正答案或一律給分。0.73% 的分母是該年度列考測驗式試題總數；本文無逐題明細。[官方說明第一點](https://wwwc.moex.gov.tw/main/news/wfrmNews.aspx?kind=3&menu_id=42&news_id=7892)

更正為數個可接受答案、選項組合有條件給分、全題給分及維持原答均應各自記錄。處理原則可能隨年度改變，個案保留當時的證據與可確認的條件。[國家考試試題疑義處理辦法第 4 條](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=R0030063)

## 重取與查核

在 repo 根目錄執行下列指令，需要系統有 curl。年度 HTML 是考畢試題索引建置時的 `year-YYYY.html`，公告、Word 與 PDF 原件保存在忽略版控的 `data/moex-notices/YYYY-MM-DD/`。在新的查核日使用新快取目錄；同一天重新執行會沿用已取得的檔案。網頁計數器或版面異動也可能改變 HTML 雜湊，與舊快照有差異時須重新定位證據。

```sh
python -m medbench.moex_notices --as-of 2026-11-26 --year-cache data/moex/index
python -m medbench.moex_notices --as-of 2026-11-26 --year-cache data/moex/index --offline
python -m medbench.moex_notices --as-of 2026-11-26 --verify-decisions
python -m medbench.moex_notices --as-of 2026-11-26 --fulltext
python -m medbench.moex_notices --as-of 2026-11-26 --fulltext --offline
python -m medbench.moex_notices --as-of 2026-11-26 --weekly
```

`--offline` 可以從已下載的資料建立中間批次；缺少的來源列在 `index.json` 的 `failures`，程式以非零狀態結束，方便下次續抓。歷史案卷的本機原件用於核對，題目清單只登錄必要計分事實與機關文號。

全文附件的 PDF 文字層使用 `[build]` 安裝選項中的 PyMuPDF。此次 OCR 使用 Tesseract 與官方 `tessdata_fast` 繁中模型，原始 SHA-256 為 `529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b`。模型放在 `data/moex-notices/ocr/chi_tra.traineddata`。未安裝時會保留原件與待辨識狀態。[固定版本的模型](https://github.com/tesseract-ocr/tessdata_fast/blob/87416418657359cb625c412a48b6e1d6d41c29bd/chi_tra.traineddata)
