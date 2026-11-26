"""Audit name-search leads against a site's own home page, retaining unresolved names."""

import argparse
import csv
import json
import unicodedata
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

if __package__:
    from .tw_society_directory import web_identity
else:
    from tw_society_directory import web_identity


def name_key(text):
    return (
        "".join(unicodedata.normalize("NFKC", text).split())
        .replace("臺", "台")
        .removeprefix("社團法人")
    )


def candidate_home(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    exclusions = (
        "gov.tw",
        "edu.tw",
        "org.cn",
        "wikipedia.org",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "google.com",
        "line.me",
        "beclass.com",
        "sanmin.com.tw",
        "wikipedia.com",
        "twincn.com",
        "findbiz.nat.gov.tw",
        "ngo.tw",
        "airitilibrary.com",
        "web66.com.tw",
        "ettoday.net",
        "yahoo.com",
        "kktix.cc",
        "kktix.com",
        "accupass.com",
        "assochub.org",
        "atlaq.com",
        "tw66.com.tw",
        "funcode.cyou",
    )
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or any(host == s or host.endswith("." + s) for s in exclusions)
    ):
        return ""
    if (
        host.replace(".", "").isdecimal()
        or ":" in host
        or parsed.username
        or parsed.password
    ):
        return ""
    if host.split(".")[0] in {"member", "mail", "annual", "learn"}:
        return ""
    return "https://" + host + "/"


def society_site_label(name, labels):
    # Event and service portals may also display the full publisher name.
    if any(
        term in label
        for label in labels
        for term in (
            "學會年會",
            "會員大會暨學術",
            "詢價官網",
            "線上課程平台",
            "輔助科技資訊平台",
        )
    ):
        return ""
    key = name_key(name)
    return next(
        (label for label in labels if len(key) >= 6 and key in name_key(label)), ""
    )


def audit(root, cache, fetch):
    attempts = defaultdict(list)
    for batch in sorted(cache.glob("b*.json")):
        for row in json.loads(batch.read_text(encoding="utf-8")):
            attempts[row["name"]].append(row)
    searches = [
        dict(
            name=name,
            query_status="searched"
            if any(r["query_status"] == "searched" for r in runs)
            else "search_unavailable",
            matches=list(
                dict.fromkeys(tuple(match) for r in runs for match in r["matches"])
            ),
        )
        for name, runs in attempts.items()
    ]
    candidates = {
        r["name"]: list(
            dict.fromkeys(
                home for _, url in r["matches"] if (home := candidate_home(url))
            )
        )
        for r in searches
    }
    urls = sorted({url for homes in candidates.values() for url in homes})
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = dict(
            zip(
                urls,
                pool.map(lambda url: web_identity(url, cache / "sites", fetch), urls),
            )
        )
    audit_rows, source_rows = [], []
    for row in searches:
        name = row["name"]
        evidence = []
        for url in candidates[name]:
            receipt = receipts[url]
            label = society_site_label(name, receipt.get("labels", []))
            if label and receipt.get("sha256"):
                evidence.append(
                    dict(
                        name=name,
                        source_id="site-identity",
                        source_url=receipt["destination"],
                        locator="首頁識別文字：" + label,
                        website=receipt["destination"],
                        website_check="identity_verified",
                        website_evidence=label,
                        source_sha256=receipt["sha256"],
                        checked_date=receipt["date"],
                    )
                )
        # Two independent homepages identifying as the same society warrant manual review.
        domains = {
            urlsplit(r["website"]).hostname.removeprefix("www.") for r in evidence
        }
        # A separately identified apex and its own subdomains share a publisher.
        preferred = [
            r
            for r in evidence
            if not any(
                urlsplit(r["website"]).hostname.endswith("." + d)
                and urlsplit(r["website"]).hostname.removeprefix("www.") != d
                for d in domains
            )
        ]
        domains = {
            urlsplit(r["website"]).hostname.removeprefix("www.") for r in preferred
        }
        if len(domains) == 1:
            status = "matched_homepage"
            source_rows.append(preferred[0])
        elif len(domains) > 1:
            status = "conflicting_homepages"
        else:
            status = (
                row["query_status"] if not candidates[name] else "no_verified_homepage"
            )
        audit_rows.append(
            dict(
                name=name,
                status=status,
                queries=len(attempts[name]),
                exact_title_hits=len(row["matches"]),
                homepages_checked=sum(bool(receipts[u]) for u in candidates[name]),
                candidate_homepages=" | ".join(candidates[name]),
                confirmed_homepages=" | ".join(r["website"] for r in evidence),
            )
        )

    def write(path, fields, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(sorted(data, key=lambda r: r["name"]))

    write(
        root / "name-search.tsv",
        [
            "name",
            "status",
            "queries",
            "exact_title_hits",
            "homepages_checked",
            "candidate_homepages",
            "confirmed_homepages",
        ],
        audit_rows,
    )
    write(
        root / "sources" / "verified-homepages.tsv",
        [
            "name",
            "source_id",
            "source_url",
            "locator",
            "website",
            "website_check",
            "website_evidence",
            "source_sha256",
            "checked_date",
        ],
        source_rows,
    )
    print(
        f"{len(audit_rows)} names, {len(urls)} candidate homepages, {len(source_rows)} identities matched"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=Path("data/tw-societies/name-search")
    )
    parser.add_argument("--out", type=Path, default=Path("datasets/tw-societies"))
    parser.add_argument("--check-sites", action="store_true")
    args = parser.parse_args()
    audit(args.out, args.cache, args.check_sites)
