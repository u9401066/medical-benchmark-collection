# /// script
# requires-python = ">=3.10"
# dependencies = ["lxml>=4.9"]
# ///
"""Extract the published names and outbound links from Taiwanese institutional directories.

Run with `uv run scripts/tw_society_directory.py --download` from the repo root.
Omit --download to reproduce from the cached source bytes.
"""

import argparse
import csv
import concurrent.futures
import hashlib
import ipaddress
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from lxml import etree, html


SOURCES = {
    "tami": ("台灣醫學資訊學會", "https://www.medinfo.org.tw/html/links.html"),
    "rsroc": ("中華民國放射線醫學會", "https://www.rsroc.org.tw/links/"),
    "gtma": ("臺中市大臺中醫師公會", "https://www.gtma.org.tw/good-link.php"),
    "tafm": ("台灣家庭醫學醫學會", "https://www.tafm.org.tw/ehc-tafm/s/w/web_link/web_link/02"),
    "tsim": ("台灣內科醫學會", "https://www.tsim.org.tw/ehc-tsim/s/w/webLink/UFLINKS?selColumnCode=LINK_ASS"),
    "tade": ("中華民國糖尿病衛教學會", "https://www.tade.org.tw/resources/"),
    "tda": ("台北市牙醫師公會", "https://www.tda.org.tw/doctor/links/"),
    "sop": ("台灣精神醫學會", "https://www.sop.org.tw/link/index.asp"),
    "tse": ("台灣心臟超音波學會", "https://tse2002.org.tw/links/"),
    "ctcn": ("耕莘健康管理專科學校護理科", "https://nurse.ctcn.edu.tw/html/p_008_01.htm"),
    "kna": ("高雄市護理師護士公會", "https://www.kna.org.tw/SiteLinkList"),
    "pain": ("台灣疼痛醫學會", "https://www.pain.org.tw/index.php/page_main/index/13"),
    "twsrt": ("中華民國醫事放射學會", "https://twsrt.org.tw/links"),
    "tastro": ("台灣放射腫瘤學會", "https://www.tastro.org.tw/webLinks/"),
    "tanp": ("台灣私立醫療機構護理業務協進會", "https://www.tanp.org.tw/?mode=link"),
    "tsitc": ("台灣免疫暨腫瘤學會", "https://www.tsitc.org.tw/link"),
}

# Only domestic professional sections. Some publishers mix these with hospital,
# overseas sister society, journal, vendor and search engine links on the same page.
SECTIONS = {
    "rsroc": ("專科醫學會", "學會(醫療相關)", "醫師公會"),
    "gtma": ("醫師公會連結", "醫學會相關連結", "醫事團體連結", "醫協會相關連結"),
    "tda": ("全聯會暨縣市公會網站連結", "各專科醫學會暨各友會網站連結"),
    "tastro": ("TJCC台灣癌症聯合學術年會主辦醫學會", "專科醫學會"),
}
BLOCKS = {
    "tade": ("相關醫學會網站", '//article//ul[@class="resources-list"]//a[@href]'),
    "tafm": ("醫學會、公會、協會及基金會", '//div[contains(@class,"LinkList")]//div[@class="title"]/a[@href]'),
    "tsim": ("相關醫學會與公會", '//*[@id="LinkList"]//a[@href]'),
    "sop": ("國內", '//*[@id="accordion02"]//a[@href]'),
    "ctcn": ("護理團體連結", '//td/a[@href] | //td//font//a[@href]'),
    "tse": ("國內醫學會", '//article[@id="links"]/h3[normalize-space()="國內醫學會"]/following-sibling::section[1]//a[@href]'),
    "kna": ("相關網站連結", '//ul[contains(@class,"list-group-flush")]/li/a[@href]'),
    "pain": ("國內相關團體", '//table//tr/td[2]/a[@href]'),
    "tanp": ("相關學、協、公會", '//table//tr/td[1]/a[@href]'),
    "twsrt": ("相關公學會", '//section[.//h2[normalize-space()="相關公學會"]]//ul/li/a[@href]'),
    "tsitc": ("友站連結", '//a[h3 or .//h3][@href]'),
}
FIELDS = ("source_id", "source_url", "name", "website", "locator", "section", "entity_type",
          "website_status", "raw_href", "website_check", "probe_url", "destination_url", "website_evidence",
          "destination_sha256", "checked_date", "exam_evidence", "exam_url", "exam_note", "source_sha256")
SHARED_HOSTS = {"sim.org.tw", "www.sim.org.tw", "www.shutien.org.tw", "www.nhri.org.tw",
                "www.uuu.to", "www.sinica.edu.tw"}


def compact(value):
    return " ".join(value.split())


