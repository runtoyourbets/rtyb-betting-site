"""
Home page (index.html), the index pages and the Betting Guides
(scripts/guides.py), generated at
build time from the same data every sport page uses: NHL's merged data
(build_site.py) and each other sport's {slug}/data.json (sport_build.py).
Static -- the refresh job rebuilds them every run.

Sections, top to bottom: nav, then the shared front sections
(scripts/front.py sections, also on every Arena hub): the brand H1 (hubs:
the slogan line), the all-sports Preview from 11 AM ET (else Yesterday's
Best, large), Yesterday's Best, The Slate, Matchup of the Day, Hottest
Trends, Streak to Watch, The Big Numbers, Get the Running Tab (hubs
only), Yesterday's Results, then Betting Guides (3 guides); footer. Every
list of sports comes from sports.LAUNCHED (in season). Also writes
/matchups/, /odds/ and /trends/ (scripts/front.py index pages) and /picks/
(forwarded to /preview/ while sports.PICKS_LIVE is False: build_site).

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
import guides
import icons
import seo
import signup
import nav
import sports
import stats_index

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


def nav_html(status, depth='', current=None):
    """The shared site nav (scripts/nav.py). status: [(sport, chip, live, short)];
    current: the index page shown ('matchups', 'odds', 'trends', 'stats', 'preview')."""
    return nav.header(depth, [(sp, live, short) for sp, chip, live, short in status], current=current)


FOOTER = '''
<footer class="hf">
  <div class="hf-inner">
    <div class="ft-signup" id="premium"><h2>Get the Running Tab</h2><p>Our free newsletter: first-segment results, trends and previews.</p><!--signup:footer--></div>
    <p class="hf-rg"><b>21+ only.</b> Gambling problem? Call <a href="tel:18004262537">1-800-GAMBLER</a>. Please bet responsibly.</p>
    <p class="hf-small">RTYB &mdash; Run to Your Bets is for information and entertainment. Not affiliated with any league or sportsbook.
    Records and units are for tracking only; past results don&rsquo;t predict future ones.</p>
    <p class="hf-small">RTYB may earn a commission from sportsbook links.</p>
    <p class="hf-small hf-legal"><a href="__ROOT__betting-guides/">Betting Guides</a> &middot; <a href="__ROOT__privacy/">Privacy</a> &middot; <a href="__ROOT__terms/">Terms</a> &middot; <a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a></p>
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
  // Email signup: scripts/signup.py (Beehiiv forms; unblurs the trends after a signup)
})();
</script>'''


def page(title, desc, body, status, depth='', noindex=False, is_home=False, current=None):
    """noindex: reachable by URL but kept out of search (Picks, unwritten guides).
    The footer follows sports.FOOTER (the home page passes is_home)."""
    css = f'<link rel="stylesheet" href="{depth}assets/site.css">'
    robots = '<meta name="robots" content="noindex">' if noindex else ''
    footer = FOOTER if sports.footer_on(is_home) else ''
    return (f'<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">{nav.THEME_HEAD}'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<meta name="description" content="{esc(desc)}">{robots}{FONTS}{css}</head>'
            f'<body class="home">{nav_html(status, depth, current)}<main class="hp">{body}</main>{footer}{PAGE_JS}{account.ACCOUNT_JS}</body></html>')


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

    # every section is shared with the hubs (scripts/front.py), every sport in season
    S = front.load(now_utc)
    learn = ''.join(guides.card(f'{guides.INDEX_DIR}/{slug}/', t, d) for slug, t, d in guides.GENERAL[:LEARN_SHOWN])
    learn_html = (f'<section class="fr-sec" id="learn"><div class="fr-head"><h2>Betting Guides</h2></div>'
                  f'<div class="hl-grid">{learn}</div><div class="fr-links">{front.more_link(guides.INDEX_DIR + "/", "All guides")}</div></section>')
    front_html = front.sections(S, now_utc, learn=learn_html)
    pieces = daily.load()

    body = front_html   # no sport chips: the ☰ menu and the bottom bar cover it
    home = page(sports.page_title(front.HOME_H1, daily=True), f'First period, first quarter and first half betting odds, stats and trends for every {sports.sport_names()} game.',
                body, status, is_home=True).replace('__LOGO_SVG__', logo_svg)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(home)

    # /matchups/, /odds/ and /trends/: every sport's games (trends) today;
    # the All tab is in the HTML, the pills filter it in place
    for kind, x in front.INDEX.items():
        main = (front.trends_index_body(S, now_utc) if kind == 'trends' else front.index_body(S, now_utc, kind))
        out = page(x['title'], x['desc'].format(sports=sports.sport_names()), main + front.FRONT_JS,
                   status, depth='../', current=kind).replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, kind), exist_ok=True)
        with open(os.path.join(ROOT, kind, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)

    stats_index.write(page, status, logo_svg)
    guides.write(page, status, logo_svg)
    daily.write_pages(page, status, logo_svg, pieces)   # columns (previews: build_site.write_previews)
    seo.write_legal(page, status, logo_svg)
    today_n = sum(1 for sp in S.values() for g in sp.games(today) if front.game_lined(sp, g))
    return {'today': today_n, 'trends': front_html.count('ht-card')}


PICKS_H1 = f'{sports.CROSS_WORDS} Picks'


def picks_soon(h1=None):
    """The coming-soon block on /picks/ and every /{sport}/picks/ while
    sports.PICKS_LIVE is False (a sport page's H1 is its page head)."""
    return ((f'<section class="hp-sec pk-soon"><h1>{esc(h1)}</h1>' if h1 else '<section class="hp-sec pk-soon">') +
            '<p class="lead">Picks are coming with Premium.</p>'
            '<p>Daily first-period, first-quarter and first-half picks from RTYB&rsquo;s numbers, every one graded in public.</p>'
            '<div class="pk-soon-tab"><h2>Get the Running Tab</h2><p>Get on the list and you&rsquo;ll hear first.</p><!--signup:tab--></div></section>')


def picks_shell():
    """/picks/ while sports.PICKS_LIVE is False (the sport pages' are
    build_site.write_sport_extras)."""
    return picks_soon(PICKS_H1)


LEARN_SHOWN = 3   # guides on the home page, then "All guides"


def write_picks(template, nhl_data, logo_svg, body, now_utc=None):
    """picks/index.html around the body from picks.py, with the site nav."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, _ = collect(template, nhl_data)
    status = [(sp,) + sport_status(sp, by_sport.get(sp['key'], {}), today) for sp in sports.LAUNCHED]
    if not sports.PICKS_LIVE:   # the Premium shell; picks.build still keeps the log
        body = picks_shell()
    html = page(sports.page_title(PICKS_H1, daily=True), 'Trend-based plays for the first quarter, half, period and inning, ranked by confidence, with every tier’s record public.',
                body, status, depth='../', noindex=not sports.PICKS_LIVE, current='picks').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'picks'), exist_ok=True)
    with open(os.path.join(ROOT, 'picks', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

