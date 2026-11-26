# 掃描試卷的逐頁 OCR 草稿

每份 `<民國年>/<asset_id>.jsonl.gz` 對應一個官方附件，一行對應一個 PDF 頁面。適合以字詞搜尋線索，再開原卷核對。OCR 保持獨立，題數、答案與更正統計仍以逐題核對紀錄為準。

2026-11-26 的民國 81–82 年批次將「附件頁數」與「相同 PDF 去重後的來源頁數」分開統計，另列未辨識頁、低信心詞元、壓縮檔大小、實測耗時及工序並行數。[年度統計與驗證紀錄](batches/2026-11-26-roc81-82.json)

民國 90 年第一次醫師第二階段檢覈另收錄兩份各 4 頁的掃描卷。外科學等科第 10 題、婦產科學等科第 13 題已從原圖逐字核讀，另存題幹、四個選項、頁面裁切座標與答案表定位。OCR 有明顯漏字及錯欄，8 頁共 4,495 個詞元，3,296 個低於信心門檻 60。[民國 90 年逐頁草稿](90/) · [逐題原圖及更正表對照](../rulings/question-excerpts.json)

民國 81 年醫師考試解剖學第 1 頁採橫排，題幹與作答選項共用欄位。試讀時英文 *Axillary sheath* 前後的中文字容易辨識錯誤，各選項也容易串接。國文則從右至左直排，指定直排繁中模型後可讀出作文題「如何提昇國人生活品質」。兩份原卷的版面與字型不同，首頁判讀及採用的模型、分割模式列在 [layouts.tsv](layouts.tsv)。[解剖學原卷](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=081010&c=004&s=1004&q=1) · [國文原卷](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=081010&c=004&s=c011&q=1)

## 如何核對一處文字

- `source` 指向官方附件 URL 及原檔 SHA-256。`pdf_page` 從 1 起算。`rendered_png_sha256` 識別本次以指定 DPI 產生的灰階頁面 PNG。
- `text` 依 OCR 引擎的讀序串接。`lines[].words[]` 保留各詞文字與方框 `bbox_pt = [左, 上, 右, 下]`。以顯示後的 PDF 頁面左上角為原點，單位為點（1/72 英吋）。遇到錯欄、漏字或藥名混淆，可按頁碼與方框找回原圖位置。
- Tesseract TSV 引擎提供逐詞 `confidence`。本批把分數低於 60 的詞列入 `low_confidence_word_count`，供複核排序。所有 OCR 頁面皆為 `pending_human_review`，高分也可能辨錯。PyMuPDF 內建 OCR 不提供這項數值，對應欄位留空。兩種引擎的輸出均保留版本與模型雜湊。
- 有足夠既有文字層的頁面標為 `existing_text_layer`。掃描頁辨識不到字時，記為 `no_text_recognized`。遇到引擎錯誤則記為 `ocr_error` 並於下次重試。

## 續跑

安裝專案的 `build` extra。若要取得逐詞信心值，可安裝 Tesseract CLI 並選 `--engine tsv`。將固定 revision 的語言模型檔放在 `data/moex/tessdata/`。程式核驗雜湊，預設使用 `layouts.tsv` 中各卷的指定語言和分割模式。未登記的卷採 `chi_tra` 與自動版面分析，待抽查後可增列。PyMuPDF 內建路徑採用其預設分割策略。[官方固定版語言模型](https://github.com/tesseract-ocr/tessdata_fast/tree/87416418657359cb625c412a48b6e1d6d41c29bd)

```powershell
python -m medbench.moex_ocr --manifest datasets/moex/archive/files.tsv --year 81 --engine tsv
python -m medbench.moex_ocr --manifest datasets/moex/archive/files.tsv --engine tsv
```

已有本機下載快取時，可以先驗證快取並輸出工作清冊，再更新兩個年度。第一行只核對原檔，不會發出新的下載請求。第二行以來源 PDF 與模型的 SHA-256 接續先前的頁面快取。

```powershell
python -m medbench.moex_archive --scopes medical,boundary --limit 0 --verify --manifest data/moex/archive/ocr-local.tsv
python -m medbench.moex_ocr --manifest data/moex/archive/ocr-local.tsv --year 81 --year 82 --engine tsv
```

同一份醫事考試 PDF 有時列在多個類科。各官方附件的輸出各自保留網址，完全相同的 PDF 位元組可沿用已核對的版面設定。不同年度亦有直排申論、英文題本與雙頁合掃，請以詞框和原始影像核對讀序。[版面設定與來源雜湊](layouts.tsv)

預設處理已驗證的 Q 題本。可用 `--role S --role M` 指定答案附件，或用 `--paper` 限定試卷。每頁成功後即存入 `data/moex/ocr-pages/`，下次使用相同來源及 OCR 設定會接續執行。先前已辨識的頁面可重用於同一來源雜湊的不同附件。
