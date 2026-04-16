from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.claude_signals import ClaudeSignalDiscovery
from app.config import get_settings
from app.models import Competitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test Claude article-backed signal discovery.")
    parser.add_argument("competitor", help="Competitor name to search")
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()

    settings = get_settings()
    discovery = ClaudeSignalDiscovery(
        max_budget_usd=settings.claude_max_budget_usd,
        timeout_seconds=settings.claude_timeout_seconds,
    )
    evidence = discovery.discover_evidence(Competitor(name=args.competitor), limit=args.limit)
    print(
        json.dumps(
            [item.model_dump(mode="json") for item in evidence],
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Claude signal discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
