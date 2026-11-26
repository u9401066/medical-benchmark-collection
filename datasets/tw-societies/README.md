# 臺灣醫學會官網與考試公告

按科別找學會時，可直接開啟[分科名錄](by-specialty.md)。每一列都標明官網的查核狀態，以及已定位的考試公告或題目。查證一份試卷時，可用[考試來源表](exam-sources.tsv)找到同一學會不同年度、科目或形式的材料。一個學會可能同時公開筆試、口試、申論或認證樣題。

| 查閱目的 | 資料與讀法 |
|---|---|
| 找某科的學會或次專科 | [分科名錄](by-specialty.md) 可展開只有登記名稱的候選，以及已解散或籌設中的單位。整併名、來源原名、其他相關科別和立案資料可查[完整 TSV](societies.tsv)。 |
| 判斷某科還缺多少網站 | [分類統計](coverage.tsv) 並列學會、其他組織、登記狀態、核實的網站、仍待核對的網址與缺額。 |
| 找可追蹤的考試 | [考試來源表](exam-sources.tsv) 分別記錄已公開試題及答案、公開題本、公開樣題、甄審公告、規定及訓練計畫。急診、神經、內科與泌尿的年度、卷別及訂正註記可查[六科歷年題本查核](sources/exam-archives.tsv)。未查到時標為待查。 |
| 確認主管機關認列的科別 | [科別與機構對照](sources/specialties.md) 完整列出西醫 25 科、牙醫 11 科及中醫 6 個試辦訓練科別。一科可由多個學會共同承辦。[骨科醫學會所列 10 個次專科團體](sources/orthopaedics.tsv)另存原稱與更名依據。 |
| 找醫事職類與跨科組織 | [護理、藥學、復健、公衛、醫教等專業來源](sources/networks.md)、[中醫藥司團體表](sources/chinese-medicine.tsv)、[生物醫學聯合學術年會成員](sources/biomedical.tsv)。另由兩個全聯會的會員名錄核實 [23 個地方護理公會與 18 個藥師公會網站](sources/guild-websites.tsv)。 |
| 查地方登記團體 | [22 縣市主管機關入口](local-portals.tsv) 記錄可查的具名名冊、檔案格式與入口限制。[北中南三市](local-coverage.md)、[高雄等 11 縣市](regional-coverage.md)、[新北等 8 縣市與缺口](municipal-coverage.md) 分列名冊版本、實取筆數及範圍。 |

