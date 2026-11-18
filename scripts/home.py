"""
Home page (index.html) and Learn page (learn/index.html), generated at
build time from the same data every sport page uses: NHL's merged data
(build_site.py) and each other sport's {slug}/data.json (sport_build.py).
Static -- the refresh job rebuilds them every run.

Sections, top to bottom: nav, sport chips, then the shared front sections
(scripts/front.py sections, also on every Arena hub): the slogan line, On
Tap (or Yesterday's Best, large), Yesterday's Best, The Slate, Matchup of
the Day, Hottest Trends, Team to Watch, Biggest Line Move, Get the Running
Tab, Yesterday's Results, then Learn (3 guides); footer. Every list of
sports comes from sports.LAUNCHED (in season). Also writes /matchups/,
/odds/ and /trends/ (the trends past each sport's first 3 behind the
newsletter unlock).

Colors are the site tokens from assets/site.css (template.html :root).
"""
import html as html_lib
import json
import os
import re
from datetime import date as Date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account
import daily
import front
import icons
import seo
import signup
import nav
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800'
         '&family=Source+Sans+3:wght@400;500;600&display=swap">')


def esc(s):
    return html_lib.escape('' if s is None else str(s), quote=True)


def signed(n):
    if n is None:
        return ''
    n = int(n) if float(n).is_integer() else n
    return f'+{n}' if n > 0 else str(n)


def fmt_units(u):
    return f"{'+' if u > 0 else ''}{u:.2f}u"


def win_units(p):
    return 100 / abs(p) if p < 0 else p / 100


def implied(p):
    return -p / (-p + 100) if p < 0 else 100 / (p + 100)


def time_et(iso):
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return t.strftime('%-I:%M %p ET')


def day_label(d):
    return Date.fromisoformat(d).strftime('%a, %b %-d')


def badge(code, color, size=26):
    color = (color or '5B6674').lstrip('#')
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r = g = b = 91
    text = '#111111' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#FFFFFF'
    code = code or '?'
    fs = max(8, int(size * (0.34 if len(code) <= 3 else 0.27)))
    return (f'<span class="team-badge" style="width:{size}px;height:{size}px;background:#{color};color:{text};'
            f'font-size:{fs}px" aria-hidden="true">{esc(code)}</span>')


# ------------------------------------------------------------------ games

def nhl_colors(template):
    m = re.search(r'TEAM_TRUE_COLOR = \{(.*?)\};', template, re.S)
    return dict(re.findall(r"(\w+): '#([0-9A-Fa-f]{6})'", m.group(1))) if m else {}


def nhl_logo(code):
    """NHL's cached SVGs (fetch_team_logos.py), light and dark."""
    light = os.path.join(ROOT, 'assets', 'logos', f'{code}_light.svg')
    if not os.path.exists(light):
        return ''
    dark = f'assets/logos/{code}_dark.svg' if os.path.exists(os.path.join(ROOT, 'assets', 'logos', f'{code}_dark.svg')) else None
    return icons.logo_html(f'assets/logos/{code}_light.svg', dark, 24)


def nhl_games(nhl_data, colors):
    """NHL schedule in the shape the home page uses."""
    out = {}
    names = {c: v.get('name', c) for c, v in (nhl_data.get('summary') or {}).items()}
    for d, games in ((nhl_data.get('schedule') or {}).get('games') or {}).items():
        for g in games:
            st = g.get('state')
            state = 'final' if st in ('OFF', 'FINAL') else 'in' if st in ('LIVE', 'CRIT') else 'pre'
            o = g.get('odds') or {}
            ml = o.get('ml') or {}
            tot = ((o.get('totals') or {}).get('1.5')) or {}
            p1 = (g.get('awayP1'), g.get('homeP1'))
            out.setdefault(d, []).append({
                'sport': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'start': g.get('startTimeUTC'), 'state': state,
                'away': {'code': g['away'], 'name': names.get(g['away'], g['away']).split()[-1], 'color': colors.get(g['away']),
                         'logo': nhl_logo(g['away'])},
                'home': {'code': g['home'], 'name': names.get(g['home'], g['home']).split()[-1], 'color': colors.get(g['home']),
                         'logo': nhl_logo(g['home'])},
                'score': (g.get('awayFinal'), g.get('homeFinal')) if state != 'pre' else None,
                'seg': '1P', 'segScore': p1 if None not in p1 and state != 'pre' else None,
                'segFinal': state == 'final' and None not in p1,
                'lines': [f"ML {g['away']} {signed(ml.get(g['away']))} · {g['home']} {signed(ml.get(g['home']))}"] if ml.get(g['away']) is not None else [],
                'extra': [f"O/U 1.5 {signed(tot.get('over'))}/{signed(tot.get('under'))}"] if tot.get('over') is not None else [],
                'ml': ml, 'total15': tot, 'btts': (o.get('btts_yes'), o.get('btts_no')),
                'href': f"{sports.section_path('nhl', 'games').lstrip('/')}?date={d}",
            })
    return out


