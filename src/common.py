from __future__ import annotations

import hashlib
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

USER_AGENT = (
    "BD-Finance-Job-Monitor/1.0 "
    "(personal non-commercial vacancy checker; one request per page per day)"
)
DEFAULT_TIMEOUT = 25
_last_domain_request: dict[str, float] = {}


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int | None
    content_type: str
    text: str
    error: str = ""
    used_browser: bool = False


def clean_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_name(value: str) -> str:
    value = clean_space(value).lower()
    value = re.sub(r"\b(plc|limited|ltd|company|co)\b\.?", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def normalize_url(value: str, base: str = "") -> str:
    value = clean_space(value)
    if not value:
        return ""
    if value.startswith("www."):
        value = "https://" + value
    if base:
        value = urljoin(base, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return parsed._replace(fragment="").geturl()


def same_domain(a: str, b: str) -> bool:
    da = urlparse(a).netloc.lower().removeprefix("www.")
    db = urlparse(b).netloc.lower().removeprefix("www.")
    return bool(da and db and (da == db or da.endswith("." + db) or db.endswith("." + da)))


def polite_pause(url: str, minimum_seconds: float = 0.8) -> None:
    domain = urlparse(url).netloc.lower()
    now = time.monotonic()
    previous = _last_domain_request.get(domain, 0)
    delay = minimum_seconds - (now - previous)
    if delay > 0:
        time.sleep(delay)
    _last_domain_request[domain] = time.monotonic()


def robots_allowed(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(USER_AGENT, url), robots_url
    except Exception:
        # A missing/unreachable robots file is not treated as a prohibition.
        return True, robots_url


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def fetch_requests(url: str) -> FetchResult:
    allowed, robots_url = robots_allowed(url)
    if not allowed:
        return FetchResult(
            ok=False,
            url=url,
            status_code=None,
            content_type="",
            text="",
            error=f"Blocked by robots.txt: {robots_url}",
        )

    polite_pause(url)
    try:
        response = requests.get(
            url,
            timeout=DEFAULT_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9,bn;q=0.7",
            },
            allow_redirects=True,
        )
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code >= 400:
            return FetchResult(
                False, response.url, response.status_code, content_type, "",
                f"HTTP {response.status_code}",
            )
        if "pdf" in content_type or response.url.lower().endswith(".pdf"):
            text = _extract_pdf_text(response.content)
        else:
            response.encoding = response.encoding or "utf-8"
            text = response.text
        return FetchResult(True, response.url, response.status_code, content_type, text)
    except Exception as exc:
        return FetchResult(False, url, None, "", "", f"{type(exc).__name__}: {exc}")


def fetch_browser(url: str) -> FetchResult:
    allowed, robots_url = robots_allowed(url)
    if not allowed:
        return FetchResult(
            ok=False, url=url, status_code=None, content_type="", text="",
            error=f"Blocked by robots.txt: {robots_url}", used_browser=True
        )
    polite_pause(url)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            response = page.goto(url, wait_until="networkidle", timeout=45_000)
            text = page.content()
            final_url = page.url
            status = response.status if response else None
            browser.close()
        return FetchResult(
            ok=bool(status is None or status < 400),
            url=final_url,
            status_code=status,
            content_type="text/html",
            text=text,
            error="" if status is None or status < 400 else f"HTTP {status}",
            used_browser=True,
        )
    except Exception as exc:
        return FetchResult(
            False, url, None, "", "", f"{type(exc).__name__}: {exc}", True
        )


def fetch_page(url: str, render_mode: str = "auto") -> FetchResult:
    if render_mode == "browser":
        return fetch_browser(url)

    result = fetch_requests(url)
    if render_mode == "requests" or not result.ok:
        return result

    if "html" in result.content_type or "<html" in result.text[:1000].lower():
        visible = html_to_visible_text(result.text)
        # Very little visible text often means a JavaScript shell.
        if len(visible) < 180:
            browser_result = fetch_browser(url)
            if browser_result.ok:
                return browser_result
    return result


def html_to_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return clean_space(soup.get_text(" ", strip=True))


def soup_from_result(result: FetchResult) -> BeautifulSoup:
    return BeautifulSoup(result.text, "html.parser")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def unique_preserve(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = clean_space(value).lower()
        if key and key not in seen:
            seen.add(key)
            output.append(clean_space(value))
    return output
