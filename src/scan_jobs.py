from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from common import (
    clean_space,
    fetch_page,
    html_to_visible_text,
    sha256_text,
    unique_preserve,
)

ROOT = Path(__file__).resolve().parents[1]
COMPANIES_FILE = ROOT / "config" / "companies.csv"
LATEST_FILE = ROOT / "data" / "latest.json"
HISTORY_FILE = ROOT / "data" / "history.csv"
LAST_RUN_FILE = ROOT / "data" / "last_run.txt"

POSITIVE_PHRASES = (
    "apply now", "application deadline", "last date of application",
    "job circular", "current opening", "current openings", "open position",
    "open positions", "vacancy", "vacancies", "we are hiring",
    "join our team", "career opportunity", "career opportunities",
)
NEGATIVE_PHRASES = (
    "no vacancy", "no vacancies", "no current opening", "no current openings",
    "no job available", "no jobs available", "currently no vacancy",
    "there are no open positions", "no career opportunity",
)
ROLE_WORDS = (
    "officer", "manager", "analyst", "executive", "associate", "trainee",
    "head of", "chief", "specialist", "intern", "engineer", "developer",
    "accountant", "auditor", "dealer", "trader", "research", "compliance",
    "risk", "finance", "legal", "human resources", "hr ", "relationship",
    "portfolio", "operations", "credit", "treasury", "investment",
    "customer service", "company secretary", "business development",
)
GENERIC_LABELS = {
    "career", "careers", "job", "jobs", "vacancy", "vacancies",
    "apply now", "join us", "join our team", "career opportunities",
    "current openings", "current opening",
}


def plausible_title(text: str) -> bool:
    value = clean_space(text)
    lower = value.lower()
    if not (4 <= len(value) <= 150):
        return False
    if lower in GENERIC_LABELS:
        return False
    if any(negative in lower for negative in NEGATIVE_PHRASES):
        return False
    if len(value.split()) > 18:
        return False
    return any(word in lower for word in ROLE_WORDS)