def team_view(doc, slug):
    t = (doc.get('teams') or {}).get(slug)
    if t:
        return {'code': t.get('code'), 'name': t.get('short') or t.get('name'), 'color': t.get('color'),
                'logo': icons.team_logo(doc['sport'], slug, 24, root='')}
    name = (doc.get('otherTeams') or {}).get(slug, slug)
    return {'code': ''.join(w[0] for w in name.split()[:3]).upper(), 'name': name, 'color': None}


def sport_games(doc):
    """One sport's data.json games in the home page shape."""
    out = {}
    seg = (doc.get('segments') or [{}])[0]
    k = seg.get('key')
    for d, games in (doc.get('games') or {}).items():
        for g in games:
            o = (g.get('odds') or {}).get(k) or {}
            res = (g.get('res') or {}).get(k) or {}
            a, h = team_view(doc, g['away']), team_view(doc, g['home'])
            lines = []
            if o.get('nrfi_yrfi'):
                lines.append(f"NRFI {signed(o['nrfi_yrfi'].get('nrfi'))} · YRFI {signed(o['nrfi_yrfi'].get('yrfi'))}")
            if o.get('ats'):
                lines.append(f"{seg.get('tag')} ATS {a['code']} {signed(o['ats']['away']['line'])}")
            if o.get('total'):
                lines.append(f"{seg.get('tag')} O/U {o['total']['line']}")
            out.setdefault(d, []).append({
                'sport': doc['sport'], 'label': doc['label'], 'slug': doc['slug'], 'start': g.get('start'),
                'state': g['state'] if g['state'] in ('pre', 'in', 'final') else 'off', 'away': a, 'home': h,
                'score': (g.get('as'), g.get('hs')) if g['state'] in ('in', 'final') else None,
                'seg': seg.get('tag'), 'segScore': tuple(res['sc']) if res.get('sc') else None,
                'segFinal': bool(res.get('sc')), 'res': res, 'segKey': k,
                'lines': lines, 'extra': [], 'note': g.get('note'),
                'href': f"{sports.section_path(doc['sport'], 'games').lstrip('/')}?date={d}",
            })
    return out


def locked_trends(n, cards):
    """The trends past the ones shown, blurred behind the newsletter box."""
    return (f'<div class="ht-locked"><div class="ht-blur" aria-hidden="true"><div class="tr-cards">{cards}</div></div>'
            f'<div class="ht-overlay"><div class="ht-lock-card">'
            f'<div class="ht-lock-title">{n} more trend{"s" if n != 1 else ""} today</div>'
            f'<p>Free with the Running Tab, our newsletter. Sign up once and they unlock on this device.</p>'
            f'<a class="btn-primary" href="#signup-tab">Get the Tab</a></div></div></div>')


def nav_html(status, depth=''):
    """The shared site nav (scripts/nav.py). status: [(sport, chip, live, short)]."""
    return nav.header(depth, [(sp, live, short) for sp, chip, live, short in status])


FOOTER = '''
<footer class="hf">
  <div class="hf-inner">
    <div class="ft-signup"><h2>Get the Running Tab</h2><p>Our free newsletter: first-segment results, trends and what&rsquo;s on tap.</p><!--signup:footer--></div>
    <p class="hf-rg"><b>21+ only.</b> Gambling problem? Call <a href="tel:18004262537">1-800-GAMBLER</a>. Please bet responsibly.</p>
    <p class="hf-small">RTYB &mdash; Run to Your Bets is for information and entertainment. Not affiliated with any league or sportsbook.
    Records and units are for tracking only; past results don&rsquo;t predict future ones.</p>
    <p class="hf-small">RTYB may earn a commission from sportsbook links.</p>
    <p class="hf-small hf-legal"><a href="__ROOT__privacy/">Privacy</a> &middot; <a href="__ROOT__terms/">Terms</a> &middot; <a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a></p>
  </div>
</footer>'''

