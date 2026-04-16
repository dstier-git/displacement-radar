from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_settings
from .dependencies import get_agent, get_competitor_discovery, get_repository
from .claude_discovery import ClaudeCompetitorDiscovery
from .markdown_render import render_markdown_report
from .reports import CompetitiveLandscapeReportGenerator
from .services import DisplacementAgent
from .storage import Repository


APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="Competitor Displacement Agent", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    repo: Repository = Depends(get_repository),
) -> HTMLResponse:
    campaigns = repo.list_campaigns()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "company": repo.get_company_profile(),
            "competitors": repo.list_competitors(),
            "signals": repo.list_signals(),
            "opportunities": repo.list_opportunities(),
            "campaigns": campaigns,
            "scan_runs": repo.list_scan_runs(),
        },
    )


@app.post("/company/discover")
def discover_company(
    company_name: str = Form(...),
    agent: DisplacementAgent = Depends(get_agent),
    discovery: ClaudeCompetitorDiscovery = Depends(get_competitor_discovery),
) -> RedirectResponse:
    agent.discover_company(company_name, discovery)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/competitors")
def add_competitor(
    name: str = Form(...),
    category: str = Form(""),
    product_positioning: str = Form(""),
    technology_uid: str = Form(""),
    customer_domains: str = Form(""),
    agent: DisplacementAgent = Depends(get_agent),
) -> RedirectResponse:
    domains = [domain.strip() for domain in customer_domains.replace("\n", ",").split(",") if domain.strip()]
    agent.add_competitor(name, category, product_positioning, technology_uid or None, domains)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/scan")
def scan(agent: DisplacementAgent = Depends(get_agent)) -> RedirectResponse:
    agent.run_scan()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/scheduler/scan")
def scheduled_scan(
    x_scheduler_secret: str | None = Header(default=None),
    agent: DisplacementAgent = Depends(get_agent),
) -> dict[str, object]:
    settings = get_settings()
    if settings.scheduler_shared_secret and x_scheduler_secret != settings.scheduler_shared_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid scheduler secret")
    return agent.run_scan().model_dump(mode="json")


@app.get("/signals")
def list_signals(repo: Repository = Depends(get_repository)) -> list[dict]:
    return [signal.model_dump(mode="json") for signal in repo.list_signals()]


@app.get("/reports/competitive-landscape", response_class=HTMLResponse)
def rendered_competitive_landscape_report(
    request: Request, repo: Repository = Depends(get_repository)
) -> HTMLResponse:
    markdown = CompetitiveLandscapeReportGenerator(repo).generate()
    return templates.TemplateResponse(
        request,
        "report.html",
        {"request": request, "report_html": render_markdown_report(markdown)},
    )


@app.get("/reports/competitive-landscape.md")
def competitive_landscape_report(repo: Repository = Depends(get_repository)) -> PlainTextResponse:
    report = CompetitiveLandscapeReportGenerator(repo).generate()
    return PlainTextResponse(report, media_type="text/markdown; charset=utf-8")


@app.get("/opportunities/{opportunity_id}", response_class=HTMLResponse)
def opportunity_detail(
    opportunity_id: str,
    request: Request,
    repo: Repository = Depends(get_repository),
) -> HTMLResponse:
    opportunity = repo.get_opportunity(opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
    signal = repo.get_signal(opportunity.signal_id)
    campaigns = repo.list_campaigns(opportunity_id=opportunity.id)
    return templates.TemplateResponse(
        request,
        "opportunity.html",
        {
            "request": request,
            "opportunity": opportunity,
            "signal": signal,
            "campaigns": campaigns,
            "company": repo.get_company_profile(),
        },
    )


@app.post("/opportunities/{opportunity_id}/prospects")
def find_opportunity_prospects(
    opportunity_id: str,
    agent: DisplacementAgent = Depends(get_agent),
) -> RedirectResponse:
    try:
        agent.find_decision_makers(opportunity_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/opportunities/{opportunity_id}/emails")
async def generate_opportunity_emails(
    opportunity_id: str,
    request: Request,
    agent: DisplacementAgent = Depends(get_agent),
) -> RedirectResponse:
    form = await request.form()
    contact_ids = [str(item) for item in form.getlist("contact_ids")]
    try:
        agent.generate_emails_for_contacts(opportunity_id, contact_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return RedirectResponse(f"/opportunities/{opportunity_id}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def campaign_detail(
    campaign_id: str,
    request: Request,
    repo: Repository = Depends(get_repository),
) -> HTMLResponse:
    campaign = repo.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    opportunity = repo.get_opportunity(campaign.opportunity_id)
    signal = repo.get_signal(campaign.signal_id)
    return templates.TemplateResponse(
        request,
        "campaign.html",
        {"request": request, "campaign": campaign, "opportunity": opportunity, "signal": signal},
    )


@app.post("/campaigns/{campaign_id}/apollo-claude-prompt")
def apollo_claude_prompt(campaign_id: str, repo: Repository = Depends(get_repository)) -> PlainTextResponse:
    campaign = repo.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="campaign not found")
    return PlainTextResponse(campaign.apollo_claude_prompt)
