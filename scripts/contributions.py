#!/usr/bin/env python3
"""Render the profile's contribution cluster from jcosta.tech's merged-PR feed.

usage: contributions.py merged-prs.json OUT_DIR
Writes OUT_DIR/contributions-dark.svg and OUT_DIR/contributions-light.svg.
One circle per repo owner, area ~ merged PRs. Org avatars are embedded (GitHub's
image proxy blocks external images inside SVGs). Personal accounts get a name
circle instead of the person's face. logos/<owner>.png overrides an avatar.
Needs GITHUB_TOKEN for the owner-type lookup.
"""
import base64, json, math, os, sys, urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

LOGOS = Path(__file__).resolve().parent.parent / "logos"
SHORT = {"mampfes/hacs_waste_collection_schedule": "waste", "rohitg00/awesome-claude-code-toolkit": "cc-toolkit",
         "punkpeye/awesome-mcp-servers": "mcp", "vorssaint/vorssaint-utils": "utils"}
LANG = {"TypeScript": "#3178c6", "Rust": "#b7410e", "Python": "#3572A5", "Go": "#00ADD8", "Ruby": "#CC342D",
        "JavaScript": "#c9b200", "Java": "#b07219", "Groovy": "#4298b8", "Swift": "#F05138"}
THEMES = {
    "dark": dict(text="#e6edf3", muted="#8b949e", ring="#30363d", bg="#161b22", line="#3fb950"),
    "light": dict(text="#1f2328", muted="#59636e", ring="#d1d9e0", bg="#f6f8fa", line="#1a7f37"),
}
W, CX, CY = 900, 450, 230
R_MIN, K = 9, 9.5  # radius = R_MIN + K*sqrt(prs-1): 1-PR owners stay visible, ink dominates


