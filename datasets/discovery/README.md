# 醫療評測與可供編修的資料來源

臺灣專科與次專科學會、醫事專業學會及地方組織另有分科名錄，可以直接查看已核實的網站與公開考題。[臺灣學會來源與覆蓋範圍](../tw-societies/README.md) · [學會試題與甄審公告](../tw-societies/exam-sources.tsv)

### 哪些既有資料能用來核實答案是否過時

本批新增五個來源，每筆保留原發布者、固定版本、資料權利及可判定的範圍。MedChangeQA 有 512 組同題新舊標註，CSV 缺逐題日期與原文定位。TempoMed-Bench 提供指引版本配對。MedQAbstain 可測模型是否會在正解被移除後硬選，需另加入仍有正解的題，才能量到過度棄答。MedAESQA 已建立 5,162 句與 9,611 筆引用關係的可重建索引，可逐句回查開放式回答的證據。HealthFC 則有證據不足、支持與反對的醫療主張。這五項是來源登錄，授權與可用範圍在表中逐筆列出。[來源表與原始文獻](temporal-review-sources.tsv) · [MedAESQA 逐句索引、來源定位與分母差異](medaesqa/README.md)

每週以 PubMed 的「進入索引日」找近期候選，與作者釋出的 GitHub、Hugging Face、研究附件及臺灣學會更新互補。新文獻先核對原作者的資料頁、是否只是既有資料的衍生集，以及能否對回正式發布版本。下列指令可以重跑一個明確期間，保存分母、實取的 PMID 與標題。跨週交疊需依 PMID 去重，同資料集的多篇論文仍要人工歸戶。

```bash
python -m medbench.benchmark_discovery --start 2026-11-13 --end 2026-11-26 --out data/discovery/pubmed-20261126.json
python -m medbench.discovery_queue --latest data/discovery/pubmed-20261126.json --out data/discovery/pubmed-screening-queue.json
```

第二條指令合併 `pubmed/` 中已存的搜尋快照和本次結果，依 PMID 去重，再扣除已登錄初篩的文獻。佇列保留最初發現的順序，從首筆即可續作。部分取得或搜尋失敗時，仍輸出已知候選及各批缺口。每週工作同時保存搜尋報告與待查佇列。要讓後續佇列持續涵蓋曾出現的候選，需將應保存的每批搜尋報告歸入版本庫。[初篩登錄表](pubmed/triage.tsv)

首批檢索涵蓋 2026-11-13 至 2026-11-26，命中 206 篇，已取得全部 206 筆 PMID 與標題。這是供編者篩選的文獻數，一份資料集可能對應多篇論文，有些論文只使用既有題庫。每週的 Actions 執行保留當批搜尋檔；正式登錄來源時，把版次、可取得的材料與權利一起存回此目錄。[首批 PubMed 候選與可重跑查詢](pubmed/2026-11-26.json)

