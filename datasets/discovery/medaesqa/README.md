# MedAESQA 句子與引文索引

[下載壓縮 JSONL](sentences.jsonl.gz)。每列對應作者標註的一個機器回答句子。索引涵蓋 40 個問題、每題 30 個模型回答、共 5,162 句。另有 40 份專家撰寫的參考答案可在原始 JSON 查閱。來源為 Deepak Gupta、Davis Bartels 與 Dina Demner-Fushman 於 2025-04-15 封存的 `medaesqa_v1.json`，OSF 檔案 revision 1。OSF 專案採 CC0 1.0 Universal。引用文獻的全文與片段依各來源條款取用，本索引只散布定位與標籤。[OSF 原始檔與版本](https://api.osf.io/v2/files/67fec8ed8d5db3b196c106bc/versions/1/) · [OSF 專案](https://osf.io/ydbzq/) · [原始研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC12179289/)

## 如何把一列對回原始回答

`question_id`、`model_key`、`answer_sentence_id` 三個來源字串共同識別一句，前置零會保留。從原始問題的 `machine_generated_answers[model_key]` 取 `answer` 得到整份回答，從 `answer_sentences[sentence_index]` 取出句子標註；`sentence_index` 由零開始。本版 40 個問題 ID 均相異，句號在各自的回答內均相異，三個識別欄位皆無空值。

| 索引欄位 | 定義 |
|---|---|
| `answer_sha256`、`sentence_sha256` | 原始回答與標註句子各自以 UTF-8 編碼的 SHA-256，保留原來的空白及標點。 |
| `match_count`、`start`、`end` | 在原始回答逐字搜尋標註句子，計入重疊匹配。唯一匹配時，`answer[start:end]` 還原原句。邊界依 Unicode 碼點由零開始，含起點、不含終點。 |
| `answer_sentence_relevance` | 作者原標籤。required 3,958、borderline 243、unnecessary 698、inappropriate 19，另有 244 句為 `null`。 |
| `citation_assessment` | 保留作者原順序及重複列，1,149 句的原始值為 `null`。每筆保存作者所填的 PMID 字串、原標籤 `evidence_relation`，以及原檔是否含非空字串片段 `has_evidence_excerpt`。 |

5,148 句能唯一逐字定位。另有 12 句出現多次（2 句有兩處、3 句有三處、7 句有四處），2 句無逐字匹配。這 14 句的兩個位置均為 `null`，仍然可以用模型鍵、原句號與陣列序號找回作者的句子標註。

## 論文與資料檔的分母

| 分析單位 | 2025-06-19 論文 | 2025-04-15 OSF revision 1 實檔 |
|---|---|---|
| 完整模型回答 | 圖 3 前述有 1,108／1,200 份可接受 | `is_answer_accurate` 是 `yes` 的有 1,102／1,200，另 98 份為 `no`。 |
| 有支持的引文 | 同段報告 5,489／8,111，表 5 列機器回答的引用總數 8,111 | `citation_assessment` 展開後共有 9,611 筆，包含 6,490 筆 `supporting`。按同句同 PMID 歸戶後，有至少一筆支持的共 5,489／8,124 組。 |
| 證據片段 | 表 5 列 7,651 | 7,651 筆引文標註含非空字串片段，另 1,960 筆為 `null`。 |

8,124 個「題號、模型、句號、PMID」組合中，390 組同時出現不同關係標籤。要求該組所有標籤都是支持，則只剩 5,116 組。使用「至少一筆支持」可重現論文的分子 5,489，分母仍相差 13 組。公開資料未交代可讓這兩個分母或回答可接受數完全對上的轉換規則，索引完整保留原檔所有標註。[原文 MedAESQA Dataset Analysis、表 5 與圖 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC12179289/)

9,611 筆原始關係為 `supporting` 6,490、`not relevant` 1,551、`neutral` 972、`invalid citation` 409、`contradicting` 189。所填 PMID 在原檔均為十進位數字字串。409 是作者對引用的原標籤，不能據此判定文獻虛構。本次未逐筆查證 PubMed 記錄或引文內容。

## 醫師複核與切分

審查者可用索引選定有分歧或缺少片段的句子，回到原答案閱讀完整脈絡，再核對引用文獻、適用族群及查核日是否已有更新指引。人工判定應另存編審者、證據版本、定位與日期。這一批保存原研究標註，尚待本庫醫師核准。切分訓練、開發及評測資料時，以 `question_id` 為單位，讓同題的 30 份回答和其句子留在同一分組。

## 重建與驗證

從固定版本下載原始檔至本機 `data/discovery/medaesqa/medaesqa_v1.json` 後，在儲存庫根目錄執行。第一行重建索引，第二行以原始檔重新比對解壓後的完整 JSONL。程式固定列序、欄位順序、換行及 gzip 標頭時間，壓縮時捨去檔名。每次執行都會輸出分母與標籤統計。[OSF 固定版本下載](https://osf.io/download/9d3qs/?revision=1) · [重建程式](../../../scripts/prepare_medaesqa.py)

```sh
python scripts/prepare_medaesqa.py data/discovery/medaesqa/medaesqa_v1.json
python scripts/prepare_medaesqa.py data/discovery/medaesqa/medaesqa_v1.json --check
```

| 檔案 | SHA-256 |
|---|---|
| 作者原始 JSON（7,276,948 bytes） | `a062742c1678b4379121ad030a06bda574afd376f331df41575938dd9849c383` |
| 索引 JSONL 解壓後 | `e3b14553c36f875ec1ed549a85dab8a3fff706e8df728a786cb65cda581030ea` |
| 本庫發布的 gzip（378,189 bytes） | `8a45aa4f495bad9ebfa3fda5700b84cda892fa339995a5299068929e4777e08c` |
