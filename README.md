# TruthLens

**Track:** Track 2 — Real-World AI Products  
**Hackathon ID:** AZIS-D2USKN  
**Live URL:** [To be added after deployment]

TruthLens is a public misinformation-triage application. It helps readers and reviewers organize submitted claims, notice simple risk signals, and make review status and context visible. Risk flags are triage signals; they do not determine whether a claim is true.

## Problem

Claims shared online can use urgent or sensational language, be written in all caps, or lack a source link. These signals can make it harder for people to decide what deserves attention. TruthLens records claims as submitted and gives the public a clear view of their risk signals and review status.

## Features

- **Submit a claim:** Enter claim text, source platform (WhatsApp, X, Instagram, or Other), category (Politics, Health, Finance, or Other), and optionally a source URL.
- **Automatic risk flags:** The server flags claims containing “breaking,” “shocking,” or “share before deleted”; claims with more than half of alphabetic characters uppercase; and claims without a source URL. Two or more flags make a claim high risk.
- **Review workflow:** Reviewers can set a claim to Verified True, Verified False, or Misleading and add a reviewer note. New claims start as Unverified.
- **Public feed and filters:** All claims, including unverified claims, are public. The feed can be filtered by category and status and prioritizes risk and review status before recency.
- **Claim detail view:** View the full submitted text, platform, category, risk information, status, reviewer note, and submission time.

No authentication or demo credentials are required. The review interface is public.

## Technology stack

- Python 3
- Flask
- SQLite
- Jinja templates, HTML, CSS, and browser JavaScript
- pytest

## How it works

The browser submits a claim to the Flask application. The server validates the input, calculates deterministic risk flags, and stores the claim and review fields in SQLite. The public feed and detail pages display the stored claim, its flags, and its status; the review page lets a reviewer update status and note. The original claim text is preserved during review.

## Run locally

From the project root, create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` instead. Start the application:

```bash
python app.py
```

Open <http://127.0.0.1:5000>. By default, the database is created at `instance/truthlens.sqlite3`. Set `TRUTHLENS_DATABASE` to use a different SQLite file path.

## Tests

Run the risk, API, and page tests with:

```bash
python -m pytest -q tests/test_risk.py tests/test_api.py tests/test_pages.py
```

**Test result:** 42 passed, 0 failed, 0 errors.

## API summary

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/claims` | Create a claim. JSON fields: `claim_text`, `source_platform`, `category`, and optional `source_url`. Risk is calculated by the server. |
| `GET` | `/api/claims` | List claims. Optional query parameters: `category` and `status`. Returns `{claims, count}`. |
| `GET` | `/api/claims/<claim_id>` | Retrieve one claim and its details. |
| `PATCH` | `/api/claims/<claim_id>` | Review a claim with required `status` and optional `reviewer_note`. Only those review fields can be changed. |

Claim statuses are `unverified`, `verified_true`, `verified_false`, and `misleading`. The browser pages are `/` (feed), `/submit`, `/claims/<claim_id>` (detail), and `/review`.

## Deployment

TruthLens has not been deployed yet. For a public deployment, use a Python host with a persistent disk or volume: SQLite stores data in a file, so an ephemeral filesystem may lose claims during restarts or redeployments. Configure the application entry point as `app:app`, install the requirements, run it with a production WSGI server, and set `TRUTHLENS_DATABASE` to a database file on the persistent volume. A production WSGI server is not currently listed in `requirements.txt` and must be supplied by the deployment configuration.

**Live URL:** [To be added after deployment]
