# EHRNavigator 的 Yale 病歷問答索引

[下載逐題 TSV](questions.tsv)。YNHHQA.txt 共 100 個編號問題，去除題號後有 99 種逐字題文。**第 67 與 68 題題文相同**，兩筆各保留原始行號。此索引可對照來源、檢查重複，以及在切分時將相同題文放在同一組。[作者的固定版本](https://github.com/BIDS-Xu-Lab/EHRNavigator/blob/be9d5181272bee487b78404ce60a849b7d24a419/YNHHQA.txt)

| 欄位 | 定義 |
|---|---|
| `source_line`、`question_number` | 從 1 開始的原始檔實體行號，以及作者給的十進位題號。此版兩欄均從 1 到 100。 |
| `question_start_byte`、`question_end_byte` | 原始 UTF-8 檔案的位元組範圍，從 0 開始，含起點、不含終點。扣除行首數字、句點、其後一個 ASCII 空格及換行，其餘位元組逐字保留。 |
| `duplicate_group` | 題文位元組完全相同時，填入該組最小的原始題號。唯一重複組值為 67，其餘列留空。 |
| `question_sha256` | 上述位元組範圍的 SHA-256。保留大小寫、Unicode、標點及內部空白，無文字正規化。 |

## 任務與可審查範圍

原文圖 6 將 Yale 的醫師編寫任務分成三類，包括檢驗數值的時間趨勢、用藥劑量或時間，以及結合檢驗與用藥資訊的問題。兩名具醫學訓練的評審盲評 100 例，初判 97 例一致，另 3 例經討論取得共識。作者報告模型在此條件下答對 85%。公開問題檔只有編號與題句，無逐題類別對照、病歷、模型回答、參考答案或評分。此索引可定位問題。若要重現每例判定仍需要獲准使用對應病歷和評分依據。[原文 Results、圖 6 與 Data availability](https://pmc.ncbi.nlm.nih.gov/articles/PMC13796827/)

研究論文採 CC BY-NC-ND 4.0。作者固定提交的根目錄未列授權檔，問題文字的重發與翻譯權仍待確認。作者亦說明 Yale 病歷受隱私及機構規範所限。此處僅發布來源定位與指紋，供日後授權查核及臨床審題。[作者庫檔案與聲明](https://github.com/BIDS-Xu-Lab/EHRNavigator/tree/be9d5181272bee487b78404ce60a849b7d24a419) · [論文授權](https://doi.org/10.1038/s44401-026-00149-1)

## 重建

來源提交為 `be9d5181272bee487b78404ce60a849b7d24a419`。固定檔案大小 10,665 bytes，SHA-256 為 `fd9e6d8e2c99de7d1230a1dd76e26b5db8152cf94dcb3a05520c5ee8975fa003`。下載原檔至 `data/discovery/ehrnavigator/YNHHQA.txt`，在儲存庫根目錄執行以下指令。第一行重建 TSV，第二行核對已保存的索引。兩者都核對來源指紋並回報 100 個原始題號、99 種題文。[固定版原始檔](https://raw.githubusercontent.com/BIDS-Xu-Lab/EHRNavigator/be9d5181272bee487b78404ce60a849b7d24a419/YNHHQA.txt) · [重建程式](../../../scripts/prepare_ehrnavigator.py)

```sh
python scripts/prepare_ehrnavigator.py data/discovery/ehrnavigator/YNHHQA.txt
python scripts/prepare_ehrnavigator.py data/discovery/ehrnavigator/YNHHQA.txt --check
```