台灣家庭醫學醫學會另按期發布繼續教育測驗。《家庭醫學與基層醫療》第 41 卷第 8、9 期各核實 16 道可公開讀取的選擇題，頁面共 32 個正解標記。原始 HTML 指紋、學會測驗編號、出版日與權利查核狀態均附於來源表。[學會期刊索引](https://www.tafm.org.tw/ehc-tafm/s/w/ebook/index_other/otherlist/2) · [已核對兩期的資料](sources/journal-quizzes.tsv)

台灣麻醉醫學會的 113、114 年專科甄審口試各有 2 個病例，分別含 8、9 個開放式提問。附件列出各小題配分，參考回答仍待補證。113 年公告另有筆試答案更正，來源表記明適用題號。[113 年公告](https://www.anesth.org.tw/news/content.asp?ID=2120) · [114 年公告](https://www.anesth.org.tw/news/content.asp?id=2232&type=1) · [口試及臨床評量附件定位與指紋](sources/clinical-assessments.tsv)

中華民國核醫學學會「醫事放射師核醫組教學評量」收錄 DOPS 操作技能直接觀察、CbD 個案討論與 mini-CEX 迷你臨床演練，各有空白評量表及配套說明。三份表分別含 10、6、7 個評量面向，按量表登錄。DOPS 空白表與說明對第 4 項使用不同標頭，後續建立評分規準時須逐項核對。兩學會的附件目前均只收錄可核查的中繼資料，題文、量表的重刊及訓練權利待確認。[核醫學會下載索引](https://snm.org.tw/xcfile?psid=0O198666711473294194&xsmsid=0O050602815341260326) · [配套說明及權利紀錄](sources/clinical-assessments.tsv)

## 全國名冊與查核界限

內政部「人民團體數位櫃檯」以社會團體名稱查詢「學會」，2026-11-26 官網列出 4,064 筆，已逐列保存全選匯出的名稱、立案證號與狀態。分母包含各學術領域，其中 3,604 筆已立案、369 筆解散、91 筆已准籌或仍在審查。另查「醫師協會」，以補充使用其他名稱的專業組織。歷史拼寫或官網沿用舊名時，保留原稱與明示更名的依據。[內政部現行查詢](https://grouptw.moi.gov.tw/searchGroup) · [即時快照與 391 筆「醫學會」交叉查詢](live-registry.md) · [全選匯出紀錄](live-registry.tsv) · [醫師協會查詢](live-physician-associations.tsv) · [異名對照](aliases.tsv)

另完整讀取內政部兩份公開 CSV，分別有 23,210 與 23,864 筆。兩份名冊彼此重疊。成立日期欄可辨識的最晚日期分別為 2023-04-16 與 2021-12-30。舊名冊用來找歷史名稱與遺漏單位。兩份檔案都沒有學會官網欄位。分類名稱所用字詞、醫療相鄰領域、動物專業及其他排除理由等篩選結果均可複查。[全國性人民團體名冊](https://data.gov.tw/dataset/13603) · [全國性社會團體按地區名冊](https://data.gov.tw/dataset/147595) · [檔案指紋與筆數](registry-snapshots.json) · [逐筆名稱篩選](registry-screen.tsv)

衛福部、學會、醫師及醫事人員公會、聯合學術年會和地方政府提供其他獨立來源。名錄的負責範圍不一，專科受託、友會、簽署團體、醫學研究會及公會分列。收錄單位不代表其具備部定專科甄審資格。公會、協會及承辦機構可在 `org_type` 各自篩選。[機構友會原始列與定位](sources/directory.tsv) · [地方名冊原始列](sources/local-societies.tsv) · [歷史名稱與當時列址](sources/historical-health.tsv)

地方主管機關入口涵蓋全臺 22 縣市。三份地方查核報告合計核對 37,878 個來源列（8,449 ＋ 18,605 ＋ 10,824），20 縣市有具名資料可判讀。部分縣市僅涵蓋特定團體類別或歷史年度。桃園的全市查詢有圖形驗證碼，雲林最新附件無法讀取。臺東與連江的縣級人民團體名冊仍待補齊。另從衛生機關、法院及職業全聯會取得[臺東 11 個與連江 3 個具名團體](eastern-health.md)，獨立計數。入口表的 `roster_rows_examined` 是逐列查核的分母，`roster_rows_selected` 是 462 條收錄來源列，`separately_sourced_organizations` 是上述 14 個補充團體。[22 縣市入口](local-portals.tsv) · [八縣市版本及限制](municipal-coverage.md)

## 網站與試題的判讀

- `society_id` 連結分科名錄與考試來源表，兩表可用這個欄位合併。同一學會的台臺異寫、法人前綴及有依據的簡稱共用識別碼。識別碼取自正規化全名的 SHA-256 前 16 碼，將來若修訂歸戶全名，需保留舊名對照。
- `confirmed` 表示網站首頁、章程、主辦單位頁面或正式受託頁已核對組織身分。`directory` 是來源名錄或已索引的學會自有頁所列候選網址，`pending` 是目前仍無可採用網址。失效的舊連結、外站代辦頁與多個可能的官網留在來源或[逐名查核紀錄](name-search.tsv)中。
- `registry_name_candidate` 表示從登記名稱辨識到醫療字詞，專業性質與網站仍待核對。科別依名稱與已知專業來源標示，跨科另記 `related_groups`。只有機構自己或發布者明確支持的更名與簡稱才合併。同網域可服務不同學會。
- `live_registry_status` 原樣保留本次中央查詢所列的狀態。空白表示該列未對應這兩次中央查詢結果，地方登記與歷史來源須回到各自發布機關核對。
- 公告公開、試卷可讀、學會提供答案、允許重刊與人工複核是不同欄目的證據。本目錄保存出處與定位，後續若編題、翻譯或加入訓練資料，再查該份檔案的權利與臨床正確性。

## 重建

在儲存庫根目錄執行 `python -m medbench.tw_societies`，即可從版控中的逐列證據重建分科名錄、考試來源表與統計。要重驗兩份原始 CSV，先依 [registry-snapshots.json](registry-snapshots.json) 下載對應版本，再執行下列指令。歷史檔案和網站查核底稿在這台工作機的 `data/tw-societies/`。

```powershell
python -m medbench.tw_societies --registry-csv 13603=data/tw-societies/complete-13603.csv --registry-csv 147595=data/tw-societies/quality-147595.csv
```
