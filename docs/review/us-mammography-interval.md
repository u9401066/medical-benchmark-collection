# 同一病例、兩個乳房攝影篩檢間隔

美國某診所以一名 46 歲、一般風險且沒有乳房症狀的女性測試提醒規則。她前次例行乳房攝影結果正常，距今 12 個月。兩題使用相同病例與查核日（2026-11-26），請審查者檢查診所採用的指引範圍如何影響答案。

| 題目 | 預期作答 | 閱卷時請留意 |
|---|---|---|
| [同時符合 ACS 與 USPSTF](../../drafts/mbc-us-mammo-0001.json) | ACS 對這個年齡層建議每年篩檢，現在到期。USPSTF 建議每兩年篩檢，約再過 12 個月到期。兩者無共同建議的固定間隔。 | 須將兩個週期各自歸到正確機構，說明它們對同一提醒日期的影響。只答「每一到兩年」會掩蓋分歧。 |
| [診所指定採用 USPSTF](../../drafts/mbc-us-mammo-0002.json) | 每兩年一次，約再過 12 個月到期。 | 在機構已指定時，須能依該機構給出明確的提醒時間。 |

ACS 官網末次修訂日期為 2026-07-23。一般風險段落分別列出年齡層，45 至 54 歲採年度篩檢。ACS 原始指引將這個間隔列為 *qualified recommendation*。請將評分限於指引所列的例行週期，避免延伸為每位女性必須採用的個人處置。[ACS 現行說明](https://www.cancer.org/cancer/types/breast-cancer/screening-tests-and-early-detection/american-cancer-society-recommendations-for-the-early-detection-of-breast-cancer.html) · [ACS 原始指引](https://doi.org/10.1001/jama.2015.12783)

USPSTF 在 2024-04-30 公布最終建議。請核對摘要表內 40 至 74 歲的每兩年篩檢，以及臨床摘要表所列的適用對象與排除條件。兩題的前提均符合上述兩個機構的族群，提問的是一般例行篩檢提醒。[USPSTF 最終建議](https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/breast-cancer-screening)

**醫師審題。** 同一病例家族含兩題，每題均有臺灣繁中及美式英文表述；適用地區皆為美國。四個版本均待具名審查，限公開開發。請依題號與語言分別記錄決議，並指出有問題的病例條件、來源定位或中英文措辭。兩題皆為第 1 版，內容 SHA-256 前 12 碼依序為 `81db5bb9bcb0` 與 `632dabc01b6b`。下次人工複審預定 2027-02-26。兩方分歧已列入待裁定佇列，即使其中一份來源的文字保持穩定，仍須依指引更新重新判斷。[審查與匯出規則](../editorial-workflow.md)

**使用範圍。** 病例、雙語題文、答案及評分條件由本專案撰寫。公開的來源紀錄保存原頁連結、定位與指紋。ACS 網頁文字、圖表等內容的重用依其使用政策申請；USPSTF 頁尾的〈Copyright and Source Information〉說明其原件重製條件。[ACS 內容使用政策](https://www.cancer.org/about-us/policies/content-usage.html) · [USPSTF 來源與著作權](https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/breast-cancer-screening)

本家族監測 ACS 一個範圍與間隔段落、USPSTF 兩個表列。三處的正文指紋均與 2026-11-26 重新擷取的結果吻合。草稿中的 `source_sha256` 識別當次取得且經 HTTP 內容解碼的完整 HTML，`passage_sha256` 識別正規化空白後的指定段落。ACS 另留 gzip 傳輸資料的 `wire_sha256`。[本批來源核對紀錄](clinical-watch-2026-11-26-us-mammo.json)
