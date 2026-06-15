# displacement-radar

Displacement signal detection and outbound draft generation.
Built during the Apollo x Google Cloud Hackathon.

## What this repo does

This project helps a seller team:

- discover or enter competitors
- identify recent competitor signals from public sources
- find likely impacted accounts and buyer personas via Apollo
- generate draft outreach emails tied to those signals

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
