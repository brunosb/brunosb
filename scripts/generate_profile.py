#!/usr/bin/env python3
"""Generate public profile assets from GitHub's GraphQL and REST APIs."""
from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
DATA = ROOT / "data"
TOKEN = os.environ.get("PROFILE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    raise SystemExit("PROFILE_GITHUB_TOKEN or GITHUB_TOKEN is required")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "brunosb-profile-generator",
    "X-GitHub-Api-Version": "2022-11-28",
}


def request(url: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = dict(HEADERS)
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def graphql(query: str) -> dict:
    body = request("https://api.github.com/graphql", {"query": query})
    if body.get("errors"):
        raise RuntimeError(json.dumps(body["errors"], ensure_ascii=False))
    return body["data"]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def generate_heatmap(calendar: dict) -> None:
    weeks = calendar["weeks"]
    total = calendar["totalContributions"]
    width = 18
    gap = 4
    left = 58
    top = 58
    cell = 14
    svg_width = left + len(weeks) * (width + gap) + 20
    svg_height = 190
    cells = []
    max_count = max(
        (day["contributionCount"] for week in weeks for day in week["contributionDays"]),
        default=1,
    )
    colors = ["#0f2d20", "#14532d", "#15803d", "#22c55e", "#86efac"]
    for col, week in enumerate(weeks):
        for row, day in enumerate(week["contributionDays"]):
            count = day["contributionCount"]
            level = 0 if count == 0 else min(4, 1 + int((count / max_count) * 3.99))
            x = left + col * (width + gap)
            y = top + row * (cell + gap)
            delay = (col * 7 + row) * 0.012
            cells.append(
                f'<rect x="{x}" y="{y}" width="{width}" height="{cell}" rx="3" '
                f'fill="{colors[level]}" data-date="{esc(day["date"])}" '
                f'data-count="{count}" style="animation-delay:{delay:.3f}s"/>'
            )
    labels = "".join(
        f'<text x="{left + i * (width + gap)}" y="44">{esc(week["contributionDays"][0]["date"][:7])}</text>'
        for i, week in enumerate(weeks)
        if i == 0 or week["contributionDays"][0]["date"][5:7]
        != weeks[i - 1]["contributionDays"][0]["date"][5:7]
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" role="img" aria-labelledby="title desc">
<title id="title">GitHub contributions in the last year</title>
<desc id="desc">{total} contributions in the last year, generated from GitHub's contribution calendar.</desc>
<defs><style>text{{font:400 11px Inter,Arial,sans-serif;fill:#64748b}} rect{{animation:appear .55s ease both}} @keyframes appear{{from{{opacity:.1;transform:translateY(3px)}}to{{opacity:1;transform:translateY(0)}}}}</style></defs>
<rect width="100%" height="100%" rx="16" fill="#07111f"/>
<text x="28" y="26" fill="#86efac" font-family="monospace" font-size="12">PUBLIC ACTIVITY / {total} CONTRIBUTIONS IN THE LAST YEAR</text>
<g>{labels}</g><g>{''.join(cells)}</g>
<text x="28" y="180">less</text><rect x="62" y="169" width="14" height="14" rx="3" fill="#0f2d20"/><rect x="82" y="169" width="14" height="14" rx="3" fill="#14532d"/><rect x="102" y="169" width="14" height="14" rx="3" fill="#15803d"/><rect x="122" y="169" width="14" height="14" rx="3" fill="#22c55e"/><rect x="142" y="169" width="14" height="14" rx="3" fill="#86efac"/><text x="164" y="180">more</text>
</svg>'''
    write(ASSETS / "activity-heatmap.svg", svg)


def generate_languages(languages: Counter[str]) -> None:
    top = languages.most_common(8)
    total = sum(languages.values()) or 1
    colors = ["#22c55e", "#38bdf8", "#f59e0b", "#a78bfa", "#fb7185", "#14b8a6", "#f97316", "#94a3b8"]
    bars = []
    for index, (name, amount) in enumerate(top):
        pct = amount / total * 100
        y = 54 + index * 25
        bars.append(
            f'<text x="32" y="{y + 12}">{esc(name)}</text>'
            f'<rect x="155" y="{y}" width="650" height="14" rx="7" fill="#172033"/>'
            f'<rect x="155" y="{y}" width="{max(8, 650 * pct / 100):.1f}" height="14" rx="7" fill="{colors[index]}"/>'
            f'<text x="830" y="{y + 12}" fill="{colors[index]}">{pct:.1f}%</text>'
        )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 930 275" role="img" aria-labelledby="title">
<title id="title">Languages across repositories Bruno contributed to</title><defs><style>text{{font:400 13px Inter,Arial,sans-serif;fill:#cbd5e1}}.bar{{animation:grow .8s ease both}}@keyframes grow{{from{{transform:scaleX(0);transform-origin:left}}to{{transform:scaleX(1)}}}}</style></defs>
<rect width="100%" height="100%" rx="16" fill="#07111f"/><text x="28" y="28" fill="#86efac" font-family="monospace" font-size="12">CONTRIBUTOR STACK / LAST FIVE YEARS</text><g>{''.join(bars)}</g>
</svg>'''
    write(ASSETS / "language-chart.svg", svg)


def generate_stats(user: dict, repos: list[dict], total_contributions: int, languages: Counter[str]) -> None:
    public = [repo for repo in repos if not repo.get("fork") and not repo.get("private")]
    stars = sum(repo.get("stargazers_count", 0) for repo in public)
    metrics = [
        (str(total_contributions), "contributions / last year", "#22c55e"),
        (str(len(public)), "public repositories", "#38bdf8"),
        (str(len([repo for repo in repos if repo.get("private")])), "private repositories (count only)", "#fb7185"),
        (str(len(languages)), "languages detected", "#a78bfa"),
    ]
    cards = []
    for i, (number, label, color) in enumerate(metrics):
        x = 28 + i * 254
        cards.append(f'<rect x="{x}" y="52" width="230" height="96" rx="12" fill="#0f172a" stroke="#263449"/><text x="{x + 18}" y="96" fill="{color}" style="font:600 30px Inter,Arial,sans-serif">{esc(number)}</text><text x="{x + 18}" y="124" fill="#94a3b8" style="font:400 12px Inter,Arial,sans-serif">{esc(label)}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 175" role="img" aria-labelledby="title"><title id="title">GitHub profile metrics</title><rect width="100%" height="100%" rx="16" fill="#07111f"/><text x="28" y="28" fill="#86efac" font-family="monospace" font-size="12">PROFILE SIGNALS / LIVE FROM GITHUB</text>{''.join(cards)}</svg>'''
    write(ASSETS / "profile-stats.svg", svg)


def contributed_repositories() -> Counter[str]:
    """Return repositories with contributions over the last five complete years.

    Only aggregate language scores are published; repository names stay in memory.
    """
    today = dt.date.today()
    aliases = []
    for year_offset in range(5):
        end = today - dt.timedelta(days=365 * year_offset)
        start = end - dt.timedelta(days=364)
        alias = f"y{year_offset}"
        aliases.append((alias, start.isoformat(), end.isoformat()))
    fields = []
    for alias, start, end in aliases:
        fields.append(
            f'''{alias}: contributionsCollection(from:"{start}T00:00:00Z",to:"{end}T23:59:59Z") {{
                commitContributionsByRepository(maxRepositories:100) {{ repository {{ nameWithOwner }} contributions {{ totalCount }} }}
                pullRequestContributionsByRepository(maxRepositories:100) {{ repository {{ nameWithOwner }} contributions {{ totalCount }} }}
                issueContributionsByRepository(maxRepositories:100) {{ repository {{ nameWithOwner }} contributions {{ totalCount }} }}
            }}'''
        )
    data = graphql("query { viewer { " + " ".join(fields) + " } }")["viewer"]
    totals: Counter[str] = Counter()
    for alias, _, _ in aliases:
        collection = data[alias]
        for group in ("commitContributionsByRepository", "pullRequestContributionsByRepository", "issueContributionsByRepository"):
            for item in collection[group]:
                totals[item["repository"]["nameWithOwner"]] += item["contributions"]["totalCount"]
    return totals


def main() -> None:
    query = """query { viewer { login name contributionsCollection { contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } } } }"""
    viewer = graphql(query)["viewer"]
    all_repos = request("https://api.github.com/user/repos?visibility=all&per_page=100&sort=updated")
    all_repos = [repo for repo in all_repos if not repo.get("archived")]
    contribution_counts = contributed_repositories()
    language_scores: Counter[str] = Counter()
    language_repo_counts: Counter[str] = Counter()
    contributed_count = 0
    for full_name, contribution_count in contribution_counts.items():
        try:
            repo = request(f"https://api.github.com/repos/{full_name}")
            languages = request(repo["languages_url"])
            total_bytes = sum(languages.values()) or 1
            if languages:
                contributed_count += 1
            for language, amount in languages.items():
                language_scores[language] += contribution_count * (amount / total_bytes)
                language_repo_counts[language] += 1
        except Exception as exc:
            print(f"warning: contribution repo unavailable: {full_name}: {exc}")
    calendar = viewer["contributionsCollection"]["contributionCalendar"]
    generate_heatmap(calendar)
    generate_languages(language_scores)
    generate_stats(viewer, all_repos, calendar["totalContributions"], language_scores)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "user": {"login": viewer["login"], "name": viewer.get("name")},
        "total_contributions_last_year": calendar["totalContributions"],
        "contributed_repository_count_last_five_years": contributed_count,
        "public_repository_count": len([r for r in all_repos if not r.get("private") and not r.get("fork")]),
        "private_repository_count": len([r for r in all_repos if r.get("private")]),
        "languages_by_contribution_weight": dict((k, round(v, 2)) for k, v in language_scores.most_common()),
        "repositories_per_language": dict(language_repo_counts.most_common()),
    }
    write(DATA / "profile-data.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
