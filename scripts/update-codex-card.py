#!/usr/bin/env python3
from __future__ import annotations

import json
import base64
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen
from xml.sax.saxutils import escape


USER_NAME = "Yoav Gal"
USER_HANDLE = "@yoav0gal"
GITHUB_AVATAR = "https://github.com/yoav0gal.png?size=160"


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compact(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def days(value: int) -> str:
    return f"{value} day" if value == 1 else f"{value} days"


def avatar_href() -> str:
    try:
        with urlopen(GITHUB_AVATAR, timeout=10) as response:
            encoded = base64.b64encode(response.read()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    except Exception:
        return GITHUB_AVATAR


def session_usage(path: Path) -> tuple[dict | None, datetime | None]:
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
                latest = payload.get("info", {})
                latest_at = parse_time(item.get("timestamp"))

    return latest, latest_at


def load_daily_usage() -> dict[date, int]:
    root = Path.home() / ".codex" / "sessions"
    daily: dict[date, int] = defaultdict(int)

    for path in root.glob("*/*/*/*.jsonl"):
        usage, updated_at = session_usage(path)
        if not usage or not updated_at:
            continue

        total = usage.get("total_token_usage", {}).get("total_tokens", 0)
        daily[updated_at.astimezone().date()] += int(total)

    return dict(daily)


def streaks(daily: dict[date, int], today: date) -> tuple[int, int]:
    active_days = {day for day, tokens in daily.items() if tokens > 0}
    current = 0
    cursor = today
    while cursor in active_days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    for day in sorted(active_days):
        previous = day - timedelta(days=1)
        run = run + 1 if previous in active_days else 1
        longest = max(longest, run)

    return current, longest


def color_for(tokens: int, peak: int) -> str:
    if tokens <= 0:
        return "#303030"
    ratio = tokens / max(peak, 1)
    if ratio >= 0.75:
        return "#3AA0FF"
    if ratio >= 0.45:
        return "#245C8C"
    if ratio >= 0.2:
        return "#1D456B"
    return "#173450"


def grid(daily: dict[date, int], today: date) -> str:
    cols = 26
    rows = 7
    size = 28
    gap = 6
    start = today - timedelta(days=(cols * rows - 1))
    peak = max(daily.values(), default=1)
    cells = []

    for col in range(cols):
        for row in range(rows):
            day = start + timedelta(days=col * rows + row)
            x = 64 + col * (size + gap)
            y = 192 + row * (size + gap)
            cells.append(
                f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="7" fill="{color_for(daily.get(day, 0), peak)}">'
                f"<title>{day.isoformat()}: {compact(daily.get(day, 0))} tokens</title></rect>"
            )

    return "\n".join(cells)


def stat(x: int, value: str, label: str) -> str:
    return f"""
  <text x="{x}" y="505" text-anchor="middle" fill="#ffffff" font-size="38" font-weight="800">{escape(value)}</text>
  <text x="{x}" y="548" text-anchor="middle" fill="#b9b9bd" font-size="28" font-weight="650">{escape(label)}</text>"""


def main() -> None:
    today = datetime.now().astimezone().date()
    daily = load_daily_usage()
    lifetime = sum(daily.values())
    peak_day = max(daily.values(), default=0)
    current, longest = streaks(daily, today)
    avatar = avatar_href()

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="998" height="612" viewBox="0 0 998 612" role="img" aria-label="Yoav Gal Codex usage card">
  <defs>
    <clipPath id="avatarClip"><circle cx="114" cy="115" r="50"/></clipPath>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="14" stdDeviation="22" flood-color="#000000" flood-opacity="0.35"/>
    </filter>
  </defs>
  <rect width="998" height="612" rx="62" fill="#181818" filter="url(#softShadow)"/>
  <image href="{avatar}" x="64" y="65" width="100" height="100" clip-path="url(#avatarClip)" preserveAspectRatio="xMidYMid slice"/>
  <circle cx="114" cy="115" r="50" fill="none" stroke="#2c2c2c" stroke-width="2"/>
  <text x="192" y="112" fill="#ffffff" font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="40" font-weight="800">{escape(USER_NAME)}</text>
  <text x="192" y="148" fill="#b9b9bd" font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="29" font-weight="700">{escape(USER_HANDLE)}</text>
  <g transform="translate(750 89)">
    <circle cx="25" cy="25" r="21" fill="none" stroke="#b9b9bd" stroke-width="4"/>
    <circle cx="25" cy="25" r="14" fill="none" stroke="#181818" stroke-width="7"/>
    <text x="49" y="39" fill="#c8c8cc" font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="37" font-weight="800">Codex</text>
  </g>
  <g font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
{grid(daily, today)}
  </g>
  <line x1="282" y1="469" x2="282" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <line x1="500" y1="469" x2="500" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <line x1="718" y1="469" x2="718" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <g font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
{stat(173, compact(lifetime), "lifetime tokens")}
{stat(391, compact(peak_day), "peak day")}
{stat(609, days(current), "current streak")}
{stat(827, days(longest), "longest streak")}
  </g>
</svg>
"""

    output = Path("assets/codex-profile-card.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg)


if __name__ == "__main__":
    main()