PAGE_JS = '''
<script>
(function() {
  'use strict';
  var root = document.documentElement;
  try { var saved = localStorage.getItem('rtyb-theme'); if (saved) root.setAttribute('data-theme', saved); } catch (e) {}
  function toggleTheme() {
    var cur = root.getAttribute('data-theme');
    var isDark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next = isDark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('rtyb-theme', next); } catch (e) {}
  }
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);
  // the menus are wired by scripts/nav.py
  // League chips: arrows (and edge fades) when the row is wider than the
  // screen; each arrow shows only when there's more that way.
  var hsRow = document.getElementById('hsRow'), hsWrap = document.getElementById('hsWrap');
  if (hsRow) {
    var prev = hsWrap.querySelector('.prev'), next = hsWrap.querySelector('.next');
    var syncArrows = function() {
      var max = hsRow.scrollWidth - hsRow.clientWidth;
      prev.hidden = hsRow.scrollLeft <= 2;
      next.hidden = hsRow.scrollLeft >= max - 2;
      hsWrap.classList.toggle('fade-l', !prev.hidden);
      hsWrap.classList.toggle('fade-r', !next.hidden);
    };
    var by = function(dir) { hsRow.scrollBy({ left: dir * Math.max(160, hsRow.clientWidth * 0.7), behavior: 'smooth' }); };
    prev.addEventListener('click', function() { by(-1); });
    next.addEventListener('click', function() { by(1); });
    hsRow.addEventListener('scroll', syncArrows, { passive: true });
    window.addEventListener('resize', syncArrows);
    syncArrows();
  }
  // Email signup: scripts/signup.py (Beehiiv forms; unblurs the trends after a signup)
})();
</script>'''


def page(title, desc, body, status, depth='', noindex=False, is_home=False):
    """noindex: reachable by URL but kept out of search (Picks, Streaks).
    The footer follows sports.FOOTER (the home page passes is_home)."""
    css = f'<link rel="stylesheet" href="{depth}assets/site.css">'
    robots = '<meta name="robots" content="noindex">' if noindex else ''
    footer = FOOTER if sports.footer_on(is_home) else ''
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<meta name="description" content="{esc(desc)}">{robots}{FONTS}{css}</head>'
            f'<body class="home">{nav_html(status, depth)}<main class="hp">{body}</main>{footer}{PAGE_JS}{account.ACCOUNT_JS}</body></html>')


# ------------------------------------------------------------------- build

def sport_status(sp, games_by_date, today):
    """(chip text, live?, short label for the menu)."""
    todays = len(games_by_date.get(today, []))
    dates = sorted(games_by_date)
    if not dates:
        month = sports.MONTHS[sp['season_start'] - 1][:3]
        return 'Soon', False, month
    t = Date.fromisoformat(today)
    # In season = games today, or a final within the last two weeks (playoff gaps).
    recent = [d for d in dates if d < today and (t - Date.fromisoformat(d)).days <= 14
              and any(g['state'] == 'final' for g in games_by_date[d])]
    if todays and (recent or any(g['state'] != 'pre' for g in games_by_date[today])):
        return f'{todays} today', True, 'LIVE'
    # an off day mid-season stays LIVE; a season that just ended (no game
    # in the coming week) never does
    if recent and any(today < d <= (t + timedelta(days=7)).isoformat() for d in dates):
        return 'Off today', True, 'LIVE'
    if todays:
        return f'Starts today ({todays})', True, 'LIVE'
    upcoming = [d for d in dates if d > today]
    if upcoming and (Date.fromisoformat(upcoming[0]) - t).days <= 60:
        nd = Date.fromisoformat(upcoming[0])
        return f'Starts {nd.strftime("%b %-d")}', False, nd.strftime('%b %-d')
    month = sports.MONTHS[sp['season_start'] - 1]
    return f'Back in {month[:3]}', False, month[:3]


def collect(template, nhl_data):
    """Every sport's games by date in the home page shape, plus each
    non-NHL sport's data.json."""
    colors = nhl_colors(template)
    by_sport = {'nhl': nhl_games(nhl_data, colors)}
    docs = {}
    for sp in sports.SPORTS:
        if sp['key'] == 'nhl':
            continue
        path = os.path.join(ROOT, sp['slug'], 'data.json')
        doc = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        docs[sp['key']] = doc
        by_sport[sp['key']] = sport_games(doc) if doc.get('games') is not None and doc.get('segments') else {}
    return by_sport, docs


