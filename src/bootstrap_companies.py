from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup

from common import (
    clean_space,
    fetch_page,
    normalize_name,
    normalize_url,
    unique_preserve,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES_FILE = ROOT / "config" / "sources.yaml"
COMPANIES_FILE = ROOT / "config" / "companies.csv"
SOURCE_ERRORS_FILE = ROOT / "data" / "source_errors.txt"

FIELDS = [
    "company_name", "category", "homepage_url", "careers_url", "check_url",
    "render_mode", "active", "notes",
]


def read_existing() -> dict[str, dict[str, str]]:
    if not COMPANIES_FILE.exists():
        return {}
    with COMPANIES_FILE.open(encoding="utf-8-sig", newline="") as handle:
        return {
            normalize_name(row["company_name"]): row
            for row in csv.DictReader(handle)
            if row.get("company_name")
        }


def looks_like_company(name: str) -> bool:
    name_l = name.lower()
    bad = {
        "home", "contact", "website", "details", "print", "font size",
        "read more", "stock brokers", "all stock brokers",
    }
    if name_l in bad or len(name) < 4 or len(name) > 160:
        return False
    company_words = (
        "limited", "ltd", "plc", "finance", "capital", "securities",
        "investment", "asset", "rating", "bank", "brokerage",
        "management", "company", "corporation",
    )
    return any(word in name_l for word in company_words)


def extract_urls(text: str) -> list[str]:
    raw = re.findall(
        r"(?:https?://|www\.)[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+",
        text,
        flags=re.I,
    )
    return [normalize_url(x.rstrip(".,);]")) for x in raw]


def parse_finance_company_links(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for a in soup.find_all("a", href=True):
        name = clean_space(a.get_text(" ", strip=True))
        href = normalize_url(a["href"], base_url)
        if looks_like_company(name) and href:
            rows.append({"company_name": name, "homepage_url": href})
    return rows


def parse_bsec_table(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    output = []

    # Preferred: actual HTML table rows.
    for tr in soup.find_all("tr"):
        cells = [clean_space(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        if re.fullmatch(r"\d+", cells[0]):
            name = cells[1]
            if looks_like_company(name):
                links = [
                    normalize_url(a.get("href", ""), base_url)
                    for a in tr.find_all("a", href=True)
                ]
                links += extract_urls(" ".join(cells))
                homepage = next((u for u in links if u and "sec.gov.bd" not in u), "")
                output.append({"company_name": name, "homepage_url": homepage})

    if output:
        return output

    # Fallback for pages whose visual table is not marked up normally.
    text = soup.get_text("\n", strip=True)
    lines = [clean_space(x) for x in text.splitlines() if clean_space(x)]
    for i, line in enumerate(lines[:-1]):
        if re.fullmatch(r"\d+", line):
            name = lines[i + 1]
            if looks_like_company(name):
                context = " ".join(lines[i + 1:i + 7])
                urls = extract_urls(context)
                output.append({
                    "company_name": name,
                    "homepage_url": next((u for u in urls if "sec.gov.bd" not in u), ""),
                })
    return output


def parse_cse_brokers(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    output = []
    for a in soup.find_all("a", href=True):
        name = clean_space(a.get_text(" ", strip=True))
        href = normalize_url(a["href"], base_url)
        if (
            looks_like_company(name)
            and any(k in name.lower() for k in ("securities", "capital", "brokerage", "shares"))
            and ("/stockbroker/" in href or "broker" in href.lower())
        ):
            output.append({"company_name": name, "homepage_url": href})
    return output


def parse_dse_brokers(html: str, base_url: str) -> list[dict[str, str]]:
    # The DSE page is sometimes protected. This works when normal HTML is returned.
    soup = BeautifulSoup(html, "html.parser")
    output = []
    for tr in soup.find_all("tr"):
        text = clean_space(tr.get_text(" ", strip=True))
        links = [normalize_url(a.get("href", ""), base_url) for a in tr.find_all("a", href=True)]
        candidates = [
            clean_space(c.get_text(" ", strip=True))
            for c in tr.find_all(["td", "a"])
        ]
        name = next((x for x in candidates if looks_like_company(x)), "")
        if name:
            homepage = next((u for u in links if u and "dsebd.org" not in u), "")
            output.append({"company_name": name, "homepage_url": homepage})
    return output


PARSERS = {
    "finance_company_links": parse_finance_company_links,
    "bsec_table": parse_bsec_table,
    "cse_brokers": parse_cse_brokers,
    "dse_brokers": parse_dse_brokers,
}


def merge_row(existing: dict[str, str] | None, discovered: dict[str, str], category: str, source: str) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    if existing:
        row.update(existing)
    row["company_name"] = discovered["company_name"]
    categories = [x.strip() for x in row.get("category", "").split("|") if x.strip()]
    if category not in categories:
        categories.append(category)
    row["category"] = " | ".join(categories)
    if not row.get("homepage_url") and discovered.get("homepage_url"):
        row["homepage_url"] = discovered["homepage_url"]
    row["render_mode"] = row.get("render_mode") or "auto"
    row["active"] = row.get("active") or "yes"
    note = row.get("notes", "")
    source_note = f"Master source: {source}"
    if source_note not in note:
        row["notes"] = "; ".join(x for x in [note, source_note] if x)
    return row


def main() -> None:
    existing = read_existing()
    merged = dict(existing)
    errors = []

    sources = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    for source in sources:
        if not source.get("active", True):
            continue
        parser = PARSERS[source["parser"]]
        result = fetch_page(source["url"], "requests")
        if not result.ok:
            errors.append(f'{source["name"]}: {result.error}')
            continue
        try:
            discovered_rows = parser(result.text, result.url)
            if not discovered_rows:
                errors.append(f'{source["name"]}: parser returned zero companies')
                continue
            for discovered in discovered_rows:
                key = normalize_name(discovered["company_name"])
                if not key:
                    continue
                merged[key] = merge_row(
                    merged.get(key), discovered, source["category"], source["name"]
                )
        except Exception as exc:
            errors.append(f'{source["name"]}: {type(exc).__name__}: {exc}')

    rows = sorted(merged.values(), key=lambda r: (r.get("category", ""), r["company_name"].lower()))
    with COMPANIES_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    SOURCE_ERRORS_FILE.write_text(
        "\n".join(errors) + ("\n" if errors else ""),
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} companies. Source warnings: {len(errors)}")


if __name__ == "__main__":
    main()
