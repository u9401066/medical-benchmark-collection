# 臺灣公費篩檢回答理由審閱表

12 份原始回答均待審。請以題號記錄意見。下列參考主張為編者草稿，來源定位可供覆核。
請先閱讀[填寫說明與定位練習](review-guide.md)。

## R-59859

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the earliest age at which an asymptomatic adult without a first-degree family history of colorectal cancer qualifies for biennial fecal immunochemical testing (FIT)? Select one answer, or explain if none applies.
A. 40 years
B. 50 years
C. 45 years
D. 60 years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "choice": "B",
  "reason": "The earliest age for an asymptomatic adult without a first-degree family history of colorectal cancer to qualify for biennial fecal immunochemical testing (FIT) under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, is 50 years."
}
```

**編者參考主張**

1. General eligibility begins at age 45, with testing every two years.（hpa-tw-fit-current）
2. On January 1, 2025, the general age range changed from 50–74 to 45–74. At ages 40–44, eligibility requires a first-degree family history of colorectal cancer.（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-17163

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
依 2026 年 11 月 26 日臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早幾歲可接受每兩年一次的定量免疫法糞便潛血檢查？請選一項。若選項均不適用，請說明。
A. 40 歲
B. 50 歲
C. 55 歲
D. 60 歲

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "A",
  "reason": "依2026年11月26日臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早40歲可接受每兩年一次的定量免疫法糞便潛血檢查。"
}
```

**編者參考主張**

1. 一般公費篩檢最低年齡為 45 歲，頻率為每兩年一次。（hpa-tw-fit-current）
2. 2025 年 1 月 1 日起一般年齡由 50–74 歲改為 45–74 歲。40–44 歲須符合一等親大腸癌家族史條件。（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-38112

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
依 2026 年 11 月 26 日臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早幾歲可接受每兩年一次的定量免疫法糞便潛血檢查？請選一項。若選項均不適用，請說明。
A. 40 歲
B. 50 歲
C. 45 歲
D. 60 歲

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "A",
  "no_valid_option": "false",
  "insufficient_information": "false",
  "reason": "根據臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早可在40歲時接受每兩年一次的定量免疫法糞便潛血檢查。"
}
```

**編者參考主張**

1. 一般公費篩檢最低年齡為 45 歲，頻率為每兩年一次。（hpa-tw-fit-current）
2. 2025 年 1 月 1 日起一般年齡由 50–74 歲改為 45–74 歲。40–44 歲須符合一等親大腸癌家族史條件。（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-82047

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
依 2026 年 11 月 26 日臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早幾歲可接受每兩年一次的定量免疫法糞便潛血檢查？請選一項。若選項均不適用，請說明。
A. 40 歲
B. 50 歲
C. 45 歲
D. 60 歲

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "A",
  "reason": "依2026年11月26日臺灣國民健康署的公費大腸癌篩檢方案，無症狀成人，若沒有大腸癌一等親家族史，建議的開始篩檢年齡為40歲。因此，最早40歲可接受每兩年一次的定量免疫法糞便潛血檢查。"
}
```

**編者參考主張**

1. 一般公費篩檢最低年齡為 45 歲，頻率為每兩年一次。（hpa-tw-fit-current）
2. 2025 年 1 月 1 日起一般年齡由 50–74 歲改為 45–74 歲。40–44 歲須符合一等親大腸癌家族史條件。（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-35111

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the earliest age at which an asymptomatic adult without a first-degree family history of colorectal cancer qualifies for biennial fecal immunochemical testing (FIT)? Select one answer, or explain if none applies.
A. 40 years
B. 50 years
C. 55 years
D. 60 years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "choice": "C",
  "reason": "According to the publicly funded colorectal cancer screening program as of November 26, 2026, the earliest age at which an asymptomatic adult without a first-degree family history of colorectal cancer qualifies for biennial fecal immunochemical testing (FIT) is 55 years."
}
```

**編者參考主張**

1. General eligibility begins at age 45, with testing every two years.（hpa-tw-fit-current）
2. On January 1, 2025, the general age range changed from 50–74 to 45–74. At ages 40–44, eligibility requires a first-degree family history of colorectal cancer.（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-97859

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
An asymptomatic 60-year-old adult has no first-degree family history of colorectal cancer. Their last routine fecal immunochemical test (FIT) was negative, and they have no separate indication for follow-up. Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the interval between routine FITs? Select one answer, or explain if none applies.
A. Every year
B. Every three years
C. Every five years
D. Every two years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "choice": "B",
  "reason": "Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, the interval between routine FITs is every three years."
}
```

