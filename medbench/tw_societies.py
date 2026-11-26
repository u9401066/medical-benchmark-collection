"""Rebuild the Taiwan medical society directory from its attributed source tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path("datasets/tw-societies")
SNAPSHOTS = {
    "13603": (
        23210,
        "bc4700434d571f617a420a9617cf1ec681a08c9535d7cba69d58af92cc32762e",
        "https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/"
        "DA99D92C-531A-40B2-AFF6-D5C1C7AEE022/resource/6CD84A67-522B-4811-96B8-3E7942AE3C1B/download",
    ),
    "147595": (
        23864,
        "bf8f2add9578750a0dcd89df8d29bae36f223d4edbfffcbdd4ba30298d7709a7",
        "https://quality.data.gov.tw/dq_download_csv.php?nid=147595&md5_url=f3ef04c20c043bca773a6439e3659c71",
    ),
}
GROUPS = [
    ("牙科與口腔", r"(?<!班)(?<!萄)牙|口腔|顎|齒顎|植體美學|齒列|義齒|齒模"),
    ("中醫與中西整合", r"中醫|中西[醫整]|[鍼針]灸|經絡|漢方|傳統醫學|中藥"),
    ("護理與助產", r"護理|護士|助產|傷口造口"),
    (
        "藥學與用藥",
        r"藥學|藥事|藥師|藥理|藥物|藥劑|藥用植物|藥害|製藥|生物藥|毒物|藥品|生藥",
    ),
    (
        "復健、功能治療與輔具",
        r"復健|物理治療|職能治療|語言治療|聽力|聽語|聽覺|溝通障礙|吞嚥|輔具|早期療育|手治療",
    ),
    ("營養與膳食", r"營養|膳食"),
    (
        "心理、精神與成癮",
        r"精神|心理|身心|自殺防治|成癮|思覺失調|憂鬱|諮商|催眠治療|沙遊|行為治療",
    ),
    (
        "急診、重症與救災醫療",
        r"急診|急症|急救|緊急救|醫療救護|重症|加護|災難醫|復甦|急重",
    ),
    ("感染、免疫與風濕", r"感染|傳染|愛滋|疫苗|結核|免疫|風[濕溼]|過敏|熱帶醫|寄生蟲"),
    ("腫瘤與血液", r"腫瘤|癌|血液|骨髓|造血|腫瘍|輸血|血友病|血栓暨止血"),
    (
        "心臟、血管與循環",
        r"心臟|心律|心血管|血管|心肺|心肌|血壓|動脈硬化|靜脈|血脂|循環",
    ),
    ("胸腔、呼吸與睡眠", r"胸腔|呼吸|肺|睡眠"),
    ("消化、肝膽與胰臟", r"消化|肝|腸|胃|胰|膽|內視鏡"),
    ("腎臟與泌尿", r"腎|泌尿|透析|尿控|尿失禁|男性學|攝護腺"),
    ("內分泌與代謝", r"內分泌|糖尿|代謝|甲狀腺|肥胖|骨質疏鬆|醛酮|腦下垂體"),
    ("神經與腦科學", r"神經|(?<!電)腦|中風|失智|癲癇|巴金森|頭痛|動作障礙"),
    (
        "婦產、生殖與周產期",
        r"婦|產科|生殖|生育|周產|週產|產前|母胎|母乳哺育|不孕|更年期|卵巢|子宮",
    ),
    ("兒科與青少年", r"兒童|小兒|兒科|青少年|新生兒|兒少"),
    (
        "骨科、運動與創傷",
        r"骨科|骨折|骨關節|骨骼|脊椎|脊髓|脊骨|關節|運動醫|運動傷害|運動防護|創傷|外傷|手外科",
    ),
    ("皮膚、整形與傷口", r"皮膚|整形|整外|顱顏|美容醫|美形|燒傷|傷口|毛髮|生髮"),
    (
        "眼科、耳鼻喉及頭頸",
        r"眼科|眼視光|視光|驗光|眼整形|眼部|視網膜|玻璃體|白內障|角膜|青光眼|耳鼻|內耳|耳科|鼻科|鼻炎|喉科|頭頸",
    ),
    (
        "影像、放射與核醫",
        r"影像|放射|超音波|核子醫|核醫|超聲|醫學物理|中子捕獲|醫用迴旋加速器",
    ),
    ("麻醉與疼痛", r"麻醉|疼痛|肌痛|痠痛"),
    (
        "病理、檢驗與基礎生醫",
        r"病理|檢驗|分子|醫檢|細胞|生物醫|生醫|解剖|生理學|生化|遺傳|微生物|實驗診斷|實驗醫|醫學實驗室|蛋白體|基因|精準醫|再生醫|生物資訊",
    ),
    ("外科、移植與手術", r"外科|移植|手術|微創|疝氣|內分泌外|乳房醫"),
    (
        "家醫、老年、安寧與長照",
        r"家庭醫|家醫|基層醫|老年|高齡|安寧|緩和|長期照|長照|居家醫|居家照顧|健康照顧|社區醫|老人醫",
    ),
    (
        "公衛、職業與預防醫學",
        r"公共衛生|公衛|流行病|環境衛生|職業[醫衛病]|職業環境|預防醫|衛生教育|衛生行政|學校衛生|健康促進|健康政策|醫療政策|健康保險|保健|職業安全衛生|菸害|戒菸",
    ),
    (
        "醫學教育、品質、資訊與醫務",
        r"醫學教|醫療教|醫事教|繼續教育|醫學模擬|醫學圖書|實證|醫療品質|病人安全|醫療資訊|醫學資訊|醫務|醫管|醫資|疾病分類|醫院協會|診所協會|共同決策|醫藥法|醫療管理|個案管理|醫療法律|醫事法|醫療法|醫療倫理|醫學倫理|研究倫理|醫學工程|醫工|醫療器材|數位醫|智慧醫|醫學人工智慧",
    ),
    ("一般內科與跨科醫學", r"內科|醫學|臨床|醫師|醫事|醫療|法醫"),
]
SOCIETY = re.compile(r"學會")
PROFESSION = re.compile(
    r"(?:醫師|牙醫|護理師|治療師|藥師|醫檢師|營養師|助產師|放射師|聽力師|驗光師).{0,8}協會"
)
MEDICAL_SIGNAL = re.compile(
    r"醫|(?:植牙|牙科|牙體|牙周|牙髓|齒顎|矯齒|口腔)|藥學|藥物|藥理|藥事|藥師|護理|助產|"
    r"營養|治療|聽力|驗光|復健|檢驗|病理|疾病|病學|防治|照護|長照|長期照顧|安寧|"
    r"臨床|生殖|生育|婦產|婦科|兒科|疼痛|創傷|腫瘤|血液|骨髓|癌|糖尿|過敏|失智|癲癇|"
    r"風濕|免疫|感染|寄生蟲|微生物|毒物|公共衛生|流行病|疫苗|急救|復甦|急診|重症|"
    r"經絡針|針灸|內科|外科|手術|內分泌|內視鏡|神經|透析|麻醉|精神|解剖|耳鼻|"
    r"心臟|血管|肺|胃腸|消化系|腎臟|肝膽|泌尿|腸道|超音波|基因體|生物化學|"
    r"語言障礙|聽語|睡眠|運動傷害|運動防護|生理學|物理治療|諮商心理|輔導心理|"
    r"病人|患者|病友|精準健康|衛生政策|健康保險|預防接種|骨科|骨質疏鬆|骨關節|脊椎|脊髓|"
    r"職業衛生|心理衛生|衛生行政|衛生教育|學校衛生|早期療育|遺傳諮詢|人類遺傳|高血壓|頭痛|"
    r"白內障|乳房整形|口吃|細胞生物|幹細胞|骨折|腦中風|巴金森|眼科|視網膜|角膜|喉科|"
    r"生物統計|輔具|聽障|失語|吞嚥|周產期|更年期|大腸直腸|耳科|鼻科|鼻炎|"
    r"輸血|視光|兒童發展療育|成癮|蛋白體|肥胖研究|牙技|顳顎|顱顎|顎咬合|體外循環|動作障礙|"
    r"婦女健康|子宮內膜|腦下垂體|分子生物|介入放射|放射線技術|心肌梗塞|血脂|動脈硬化|齒列|"
    r"兒童青少年發展障礙|代謝體|表觀遺傳|腦刺激|結直腸|器官捐贈|義齒|顱顏|血栓|靜脈學|肌痛|"
    r"母乳哺育|健康照顧|思覺失調|醛酮|肌能系貼紮|菸害|戒菸|生物資訊|痠痛|卵巢|居家照顧"
)


def normalized(name):
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).replace("臺", "台")
    return re.sub(r"^社團法人", "", value)


def classification(name):
    return [group for group, pattern in GROUPS if re.search(pattern, name)]


def registry_scope(name):
    n = normalized(name)
    if re.search(r"獸醫|(?<!運)動物|犬貓|寵物|魚病", n):
        return "animal_related"
    if re.search(r"火藥|植物病理|藥師七?佛|藥師山居士|佛醫宗|車輛職能", n):
        return "outside_medical_scope"
    if re.search(r"同學會|校友會|獎助學會", n) or not (
        SOCIETY.search(n) or PROFESSION.search(n)
    ):
        return ""
    if MEDICAL_SIGNAL.search(n):
        return "name_candidate"
    if classification(n):
        return "adjacent_name"
    return "other_society_name"


def records(path, delimiter="\t"):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


def write_table(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fields, delimiter="\t", lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def screen_registries(inputs, out, known_names):
    evidence = []
    snapshots = []
    for dataset_id, path in inputs:
        data = records(path, ",")
        expected_rows, expected_sha, download_url = SNAPSHOTS[dataset_id]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if len(data) != expected_rows or digest != expected_sha:
            raise ValueError(f"{path}: does not match the pinned {dataset_id} release")
        stats = Counter()
        seq = set()
        for record in data:
            name = record["Name"].strip()
            if not name or not record["SeqNo"] or record["SeqNo"] in seq:
                raise ValueError(
                    f"{path}: missing name or duplicate sequence {record['SeqNo']!r}"
                )
            seq.add(record["SeqNo"])
            scope = registry_scope(name)
            if (
                scope not in {"animal_related", "outside_medical_scope"}
                and normalized(name) in known_names
            ):
                scope = "linked_directory_name"
            stats[scope or "other_organization"] += 1
            if scope:
                evidence.append(
                    dict(
                        name=name,
                        dataset_id=dataset_id,
                        seq=record["SeqNo"],
                        screen=scope,
                    )
                )
        snapshots.append(
            dict(
                dataset_id=dataset_id,
                source_url=f"https://data.gov.tw/dataset/{dataset_id}",
                download_url=download_url,
                sha256=digest,
                bytes=path.stat().st_size,
                rows=len(data),
                screening=dict(sorted(stats.items())),
            )
        )
    write_table(
        out / "registry-screen.tsv", ["dataset_id", "seq", "name", "screen"], evidence
    )
    (out / "registry-snapshots.json").write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


SITE_CONFIRMED = {
    "identity_verified",
    "first_party_page_opened",
    "government_page_opened",
    "self_identified",
    "official_site_verified",
    "self_identified_on_site",
}
PUBLIC_PAPERS = {"public_questions_with_key", "public_questions", "sample_questions"}
EXAM_RANK = [
    "public_questions_with_key",
    "public_questions",
    "sample_questions",
    "public_assessment_form",
    "announcement",
    "regulations",
    "training_program",
    "members_only",
    "unverified",
    "unresolved",
    "",
]
SITE_LABELS = {
    "confirmed": "已核對主體",
    "directory": "名錄列址，待核對",
    "pending": "待查官網",
}


def organization_type(name):
    if "衛生福利部" in name or "衛生主管機關" in name:
        return "主管機關"
    if "公會" in name:
        return "公會"
    if "聯合會" in name or "聯盟" in name or "委員會" in name or "基金會" in name:
        return "聯合組織／其他機構"
    if "學會" in name:
        return "學會"
    if "大學" in name and name.endswith("系"):
        return "大學學系"
    if "醫院" in name and name.endswith(("部", "科")):
        return "醫院科部"
    return "協會／其他專業組織"


def source_tables(root):
    observations = []
    for path in sorted((root / "sources").glob("*.tsv")):
        for r in records(path):
            if not r.get("name") or not r.get("source_url"):
                raise ValueError(f"{path}: missing organization or source URL")
            observations.append({**r, "source_file": path.name})
    return observations


def aliases_for(root):
    path = root / "aliases.tsv"
    return (
        {normalized(r["variant"]): r["canonical"] for r in records(path)}
        if path.exists()
        else {}
    )


def society_id(name, aliases):
    key = normalized(name)
    canonical = normalized(aliases.get(key, key))
    return "tw-soc-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def exam_sources(root, observations):
    aliases = aliases_for(root)
    rows = {}
    for r in observations:
        url = r.get("exam_url", "")
        kind = r.get("exam_evidence", "")
        if not url or kind in {"", "unverified", "unresolved"}:
            continue
        key = normalized(r["name"]), url, kind, r.get("exam_note", "")
        if key not in rows:
            rows[key] = dict(
                name=r["name"],
                society_id=society_id(r["name"], aliases),
                exam_evidence=kind,
                exam_url=url,
                exam_note=r.get("exam_note", ""),
                source_url=r["source_url"],
                locator=r["locator"],
                evidence_url=r.get("evidence_url", ""),
                evidence_sha256=r.get("evidence_sha256", ""),
                source_file=r["source_file"],
                source_id=r["source_id"],
            )
    write_table(
        root / "exam-sources.tsv",
        [
            "name",
            "society_id",
            "exam_evidence",
            "exam_url",
            "exam_note",
            "source_url",
            "locator",
            "evidence_url",
            "evidence_sha256",
            "source_file",
            "source_id",
        ],
        [rows[k] for k in sorted(rows)],
    )


def build(root, observations):
    aliases = aliases_for(root)
    canonical_names = {normalized(name): name for name in aliases.values()}

    def identity(name):
        key = normalized(name)
        return normalized(aliases.get(key, key))

    indexed = defaultdict(list)
    for r in observations:
        if registry_scope(r["name"]) in {"animal_related", "outside_medical_scope"}:
            continue
        indexed[identity(r["name"])].append(r)
    register = defaultdict(list)
    for r in records(root / "registry-screen.tsv"):
        if (
            r["screen"] in {"name_candidate", "linked_directory_name"}
            or identity(r["name"]) in indexed
        ):
            register[identity(r["name"])].append(r)
    current = defaultdict(list)
    for path in (root / "live-registry.tsv", root / "live-physician-associations.tsv"):
        if not path.exists():
            continue
        for r in records(path):
            key = identity(r["name"])
            if (
                key in indexed
                or key in register
                or registry_scope(r["name"]) == "name_candidate"
            ):
                current[key].append(r)
    combined = []
    for key in sorted(indexed.keys() | register.keys() | current.keys()):
        evidence = indexed[key]
        matches = register[key]
        live = current[key]
        names = [r["name"] for r in live + evidence + matches]
        name = canonical_names.get(key, names[0])
        groups = classification(key)
        if not groups:
            groups = [r["group"] for r in evidence if r.get("group")]
        groups = list(dict.fromkeys(groups or ["綜合及其他醫事領域"]))
        options = [
            r
            for r in evidence
            if r.get("website") and urlsplit(r["website"]).scheme in {"http", "https"}
        ]
        confirmed = [r for r in options if r.get("website_check") in SITE_CONFIRMED]
        preferred = (confirmed or options or [{}])[0]
        status = "confirmed" if confirmed else "directory" if options else "pending"
        exam = [
            r
            for r in evidence
            if r.get("exam_url") and r.get("exam_evidence") in EXAM_RANK[:-3]
        ]
        exam.sort(key=lambda r: EXAM_RANK.index(r["exam_evidence"]))
        best = exam[0] if exam else {}
        combined.append(
            dict(
                name=name,
                society_id=society_id(name, aliases),
                observed_names=" | ".join(dict.fromkeys(names)),
                group=groups[0],
                related_groups="｜".join(groups[1:]),
                org_type=organization_type(key),
                inclusion="directory_or_first_party"
                if evidence
                else "registry_name_candidate",
                website=preferred.get("website", "") if status == "confirmed" else "",
                directory_website=preferred.get("website", "")
                if status == "directory"
                else "",
                website_status=status,
                website_source=(
                    preferred.get("destination_url")
                    or (
                        preferred.get("website_evidence", "")
                        if preferred.get("website_evidence", "").startswith("https://")
                        else ""
                    )
                    or preferred.get("source_url", "")
                ),
                exam_evidence=best.get("exam_evidence", "unverified"),
                exam_url=best.get("exam_url", ""),
                exam_note=best.get("exam_note", ""),
                live_registry_status=" | ".join(
                    dict.fromkeys(r["status"] for r in live)
                ),
                live_registry_ids=" | ".join(
                    dict.fromkeys(
                        r.get("registry_id") or r.get("seq", "") for r in live
                    )
                ),
                sources=" | ".join(
                    dict.fromkeys(
                        r["source_file"] + "#" + r["source_id"] for r in evidence
                    )
                ),
                registry_refs=" | ".join(
                    r["dataset_id"] + "#" + r["seq"] for r in matches
                ),
            )
        )
    combined.sort(key=lambda r: (r["group"], r["name"]))
    write_table(root / "societies.tsv", list(combined[0]), combined)
    return combined


def markdown_url(url):
    return url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")


def write_directory(root, items):
    labels = {
        "public_questions_with_key": "公開試題與答案",
        "public_questions": "公開試題",
        "sample_questions": "公開樣題",
        "public_assessment_form": "公開臨床評量表",
        "announcement": "甄審或考試公告",
        "regulations": "甄審規定",
        "training_program": "訓練計畫",
        "members_only": "會員入口",
    }
    lines = [
        "# 按科別查臺灣醫學會及相關專業組織",
        "",
        "每個單位依主領域列一次。跨科標籤、登記名冊序號和逐筆來源可以在完整 TSV 查詢。名稱初篩的候選另有清單。",
        "",
        "[所有單位與科別](societies.tsv) · [全部已定位的考試資料](exam-sources.tsv) · [來源及收錄範圍](README.md)",
        "",
    ]
    groups = defaultdict(list)
    for r in items:
        groups[r["group"]].append(r)
    totals = Counter(r["website_status"] for r in items)
    society_count = sum(r["org_type"] == "學會" for r in items)
    lines += [
        f"共 {len(groups):,} 個領域、{len(items):,} 個組織名稱，其中 {society_count:,} 個列為學會。"
        f"{totals['confirmed']:,} 個單位已核對網站身分，{totals['directory']:,} 個有候選網址，"
        f"{totals['pending']:,} 個待查網址。",
        "",
    ]
    lines += ["| 跳至科別 | 名錄單位 | 已核對網站身分 |", "|---|---:|---:|"]
    for number, (group, grouped) in enumerate(groups.items(), start=1):
        verified = sum(r["website_status"] == "confirmed" for r in grouped)
        lines.append(f"| [{group}](#field-{number}) | {len(grouped)} | {verified} |")
    lines.append("")
    for number, (group, grouped) in enumerate(groups.items(), start=1):
        historical = [
            r
            for r in grouped
            if r["live_registry_status"] and r["live_registry_status"] != "已立案"
        ]
        current = [
            r
            for r in grouped
            if not r["live_registry_status"] or r["live_registry_status"] == "已立案"
        ]
        rows = sorted(
            (r for r in current if r["inclusion"] != "registry_name_candidate"),
            key=lambda r: (
                r["org_type"] != "學會",
                ("confirmed", "directory", "pending").index(r["website_status"]),
                r["name"],
            ),
        )
        candidates = [
            r["name"] for r in current if r["inclusion"] == "registry_name_candidate"
        ]
        lines += [f'<a id="field-{number}"></a>', "", f"## {group}", ""]
        if rows:
            lines += ["| 團體名稱 | 種類 | 官網 | 公開考試資料 |", "|---|---|---|---|"]
        for r in rows:
            url = r["website"] or r["directory_website"]
            link = (
                f"[{SITE_LABELS[r['website_status']]}]({markdown_url(url)})"
                if url
                else "待查"
            )
            evidence = r["exam_evidence"]
            exam = (
                f"[{labels.get(evidence, evidence)}]({markdown_url(r['exam_url'])})"
                if r["exam_url"]
                else "待查"
            )
            lines.append(
                f"| {r['name'].replace('|', '／')} | {r['org_type']} | {link} | {exam} |"
            )
        lines.append("")
        if candidates:
            lines += [
                "<details>",
                f"<summary>登記名稱初篩，待核對專業範圍與官網（{len(candidates)}）</summary>",
                "",
            ]
            lines.extend("- " + name for name in candidates)
            lines += ["", "</details>", ""]
        if historical:
            lines += [
                "<details>",
                "<summary>內政部登記為解散、籌設或審查中</summary>",
                "",
            ]
            lines.extend(
                f"- {r['name']}（{r['live_registry_status']}）" for r in historical
            )
            lines += ["", "</details>", ""]
    (root / "by-specialty.md").write_text(
        "\n".join(lines).rstrip() + "\n", encoding="utf-8"
    )


def coverage(root, rows):
    stats = []
    for group in sorted({r["group"] for r in rows}):
        group_rows = [r for r in rows if r["group"] == group]
        sites = Counter(r["website_status"] for r in group_rows)
        stats.append(
            dict(
                group=group,
                organizations=len(group_rows),
                societies=sum(r["org_type"] == "學會" for r in group_rows),
                live_registered=sum(
                    r["live_registry_status"] == "已立案" for r in group_rows
                ),
                live_dissolved=sum(
                    r["live_registry_status"] == "解散" for r in group_rows
                ),
                live_application=sum(
                    bool(r["live_registry_status"])
                    and r["live_registry_status"] not in {"解散", "已立案"}
                    for r in group_rows
                ),
                confirmed_websites=sites["confirmed"],
                candidate_websites=sites["directory"],
                without_website=sites["pending"],
                public_exam_or_sample=sum(
                    r["exam_evidence"] in PUBLIC_PAPERS for r in group_rows
                ),
            )
        )
    write_table(root / "coverage.tsv", list(stats[0]), stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT)
    parser.add_argument(
        "--registry-csv",
        action="append",
        metavar="DATASET_ID=PATH",
        help="re-screen original MOI CSVs (supply both datasets)",
    )
    args = parser.parse_args()
    evidence = source_tables(args.out)
    if args.registry_csv:
        inputs = [x.split("=", 1) for x in args.registry_csv]
        if sorted(n for n, _ in inputs) != ["13603", "147595"]:
            parser.error("supply a CSV for each of 13603 and 147595")
        screen_registries(
            [(n, Path(p)) for n, p in sorted(inputs)],
            args.out,
            {normalized(r["name"]) for r in evidence},
        )
    items = build(args.out, evidence)
    exam_sources(args.out, evidence)
    write_directory(args.out, items)
    coverage(args.out, items)
    print(
        json.dumps(
            dict(
                organizations=len(items),
                sources=len(evidence),
                websites=dict(Counter(r["website_status"] for r in items)),
                exam_evidence=dict(Counter(r["exam_evidence"] for r in items)),
            ),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
