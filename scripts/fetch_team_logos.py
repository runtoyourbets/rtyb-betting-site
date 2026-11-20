"""
Download and cache official NHL team logo SVGs (light + dark variants) into
assets/logos/ at the repo root, keyed by RTYB's own site team codes (see
ABBREV_MAP in fetch_schedule.py) so the front end can always reference
/assets/logos/{CODE}_{light|dark}.svg regardless of what NHL's actual
abbreviation is for that team.

Idempotent by design: a team's light/dark file that already exists on disk
(and is non-empty) is skipped entirely -- no request made for it. That makes
this safe to run on every scheduled refresh (every 10 min, per
.github/workflows/refresh.yml): the first real run -- in GitHub Actions,
the only environment that can actually reach assets.nhle.com from this
project (this sandbox's egress proxy blocks it outright) -- seeds every
file once, and every run after that is a no-op unless a file goes missing
or was never fetched.

Logo source: always NHL's public SVG asset host,
  https://assets.nhle.com/logos/nhl/svg/{ABBREV}_{variant}.svg
using each team's REAL NHL abbreviation (NHL_ABBREV below), not RTYB's own
site code where the two differ.

On the product spec's suggestion to prefer a logo URL from "our existing
NHL data source" (api-web.nhle.com) if it returns one: fetch_schedule.py's
own docstring and parsing code are the only evidence available for what
that API actually returns, and its parsing there only ever reads
awayTeam/homeTeam .abbrev and .score, plus (for finished games)
goals/periodDescriptor fields for the 1P score backfill -- there is no
logo field read or mentioned anywhere in it. Rather than guess a field name
(e.g. "logo" or "darkLogo") that might not exist and silently produce
nothing in production, this script skips that path entirely and goes
straight to the NHL SVG asset URLs above as the sole source. If someone
later confirms api-web.nhle.com does include a usable per-team logo URL,
that can be wired in deliberately with a real field name in hand.

A single team's missing/failed logo never fails the whole script: it's
logged as a WARN to stderr and that team is simply left on the client-side
circle fallback until a later run (in an environment that can reach NHL)
fills it in.

Cropping: NHL ships every logo on a wide 960x640 canvas with the artwork
in the middle, so at badge size (22px) a logo only filled part of its box.
crop_team() sets each team's viewBox to its artwork's bounding box (plus a
small margin), the same box for light and dark so a theme switch doesn't
shift it. Pages show logos with object-fit: contain, so nothing stretches.
It runs on every team each run, so a refetched file is cropped before the
build sees it, and a file that's already cropped is left untouched.
"""
import json
import math
import os
import re
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGOS_DIR = os.path.join(ROOT, 'assets', 'logos')

# RTYB site code -> NHL's real abbreviation, for the handful fetch_schedule.py
# remaps to join against the archived season dataset (see its ABBREV_MAP).
# Every other team's site code already matches NHL's own abbreviation.
NHL_ABBREV = {'TB': 'TBL', 'NJ': 'NJD', 'SJ': 'SJS', 'LA': 'LAK', 'ANH': 'ANA'}

LOGO_URL = 'https://assets.nhle.com/logos/nhl/svg/{abbrev}_{variant}.svg'
VARIANTS = ('light', 'dark')


def nhl_abbrev(site_code):
    return NHL_ABBREV.get(site_code, site_code)


def fetch_bytes(url, tries=3, timeout=15):
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'rtyb-fetch/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"WARN: failed to fetch {url}: {last_err}", file=sys.stderr)
    return None


CROP_MARGIN = 0.02   # of the artwork's longer side, on every edge
_TOKEN = re.compile(r'[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
_ARGS = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'A': 7, 'Z': 0}


def _cubic_extrema(p0, p1, p2, p3):
    """t in (0, 1) where one coordinate of a cubic Bezier turns around."""
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 2 * (p0 - 2 * p1 + p2)
    c = p1 - p0
    if abs(a) < 1e-12:
        roots = [-c / b] if abs(b) > 1e-12 else []
    else:
        disc = b * b - 4 * a * c
        roots = [] if disc < 0 else [(-b + s * math.sqrt(disc)) / (2 * a) for s in (1, -1)]
    return [t for t in roots if 0 < t < 1]


def _cubic_at(p0, p1, p2, p3, t):
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _arc_points(x1, y1, rx, ry, phi, large, sweep, x2, y2, steps=64):
    """Points along an SVG elliptical arc (endpoint -> center form, SVG spec
    F.6.5), sampled finely enough for a bounding box."""
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0, num / den)) if den else 0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    pts = []
    for i in range(1, steps + 1):
        t = t1 + dt * i / steps
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        pts.append((cp * ex - sp * ey + cx, sp * ex + cp * ey + cy))
    return pts


