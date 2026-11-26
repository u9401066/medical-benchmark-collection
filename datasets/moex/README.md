# 考選部歷年醫學與醫事考題

這份資料集用於清點及複核官方考題。每份試卷以「考試代碼、類科代碼、科目代碼」識別。代碼保留前導零與歷年出現的英文字母。同一份考題出現在兩個類科時，保留兩筆官方列載關係，下載的相同位元檔案則依 SHA-256 共用。

## 從統計表找資料

[開啟逐年統計總表](coverage/README.md)

| 查閱問題 | 檔案與讀法 |
|---|---|
| 各年官網列了多少？哪些年份已核對？ | [逐年覆蓋表](coverage/years.tsv) 並列年度選單場次數，以及場次、類科、科目的官方數字與實際取得數。`status` 是官方索引對帳結果。其後的下載與題目統計只計 `medical`，`boundary_papers` 另列。分母有落差時看 `detail`。 |
| 某場考試的某一類科還少幾份？ | [場次與類科統計](coverage/groups.tsv) 依年度、場次、類科、收錄範圍彙總。[逐科清單](coverage/papers.tsv) 可追到同一科的試題、原答案、更正答案及逐題抽取狀態。 |
| 如何找到原始附件？ | [官方逐科索引](index/assets.tsv) 有每個附件的網址、角色及識別碼。[下載清冊](archive/files.tsv) 記錄格式、位元組數、SHA-256 和本機快取相對路徑。[整場附件索引](index/exam_assets.tsv) 與[整場下載清冊](archive/exam-files.tsv) 另存整場標準答案或無障礙附件。 |
| 哪些資料來自公告？ | [公告與附件](notices/) 保留獨立公告的來源與追查範圍。公告、試題疑義答復和行政救濟可能敘述同一題的不同階段，應比對文號、日期、卷別、題號及正式決議。 |
| 我要查某一道題 | [逐題資料](items/) 依民國年／場次存放，每個 gzip JSONL 檔每列是一份試卷，`items` 是題目陣列。已定位的題目包含題號、頁碼、題幹、選項、引用與影像／表格等標記。 |
| 一個 ZIP 裡有哪些 Word 或文字檔？ | [無障礙附件包統計](archive/accessible-packages.tsv) 與[包內逐檔清冊](archive/accessible-members.tsv) 記錄官方 B 附件內的檔名、格式及各自的 SHA-256。一個場次的附件包可能只收錄部分類科，逐一核對目錄及科目後才連回試卷。 |
| 舊卷只有影像，要怎麼看？ | [逐頁 OCR](ocr/README.md) 可查原 PDF、頁碼、模型和逐詞位置。低信心字詞和橫／直排版面另留待人工核對。 |
| 獨立公告對上了哪些題？ | [逐題決議對照](rulings/README.md) 記錄公告或訴願的文號、結論、來源位置與試卷比對結果，也列出尚未配到原卷的歷史案件。 |
| 舊站上的連結是否重複？ | [舊版場次頁](legacy/pages.tsv) 及[逐連結比對](legacy/links.tsv) 保留頁面與檔案指紋。空白的答案連結另列；當附件與現行平台的同類檔案位元相同，就列出相符的場次或試卷代碼。 |

