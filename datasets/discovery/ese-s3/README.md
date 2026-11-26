# 牙髓病學 S3 指引題的重測附表

2026-11-26 核對 PMID `43069390` 的三份公開附件。作者依 European Society of Endodontology 的 S3 指引出題，包含 20 道選擇題、30 道是非題。論文資料聲明指向補充材料，出版頁列保留權利。此處發布檔案指紋、重算程式與聚合結果。題目、答案鍵和逐格正誤由原發布頁提供。[論文、授權及補充材料](https://link.springer.com/article/10.1007/s10266-026-01631-w)

| 上游檔案 | 可核對的位置 | SHA-256 |
|---|---|---|
| Supplementary Material 1 | DOCX 第一表第 2–51 列，題號欄和第 7 欄逐題答對數。[原始題本](https://static-content.springer.com/esm/art%3A10.1007%2Fs10266-026-01631-w/MediaObjects/10266_2026_1631_MOESM1_ESM.docx) | `6d089bcdca11a22649d3499d74085ce88abe3c6bc0711ca6a3cad30166f9e801` |
| Supplementary Material 2 | XLSX 第一工作表 `A1:BU51`。第 1 列定義模型、測試日及帳號，`B2:BU51` 為逐格正誤。[原始工作簿](https://static-content.springer.com/esm/art%3A10.1007%2Fs10266-026-01631-w/MediaObjects/10266_2026_1631_MOESM2_ESM.xlsx) | `b14aa9093710fdf7f7e3d72c74329bc3cb11e4ff8113d36fbeffdc455f2465d2` |
| Supplementary Material 3 | 作者的分析程式，可搜尋 `Cell = 'D'` 定位編碼說明。[原始程式](https://static-content.springer.com/esm/art%3A10.1007%2Fs10266-026-01631-w/MediaObjects/10266_2026_1631_MOESM3_ESM.txt) | `1de16244bf026ab029b83552c8b4e3ace35c9b08f08afff3b8bbabdede28c037` |

以題號 `A1`–`A20`、`B1`–`B30` 連接題本與工作簿。工作簿另有 25 列備註。第 7 天第 3 帳號的一個模型名拼寫為 `CHAGTGPT`，重算時校正為 `CHATGPT`。工作簿的 `D` 表示答對，`Y` 表示答錯。逐題答對數 50／50 與 DOCX 記載相符。8 個模型 × 3 天 × 3 帳號 × 50 題，共 3,600 筆正誤，其中 3,370 筆答對（93.61%）。

| 固定條件下比較 | 配對數 | 兩次皆對 | 對→錯 | 錯→對 | 兩次皆錯 |
|---|---:|---:|---:|---:|---:|
| 同題、模型、帳號，第 1 天→第 7 天 | 1,200 | 1,118 | 0 | 0 | 82 |
| 同題、模型、帳號，第 1 天→第 30 天 | 1,200 | 1,116 | 2 | 18 | 64 |
| 同題、模型、日期，第 1→第 2 帳號 | 1,200 | 1,096 | 32 | 28 | 44 |
| 同題、模型、日期，第 1→第 3 帳號 | 1,200 | 1,105 | 23 | 13 | 59 |

每列比較反覆使用同一批 50 道題。第 1 天與第 7 天的正誤碼逐格相同，實檔能查到的粒度止於正誤。作答選項、理由、引用及獨立重測過程均待其他材料核對。為量測總分相同時的改答及理由變動，本專案分別保存所選選項、原始回答與後端版本。[聚合結果](aggregate.json) · [配對評估與重跑設計](../../../docs/temporal-evaluation.md)

從原發布頁取得附件 1、2，安裝 `.[report]`，在專案根目錄執行以下指令。程式先核對兩個檔案的 SHA-256，再印出聚合 JSON。

```sh
python scripts/audit_ese_repeats.py path/to/10266_2026_1631_MOESM1_ESM.docx path/to/10266_2026_1631_MOESM2_ESM.xlsx
```
