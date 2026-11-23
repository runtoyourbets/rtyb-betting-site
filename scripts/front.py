"""
The front-page sections, one component each, shared by the home page (every
sport in season), each Arena hub /{sport}/ (that sport only) and the index
pages /matchups/ and /odds/ (every sport, today):

  Yesterday's Best     the one market with the best record (and positive
                       units) yesterday; hidden when nothing was positive
  The Slate            the next 3 games to start, per sport pill (All first)
  Hottest Trends       the trend cards with the biggest edge over the league
  Yesterday's Results  each sport's Results box, by segment

Everything is static HTML written at build time (search engines see every
game); a small script (FRONT_JS) switches the pills and, as games start,
moves the next ones up the Slate and marks trend rows LIVE.

A game with no saved line for any market of its segment shows nowhere
(game_lined); the Results rows count only games with a line for the market,
so the record and the units cover the same games (assets/sport.js
resultRows does the same on the Matchups page).

Each sport's games come from its data.json (NHL: sport.json, the same
shape), prices from {slug}/odds/{date}.json (the Odds page's best price),
trend cards from {slug}/trends.json. `root` prefixes every link and asset:
'' on the home page, '../' one folder down (hubs, /matchups/, /odds/).
"""
import html as html_lib
import json
import os
from datetime import date as Date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import definitions
import books as books_cfg
import icons
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
SLATE_SHOWN = 3        # games per Slate tab
SLATE_BUFFER = 12      # per sport, so games can drop off between builds
TRENDS_SHOWN = 3       # trend cards before "Show more"
TRENDS_MORE = 6        # ... and after it
TREND_ROWS = 5         # game rows per trend card
TREND_MIN_N = 20       # Hottest Trends: games behind the record,
TREND_MIN_EDGE = 0.05  # ... and points over the league rate, to qualify
TREND_MIN_RATE = 0.55  # every Hottest Trends card (home, hubs, /trends/): a 55%+ win rate
RECORD_TIP = (definitions.tooltips().get('record_line') or {}).get('tooltip') or ''   # the record line's hover text
HOT_SHOWN = 3          # Hottest Trends: exactly this many cards,
HOT_ROWS = 3           # ... with up to this many game rows each
BEST_SHOW_U = 1.0      # Yesterday's Best: the units a row needs
BEST_MIN_PCT = 0.55    # ... and the win rate
BEST_PER_SPORT = 2     # ... and at most this many rows from one sport
ML_CAP = 2000          # moneylines past -2000 / +2000 show a dash
FLIP = {'W': 'L', 'L': 'W'}


def esc(s):
    return html_lib.escape('' if s is None else str(s), quote=True)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def signed(n):
    if n is None:
        return ''
    n = int(n) if float(n).is_integer() else n
    return f'+{n}' if n > 0 else str(n)


def line_txt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def price_txt(p):
    """A price, or a dash past -2000 / +2000."""
    if not isinstance(p, (int, float)):
        return '-'
    return '-' if abs(p) > ML_CAP else esc(signed(round(p)))


def fmt_units(u):
    r = round(u, 2)
    return f"{'+' if r > 0 else ''}{r:.2f}u"


def unit_tone(u):
    # green above +0.5u, red below -0.5u, yellow between (CLAUDE.md color rule)
    r = round(u, 2)
    return 'pos' if r > 0.5 else 'neg' if r < -0.5 else 'mid'


def units_pill(u, priced):
    if not priced:
        return '<span class="u-pill u-none">-</span>'
    r = round(u, 2)
    cls = 'u-pos2' if r >= 3 else 'u-pos1' if r > 0.5 else 'u-neg2' if r < -3 else 'u-neg1' if r < -0.5 else 'u-mid'
    return f'<span class="u-pill {cls}">{fmt_units(r)}</span>'


def implied(p):
    return -p / (-p + 100) if p < 0 else 100 / (p + 100)


def parse(iso):
    try:
        return datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except ValueError:
        return None


def time_et(iso):
    t = parse(iso)
    return t.astimezone(ET).strftime('%-I:%M %p ET') if t else 'TBD'


def day_label(d):
    return Date.fromisoformat(d).strftime('%a, %b %-d')


