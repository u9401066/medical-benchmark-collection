# 內政部即時登記查詢快照

2026-11-26 查詢內政部「人民團體數位櫃檯」，選「社會團體」，在團體名稱輸入「學會」，不限制團體狀態或成立日期。官網回報 4,064 筆，使用「全選所有」及「ODS 檔」匯出，實得 4,064 個不重複名稱。全表涵蓋各種學術、文化、宗教、教育等團體，可用來比對組織登記及篩選醫學領域。內政部表示主管之人民團體資料會依異動更新。[官網原查詢](https://grouptw.moi.gov.tw/SearchGroup?IsQuery=true&tab=little&Q_Type=%E7%A4%BE%E6%9C%83%E5%9C%98%E9%AB%94&Q_Name=%E5%AD%B8%E6%9C%83)、[內政部說明](https://www.moi.gov.tw/News_Content.aspx?n=15255&s=263489)、[4,064 筆完整登記表](live-registry.tsv)

| 官網原狀態 | 名稱含「學會」之查詢結果 |
| --- | ---: |
| 已立案 | 3,604 |
| 解散 | 369 |
| 已准籌 | 76 |
| 立案審查中 | 9 |
| 籌組審核中 | 6 |

4,064 筆中有 8 筆的當次登記名稱實際未含「學會」，均保留原列並標為 `literal_name_match=no`。成立日期有 84 筆空白，全表最晚載至 2026-11-08（立案審查中），其中「已立案」最晚載至 2026-10-24。302 筆立案證書字號空白，其中 89 筆的狀態為已立案。兩個非空證號分別出現在兩個不同名稱，故比對時保留原名稱、所屬快照與列號，證號保留前導零。用本專案的名稱正規化函式與兩份舊版全國名冊合併比對，4,064 個現名中有 529 個查無同名，包括 431 個已立案名稱；此數亦涵蓋非醫事領域。[舊版快照](registry-snapshots.json)

## 交叉查詢

| 同日另查的社會團體名稱 | 官網／ODS 筆數 | 狀態 | 與 4,064 筆同名 | 本次 ODS 位元組及 SHA-256 |
| --- | ---: | --- | ---: | --- |
| [醫學會](https://grouptw.moi.gov.tw/SearchGroup?IsQuery=true&tab=little&Q_Type=%E7%A4%BE%E6%9C%83%E5%9C%98%E9%AB%94&Q_Name=%E9%86%AB%E5%AD%B8%E6%9C%83) | 391／391 | 已立案 375、解散 9、已准籌 7 | 391 | 42,389　`72c7bcaaf4dbe6b50ee5acc14c690566b6ff182f7f56088e812f1412475f7094` |
| [醫師協會](https://grouptw.moi.gov.tw/SearchGroup?IsQuery=true&tab=little&Q_Type=%E7%A4%BE%E6%9C%83%E5%9C%98%E9%AB%94&Q_Name=%E9%86%AB%E5%B8%AB%E5%8D%94%E6%9C%83) | 16／16 | 已立案 14、解散 2 | 0 | 8,305　`75efcc1408026643eaef5cae7e9736e8af37596d051d04c42f9aafcd63b6bcce` |

「醫師協會」另存完整表，其中包含三個獸醫相關團體及一個已解散的人類醫學團體。此查詢使用連續詞「醫師協會」，專業協會也可能以其他用語命名。兩個查詢均選社會團體，另有專門的職業團體查詢類別。地方登記資料見各縣市名冊。[16 筆補充表](live-physician-associations.tsv)、[地方名冊涵蓋範圍](local-coverage.md)

## 檔案及重現

主查詢 ODS 原始大小 390,878 位元組，SHA-256 為 `59b2680b941b08790d01705194cb1c23c961d448f2466d728f523f53705af456`。匯出版有一張 `Sheet 1`，第 1 列是表頭。`seq` 從第一筆資料起算，`locator` 指向含表頭的實際工作表列號。`registry_id` 是官方「立案證書字號」，`status` 保留原狀態，`established_roc` 和 `established_date` 分別為原始民國日期及換算後的公曆日期。本表保存團體名稱、團體類型、狀態、證書字號與成立日期，另附查詢和來源定位。未保存有姓名、電話及地址欄位的原始 ODS。

腳本讀取公開查詢回應，再於同一個瀏覽工作階段提交網頁提供的全選 ODS 匯出表單。在記憶體計算原檔指紋，核對工作表筆數與官網分母後才寫入 TSV。以下命令輸出新的快照。相同查詢重新產生的 ODS 可能有不同位元組指紋；本次重跑「醫師協會」時 16 筆的五個登記欄位與順序全部相同。[擷取腳本](../../scripts/tw_society_live_register.py)

```powershell
python scripts/tw_society_live_register.py --term 學會 --output data/tw-societies/live-societies-new.tsv
python scripts/tw_society_live_register.py --term 醫師協會 --output data/tw-societies/live-physicians-new.tsv
```