def extract_titles_from_html(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    selectors = [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "a", "li", "td", "strong",
        "[class*='job']", "[class*='vacan']", "[class*='position']",
        "[id*='job']", "[id*='vacan']", "[id*='position']",
    ]
    for element in soup.select(",".join(selectors)):
        text = clean_space(element.get_text(" ", strip=True))
        if plausible_title(text):
            candidates.append(text)

    # Also detect labels such as "Position: Senior Officer".
    visible = html_to_visible_text(html)
    for match in re.finditer(
        r"(?:position|designation|job title)\s*[:\-]\s*([^|•]{4,120})",
        visible,
        flags=re.I,
    ):
        title = clean_space(match.group(1))
        if plausible_title(title):
            candidates.append(title)

    # Remove obvious duplicated parent/child text.
    output = []
    for candidate in unique_preserve(candidates):
        lc = candidate.lower()
        if any(lc != x.lower() and lc in x.lower() for x in candidates):
            continue
        output.append(candidate)
    return output[:30]


def extract_titles_from_text(text: str) -> list[str]:
    candidates = []
    for line in re.split(r"[\r\n•|]+", text):
        line = clean_space(line)
        if plausible_title(line):
            candidates.append(line)
    return unique_preserve(candidates)[:30]


def classify(content: str, content_type: str) -> tuple[str, list[str], str]:
    lower = content.lower()
    negative_hits = [p for p in NEGATIVE_PHRASES if p in lower]
    positive_hits = [p for p in POSITIVE_PHRASES if p in lower]

    if "html" in content_type or "<html" in content[:1000].lower():
        titles = extract_titles_from_html(content)
        visible = html_to_visible_text(content)
    else:
        titles = extract_titles_from_text(content)
        visible = clean_space(content)

    if titles:
        return "JOB FOUND", titles, f"Detected {len(titles)} probable title(s)"
    if negative_hits:
        return "JOB NOT FOUND", [], f"Negative notice detected: {negative_hits[0]}"
    if positive_hits:
        # A positive signal with no clear title is safer as manual review.
        return "MANUAL REVIEW", [], f"Vacancy signal detected but title was unclear: {positive_hits[0]}"
    if len(visible) < 80:
        return "MANUAL REVIEW", [], "Page contained too little readable text"
    return "JOB NOT FOUND", [], "No vacancy signal or probable job title detected"


def read_previous() -> dict[str, dict]:
    if not LATEST_FILE.exists():
        return {}
    try:
        data = json.loads(LATEST_FILE.read_text(encoding="utf-8"))
        return {x["company_name"]: x for x in data.get("results", [])}
    except Exception:
        return {}


def append_history(results: list[dict], run_at: str) -> None:
    fields = [
        "run_at", "company_name", "category", "status", "titles",
        "new_titles", "check_url", "http_status", "error",
    ]
    exists = HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for result in results:
            writer.writerow({
                "run_at": run_at,
                "company_name": result["company_name"],
                "category": result["category"],
                "status": result["status"],
                "titles": " | ".join(result["titles"]),
                "new_titles": " | ".join(result["new_titles"]),
                "check_url": result["check_url"],
                "http_status": result["http_status"],
                "error": result["error"],
            })


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Dhaka"))
    run_at = now.isoformat(timespec="seconds")
    previous = read_previous()

    with COMPANIES_FILE.open(encoding="utf-8-sig", newline="") as handle:
        companies = list(csv.DictReader(handle))

    results = []
    for index, company in enumerate(companies, 1):
        if company.get("active", "yes").lower() not in {"yes", "true", "1"}:
            continue

        url = (
            company.get("check_url", "").strip()
            or company.get("careers_url", "").strip()
            or company.get("homepage_url", "").strip()
        )
        base = {
            "company_name": company["company_name"],
            "category": company.get("category", ""),
            "homepage_url": company.get("homepage_url", ""),
            "careers_url": company.get("careers_url", ""),
            "check_url": url,
            "checked_at": run_at,
            "status": "CHECK FAILED",
            "titles": [],
            "new_titles": [],
            "reason": "",
            "http_status": "",
            "error": "",
            "used_browser": False,
            "content_hash": "",
        }

        if not url:
            base.update(
                status="MANUAL REVIEW",
                reason="No homepage or career URL is available",
            )
            results.append(base)
            continue

        fetched = fetch_page(url, company.get("render_mode", "auto") or "auto")
        base["http_status"] = fetched.status_code or ""
        base["used_browser"] = fetched.used_browser
        if not fetched.ok:
            status = "BLOCKED" if "robots.txt" in fetched.error else "CHECK FAILED"
            base.update(status=status, reason=fetched.error, error=fetched.error)
            results.append(base)
            print(f"[{index}/{len(companies)}] {company['company_name']}: {status}")
            continue

        status, titles, reason = classify(fetched.text, fetched.content_type)
        old_titles = set(previous.get(company["company_name"], {}).get("titles", []))
        new_titles = [title for title in titles if title not in old_titles]
        base.update(
            check_url=fetched.url,
            status=status,
            titles=titles,
            new_titles=new_titles,
            reason=reason,
            content_hash=sha256_text(clean_space(fetched.text)),
        )
        results.append(base)
        print(
            f"[{index}/{len(companies)}] {company['company_name']}: "
            f"{status} ({len(titles)} titles)"
        )

    summary = {
        "JOB FOUND": sum(r["status"] == "JOB FOUND" for r in results),
        "JOB NOT FOUND": sum(r["status"] == "JOB NOT FOUND" for r in results),
        "MANUAL REVIEW": sum(r["status"] == "MANUAL REVIEW" for r in results),
        "CHECK FAILED": sum(r["status"] == "CHECK FAILED" for r in results),
        "BLOCKED": sum(r["status"] == "BLOCKED" for r in results),
        "TOTAL": len(results),
    }
    payload = {"generated_at": run_at, "summary": summary, "results": results}
    LATEST_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LAST_RUN_FILE.write_text(run_at + "\n", encoding="utf-8")
    append_history(results, run_at)


if __name__ == "__main__":
    main()