# ----------------------------------------------------------------- data
class Sport:
    """One sport's data for the sections: its data.json (NHL: sport.json),
    trends.json, and the Odds page's files."""

    def __init__(self, sp):
        self.sp, self.key, self.label = sp, sp['key'], sp['label']
        self.dir = os.path.join(ROOT, sp['slug'])
        self.doc = read_json(os.path.join(self.dir, 'sport.json' if sp['key'] == 'nhl' else 'data.json'), {}) or {}
        self.trends = read_json(os.path.join(self.dir, 'trends.json'), {}) or {}
        self.hub = read_json(os.path.join(self.dir, 'hub.json'), {}) or {}
        self.sources = (read_json(os.path.join(self.dir, 'odds.json'), {}) or {}).get('sources') or {}
        self.segments = self.doc.get('segments') or sp['segments']
        self.weekly = sp.get('schedule') == 'week'
        self._odds = {}
        self.matchups = sports.section_path(sp, 'games').lstrip('/')
        self.odds_page = sports.section_path(sp, 'odds').lstrip('/')
        self.trends_page = sports.section_path(sp, 'trends').lstrip('/')

    def games(self, d):
        return list((self.doc.get('games') or {}).get(d) or [])

    def all_games(self):
        for d in sorted(self.doc.get('games') or {}):
            for g in self.doc['games'][d]:
                yield d, g

    def odds_game(self, d, g):
        """The Odds page's row for the game (best price per side, every book)."""
        if d not in self._odds:
            self._odds[d] = {(x['away'], x['home']): x for x in (read_json(os.path.join(self.dir, 'odds', f'{d}.json'), {}) or {}).get('games') or []}
        return self._odds[d].get((g['away'], g['home'])) or {}

    # ---- teams: one code everywhere (sports.team_code / other_code)
    def team(self, slug):
        return (self.doc.get('teams') or {}).get(slug) or {}

    def name_html(self, slug):
        """Desktop: the nickname (college: the school); phones: the code."""
        t = self.team(slug)
        full = t.get('short') or t.get('name') or (self.doc.get('otherTeams') or {}).get(slug) or self.code(slug)
        return f'<span class="tn-full">{esc(full)}</span><span class="tn-short">{esc(self.code(slug))}</span>'

    def full_name(self, slug):
        """"Phoenix Suns"; college: the school (CLAUDE.md: never the nickname)."""
        t = self.team(slug)
        if self.key in sports.COLLEGE:
            return t.get('short') or t.get('name') or (self.doc.get('otherTeams') or {}).get(slug) or self.code(slug)
        return t.get('name') or t.get('short') or (self.doc.get('otherTeams') or {}).get(slug) or self.code(slug)

    def link(self, slug, inner, root, cls='gm-team'):
        """inner linked to the team's page (a span when it has none)."""
        href = self.team_href(slug, root)
        return f'<a class="{cls}" href="{esc(href)}">{inner}</a>' if href else f'<span class="{cls}">{inner}</span>'

    def team_href(self, slug, root):
        """The team's page, or None when it has none (non-league opponents)."""
        d = os.path.join(self.dir, 'teams', str(slug).lower())
        return f'{root}{self.sp["slug"]}/teams/{str(slug).lower()}/' if os.path.isdir(d) else None

    def code(self, slug):
        t = self.team(slug)
        return t.get('code') or (self.doc.get('otherCodes') or {}).get(slug) or sports.other_code(self.key, (self.doc.get('otherTeams') or {}).get(slug, slug))

    def badge(self, slug, size=22, root=''):
        """The team's logo, else a team-color badge with its code."""
        t = self.team(slug)
        if t.get('svg'):   # NHL: assets/logos/{CODE}_light.svg / _dark.svg
            return icons.logo_html(f'{root}assets/logos/{slug}_light.svg', f'{root}assets/logos/{slug}_dark.svg', size)
        logo = icons.team_logo(self.key, slug, size, root=root)
        if logo:
            return logo
        hexc = str(t.get('color') or '5B6674').lstrip('#')
        try:
            r, g, b = (int(hexc[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            hexc, r, g, b = '5B6674', 91, 102, 116
        fg = '#111' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#FFF'
        code = self.code(slug)
        fs = max(8, round(size * (0.27 if len(code) > 3 else 0.34)))
        return (f'<span class="team-badge" style="width:{size}px;height:{size}px;background:#{hexc};color:{fg};'
                f'font-size:{fs}px" aria-hidden="true">{esc(code)}</span>')

    # ---- prices: the Odds page's best, else the saved line
    def market(self, d, g, k):
        """{market: best row} for segment k."""
        best = ((self.odds_game(d, g).get('best') or {}).get(k)) or {}
        saved = (g.get('odds') or {}).get(k) or {}
        return {m: best.get(m) or saved.get(m) for m in set(best) | set(saved) if best.get(m) or saved.get(m)}

    def seg_keys(self):
        return [s['key'] for s in self.segments]


def game_lined(sport, g, k=None):
    """A saved line for any market of the segment (any segment when k is
    None); a game without one shows nowhere."""
    keys = [k] if k else sport.seg_keys()
    if sport.doc.get('sportType') == 'baseball':
        keys = ['1i', 'f5']
    for x in keys:
        o = (g.get('odds') or {}).get(x) or {}
        for v in o.values():
            if v is not None and (not isinstance(v, dict) or any(y is not None for y in v.values())):
                return True
    return False


def started(g, now):
    if g.get('state') in ('in', 'final', 'post'):
        return True
    t = parse(g.get('start')) if g.get('start') else None
    return bool(t) and t <= now


def load(now_utc=None, keys=None):
    """{key: Sport} for the sports in season (the home and index pages' games
    and trends), or `keys` (a hub: any sport on the site), in menu order."""
    if keys is None:
        return {sp['key']: Sport(sp) for sp in sports.IN_SEASON}
    return {sp['key']: Sport(sp) for sp in sports.LAUNCHED if sp['key'] in keys}


# ------------------------------------------------------ Results box rows
# The Matchups page's Results box (assets/sport.js resultRows), the same
# rows in the same order: only games with a line for the market count.
class Row:
    def __init__(self, label, ties=False, no_tie=False, always=False):
        self.label, self.ties, self.no_tie, self.always = label, ties, no_tie, always
        self.w = self.l = self.t = self.n = 0
        self.u = 0.0

    def add(self, r, u):
        if not r or u is None:
            return
        if r == 'W':
            self.w += 1
        elif r == 'L':
            self.l += 1
        else:
            self.t += 1
        self.u += u
        self.n += 1

    @property
    def gp(self):
        return self.w + self.l + self.t

    @property
    def pct(self):
        return self.w / (self.w + self.l) if self.w + self.l else None

    def rec(self):
        return f'{self.w}-{self.l}' + ('' if self.no_tie else f'-{self.t}')


def fav_side(o):
    ml = (o or {}).get('ml') or {}
    a, h = ml.get('away'), ml.get('home')
    if isinstance(a, (int, float)) and isinstance(h, (int, float)) and implied(a) != implied(h):
        return 'away' if implied(a) > implied(h) else 'home'
    line = (((o or {}).get('ats') or {}).get('away') or {}).get('line')
    if isinstance(line, (int, float)) and line != 0:
        return 'away' if line < 0 else 'home'
    return None


def seg_fav(g, k):
    f = fav_side((g.get('odds') or {}).get(k))
    if f:
        return f
    ml = g.get('fml') or {}
    if isinstance(ml.get('away'), (int, float)) and isinstance(ml.get('home'), (int, float)) and implied(ml['away']) != implied(ml['home']):
        return 'away' if implied(ml['away']) > implied(ml['home']) else 'home'
    return ('home' if g['fs'] < 0 else 'away') if g.get('fs') else None


def result_rows(sport, games, k):
    def done(g, key):
        r = (g.get('res') or {}).get(key)
        return r if g.get('state') == 'final' and r and r.get('sc') and not r.get('na') else None

    def su_side(r, home):
        x = r.get('su')
        if not x or x == 'NA':
            return None
        x = FLIP.get(x, x) if home else x
        return x if x in ('W', 'L') else 'T'

    def u_at(u, m, i):
        v = (u or {}).get(m)
        return v[i] if v and len(v) > i else None

    rows = []
    if sport.key == 'nhl':
        hm, fv = Row('Home teams', ties=True), Row('Favorites', ties=True)
        ov, bt = Row('O/U: Over 1.5', no_tie=True), Row('BTTS Yes', no_tie=True)
        m3 = Row('3-way ML (home team)', no_tie=True, always=True)
        rows = [hm, fv, ov, bt, m3]
        for g in games:
            r = done(g, '1p')
            if not r:
                continue
            u = r.get('u') or {}
            hm.add(su_side(r, True), u_at(u, 'su', 1))
            f = seg_fav(g, '1p')
            if f:
                fv.add(su_side(r, f == 'home'), u_at(u, 'su', 0 if f == 'away' else 1))
            if r.get('tot') in ('O', 'U'):
                ov.add('W' if r['tot'] == 'O' else 'L', u_at(u, 'tot', 0))
            if r.get('btts') in ('Y', 'N'):
                bt.add('W' if r['btts'] == 'Y' else 'L', u_at(u, 'btts', 0))
            if r.get('su') and r['su'] != 'NA':
                m3.add('W' if r['su'] == 'L' else 'L', u_at(u, 'ml3', 1))
    elif sport.doc.get('sportType') == 'baseball':
        bh, bf = Row('Home teams (F5 moneyline)', ties=True), Row('Favorites (F5)', ties=True)
        yr, fo = Row('YRFI', no_tie=True), Row('F5 O/U: Over')
        rows = [bh, bf, yr, fo]
        for g in games:
            r, ri = done(g, 'f5'), done(g, '1i')
            if ri and ri.get('rfi') in ('Y', 'N'):
                yr.add('W' if ri['rfi'] == 'Y' else 'L', u_at(ri.get('u'), 'rfi', 0))
            if not r:
                continue
            u = r.get('u') or {}
            bh.add(su_side(r, True), u_at(u, 'su', 1))
            f = seg_fav(g, 'f5')
            if f:
                bf.add(su_side(r, f == 'home'), u_at(u, 'su', 0 if f == 'away' else 1))
            if r.get('tot') and r['tot'] != 'NA':
                fo.add({'O': 'W', 'U': 'L'}.get(r['tot'], 'T'), u_at(u, 'tot', 0))
    else:
        seg = next((s for s in sport.segments if s['key'] == k), {})
        ml = 'ML' in (seg.get('markets') or ['ML'])
        sh = Row('Home teams (moneyline)') if ml else None
        sf = Row('Favorites (moneyline)') if ml else None
        sa, so = Row('Favorites (spread)'), Row('O/U: Over')
        rows = [x for x in (sh, sf, sa, so) if x]
        for g in games:
            r = done(g, k)
            if not r:
                continue
            u, o = r.get('u') or {}, (g.get('odds') or {}).get(k) or {}
            if ml:
                sh.add(su_side(r, True), u_at(u, 'su', 1))
                f = seg_fav(g, k)
                if f:
                    sf.add(su_side(r, f == 'home'), u_at(u, 'su', 0 if f == 'away' else 1))
            line = ((o.get('ats') or {}).get('away') or {}).get('line')
            if r.get('ats') and r['ats'] != 'NA' and isinstance(line, (int, float)) and line != 0:
                fs = 'away' if line < 0 else 'home'
                x = FLIP.get(r['ats'], r['ats']) if fs == 'home' else r['ats']
                sa.add(x if x in ('W', 'L') else 'T', u_at(u, 'ats', 0 if fs == 'away' else 1))
            if r.get('tot') and r['tot'] != 'NA':
                so.add({'O': 'W', 'U': 'L'}.get(r['tot'], 'T'), u_at(u, 'tot', 0))
    any_final = any(g.get('state') == 'final' for g in games)
    return [x for x in rows if x.gp or (x.always and any_final and x.n)]


def results_title(d):
    dt = Date.fromisoformat(d)
    return f"{dt.strftime('%A')} {dt.month}/{dt.day} Results"


def results_box(rows, title):
    """The Matchups page's Results box (assets/sport.js resultsBox)."""
    if not rows:
        return ''
    body = ''.join(
        f'<div class="ds-row"><span class="ds-label">{esc(x.label)}</span><span class="ds-right">'
        f'<span class="ds-record ds-col-rec mono">{x.rec()}</span>'
        f'<span class="ds-col-pct mono">{"-" if x.pct is None else str(round(x.pct * 100)) + "%"}</span>'
        f'<span class="ds-col-units">{units_pill(x.u, x.n)}</span></span></div>' for x in rows)
    return (f'<div class="daily-summary gm-results"><h3>{esc(title)}</h3>'
            '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span>'
            '<span class="ds-col-pct">Win %</span><span class="ds-col-units">Units</span></span></div>' + body + '</div>')


def seg_tag(sport, k):
    return next((s['tag'] for s in sport.segments if s['key'] == k), k.upper())


def result_segments(sport):
    """The segments a Results box is drawn for (NHL and MLB: one box)."""
    if sport.key == 'nhl':
        return ['1p']
    if sport.doc.get('sportType') == 'baseball':
        return ['f5']
    return sport.seg_keys()


# ------------------------------------------------------ Yesterday's Best
def best_rows(sport, games, k):
    """[(short market, Row)] for one segment yesterday, every side of every
    market: home / road, favorite / underdog (moneyline and spread), Over /
    Under, NHL's 3-way and BTTS Yes / No, YRFI / NRFI. Only games with a
    line count (the unit figures are only there for those)."""
    def done(g, key):
        r = (g.get('res') or {}).get(key)
        return r if g.get('state') == 'final' and r and r.get('sc') and not r.get('na') else None

    def side_res(x, side):
        if not x or x == 'NA':
            return None
        x = FLIP.get(x, x) if side == 'home' else x
        return x if x in ('W', 'L') else 'T'

    def u_at(u, m, i):
        v = (u or {}).get(m)
        return v[i] if v and len(v) > i else None

    nhl, base = sport.key == 'nhl', sport.doc.get('sportType') == 'baseball'
    seg = 'f5' if base else k
    tag = 'F5' if base else seg_tag(sport, k)
    seg_info = next((s for s in sport.segments if s['key'] == seg), {})
    has_ml = nhl or base or 'ML' in (seg_info.get('markets') or ['ML'])
    rows = {}

    def add(label, res, u):
        rows.setdefault(label, Row(label)).add(res, u)
    for g in games:
        r = done(g, seg)
        if r:
            u, o = r.get('u') or {}, (g.get('odds') or {}).get(seg) or {}
            if has_ml:
                f = seg_fav(g, seg)
                for side in ('away', 'home'):
                    x, ux = side_res(r.get('su'), side), u_at(u, 'su', 0 if side == 'away' else 1)
                    add(f'{tag} {"Road" if side == "away" else "Home"} ML', x, ux)
                    if f:
                        add(f'{tag} {"Fav" if side == f else "Dog"} ML', x, ux)
            line = ((o.get('ats') or {}).get('away') or {}).get('line')
            if not nhl and r.get('ats') and r['ats'] != 'NA' and isinstance(line, (int, float)) and line != 0:
                fs = 'away' if line < 0 else 'home'
                for side in ('away', 'home'):
                    add(f'{tag} {"Fav" if side == fs else "Dog"} Spread', side_res(r['ats'], side), u_at(u, 'ats', 0 if side == 'away' else 1))
            if r.get('tot') and r['tot'] != 'NA':
                ou = ' 1.5' if nhl else ''
                add(f'{tag} Over{ou}', {'O': 'W', 'U': 'L'}.get(r['tot'], 'T'), u_at(u, 'tot', 0))
                add(f'{tag} Under{ou}', {'U': 'W', 'O': 'L'}.get(r['tot'], 'T'), u_at(u, 'tot', 1))
            if nhl and r.get('su') and r['su'] != 'NA':   # 3-way: a tie loses both teams
                add(f'{tag} 3-Way Road', 'W' if r['su'] == 'W' else 'L', u_at(u, 'ml3', 0))
                add(f'{tag} 3-Way Home', 'W' if r['su'] == 'L' else 'L', u_at(u, 'ml3', 1))
            if nhl and r.get('btts') in ('Y', 'N'):
                add(f'{tag} BTTS Yes', 'W' if r['btts'] == 'Y' else 'L', u_at(u, 'btts', 0))
                add(f'{tag} BTTS No', 'W' if r['btts'] == 'N' else 'L', u_at(u, 'btts', 1))
        ri = done(g, '1i') if base and k == 'f5' else None
        if ri and ri.get('rfi') in ('Y', 'N'):
            add('YRFI', 'W' if ri['rfi'] == 'Y' else 'L', u_at(ri.get('u'), 'rfi', 0))
            add('NRFI', 'W' if ri['rfi'] == 'N' else 'L', u_at(ri.get('u'), 'rfi', 1))
    return list(rows.items())


def best_cands(S, yday):
    """[(sport, short market, row)] yesterday at +1.0u or better and a 55%+
    win rate, any market and side, the most units first."""
    cand = []
    for sport in S.values():
        games = [g for g in sport.games(yday)]
        for k in result_segments(sport):
            for label, x in best_rows(sport, games, k):
                if x.n and round(x.u, 2) >= BEST_SHOW_U and (x.pct or 0) >= BEST_MIN_PCT:
                    cand.append((sport, label, x))
    cand.sort(key=lambda c: (-round(c[2].u, 2), -(c[2].pct or 0)))
    return cand


def best_row(sport, label, x):
    """"[icon] NBA · 1Q Fav ML · 75% (3-1) · +2.05u", one line."""
    pct = f'{round(x.pct * 100)}% ({x.w}-{x.l})' if x.pct is not None else f'{x.w}-{x.l}'
    return (f'<li class="yb-row">{icons.sport_icon(sport.sp)}<span class="yb-sp">{esc(sport.label)}</span><span class="yb-dot">&middot;</span>'
            f'<span class="yb-mk">{esc(label)}</span><span class="yb-dot">&middot;</span><span class="yb-rec">{pct}</span>'
            f'<span class="yb-dot">&middot;</span><span class="yb-u">{fmt_units(x.u)}</span></li>')


def best_card(yday, inner, hero=False):
    """A normal card: the purple title bar ("YESTERDAY'S BEST · TUE, NOV 17"),
    then the rows."""
    return (f'<section class="fr-sec yb{" yb-hero" if hero else ""}" id="best"><div class="st-card yb-card">'
            f'<div class="st-head"><h4>Yesterday&rsquo;s Best &middot; {esc(day_label(yday))}</h4></div>{inner}</div></section>')


def yesterdays_best(S, yday, hero=False):
    """Up to 3 rows, the most units first, each +1.0u or better at 55%+, at
    most 2 from one sport; none: no card."""
    cand, per = [], {}
    for c in best_cands(S, yday):
        if per.get(c[0].key, 0) < BEST_PER_SPORT and len(cand) < 3:
            per[c[0].key] = per.get(c[0].key, 0) + 1
            cand.append(c)
    if not cand:
        return ''
    return best_card(yday, f'<ul class="yb-rows">{"".join(best_row(*c) for c in cand)}</ul>', hero)


def best_hero(S, yday, hub=False):
    """The hero when there's no Preview: the same rows (a hub: its sport's)."""
    return yesterdays_best(S, yday, hero=True)


HOME_H1 = 'Run to Your Bets: First Period, Quarter & Half Betting'


PRODUCT_LINE = ('Early bets settle fast. Run to yours with the numbers. '
                'First period, quarter and half odds, stats and trends for every game.')

HOME_LINES = (('period', 'fr-b1'), ('quarter', 'fr-b2'), ('half', 'fr-b1'))   # the brand colors: purple, yellow, purple


def slogan(S, hub=False):
    """The home page's H1: the three brand lines and the product line under
    them (HOME_H1 stays the page title); a hub's segments line (the hub's H1
    is its page head)."""
    if not hub:
        lines = ''.join(f'<span class="fr-line">The first <span class="{c}">{w}.</span></span>' for w, c in HOME_LINES)
        return f'<h1 class="fr-big">{lines}</h1><p class="fr-lede">{esc(PRODUCT_LINE)}</p>'
    sp = next(iter(S.values()))
    words = ['The ' + x['label'].replace('1st ', 'first ').lower() for x in sp.segments]
    return f'<p class="fr-slogan">{" &middot; ".join(words)}</p>'


# ------------------------------------------------------------ The Slate
def fav_of(mk):
    """The segment's favorite: by its spread line, else its moneyline."""
    a = ((mk.get('ats') or {}).get('away') or {}).get('line')
    if isinstance(a, (int, float)) and a != 0:
        return 'away' if a < 0 else 'home'
    ml = mk.get('ml') or {}
    if isinstance(ml.get('away'), (int, float)) and isinstance(ml.get('home'), (int, float)):
        return 'away' if implied(ml['away']) >= implied(ml['home']) else 'home'
    return None


def book_of(sport, og, k, m, side, price, line=None):
    """The source with the best price (the Odds page's green outline), for
    its logo on /odds/: sportsbooks first, then the exchanges."""
    import sport_build
    books = ((og.get('books') or {}).get(k) or {}).get(m) or {}
    for exch in (False, True):
        for b, row in books.items():
            if not books_cfg.settings().counts(b) or bool((sport.sources.get(b) or {}).get('x')) != exch:
                continue
            v = row.get(side) if isinstance(row, dict) else None
            if not isinstance(v, dict) or v.get('price') != price:
                continue
            ln = row.get('line') if m == 'total' else v.get('line')
            if line is not None and ln != line:
                continue
            return b
    return None


def book_html(sport, b, root):
    if not b:
        return ''
    s = sport.sources.get(b) or {}
    name = s.get('name') or b
    if s.get('logo'):
        return f'<img class="sl-book" src="{root}{esc(s["logo"])}" alt="{esc(name)}" title="{esc(name)}" loading="lazy">'
    return f'<span class="sl-bname">{esc(name)}</span>'


def cell(top, sub='', book=''):
    """One market cell: the line (or price) on top, the price under it on /odds/."""
    return (f'<span class="cell"><span class="ob-ln">{top}</span>'
            + (f'<span class="ob-pr">{sub}</span>' if sub else '') + (f'<span class="sl-src">{book}</span>' if book else '') + '</span>')


def dash():
    return '<span class="cell"><span class="mc-dash">-</span></span>'


def mk_h(text):
    """An odds table's segment or market label: the accent chip (template.html .mk-h)."""
    return f'<span class="mk-h">{esc(text)}</span>'


def spread_rows(sport, d, g, odds, root):
    """ATS · ML · O/U, one row per segment, the favorite only."""
    og = sport.odds_game(d, g) if odds else {}
    rows = ''
    for s in sport.segments:
        k = s['key']
        mk = sport.market(d, g, k)
        if not mk:
            continue
        f = fav_of(mk)
        ats, ml, tot = mk.get('ats') or {}, mk.get('ml') or {}, mk.get('total') or {}
        c_ats = c_ml = c_tot = dash()
        if f and (ats.get(f) or {}).get('line') is not None:
            a = ats[f]
            c_ats = cell(f"{esc(sport.code(g[f]))} {esc(signed(a['line']))}", price_txt(a.get('price')) if odds else '',
                         book_html(sport, book_of(sport, og, k, 'ats', f, a.get('price'), a['line']), root) if odds else '')
        if f and isinstance(ml.get(f), (int, float)):
            c_ml = cell(price_txt(ml[f]), '', book_html(sport, book_of(sport, og, k, 'ml', f, ml[f]), root) if odds and abs(ml[f]) <= ML_CAP else '')
        if tot.get('line') is not None:
            c_tot = cell(esc(line_txt(tot['line'])), ('o' + price_txt(tot.get('over'))) if odds and tot.get('over') is not None else '',
                         book_html(sport, book_of(sport, og, k, 'total', 'over', tot.get('over'), tot['line']), root) if odds else '')
        rows += f'<span class="sl-rh">{mk_h(s["tag"])}</span>{c_ats}{c_ml}{c_tot}'
    if not rows:
        return ''
    return (f'<div class="sl-mk"><span></span><span class="sl-ch">{mk_h("ATS")}</span><span class="sl-ch">{mk_h("ML")}</span>'
            f'<span class="sl-ch">{mk_h("O/U")}</span>{rows}</div>')


def baseball_rows(sport, d, g, odds, root):
    """NRFI/YRFI, then F5 in the spread table's style."""
    rfi = (sport.market(d, g, '1i').get('rfi') or sport.market(d, g, '1i').get('nrfi_yrfi')) or {}
    y, n = rfi.get('yes', rfi.get('yrfi')), rfi.get('no', rfi.get('nrfi'))
    top = ''
    if isinstance(y, (int, float)) and isinstance(n, (int, float)):
        side, p = ('NRFI', n) if implied(n) >= implied(y) else ('YRFI', y)
        top = f'<span class="sl-rh">{mk_h("1st inn")}</span><span class="sl-wide">{cell(f"{side} {price_txt(p)}")}</span>'
    f5 = spread_rows(sport, d, g, odds, root)
    if not top:
        return f5
    if not f5:
        return f'<div class="sl-mk">{top}</div>'
    o_u = f'<span class="sl-ch">{mk_h("O/U")}</span>'
    return f5.replace(o_u, o_u + top, 1)


def nhl_grid(sport, d, g, odds, root):
    """ML · O/U over BTTS · 3-WAY: the favorite (or favored side) and price."""
    og = sport.odds_game(d, g) if odds else {}
    mk = sport.market(d, g, '1p')
    if not mk:
        return ''
    ml, tot, btts, m3 = mk.get('ml') or {}, mk.get('total') or {}, mk.get('btts') or {}, mk.get('ml3') or {}

    def box(head, body):
        return f'<div class="sl-q"><span class="sl-qh">{mk_h(head)}</span>{body}</div>'

    def team_price(row, m):
        sides = [s for s in ('away', 'home') if isinstance(row.get(s), (int, float))]
        if not sides:
            return dash()
        s = min(sides, key=lambda x: (-implied(row[x]), x))
        return cell(f'{esc(sport.code(g[s]))} {price_txt(row[s])}', '',
                    book_html(sport, book_of(sport, og, '1p', m, s, row[s]), root) if odds and abs(row[s]) <= ML_CAP else '')
    c_tot = dash()
    if tot.get('line') is not None and isinstance(tot.get('over'), (int, float)):
        c_tot = cell(f"{esc(line_txt(tot['line']))} o{price_txt(tot['over'])}", '',
                     book_html(sport, book_of(sport, og, '1p', 'total', 'over', tot['over'], tot['line']), root) if odds else '')
    c_btts = dash()
    if isinstance(btts.get('yes'), (int, float)) or isinstance(btts.get('no'), (int, float)):
        opts = [(s, btts[s]) for s in ('yes', 'no') if isinstance(btts.get(s), (int, float))]
        s, p = min(opts, key=lambda x: -implied(x[1]))
        c_btts = cell(f"{'Yes' if s == 'yes' else 'No'} {price_txt(p)}", '', book_html(sport, book_of(sport, og, '1p', 'btts', s, p), root) if odds else '')
    return ('<div class="sl-grid">' + box('ML', team_price(ml, 'ml')) + box('O/U', c_tot) +
            box('BTTS', c_btts) + box('3-WAY', team_price(m3, 'ml3')) + '</div>')


def markets_html(sport, d, g, odds=False, root=''):
    if sport.key == 'nhl':
        return nhl_grid(sport, d, g, odds, root)
    if sport.doc.get('sportType') == 'baseball':
        return baseball_rows(sport, d, g, odds, root)
    return spread_rows(sport, d, g, odds, root)


def when_txt(sport, d, g, today, now, full=False):
    """The title bar: the start time, with the day when it isn't today
    (football always: "THU 8:15 PM ET"); LIVE or FINAL once it starts.
    full (the index pages): "LIVE · 4th · TOR 83-80", "FINAL · 1Q TOR 29-23"."""
    if g.get('state') == 'final':
        return 'FINAL' + (f' · {final_seg(sport, g)}' if full and final_seg(sport, g) else '')
    if started(g, now):
        if not full:
            return 'LIVE'
        detail = str(g.get('detail') or '')
        period = detail.split(' - ')[-1].strip() if detail else ''
        lead = lead_txt(sport, g, g.get('as'), g.get('hs'))
        return ' · '.join(x for x in ('LIVE', period, lead) if x)
    t = parse(g.get('start'))
    if not t:
        return 'TBD'
    t = t.astimezone(ET)
    day = t.strftime('%a ').upper() if sport.weekly or t.date().isoformat() != today else ''
    return day + t.strftime('%-I:%M %p ET')


def lead_txt(sport, g, a, h):
    """'TOR 83-80': the leader first; level: '1-1'."""
    if a is None or h is None:
        return ''
    if a == h:
        return f'{a}-{h}'
    return f'{sport.code(g["away"])} {a}-{h}' if a > h else f'{sport.code(g["home"])} {h}-{a}'


def final_seg(sport, g):
    """'1Q TOR 29-23': the opening segment's score (the first one graded)."""
    for k in sport.seg_keys():
        sc = (((g.get('res') or {}).get(k)) or {}).get('sc')
        if sc and len(sc) == 2:
            return f'{seg_tag(sport, k)} {lead_txt(sport, g, sc[0], sc[1])}'
    return ''


def round_txt(g):
    """Postseason: the round from the schedule's note ("Second Round · Game 3");
    NHL's schedule has no notes."""
    note = str(g.get('note') or '') if g.get('post') else ''
    return ' &middot; '.join(esc(x.strip()) for x in note.split(' - ') if x.strip() and 'If Necessary' not in x) if note else ''


def slate_card(sport, d, g, today, now, root, odds=False, show_sport=True, full=False):
    def side(slug, sc):
        return (f'<span class="sl-tm">{sport.badge(slug, 22, root)}<span class="sl-code">{esc(sport.code(slug))}</span>'
                + (f'<span class="sl-sc">{esc(sc)}</span>' if sc is not None else '') + '</span>')
    live_or_done = g.get('state') in ('in', 'final')
    a_sc, h_sc = (g.get('as'), g.get('hs')) if live_or_done else (None, None)
    href = f"{root}{sport.odds_page if odds else sport.matchups}" + (f"?week={g['wk']}" if sport.weekly and g.get('wk') else f'?date={d}')
    sp_lbl = f'<span class="sl-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span>' if show_sport else ''
    return (f'<a class="st-card sl-card" href="{esc(href)}" data-sport="{sport.key}" data-day="{d}" data-start="{esc(g.get("start") or "")}"'
            f' data-state="{esc(g.get("state") or "pre")}"{" data-weekly" if sport.weekly else ""}>'
            f'<div class="st-head"><h4><span class="sl-when">{esc(when_txt(sport, d, g, today, now, full))}</span>{sp_lbl}</h4></div>'
            + (f'<p class="sl-round">{round_txt(g)}</p>' if round_txt(g) else '') +
            f'<div class="sl-teams">{side(g["away"], a_sc)}<span class="sl-at">@</span>{side(g["home"], h_sc)}</div>'
            f'{markets_html(sport, d, g, odds, root)}</a>')


def week_key(sport, today):
    """Football: the week with games still to play (the hub's rule)."""
    import hub
    w = hub.current_week(sport.doc)
    return w['key'] if w else None


def upcoming(sport, today, now):
    """[(date, game)] still to start, in start order: today's, then the next
    game day's (football: the rest of this week)."""
    out = []
    if sport.weekly:
        # the week's next games; once its last one starts, next week's
        out = [(d, g) for d, g in sport.all_games() if d >= today]
    else:
        days = sorted(d for d in (sport.doc.get('games') or {}) if d >= today)
        for d in days:
            day = [(d, g) for g in sport.games(d)]
            if d == today:
                out += day
                continue
            if any(game_lined(sport, g) and not started(g, now) for _, g in day):
                out += day
                break
    out = [(d, g) for d, g in out if game_lined(sport, g) and not started(g, now)]
    return sorted(out, key=lambda x: (x[1].get('start') or '', x[1]['away']))


def pills(name, opts, cur='all'):
    """A pill row (scrolls sideways on phones): [(value, label)], or
    [(value, label, icon html)] for a sport's league icon before its name."""
    return (f'<div class="fr-pills" role="group" aria-label="{esc(name)}" data-pills="{esc(name)}">' + ''.join(
        f'<button class="seg-btn" type="button" data-pick="{esc(o[0])}" aria-pressed="{str(o[0] == cur).lower()}">{o[2] if len(o) > 2 else ""}{esc(o[1])}</button>'
        for o in opts) + '</div>')


def more_link(href, text, attrs=''):
    return f'<a class="fr-more" href="{esc(href)}"{attrs}>{text} &rarr;</a>'


def slate(S, now_utc, root='', hub=False):
    now = now_utc
    today = now.astimezone(ET).date().isoformat()
    cards, links, opts, ends = [], '', [('all', 'All')] if not hub else [], {}
    for sport in S.values():
        opts.append((sport.key, sport.label, icons.sport_icon(sport.sp)))
        # today's last start: once it passes, the tab shows the next game day
        starts = [g['start'] for g in sport.games(today) if game_lined(sport, g) and g.get('start')]
        if starts:
            ends[sport.key] = max(starts)
        for d, g in upcoming(sport, today, now)[:SLATE_BUFFER]:
            cards.append((g.get('start') or '', d, sport, g))
        links += more_link(f'{root}{sport.matchups}', f'{esc(sport.label)} Matchups', f' data-tab="{sport.key}"')
    if not hub:
        links = more_link(f'{root}matchups/', 'All matchups', ' data-tab="all"') + links
    cards.sort(key=lambda x: (x[0], x[2].label))
    body = ''.join(slate_card(sport, d, g, today, now, root) for _, d, sport, g in cards)
    head = (f'<div class="sl-headline"><div class="sl-title"><h2>The Slate</h2>'
            f'<span class="sl-next" data-next hidden><i class="sl-dot" aria-hidden="true"></i><span data-next-text></span></span></div>'
            f'<span class="sl-date">{esc(day_label(today))}</span></div>'
            + ('' if hub else pills('Sport', opts)))
    empty = '<p class="fr-empty" data-empty hidden>No more games on the board today.</p>'
    # every game today started: the next game day's cards under this line
    # (no lines posted yet: the line alone, worded for that)
    live = more_link(f'{root}{sport.matchups}' if hub and S else f'{root}matchups/', 'Matchups')
    over = (f'<p class="sl-over" data-over hidden><span data-over-text>Tonight&rsquo;s games are underway.</span> Follow them live on {live}</p>')
    tab = next(iter(S)) if hub and S else 'all'
    return (f'<section class="fr-sec sl" id="slate" data-slate data-tab="{tab}" data-today="{today}" data-shown="{SLATE_SHOWN}"'
            f" data-ends='{esc(json.dumps(ends))}'>{head}{over}"
            f'<div class="sl-cards">{body}</div>{empty}<div class="fr-links">{links}</div></section>')


# -------------------------------------------------------- Hottest Trends
def slate_key(sport, today):
    return week_key(sport, today) if sport.weekly else today


def trend_row(sport, c, x, g, root, now, last=''):
    """One game row; last: the trend's "Last time" line, under the row
    (desktop: on hover or a click; phones: a tap opens it, ▾)."""
    st = 'FINAL' if g.get('state') == 'final' else 'LIVE' if started(g, now) else ''
    when = st or time_et(g.get('start'))
    t = parse(g.get('start'))
    if not st and t and (sport.weekly or t.astimezone(ET).date() != now.astimezone(ET).date()):
        when = t.astimezone(ET).strftime('%a %-I:%M %p')   # not today: the day first ("Sat 1:00 PM")
    # the logo loads right away (a lazy one could stay blank as rows move up)
    logo = sport.badge(g[x['side']], 16, root).replace(' loading="lazy"', '') if x.get('side') else ''
    bet = (f'Bet {sport.link(g[x["side"]], logo + " " + esc(sport.code(g[x["side"]])), root)}' if x.get('side') else esc(x.get('label')))
    opens = ' tabindex="0" aria-expanded="false"' if last else ''
    caret = '<i class="tr-caret" aria-hidden="true">&#9662;</i>' if last else ''
    return (f'<div class="tr-row fr-trow{" tr-has-last" if last else ""}" data-start="{esc(g.get("start") or "")}" data-state="{esc(g.get("state") or "pre")}"'
            f'{opens}>'
            f'<span class="tr-time">{esc(when)}</span><span class="tr-match">{sport.link(g["away"], esc(sport.code(g["away"])), root)} @ '
            f'{sport.link(g["home"], esc(sport.code(g["home"])), root)}</span>'
            f'<span class="tr-bet">{bet}</span>{caret}</div>'
            + (f'<p class="tr-last">{esc(last)}</p>' if last else ''))


def today_game(g, today, now):
    """Starts today (ET) or is live now."""
    t = parse(g.get('start')) if g.get('start') else None
    live = g.get('state') != 'final' and started(g, now)
    return live or bool(t) and t.astimezone(ET).date().isoformat() == today


# "Fade X" makes the same bets as "Back the opposite of X"
OPPOSITE = {'tier1': 'tier4', 'tier2': 'tier3', 'home_fav': 'road_dog', 'road_fav': 'home_dog', 'rested': 'tired'}
OPPOSITE.update({v: k for k, v in list(OPPOSITE.items())})


def mirror_key(sport, c):
    """Cards with the same key are mirrors: Fade X and Back the opposite of X."""
    a = c.get('angle')
    if c.get('dir') == 'Fade' and a in OPPOSITE:
        return (sport.key, c['seg'], c['mk'], 'Back', OPPOSITE[a])
    return (sport.key, c['seg'], c['mk'], c.get('dir'), a)


def bet_key(sport, c, x):
    """The bet a trend row makes: the same key means the same bet."""
    return (sport.key, str(x['id']), c['seg'], c['mk'], x.get('side') or x.get('bet'))


def today_rows(sport, c, by_id, today, now, left=False):
    """The card's rows for today's games that have a line. left: only games
    still to start (football: the week's)."""
    def fits(g):
        if left:
            return not started(g, now) and (sport.weekly or (parse(g.get('start')) and parse(g['start']).astimezone(ET).date().isoformat() == today))
        return today_game(g, today, now)
    return [x for x in c.get('games') or [] if str(x['id']) in by_id
            and fits(by_id[str(x['id'])]) and game_lined(sport, by_id[str(x['id'])], c['seg'])]


def trend_card(sport, c, by_id, root, now, show_sport, hidden=False, xs=None):
    if xs is None:
        xs = [x for x in c.get('games') or [] if str(x['id']) in by_id and game_lined(sport, by_id[str(x['id'])], c['seg'])]
    # up to TREND_ROWS rows, games still to play first (football weeks run long)
    xs = sorted(xs, key=lambda x: by_id[str(x['id'])].get('state') == 'final')[:TREND_ROWS]
    rows = ''.join(trend_row(sport, c, x, by_id[str(x['id'])], root, now) for x in xs)
    if not rows:
        return ''   # a card with no rows to show is hidden
    sp = f'<span class="fr-tsport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span>' if show_sport else ''
    rate, base = c['rate'] * 100, c['base'] * 100
    return (f'<div class="tr-card"{" hidden data-more" if hidden else ""}><div class="tr-top">{sp}<span class="lt-tag">{esc(c["tag"].replace(" ATS", " Spread"))}</span></div>'
            f'<h3 class="tr-title">{esc(c["title"])}</h3>'
            f'<div class="tr-rec" title="{esc(RECORD_TIP)}">{round(rate)}% ({c["w"]}-{c["l"]}) &middot; league {round(base)}% &middot; '
            f'<span class="{unit_tone(c["units"])}">{fmt_units(c["units"])}</span></div>'
            f'<div class="tr-bar" aria-hidden="true"><span style="width:{rate:.1f}%"></span><i style="left:{base:.1f}%"></i></div>'
            f'<div class="tr-rows">{rows}</div></div>')


def hot_cards(S, now_utc, bar=True, day=None, left=False):
    """[(sport, card, by_id, rows)] in order: cards with a game today (ET)
    or live now, rows for today's games only; no 3-way ML; a 55%+ win rate
    (TREND_MIN_RATE); ranked by season
    units. bar: Hottest Trends' bar too (20+ games, 5+ points over the
    league rate). A mirror (Fade X / Back the other side: the same bets)
    keeps the one with more units, and a card whose rows are all bets
    already shown above it is skipped. The first 3 never repeat a sport +
    market; the next card moves up. day: that day's cards instead of
    today's (football: none; its week counts today). left: rows only for
    games still to start."""
    today = day or now_utc.astimezone(ET).date().isoformat()
    found = []
    for sport in S.values():
        if day and sport.weekly:
            continue
        key = slate_key(sport, today)
        cards = (((sport.trends.get('slates') or {}).get(key) or {}).get('cards')) or []
        by_id = {str(g['id']): g for _, g in sport.all_games()}
        for c in cards:
            if c.get('mk') == 'ml3' or (c.get('units') or 0) <= 0 or (c.get('rate') or 0) < TREND_MIN_RATE - 1e-9:
                continue
            if bar and ((c.get('n') or 0) < TREND_MIN_N or (c.get('rate') or 0) - (c.get('base') or 0) < TREND_MIN_EDGE - 1e-9):
                continue
            xs = today_rows(sport, c, by_id, today, now_utc, left)
            if xs:
                found.append((sport, c, by_id, xs))
    found.sort(key=lambda f: (-f[1]['units'], -(f[1]['rate'] - f[1]['base']), f[1]['id']))
    kept, shown, mirrors = [], set(), set()
    for f in found:
        bets = {bet_key(f[0], f[1], x) for x in f[3]}
        m = mirror_key(f[0], f[1])
        if m in mirrors or bets <= shown:
            continue   # its mirror, or cards above it, already show these bets
        shown |= bets
        mirrors.add(m)
        kept.append(f)
    top, rest = [], []
    for f in kept:
        mk = (f[0].key, f[1]['seg'], f[1]['mk'])
        if len(top) < HOT_SHOWN and mk not in {(t[0].key, t[1]['seg'], t[1]['mk']) for t in top}:
            top.append(f)
        else:
            rest.append(f)
    return top + rest


def tip_body(title, definition, compare=''):
    """The "i" box's contents (template.html #tipBox): the title, a short
    definition and, on trends only, the comparison line. Nothing else."""
    return (f'<span class="tip-t">{esc(title)}</span>' + (f'<span class="tip-d">{esc(definition)}</span>' if definition else '')
            + (f'<span class="tip-c">{esc(compare)}</span>' if compare else ''))


TERM_OF = {'ml': 'moneyline', 'ml3': '3-way-moneyline', 'total': 'total', 'btts': 'btts', 'rfi': 'nrfi'}


def info_tip(label, body, term=''):
    """term: the market's glossary anchor (data-term); the box has no link out (Nov 20)."""
    t = f' data-term="{esc(term)}"' if term else ''
    return f'<button type="button" class="info-tip" aria-label="About {esc(label)}"{t}>i<span class="tip-bubble" role="tooltip">{body}</span></button>'


def trend_compare(c):
    """"This trend: 62% (57-35). League average: 50%." """
    return f'This trend: {round(c["rate"] * 100)}% ({c["w"]}-{c["l"]}). League average: {round(c["base"] * 100)}%.'


def trend_tip(sport, c):
    """The "i" circle, the same as the Trends page's."""
    term = ('run-line' if sport and sport.key == 'mlb' else 'spread') if c.get('mk') == 'ats' else TERM_OF.get(c.get('mk'), '')
    return info_tip(c['title'], tip_body(c['title'], c.get('meaning') or '', trend_compare(c)), term)


def last_line(sport, c):
    """The trend's "Last time" line under its rows, only when the trend's
    show_last switch is on (content/definitions.json, off by default)."""
    on = ((sport.trends.get('tips') or {}).get('show_last')) or []
    return (c.get('last') or '') if c.get('angle') in on else ''


def hot_card(sport, c, by_id, xs, root, now, show_sport=True, n_rows=HOT_ROWS, attrs='', last_recs=None):
    """A Hottest Trends card: the market in the purple bar ("NBA · 1H ML")
    with the "i" on the right, the title, the record and units, then up to
    3 game rows (games still to play first; n_rows: more in the HTML, for
    the script to move up as games start). last_recs (early season): each
    trend's record last season, behind the "Last season" toggle."""
    xs = sorted(xs, key=lambda x: (by_id[str(x['id'])].get('state') == 'final', by_id[str(x['id'])].get('start') or ''))[:n_rows]
    last = last_line(sport, c)
    rows = ''.join(trend_row(sport, c, x, by_id[str(x['id'])], root, now, last).replace('<div ', '<div hidden ', 1) if i >= HOT_ROWS else
                   trend_row(sport, c, x, by_id[str(x['id'])], root, now, last) for i, x in enumerate(xs))
    if not rows:
        return ''
    tag = esc(c['tag'].replace(' ATS', ' Spread'))
    rate, base = c['rate'] * 100, c['base'] * 100
    this_attr = ' data-season="this"' if last_recs is not None else ''
    return (f'<div class="st-card tr-card ht-card"{attrs}><div class="st-head"><h4><span class="sl-sport">{icons.sport_icon(sport.sp) + esc(sport.label) + " &middot; " if show_sport else ""}{tag}</span>{trend_tip(sport, c)}</h4></div>'
            f'<h3 class="tr-title">{esc(c["title"])}</h3>'
            f'<p class="ht-rec"{this_attr}>{round(rate)}% ({c["w"]}-{c["l"]}) &middot; <span class="{unit_tone(c["units"])}">{fmt_units(c["units"])}</span></p>'
            + (last_rec_html(last_recs.get(c['id'])) if last_recs is not None else '') +
            f'<p class="ht-avg">League average {round(base)}%</p>'
            f'<div class="tr-rows">{rows}</div></div>')


def last_rec_html(r):
    """The card's record last season (the early-season toggle)."""
    if not r or not r['w'] + r['l']:
        return '<p class="ht-rec" data-season="last" hidden>Not tracked last season</p>'
    u = (f' &middot; <span class="{unit_tone(r["units"])}">{fmt_units(r["units"])}</span>' if r['all_priced'] else '')
    pct = round(100 * r['w'] / (r['w'] + r['l']))
    return f'<p class="ht-rec" data-season="last" hidden>{pct}% ({r["w"]}-{r["l"]}){u}</p>'


HOT_BUFFER = 12   # Hottest Trends: cards per day in the HTML, so the next one can move up


def next_trend_day(S, now_utc):
    """The next game day (after today) with a qualifying trend, or None."""
    today = now_utc.astimezone(ET).date().isoformat()
    days = sorted({d for sp in S.values() if not sp.weekly for d in ((sp.trends.get('slates') or {})) if '-' in d and len(d) == 10 and d > today})
    return next((d for d in days if hot_cards(S, now_utc, day=d, left=True)), None)


def hottest_trends(S, now_utc, root='', hub=False, early=False):
    """Exactly 3 trend cards, each with a game still to start (hot_cards,
    left=True), rows only for those games. As a trend's last game starts it
    drops off and the next one moves up (FRONT_JS); when today has none left,
    the next game day's top 3, dated that day (football: "This week"). No
    trend at all: no section. More trends: /trends/ (a hub: its Trends page).
    early (a hub in its first 21 days): a This season / Last season toggle."""
    today = now_utc.astimezone(ET).date().isoformat()
    nxt = next_trend_day(S, now_utc)
    last_recs = None
    if early and hub and S:
        import offseason
        last_recs = offseason.last_season_records(next(iter(S.values())))
    cards, shown = '', []
    for i, day in enumerate((today, nxt)):
        found = hot_cards(S, now_utc, day=None if day == today else day, left=True)[:HOT_BUFFER] if day else []
        today_cards = cards if i == 1 else ''
        for sp, c, b, xs in found:
            label = 'This week' if sp.weekly else day_label(day)
            show = len(shown) < HOT_SHOWN and (i == 0 or not today_cards)
            attrs = f' data-group="{i}" data-label="{esc(label)}"' + ('' if show else ' hidden')
            html = hot_card(sp, c, b, xs, root, now_utc, not hub, n_rows=TREND_ROWS * 2, attrs=attrs, last_recs=last_recs)
            if html and show:
                shown.append(label)
            cards += html
    if not cards:
        return ''
    date = next((x for x in shown if x != 'This week'), 'This week')   # the shown cards' day; football only: "This week"
    href = root + (next(iter(S.values())).trends_page if hub and S else 'trends/')
    toggle = pills('Season', [('this', 'This season'), ('last', 'Last season')], 'this').replace('data-pills=', 'data-season-pills data-pills=', 1) if last_recs is not None else ''
    return (f'<section class="fr-sec" id="trends" data-hot data-shown="{HOT_SHOWN}" data-rows="{HOT_ROWS}">'
            f'<div class="fr-head fr-stack"><h2>Hottest Trends</h2><span class="fr-date" data-hot-date>{esc(date)}</span></div>{toggle}'
            f'<div class="tr-cards ht-cards">{cards}</div><div class="fr-links">{more_link(href, "More trends")}</div></section>')


# ---------------------------------------------------- Matchup of the Day
def motd_pick(S, now_utc, hub=False):
    """(sport, pick, game) from each sport's hub.json (scripts/hub.py's
    rules). Home: tonight's game, any sport, with the most trends, ties to
    the stronger Trend to Watch %, then the earlier start (hub.rank_key)."""
    today = now_utc.astimezone(ET).date().isoformat()
    best = None
    for sport in S.values():
        m = sport.hub.get('motd')
        if not m:
            continue
        g = next((x for _, x in sport.all_games() if str(x['id']) == str(m['id'])), None) or m
        if not hub and (not today_game(g, today, now_utc) or g.get('state') == 'final'):
            continue
        score = hub_rank(m)
        if best is None or score < best[0]:
            best = (score, sport, m, g)
    return best[1:] if best else None


def hub_rank(m):
    import hub
    return hub.rank_key(m)


def motd_watch(sport, m):
    """TREND TO WATCH: the market, large ("1H UNDER"; a side: "SUNS 1H ML",
    desktop the nickname, college the school, phones the code)."""
    tag = seg_tag(sport, m['seg'])
    if m.get('pick') in ('away', 'home'):
        what = {'ml': 'ML', 'ats': 'Spread', 'ml3': '3-Way ML'}.get(m['mk'], m['mk'].upper())
        return f'{sport.name_html(m[m["pick"]])} {esc(tag)} {what}'
    if m['mk'] == 'total':
        what = f"{tag} {'Over' if m['pick'] == 'over' else 'Under'}" + (' 1.5' if sport.key == 'nhl' else '')
    elif m['mk'] == 'btts':
        what = f"{tag} BTTS {'Yes' if m['pick'] == 'yes' else 'No'}"
    else:
        what = 'YRFI' if m['pick'] == 'yes' else 'NRFI'
    return esc(what)


def seg_words(sport, k):
    """"1st period", "first five" (the words {segment} becomes)."""
    lab = next((s['label'] for s in sport.segments if s['key'] == k), 'opening segment')
    return lab.lower().replace('first five innings', 'first five').replace('first 5 innings', 'first five')


def label_text(x, seg, btts=False):
    """A matchup label's definition: {segment}s reads "1st periods" (the
    first five stays "first five"), BTTS labels their own wording."""
    t = (x.get('tooltip_btts') if btts else None) or x.get('tooltip') or ''
    return t.replace('{segment}s', seg if seg == 'first five' else seg + 's').replace('{segment}', seg)


def label_chip(label, definition, cls='mo-chip'):
    """The label chip with its own "i" next to it."""
    return (f'<span class="lbl-chip"><span class="{cls}">{esc(label)}</span>'
            + info_tip(label, tip_body(label, definition)) + '</span>')


def motd_chip(sport, m):
    """The matchup label with its "i" (content/definitions.json
    matchup_labels, the same words as the Matchups page)."""
    if not m.get('label'):
        return ''
    labels = definitions.tooltips().get('matchup_labels') or {}
    x = next((v for v in labels.values() if isinstance(v, dict) and v.get('label') == m['label']), None)
    if not x:
        return f'<span class="mo-chip">{esc(m["label"])}</span>'
    return label_chip(m['label'], label_text(x, seg_words(sport, m['seg']), m.get('label_mk') == 'btts'))


def motd_odds(sport, m, root):
    """BEST ODDS: the book's logo tile and the Odds page's cell, the same
    size side by side, green outline (the best price)."""
    p = m.get('price') or {}
    if p.get('price') is None:
        return ''
    top, sub = price_txt(p['price']), ''
    if m.get('mk') == 'total' and p.get('line') is not None:
        top, sub = ('u' if m.get('pick') == 'under' else 'o') + line_txt(p['line']), price_txt(p['price'])
    elif m.get('mk') == 'ats' and p.get('line') is not None:
        top, sub = signed(p['line']), price_txt(p['price'])
    book = next((b for b, x in sport.sources.items() if (x or {}).get('name') == p.get('book')), None)
    logo = book_html(sport, book, root) if book else f'<span class="sl-bname">{esc(p.get("book"))}</span>'
    return (f'<div class="mo-best"><span class="mo-best-l">Best odds</span>'
            f'<span class="mo-best-row"><span class="mo-best-b">{logo}</span><span class="mo-best-c">{cell(esc(top), esc(sub))}</span></span></div>')


MOTD_ROWS = 6   # trend rows at most (scripts/hub.py fills to 4)


def motd(S, now_utc, root='', hub=False):
    """Desktop: two columns in the card. Left: the teams (large logos, full
    names), the Slate's odds table and the venue / TV line. Right: the
    matchup label (its "i"), TREND TO WATCH and the market, the best odds
    and 4-6 agreeing trends, one line each ("NY · 1H Under · 79% (11-3)").
    Phones: one column in that order, no venue line."""
    pick = motd_pick(S, now_utc, hub)
    if not hub:
        import hub as hub_mod
        print(hub_mod.log_line(pick[0].sp, pick[1], home=True) if pick else 'Matchup of the Day (home): no game qualifies')
    if not pick:
        return ''
    sport, m, g = pick
    today = now_utc.astimezone(ET).date().isoformat()
    day = m.get('date') or today
    big = 64

    def team(slug):
        return (f'<span class="mo-team">{sport.link(slug, sport.badge(slug, big, root), root, "mo-logo")}'
                f'{sport.link(slug, esc(sport.full_name(slug)), root, "mo-name")}</span>')
    trends = ''.join(f'<li><span class="mo-tl">{esc(t.get("short") or t["text"])}</span><span class="mo-tr">{esc(t["rec"])}</span></li>'
                     for t in (m.get('trends') or [])[:MOTD_ROWS])
    season = ((sport.hub.get('motdRecord') or {}).get('season')) or [0, 0]
    rec = f'<p class="mo-rec">Season: <span class="mono">{season[0]}-{season[1]}</span></p>' if season[0] > season[1] else ''
    title = 'Matchup of the Week' if hub and sport.weekly else 'Matchup of the Day'
    import preview
    chip = motd_chip(sport, m)
    odds = markets_html(sport, day, g, False, root) if g is not m else ''
    venue = preview.venue_line(sport, g) if g is not m else ''
    odds += f'<p class="mo-venue">{venue}</p>' if venue else ''
    return (f'<section class="fr-sec mo" id="motd"><div class="fr-head"><h2>{title}</h2></div>'
            f'<div class="st-card mo-card"><div class="st-head"><h4><span>{esc(when_txt(sport, day, g, today, now_utc))}</span>'
            f'<span class="sl-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span></h4></div>'
            + (f'<p class="sl-round">{round_txt(g)}</p>' if g is not m and round_txt(g) else '') +
            f'<div class="mo-cols"><div class="mo-left"><div class="mo-teams">{team(m["away"])}<span class="mo-at">@</span>{team(m["home"])}</div>'
            f'{odds}</div>'
            f'<div class="mo-right">{chip}<p class="mo-watch-l">Trend to watch</p><p class="mo-watch">{motd_watch(sport, m)}</p>{motd_odds(sport, m, root)}'
            f'<ul class="mo-list">{trends}</ul>{rec}</div></div></div></section>')


# ------------------------------------------------------- Streak to Watch
STREAK_ORDER = {'ml': 0, 'ats': 1, 'total': 2, 'btts': 3, 'rfi': 4}   # ties: a win/loss run first


def streak_line(sport, m, st, k):
    """The market first, then the run: "1H Under · 7 straight"."""
    tag = seg_tag(sport, k)
    w = {'ml': f"{tag} ML {'wins' if st['kind'] == 'W' else 'losses'}",
         'ats': f"{tag} Spread {'covers' if st['kind'] == 'W' else 'losses'}",
         'total': f"{tag} {'Over' if st['kind'] == 'O' else 'Under'}" + (' 1.5' if sport.key == 'nhl' else ''),
         'btts': f"{tag} BTTS {'Yes' if st['kind'] == 'Y' else 'No'}",
         'rfi': 'YRFI' if st['kind'] == 'Y' else 'NRFI'}[m]
    return f"{w} · {st['n']} straight"


def preview_lead_teams(key, now_utc):
    """The teams of today's published Preview's lead game (key: 'all' or a
    sport), so Streak to Watch doesn't repeat it."""
    import preview
    if not sports.PREVIEW_LIVE:
        return set()
    p = preview.todays(key, now_utc)
    lead = ((read_json(preview.LEADS, {}) or {}).get(p['date']) or {}).get(key) if p else None
    return {(lead['sport'], lead['away']), (lead['sport'], lead['home'])} if lead else set()


STREAK_MIN = 5          # Streaks to Watch: a run this long (football: STREAK_MIN_WEEKLY)
STREAK_MIN_WEEKLY = 4
STREAK_ROWS = 10        # rows under the top streak (desktop; FRONT_JS trims them to the
STREAK_PHONE = 5        # Matchup of the Day card's height), and on phones


def streak_day(sport, now_utc, hub=False):
    """[(date, game)] the block covers, not started: the displayed day
    (today's games, else the next game day's); a football hub: the week's."""
    today = now_utc.astimezone(ET).date().isoformat()
    games = upcoming(sport, today, now_utc)
    if hub and sport.weekly:
        wk = week_key(sport, today)
        return [(d, g) for d, g in games if g.get('wk') == wk] if wk else []
    return [(d, g) for d, g in games if d == games[0][0]] if games else []


def streak_next_day(sport, now_utc, hub=False):
    """[(date, game)] of the game day after the block's (football hub: next
    week): what Streaks to Watch shows once every game on it has started."""
    cur = streak_day(sport, now_utc, hub)
    if hub and sport.weekly:
        weeks = [w['key'] for w in sport.doc.get('weeks') or []]
        wk = cur[0][1].get('wk') if cur else week_key(sport, now_utc.astimezone(ET).date().isoformat())
        nxt = weeks[weeks.index(wk) + 1] if wk in weeks and weeks.index(wk) + 1 < len(weeks) else None
        return [(d, g) for d, g in sport.all_games() if nxt and g.get('wk') == nxt and not started(g, now_utc)]
    after = cur[0][0] if cur else now_utc.astimezone(ET).date().isoformat()
    for d in sorted(x for x in (sport.doc.get('games') or {}) if x > after):
        day = [(d, g) for g in sport.games(d) if game_lined(sport, g) and not started(g, now_utc)]
        if day:
            return day
    return []


def streaks(S, now_utc, hub=False, nxt=False):
    """[{sport, game, day, side, m, k, st, rate}]: every team on the
    displayed day with a current run of STREAK_MIN+ (football 4+), its
    longest only; longest first, then the earlier start, then the higher
    season rate in that market (home: today's games first, then each later
    day's, each longest first). Never a team from the lead game of today's
    published Preview at the top (the next one moves up). nxt: the next
    game day's instead (every sport's games on the earliest such day)."""
    import hub as H
    skip = preview_lead_teams(next(iter(S)) if hub and S else 'all', now_utc)
    out = []
    pick = {k: [(d, g) for d, g in (streak_next_day if nxt else streak_day)(sp, now_utc, hub) if game_lined(sp, g)] for k, sp in S.items()}
    if nxt and not (hub and next(iter(S.values())).weekly):
        first = min((gs[0][0] for gs in pick.values() if gs), default=None)
        pick = {k: [(d, g) for d, g in gs if d == first] for k, gs in pick.items()}
    for key, sport in S.items():
        games = pick[key]
        if not games:
            continue
        need = STREAK_MIN_WEEKLY if sport.weekly else STREAK_MIN
        before = min(d for d, _ in games)
        seqs = {k: H.team_seqs(sport.doc, before, k) for k in {x[0] for x in H.market_keys(sport.doc)}}
        for d, g in games:
            for side in ('away', 'home'):
                best = None
                for k, m in H.market_keys(sport.doc):
                    seq = ((seqs[k].get(g[side]) or {}).get(m)) or []
                    st = H.streak_of(seq)
                    if not st or st['n'] < need:
                        continue
                    dec = [x for x in seq if x in (H.HIT[m], H.MISS[m])] if m != 'ml' else seq
                    rate = sum(1 for x in dec if x == st['kind']) / len(dec) if dec else 0
                    score = (st['n'], -STREAK_ORDER.get(m, 9))
                    if best is None or score > best[0]:
                        best = (score, {'sport': sport, 'game': g, 'day': d, 'side': side, 'm': m, 'k': k, 'st': st, 'rate': rate})
                if best:
                    out.append(best[1])
    if hub:
        out.sort(key=lambda x: (-x['st']['n'], x['game'].get('start') or '', -x['rate']))
    else:   # home: tonight's games first (longest, then the earlier start), then the next game day's
        out.sort(key=lambda x: (x['day'], -x['st']['n'], x['game'].get('start') or '', -x['rate']))
    for x in out:
        x['lead'] = (x['sport'].key, x['game'][x['side']]) in skip
    top = next((x for x in out if not x['lead']), None)
    if top:
        out.remove(top)
        out.insert(0, top)
    return out


def next_txt(sport, x, now_utc, short=False):
    """"vs Portland Trail Blazers · 8:00 PM ET" ("@" on the road; another
    day: "Sun 1:00 PM ET"); short: the opponent's code."""
    g, side = x['game'], x['side']
    opp = g['home' if side == 'away' else 'away']
    when = parse(g.get('start'))
    t = ''
    if when:
        when = when.astimezone(ET)
        t = (when.strftime('%a ') if when.date().isoformat() != now_utc.astimezone(ET).date().isoformat() else '') + when.strftime('%-I:%M %p') + ' ET'
    name = sport.code(opp) if short else sport.full_name(opp)
    return f"{'@' if side == 'away' else 'vs'} {esc(name)}" + (f' &middot; {t}' if t else '')


def heat_cls(n):
    """Streak heat (CLAUDE.md --heat-1..4): 3-4, 5-6, 7-8, 9+."""
    return 'heat heat-' + str(4 if n >= 9 else 3 if n >= 7 else 2 if n >= 5 else 1)


def streak_item(x, i, now_utc, root, hub, phone_more):
    """One streak: the big block (the top one) and its one-line row; FRONT_JS
    picks which shows as games start."""
    sport, g, side = x['sport'], x['game'], x['side']
    slug, opp = g[side], g['home' if side == 'away' else 'away']
    line = esc(streak_line(sport, x['m'], x['st'], x['k']))
    sp_tag = '' if hub else f'<span class="sl-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span>'
    head = f'<div class="st-head"><h4>{sp_tag}</h4></div>' if sp_tag else ''
    big = (f'<div class="sw-big">{head}'
           f'<div class="tw-main">{sport.link(slug, sport.badge(slug, 84, root), root, "tw-logo")}<div class="tw-copy">'
           f'{sport.link(slug, esc(sport.full_name(slug)), root, "tw-name")}<p class="tw-line">{line}</p></div></div>'
           f'<div class="tw-next"><p class="tw-next-l">Next matchup</p><p class="tw-next-g">{sport.link(opp, sport.badge(opp, 24, root), root, "tw-opp")}'
           f'<span>{next_txt(sport, x, now_utc)}</span></p></div></div>')
    # two lines: the heat chip · icon (home) · logo · code · the full streak, then opponent + time;
    # the first row under the top block carries the MORE STREAKS TO WATCH divider
    row = (f'<p class="sw-div">More streaks to watch</p>'
           f'<div class="sw-row"><span class="sw-l1"><span class="sk-len {heat_cls(x["st"]["n"])}">{x["st"]["n"]}</span>{"" if hub else icons.sport_icon(sport.sp)}{sport.link(slug, sport.badge(slug, 22, root), root, "sw-logo")}'
           f'<span class="sw-code">{esc(sport.code(slug))}</span><span class="sw-line">{line}</span></span>'
           f'<span class="sw-next">{next_txt(sport, x, now_utc, short=True)}</span></div>')
    cls = 'sw-item' + (' sw-top' if i == 0 else '') + (' sw-first' if i == 1 else '') + (' sw-more' if i > STREAK_PHONE else '')
    lead = ' data-lead' if x.get('lead') else ''
    return f'<li class="{cls}" data-start="{esc(g.get("start") or "")}" data-state="{esc(g.get("state") or "pre")}"{lead}>{big}{row}</li>'


def streak_when(xs, now_utc, hub):
    """' · Fri, Nov 20' (football hub: ' · Week 12') for a list that isn't
    today's, else ''."""
    if not xs:
        return ''
    if hub and xs[0]['sport'].weekly:
        wk = week_label([(x['day'], x['game']) for x in xs])
        return f' · {wk}' if wk else ''
    day = min(x['day'] for x in xs)
    return '' if day == now_utc.astimezone(ET).date().isoformat() else f' · {day_label(day)}'


def streaks_watch(S, now_utc, root='', hub=False):
    """Streak to Watch (one) / Streaks to Watch (2+): the top streak large
    (logo, full name, the run in yellow, NEXT MATCHUP), then up to
    STREAK_ROWS one-line rows (phones: STREAK_PHONE and "All streaks").
    A second, hidden list holds the next game day's streaks (titled
    "Streaks to Watch · Fri, Nov 20"); FRONT_JS shows it once every streak
    in the first has started. Neither has any: no block, and Matchup of the
    Day goes full width (.fv.sw-none)."""
    lists = []
    for nxt in (False, True):
        xs = streaks(S, now_utc, hub, nxt)[:STREAK_ROWS + 1]
        if xs:
            lists.append((xs, streak_when(xs, now_utc, hub)))
    if not lists:
        return ''
    if len(lists) == 2 and lists[0][1] == lists[1][1]:
        lists = lists[:1]
    top = lists[0][0][0]['sport']
    xs, when = lists[0]
    title = ('Streak to Watch' if len(xs) == 1 else 'Streaks to Watch') + when
    uls = ''
    for n, (xs, when) in enumerate(lists):
        items = ''.join(streak_item(x, i, now_utc, root, hub, len(xs) > STREAK_PHONE + 1) for i, x in enumerate(xs))
        uls += (f'<ul class="sw-list" data-one="Streak to Watch{esc(when)}" data-many="Streaks to Watch{esc(when)}"'
                f'{" hidden" if n else ""}>{items}</ul>')
    link = more_link(f'{root}{top.trends_page}#streak-trends', 'All streaks')
    return (f'<section class="fr-sec tw sw" id="team-watch" data-streaks><div class="fr-head"><h2>{esc(title)}</h2></div>'
            f'<div class="st-card tw-card">{uls}<div class="fr-links sw-all">{link}</div></div></section>')


# ------------------------------------------------------ Get the Running Tab
def running_tab():
    import signup
    # id="premium": the nav's Sign in / Go Premium links land here
    return ('<section class="fr-sec rt" id="premium"><div class="st-card rt-card"><h2>Get the Running Tab</h2>'
            '<p class="rt-line">Free newsletter: last night&rsquo;s results, tonight&rsquo;s spots. Readers hear first when Premium launches.</p>'
            f'{signup.box("tab")}</div></section>')


# ------------------------------------------------------- index pages
# /matchups/, /odds/ and /trends/: title + date, pills (All + each sport,
# tapping one scrolls to its section), then one section per sport in
# season, always listed, in nav order: up to 3 cards and "More NHL
# Matchups". Everything is in the HTML.
INDEX_CARDS = 3
ROLLOVER_HOUR = 6   # the index pages' day runs 6 AM to 6 AM ET


def index_day(now_utc):
    return (now_utc.astimezone(ET) - timedelta(hours=ROLLOVER_HOUR)).date().isoformat()


def index_games(sport, now_utc):
    """[(date, game)], up to INDEX_CARDS. Daily sports: the day's first 3 by
    start time, kept all day (live and final too); none that day: the next
    game day's first 3. Weekly sports: the week's next 3 still to start."""
    day = index_day(now_utc)
    if sport.weekly:
        return upcoming(sport, day, now_utc)[:INDEX_CARDS]
    for d in sorted(x for x in (sport.doc.get('games') or {}) if x >= day):
        games = sorted((g for g in sport.games(d) if game_lined(sport, g)), key=lambda g: (g.get('start') or '', g['away']))
        if games:
            return [(d, g) for g in games[:INDEX_CARDS]]
    return []


def week_label(games):
    """'Week 11' from the shown games' week key ('2-11')."""
    wk = next((str(g.get('wk')) for _, g in games if g.get('wk')), '')
    n = wk.split('-')[-1]
    return f'Week {n}' if n.isdigit() else ''


def index_section(sport, inner, more_href, more_text, heading_extra=''):
    extra = f' <span class="ix-week">&middot; {esc(heading_extra)}</span>' if heading_extra else ''
    return (f'<section class="ix-group" id="ix-{sport.key}"><h2 class="ix-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}{extra}</h2>'
            f'{inner}<div class="fr-links">{more_link(more_href, more_text)}</div></section>')


def index_page(kind, day, sections_html, S):
    return (f'<div class="ix" id="ix-top"><div class="ix-head"><h1>{esc(INDEX[kind]["h1"])}</h1><span class="sl-date">{esc(day_label(day))}</span></div>'
            f'{sections_html}</div>')


def trends_index_body(S, now_utc, root='../'):
    """/trends/: per sport, the top 3 trends (ranked by season units) for
    the games /odds/ and /matchups/ show (index_games: daily sports their
    day, labeled when it isn't today; football the week's games still to
    start), Hottest Trends cards with the "i", up to 3 rows each. Fully open:
    the newsletter lock is on each sport's own Trends page."""
    out, today = '', index_day(now_utc)
    for sport in S.values():
        games = index_games(sport, now_utc)
        ids, day = {str(g['id']) for _, g in games}, games[0][0] if games else None
        found = []
        if games:
            for sp, c, b, xs in hot_cards({sport.key: sport}, now_utc, bar=False, day=None if sport.weekly else day, left=sport.weekly):
                xs = [x for x in xs if str(x['id']) in ids]
                if xs:
                    found.append((sp, c, b, xs))
        found.sort(key=lambda f: -f[1]['units'])
        cards = [h for h in (hot_card(sp, c, b, xs, root, now_utc, False) for sp, c, b, xs in found) if h][:INDEX_CARDS]
        inner = (f'<div class="tr-cards ht-cards">{"".join(cards)}</div>' if cards
                 else f'<p class="fr-empty">No {esc(sport.label)} trends for {"these games" if games else "games coming up"} yet.</p>')
        extra = week_label(games) if sport.weekly else (day_label(day) if day and day != today else '')
        out += index_section(sport, inner, f'{root}{sport.trends_page}', f'More {esc(sport.label)} Trends', extra)
    return index_page('trends', today, out, S) + running_tab()


# ---------------------------------------------------- Yesterday's Results
def last_week(sport, today):
    """Football: the latest week whose games are all final ("Week 10")."""
    done = None
    for w in sport.doc.get('weeks') or []:
        games = [g for _, g in sport.all_games() if g.get('wk') == w['key']]
        if games and w['start'] <= today and all(g.get('state') in ('final', 'post') for g in games):
            done = w
    return done


WR_ROWS = 3   # Week N Results: best / worst results shown
WR_STREAKS = 4   # ... and streaks that grew, and that ended
# a streak that ended, by its market and the result it ran on: "1Q Under streak ended at 11"
STREAK_WORD = {'su': {'W': 'win', 'L': 'losing'}, 'ats': {'W': 'cover', 'L': 'no-cover'}, 'tot': {'O': 'Over', 'U': 'Under'},
               'rfi': {'Y': 'YRFI', 'N': 'NRFI'}}


def between_weeks(sport, today):
    """Football: the week just finished when `today` is after its last game
    (the hub shows its results until the next week's preview is up), else None."""
    wk = last_week(sport, today)
    return wk if wk and wk['end'] < today else None


def week_results(sport, wk, now_utc, root=''):
    """A football hub between weeks: "Week 11 Results", the week's
    first-segment records (favorite ATS, Overs, home team; the Betting
    Guides' lastweek numbers), the best and worst results (each linked to
    its game on the Odds page), the streaks that grew or ended, and when the
    next week's preview comes. Same card as Yesterday's Best."""
    import daily_content as dc
    import guide_stats
    import preview as pv
    D = sport.doc
    games = [(d, g) for d, g in guide_stats.finals(D, sport.key) if g.get('wk') == wk['key']]
    stats = (('fav_ats', 'Favorites ATS'), ('over', 'Overs'), ('home_ml', 'Home teams'))
    vals = {}
    rec = ''
    for s in sport.segments:
        rows = [(g, (g.get('res') or {}).get(s['key'])) for _, g in games]
        rows = [(g, x) for g, x in rows if x and x.get('sc') and not x.get('na')]
        for stat, word in stats:
            v = guide_stats.value(stat, rows, s['key'])
            if v != guide_stats.EMPTY:
                vals[(stat, s['key'])] = v
                rec += (f'<li class="yb-row"><span class="yb-sp">{esc(s["tag"])}</span><span class="yb-dot">&middot;</span>'
                        f'<span class="yb-mk">{word}</span><span class="yb-dot">&middot;</span><span class="yb-rec">{esc(v)}</span></li>')
    # desktop: the records as a grid (a row per record, a column per segment); phones keep the list
    segs = [s for s in sport.segments if any((stat, s['key']) in vals for stat, _ in stats)]
    grid = ''.join(f'<tr><th scope="row">{word}</th>' + ''.join(f'<td class="nw">{esc(vals.get((stat, s["key"]), "-"))}</td>' for s in segs) + '</tr>'
                   for stat, word in stats if any((stat, s['key']) in vals for s in segs))
    if grid:
        grid = ('<table class="wr-grid"><thead><tr><th></th>' + ''.join(f'<th scope="col">{esc(s["tag"])}</th>' for s in segs)
                + f'</tr></thead><tbody>{grid}</tbody></table>')
    # every moneyline / spread / total bet of the week, with its game
    finals = [g for _, g in sport.all_games() if g.get('wk') == wk['key'] and g.get('state') == 'final' and g.get('res')]
    bets = []
    for g in finals:
        for b in dc.results_packet(sport.key, D, [g])[1]:
            if b.get('units') is not None:
                bets.append((b, g))
    best = sorted([x for x in bets if x[0]['units'] > 0], key=lambda x: -x[0]['units'])[:WR_ROWS]
    # the biggest upsets: the shortest price that lost (every favorite's miss is -1u, so the price ranks them)
    worst = sorted([x for x in bets if x[0]['units'] < 0 and isinstance(x[0].get('price'), (int, float))],
                   key=lambda x: x[0]['price'])[:WR_ROWS]

    def game_href(g):
        return f"{root}{sport.odds_page}?week={g['wk']}#og-{g['away']}-{g['home']}"

    def bet_row(b, g, miss=False):
        price = f' ({price_txt(b["price"])})' if isinstance(b.get('price'), (int, float)) and not miss else ''
        tail = f'<span class="yb-rec">{price_txt(b["price"])}</span>' if miss else units_pill(b['units'], True)
        return (f'<li class="yb-row"><a class="wr-bet" href="{esc(game_href(g))}">{esc(b["bet"])}{price}</a><span class="yb-dot">&middot;</span>'
                f'<span class="yb-mk">{esc(sport.code(g["away"]))} @ {esc(sport.code(g["home"]))}</span><span class="yb-dot">&middot;</span>'
                f'{tail}</li>')
    # streaks the week's game grew or ended (3+ games)
    played = {dc.team_of(D, g[x])[1] for g in finals for x in ('away', 'home')}
    changes = dc.streak_changes(dc.seqs_of(D, wk['end']), played, dc.labels_of(D))

    def n_of(c):
        return int(c['streak'].split()[-2])

    def streak_row(c):
        n = n_of(c)
        if c['change'] == 'snapped':   # "SJSU · 1Q Under streak ended at 11", then the game that ended it
            g = next((g for g in reversed(finals) if c['team'] in (dc.team_of(D, g['away'])[1], dc.team_of(D, g['home'])[1])), None)
            seg, m = c['market'].split(':')
            tag = next((s['tag'] for s in sport.segments if s['key'] == seg), seg)
            what = STREAK_WORD.get(m, {}).get(c.get('was'), '')
            game = (f'<span class="yb-dot">&middot;</span><a class="wr-bet" href="{esc(game_href(g))}">'
                    f'{esc(sport.code(g["away"]))} @ {esc(sport.code(g["home"]))}</a>') if g else ''
            return (f'<li class="yb-row"><span class="yb-sp">{esc(c["team"])}</span><span class="yb-dot">&middot;</span>'
                    f'<span class="yb-mk">{esc(" ".join(x for x in ((tag if m != "rfi" else ""), what) if x))} streak ended at {n}</span>{game}</li>')
        return (f'<li class="yb-row"><span class="sk-len {heat_cls(n)}">{n}</span><span class="yb-sp">{esc(c["team"])}</span>'
                f'<span class="yb-mk">{esc(c["streak"])}</span></li>')
    grew = sorted([c for c in changes if c['change'] == 'extended'], key=lambda c: -n_of(c))[:WR_STREAKS]
    ended = sorted([c for c in changes if c['change'] == 'snapped'], key=lambda c: -n_of(c))[:WR_STREAKS]

    def part(title, rows):
        return f'<p class="wr-h">{title}</p><ul class="yb-rows">{rows}</ul>' if rows else ''
    nxt = next((w for w in D.get('weeks') or [] if w['start'] > wk['end']), None)
    coming = ''
    if nxt and pv.weekly(sport):
        today = now_utc.astimezone(ET).date()
        thu = today + timedelta(days=(3 - today.weekday()) % 7)   # the Week Preview is drafted Thursday
        coming = f'<p class="wr-next">{esc(nxt["label"])} preview coming {esc(day_label(thu.isoformat()))}</p>'
    def pair(a, b):   # side by side on desktop, stacked on phones
        return f'<div class="wr-two"><div>{a}</div><div>{b}</div></div>' if a and b else a or b
    records = part('Records', rec)
    if records and grid:
        records = f'<p class="wr-h">Records</p>{grid}<ul class="yb-rows wr-list">{rec}</ul>'
    inner = (records + pair(part('Best results', ''.join(bet_row(*x) for x in best)),
                            part('Biggest misses', ''.join(bet_row(*x, miss=True) for x in worst)))
             + pair(part('Streaks that grew', ''.join(streak_row(c) for c in grew)),
                    part('Streaks that ended', ''.join(streak_row(c) for c in ended))) + coming)
    return (f'<section class="fr-sec yb yb-hero wr" id="week-results"><div class="st-card yb-card">'
            f'<div class="st-head"><h4>{esc(wk["label"])} Results</h4></div>{inner}</div></section>')


def yesterdays_results(S, yday, root='', hub=False, week=None):
    """Pills per sport that played yesterday (home), then that sport's
    segment pills; each pane is the Matchups page's Results box. yday can be
    an earlier day (a hub with no games today: its last game day), titled
    "[Weekday]'s Results". A football hub passes its last finished week:
    "Last Week's Results · Week 10"."""
    panes, sport_opts = '', []
    for sport in S.values():
        games = [g for _, g in sport.all_games() if g.get('wk') == week['key']] if week else sport.games(yday)
        segs = []
        for k in result_segments(sport):
            rows = result_rows(sport, games, k)
            if rows:
                segs.append((k, results_box(rows, f"{week['label']} Results" if week else results_title(yday))))
        if not segs:
            continue
        sport_opts.append((sport.key, sport.label))
        tags = [(k, 'NRFI · F5' if k == 'f5' and sport.doc.get('sportType') == 'baseball' else seg_tag(sport, k)) for k, _ in segs]
        inner = pills(f'{sport.label} segment', tags, segs[0][0])
        inner += ''.join(f'<div data-pane="{k}"{"" if i == 0 else " hidden"}>{box}</div>' for i, (k, box) in enumerate(segs))
        q = f"week={week['key']}" if week else f"date={yday}"
        inner += f'<div class="fr-links">{more_link(f"{root}{sport.matchups}?{q}", esc(sport.label) + " Results")}</div>'
        panes += f'<div class="fr-res" data-pane="{sport.key}"{"" if not panes else " hidden"} data-sub>{inner}</div>'
    if not panes:
        return ''
    named = 'Yesterday' if yday >= (datetime.now(ET).date() - timedelta(days=1)).isoformat() else Date.fromisoformat(yday).strftime('%A')
    if week:
        named = 'Last Week'
    head = (f'<div class="fr-head"><h2>{named}&rsquo;s Results</h2><span class="fr-date">{esc(week["label"] if week else day_label(yday))}</span></div>'
            + (pills('Sport', sport_opts, sport_opts[0][0]) if not hub else ''))
    return f'<section class="fr-sec" id="results" data-tabs>{head}{panes}</section>'


# --------------------------------------------------------- index pages
INDEX = {
    'matchups': {'title': sports.page_title(f'{sports.CROSS_WORDS} Matchups', daily=True), 'h1': f'{sports.CROSS_WORDS} Matchups',
                 'desc': 'Every game today with first period, first quarter and first half odds: the favorite, spread, moneyline and total for {sports}.',
                 'link': 'Matchups'},
    'odds': {'title': sports.page_title(f'{sports.CROSS_WORDS} Odds', daily=True), 'h1': f'{sports.CROSS_WORDS} Odds',
             'desc': 'The best first period, first quarter and first half price at every sportsbook today, for {sports}.',
             'link': 'Odds'},
    'trends': {'title': sports.page_title(f'{sports.CROSS_WORDS} Betting Trends', daily=True), 'h1': f'{sports.CROSS_WORDS} Betting Trends',
               'desc': 'Every first period, first quarter and first half betting trend with a game today, for {sports}.',
               'link': 'Trends'},
}


def index_body(S, now_utc, kind, root='../'):
    """/matchups/ (Slate cards) and /odds/ (the best price per market, with
    the book): index_games for every sport in season."""
    odds = kind == 'odds'
    day = index_day(now_utc)
    out = ''
    for sport in S.values():
        games = index_games(sport, now_utc)
        inner = (f'<div class="sl-cards">{"".join(slate_card(sport, d, g, day, now_utc, root, odds=odds, show_sport=False, full=True) for d, g in games)}</div>'
                 if games else f'<p class="fr-empty">No {esc(sport.label)} games with {"lines" if odds else "odds"} coming up.</p>')
        out += index_section(sport, inner, f'{root}{sport.odds_page if odds else sport.matchups}',
                             f'More {esc(sport.label)} {INDEX[kind]["link"]}', week_label(games) if sport.weekly else '')
    return index_page(kind, day, out, S)


# ------------------------------------------------------------ the script
# Pills switch panes in place; the Slate keeps the next 3 games per tab
# (today's first; none left today: the next day's), dropping each game as
# it starts; trend rows flip to LIVE at their start time.
FRONT_JS = '''
<script>
(function() {
  'use strict';
  function now() { return Date.now(); }
  function isOn(el) { var s = el.getAttribute('data-start'); return el.getAttribute('data-state') !== 'pre' || (s && Date.parse(s) <= now()); }
  function etDay(t) { return new Date(t).toLocaleDateString('en-CA', { timeZone: 'America/New_York' }); }
  function dayLabel(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }); }
  function slate(sec) {
    var tab = sec.getAttribute('data-tab'), n = +sec.getAttribute('data-shown') || 3, today = etDay(now());
    var cards = [].slice.call(sec.querySelectorAll('.sl-card'));
    var mine = cards.filter(function(c) { return (tab === 'all' || c.getAttribute('data-sport') === tab) && !isOn(c); });
    var day = mine.some(function(c) { return c.getAttribute('data-day') === today; }) ? today : (mine[0] && mine[0].getAttribute('data-day'));
    // football's tab: the week's next games whatever the day; else today's
    // (fewer than 3 left: what's left), or the next game day's when none are
    var weekly = tab !== 'all' && mine.length && mine[0].hasAttribute('data-weekly');
    var keep = (weekly ? mine : mine.filter(function(c) { return c.getAttribute('data-day') === day; })).slice(0, n);
    cards.forEach(function(c) { c.hidden = keep.indexOf(c) === -1; });
    sec.classList.toggle('sl-all', tab === 'all');
    // every game today has started (the tab's sports): the next game day's
    // cards under "Tonight's games are underway", or the line alone
    var ends = {}; try { ends = JSON.parse(sec.getAttribute('data-ends') || '{}'); } catch (e) {}
    var last = Object.keys(ends).filter(function(k) { return tab === 'all' || k === tab; }).map(function(k) { return Date.parse(ends[k]); });
    // only after the last game of the day it was built for has started (a
    // page from an earlier day never says it; a sport with no games never does)
    var over = sec.getAttribute('data-today') === today && last.length > 0 && Math.max.apply(null, last) <= now() &&
      !keep.some(function(c) { return c.getAttribute('data-day') === today; });
    var ov = sec.querySelector('[data-over]');
    if (ov) {
      ov.hidden = !over;
      ov.querySelector('[data-over-text]').textContent = keep.length ? 'Tonight\u2019s games are underway.' : 'All of today\u2019s games have started.';
    }
    var shown = keep.length ? keep[0].getAttribute('data-day') : today, dl = sec.querySelector('.sl-date');
    if (dl && shown) dl.textContent = dayLabel(shown);
    var empty = sec.querySelector('[data-empty]');
    if (empty) empty.hidden = keep.length > 0 || over;
    sec.querySelectorAll('.fr-links [data-tab]').forEach(function(a) { a.hidden = a.getAttribute('data-tab') !== tab; });
    // the live chip: "Next up · 14 min" today; another day's "Next up · Thu 7:00 PM"
    var next = sec.querySelector('[data-next]');
    if (next) {
      var t = keep.length ? Math.min.apply(null, keep.map(function(c) { return Date.parse(c.getAttribute('data-start')); })) : NaN;
      next.hidden = isNaN(t);
      if (!isNaN(t)) {
        var mins = Math.max(1, Math.ceil((t - now()) / 60000)), when;
        if (etDay(t) === today) when = mins >= 60 ? Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm' : mins + ' min';
        else when = new Date(t).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }).replace(',', '');
        next.querySelector('[data-next-text]').textContent = 'Next up \\u00b7 ' + when;
      }
    }
  }
  function pick(group, v) {
    group.querySelectorAll('[data-pick]').forEach(function(b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-pick') === v)); });
  }
  document.querySelectorAll('[data-slate]').forEach(function(sec) {
    var g = sec.querySelector('[data-pills]');
    if (g) g.addEventListener('click', function(e) {
      var b = e.target.closest('[data-pick]'); if (!b) return;
      pick(g, b.getAttribute('data-pick')); sec.setAttribute('data-tab', b.getAttribute('data-pick')); slate(sec);
    });
    slate(sec);
    setInterval(function() { slate(sec); }, 60000);
  });
  // tabbed panes: Yesterday's Results (sport, then segment), the index pages
  document.querySelectorAll('[data-pills]').forEach(function(g) {
    if (g.closest('[data-slate]')) return;
    g.addEventListener('click', function(e) {
      var b = e.target.closest('[data-pick]'); if (!b) return;
      var v = b.getAttribute('data-pick');
      pick(g, v);
      [].forEach.call(g.parentNode.children, function(el) {
        if (!el.hasAttribute('data-pane')) return;
        var p = el.getAttribute('data-pane');
        el.hidden = v === 'all' ? el.hasAttribute('data-only') : p !== v;
      });
    });
  });
  // The Big Numbers: the title bar names the segment shown ("NBA · 1st Half")
  document.querySelectorAll('[data-bn-names]').forEach(function(c) {
    var names = {}; try { names = JSON.parse(c.getAttribute('data-bn-names')); } catch (e) {}
    c.addEventListener('click', function(e) {
      var b = e.target.closest('[data-pick]'), t = c.querySelector('[data-bn-seg]');
      if (b && t && names[b.getAttribute('data-pick')]) t.textContent = names[b.getAttribute('data-pick')];
    });
  });
  document.querySelectorAll('[data-trends-more]').forEach(function(b) {
    b.addEventListener('click', function() {
      b.parentNode.querySelectorAll('.tr-card[data-more]').forEach(function(c) { c.hidden = false; });
      b.remove();
    });
  });
  // a trend row's "Last time" line: a click or tap opens it under the row
  // (one at a time; again closes it); desktop also shows it on hover (CSS)
  // (assets/sport.js has the same handler; window.__lastRows: one of them)
  function lastRow(r) {
    var open = r.getAttribute('aria-expanded') !== 'true';
    document.querySelectorAll('.tr-has-last[aria-expanded="true"]').forEach(function(x) { x.setAttribute('aria-expanded', 'false'); });
    r.setAttribute('aria-expanded', String(open));
  }
  if (!window.__lastRows) {
    window.__lastRows = true;
    document.addEventListener('click', function(e) {
      var r = e.target.closest ? e.target.closest('.tr-has-last') : null;
      if (r && !e.target.closest('a, button')) lastRow(r);
    });
    document.addEventListener('keydown', function(e) {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.classList && e.target.classList.contains('tr-has-last')) { e.preventDefault(); lastRow(e.target); }
    });
  }
  function rows() {
    document.querySelectorAll('.fr-trow[data-state="pre"]').forEach(function(r) {
      if (!isOn(r)) return;
      r.setAttribute('data-state', 'in');
      r.querySelector('.tr-time').textContent = 'LIVE';
    });
  }
  rows();
  setInterval(rows, 60000);
  // Hottest Trends: rows only for games still to start; a trend whose games
  // have all started drops off and the next moves up; none left today: the
  // next game day's (data-group 1), dated that day
  function hot(sec) {
    var n = +sec.getAttribute('data-shown') || 3, r = +sec.getAttribute('data-rows') || 3;
    var cards = [].slice.call(sec.querySelectorAll('.ht-card'));
    var alive = cards.filter(function(c) {
      var all = [].slice.call(c.querySelectorAll('.fr-trow')), left = all.filter(function(x) { return !isOn(x); }).slice(0, r);
      all.forEach(function(x) { x.hidden = left.indexOf(x) === -1; });
      return left.length > 0;
    });
    var g = alive.some(function(c) { return c.getAttribute('data-group') === '0'; }) ? '0' : '1';
    var keep = alive.filter(function(c) { return c.getAttribute('data-group') === g; }).slice(0, n);
    cards.forEach(function(c) { c.hidden = keep.indexOf(c) === -1; });
    sec.hidden = !keep.length;
    var d = sec.querySelector('[data-hot-date]');
    if (d && keep.length) d.textContent = keep.map(function(c) { return c.getAttribute('data-label'); }).filter(function(l) { return l !== 'This week'; })[0] || 'This week';
  }
  function live() {
    document.querySelectorAll('[data-hot]').forEach(hot);
  }
  live();
  setInterval(live, 60000);
  // Hottest Trends in a sport's first 21 days: This season / Last season
  document.querySelectorAll('[data-season-pills]').forEach(function(g) {
    g.addEventListener('click', function(e) {
      var b = e.target.closest('[data-pick]'); if (!b) return;
      var v = b.getAttribute('data-pick');
      pick(g, v);
      g.closest('section').querySelectorAll('[data-season]').forEach(function(p) { p.hidden = p.getAttribute('data-season') !== v; });
    });
  });
  // Streaks to Watch: a streak drops off when its game starts and the next
  // moves up (never a team from the Preview's lead game on top); phones keep
  // 5 rows, desktop 5+ rows, filled to Matchup of the Day's height
  var wide = window.matchMedia('(min-width: 900px)');
  function streaksFit(sec) {
    // the first list with a streak still to start (the next game day's once today's have)
    var lists = [].slice.call(sec.querySelectorAll('.sw-list'));
    var list = lists.filter(function(l) { return [].some.call(l.children, function(i) { return !isOn(i); }); })[0] || lists[0];
    lists.forEach(function(l) { l.hidden = l !== list; });
    var items = [].slice.call(list.children), alive = items.filter(function(i) { return !isOn(i); });
    var top = alive.filter(function(i) { return !i.hasAttribute('data-lead'); })[0] || null;
    items.forEach(function(i) { i.hidden = alive.indexOf(i) === -1; i.classList.toggle('sw-top', i === top); i.classList.remove('sw-cut'); });
    if (top && list.firstElementChild !== top) list.insertBefore(top, list.firstElementChild);
    var rows = alive.filter(function(i) { return i !== top; });
    rows.forEach(function(r, n) { r.classList.toggle('sw-more', n >= 5); r.classList.toggle('sw-first', n === 0); });
    sec.hidden = !alive.length;
    var h = sec.querySelector('h2');
    if (h) h.textContent = alive.length === 1 ? list.getAttribute('data-one') : list.getAttribute('data-many');
    var mo = document.querySelector('.fv-motd .mo-card'), grid = sec.closest('.fv');
    // no streaks left on either day: Matchup of the Day takes the full width
    if (grid) grid.classList.toggle('sw-none', !alive.length);
    if (wide.matches && mo && grid) {
      // measure both cards at their own height (not stretched level), then level them
      var card = sec.querySelector('.tw-card'), cut = rows.slice();
      grid.classList.add('sw-measure');
      // never under 5 rows below the top streak; more when Matchup of the Day is taller
      while (cut.length > 5 && card.getBoundingClientRect().bottom > mo.getBoundingClientRect().bottom + 1) cut.pop().classList.add('sw-cut');
      grid.classList.remove('sw-measure');
    }
  }
  function streaksAll() { document.querySelectorAll('[data-streaks]').forEach(streaksFit); }
  streaksAll();
  window.addEventListener('load', streaksAll);
  window.addEventListener('resize', streaksAll);
  setInterval(streaksAll, 60000);
  // the off-season countdown: days / hours / minutes to opening day, and each milestone's days left
  function countdown() {
    document.querySelectorAll('[data-countdown]').forEach(function(c) {
      var left = Math.max(0, Math.floor((Date.parse(c.getAttribute('data-countdown')) - now()) / 60000));
      var v = { d: Math.floor(left / 1440), h: Math.floor(left / 60) % 24, m: left % 60 };
      c.querySelectorAll('[data-cd]').forEach(function(x) { x.textContent = v[x.getAttribute('data-cd')]; });
    });
    var today = Date.parse(etDay(now()) + 'T12:00:00Z');
    document.querySelectorAll('[data-days]').forEach(function(x) {
      var n = Math.round((Date.parse(x.getAttribute('data-days') + 'T12:00:00Z') - today) / 864e5);
      x.textContent = n > 0 ? n + (n === 1 ? ' day' : ' days') : '';
    });
  }
  countdown();
  setInterval(countdown, 30000);
})();
</script>'''


def yesterday(now_utc):
    return (now_utc.astimezone(ET).date() - timedelta(days=1)).isoformat()


def next_games(st):
    """No games today: "Next games: Fri, Nov 21"."""
    return f'<section class="fr-sec nx" id="next-games"><p class="nx-line">Next games: <span class="nx-day">{esc(day_label(st["next"]))}</span></p></section>' if st.get('next') else ''


def off_sections(sport, st, now_utc, root):
    """A hub between seasons (off-season, preseason, season just ended):
    Countdown + Champions, Best Bet of last season + Season in Review, The
    RTYB Awards, then the Betting Guide card + the Running Tab. Desktop:
    template.html .fv-off."""
    import offseason
    b = offseason.blocks(sport, st, now_utc, root)

    def box(cls, html):
        return f'<div class="{cls}">{html}</div>' if html else ''
    return ('<div class="fv fv-off">' + box('fv-cd', b['countdown']) + box('fv-champ', b['champions'])
            + box('fv-motd', b['best']) + box('fv-pair', b['review']) + box('fv-trends', b['awards'])
            + box('fv-results', b['guide']) + box('fv-tab', b['tab']) + f'</div>{FRONT_JS}')


def hub_hero(S, st, pv, now_utc, root=''):
    """A hub's hero: its Preview; football between weeks, the finished
    week's results until the next week's preview is up; else (no games
    today: "Next games: [day]" +) Yesterday's Best."""
    if pv:
        return pv
    sport = next(iter(S.values())) if S else None
    wk = between_weeks(sport, now_utc.astimezone(ET).date().isoformat()) if sport and sport.weekly else None
    if wk:
        return week_results(sport, wk, now_utc, root)
    return (next_games(st) if st and st['layout'] == 'no_games' else '') + best_hero(S, yesterday(now_utc), True)


def sections(S, now_utc, root='', hub=False, learn=''):
    """The front page, home and every hub (a hub: that sport only), six
    slots in this order on phones; desktop places them by grid area
    (template.html .fv): the hero full width; The Slate; Matchup of the Day
    (2/3) | Streaks to Watch (1/3), bottoms level; The Big Numbers full
    width; Hottest Trends; Yesterday's Results (2/3) with Betting Guides
    under it, the ad slot to their right (nothing while ADS_ON is off).
    Home: the H1 first, the all-sports Preview (once published) as the hero
    with Yesterday's Best under it, else Yesterday's Best as the hero.
    A hub fills the slots by its season state (scripts/seasons.py):
      game day         the sport's Preview (Yesterday's Best before it's up),
                       today's games
      no games today   "Next games: [day]" + Yesterday's Best (the next game
                       day's Preview once it shows), the next game day's
                       games, the last game day's results
      football between weeks  "Week N Results" (week_results) from the day
                       after the week's last game until the next week's
                       preview is up
      between seasons  off_sections"""
    import bignums
    import preview
    import seasons
    yday = yesterday(now_utc)
    st = None
    if hub and S:
        sport = next(iter(S.values()))
        st = seasons.of(sport.sp, sport.doc, now_utc)
        if st['layout'] == 'off':
            return off_sections(sport, st, now_utc, root)
    no_games = bool(st) and st['layout'] == 'no_games'
    if hub:
        pv = preview.hub_section(next(iter(S)), now_utc, root, day=st['next'] if no_games else None) if sports.PREVIEW_LIVE and S else ''
        hero = hub_hero(S, st, pv, now_utc, root)
        best = ''
    else:
        p = preview.hero(now_utc, root) if sports.PREVIEW_LIVE else ''
        hero = p or best_hero(S, yday, hub)
        best = yesterdays_best(S, yday) if p else ''
    res_day = st['last'] if no_games and st.get('last') else yday
    res_week = None
    if hub and S and next(iter(S.values())).weekly:
        res_week = last_week(next(iter(S.values())), now_utc.astimezone(ET).date().isoformat())

    def box(cls, html):
        return f'<div class="{cls}">{html}</div>' if html else ''
    ad = preview.ad_slot('front')
    pair = streaks_watch(S, now_utc, root, hub)
    return (f'<div class="fv{"" if hub else " fv-home"}{"" if pair else " sw-none"}">' + ('' if hub else box('fv-slogan', slogan(S))) + box('fv-hero', hero) + box('fv-yb', best)
            + box('fv-slate', slate(S, now_utc, root, hub)) + box('fv-motd', motd(S, now_utc, root, hub))
            + box('fv-pair', pair) + box('fv-bn', bignums.section(S, now_utc, root, hub))
            + box('fv-trends', hottest_trends(S, now_utc, root, hub, early=bool(st) and st['key'] == 'early'))
            + box('fv-results', yesterdays_results(S, res_day, root, hub, week=res_week)) + box('fv-learn', learn) + (f'<div class="fv-ad">{ad}</div>' if ad else '')
            + f'</div>{FRONT_JS}')