def fetch(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def owner_types(owners):
    q = "query{" + " ".join(f'a{i}: repositoryOwner(login: "{o}"){{__typename login}}' for i, o in enumerate(owners)) + "}"
    res = json.loads(fetch("https://api.github.com/graphql", json.dumps({"query": q}).encode(),
                           {"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}"}))
    if "errors" in res:
        sys.exit(f"owner lookup failed: {res['errors']}")
    return {v["login"].lower(): v["__typename"] for v in res["data"].values() if v}


def data_uri(b):
    mime = "image/jpeg" if b[:2] == b"\xff\xd8" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


def pack(counts):
    # ponytail: greedy spiral packing, O(n^2) over ~100 owners; d3-hierarchy pack if it gets slow
    placed = []
    for owner, n in counts:
        r = R_MIN + K * math.sqrt(n - 1)
        t = 0.0
        while True:
            x, y = CX + 1.9 * 3 * t * math.cos(t), CY + 3 * t * math.sin(t)  # wide spiral for a banner
            if all((x - a) ** 2 + (y - b) ** 2 >= (r + c + 2) ** 2 for a, b, c, *_ in placed):
                break
            t += 0.05
        placed.append((x, y, r, owner, n))
    return placed


def main():
    prs = json.load(open(sys.argv[1]))["prs"]
    out_dir = Path(sys.argv[2])
    owner_of = lambda p: p["repo"].split("/")[0]
    # sort by count then name so unchanged data always gives the same layout
    counts = sorted(Counter(map(owner_of, prs)).items(), key=lambda kv: (-kv[1], kv[0].lower()))
    types = owner_types([o for o, _ in counts])
    top_repo = {o: Counter((p["repo"], p.get("language")) for p in prs if owner_of(p) == o).most_common(1)[0][0]
                for o, _ in counts}
    placed = pack(counts)

    images = {}
    for x, y, r, owner, n in placed:
        logo = LOGOS / f"{owner}.png"
        if logo.exists():
            images[owner] = (data_uri(logo.read_bytes()), True)
        elif types.get(owner.lower()) == "Organization":
            # 2x the drawn diameter for retina, capped
            images[owner] = (data_uri(fetch(f"https://github.com/{owner}.png?size={min(460, math.ceil(4 * r))}")), False)

    repos = {p["repo"] for p in prs}
    stars = sum({p["repo"]: p["stars"] for p in prs}.values())
    dates = sorted(p["mergedAt"][:10] for p in prs)
    d0, d1 = date(2026, 1, 1), date.fromisoformat(dates[-1])
    span = max((d1 - d0).days, 1)
    GY = max(y + r for x, y, r, *_ in placed) + 50
    GH, X0, X1 = 70, 60, W - 60
    c = sum(d < "2026-01-01" for d in dates)
    pts = [(X0, GY + GH)]
    for d in dates:
        if d < "2026-01-01":
            continue
        c += 1
        pts.append((X0 + (date.fromisoformat(d) - d0).days / span * (X1 - X0), GY + GH - GH * c / len(dates)))
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    for theme, t in THEMES.items():
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'viewBox="0 0 {W} {GY + GH + 50:.0f}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif">',
             f'<title>{len(prs)} merged pull requests across {len(repos)} open source projects</title><defs>']
        o += [f'<clipPath id="c{i}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/></clipPath>'
              for i, (x, y, r, *_) in enumerate(placed)]
        o.append("</defs>")
        for i, (x, y, r, owner, n) in enumerate(placed):
            repo, lang = top_repo[owner]
            o.append(f'<a href="https://github.com/{repo}"><title>{repo}: {n} merged PR{"s" * (n > 1)}</title>')
            if owner in images:
                uri, inset = images[owner]
                s = r * (1.25 if inset else 2)  # wide logo overrides sit inside the circle
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{t["bg"]}"/>')
                o.append(f'<image href="{uri}" x="{x - s / 2:.1f}" y="{y - s / 2:.1f}" width="{s:.1f}" height="{s:.1f}" clip-path="url(#c{i})"/>')
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" stroke="{t["ring"]}" stroke-width="1.5"/>')
            else:  # personal account: repo name on its language color, never the person's face
                name = SHORT.get(repo, repo.split("/")[1].removeprefix("eslint-plugin-"))
                o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{LANG.get(lang, "#6e7681")}"/>')
                if r >= 12:
                    fs = max(min(r * 0.5, 1.75 * r / len(name)), 5.5)
                    o.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{fs:.1f}" fill="#fff" font-weight="600" '
                             f'text-anchor="middle" dominant-baseline="central">{name}</text>')
            o.append("</a>")
        o.append(f'<polygon points="{path} {X1},{GY + GH:.1f} {X0},{GY + GH:.1f}" fill="{t["line"]}" fill-opacity=".15"/>')
        o.append(f'<polyline points="{path}" fill="none" stroke="{t["line"]}" stroke-width="2"/>')
        o.append(f'<text x="{X0}" y="{GY + GH + 18:.1f}" font-size="12" fill="{t["muted"]}">Jan 2026</text>')
        o.append(f'<text x="{X1}" y="{GY + GH + 18:.1f}" font-size="12" fill="{t["muted"]}" text-anchor="end">now</text>')
        o.append(f'<text x="{X1}" y="{GY - 8:.1f}" font-size="13" fill="{t["text"]}" text-anchor="end" font-weight="600">{len(prs)}</text>')
        o.append(f'<text x="{W / 2}" y="{GY + GH + 42:.1f}" font-size="15" fill="{t["text"]}" text-anchor="middle">'
                 f'<tspan font-weight="600">{len(prs)}</tspan> merged PRs · <tspan font-weight="600">{len(repos)}</tspan> projects · '
                 f'<tspan font-weight="600">{stars / 1e6:.1f}M</tspan> combined stars</text></svg>')
        (out_dir / f"contributions-{theme}.svg").write_text("\n".join(o))
    print(f"{len(prs)} PRs, {len(placed)} owners, {len(images)} images")


if __name__ == "__main__":
    main()
