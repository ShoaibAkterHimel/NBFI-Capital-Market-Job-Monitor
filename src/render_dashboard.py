from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    latest_file = ROOT / "data" / "latest.json"
    if not latest_file.exists():
        data = {
            "generated_at": "Not run yet",
            "summary": {
                "JOB FOUND": 0, "JOB NOT FOUND": 0, "MANUAL REVIEW": 0,
                "CHECK FAILED": 0, "BLOCKED": 0, "TOTAL": 0,
            },
            "results": [],
        }
    else:
        data = json.loads(latest_file.read_text(encoding="utf-8"))

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("index.html.j2")
    html = template.render(data=data)
    (ROOT / "docs" / "index.html").write_text(html, encoding="utf-8")
    (ROOT / "docs" / "latest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
