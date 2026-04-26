# displacement-radar

Displacement signal detection and outbound draft generation.
Built during the Apollo x Google Cloud Hackathon.

## What this repo does

This project helps a seller team:

- discover or enter competitors
- identify recent competitor signals from public sources
- find likely impacted accounts and buyer personas
- generate draft outreach emails tied to those signals

The core focus is speed-to-draft with human review, not fully automated outbound.

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

## What is implemented today

- FastAPI web app with HTML templates
- competitor and signal management
- displacement relationship graph output at `/graph/displacement.json`
- markdown + Mermaid competitive landscape reports
- optional Apollo account/contact lookup
- optional OpenAI web-search prospecting
- optional Claude MCP-assisted discovery/prospecting
- optional Vertex/Gemini grounding for live signal discovery

## What is not accurate to claim right now

- no Gmail API delivery flow in this codebase
- no dedicated browser-scraping pipeline (the app primarily uses model-assisted web discovery/grounding)

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
- `aahan/backend/.env.example` (only if you run the prototype)

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

## Notes before publishing

- keep real API keys out of git (only commit `.env.example`)
- generated prospect/contact data may be sensitive; avoid committing local data artifacts