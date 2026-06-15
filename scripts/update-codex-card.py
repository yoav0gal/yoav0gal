#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape


USER_NAME = "Yoav Gal"
USER_HANDLE = "@yoav0gal"
GITHUB_AVATAR = "https://github.com/yoav0gal.png?size=160"
CHATGPT_BASE_URL = "https://chatgpt.com"
USAGE_ENDPOINT = "/backend-api/wham/usage"
DAILY_ENDPOINT = "/backend-api/wham/usage/daily-token-usage-breakdown"
CACHE_PATH = Path("assets/codex-usage-cache.json")


def compact(value: float, suffix: str = "") -> str:
    if value >= 1_000_000_000:
        text = f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        text = f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        text = f"{value / 1_000:.1f}K"
    elif value >= 100:
        text = f"{value:.0f}"
    elif value >= 10:
        text = f"{value:.1f}"
    else:
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def days(value: int) -> str:
    return f"{value} day" if value == 1 else f"{value} days"


def avatar_href() -> str:
    try:
        with urlopen(GITHUB_AVATAR, timeout=10) as response:
            encoded = base64.b64encode(response.read()).decode("ascii")
            return f"data:image/png;base64,{encoded}"
    except Exception:
        return GITHUB_AVATAR


def read_access_token() -> str | None:
    if token := os.environ.get("CODEX_ACCESS_TOKEN"):
        return token

    auth_json = os.environ.get("CODEX_AUTH_JSON")
    if auth_json:
        try:
            auth = json.loads(auth_json)
            return auth.get("tokens", {}).get("access_token") or auth.get("access_token")
        except json.JSONDecodeError:
            return None

    auth_path = Path.home() / ".codex" / "auth.json"
    if auth_path.exists():
        try:
            auth = json.loads(auth_path.read_text())
            return auth.get("tokens", {}).get("access_token")
        except (OSError, json.JSONDecodeError):
            return None

    return None


def get_json(path: str, token: str) -> dict:
    request = Request(
        CHATGPT_BASE_URL + path,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Referer": "https://chatgpt.com/codex/cloud/settings/usage",
            "User-Agent": "Mozilla/5.0 Codex profile card",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def public_rate_limit(data: dict) -> dict:
    rate_limit = data.get("rate_limit") or {}
    return {
        "allowed": rate_limit.get("allowed"),
        "limit_reached": rate_limit.get("limit_reached"),
        "primary_window": rate_limit.get("primary_window"),
        "secondary_window": rate_limit.get("secondary_window"),
    }


def load_live_usage() -> dict:
    token = read_access_token()
    if not token:
        raise RuntimeError("No Codex auth token found")

    try:
        rate_limit = get_json(USAGE_ENDPOINT, token)
        daily = get_json(DAILY_ENDPOINT, token)
    except HTTPError as exc:
        raise RuntimeError(f"Codex usage request failed: HTTP {exc.code}") from exc

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rate_limit": public_rate_limit(rate_limit),
        "daily": daily,
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def load_cached_usage() -> dict:
    if not CACHE_PATH.exists():
        raise RuntimeError("No live Codex auth and no cached usage data")
    return json.loads(CACHE_PATH.read_text())


def load_usage() -> dict:
    try:
        return load_live_usage()
    except RuntimeError:
        return load_cached_usage()


def daily_usage_rows(payload: dict) -> dict[date, float]:
    daily: dict[date, float] = defaultdict(float)
    for row in payload.get("daily", {}).get("data", []):
        try:
            day = date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue

        values = row.get("product_surface_usage_values") or {}
        total = sum(float(value or 0) for value in values.values())
        if total == 0:
            total = sum(float(model.get("credits") or 0) for model in row.get("models", []))
        daily[day] += total
    return dict(daily)


def streaks(daily: dict[date, float], today: date) -> tuple[int, int]:
    active_days = {day for day, usage in daily.items() if usage > 0}
    if not active_days:
        return 0, 0

    anchor = today if today in active_days else max(active_days)
    current = 0
    cursor = anchor
    while cursor in active_days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    previous = None
    for day in sorted(active_days):
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    return current, longest


def color_for(value: float, peak: float) -> str:
    if value <= 0:
        return "#303030"
    ratio = value / max(peak, 1)
    if ratio >= 0.75:
        return "#3AA0FF"
    if ratio >= 0.45:
        return "#245C8C"
    if ratio >= 0.2:
        return "#1D456B"
    return "#173450"


def grid(daily: dict[date, float], today: date) -> str:
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
            value = daily.get(day, 0)
            x = 64 + col * (size + gap)
            y = 192 + row * (size + gap)
            cells.append(
                f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="7" fill="{color_for(value, peak)}">'
                f"<title>{day.isoformat()}: {compact(value)} Codex credits</title></rect>"
            )

    return "\n".join(cells)


def stat(x: int, value: str, label: str) -> str:
    return f"""
  <text x="{x}" y="505" text-anchor="middle" fill="#ffffff" font-size="38" font-weight="800">{escape(value)}</text>
  <text x="{x}" y="548" text-anchor="middle" fill="#b9b9bd" font-size="27" font-weight="650">{escape(label)}</text>"""


def rate_summary(payload: dict) -> str:
    rate_limit = payload.get("rate_limit", {})
    primary = rate_limit.get("primary_window") or {}
    secondary = rate_limit.get("secondary_window") or {}
    primary_used = int(primary.get("used_percent") or 0)
    secondary_used = int(secondary.get("used_percent") or 0)
    if rate_limit.get("allowed") is False or rate_limit.get("limit_reached") is True:
        return "limit reached"
    return f"{primary_used}% / {secondary_used}%"


def main() -> None:
    payload = load_usage()
    today = datetime.now().astimezone().date()
    daily = daily_usage_rows(payload)
    total = sum(daily.values())
    peak_day = max(daily.values(), default=0)
    current, longest = streaks(daily, today)
    avatar = avatar_href()
    generated_at = payload.get("generated_at", "")
    generated_label = generated_at[:10] if generated_at else today.isoformat()

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
  <text x="936" y="164" text-anchor="end" fill="#737373" font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="16" font-weight="650">live dashboard data - {escape(generated_label)} - limit {escape(rate_summary(payload))}</text>
  <g font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
{grid(daily, today)}
  </g>
  <line x1="282" y1="469" x2="282" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <line x1="500" y1="469" x2="500" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <line x1="718" y1="469" x2="718" y2="548" stroke="#2c2c2c" stroke-width="2"/>
  <g font-family="Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
{stat(173, compact(total), "30d credits")}
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
