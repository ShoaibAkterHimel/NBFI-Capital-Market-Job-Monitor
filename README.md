# Bangladesh Finance Job Monitor

A zero-subscription-cost job-monitoring starter kit for Bangladesh NBFIs and
capital-market intermediaries.

It:

1. refreshes the regulated-company master list from Bangladesh Bank, BSEC and CSE;
2. discovers likely career/job pages;
3. checks those pages every day;
4. reports **JOB FOUND**, **JOB NOT FOUND**, **MANUAL REVIEW**, **CHECK FAILED** or **BLOCKED**;
5. extracts probable job titles;
6. publishes a searchable static dashboard through GitHub Pages;
7. stores a CSV history.

## Why five statuses?

A failed request is not proof that no job exists. Keeping failures and blocked
pages separate prevents dangerous false negatives.

## Cost

The software uses Python and open-source packages. Run it in a **public GitHub
repository** with standard GitHub-hosted runners and publish `docs/` through
GitHub Pages. No paid API, database or web host is required.

## Setup

1. Create a public GitHub repository.
2. Upload this project's files.
3. Open **Settings → Pages**.
4. Set the source to **Deploy from a branch**, branch `main`, folder `/docs`.
5. Open the **Actions** tab and run “Daily finance-sector job scan” manually once.
6. Review `config/companies.csv`.
7. Correct missing or wrong `homepage_url`, `careers_url` or `check_url` values.
8. Set `render_mode`:
   - `auto`: requests first, browser fallback;
   - `requests`: simple HTML/PDF only;
   - `browser`: JavaScript-rendered site.
9. Keep `active=yes` only for companies you want checked.

The workflow is scheduled for 9:15 AM in `Asia/Dhaka`.

## Local test

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
python run_local.py
```

Open `docs/index.html`.

## Master-list coverage

The starter sources cover:

- Bangladesh Bank finance companies / NBFIs;
- BSEC merchant bankers;
- credit-rating agencies;
- asset-management companies;
- custodians;
- trustees;
- fund managers;
- market makers;
- CSE stock brokers / TREC holders;
- DSE TREC holders when the DSE page permits automated access.

The bootstrap process **merges** official-source results into
`config/companies.csv`; it does not erase career URLs you added manually.

## Important limitations

- Some websites publish vacancies only as images, Facebook posts, LinkedIn posts,
  or JavaScript widgets. Those may require a custom parser or manual review.
- CAPTCHA, login pages and anti-bot systems must not be bypassed.
- Website layouts change. A page that suddenly becomes unreadable is reported as
  `MANUAL REVIEW` or `CHECK FAILED`, not `JOB NOT FOUND`.
- Job-title detection is heuristic. Review the first few runs and add company-
  specific selectors or keywords for difficult websites.
- Respect each website's terms and `robots.txt`. The scanner makes a small number
  of polite requests and does not attempt to evade blocks.
- “All capital-market companies” can mean either regulated intermediaries or
  every listed issuer. This starter targets **regulated intermediaries**. Add
  listed issuers as another official source only when you deliberately want that
  much larger scope.

## Suggested maintenance

Review `data/source_errors.txt` weekly. Review all `MANUAL REVIEW`,
`CHECK FAILED`, and `BLOCKED` rows. When a company changes its domain, update the
CSV. The daily workflow commits `data/last_run.txt`, keeping a visible audit trail.

## Optional alerts

The dashboard is the default report. A later extension can send free Telegram
bot messages only when `new_titles` is non-empty. Keep bot credentials in GitHub
Actions secrets, never in the repository.