def sport_statuses(template, nhl_data, now_utc=None):
    """{sport key: {'chip', 'live', 'short'}} -- the same LIVE / date /
    month labels the home page shows, for every page's Sports menu."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, _ = collect(template, nhl_data)
    out = {}
    for sp in sports.SPORTS:
        chip, live, short = sport_status(sp, by_sport.get(sp['key'], {}), today)
        out[sp['key']] = {'chip': chip, 'live': live, 'short': short}
    return out


def build(template, nhl_data, logo_svg, now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, docs = collect(template, nhl_data)

    status = []
    for sp in sports.LAUNCHED:
        chip, live, short = sport_status(sp, by_sport.get(sp['key'], {}), today)
        status.append((sp, chip, live, short))

    # ---- sections
    chips = ''.join(
        f'<a class="hs-chip{" live" if live else ""}" href="{sports.section_path(sp, "games").lstrip("/")}">'
        f'<span class="hs-name">{icons.sport_icon(sp)}{esc(sp["label"])}</span><span class="hs-count">{esc(chip)}</span></a>'
        for sp, chip, live, short in status)

    # every section is shared with the hubs (scripts/front.py), every sport in season
    S = front.load(now_utc)
    learn = ''.join(f'<a class="hl-card" href="learn/#{a}"><b>{esc(t)}</b><span>{esc(d)}</span></a>' for a, t, d in LEARN_LINKS[:LEARN_SHOWN])
    learn_html = (f'<section class="fr-sec" id="learn"><div class="fr-head"><h2>Learn</h2></div>'
                  f'<div class="hl-grid">{learn}</div><div class="fr-links">{front.more_link("learn/", "All guides")}</div></section>')
    front_html = front.sections(S, now_utc, learn=learn_html)
    pieces = daily.load()

    chip_row = (f'<div class="hs-wrap" id="hsWrap">'
                f'<button class="hs-arrow prev" type="button" aria-label="Scroll leagues left" hidden>&lsaquo;</button>'
                f'<div class="hs-row" id="hsRow">{chips}</div>'
                f'<button class="hs-arrow next" type="button" aria-label="Scroll leagues right" hidden>&rsaquo;</button></div>')
    body = f'{chip_row}{front_html}'
    home = page('RTYB — Run to Your Bets', f'First period, first quarter and first half betting odds, stats and trends for every {sports.sport_names()} game.',
                body, status, is_home=True).replace('__LOGO_SVG__', logo_svg)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(home)

    # /matchups/, /odds/ and /trends/: every sport's games (trends) today;
    # the All tab is in the HTML, the pills filter it in place
    for kind, x in front.INDEX.items():
        main = (front.trends_index_body(S, now_utc, locked_trends) if kind == 'trends' else front.index_body(S, now_utc, kind))
        out = page(x['title'], x['desc'].format(sports=sports.sport_names()), main + front.FRONT_JS,
                   status, depth='../').replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, kind), exist_ok=True)
        with open(os.path.join(ROOT, kind, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)

    learn_page = page('Learn: How 1st Period, Quarter and Half Bets Work | RTYB', 'How first-segment bets work: spreads, moneylines, totals, NRFI, First Five and units.',
                      LEARN_BODY, status, depth='../').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'learn'), exist_ok=True)
    with open(os.path.join(ROOT, 'learn', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(learn_page)
    daily.write_pages(page, status, logo_svg, pieces)
    seo.write_legal(page, status, logo_svg)
    today_n = sum(1 for sp in S.values() for g in sp.games(today) if front.game_lined(sp, g))
    return {'today': today_n, 'trends': front_html.count('ht-card')}


LEARN_SHOWN = 3   # guides on the home page, then "All guides"
LEARN_LINKS = [
    ('segments', 'First-segment bets', 'Why the 1st period, quarter, half and inning.'),
    ('ats', 'Spread (ATS)', 'Covering, pushes and the -110 price.'),
    ('su', 'Moneyline and SU', 'Straight-up records, ties and prices.'),
    ('totals', 'Totals (O/U)', 'Overs, unders and whole-number pushes.'),
    ('nrfi', 'NRFI / YRFI and F5', 'Baseball’s first inning and first five.'),
    ('units', 'Units', 'How RTYB counts profit and loss.'),
    ('confidence', 'How confidence works', 'How Today’s Picks are scored, tiered and graded.'),
]


def write_picks(template, nhl_data, logo_svg, body, now_utc=None):
    """picks/index.html around the body from picks.py, with the site nav."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, _ = collect(template, nhl_data)
    status = [(sp,) + sport_status(sp, by_sport.get(sp['key'], {}), today) for sp in sports.LAUNCHED]
    html = page('Today’s Picks | RTYB', 'Trend-based plays for the first quarter, half, period and inning, ranked by confidence, with every tier’s record public.',
                body, status, depth='../', noindex=True).replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'picks'), exist_ok=True)
    with open(os.path.join(ROOT, 'picks', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

LEARN_BODY = '''
<section class="hp-sec learn">
  <h1>Learn</h1>
  <p class="lead">RTYB tracks the opening segment of every game. Here&rsquo;s what each market means and how we grade it.</p>
  <h2 id="segments">First-segment bets</h2>
  <p>Instead of the whole game, these bets settle on the first piece of it: the 1st period in the NHL, the 1st quarter or
  1st half in football and basketball, and the 1st inning or first five innings in baseball. They settle fast and
  depend on how teams start, which is what RTYB&rsquo;s records and trends measure.</p>
  <h2 id="ats">Spread (ATS)</h2>
  <p>The favorite gives points and the underdog gets them: &ldquo;Lakers &minus;1.5&rdquo; wins if the Lakers win the
  segment by 2 or more. Records are W-L-P &mdash; a push (P) is when the margin lands exactly on the line, and the bet is
  refunded. Spreads are usually priced at &minus;110 (risk $110 to win $100) unless another price is listed.</p>
  <h2 id="su">Moneyline and SU</h2>
  <p>A moneyline bet is on who wins the segment outright. RTYB shows these records as SU (straight up), W-L-T. A tie
  in the segment is a push for the bet (0 units). Prices: &minus;150 means risk $150 to win $100; +130 means risk $100 to
  win $130.</p>
  <h2 id="totals">Totals (Over / Under)</h2>
  <p>A bet on combined points, goals or runs in the segment. Records are O-U-P. A half-point line (44.5) can&rsquo;t push;
  a whole-number line (44) pushes when the total lands on it exactly.</p>
  <h2 id="nrfi">NRFI / YRFI and First Five (F5)</h2>
  <p>NRFI is &ldquo;no run first inning&rdquo; &mdash; neither team scores in the 1st. YRFI is the opposite. There are no
  pushes; if the 1st inning isn&rsquo;t finished, it&rsquo;s No Action. First Five bets settle on the score after five
  innings: the F5 spread is always 0.5 runs (a tie goes to the +0.5 side), an F5 moneyline tie is a push, and fewer than
  five innings played means No Action.</p>
  <h2 id="units">Units</h2>
  <p>1 unit = $100 risked on every game in a category at the listed price. A loss is &minus;1 unit; a win pays by the
  price (+0.91u at &minus;110). Pushes, ties and No Action are 0. Records that need odds &mdash; spreads, totals,
  favorites and units &mdash; only count games with saved odds, and say how many (&ldquo;based on N games with
  odds&rdquo;).</p>
  <h2 id="confidence">How confidence works (Today&rsquo;s Picks)</h2>
  <p>Every play on <a href="../picks/">Today&rsquo;s Picks</a> starts from a saved line: a moneyline price, a spread or a
  total. For each side, RTYB collects angles from this season&rsquo;s graded games played before it, at <em>today&rsquo;s</em>
  line: the team&rsquo;s record this season, over its last 8 and at this venue, and the opponent&rsquo;s record at its venue
  (for totals, both teams&rsquo; games). Each angle&rsquo;s hit rate is pulled toward 50% by 8 imaginary games, so small samples
  move less, and the angles are averaged by sample size. The <b>edge</b> is that estimate minus the chance the price
  implies (&minus;110 when no price was saved).</p>
  <p>A play needs at least two angles that agree and an edge of 3% or more. <b>A-tier</b>: edge 6%+ on a sample of 15+ with a
  saved price. <b>B-tier</b>: edge 4%+ on 10+. Everything else is <b>C</b>, and a sample under 10 can&rsquo;t rank above C.
  Personalities tag the style of each play (Chalk Eater, Dog Hunter, Streak Rider, Contrarian, Over Lover, Under Grinder,
  Early Bird).</p>
  <p>Plays lock when the game starts and are graded on the saved line and price: wins at the price, losses &minus;1u, pushes
  and tied moneyline segments 0u. Records start from the first day Picks went live; nothing is backfilled.</p>
  <h2 id="responsible">Bet responsibly</h2>
  <p>Only bet what you can afford to lose. If gambling stops being fun, call 1-800-GAMBLER for free, confidential help.</p>
</section>'''
