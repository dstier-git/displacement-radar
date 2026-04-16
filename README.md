# Competitor Displacement Agent

Apollo × Google Cloud hackathon MVP that watches competitor bad-day signals and turns them into draft-only displacement campaigns.

## What it does

1. Tracks competitor watchlist entries.
2. Detects competitor signals such as pricing changes, outages, negative-review waves, executive departures, layoffs, and contract complaints.
3. Uses Apollo account/contact discovery to identify likely affected companies and buyer personas.
4. Scores opportunities and generates draft outreach: email, LinkedIn note, call opener, evidence links, and an Apollo Claude handoff prompt.
5. Keeps execution human-in-the-loop: no contacts are created and no sequences are enrolled by default.
6. Generates a markdown competitive landscape report with Mermaid graphs for the current market map and trailing-30-day changes.

## Stack

- FastAPI + Jinja for the hackathon UI
- Apollo REST API wrapper for organization/person search payloads
- Vertex AI Gemini seam for classification/copy generation, with deterministic demo fallback
- Cloud Run-ready container
- Cloud Scheduler-compatible `/scheduler/scan` endpoint
- JSON local store for local demos; Firestore is the intended production persistence target

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>, add competitors or use the seeded demo competitors, then click **Run scan**.
Use **Open rendered report** on the dashboard, visit `/reports/competitive-landscape` for rendered Mermaid graphs, or visit `/reports/competitive-landscape.md` to export the markdown landscape report.

## Configuration

Create `.env` or set environment variables:

```bash
APOLLO_API_KEY=your_apollo_key
GOOGLE_CLOUD_PROJECT=your-gcp-project
GOOGLE_CLOUD_LOCATION=global
VERTEX_MODEL=gemini-2.5-flash
SCHEDULER_SHARED_SECRET=replace-me
DEMO_MODE=true
DATA_PATH=.data/displacement-agent.json
```

`DEMO_MODE=true` keeps the app deterministic and avoids live Apollo/Gemini calls. Set it to `false` after wiring live Google Search grounding and validating Apollo filters for your target market.

## Apollo Claude MCP handoff

Apollo's Claude integration is user-authorized and approval-scoped, so this MVP treats it as a human review surface rather than a headless backend. Each generated campaign includes a prompt that asks Claude, with Apollo enabled, to verify the account and contacts and prepare a sequence draft without creating contacts or enrolling anyone until explicit approval.

## Cloud Run deploy sketch

```bash
gcloud run deploy displacement-agent \
  --source . \
  --region us-central1 \
  --set-env-vars APOLLO_API_KEY=...,GOOGLE_CLOUD_PROJECT=...,SCHEDULER_SHARED_SECRET=...
```

Create a scheduled scan:

```bash
gcloud scheduler jobs create http displacement-agent-scan \
  --schedule="*/30 * * * *" \
  --uri="https://SERVICE_URL/scheduler/scan" \
  --http-method=POST \
  --headers="x-scheduler-secret=YOUR_SECRET" \
  --oidc-service-account-email="SCHEDULER_SA@PROJECT.iam.gserviceaccount.com"
```

## Tests

```bash
pytest
```

Tests cover signal classification, Apollo query payload planning, draft-only Claude prompts, scan dedupe, and key web routes.
