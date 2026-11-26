# 單題公告與答案卷對照

[items.jsonl](items.jsonl) 每行是一筆經查核的公告、訴願案件或更正表紀錄。可用逐題資料的 `item_id` 查到該題的決議、原文網址、證據位置及可取得的原答案表（S）、更正答案表（M）。沒有對照紀錄的題目，狀態一律為「尚未完成獨立公告比對」。[scope.json](scope.json) 記錄本批查核範圍與數量。

| 實例 | 可查證的結論 |
|---|---|
| 牙體技術學（四），`111110-109-0804-046` | 訴願決定書記載疑義會議維持 C。原答案表與更正表第 46 題均為 C。同一更正表另有第 1、17、18 題的變更，這三題的來源階段標為「同份更正表」，各自保留作答規則。 |
| 社會工作，`112110-103-0301-034` | 邊界案例。最初的新聞稿說明正在研議爭議。後續公告決議一律給分，可對回原答案 C、更正表的 `#` 與該題備註。 |
| 民國 90 年醫師第二階段檢覈筆試 | 外科學等科第 10 題可作答 A 或 B（`090040-001-2004-010`）；婦產科學等科第 13 題維持 A（`090040-001-3004-013`）。兩科的更正表均可回查。原公布答案的文字依據來自決定書，官方科目索引僅列 Q、M。 |
| 民國 99 年醫學（二），`099130-101-200-004` | 彙編記載初次維持 D，後續改為 C 或 D，更正表第 4 題備註可核對。CD 同時作答的處理仍待證據。 |
| 民國 86 年公共衛生學 | 彙編記載第 86 題可答 B 或 C。候選試卷總共 80 題，更正表的第 68 題記載 B 或 BC。兩種題號及答法各自保留，`mapping` 標記為 `documented_item_mapping_conflict`，`item_id` 留空。 |
| 民國 83 年基礎醫學（一） | 主管機關記載更正後重新評閱，欠缺題號。同期更正表有第 49、79 題。此案及兩個候選號碼保存在 `scope.json` 的 `unresolved_case_summaries`，未計入單題紀錄。 |

`documents` 保存決議及先前說明的角色、文號或公告 ID、日期、網址、雜湊與定位。文獻與候選卷的題號發生衝突時，候選文件的角色為 `conflicting_candidate_sheet`。`answer_sources` 分列曾核對的 S、M 檔及本次下載清冊的對應版本。`ledger_item` 包含可比對的原鍵、更正鍵、備註及解析規則。`compared_key_roles` 列出這次取得、且逐題紀錄能對應到已核查版本的答案表。若索引僅列 M，可單獨核對更正表，原公布答案仍依該案決定書或彙編的記載。若公告原件與清冊版本不同、原檔未到齊、逐題紀錄過期或規則不一致，`grid_comparison` 會分別指出原因。同一題可能有不同階段的紀錄，解讀時請同時查閱日期及文件種類。

對照程式以官方試卷代碼、題號與來源 SHA-256 定位，並比對已提取紀錄引用的答案檔版本。案件中披露的請求、初步說明與決議保留各自的出處。僅公布全國合計的公告保存在 [scope.json](scope.json)，不分配至單題。逐案整理的來源清單在 [decisions.json](../notices/decisions.json)。

民國 90 年兩題與 99 年醫學（二）第 4 題另有原件逐題摘錄。用 `item_id` 或 `decision_id` 可將摘錄連回本目錄的對照紀錄。每題保存 Q 上可見的完整題幹與四個選項、Q／M 的卷首代號、題號、M 對應儲存格與備註位置。90 年兩題逐字核對掃描圖，99 年第 4 題同時核對原生文字與圖面。摘錄中的給分規則只表達歷屆考試的處理方式，臨床審查仍待進行。[逐題摘錄及裁切區域雜湊](question-excerpts.json) · [原卷掃描的逐頁 OCR 草稿](../ocr/90/)

要從原始 PDF 重現一處摘錄，先對照 `Q.sha256` 或 `M.sha256` 核實原檔。使用摘錄記錄的 PyMuPDF 版本開啟該檔，以 `pdf_page - 1` 取頁，左上角為原點，單位是 PDF 點。以下以 `region` 表示該題的 `Q.numbered_question_and_options` 或 `M.number_and_answer_cell`。

```python
page = doc[region["pdf_page"] - 1]
crop = page.get_pixmap(matrix=pymupdf.Matrix(4, 4), clip=pymupdf.Rect(*region["bbox_pt"]),
                       colorspace=pymupdf.csGRAY, alpha=False)
assert hashlib.sha256(crop.tobytes("png")).hexdigest() == region["rendered_png_sha256"]
```

在 repo 根目錄執行 `python -m medbench.moex_rulings` 即可由已公布的官方索引、附件清冊、逐題紀錄與決議重建對照。使用其他批次時可分別指定 `--index`、`--manifest`、`--items`、`--decisions` 及 `--out`。