**編者參考主張**

1. At the end of 2024, a 60-year-old met the age requirement for screening every two years.（hpa-tw-fit-2024）
2. In 2025 the general age range expanded from 50 through 74 to 45 through 74.（hpa-tw-fit-change）
3. The program table checked on November 26, 2026, includes 60-year-olds and specifies one FIT every two years.（hpa-tw-fit-current）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)
- `hpa-tw-fit-2024`　FAQ updated 2024-11-18　癌症防治組，內文第一段描述補助年齡與頻率。 [大腸癌篩檢有篩過就好，沒有定期篩沒關係?](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770)

## R-77546

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the earliest age at which an asymptomatic adult without a first-degree family history of colorectal cancer qualifies for biennial fecal immunochemical testing (FIT)? Select one answer, or explain if none applies.
A. 40 years
B. 50 years
C. 55 years
D. 60 years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "option": "B",
  "necessity": "a necessary fact is missing",
  "reason": "The question does not provide the specific age requirement for the FIT test based on the publicly funded colorectal cancer screening program. The information given is about the screening program's eligibility criteria, but it does not specify the minimum age for FIT testing. Therefore, the correct answer cannot be determined from the provided options."
}
```

**編者參考主張**

1. General eligibility begins at age 45, with testing every two years.（hpa-tw-fit-current）
2. On January 1, 2025, the general age range changed from 50–74 to 45–74. At ages 40–44, eligibility requires a first-degree family history of colorectal cancer.（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-91181

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
依 2026 年 11 月 26 日臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早幾歲可接受每兩年一次的定量免疫法糞便潛血檢查？請選一項。若選項均不適用，請說明。
A. 40 歲
B. 50 歲
C. 55 歲
D. 60 歲

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "A",
  "no_valid_option": "B, C, D",
  "reason": "根據臺灣國民健康署的公費大腸癌篩檢方案，沒有大腸癌一等親家族史的無症狀成人，最早可在40歲時接受每兩年一次的定量免疫法糞便潛血檢查。"
}
```

**編者參考主張**

1. 一般公費篩檢最低年齡為 45 歲，頻率為每兩年一次。（hpa-tw-fit-current）
2. 2025 年 1 月 1 日起一般年齡由 50–74 歲改為 45–74 歲。40–44 歲須符合一等親大腸癌家族史條件。（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-40140

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
一名 60 歲成人沒有症狀，也沒有大腸癌一等親家族史。上次例行糞便潛血檢查為陰性，目前無需因其他原因追蹤。依 2026 年 11 月 26 日當時適用的臺灣國民健康署公費大腸癌篩檢方案，例行定量免疫法糞便潛血檢查的間隔是多久？請選一項。若選項均不適用，請說明。
A. 每年一次
B. 每三年一次
C. 每五年一次
D. 每兩年一次

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "B",
  "no_valid_option": "no",
  "reason": "根據2026年11月26日當時適用的臺灣國民健康署公費大腸癌篩檢方案，例行定量免疫法糞便潛血檢查的間隔是每三年一次。"
}
```

**編者參考主張**

1. 2024 年底，60 歲符合公費篩檢的年齡條件，例行檢查為每兩年一次。（hpa-tw-fit-2024）
2. 2025 年起一般篩檢年齡由 50–74 歲擴大為 45–74 歲。（hpa-tw-fit-change）
3. 依 2026 年 11 月 26 日的現行服務表，60 歲成人可每兩年接受一次公費定量免疫法糞便潛血檢查。（hpa-tw-fit-current）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)
- `hpa-tw-fit-2024`　FAQ updated 2024-11-18　癌症防治組，內文第一段描述補助年齡與頻率。 [大腸癌篩檢有篩過就好，沒有定期篩沒關係?](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770)

## R-62641

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the earliest age at which an asymptomatic adult without a first-degree family history of colorectal cancer qualifies for biennial fecal immunochemical testing (FIT)? Select one answer, or explain if none applies.
A. 40 years
B. 50 years
C. 45 years
D. 60 years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "option": "B",
  "necessity": "a necessary fact is missing",
  "reason": "The question does not provide the specific age requirement for the FIT test based on the publicly funded colorectal cancer screening program. The information given is about the program's eligibility criteria, but it does not specify the minimum age for FIT testing. Therefore, the correct answer cannot be determined from the provided information."
}
```

