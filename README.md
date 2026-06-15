# displacement-radar

Displacement signal detection and outbound draft generation.
Built during the Apollo x Google Cloud Hackathon.

## What this repo does

This project helps a seller team:

- discover or enter competitors
- identify recent competitor signals from public sources
- find likely impacted accounts and buyer personas via Apollo
- generate draft outreach emails tied to those signals

## Preview screenshots from frontend
**Using the Apollo MCP to identify decision makers at potential customer companies (from auto-discovered displacement opportunities):**

<img width="1426" height="869" alt="email drafts" src="https://github.com/user-attachments/assets/443f75ca-24d2-46eb-b4f3-1da4175a9a7b" />

**Comprehensive competitive landscape report, generated from web-scraping, Claude-reviewed competitorrs, and Apollo GTM tools:**

<img width="1351" height="869" alt="competitive landscape" src="https://github.com/user-attachments/assets/f1a082db-8cd9-4910-a5f1-b2d91f18e0cd" />

**Opportunity graphs:**

<img width="1382" height="344" alt="change graph" src="https://github.com/user-attachments/assets/90d87c2c-d73a-4769-ac47-f1f4251f9359" />
<img width="401" height="261" alt="signal mix graph" src="https://github.com/user-attachments/assets/badf4030-3a86-440a-85a6-cf72aa94e697" />

**Competitive landscape visualizations:**

<img width="1054" height="456" alt="account map" src="https://github.com/user-attachments/assets/96f098ee-a27a-4cb3-9d1b-5dbbcc796b33" />


## Current repo layout

- `apollo_hackathon/` - main FastAPI app and tests
- `apollo_hackathon_cursor/` - parallel Cursor-oriented variant
- `aahan/` - earlier Node/React prototype

If you want one canonical app to run today, start with `apollo_hackathon/`.

## Main workflow (apollo_hackathon)

1. Enter your company and product.
2. Add competitors manually or use model-assisted competitor discovery.
3. Run a scan to collect and rank competitor signals.
4. Build opportunities and find impacted prospects.
5. Generate outreach drafts for selected contacts.
6. Review/edit before any external action.

- 
## Quickstart (main app)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apollo_hackathon/requirements.txt
uvicorn apollo_hackathon.app.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Configuration

Copy and fill values from:

- `apollo_hackathon/.env.example`

Key variables in `apollo_hackathon/.env.example`:

- `APOLLO_API_KEY` - Apollo account/contact lookup
- `OPENAI_API_KEY` - OpenAI web-search prospecting
- `CLAUDE_MCP_CONFIG` - path to MCP config file
- `PREFER_CLAUDE_MCP_PROSPECTING` - toggle Claude MCP prospecting path
- `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `VERTEX_MODEL` - Vertex/Gemini options
- `DATA_PATH` / `SEED_DATA_PATH` - local app data and seed snapshot

## Testing

```bash
pytest
```

`pyproject.toml` is configured to run tests under `apollo_hackathon/tests`.
