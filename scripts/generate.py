#!/usr/bin/env python3
"""Generate the profile README cards (terminal style, Catppuccin Mocha + Latte).

Writes assets/cards/profile-dark.svg and profile-light.svg (all cards composed into one\nimage, so widths and gaps are exact) plus assets/cards/cache.json.
Every data source is optional: when a fetch fails (or WakaTime answers 202 while it
is still computing), the last good value from cache.json is reused, so a flaky
upstream never wipes the profile.

Env:
  GH_TOKEN           GitHub token of the profile owner (read:user, repo for private counts)
  WAKATIME_API_KEY   WakaTime OAuth access token (https://wakatime.com/oauth)
Stdlib only, Python 3.10+.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ----------------------------------------------------------------------------- config
USER = "gere-lajos"
CODING_SINCE = dt.date(2009, 1, 1)
STATIC = {
    "role": "Lead Software Developer @ Helix Digital",
    "langs": "PHP · TypeScript · Python · SQL",
    "stack": "Laravel · Next.js · React · Docker",
    "pbs": [("5K", "18:20", 1100), ("10K", "38:47", 2327)],  # label, display, seconds
    "award": "3rd · HCSC'26 cyber challenge",
    "locale": "hu_HU.UTF-8 · Europe/Budapest",
    "status": "open to freelancing · remote only",
}
SITE_STATS = "https://gerelajos.hu/api/stats.json"
SITE_WAKA = "https://gerelajos.hu/api/wakatime.json"
NON_CODE_LANGS = {"Markdown", "Other", "Text", "JSON", "YAML", "TOML", "INI", "XML",
                  "CSV", "Git Config", "Ignore List", "Image", "Docker", "Makefile"}

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "cards"
CACHE = OUT / "cache.json"
TODAY = dt.datetime.now(dt.timezone.utc).date()

MOCHA = dict(base="#1e1e2e", mantle="#181825", surface0="#313244", surface1="#45475a", surface2="#585b70",
             overlay0="#6c7086", overlay1="#7f849c", text="#cdd6f4", subtext0="#a6adc8", subtext1="#bac2de",
             red="#f38ba8", peach="#fab387", yellow="#f9e2af", green="#a6e3a1", teal="#94e2d5", sapphire="#74c7ec",
             blue="#89b4fa", lavender="#b4befe", mauve="#cba6f7", pink="#f5c2e7",
             l0="#313244", l1="#2f4a3a", l2="#4f7a55", l3="#7fb87a", l4="#a6e3a1")
LATTE = dict(base="#eff1f5", mantle="#e6e9ef", surface0="#ccd0da", surface1="#bcc0cc", surface2="#acb0be",
             overlay0="#9ca0b0", overlay1="#8c8fa1", text="#4c4f69", subtext0="#6c6f85", subtext1="#5c5f77",
             red="#d20f39", peach="#fe640b", yellow="#df8e1d", green="#40a02b", teal="#179299", sapphire="#209fb5",
             blue="#1e66f5", lavender="#7287fd", mauve="#8839ef", pink="#ea76cb",
             l0="#ccd0da", l1="#b8dcae", l2="#86c474", l3="#5aae40", l4="#40a02b")
LANG_COLORS = ["blue", "lavender", "yellow", "green", "peach", "teal"]

FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
CW = 7.8  # monospace advance at 13px
W, HW = 830, 407


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ----------------------------------------------------------------------------- fetch
def http_json(url: str, *, headers: dict | None = None, data: bytes | None = None, timeout: int = 60):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "profile-cards", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


def gql(query: str, variables: dict | None = None) -> dict:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise RuntimeError("GH_TOKEN missing")
    _, body = http_json("https://api.github.com/graphql",
                        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
                        data=json.dumps({"query": query, "variables": variables or {}}).encode())
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch_github() -> dict:
    since_d = TODAY - dt.timedelta(days=30)
    since = dt.datetime.combine(since_d, dt.time(), dt.timezone.utc).isoformat()
    d = gql("""query($login:String!){user(login:$login){id
      contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}""",
            {"login": USER})["user"]
    cal = d["contributionsCollection"]["contributionCalendar"]
    days = [[x["date"], x["contributionCount"]] for w in cal["weeks"] for x in w["contributionDays"]]
    # Private/org work shows up only as "restricted" in contributionsCollection, so count
    # the owner's commits per recently pushed repo instead. Repo names are never rendered.
    q = gql("""query($uid:ID!,$since:GitTimestamp!,$prq:String!,$rvq:String!){
      viewer{repositories(first:100,affiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],
        ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],orderBy:{field:PUSHED_AT,direction:DESC}){
        nodes{pushedAt primaryLanguage{name}
          defaultBranchRef{target{... on Commit{history(since:$since,author:{id:$uid}){totalCount}}}}}}}
      prs: search(query:$prq,type:ISSUE){issueCount}
      reviews: search(query:$rvq,type:ISSUE){issueCount}}""",
            {"uid": d["id"], "since": since,
             "prq": f"author:{USER} is:pr created:>={since_d}",
             "rvq": f"reviewed-by:{USER} -author:{USER} is:pr updated:>={since_d}"})
    langs: dict[str, list[int]] = {}
    commits = repos = 0
    for node in q["viewer"]["repositories"]["nodes"]:
        target = (node.get("defaultBranchRef") or {}).get("target") or {}
        n = (target.get("history") or {}).get("totalCount", 0)
        if not n:
            continue
        name = (node.get("primaryLanguage") or {}).get("name") or "Other"
        acc = langs.setdefault(name, [0, 0])
        acc[0] += n
        acc[1] += 1
        commits += n
        repos += 1
    return {
        "total": cal["totalContributions"],
        "days": days,
        "recent": {
            "commits": commits,
            "prs": q["prs"]["issueCount"],
            "reviews": q["reviews"]["issueCount"],
            "repos": repos,
            "langs": sorted(([k, v[0], v[1]] for k, v in langs.items()), key=lambda t: -t[1]),
        },
    }


def fetch_waka() -> dict:
    key = os.environ.get("WAKATIME_API_KEY", "")
    if not key:
        raise RuntimeError("WAKATIME_API_KEY missing")
    out = {}
    for rng in ("all_time", "last_7_days"):
        status, body = http_json(f"https://wakatime.com/api/v1/users/current/stats/{rng}?api_key={key}", timeout=120)
        data = body.get("data") or {}
        if status != 200 or not data.get("is_up_to_date", True) or data.get("status") not in (None, "ok"):
            raise RuntimeError(f"wakatime {rng} not ready (HTTP {status}, status={data.get('status')})")
        out[rng] = data
    a, w = out["all_time"], out["last_7_days"]
    cat = lambda d, n: next((c["total_seconds"] for c in d.get("categories", []) if c["name"] == n), 0)
    code_langs = [l for l in a.get("languages", []) if l["name"] not in NON_CODE_LANGS]
    tot = sum(l["total_seconds"] for l in code_langs) or 1
    editors = w.get("editors", [])
    return {
        "total_h": a["total_seconds"] / 3600,
        "ai_h": cat(a, "AI Coding") / 3600,
        "ai_lines": a.get("ai_additions", 0),
        "week_h": w.get("total_seconds_including_other_language", w.get("total_seconds", 0)) / 3600,
        "langs": [[l["name"], l["total_seconds"] / tot] for l in code_langs[:5]],
        "editor": [editors[0]["name"], editors[0]["percent"]] if editors else None,
    }


def fetch_site() -> dict:
    _, stats = http_json(SITE_STATS)
    _, daily = http_json(SITE_WAKA)
    if not stats.get("run_ytd_distance"):
        raise RuntimeError("site stats without running data")
    return {"stats": stats, "daily": daily}


def gather() -> dict:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for name, fn in (("github", fetch_github), ("waka", fetch_waka), ("site", fetch_site)):
        try:
            cache[name] = fn()
            cache.setdefault("fetched", {})[name] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            log(f"ok   {name}")
        except Exception as e:  # keep last good value
            log(f"keep {name}: {e}")
    return cache


# ----------------------------------------------------------------------------- svg helpers
def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def window(title: str, h: float, body: list[str], w: int = W) -> str:
    h = round(h)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{FONT}" font-size="13">
<title>{esc(title)}</title>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="@base" stroke="@surface0"/>
<path d="M0.5 32 V10.5 a10 10 0 0 1 10 -10 H{w-10.5} a10 10 0 0 1 10 10 V32 Z" fill="@mantle"/>
<line x1="0.5" y1="32" x2="{w-0.5}" y2="32" stroke="@surface0"/>
<circle cx="18" cy="16" r="5.5" fill="@red"/><circle cx="36" cy="16" r="5.5" fill="@yellow"/><circle cx="54" cy="16" r="5.5" fill="@green"/>
<text x="{w/2}" y="20.5" text-anchor="middle" fill="@overlay1" font-size="12">{esc(title)}</text>
{chr(10).join(body)}
</svg>
'''


def prompt(y: float, cmd: str, x: float = 20) -> str:
    return (f'<text x="{x}" y="{y}"><tspan fill="@green">lali</tspan><tspan fill="@overlay1">@</tspan>'
            f'<tspan fill="@blue">budapest</tspan><tspan fill="@overlay1"> ~ $ </tspan>'
            f'<tspan fill="@text">{esc(cmd)}</tspan></text>')


def seg_bar(x: float, y: float, frac: float, cells: int, color: str) -> str:
    """Terminal-like block bar drawn with rects (glyph widths vary across fonts)."""
    full = max(0, min(cells, round(frac * cells)))
    out = []
    for i in range(cells):
        fill = f"@{color}" if i < full else "@surface1"
        op = "" if i < full else ' opacity="0.55"'
        out.append(f'<rect x="{x + i * CW:.1f}" y="{y - 10}" width="{CW - 1.2:.1f}" height="12" rx="1" fill="{fill}"{op}/>')
    return "".join(out)


def fmt_h(h: float) -> str:
    return f"{h:,.0f} h"


def fmt_hm(h: float) -> str:
    return f"{int(h)} h {int(round(h % 1 * 60)):02d} m"


def shade(hex_color: str, k: float) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*(round(c * (1 - k)) for c in (r, g, b)))


def themed(svg: str, pal: dict) -> str:
    for k in sorted(pal, key=len, reverse=True):
        svg = svg.replace(f"@{k}", pal[k])
    return svg


# ----------------------------------------------------------------------------- cards
def card_neofetch(c: dict) -> str:
    site = (c.get("site") or {}).get("stats", {})
    waka = c.get("waka") or {}
    years = int((TODAY - CODING_SINCE).days // 365.25)
    editor = waka.get("editor")
    runs = (f"{site['run_ytd_distance']/1000:,.0f} km in {TODAY.year} · {site['run_ytd_count']} runs"
            if site.get("run_ytd_distance") else "—")
    keys = (f"{site['total_keys']:,} keystrokes, {site.get('total_kms', 0):.0f} km of mouse"
            if site.get("total_keys") else "—")
    info = [
        ("OS", STATIC["role"]),
        ("Uptime", f"{years} years of writing code (since {CODING_SINCE.year})"),
        ("Shell", f"{editor[0]} · {editor[1]:.0f}% of editor time this week" if editor else "zsh"),
        ("Langs", STATIC["langs"]),
        ("Stack", STATIC["stack"]),
        ("Keys", keys),
        ("Runs", runs),
        ("PB", " · ".join(f"{k} {v}" for k, v, _ in STATIC["pbs"])),
        ("Awards", STATIC["award"]),
        ("Locale", STATIC["locale"]),
        ("Status", STATIC["status"]),
    ]
    glyph = [" #####   ##      ", "##   ##  ##      ", "##       ##      ", "##  ###  ##      ",
             "##   ##  ##      ", "##   ##  ##      ", " #####   ####### "]
    rows = ["mauve", "mauve", "pink", "pink", "peach", "peach", "yellow"]
    px = 12
    b = [prompt(58, "neofetch --off-the-clock")]
    for r, row in enumerate(glyph):
        for col, ch in enumerate(row):
            if ch == "#":
                b.append(f'<rect x="{34+col*px+3}" y="{84+r*px+3}" width="{px-1.5}" height="{px-1.5}" rx="1.5" fill="@{rows[r]}" opacity="0.18"/>')
                b.append(f'<rect x="{34+col*px}" y="{84+r*px}" width="{px-1.5}" height="{px-1.5}" rx="1.5" fill="@{rows[r]}"/>')
    b.append(f'<text x="34" y="{84+7*px+30}" fill="@overlay0" font-size="12">// szia, Lali vagyok</text>')
    b.append(f'<text x="34" y="{84+7*px+50}" fill="@overlay0" font-size="12">// I build working solutions</text>')
    ix = 270
    b.append(f'<text x="{ix}" y="90"><tspan fill="@mauve" font-weight="700">gere-lajos</tspan><tspan fill="@overlay1">@</tspan><tspan fill="@mauve" font-weight="700">github</tspan></text>')
    b.append(f'<line x1="{ix}" y1="101" x2="{ix+17*CW}" y2="101" stroke="@surface2"/>')
    for i, (k, v) in enumerate(info):
        y = 126 + i * 19
        b.append(f'<text x="{ix}" y="{y}"><tspan fill="@blue" font-weight="700">{k}</tspan><tspan fill="@overlay1">:</tspan>'
                 f'<tspan x="{ix+8*CW}" fill="@text">{esc(v)}</tspan></text>')
    py = 126 + len(info) * 19 + 8
    for i, col in enumerate(["surface1", "red", "green", "yellow", "blue", "pink", "teal", "subtext1"]):
        b.append(f'<rect x="{ix+i*26}" y="{py}" width="24" height="14" fill="@{col}"/>')
    return window("lali@budapest: ~ · zsh", py + 34, b)


def streak_of(days: list) -> int:
    n = 0
    for i, (_, cnt) in enumerate(reversed(days)):
        if cnt > 0:
            n += 1
        elif i == 0:  # today may still be empty
            continue
        else:
            break
    return n


def card_now(c: dict) -> str:
    gh = c.get("github") or {}
    rec = gh.get("recent") or {}
    langs = rec.get("langs", [])[:4]
    b = [prompt(58, "now --last 30d")]
    top = max((l[1] for l in langs), default=1) or 1
    for i, (name, commits, repos) in enumerate(langs):
        y = 86 + i * 22
        col = LANG_COLORS[i % len(LANG_COLORS)]
        b.append(f'<text x="20" y="{y}" fill="@{col}" font-weight="700">{esc(name)}</text>')
        b.append(seg_bar(20 + 14 * CW, y, commits / top, 18, col))
        b.append(f'<text x="{20+34*CW}" y="{y}" fill="@subtext0">{commits:,} commits · {repos} repo{"s" if repos != 1 else ""}</text>')
    y = 86 + max(len(langs), 1) * 22 + 8
    summary = (f"↳ {rec.get('commits', 0):,} commits · {rec.get('prs', 0)} PRs · {rec.get('reviews', 0)} reviews · "
               f"{rec.get('repos', 0)} repos · {streak_of(gh.get('days', []))}-day streak")
    summary = summary.replace(" 1 PRs", " 1 PR").replace(" 1 reviews", " 1 review").replace(" 1 repos", " 1 repo")
    b.append(f'<text x="20" y="{y}" fill="@overlay0">{esc(summary)}</text>')
    y += 26
    b.append(prompt(y, "") + f'<rect x="{20+18*CW:.1f}" y="{y-12}" width="8" height="15" fill="@text">'
             '<animate attributeName="opacity" values="1;1;0;0" dur="1.1s" repeatCount="indefinite"/></rect>')
    return window("~/now.log", y + 18, b)


def card_waka(c: dict) -> str:
    waka = c.get("waka") or {}
    daily = (c.get("site") or {}).get("daily") or []
    vals = [x.get("value", 0) for x in daily][-364:]
    weeks = [sum(vals[i:i + 7]) for i in range(0, len(vals), 7)]
    last30 = sum(vals[-30:])
    b = [prompt(58, "waka --summary", 16)]
    rows = [("total", fmt_h(waka["total_h"]) if waka else "—", "text"),
            ("ai coding", fmt_h(waka["ai_h"]) if waka else "—", "peach"),
            ("this week", fmt_hm(waka["week_h"]) if waka else "—", "text"),
            ("last 30 days", fmt_h(last30) if vals else "—", "text")]
    for i, (k, v, col) in enumerate(rows):
        y = 84 + i * 20
        b.append(f'<text x="16" y="{y}" fill="@overlay1">{k}</text><text x="{HW-16}" y="{y}" text-anchor="end" fill="@{col}" font-weight="700">{v}</text>')
    y = 170
    b.append(f'<text x="16" y="{y}" fill="@overlay0" font-size="11.5">weekly hours, last {len(weeks)} weeks</text>')
    if weeks:
        mx = max(weeks) or 1
        sx, sy, sw, sh = 16, y + 8, HW - 32, 46
        bw = sw / len(weeks)
        for i, v in enumerate(weeks):
            hh = max(1.5, v / mx * sh)
            b.append(f'<rect x="{sx+i*bw:.1f}" y="{sy+sh-hh:.1f}" width="{bw-1.6:.1f}" height="{hh:.1f}" rx="1" fill="@sapphire" opacity="{0.45+0.55*v/mx:.2f}"/>')
    y = 250
    langs = waka.get("langs", [])
    top = max((f for _, f in langs), default=1) or 1
    for i, (n, f) in enumerate(langs):
        yy = y + i * 19
        col = LANG_COLORS[i % len(LANG_COLORS)]
        b.append(f'<text x="16" y="{yy}" fill="@subtext1">{esc(n)}</text>')
        b.append(seg_bar(16 + 16 * CW, yy, f / top, 21, col))
        b.append(f'<text x="{HW-16}" y="{yy}" text-anchor="end" fill="@overlay1">{f*100:.0f}%</text>')
    return window("wakatime · all time", 351, b, HW)


def card_run(c: dict) -> str:
    s = (c.get("site") or {}).get("stats") or {}
    b = [prompt(58, "strava --ytd", 16)]
    if s.get("run_ytd_distance"):
        km = s["run_ytd_distance"] / 1000
        doy = TODAY.timetuple().tm_yday
        b.append(f'<text x="16" y="96" fill="@green" font-size="30" font-weight="700">{km:,.0f}<tspan font-size="14" fill="@overlay1" font-weight="400"> km in {TODAY.year}</tspan></text>')
        rows = [("runs", f"{s['run_ytd_count']}"), ("moving time", fmt_hm(s["run_ytd_moving_time"] / 3600)),
                ("weekly avg", f"{km / (doy / 7):.0f} km")]
        for i, (k, v) in enumerate(rows):
            y = 124 + i * 20
            b.append(f'<text x="16" y="{y}" fill="@overlay1">{k}</text><text x="{HW-16}" y="{y}" text-anchor="end" fill="@text" font-weight="700">{v}</text>')
        if s.get("run_last_distance"):
            lk, lt = s["run_last_distance"] / 1000, s["run_last_moving_time"]
            pace = lt / lk if lk else 0
            b.append(f'<text x="16" y="196" fill="@overlay0" font-size="11.5">last run · {esc(s.get("run_last_date", ""))}</text>')
            hr = f'  <tspan fill="@overlay1">·</tspan>  <tspan fill="@red">♥</tspan> {s["run_last_avg_heartrate"]:.0f}' if s.get("run_last_avg_heartrate") else ""
            b.append(f'<text x="16" y="216" fill="@text" xml:space="preserve">{lk:.1f} km  <tspan fill="@overlay1">·</tspan>  '
                     f'{int(lt//3600)}:{int(lt%3600//60):02d}:{int(lt%60):02d}  <tspan fill="@overlay1">·</tspan>  {int(pace//60)}:{int(pace%60):02d}/km{hr}</text>')
    else:
        b.append('<text x="16" y="96" fill="@overlay0">no data yet</text>')
    y = 244
    b.append(f'<text x="16" y="{y}" fill="@overlay0" font-size="11.5">personal bests · pace</text>')
    for i, (k, v, secs) in enumerate(STATIC["pbs"]):
        yy = y + 22 + i * 22
        dist = {"5K": 5, "10K": 10, "HM": 21.0975, "M": 42.195}.get(k, 1)
        pace = secs / dist
        frac = min(1.0, 200 / pace)  # 3:20/km would be a full bar
        b.append(f'<text x="16" y="{yy}" fill="@yellow" font-weight="700">{k}</text>')
        b.append(f'<rect x="{16+5*CW:.1f}" y="{yy-10}" width="{(HW-32-5*CW-112)*frac:.0f}" height="10" rx="2" fill="@yellow" opacity="0.8"/>')
        b.append(f'<text x="{HW-16}" y="{yy}" text-anchor="end" fill="@text"><tspan font-weight="700">{v}</tspan>'
                 f'<tspan fill="@overlay1"> {int(pace//60)}:{int(pace%60):02d}/km</tspan></text>')
    return window("strava · via gerelajos.hu", 351, b, HW)


def card_contrib(c: dict) -> str:
    gh = c.get("github") or {}
    days = gh.get("days") or []
    cs = 13.0
    cx, cy = math.cos(math.radians(22)) * cs, math.sin(math.radians(22)) * cs
    ox, oy = 24 + 7 * cx, 150
    mx = max((n for _, n in days), default=1) or 1
    cells = []
    if days:
        first = dt.date.fromisoformat(days[0][0])
        start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # back to Sunday
        for d, n in days:
            delta = (dt.date.fromisoformat(d) - start).days
            cells.append((delta // 7, delta % 7, n))
    b = [prompt(58, "git log --since=1.year --graph=3d")]
    for wi, di, n in sorted(cells, key=lambda t: (t[0] + t[1], t[0])):
        lvl = 0 if n == 0 else 1 if n < 8 else 2 if n < 25 else 3 if n < 60 else 4
        hgt = 2 + (math.sqrt(n / mx) * 70 if n else 0)
        x0, y0 = ox + (wi - di) * cx, oy + (wi + di) * cy
        P = lambda pts: " ".join(f"{a:.1f},{bb:.1f}" for a, bb in pts)
        top = [(x0, y0 - hgt), (x0 + cx, y0 + cy - hgt), (x0, y0 + 2 * cy - hgt), (x0 - cx, y0 + cy - hgt)]
        left = [(x0 - cx, y0 + cy - hgt), (x0, y0 + 2 * cy - hgt), (x0, y0 + 2 * cy), (x0 - cx, y0 + cy)]
        right = [(x0, y0 + 2 * cy - hgt), (x0 + cx, y0 + cy - hgt), (x0 + cx, y0 + cy), (x0, y0 + 2 * cy)]
        b.append(f'<polygon points="{P(left)}" fill="@l{lvl}L"/><polygon points="{P(right)}" fill="@l{lvl}R"/>'
                 f'<polygon points="{P(top)}" fill="@l{lvl}"/>')
    b.append(f'<text x="{W-20}" y="70" text-anchor="end" fill="@green" font-size="26" font-weight="700">{gh.get("total", 0):,}</text>')
    b.append(f'<text x="{W-20}" y="90" text-anchor="end" fill="@overlay1">contributions, last 12 months</text>')
    b.append(f'<text x="{W-20}" y="112" text-anchor="end" fill="@overlay0" font-size="12">busiest day: {mx} · current streak: {streak_of(days)} days</text>')
    b.append('<text x="20" y="462" fill="@overlay0" font-size="11.5">less</text>')
    for i in range(5):
        b.append(f'<rect x="{56+i*16}" y="452" width="12" height="12" rx="2" fill="@l{i}"/>')
    b.append(f'<text x="{56+5*16+6}" y="462" fill="@overlay0" font-size="11.5">more</text>')
    return window("contributions", 482, b)


# ----------------------------------------------------------------------------- main
GAP = 16  # vertical and horizontal gap between cards (2 * HW + GAP == W)


def place(svg: str, x: float, y: float) -> tuple[str, float]:
    """Nest a card SVG at (x, y) inside the composed profile image; return it with its height."""
    m = re.search(r'height="(\d+)"', svg)
    h = float(m.group(1)) if m else 0
    return svg.replace("<svg ", f'<svg x="{x}" y="{y}" ', 1), h


def compose(data: dict) -> str:
    """All cards stacked in ONE image: exact widths and gaps regardless of README layout."""
    parts, y = [], 0.0
    for fn in (card_neofetch, card_now):
        svg, h = place(fn(data), 0, y)
        parts.append(svg)
        y += h + GAP
    left, hl = place(card_waka(data), 0, y)
    right, hr = place(card_run(data), HW + GAP, y)
    parts += [left, right]
    y += max(hl, hr) + GAP
    svg, h = place(card_contrib(data), 0, y)
    parts.append(svg)
    y += h
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{y:.0f}" viewBox="0 0 {W} {y:.0f}">\n'
            f'<title>Gere Lajos (lali@budapest): profile</title>\n' + "\n".join(parts) + "</svg>\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    data = gather()
    CACHE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    for theme, pal in (("dark", MOCHA), ("light", LATTE)):
        full = dict(pal)
        for i in range(5):  # side faces of the 3D bars
            full[f"l{i}L"] = shade(pal[f"l{i}"], 0.18)
            full[f"l{i}R"] = shade(pal[f"l{i}"], 0.32)
        (OUT / f"profile-{theme}.svg").write_text(themed(compose(data), full))
    log(f"wrote profile-dark.svg + profile-light.svg to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
