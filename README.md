# displacement-radar

Draft-only competitor displacement intelligence for seller teams.
Built during the Apollo x Google Cloud Hackathon.

## What It Does

`displacement-radar` helps a seller team turn competitor pain signals into reviewed outbound drafts.

- Discover or enter competitors.
- Identify recent competitor signals from public sources.
- Map signals to likely affected accounts and buyer personas.
- Use Apollo to find decision makers and contact data.
- Generate evidence-backed outreach drafts for human review.

The product boundary is intentionally draft-only: it does not send emails, create Gmail messages, or enroll contacts in sequences without external human action.

## Main Workflow

1. Enter your company and product.
2. Add competitors manually or use model-assisted competitor discovery.
3. Run a scan to collect and rank competitor signals.
4. Review signal-backed opportunities and impacted accounts.
5. Select decision makers found through Apollo.
6. Generate draft outreach for selected contacts.
7. Review, edit, and approve any external action outside the app.

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


## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r apollo_hackathon/requirements.txt
uvicorn apollo_hackathon.app.main:app --reload
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The canonical app lives in `apollo_hackathon/`.

## Configuration

Copy and fill values from:

- `apollo_hackathon/.env.example`

Key variables:

- `APOLLO_API_KEY` - Apollo account/contact lookup.
- `OPENAI_API_KEY` - OpenAI web-search prospecting.
- `CLAUDE_MCP_CONFIG` - path to a Claude MCP config file.
- `PREFER_CLAUDE_MCP_PROSPECTING` - prefer Claude MCP prospecting when configured.
- `CLAUDE_DRAFT_EMAILS` - use Claude for draft email generation when configured.
- `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `VERTEX_MODEL` - Vertex/Gemini options.
- `DATA_PATH` / `SEED_DATA_PATH` - local app data and seed snapshot paths.

## Testing

```bash
pytest
```

`pyproject.toml` is configured to run tests under `apollo_hackathon/tests`.