def groups(source, doc):
    if source in SECTIONS:
        for section in SECTIONS[source]:
            blocks = doc.xpath('//ul[normalize-space(preceding-sibling::*[1])=$section]', section=section)
            if len(blocks) != 1:
                raise ValueError(f"{source}: cannot uniquely identify {section}")
            yield section, blocks[0].xpath('.//a[@href]')
    elif source == "tami":
        # The source itself spells its domestic directory anchor "comestic".
        section = ""
        active = False
        found_end = False
        for a in doc.xpath('//a'):
            marker = a.get("name", "")
            if marker == "abroad":
                found_end = True
                break
            if marker == "comestic":
                active = True
            if active and marker.isdigit():
                section = "國內醫學會 #" + marker
            if active and section and a.get("href", "").startswith(("http:", "https:")):
                yield section, [a]
        if not active or not found_end:
            raise ValueError("tami: domestic section boundaries missing")
    else:
        section, selector = BLOCKS[source]
        yield section, doc.xpath(selector)


def identity(value):
    no_acronym = re.sub(r"[（(][A-Za-z][A-Za-z0-9 .-]*[）)]$", "", value)
    return re.sub(r"\s|社團法人|財團法人", "", no_acronym).replace("臺", "台")


def classification(name):
    if "人口學會" in name:
        return "adjacent_discipline"
    if "基金會" in name or "策進會" in name:
        return "foundation"
    if "公會" in name:
        return "guild"
    if "協會" in name or "聯盟" in name:
        return "association"
    return "society"


def website_candidate(name, raw, source_url):
    url = urljoin(source_url, raw)
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme not in {"http", "https"} or not host:
        return "", "unsupported_link"
    if "雜誌" in name:
        return "", "journal_link"
    if "雲端學習" in name:
        return "", "learning_portal"
    if host in {"www.facebook.com", "zh-tw.facebook.com"}:
        return "", "social_profile"
    if identity(name) == "台灣放射腫瘤學會" and domain(url) == "rsroc.org.tw":
        return "", "different_society_domain"
    if identity(name) == "中華民國內分泌暨糖尿病學會":
        return "", "shared_portal_multiple_societies"
    try:
        ipaddress.ip_address(host)
        return "", "legacy_ip"
    except ValueError:
        pass
    if (host in SHARED_HOSTS or host.endswith((".edu.tw", ".gov.tw", ".hinet.net", ".pchome.com.tw",
            ".yahoo.com", ".kimo.com.tw", ".pixnet.net", ".yam.com", ".gcn.net.tw", ".url.tw",
            ".at-taiwan.com", ".sinica.edu.tw"))):
        return "", "hosted_or_directory_link_unconfirmed"
    for publisher, publisher_url in SOURCES.values():
        if identity(name) == identity(publisher) and host.removeprefix("www.") == urlsplit(publisher_url).hostname.removeprefix("www."):
            return url, "publisher_domain_crosscheck"
    return url, "directory_listed"


