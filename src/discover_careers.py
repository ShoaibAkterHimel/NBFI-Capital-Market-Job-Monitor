from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from common import clean_space, fetch_page, normalize_url, same_domain, unique_preserve

ROOT = Path(__file__).resolve().parents[1]
COMPANIES_FILE = ROOT / "config" / "companies.csv"

CAREER_TERMS = (
    "career", "careers", "job", "jobs", "vacancy", "vacancies",
    "recruitment", "join us", "work with us", "opportunity", "opportunities",
)
COMMON_PATHS = (
    "/career", "/careers", "/career-opportunities", "/jobs",
    "/vacancy", "/vacancies", "/recruitment",
)


def score_link(text: str, url: str) -> int:
    combined = f"{text} {url}".lower()
    score = 0
    for term in CAREER_TERMS:
        if term in combined:
            score += 3
    if any(x in combined for x in ("news", "tender", "investor", "product")):
        score -= 4
    return score


def discover(homepage: str, render_mode: str) -> tuple[str, str]:
    result = fetch_page(homepage, render_mode)
    if not result.ok:
        return "", f"Homepage check failed: {result.error}"
    soup = BeautifulSoup(result.text, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        text = clean_space(a.get_text(" ", strip=True))
        url = normalize_url(a["href"], result.url)
        if not url or not same_domain(homepage, url):
            continue
        score = score_link(text, url)
        if score > 0:
            candidates.append((score, url))
    candidates.sort(reverse=True)

    for _, url in candidates:
        check = fetch_page(url, render_mode)
        if check.ok:
            return check.url, "Career URL discovered from homepage"

    parsed = urlparse(result.url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    for path in COMMON_PATHS:
        url = urljoin(base, path)
        check = fetch_page(url, render_mode)
        if check.ok and check.status_code != 404:
            visible = BeautifulSoup(check.text, "html.parser").get_text(" ", strip=True).lower()
            if any(term in visible for term in CAREER_TERMS):
                return check.url, "Career URL discovered from common path"

    return "", "No career page discovered; homepage will be monitored"


def main() -> None:
    with COMPANIES_FILE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = handle.readline if False else None

    for i, row in enumerate(rows, 1):
        if row.get("active", "yes").lower() not in {"yes", "true", "1"}:
            continue
        if row.get("check_url") or row.get("careers_url"):
            continue
        homepage = row.get("homepage_url", "").strip()
        if not homepage:
            row["notes"] = "; ".join(
                x for x in [row.get("notes", ""), "Manual review: homepage missing"] if x
            )
            continue
        career_url, note = discover(homepage, row.get("render_mode", "auto"))
        if career_url:
            row["careers_url"] = career_url
            row["check_url"] = career_url
        else:
            row["check_url"] = homepage
        if note not in row.get("notes", ""):
            row["notes"] = "; ".join(x for x in [row.get("notes", ""), note] if x)
        print(f"[{i}/{len(rows)}] {row['company_name']}: {career_url or homepage}")

    fieldnames = [
        "company_name", "category", "homepage_url", "careers_url", "check_url",
        "render_mode", "active", "notes",
    ]
    with COMPANIES_FILE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
