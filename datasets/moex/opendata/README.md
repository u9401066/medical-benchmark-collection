# 政府開放資料與考畢試題查詢平臺的對照

本次比對採用政府資料開放平臺為資料集 170565 提供的 CSV 匯出檔。2026 年 11 月 26 日取得的檔案共 25,099,131 位元組、64,815 筆，涵蓋民國 101 至 115 年。提供機關為考選部，目錄標示按日更新，授權為政府資料開放授權條款第 1 版。原站資源、這次實際下載的政府匯出網址、資料本身與比對用索引的 SHA-256 均記於來源紀錄。[政府資料集 170565](https://data.gov.tw/dataset/170565) · [來源與指紋](source.json)

以考試、類科、科目三個官方代碼配對，再逐一比對 CSV 所載試題及答案網址。原始 CSV 的 64,815 筆資料各有不同的科目鍵。依 CSV 提供的類科名與科目名初篩，4,940 筆屬醫事、3,864 筆待複核，這兩組均逐筆對到查詢平臺的固定索引。其餘 56,011 筆列入局外分母。308 個場次中，有 96 場同時出現醫事與局外科目。[年度分母](years.tsv) · [按場次拆分的分母](exams.tsv) · [試題型態](paper-types.tsv)

兩個來源也能補出單一來源缺失的資訊。民國 102 年公務人員升官等合併考試有 7 筆科目在查詢平臺欠類科標題，原先列為待複核。CSV 提供其工程、海運相關類科名，依同一套規則歸為局外，逐列保留兩側結果。在列入逐筆對照的 8,811 筆中，有 1,695 筆 CSV 提供更正答案連結，查詢平臺另列原答案 S。這些網址可以一併查證當年原始與更正版本。[逐筆對照](records.tsv)

民國 115 年這份政府匯出僅含 4 個場次、409 筆科目。固定索引另有 197 筆醫事、183 筆待複核科目屬於該 CSV 未涵蓋的整場考試，另列為 `exam_not_in_csv`。在雙方均已列出的場次中，醫事與待複核科目的單方缺卷計數均為零。[逐科範圍差異](portal-only.tsv) · [考畢試題固定索引](../index/README.md)

同日考選部原站回傳 HTTP 200，宣告 CSV 為 28,072,258 位元組。三次傳輸的連線均在途中重設，其中一次已讀取至少 15,708,160 位元組。本次僅有政府匯出具備完整檔案指紋，原站版本的列數與內容差異仍待完整取回後查核。[考選部原站 CSV](https://wwwc.moex.gov.tw/main/Exam/wHandExamQandA_CSV.ashx)

可用下列指令另取政府匯出或考選部原站 CSV。分別保存快取可保留兩種發布方式的位元組與指紋。重建本次快照須使用來源紀錄內的同一個 SHA-256。

~~~bash
python -m medbench.moex_opendata --fetch --source government_csv_export --cache data/moex/open-data/quality --out data/moex/opendata-quality
python -m medbench.moex_opendata --fetch --source origin --cache data/moex/open-data/origin --out data/moex/opendata-origin
~~~
