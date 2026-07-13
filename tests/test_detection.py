import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scan_jobs import classify, extract_titles_from_html


def test_positive_title():
    html = """
    <html><body>
      <h2>Senior Credit Risk Officer</h2>
      <a href="/apply">Apply Now</a>
    </body></html>
    """
    status, titles, _ = classify(html, "text/html")
    assert status == "JOB FOUND"
    assert "Senior Credit Risk Officer" in titles


def test_explicit_no_vacancy():
    html = "<html><body><p>There are no current openings.</p></body></html>"
    status, titles, _ = classify(html, "text/html")
    assert status == "JOB NOT FOUND"
    assert titles == []


def test_unclear_vacancy_signal_requires_review():
    html = "<html><body><p>We are hiring. Apply now.</p></body></html>"
    status, titles, _ = classify(html, "text/html")
    assert status == "MANUAL REVIEW"
    assert titles == []
