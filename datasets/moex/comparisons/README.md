# EMPEC 與考選部原卷的逐題比對

Zheheng Luo 的 EMPEC 已整理臺灣多種醫事人員國考單選題。這次把原作者的兩次發行分開查核，並將 225 道可在指定官方樣本唯一定位的題目連回原卷與答案。可用這份對照標記已公開訓練資料的重疊，或回查歷屆給分規則。

| 發行來源 | 實際查核範圍 | 完整吻合 | 僅題幹吻合 |
| --- | --- | ---: | ---: |
| 作者 GitHub 所連 ZIP | 繁體 JSON 中民國 112 年的全部 2,790 列，對照 2023 年第一次考試醫學（二）、醫學（三）、藥物治療學三卷共 260 題 | 223 | 18 |
| Hugging Face `train` 首頁 | 首 100 列中標記 2023 年的 8 列，對照上述三卷 | 3 | 0 |
| Hugging Face `train` 首頁 | 首 100 列中標記 2024 年的 2 列，搜尋本庫民國 113 年 158 卷中具備題幹及四個非空選項的 7,952 筆 | 1 | 1 |

兩個版本包含共同題目。逐列對照共 246 筆，其中有 227 筆完整吻合，對應 225 個不同的官方題號。2023 年原始 ZIP 的其餘 2,538 列在這三卷沒有完全相同的題幹，11 列的 A–D 標籤無法依本次規則切開。這些數字的分母限於表列範圍。三卷依 2023 年 Hugging Face 首頁可觀察到的科目選取，整庫覆蓋率仍待查核。

## 同一名稱下的版本

- GitHub 作者說明記載 81,761 題，並報告在 2023 年第一次考試的 2,840 題上評估模型。實際下載連結中的 ZIP，繁體 JSON 可讀出 **81,694 列**，年份標籤涵蓋 102 至 112，末年的 `112` 標籤有 2,790 列。ZIP 同時附有簡體檔。這份比對使用繁體檔的原始列序。[作者 GitHub 固定版說明](https://github.com/zhehengluoK/Examinations-for-Medical-PErsonnel-in-Chinese/blob/eed024cc566186dd24dce4b497b98faf742971ba/README.md) · [作者公開下載](https://drive.google.com/file/d/1PgXcl-7l2PWAevJeXkWpTN_WqBs-ea9W/view)
- 作者在 Hugging Face 的固定版本列出 `train` 149,603、`validation` 200、`test` 8,000，合計 **157,803 列**，資料卡標示 CC BY-NC-ND 4.0。獨立題數仍需跨列、跨 split 去重。這次直接讀取公開 `train` 瀏覽器第 0–99 列，實見 2011–2024 年；完整三個 split 的逐列分布與重疊仍待核對。[作者 Hugging Face 固定版資料卡](https://huggingface.co/datasets/KenLuo/EMPEC/blob/5aeabb033531936168ad84a0d5ff761911d97294/README.md) · [公開訓練列](https://huggingface.co/datasets/KenLuo/EMPEC/viewer)

## 如何回查

[逐列對照](empec-matches.tsv) 的 `release`、`split`、`row_index_0` 指向上游資料列，索引從 0 開始。`official_paper_id` 可連結[官方檔案清單](empec-official-sources.tsv)，再按 `official_item_id` 末三位的題號與 `question_pages` 查閱試卷。所有 PDF 頁碼從 1 開始。Q 是試卷，S 是原公布答案，M 是更正答案。空白欄位表示該筆沒有對應的已擷取證據。SHA-256、各 split 列數、年度分布及這次官方比對範圍見[統計及版本](empec-summary.json)。

比對將作者繁體 `question` 依空白後的 `A.`、`B.`、`C.`、`D.` 依序切成五欄。對兩方的題幹和各選項分別套用 Unicode NFC 並去除空白。每一欄文字與選項順序皆相同，且同年官方樣本只有一題符合時，才標記 `unique_full_match`。題幹相同但選項有差異者保留為 `stem_only_candidate`。兩個 `fields_sha256` 都取五個正規化字串組成的緊湊、UTF-8 JSON 陣列（無 ASCII 跳脫）。這項比對只核對可以擷取的文字和卷內答案，圖像及臨床時效仍需另外審查。

- 在原始 ZIP 的 223 筆完整吻合中，220 筆字母答案符合官方單選規則。另 3 筆在 EMPEC 各有一個字母，但官方 M 檔已將該題改為一律給分，分別是醫學（二）第 69 題、醫學（三）第 47 題，以及藥物治療學第 45 題。對照表保留兩版官方欄位、各自頁碼與給分規則。[官方檔案及雜湊](empec-official-sources.tsv)
- Hugging Face `train` 第 55 列完整吻合 2024 年物理治療學概論第 74 題。第 65 列吻合核子醫學診療原理與技術學第 65 題的題幹與 A、B、D；其 C 選項擷取文字相差一個表示上標的 `^`，目前保留候選狀態。[兩筆原卷定位與欄位指紋](empec-matches.tsv)