def extract(source, raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp950")
    doc = html.fromstring(text)
    source_url = SOURCES[source][1]
    digest = hashlib.sha256(raw).hexdigest()
    result = []
    for section, anchors in groups(source, doc):
        for a in anchors:
            name = compact(a.text_content())
            if source == "tda":
                name = compact(a.text or "")
            elif source == "pain":
                name = compact(a.xpath('ancestor::tr[1]/td[1]')[0].text_content())
            elif source == "twsrt":
                name = name.removesuffix("（開啟新視窗）").strip()
            elif source == "tsitc" and name.startswith(("AACR", "SITC", "ESMO", "ASCO")):
                continue
            elif source == "tafm":
                name = re.sub(r"^0[123]", "", name)
            elif source == "ctcn":
                # Word HTML splits a single organization name across adjacent anchors.
                cell = a.xpath('ancestor::td[1]')[0]
                links = cell.xpath('.//a[@href]')
                if len(links) > 1 and len({x.get("href") for x in links}) == 1:
                    if a != links[0]:
                        continue
                    name = "".join(compact(x.text_content()) for x in links)
            if not re.search("學會|公會|協會|基金會|聯盟|策進會|協進會", name):
                continue
            href = a.get("href")
            candidate, status = website_candidate(name, href, source_url)
            result.append(dict(source_id=source, source_url=source_url, name=name, website=candidate,
                               locator=doc.getroottree().getpath(a), section=section, entity_type=classification(name),
                               website_status=status, raw_href=href, source_sha256=digest, website_check="directory_only"))
    if not result:
        raise ValueError(f"{source}: no directory rows (check for maintenance pages or layout changes)")
    return result


def domain(url):
    return (urlsplit(url).hostname or "").removeprefix("www.")


def add_exam_metadata(records):
    # The observed association home page announces the exam and links post 1183
    # through an onclick handler. The two PDFs identify the publisher in full.
    for row in records:
        if identity(row["name"]) != "台灣醫學資訊學會" or domain(row["raw_href"]) != "medinfo.org.tw":
            continue
        home = "https://www.medinfo.org.tw/"
        row.update(
            website=home, website_check="identity_verified", website_status="homepage_and_publisher_exam",
            probe_url=home, destination_url=home, checked_date="2026-11-26",
            website_evidence="首頁標題「台灣醫資學會」及公告所連兩份試卷卷首「社團法人台灣醫學資訊學會」",
            destination_sha256="b10f11048300a53da148b372556509e068e8abf9686e72c91c11ecf5066f118c",
            exam_evidence="public_questions_with_key", exam_url="https://www.medinfo.org.tw/html/newsDetail.php?postid=1183",
            exam_note=(
                "2026-11-23 13:07:53 公告，公告 HTML SHA-256 ac58a0712c045231b8319d4da585d2c600e5ec9d511644138d81cc2af4f8935a。"
                "疑義截止 11/27 18:00。管理師 PDF 4 頁、50 題、題前有作答鍵，為公告時版本。"
                "https://my.medinfo.org.tw/forum/news_attach/1-261121_MIM_Q&A.pdf "
                "SHA-256 bbd3bcea2d1b70e210408781920cd502d03892326b065d4ebc5ba586fa452417。"
                "分析師 PDF 2 頁，6 道申論中前 2 題必答、餘 4 選 2，附件僅載題目。"
                "https://my.medinfo.org.tw/forum/news_attach/2-261121_MIA_Q.pdf "
                "SHA-256 f3ec3901542adf9d1b5d3399f4e37e8c5de33f1c8d0b468a9fefa59d2cf9f2cb。"
            ),
        )


class SameSiteRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https" or domain(req.full_url) != domain(newurl):
            raise ValueError("redirect requires separate identity check: " + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def web_identity(url, cache, allow_network):
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf8"))
    if not allow_network:
        return {}
    receipt = {"requested": url, "date": date.today().isoformat()}
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MedicalBenchmarkCollection/1.0)"})
        with build_opener(SameSiteRedirect()).open(req, timeout=9) as resp:
            receipt["destination"] = resp.geturl()
            body = resp.read(2_000_001)
            if len(body) > 2_000_000:
                raise ValueError("homepage exceeds 2 MB")
        try:
            page = body.decode("utf-8-sig")
        except UnicodeDecodeError:
            page = body.decode("cp950", errors="replace")
        tree = html.fromstring(page)
        labels = []
        for xp in ('//title/text()', '//meta[@property="og:site_name"]/@content', '//h1',
                   '//a[contains(@class,"logo")]/@title', '//img[contains(@class,"logo")]/@alt'):
            for element in tree.xpath(xp):
                text = compact(element if isinstance(element, str) else element.text_content())
                if text and len(text) <= 200 and text not in labels:
                    labels.append(text)
        receipt.update(labels=labels, sha256=hashlib.sha256(body).hexdigest())
    except (OSError, ValueError, etree.ParserError) as error:
        receipt["error"] = str(error)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf8")
    return receipt


def compare_websites(records, cache, allow_network):
    # Probe the public home page independently of the publisher's historical
    # HTTP path. The exact href and directory locator remain in their own fields.
    probes = {}
    for r in records:
        if r["website"]:
            host = urlsplit(r["website"]).hostname
            r["probe_url"] = "https://" + host + "/"
            probes[r["probe_url"]] = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(web_identity, url, cache, allow_network): url for url in probes}
        for future in concurrent.futures.as_completed(futures):
            probes[futures[future]] = future.result()
    for r in records:
        receipt = probes.get(r.get("probe_url")) or {}
        if not receipt:
            continue
        r["checked_date"] = receipt["date"]
        r["destination_url"] = receipt.get("destination", "")
        r["destination_sha256"] = receipt.get("sha256", "")
        name = identity(r["name"])
        for label in receipt.get("labels", []):
            # Short labels such as 外科醫學會 would also match many subspecialties.
            if len(name) >= 6 and name in identity(label):
                r.update(website=receipt["destination"], website_check="identity_verified", website_evidence=label)
                break
        else:
            if receipt.get("labels"):
                r["website_evidence"] = receipt["labels"][0]
                r["website_status"] = "homepage_identity_not_matched"
                r["website"] = ""
            elif "redirect requires separate" in receipt.get("error",""):
                r["website_status"] = "redirect_requires_identity_check"
                r["destination_url"] = receipt["error"].split(": ", 1)[-1]
                r["website"] = ""


def fetch(source, path):
    url = SOURCES[source][1]
    try:
        with urlopen(Request(url, headers={"User-Agent": "MedicalBenchmarkCollection/1.0"}), timeout=75) as response:
            if urlsplit(response.geturl()).scheme != "https":
                raise ValueError("unexpected redirect from HTTPS")
            body = response.read()
    except OSError:
        body = subprocess.check_output([
            "curl", "--fail", "--silent", "--show-error", "--location", "--proto", "=https",
            "--proto-redir", "=https", "--connect-timeout", "15", "--max-time", "150", url,
        ])
    extract(source, body)
    path.write_bytes(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("data/tw-societies/directory"))
    parser.add_argument("--out", type=Path, default=Path("datasets/tw-societies/sources/directory.tsv"))
    parser.add_argument("--download", action="store_true", help="Download missing public directories")
    parser.add_argument("--check-sites", action="store_true", help="Fetch missing HTTPS home page identity receipts")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    records = []
    for source in SOURCES:
        path = args.cache / (source + ".html")
        if args.download and not path.exists():
            fetch(source, path)
        records.extend(extract(source, path.read_bytes()))
    compare_websites(records, args.cache / "sites", args.check_sites)
    add_exam_metadata(records)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    main()
