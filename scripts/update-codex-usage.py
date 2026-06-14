#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def compact(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def latest_usage_for_session(path: Path) -> tuple[dict | None, str | None]:
    latest = None
    latest_at = None

    with path.open(errors="ignore") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            payload = item.get("payload", {})
            if item.get("type") == "event_msg" and payload.get("type") == "token_count":
                latest = payload.get("info")
                latest_at = item.get("timestamp")

    return latest, latest_at


def main() -> None:
    today = datetime.now().astimezone()
    session_dir = Path.home() / ".codex" / "sessions" / f"{today:%Y}" / f"{today:%m}" / f"{today:%d}"
    readme = Path("README.md")

    sessions = list(session_dir.glob("*.jsonl")) if session_dir.exists() else []
    usage_rows = []

    for session in sessions:
        usage, updated_at = latest_usage_for_session(session)
        if usage and updated_at:
            usage_rows.append((parse_timestamp(updated_at), usage))

    usage_rows.sort(key=lambda row: row[0])
    latest = usage_rows[-1][1] if usage_rows else {}
    latest_time = usage_rows[-1][0] if usage_rows else datetime.now(timezone.utc)

    latest_total = latest.get("total_token_usage", {})
    latest_turn = latest.get("last_token_usage", {})
    tokens_today = sum(row[1].get("total_token_usage", {}).get("total_tokens", 0) for row in usage_rows)

    block = f"""<!-- CODEX-USAGE:START -->
<img src="https://img.shields.io/badge/Codex%20fan-always%20building-00C2FF?style=for-the-badge&logo=openai&logoColor=white" alt="Codex fan" />
<br />
<table>
  <tr>
    <td align="center"><b>{len(sessions)}</b><br /><sub>sessions today</sub></td>
    <td align="center"><b>{compact(tokens_today)}</b><br /><sub>tokens today</sub></td>
    <td align="center"><b>{compact(latest_total.get("total_tokens"))}</b><br /><sub>latest session</sub></td>
    <td align="center"><b>{compact(latest_turn.get("total_tokens"))}</b><br /><sub>last turn</sub></td>
  </tr>
</table>

<sub>input {compact(latest_total.get("input_tokens"))} | output {compact(latest_total.get("output_tokens"))} | reasoning {compact(latest_total.get("reasoning_output_tokens"))} | updated {latest_time:%Y-%m-%d %H:%M UTC}</sub>
<!-- CODEX-USAGE:END -->"""

    text = readme.read_text()
    next_text = re.sub(
        r"<!-- CODEX-USAGE:START -->.*?<!-- CODEX-USAGE:END -->",
        block,
        text,
        flags=re.S,
    )

    if next_text == text:
        raise SystemExit("Codex usage markers were not found in README.md")

    readme.write_text(next_text)


if __name__ == "__main__":
    main()
