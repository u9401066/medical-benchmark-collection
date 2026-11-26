# 醫療評測與可供編修的資料來源

收錄單位可以是一份資料集、評測平台或作者分享的文件。同一作品在 Google、Hugging Face 或 GitHub 建立的不同入口共用一個來源身分。來源目錄、可下載樣本、作者釋出的正式 benchmark 與本專案醫師審定的案例各有不同用途。首批查核日期為 2026-11-26。

[已查驗的 12 項公開分享與作者入口](public-shares.tsv) 列出 Google Sheets、Docs、Drive、作者網站及固定發行版，區別資料集、排行榜、研究附件、教學素材與受控資源。失效連結保留查驗結果與可用的學校或機構備份。

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
