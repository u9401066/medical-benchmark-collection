# 醫療評測與可供編修的資料來源

臺灣專科與次專科學會、醫事專業學會及地方組織另有分科名錄，可以直接查看已核實的網站與公開考題。[臺灣學會來源與覆蓋範圍](../tw-societies/README.md) · [學會試題與甄審公告](../tw-societies/exam-sources.tsv)

### 哪些既有資料能用來核實答案是否過時

本批新增五個來源，每筆保留原發布者、固定版本、資料權利及可判定的範圍。MedChangeQA 有 512 組同題新舊標註，CSV 缺逐題日期與原文定位。TempoMed-Bench 提供指引版本配對。MedQAbstain 可測模型是否會在正解被移除後硬選，需另加入仍有正解的題，才能量到過度棄答。MedAESQA 可檢查開放式回答的特定句子是否得到所引證據的支持。HealthFC 則有證據不足、支持與反對的醫療主張。這五項是來源登錄，授權與可用範圍在表中逐筆列出。[來源表與原始文獻](temporal-review-sources.tsv)

每週以 PubMed 的「進入索引日」找近期候選，與作者釋出的 GitHub、Hugging Face、研究附件及臺灣學會更新互補。新文獻先核對原作者的資料頁、是否只是既有資料的衍生集，以及能否對回正式發布版本。下列指令可以重跑一個明確期間，保存分母、實取的 PMID 與標題。跨週交疊需依 PMID 去重，同資料集的多篇論文仍要人工歸戶。

```bash
python -m medbench.benchmark_discovery --start 2026-11-13 --end 2026-11-26 --out data/discovery/pubmed-20261126.json
```

首批檢索涵蓋 2026-11-13 至 2026-11-26，命中 206 篇，已取得全部 206 筆 PMID 與標題。這是供編者篩選的文獻數，一份資料集可能對應多篇論文，有些論文只使用既有題庫。每週的 Actions 執行保留當批搜尋檔；正式登錄來源時，把版次、可取得的材料與權利一起存回此目錄。[首批 PubMed 候選與可重跑查詢](pubmed/2026-11-26.json)

本批已有兩筆完成資料釋出狀態核對。中醫辨證論治評測 TCM-BEST4SDT 可定位至 Figshare 第 8 版，資料採 CC BY 4.0。風濕科 RheumBench 的論文提供醫師評分方法，取得原始資料需要向作者申請。其餘 204 篇尚待登錄逐筆判定。另完成 MedChangeQA 固定版本的 512 筆標籤稽核，可供抽樣設計使用。[PubMed 候選核對表](pubmed/triage.tsv) · [TCM-BEST4SDT 版本與檔案](https://api.figshare.com/v2/articles/30615956/versions/8) · [RheumBench 資料聲明](https://link.springer.com/article/10.1007/s10916-026-02493-z#data-availability) · [MedChangeQA 標籤交叉表](../../docs/review/medchange-audit.md)

收錄單位可以是一份資料集、評測平台或作者分享的文件。同一作品在 Google、Hugging Face 或 GitHub 建立的不同入口共用一個來源身分。來源目錄、可下載樣本、作者釋出的正式 benchmark 與本專案醫師審定的案例各有不同用途。首批查核日期為 2026-11-26。

已查驗的 13 項來源涵蓋 Google Sheets、Docs、Drive、作者網站及固定發行版。清單記錄每項資源提供題本、排行榜、研究附件或教學材料，並保留原連結失效時的機構入口。臺灣部分新增長庚大學醫學系公布的 115 年第一次 OSCE 標準化病人劇情摘要 63 例與 20 種操作技能題型。該批僅登錄後設資料，校方要求轉載須經允許。[公開分享清單](public-shares.tsv) · [長庚大學 OSCE 專區](https://www.cgu.edu.tw/med/Subject/Detail/76921?nodeId=15049)

| 來源與版本 | 已有的工作 | 本專案可如何沿用 |
|---|---|---|
| 維也納醫療 AI 資料目錄 v0.1.3 | 作者以 Google Sheet 共享，並在 Zenodo 固定發行。已收錄 475 筆資料集線索 | 依任務、語言、資料型態找原作，保留原始行號及當年授權標註。[本地可查清單、署名與授權](vienna/README.md) |
| Stanford MedHELM | 由臨床工作建立 121 項任務分類，彙整不同存取條件的子評測，並提供評分框架及結果 | 用分類檢查本庫的臨床工作覆蓋；依各子評測的提供者及版本登錄使用條件。[計畫網站](https://medhelm.org/) · [研究原文](https://pmc.ncbi.nlm.nih.gov/articles/PMC13267972/) |
| Evidence Inference 2.0 | 醫師閱讀隨機試驗，標記介入、對照與結局，並提供支持判斷的原文章節位置 | 參考其醫師標註與複核方式，測試 agent 能否擷取正確的證據及辨認適用族群。[作者網站](https://evidence-inference.ebm-nlp.com/) · [欄位與版本](https://evidence-inference.ebm-nlp.com/download/) |
| BioASQ Task 14b | 主辦方按批次整理文獻檢索、證據片段、短答與整合回答 | 將「找到正確文章」、「找到支持文字」與「答案成立」分項評分，保留批次與檢索日期。[主辦方任務規格](https://assess.bioasq.org/participate/challenges) |
| PhysioNet ReEvalMed 1.0.0 | 放射報告成對改寫，臨床審查者確認差異及臨床重要性，附理由 | 參考其修訂方法，自編報告差異案例。原始檔依 PhysioNet 資格審查與資料使用協議提供；本庫登錄方法與來源。[資料卡、版本與取用條件](https://physionet.org/content/reevalmed/1.0.0/) |
| MedAgentBench | 在模擬電子病歷中以具體任務評測代理操作，作者提供環境與評估程式 | 登錄工具、資料版本、初始狀態與操作結果，供後續建立可複評的代理任務。[作者程式](https://github.com/stanfordmlgroup/MedAgentBench) · [原始研究](https://doi.org/10.1056/AIdbp2500144) |
| 臺灣國考既有整理 | 考選部開放資料、EMPEC、medical-bench-tw、MedQA-TWMLE 與社群下載工具 | 用既有題庫交叉比對，回到考選部確認原卷、改答與送分。各來源題數可能重疊。[版本與來源對照](../moex/README.md#既有彙整與可比範圍) |

發現一項資料時，先記作者或發布機構、正式入口、版本或穩定 ID、收錄單位、任務、語言、地域與使用條件。清單或排行榜可以指向原作；判斷能否改編、翻譯與納入訓練，需要查看原作的條款。生產資料另外記錄原始版本、修改內容、臨床依據、醫師決議、語言版本與資料分組。[編修流程](../../docs/editorial-workflow.md)
