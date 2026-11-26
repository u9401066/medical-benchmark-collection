# 醫學評測目錄

截至 2026-11-26，`medbench` 可載入 14 個題庫，共 51,513 題。`@core` 有 3,686 題，`@academic` 有 14,834 題，`@zh-tw` 有 38,092 題。後兩組共用 MedQA-TWMLE 的 1,413 題。`@all` 依題庫名稱去重，跨來源的相似病例仍可能重疊。[題庫版本、檔案 SHA-256 與組別定義](../medbench/datasets.py)

## 已接入的文字問答

表中題數是本專案選用的資料範圍。語言依原題標示，英文來源可來自不同醫療體系。

| 評測名稱 | 原題語言與任務 | 本專案採用的範圍 | 第一手來源 |
|---|---|---|---|
| `medqa_usmle`、`medqa_twmle`、`medqa_mcmle` | 美國英文、臺灣繁中、中國大陸簡中的醫師考題，各自獨立命題 | 各地 test，依序 1,273、1,413、3,426 題，皆為四選一 | [MedQA 論文](https://doi.org/10.3390/app11146421) · [作者資料說明](https://github.com/jind11/MedQA) |
| `pubmedqa` | 英文，根據研究摘要回答 yes／no／maybe | Hugging Face 的 `pqa_labeled/train` 全部 1,000 題；原論文從中取 500 題作為 test。引用分數時須註明分母 | [原論文 §3](https://aclanthology.org/D19-1259.pdf) · [作者資料卡](https://huggingface.co/datasets/qiaojin/PubMedQA) |
| `medmcqa` | 英文，印度醫學研究所入學考題 | validation，4,183 題。依來源 `cop` 欄位評單一選項，保留 `choice_type` | [MedMCQA 論文](https://proceedings.mlr.press/v174/pal22a.html) · [資料卡](https://huggingface.co/datasets/openlifescienceai/medmcqa) |
| `mmlu_med` | 英文，含解剖、遺傳、生物與臨床知識 | 選用 6 科 test，共 1,089 題 | [MMLU 論文](https://arxiv.org/abs/2009.03300) · [資料卡](https://huggingface.co/datasets/cais/mmlu) |
| `medxpertqa` | 英文，專家級醫學推理與理解，十選一 | Text/test，2,450 題；多模態題為另一子集 | [MedXpertQA 論文](https://proceedings.mlr.press/v267/zuo25a.html) · [資料卡](https://huggingface.co/datasets/TsinghuaC3I/MedXpertQA) |
| `tmmlu_med` | 臺灣繁中，醫藥及醫事職類選擇題 | TMMLU+ 的 8 科 test，共 4,151 題 | [TMMLU+ 論文](https://arxiv.org/abs/2403.01858) · [資料卡](https://huggingface.co/datasets/ikala/tmmluplus) |
| `twmed_md`、`twmed_dent`、`twmed_tcm`、`twmed_rx`、`twmed_rn`、`twmed_allied` | 臺灣繁中，醫師、牙醫師、中醫師、藥師、護理師與助產師、其他醫事職類 | 自建 `twmed-v1`，2024–2026 年可純文字作答的國考單選題。上述六組依序有 2,872、2,645、2,821、2,518、3,072、18,600 題 | [考選部考畢試題](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx) · [建置與排除紀錄](twmed/README.md) |

學術資料來自固定 revision。MedQA 作者儲存庫列 MIT，實際下載的 BigBio 資料卡標示 `unknown`，轉載或翻譯題文時須核對原始來源。PubMedQA、MMLU、MedXpertQA、TMMLU+ 的資料卡列 MIT；MedMCQA 列 Apache-2.0。[MedQA 作者儲存庫](https://github.com/jind11/MedQA) · [BigBio 資料卡](https://huggingface.co/datasets/bigbio/med_qa)

`twmed-v1` 壓縮檔共 32,528 筆，SHA-256 為 `169fabd030cf24939a33ac89920670b1d819a570f5d56c56668ad7bd35ab580a`。每題可依考試、類科、科目與題號定位，來源清單列出 1,056 筆試題、答案與更正答案 PDF 紀錄。法規依據為《著作權法》第 9 條第 1 項第 5 款；考選部另要求引用時註明來源並保持完整。若臨床指引已更新，應另建具版本的衍生題，並保留原場次與當年答案。[來源與雜湊](twmed/sources.tsv) · [法規條文](https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=J0070017&flno=9) · [考選部引用聲明](https://wwwq.moex.gov.tw/exam/wFrmExamQandASearch.aspx)

現有執行紀錄中，核心三庫有全量結果，另外十一庫有每庫抽 20 題的試跑。這兩批紀錄的來源 revision 與 SHA-256 可逐項對回載入器。[核心題庫 manifest](../results/bonsai27b-pq2-medium/manifest.json) · [抽樣試跑 manifest](../results/inkling2mini-iq4xs-prod-medium/manifest.json)

## 既有的代理工具與效能研究

- **工具選擇**記錄模型第一次呼叫是否選對 PubMed／Zotero 工具，題目分為保留集 52 題與困難集 110 題。評分對象是首次工具選擇，完整答案的臨床正確性需另行評量。[試題組別、設定與結果](../results/toolbench/README.md)
- **檢索任務的執行速度**使用一項尋找三篇臨床試驗並製表的任務，分析請求重播與端到端耗時。適合比較伺服器設定。[研究方法與結果](../reports/inkling2mini/AGENT-SPEED.md)

## 待接入的公開評測

臺灣醫事國考另有 EMPEC 與 medical-bench-tw 等逐題彙整。本專案記錄各版本涵蓋的年份、職類、題型與取用條件，以便與官方原卷核對重疊。[考選部資料與既有彙整](moex/README.md#既有彙整與可比範圍)

以下五項已有原作者或主辦方公開的方法與資料入口，本階段只收錄索引。

| 候選 | 可測能力 | 取得方式與接入條件 |
|---|---|---|
| BioASQ Task 14b | 英文文獻檢索、證據片段定位與問答，可比較自行檢索及提供標準文獻兩種設定 | 依屆次與批次鎖定資料。開發集下載須註冊，主辦方列 CC BY 2.5。接入時分開回報檢索與答案指標。[任務與指標](https://participants-area.bioasq.org/general_information/Task14b/) · [資料入口與授權](https://participants-area.bioasq.org/datasets/) |
| MedAgentBench | 臨床代理在虛擬電子病歷查詢與執行任務；原論文的英文基準有 10 類、300 項任務 | 作者公開程式與 FHIR 伺服器映像。需固定環境版本、重設病例狀態並用原任務評分程式判定結果。[論文](https://doi.org/10.1056/AIdbp2500144) · [環境與評分程式](https://github.com/stanfordmlgroup/MedAgentBench) |
| HealthBench | 多語健康對話，5,000 個情境，各有醫師擬定的加權評分準則 | 作者提供資料與 MIT 授權的評測專案。接入時記錄評分模型與準則版本，繁中版須檢查翻譯是否保留各項得失分條件。[方法](https://openai.com/index/healthbench/) · [官方評測與授權](https://github.com/openai/simple-evals) |
| VQA-RAD | 英文放射影像問答，醫師為影像撰寫問題並提供參考答案 | 作者將題答及影像存於 OSF。接入前需核對題圖配對、影像使用條件與訓練／測試影像重疊情形。[原始研究](https://doi.org/10.1038/sdata.2018.251) · [資料存放紀錄](https://doi.org/10.17605/OSF.IO/89KPS) |
| AgentClinic | 代理在模擬診間透過多輪互動蒐集線索並做出診斷 | 作者提供模擬程式與案例。接入時需固定模擬病人、評分者及可用工具。MedQA 衍生案例須和既有題庫核對重疊。[原始研究](https://doi.org/10.1038/s41746-026-02674-7) · [作者程式與案例](https://github.com/SamuelSchmidgall/AgentClinic) |

### 一次可重跑的發現紀錄

2026-11-26 使用 PubMed Search MCP 搜尋標題含評測、醫學及 agent 用語的文獻。來源限 PubMed，採用 `shallow,no_relax`，上限 50 筆。PubMed 回報命中 10 筆，從中定位到 MedAgentBench 與 AgentClinic 的原始研究。標題中的 `agents` 也會命中藥物研究，必須核對摘要、任務和公開資料入口。後續批次可沿用檢索式，另查會議論文、資料平台及作者儲存庫，補足 PubMed 涵蓋範圍。

```text
(benchmark[ti] OR benchmarks[ti] OR benchmarking[ti])
AND (clinical[ti] OR medical[ti] OR healthcare[ti])
AND (agent[ti] OR agents[ti] OR agentic[ti])
```