def path_points(d):
    """Every point that bounds path data `d`: segment ends, curve extrema,
    arc samples. Handles the full SVG path grammar (absolute and relative)."""
    toks = _TOKEN.findall(d)
    pts = []
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    last_ctrl = None   # (x, y, kind) of the previous C/S or Q/T control point
    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in 'Zz':
                x, y = sx, sy
                last_ctrl = None
                continue
        up = cmd.upper()
        n = _ARGS[up]
        a = [float(v) for v in toks[i:i + n]]
        i += n
        rel = cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if up == 'M':
            x, y = a[0] + ox, a[1] + oy
            sx, sy = x, y
            pts.append((x, y))
            cmd = 'l' if rel else 'L'   # extra pairs after M are line-tos
            last_ctrl = None
        elif up in 'LHV':
            if up == 'H':
                x = a[0] + (x if rel else 0)
            elif up == 'V':
                y = a[0] + (y if rel else 0)
            else:
                x, y = a[0] + ox, a[1] + oy
            pts.append((x, y))
            last_ctrl = None
        elif up in 'CS':
            if up == 'C':
                c1 = (a[0] + ox, a[1] + oy)
                c2, end = (a[2] + ox, a[3] + oy), (a[4] + ox, a[5] + oy)
            else:
                c1 = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_ctrl[2] == 'c' else (x, y)
                c2, end = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            for k in (0, 1):
                for t in _cubic_extrema((x, y)[k], c1[k], c2[k], end[k]):
                    pts.append((_cubic_at(x, c1[0], c2[0], end[0], t), _cubic_at(y, c1[1], c2[1], end[1], t)))
            x, y = end
            pts.append(end)
            last_ctrl = (c2[0], c2[1], 'c')
        elif up in 'QT':
            if up == 'Q':
                q, end = (a[0] + ox, a[1] + oy), (a[2] + ox, a[3] + oy)
            else:
                q = (2 * x - last_ctrl[0], 2 * y - last_ctrl[1]) if last_ctrl and last_ctrl[2] == 'q' else (x, y)
                end = (a[0] + ox, a[1] + oy)
            # A quadratic is the cubic with controls 2/3 of the way to q.
            c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y))
            c2 = (end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]))
            for k in (0, 1):
                for t in _cubic_extrema((x, y)[k], c1[k], c2[k], end[k]):
                    pts.append((_cubic_at(x, c1[0], c2[0], end[0], t), _cubic_at(y, c1[1], c2[1], end[1], t)))
            x, y = end
            pts.append(end)
            last_ctrl = (q[0], q[1], 'q')
        elif up == 'A':
            end = (a[5] + ox, a[6] + oy)
            pts.extend(_arc_points(x, y, a[0], a[1], a[2], int(a[3]), int(a[4]), *end))
            x, y = end
            last_ctrl = None
    return pts


def artwork_box(svg):
    """(minx, miny, maxx, maxy) of every <path> in the SVG text."""
    xs, ys = [], []
    for d in re.findall(r'<path\b[^>]*?\sd="([^"]*)"', svg):
        for px, py in path_points(d):
            xs.append(px)
            ys.append(py)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def cropped_viewbox(boxes):
    """The viewBox string around the union of `boxes`, plus CROP_MARGIN."""
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    pad = CROP_MARGIN * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = (math.floor(x0 - pad), math.floor(y0 - pad), math.ceil(x1 + pad), math.ceil(y1 + pad))
    return f'{x0} {y0} {x1 - x0} {y1 - y0}'


def crop_team(paths):
    """Set the team's light and dark files to one viewBox around their
    artwork. Returns how many files changed (0 when already cropped)."""
    texts = {p: open(p, encoding='utf-8').read() for p in paths if os.path.exists(p)}
    boxes = [b for b in (artwork_box(t) for t in texts.values()) if b]
    if not boxes:
        return 0
    vb = cropped_viewbox(boxes)
    changed = 0
    for p, text in texts.items():
        new = re.sub(r'(<svg\b[^>]*?\sviewBox=")[^"]*(")', lambda m: m.group(1) + vb + m.group(2), text, count=1)
        if new != text:
            tmp = p + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(new)
            os.replace(tmp, p)
            changed += 1
    return changed


def team_codes():
    """Every team code base_data.json's summary has a season stat line for --
    the authoritative "teams this site actually has pages for" list (matches
    TEAM_TRUE_COLOR's keys in template.html 1:1 in practice)."""
    base_path = os.path.join(ROOT, 'base_data.json')
    if not os.path.exists(base_path):
        return []
    with open(base_path, encoding='utf-8') as f:
        base = json.load(f)
    return sorted(base.get('summary', {}).keys())


def main():
    codes = team_codes()
    if not codes:
        print("WARN: no team codes found in base_data.json -- nothing to do", file=sys.stderr)
        return
    os.makedirs(LOGOS_DIR, exist_ok=True)

    cached = 0
    downloaded = 0
    failed = 0

    for code in codes:
        abbrev = nhl_abbrev(code)
        for variant in VARIANTS:
            dest = os.path.join(LOGOS_DIR, f'{code}_{variant}.svg')
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                cached += 1
                continue
            url = LOGO_URL.format(abbrev=abbrev, variant=variant)
            data = fetch_bytes(url)
            if data is None:
                failed += 1
                print(f"WARN: no {variant} logo for {code} ({abbrev}) -- left on fallback for now", file=sys.stderr)
                continue
            # Write via a temp file + rename so a run interrupted mid-write
            # never leaves a truncated file behind that a later run's
            # os.path.getsize() check would treat as already-cached.
            tmp = dest + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, dest)
            downloaded += 1

    cropped = 0
    for code in codes:
        try:
            cropped += crop_team([os.path.join(LOGOS_DIR, f'{code}_{v}.svg') for v in VARIANTS])
        except (ValueError, IndexError, KeyError, ZeroDivisionError) as e:
            # An unexpected SVG keeps its own viewBox; the logo still shows.
            print(f"WARN: couldn't crop {code}'s logo ({e}) -- left as fetched", file=sys.stderr)

    print(f"team logos: {cached} already cached, {downloaded} newly downloaded, {failed} failed (left on fallback), {cropped} files cropped")


if __name__ == '__main__':
    main()
