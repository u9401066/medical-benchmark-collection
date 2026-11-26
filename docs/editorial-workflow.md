# 編題、在地化與臨床複審

每一批更新都要能回答三個問題：這份評測測什麼能力？在哪個語言與醫療情境下，答案成立？其他人能否依紀錄重現當時的判定？[現有題庫與待接入評測](../datasets/catalog.md)

## 收到一個來源時

| 來源 | 第一份產物 | 接入評測前的查核 |
|---|---|---|
| 作者發布的 benchmark | 目錄條目，連結原文、資料卡與評分程式 | 固定版本與 split，查清題文、答案、圖像與翻譯的使用條件。記下原作者的指標與分母，以及本專案實際採用的子集。 |
| 考古題、病例教學或指引 | 來源紀錄，標明出題機構、地區、年份、題號或章節 | 查找官方答案與更正公告。遇到缺圖、承上題或歷史答案，只能在取得作答所需的完整資訊後當作獨立新題。 |
| 醫師與編者共創 | 具概念 ID 的原創草稿，標明欲測能力與受試對象 | 用虛構病例寫題，為答案及容易混淆的選項找到根據。區分定義或建議的直接出處，以及解釋其臨床意義的研究。 |

若只能確定一項資源存在，先登錄名稱、作者與來源連結。累積一批時，按專科、任務、語言、就醫場域盤點缺口，例如是否只有英文選擇題，或是否缺少需要檢索、判讀影像及處理不確定性的病例。以缺口決定下一批收集方向。

## 雙語題如何送審

1. **固定臨床問題。** 每個概念配置一個穩定 ID，每個語言版本另有 ID。記錄原創或改編、來源版本、題目修訂號、適用人群、地區、指引版本及查核日期。保留答案、理由和可定位的證據，例如 PMID／DOI 搭配表格、列、段落或建議編號。下載檔案時記錄檔案雜湊；只取得片段時，明列片段範圍與正規化方式。
2. **逐項比對兩版。** 核對時間、單位、數值、否定詞、選項含義與正解。臺灣繁中採用當地病歷及檢驗慣用語，美式英文依美國臨床書寫慣例。語言和醫療管轄區分別記錄。若健保給付、藥品可近性或不同地區指引會改變正解，另立地區情境與答案，標記為不可直接配對比較。
3. **留下醫師判定。** 維護者在題目紀錄或 PR 中以「題目 ID／修訂號、兩版是否成立、應改文字、依據」回覆。編者登錄審查者、日期、決議和下次應重查的條件。遇到兩個可接受答案或互相衝突的指引，先列出各自成立的條件，再請醫師裁決或退回重寫。
4. **處理過時題。** 同時保存原年份及官方答案、新證據的版本與定位、改答案的理由和生效版本。若一題已在正式批次計分，於新版修訂或撤題，列出受影響的批次與分母。歷史成績繼續引用當時的題目版本。

公開討論過的題組歸入開發集。預留獨立評估集時，同病例、同概念、不同語言與近似改寫分入同一 split。做雙語比較時每個概念計一對，並列出兩版皆對、皆錯、僅繁中對與僅英文對的數量。

## 本批可供複審的兩個案例

**腎臟科雙語原創題** `mbc-ckd-0001` 測量讀取 eGFR 與 UACR 後能否正確記錄 CKD 分級。兩版共用數值與測量間隔。答案依據定位至 KDIGO 2024 印刷頁 S137 的表 1–3。草稿內附醫師審查欄位，可直接對照兩版用語與證據。[雙語草稿與文獻定位](../drafts/mbc-ckd-0001.json)