**編者參考主張**

1. General eligibility begins at age 45, with testing every two years.（hpa-tw-fit-current）
2. On January 1, 2025, the general age range changed from 50–74 to 45–74. At ages 40–44, eligibility requires a first-degree family history of colorectal cancer.（hpa-tw-fit-change）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)

## R-30969

語言 `zh-TW`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
一名 60 歲成人沒有症狀，也沒有大腸癌一等親家族史。上次例行糞便潛血檢查為陰性，目前無需因其他原因追蹤。依 2026 年 11 月 26 日當時適用的臺灣國民健康署公費大腸癌篩檢方案，例行定量免疫法糞便潛血檢查的間隔是多久？請選一項。若選項均不適用，請說明。
A. 每年一次
B. 每三年一次
C. 每五年一次
D. 每兩年一次

請用 JSON 物件回答。choice 填一個選項代號、no_valid_option（皆不適用）、insufficient_information（資訊不足）或 abstain（無法作答）。reason 請用繁體中文簡述理由。
```

**回答原文**

```text
{
  "choice": "B",
  "reason": "根據2026年11月26日當時適用的臺灣國民健康署公費大腸癌篩檢方案，例行定量免疫法糞便潛血檢查的間隔是每三年一次。"
}
```

**編者參考主張**

1. 2024 年底，60 歲符合公費篩檢的年齡條件，例行檢查為每兩年一次。（hpa-tw-fit-2024）
2. 2025 年起一般篩檢年齡由 50–74 歲擴大為 45–74 歲。（hpa-tw-fit-change）
3. 依 2026 年 11 月 26 日的現行服務表，60 歲成人可每兩年接受一次公費定量免疫法糞便潛血檢查。（hpa-tw-fit-current）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)
- `hpa-tw-fit-2024`　FAQ updated 2024-11-18　癌症防治組，內文第一段描述補助年齡與頻率。 [大腸癌篩檢有篩過就好，沒有定期篩沒關係?](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770)

## R-50943

語言 `en-US`，適用地區 TW，依據日期 2026-11-26。

**題目及作答規則**

```text
An asymptomatic 60-year-old adult has no first-degree family history of colorectal cancer. Their last routine fecal immunochemical test (FIT) was negative, and they have no separate indication for follow-up. Under Taiwan's publicly funded colorectal cancer screening program as of November 26, 2026, what is the interval between routine FITs? Select one answer, or explain if none applies.
A. Every year
B. Every three years
C. Every five years
D. Every two years

Return a JSON object. For choice give one option label, no_valid_option (none applies), insufficient_information (a necessary fact is missing), or abstain (unable to answer). In reason, briefly explain in American English.
```

**回答原文**

```text
{
  "answer": "B",
  "necessity": "The question asks for the interval between routine FITs based on the publicly funded colorectal cancer screening program in Taiwan as of November 26, 2026. The program specifies that the interval between routine FITs is every three years."
}
```

**編者參考主張**

1. At the end of 2024, a 60-year-old met the age requirement for screening every two years.（hpa-tw-fit-2024）
2. In 2025 the general age range expanded from 50 through 74 to 45 through 74.（hpa-tw-fit-change）
3. The program table checked on November 26, 2026, includes 60-year-olds and specifies one FIT every two years.（hpa-tw-fit-current）

**核對來源**

- `hpa-tw-fit-current`　Program table observed 2026-11-26　公費健檢服務表，大腸癌篩檢這一列的服務對象、頻率及服務項目。 [大腸癌篩檢(定量免疫)](https://www.hpa.gov.tw/Pages/List.aspx?nodeid=190)
- `hpa-tw-fit-change`　2025-01-16 release; policy effective 2025-01-01　內文含「114年1月1日」的段落，同句載明舊年齡、新年齡及家族史例外。 [健康台灣–擴展腸癌防護網 「腸」常篩檢護健康](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4878&pid=18761)
- `hpa-tw-fit-2024`　FAQ updated 2024-11-18　癌症防治組，內文第一段描述補助年齡與頻率。 [大腸癌篩檢有篩過就好，沒有定期篩沒關係?](https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=17770)