平台年度選單從民國 81 年（1992）至 115 年（2026）。每年先清點所有考試，避免只按考試名稱而漏掉混合場次中的公職醫事、衛生行政、衛生技術或早年檢覈考試。`medical` 為可辨識的人類醫療、醫事及公共衛生類科。`boundary` 保留食品、職業衛生、獸醫、社工，以及其他類科中出現醫學關鍵字的待辨項目。年度表的確定收錄數與邊界數各有分母。網路平台可檢索的下限，與考試本身的歷史起點可能不同。考選部也列出國家圖書館及各地文化中心的歷史查閱管道。[官方考畢試題平台](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx) · [考畢試題查閱管道](https://wwwq.moex.gov.tw/content/wfrmContent.aspx?menu_id=242)

## 題目與答案

實作題另存作答指示與官方評分標準。例如民國 106 年牙體技術師「全口活動義齒排列」是一項 100 分操作任務，卷上列出五項各 20 分的評分標準。這一題的 `published_rubric` 保留標準全文與頁碼，`requires_performance` 表示須檢視實際操作或作品。兩個官方入口提供相同的原始 PDF，SHA-256 為 `5c14cd10f94da7ab3631a00034772369b1198d96372d2d978b1b5c30e609d7bd`。[舊站試卷](https://www.moex.gov.tw/other/106110/11150.pdf) · [現行平台試卷](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=106110&c=111&s=1005&q=1)

類科覆蓋以該類科的**全考科**為單位，因此醫事類科若考國文或共同科目，也保留官方列載。日後編製「只測醫學能力」的子集時，另作學科標註。年度 `verified`、附件 `verified`、逐題 `extracted` 依序代表索引總數相符、原檔已取得且記錄雜湊、已產生題目紀錄。醫師對內容的判定另行保存。

- **Q、S、M** 分別代表官方試題、原始標準答案與更正答案。三者各有來源。某卷只有 Q 時，保留試卷並標出答案狀態。沒有查到 M 的卷，仍可有散落在公告中的更正。遇到網站回傳 HTML 錯誤頁、損壞檔案或多個無法判定主從的附件，留下待處理紀錄。
- **給分方式**保留官方鍵值與備註原文。逐題標示 `single`（單一答案）、`replacement`（有更換答案的證據）、`any_of`（指定答案或作答組合皆可）、`all_of`（須選完整組合）、`all_credit`（一律給分）、`conditional_credit`（附條件給分）及 `unresolved`（待核對）。計算多重給分、送分與撤題時應分項報告。
- **統計單位**為試卷列載、附件列載或題目紀錄。`M_verified` 數更正檔案，`items_with_corrected_key` 數有 M 卷鍵值的題目；一份 M 常重列整張答案卷。只有逐題備註、原鍵與更正鍵，以及相符的公告證據，才能判斷哪一道題被更動。`items_with_text` 表示有題幹文字，含圖或承上題仍可能缺少獨立作答條件。
- **待醫師核對**的欄位包含題目適用情境、醫學正確性及是否適合獨立計分。本檔案庫保留申論、圖片題、答案有爭議或尚未抽出文字的卷別。既有可計分的 2024–2026 單選子集另有固定版本。[twmed-v1](../twmed/README.md)

例如，民國 113 年護理師「內外科護理學」第 28 題，原答案為 A，更正卷以 `#` 標記，備註寫明該題一律給分。只保存最後一個答案字元會遺失作答規則。[原答案](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=S&code=113180&c=101&s=0103&q=1) · [更正答案](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=M&code=113180&c=101&s=0103&q=1)

《國家考試試題疑義處理辦法》第 4 條區分單選題更正後的可接受組合、互斥組合及複選題更正為單一正解的給分方式。申論題或子題有誤時，第 5 條另有配分處理。因此查核以該次考試的原文、決議及當時法規版本為準。保留考生提出的請求、機關決定與後續救濟各自的身分及日期。[第 4、5 條及修正日期](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=R0030063)

## 既有彙整與可比範圍

[雙官方清單的逐科比對](opendata/README.md) 已核對政府 CSV 中 64,815 筆科目。在與本庫相關的項目中，找到 1,695 筆由 CSV 連到更正答案、另由考畢平台補到原答案的紀錄。

[EMPEC 與官方原卷的逐題對照](comparisons/README.md) 已將 225 個官方題號配到題幹及選項一致的上游紀錄。民國 112 年三份卷共找到 3 題在舊題庫列單一選項、在考選部更正卷列為一律給分；對照表保留逐題頁碼及原件指紋。

| 來源 | 已整理的內容 | 與這份清冊怎麼對照 |
|---|---|---|
| 考選部開放資料 170565 | 自民國 101 年起提供全國考試逐科 CSV，含類科、節次、題型、試題及答案網址 | 適合逐卷核對。例：101010 場牙醫師（一）牙醫學（一）在 CSV 連更正卷，考畢試題平台同時列出原答案及更正卷。[官方資料集](https://data.gov.tw/dataset/170565) |
| EMPEC | 2011–2024 年、20 個醫事職類、124 科，共 157,803 題，另有英文測試集 | 適合比對已轉成文字的選擇題，研究建集時排除須讀圖表的題目及部分在地考科。資料卡列 CC BY-NC-ND 4.0。[ACL 論文](https://aclanthology.org/2025.findings-acl.518/) · [作者資料集](https://huggingface.co/datasets/KenLuo/EMPEC) |
| medical-bench-tw v3.1.2 | 資料卡載明 2009–2026 年、187,910 個不同題目 ID，涵蓋國考與其他醫療考試，公開主測試集有 1,738 題 | 該版聚焦無圖單一答案題。資料檔須接受存取條款，作者註明尚待系統性醫師複核。跨集比較須記錄定版和相同來源題的重疊。[作者資料卡](https://huggingface.co/datasets/Erichuang777777/medical-bench-tw) |
| MedQA-TWMLE | 醫師考試的繁體中文子集，本專案已接入 1,413 題測試題 | 可重現既有論文的醫師評測；多職類比較須另列各職類分母。[作者儲存庫](https://github.com/jind11/MedQA) · [本專案目錄](../catalog.md) |
| exams_tw | 社群整理的考選部網址表、試卷下載程式及 PDF 轉 JSON 範例 | 維護者記錄曾下載 89,484 個各類國考 PDF，此數以檔案為單位，涵蓋各行業。[作者專案](https://github.com/pofeng/exams_tw) |

## 重現一批

在儲存庫根目錄安裝 `pip install -e ".[build]"`。索引可由 `python -m medbench.moex_index --help` 查閱取得方式。以下指令示範如何依已公布的索引核對單一試卷，再更新統計表。

```sh
python -m medbench.moex_archive --paper 113180-101-0103 --manifest data/moex/local-files.tsv
python -m medbench.moex_items --manifest data/moex/local-files.tsv --paper 113180-101-0103 --out data/moex/local-items
python -m medbench.moex_coverage --manifest data/moex/local-files.tsv --items data/moex/local-items --out data/moex/local-coverage
```

檔案快取預設在 `data/moex/archive`，清冊內的 `local_path` 相對於這個目錄。`--limit 0 --verify` 可用已下載的資料重新驗算清冊。`--refresh` 會重訪來源並保留歷史檔案版本。不同時點的官網內容若已改版，依原始 SHA-256 與新版區別。引用原始檔時併列考選部、場次、類科、科目、題號及原檔連結。考選部要求引用註明出處並確保資料完整。[官方引用聲明](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx)

完整一批使用 `python -m medbench.moex_bundle --years 81-115` 依官方每次最多八科的打包方式下載醫事卷。執行 `python -m medbench.moex_checkpoint` 可離線重驗已取得的檔案，產生逐題資料、下載清冊與三層覆蓋表。各年度可分開下載，多批共用同一個快取。公開資料集納入清冊及抽取結果，原始附件可依清冊的官方來源及 SHA-256 重取。