**國考承上題** `twmed_md-113020-302-11-003` 詢問前題四種量表中有幾種包含年齡。113 年第一次醫師（二）醫學（三）原卷第 1 頁第 2 題以表格列出四個名稱，第 3 題沿用該表。`twmed-v1` 的建置紀錄將第 2 題標為 `table or formula` 並排除，第 3 題仍在題庫。審查狀態為待處理，可評估將兩題編成共用題組，或從新版獨立單題分析中排除第 3 題。既有結果可依原題 ID 追溯。[考選部原卷，第 1 頁](https://wwwq.moex.gov.tw/exam/wHandExamQandA_File.ashx?t=Q&code=113020&c=302&s=11&q=1) · [排除紀錄](../datasets/twmed/build_log.json) · [原卷 SHA-256](../datasets/twmed/sources.tsv)

同一版 32,528 筆原始紀錄中，有 177 題標記 `meta.depends_on_previous`。以同一考試、類科、科目及題號減一比對原始 ID，其中 38 題缺少緊鄰前題，列入優先複審。即使相鄰題號都在題庫，目前逐題提示仍可能缺少實際共用的病例。判讀時應回看原卷確認病例起點、圖表與作答所需條件。[38 題複審清單](review/twmed-v1-context.tsv)

### 用同一案例測 agent 找證據

可將下列指令單獨提供給受測 agent，允許查找考選部公開試卷，並記錄實際取得的來源、作答及查找失敗原因。

> 請查臺灣 113 年第一次醫師（二）醫學（三）第 3 題。若系統只顯示第 3 題的文字和選項，是否足以作答？請依原卷逐一列出本題所指的四個量表，附上可直接核對的官方試卷、頁碼和題號。

評分者逐項記錄是否達成，並保留答案中的對應片段。

| 可觀察行為 | 判定依據 |
|---|---|
| 辨識題幹依賴 | 說明單看第 3 題無從知道「上述四種量表」是哪四種。 |
| 找回所需資料 | 正確找出 APACHE II、BODE、International Prognostic Index（IPI）及 TIMI Risk Score。英文全名或無歧義的縮寫均可接受。 |
| 提供可核對的證據 | 引用考選部該場次原卷第 1 頁，指出第 2 題提供量表與對象、第 3 題承接該表。 |

這是公開開發案例。成績解讀限於「辨識缺少脈絡並找回指定來源」。若要測量臨床建議的正確性，須另訂對應病例的臨床決策、證據與安全性評分準則。

## 分批發布

### 審查紀錄與資料匯出

醫師可從公開審查本選題，同頁閱讀歷史問法、當期題文、編者擬答、主張及第一手證據位置。直接在對話回覆題號、語言、修訂版、決議及理由即可。[2026-11-26 雙語審查本](review/queue-2026-11-26.md)

醫師可直接在討論中用「案例與語言／原句／核准、修訂或撤回／理由／證據定位」回覆。編者保存原始版本，將經確認的判定記入 `docs/review/decisions.jsonl`，每行為一個決議。Git 保留修前／修後差異。同一病例的翻譯或重寫沿用 `family_id`，資料用途由整個病例家族共同決定。

執行 `python -m medbench.curation queue` 可以看到待審版本與內容 SHA-256。決議欄位包含 `variant_id`、`revision`、`content_sha256`、`reviewer`、`date`、`decision`（`approve`／`revise`／`withdraw`）、`reason`、`evidence_locator`、`checked` 與 `approved_uses`。同一語言版本以最新決議為準。核准時要能指出已檢視的臨床內容與語言（`clinical`、`language`）。修改題幹、答案、依據、評分條件或資料用途後，舊核准會顯示 `stale_review`。

現行微調資料用 `clinical-train` 匯出，公開開發案例與保留評估案例分別用 `clinical-development` 和 `clinical-evaluation`。匯出須符合資料權利、病例分組和該語言版本的醫師決議。較早期的 `train`、`development`、`evaluation` 模式供舊版重現，資料再利用仍依原授權。輸出含提示、參考回答、評分準則、文獻與修訂識別碼。審查進度以 `python -m medbench.curation queue` 為準。

新加入的非考題案例請 agent 在讀書會檢查一項對 SPRINT 的說法。繁中與美式英文各有自由作答與三項評分準則，原始依據可定位至 PMID 26551272 的摘要 Methods 第一句。後續可分別評閱來源查找、對收案條件的判讀、對外推適用性的說明。[雙語草稿](../drafts/mbc-evidence-sprint-0001.json) · [SPRINT 原始報告](https://pubmed.ncbi.nlm.nih.gov/26551272/)

每批以 Git commit 或 tag 固定題目與來源清單，記錄新增、修訂、撤題及待審的 ID。只有通過該項臨床與語言審查的自編題才加入指定評測組。執行時保存題庫雜湊、模型與提示版本、工具與檢索範圍、評分規則、樣本數及失敗數。工具呼叫成功、證據支持答案，以及臨床判斷正確，是三個分別報告的結果。

考選部複審清單中的 4 道醫師題保留在[暫停交接](../datasets/moex/RESUME.md)。當期的來源蒐集、時效複審與評估進度列在 [roadmap](roadmap.md)。

## 臨床時效維護

需要集中回填時，可用 `medbench.review_packet` 產生 JSON 工作表。編者將具名決議記入各列的 `review`。只完成一個語言就填該版，其餘列維持空白。`approve` 須列出核准用途與已核對項目，當期題需包含 `clinical`、`language`、`temporal`。`revise` 或 `withdraw` 記下理由與依據，`approved_uses` 留空。

```sh
python -m medbench.evidence_watch --out data/clinical-watch/latest.json
python -m medbench.review_packet prepare --watch-report data/clinical-watch/latest.json --family mbc-tw-adult-0001 --out data/review/worksheet.json
python -m medbench.review_packet candidate --packet data/review/worksheet.json --watch-report data/clinical-watch/latest.json --out data/review/candidate-decisions.jsonl
python -m medbench.curation queue --decisions data/review/candidate-decisions.jsonl --watch-report data/clinical-watch/latest.json
```

跨日送回時，以驗證候選檔當天的監測報告複核。程式比對工作表的原題、選項順序、內容指紋與上一筆決議，也核對證據生效日、授權及正式匯出條件。通過後會產生含既有紀錄及新決議的候選檔，供維護者確認後登錄。供閱讀的公開工作表可用 `prepare --markdown` 重建。

題目要保留兩個能獨立還原的判斷。原考題保存出題日、原題、原答案或給分公告及其出處。自編的歷史情境要明示是依當年資料重建。現行問法則寫出判斷日期、醫療管轄區、適用人群及版本。翻譯美式英文時仍可考臺灣制度。原題限定「依 2024 年規則」時，原答案繼續按 2024 年判分。

1. **收到變更線索。** 主動追蹤發布者目前維護的規則、現行指引索引及勘誤或撤回公告。指定網頁可用 `watch_xpath` 和 `passage_sha256` 監測單一表列或段落，SHA-256 取自 UTF-8 正文，連續空白收成一個半形空格。報告記錄查核日期、段落相符、內容改變或無法核對，並列出受影響的病例家族。另一網址新發布的指引，要從新文獻、正式公告或人工通報連回題目。資料尚待釐清時，登錄 `revise` 或 `withdraw` 決議即可暫停該版匯出。
2. **逐題重審。** 在語言版本的 `clinical_update` 填寫當期問法、`as_of`、`jurisdiction`、`review_due`、`outcome`、`valid_options`、條件成立的答案、詳解及 `evidence_ids`。每個證據 ID 都有 URL、版本和段落或表格定位。詳解逐項核對「哪裡改了」、「哪些人適用」、「各選項為何成立或失效」。無有效選項可明確作答；題幹缺資料要指明缺項；證據衝突送醫師裁決並暫停現行資料匯出。
3. **醫師裁決與發布。** 在既有逐版本決議中記錄審查者、日期、核准用途、理由與定位，`checked` 同時包含 `clinical`、`language`、`temporal`。題文、答案或依據改動後要更新題目修訂號並重新核准。已到複審日、先前核准內容雜湊失效、撤回或被監測來源有異動時，嚴格匯出會攔下該筆。維護者檢查新舊證據、記錄決議，再發布新快照。已發行的快照另留修訂紀錄，供使用者重編下游訓練集。

多個選項成立時，醫師須指定 `selection_rule`。任選一項皆給分用 `any_one`，記全可接受選項，並指定訓練樣本採用的代表答案。必須全選用 `all_required`，訓練答案須列全，選項順序可以不同。

同一次政策更新可以同時產生改答題及答案穩定的對照。醫師可先從一頁審題單核對差異，再開啟各語言的原題、選項、詳解與逐項證據。在本次篩檢案例，問法雖有三個，所有版本必須留在同一個資料分割。[臺灣公費篩檢雙語審題單](review/tw-fit-controls.md)

**用途與權利需各自有依據。** 在題本的 `source_rights` 填寫材料來源（專案原創或第三方）、授權狀態、署名、適用範圍、查核日及允許用途。第三方材料另記來源版本、原件網址、授權名稱及條款或許可網址。已向作者申請時可先登錄 `pending`。現行資料匯出同時檢查來源允許用途、病例分組及醫師對該用途的核准，並隨資料列保留權利依據。已有臨床核准但權利尚待確認者，仍能在審查佇列查看 `rights_status`。[實例及完整欄位](../drafts/mbc-tw-fit-0002.json)

公費糞便潛血檢查的雙語草稿中，相同四個選項在 2024 年可以選 50 歲。2025 年 1 月 1 日起，一般公費篩檢起始年齡降至 45 歲，40–44 歲另有一等親大腸癌家族史條件。本題限定沒有這項家族史，原選項缺 45 歲。題幹問的是臺灣公費方案的資格，兩個語言版本都待醫師評閱。`clinical_update.claims` 分別將年齡、頻率與家族史例外連到能支持它們的原文。[雙語草稿](../drafts/mbc-tw-fit-0001.json) · [舊版國健署問答](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770) · [變更公告](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761) · [現行服務表](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)

在 repo 根目錄安裝 `.[build]` 後，可按本日證據重建佇列與匯出檔。

```bash
python -m medbench.evidence_watch --out data/clinical-watch/report.json
python -m medbench.curation queue --watch-report data/clinical-watch/report.json
python -m medbench.curation clinical-train --watch-report data/clinical-watch/report.json --out data/curated/clinical-train.jsonl
```

現行開發集與保留評估集分別使用 `clinical-development`、`clinical-evaluation`，同樣檢查指定用途、審核決議與證據時效。公開的示範病例只准用於開發。首批留存了以當日取得的官方 HTML 重驗的段落紀錄，並在草稿內記錄三份原始回應的 SHA-256。2027-02-26 是本例預定人工複審日。[2026-11-26 來源核對紀錄](review/tw-fit-watch-2026-11-26.json)

已指定監測段落的題目需要同一查核日的報告。未啟用段落監測的證據依人工版本與複審日控管。歷史重現須選定題本 Git 版本、當日監測報告及當時已登錄的決議，並給予 `--as-of YYYY-MM-DD`。公開開發題、保留評估題和訓練題依既有病例家族分組。要建現行微調集請用 `clinical-train`。相容模式 `train` 仍可匯出整個病例家族都採舊格式、未作時效核對的樣本，這些列以 `answer_basis=source_version_unassessed` 標記。