**文獻初篩進度為 62／206，尚有 144 篇。** 首輪核對 TCM-BEST4SDT 與 RheumBench，前者可取得採 CC BY 4.0 的 Figshare 第 8 版，後者須向作者申請。第二輪按快照原順序查核第 1 至 10 篇，與首輪兩篇均無重複。四篇公開研究附件，兩篇的研究資料須申請，兩篇是可供追查上游文獻的綜述，一篇整合既有資源，一篇公開固定版本的評分重現套件。這些是按研究材料判定的筆數；同一篇也可能公開評分程式、限制病人資料取用。[PubMed 候選核對表](pubmed/triage.tsv) · [TCM-BEST4SDT 版本與檔案](https://api.figshare.com/v2/articles/30615956/versions/8) · [RheumBench 資料聲明](https://link.springer.com/article/10.1007/s10916-026-02493-z#data-availability)

抗生素管理研究的 Zenodo v1.2 可用來查提示、評分規則及聚合結果，病人層級的輸入與作答受限。動脈瘤性蜘蛛膜下腔出血研究的公開附件含土耳其文原題及英文翻譯，逐筆模型答案與醫師分數須另行申請。核對表的 `dataset` 欄填作者名稱或材料描述，綜述沒有具名材料時留空。另已實算 MedChangeQA 的 512 筆新舊配對，可用於時效問題的分層抽樣。[抗生素管理重現套件](https://doi.org/10.5281/zenodo.24194665) · [蜘蛛膜下腔出血問答附表](https://www.mdpi.com/article/10.3390/jcm15228896/s1) · [MedChangeQA 標籤交叉表](../../docs/review/medchange-audit.md)

第三輪按快照順序查核第 11–20 篇。兩篇可核對作者釋出的版本，三篇提供可用於評測的附件，三篇綜述可追查上游研究，一篇依作者申請取得，一篇核實了 ADNI 的上游申請條件。產前照護附件將 51 題對回 2016 年 WHO 建議，並分開提供評分定義與已編碼作答。CoDE 釋出無病人資料的評分程式與合成範例，另行列明臨床紀錄取用條件。[產前照護題目與評分附件](https://www.mdpi.com/article/10.3390/healthcare14223867/s1) · [CoDE 固定版本](https://github.com/kenshinpg/CoDE/tree/3855b5b73a39acd39e72b3d2051dea269117a25e)

**兒科病例的附件編號需要對照實檔。** 出版者列出七份 Word 文件，網頁第 6 檔才是內標「Material 1」的 120 題題本，第 3 檔則是內標「Material 4」的正誤矩陣。逐列核對矩陣，5 個模型各答 120 題，合計 558／600 題答對，與作者報告的 93% 相符。文章採 CC BY-NC-ND 4.0，本庫保留檔案指紋及聚合統計。[兒科研究與授權](https://doi.org/10.1186/s12911-026-03818-1) · [題本 DOCX](https://static-content.springer.com/esm/art%3A10.1186%2Fs12911-026-03818-1/MediaObjects/12911_2026_3818_MOESM6_ESM.docx) · [正誤矩陣 DOCX](https://static-content.springer.com/esm/art%3A10.1186%2Fs12911-026-03818-1/MediaObjects/12911_2026_3818_MOESM3_ESM.docx)

第四輪按快照第 21–30 篇核對了 10 篇。FoodBench v1.0 公開 7 個檔案，另有三項任務依賴須向上游申請的 Recipe1+。COSAVRI 的發行版包含人工修訂紀錄與決策工作表，可追查某個試驗結局如何取捨。罕見病統合分析則公開了 19 筆系統與資料集組合的分母、命中數及重現程式。[FoodBench 公開檔案與取用條件](https://zenodo.org/records/17798877) · [COSAVRI 人工修訂材料](https://doi.org/10.5281/zenodo.23809841) · [罕見病統合分析固定版本](https://github.com/minhha0510/Rare-Disease-Meta-Analysis-2026/tree/6f3eaf6c8b85ce76c984823239ccfb976bd54254)

牙科研究的 13 份 PDF 中，第 2、6、10 檔各有 33 次原始問答，對應 11 個 PICO 問題、3 個模型、3 天重測。中國臨床醫學考試研究的附七可重算 1,644 題、16,440 次作答與 14 次格式衝突，並可追到每題使用的答案版本。作者無權重發完整考題。另一項急診研究的公開矩陣有 305 筆就診，保留評分而將生命徵象改成常數。[牙科研究與附件](https://doi.org/10.1038/s41432-026-01287-z) · [中英逐題配對、格式衝突與分組分母](../../docs/review/bilingual-exam-audit.md) · [中國醫學考試的資料聲明與附表](https://pmc.ncbi.nlm.nih.gov/articles/PMC13792588/) · [急診檢傷資料範圍](https://pmc.ncbi.nlm.nih.gov/articles/PMC13795786/)

第五輪核對快照第 31–40 篇。腫瘤會診研究公開九面向評分規準，可用來比較醫師與模型評審；研究中 108 次會診的 324 份回答受病人保密限制。耳鼻喉科試驗的評讀量表藏在附三 Word 文件的內嵌文件，兩位醫師盲評的逐筆紀錄須申請。胸部 X 光綜述公開 1,000 筆文獻匯出與 776 筆重跑書目紀錄，可回查各影像庫的標註來源。護理綜述則逐項列出 23 篇研究的查核材料，其中 13 篇以中文發表。[腫瘤科評分規準](https://pmc-oa-opendata.s3.amazonaws.com/PMC13801721.1/curroncol-33-00721-s001.zip) · [耳鼻喉科評讀量表](https://pmc-oa-opendata.s3.amazonaws.com/PMC13792887.1/formative-v10-e99015-s003.docx) · [護理評測材料索引](https://pmc-oa-opendata.s3.amazonaws.com/PMC13793833.1/Table_1.docx)

第六輪核對快照第 41–51 筆，跳過已登錄的第 46 筆 RheumBench，共新增 10 篇。EHRNavigator 的 Yale 代理任務公開 100 個編號問題，移除題號後有 99 種題文，第 67、68 題相同；研究的雙人盲評與病歷完整度需另查原文。MedGuard 原文及作者 README 均提到中文遠距醫療評測集，但核對的 GitHub 提交未含所列目錄，1,665 段對話及 7,589 個人工標註主張仍屬研究報告數。另核實可查閱 14 頁耳鳴實證推理情境，以及放射物理模擬出題提示。[EHRNavigator 逐題定位、重複組與重建方式](ehrnavigator/README.md) · [作者的問題檔](https://github.com/BIDS-Xu-Lab/EHRNavigator/blob/be9d5181272bee487b78404ce60a849b7d24a419/YNHHQA.txt) · [MedGuard 作者庫固定版本](https://github.com/XMUDM/MedGuard/tree/4f2778d11dae8ab336202eeb9168d544ce05a461) · [耳鳴情境與原始評量設計](https://doi.org/10.1007/s10459-026-10602-3)

第七輪核對快照第 52–61 筆，下一筆為第 62 筆 PMID `43073205`。FOX 公開 3 個生殖醫學病例及 Q1–Q32 的三模型評分，32 個題號的完整題文仍待取得。腦炎衛教正文表 1 可重算 50 個候選搜尋詞，排除 18 個後留 32 個，研究另報 128 份回答的雙評閱者一致性。[FOX 病例附件](https://static-content.springer.com/esm/art%3A10.1007%2Fs43032-026-02268-4/MediaObjects/43032_2026_2268_MOESM2_ESM.docx) · [腦炎衛教研究的搜尋詞與評讀](https://www.frontiersin.org/journals/public-health/articles/10.3389/fpubh.2026.1986483/full)

神經外科影像極短答有四份方法及評分附件。附三 S2 可重算 36 個題號、360 份作答，模型與專家共識完全一致 324／360。論文另報兩位專家討論前一致 347／360。真實病例、MRI 及逐份住院醫師原答須另行申請。CLAD 的出版附件可重算 268 個案件及 3,072 次模型模擬。作者 v1.0.0 的醫師複核檔有 130 列，121 列有醫師評分，涵蓋 118 個相異 run ID。三等級完全一致 89／121，排除任何一側為中間分數後是 89／106。兩種分母對應不同判定。作者發布檔與論文資料聲明列 CC BY-NC 4.0，Zenodo 目錄標 CC BY 4.0，已在初篩表記錄重用前須確認。[神經外科評分附件](https://static-content.springer.com/esm/art%3A10.1186%2Fs12909-026-10295-7/MediaObjects/12909_2026_10295_MOESM3_ESM.docx) · [CLAD v1.0.0 資料與程式](https://github.com/dviraran/CLAD/tree/5ced25faf92e7505d78b9c1588afa5ca6e426661) · [CLAD 作者論文及附表](https://pmc.ncbi.nlm.nih.gov/articles/PMC13793154/) · [Zenodo 目錄](https://zenodo.org/api/records/21097485)

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
