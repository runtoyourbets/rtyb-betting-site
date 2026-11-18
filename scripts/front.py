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
HOT_SHOWN = 3          # Hottest Trends: exactly this many cards,
HOT_ROWS = 3           # ... with up to this many game rows each
PREVIEW_HOUR = 11      # On Tap shows from 11 AM ET to the next day's 11 AM
MOTD_TRENDS = 4        # agreeing trends listed on Matchup of the Day
BEST_MIN = 3           # Yesterday's Best: decided games a record needs
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
        return '&mdash;'
    return '&mdash;' if abs(p) > ML_CAP else esc(signed(round(p)))


def fmt_units(u):
    r = round(u, 2)
    return f"{'+' if r > 0 else ''}{r:.2f}u"


def unit_tone(u):
    # green above +0.5u, red below -0.5u, yellow between (CLAUDE.md color rule)
    r = round(u, 2)
    return 'pos' if r > 0.5 else 'neg' if r < -0.5 else 'mid'


def units_pill(u, priced):
    if not priced:
        return '<span class="u-pill u-none">&mdash;</span>'
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
    """{key: Sport} for the sports on the site (or `keys`), in nav order."""
    return {sp['key']: Sport(sp) for sp in sports.LAUNCHED if keys is None or sp['key'] in keys}


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
        f'<span class="ds-col-pct mono">{"&mdash;" if x.pct is None else str(round(x.pct * 100)) + "%"}</span>'
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
def best_words(sport, k, x):
    seg = '' if sport.key == 'nhl' or sport.doc.get('sportType') == 'baseball' else seg_tag(sport, k) + ' '
    if sport.key == 'nhl':
        seg = '1P '
    label = (x.label.replace(' (moneyline)', ' ML').replace(' (spread)', ' Spread').replace(' (F5 moneyline)', ' F5 ML')
             .replace('O/U: ', 'O/U ').replace(' (home team)', ', home team'))
    return f'{seg}{label}'


def best_cands(S, yday):
    """[(sport, segment, row)] yesterday with positive units, a winning
    record and 3+ decided games (1-0 is 100% but says little), best first:
    best win %, then units."""
    cand = []
    for sport in S.values():
        games = [g for g in sport.games(yday)]
        for k in result_segments(sport):
            for x in result_rows(sport, games, k):
                if x.n and x.w > x.l and x.w + x.l >= BEST_MIN and round(x.u, 2) > 0:
                    cand.append((x.pct or 0, x.u, sport, k, x))
    cand.sort(key=lambda c: (-c[0], -c[1]))
    return [(sport, k, x) for _, _, sport, k, x in cand]


def best_what(sport, k, x):
    ties = ''
    if x.t:
        word = 'tie' if x.ties else 'push'
        ties = f" ({x.t} {word}{'' if x.t == 1 else 's' if x.ties else 'es'})"
    return f'{sport.label} &middot; {esc(best_words(sport, k, x))} went {x.w}&ndash;{x.l}{ties}, {fmt_units(x.u)}'


def yesterdays_best(S, yday):
    """The slim strip: the single best market yesterday, else nothing."""
    cand = best_cands(S, yday)
    if not cand:
        return ''
    return (f'<section class="fr-sec yb" id="best"><div class="yb-box">'
            f'<div class="yb-head"><h2 class="yb-title">Yesterday&rsquo;s Best</h2><span class="yb-date">{esc(day_label(yday))}</span></div>'
            f'<p class="yb-line">{best_what(*cand[0])}</p></div></section>')


def best_hero(S, yday, hub=False):
    """The hero when there's no On Tap: Yesterday's Best, large, with the
    next-best positive results from two other sports (a hub: from its own
    other markets) on one line. Built from the numbers; nothing to approve."""
    cand = best_cands(S, yday)
    if not cand:
        return ''
    top, more, seen = cand[0], [], {cand[0][0].key}
    for sport, k, x in cand[1:]:
        if len(more) == 2:
            break
        if hub or sport.key not in seen:
            seen.add(sport.key)
            more.append(f'{esc(sport.label)} {esc(best_words(sport, k, x))} {x.w}&ndash;{x.l}')
    line = f'<p class="yb-more">{" &middot; ".join(more)}</p>' if more else ''
    return (f'<section class="fr-sec yb yb-hero" id="best"><div class="yb-box yb-big">'
            f'<span class="yb-kicker">Yesterday&rsquo;s Best &middot; {esc(day_label(yday))}</span>'
            f'<h2 class="yb-headline">{best_what(*top)}</h2>{line}</div></section>')


# ------------------------------------------------------------- On Tap
def on_tap_piece(S, now_utc, key):
    """The published On Tap preview showing now: dated D, from D 11 AM ET to
    D+1 11 AM ET (key 'all': the home page's). On a football-only day the
    home page takes football's Week Preview."""
    import daily
    now = now_utc.astimezone(ET)
    d = now.date() if now.hour >= PREVIEW_HOUR else now.date() - timedelta(days=1)
    day = d.isoformat()
    pieces = [p for p in daily.load() if p['kind'] == 'preview' and p['date'] == day]
    p = next((p for p in pieces if p['sport'] == key), None)
    if p or key != daily.ALL:
        return p
    playing = [sp for sp in S.values() if any(game_lined(sp, g) for g in sp.games(day))]
    if playing and all(sp.weekly for sp in playing):
        return next((p for sp in playing for p in pieces if p['sport'] == sp.key), None)
    return None


def on_tap_hero(p, root):
    d = Date.fromisoformat(p['date'])
    summary = (p['teaser'] or '').split('. ')[0].rstrip('.') + '.' if p.get('teaser') else ''
    return (f'<section class="fr-sec ot" id="on-tap"><a class="ot-card" href="{esc(root + p["path"])}">'
            f'<span class="ot-label">On Tap &middot; {d.strftime("%A")}, {d.strftime("%b")} {d.day}</span>'
            f'<h2 class="ot-title">{esc(p["hook"] or p["title"])}</h2>'
            + (f'<p class="ot-sum">{esc(summary)}</p>' if summary else '') +
            '<span class="ot-more">Read the preview &rarr;</span></a></section>')


HOME_H1 = 'Run to Your Bets: First Period, Quarter & Half Betting'


def slogan(S, hub=False):
    """The home page's H1 (small, the slogan line); a hub's segments line
    (the hub's H1 is its page head)."""
    if not hub:
        return f'<h1 class="fr-slogan">{esc(HOME_H1)}</h1>'
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
            if b in sport_build.NO_BEST or bool((sport.sources.get(b) or {}).get('x')) != exch:
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
    return '<span class="cell"><span class="mc-dash">&ndash;</span></span>'


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
        rows += f'<span class="sl-rh">{esc(s["tag"])}</span>{c_ats}{c_ml}{c_tot}'
    if not rows:
        return ''
    return ('<div class="sl-mk"><span></span><span class="sl-ch">ATS</span><span class="sl-ch">ML</span>'
            f'<span class="sl-ch">O/U</span>{rows}</div>')


def baseball_rows(sport, d, g, odds, root):
    """NRFI/YRFI, then F5 in the spread table's style."""
    rfi = (sport.market(d, g, '1i').get('rfi') or sport.market(d, g, '1i').get('nrfi_yrfi')) or {}
    y, n = rfi.get('yes', rfi.get('yrfi')), rfi.get('no', rfi.get('nrfi'))
    top = ''
    if isinstance(y, (int, float)) and isinstance(n, (int, float)):
        side, p = ('NRFI', n) if implied(n) >= implied(y) else ('YRFI', y)
        top = f'<span class="sl-rh">1st inn</span><span class="sl-wide">{cell(f"{side} {price_txt(p)}")}</span>'
    f5 = spread_rows(sport, d, g, odds, root)
    if not top:
        return f5
    if not f5:
        return f'<div class="sl-mk">{top}</div>'
    return f5.replace('<span class="sl-ch">O/U</span>', f'<span class="sl-ch">O/U</span>{top}', 1)


def nhl_grid(sport, d, g, odds, root):
    """ML · O/U over BTTS · 3-WAY: the favorite (or favored side) and price."""
    og = sport.odds_game(d, g) if odds else {}
    mk = sport.market(d, g, '1p')
    if not mk:
        return ''
    ml, tot, btts, m3 = mk.get('ml') or {}, mk.get('total') or {}, mk.get('btts') or {}, mk.get('ml3') or {}

    def box(head, body):
        return f'<div class="sl-q"><span class="sl-qh">{head}</span>{body}</div>'

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
    """A pill row (scrolls sideways on phones): [(value, label)]."""
    return (f'<div class="fr-pills" role="group" aria-label="{esc(name)}" data-pills="{esc(name)}">' + ''.join(
        f'<button class="seg-btn" type="button" data-pick="{esc(v)}" aria-pressed="{str(v == cur).lower()}">{esc(t)}</button>'
        for v, t in opts) + '</div>')


def more_link(href, text, attrs=''):
    return f'<a class="fr-more" href="{esc(href)}"{attrs}>{text} &rarr;</a>'


def slate(S, now_utc, root='', hub=False):
    now = now_utc
    today = now.astimezone(ET).date().isoformat()
    cards, links, opts = [], '', [('all', 'All')] if not hub else []
    for sport in S.values():
        opts.append((sport.key, sport.label))
        for d, g in upcoming(sport, today, now)[:SLATE_BUFFER]:
            cards.append((g.get('start') or '', d, sport, g))
        links += more_link(f'{root}{sport.matchups}', f'{esc(sport.label)} Matchups', f' data-tab="{sport.key}"')
    if not hub:
        links = more_link(f'{root}matchups/', 'All matchups', ' data-tab="all"') + links
    cards.sort(key=lambda x: (x[0], x[2].label))
    body = ''.join(slate_card(sport, d, g, today, now, root) for _, d, sport, g in cards)
    head = (f'<div class="sl-headline"><div class="sl-title"><h2>The Slate</h2><span class="sl-next" data-next hidden></span></div>'
            f'<span class="sl-date">{esc(day_label(today))}</span></div>'
            + ('' if hub else pills('Sport', opts)))
    empty = '<p class="fr-empty" data-empty hidden>No more games on the board today.</p>'
    tab = next(iter(S)) if hub and S else 'all'
    return (f'<section class="fr-sec sl" id="slate" data-slate data-tab="{tab}" data-today="{today}" data-shown="{SLATE_SHOWN}">{head}'
            f'<div class="sl-cards">{body}</div>{empty}<div class="fr-links">{links}</div></section>')


# -------------------------------------------------------- Hottest Trends
def slate_key(sport, today):
    return week_key(sport, today) if sport.weekly else today


def trend_row(sport, c, x, g, root, now):
    st = 'FINAL' if g.get('state') == 'final' else 'LIVE' if started(g, now) else ''
    when = st or time_et(g.get('start'))
    if sport.weekly and not st and parse(g.get('start')):
        when = parse(g['start']).astimezone(ET).strftime('%a %-I:%M %p')
    bet = (f'Bet {sport.badge(g[x["side"]], 16, root)} {esc(sport.code(g[x["side"]]))}' if x.get('side') else esc(x.get('label')))
    return (f'<div class="tr-row fr-trow" data-start="{esc(g.get("start") or "")}" data-state="{esc(g.get("state") or "pre")}">'
            f'<span class="tr-time">{esc(when)}</span><span class="tr-match">{esc(sport.code(g["away"]))} @ {esc(sport.code(g["home"]))}</span>'
            f'<span class="tr-bet">{bet}</span></div>')


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


def today_rows(sport, c, by_id, today, now):
    """The card's rows for today's games that have a line."""
    return [x for x in c.get('games') or [] if str(x['id']) in by_id
            and today_game(by_id[str(x['id'])], today, now) and game_lined(sport, by_id[str(x['id'])], c['seg'])]


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
            f'<div class="tr-rec"><b class="mono">{c["w"]}&ndash;{c["l"]}</b> &middot; {round(rate)}% &middot; league {round(base)}% &middot; '
            f'<span class="{unit_tone(c["units"])}">{fmt_units(c["units"])}</span></div>'
            f'<div class="tr-bar" aria-hidden="true"><span style="width:{rate:.1f}%"></span><i style="left:{base:.1f}%"></i></div>'
            f'<div class="tr-rows">{rows}</div></div>')


def hot_cards(S, now_utc, bar=True):
    """[(sport, card, by_id, rows)] in order: cards with a game today (ET)
    or live now, rows for today's games only; no 3-way ML; a 55%+ win rate
    (TREND_MIN_RATE); ranked by season
    units. bar: Hottest Trends' bar too (20+ games, 5+ points over the
    league rate). A mirror (Fade X / Back the other side: the same bets)
    keeps the one with more units, and a card whose rows are all bets
    already shown above it is skipped. The first 3 never repeat a sport +
    market; the next card moves up."""
    today = now_utc.astimezone(ET).date().isoformat()
    found = []
    for sport in S.values():
        key = slate_key(sport, today)
        cards = (((sport.trends.get('slates') or {}).get(key) or {}).get('cards')) or []
        by_id = {str(g['id']): g for _, g in sport.all_games()}
        for c in cards:
            if c.get('mk') == 'ml3' or (c.get('units') or 0) <= 0 or (c.get('rate') or 0) < TREND_MIN_RATE - 1e-9:
                continue
            if bar and ((c.get('n') or 0) < TREND_MIN_N or (c.get('rate') or 0) - (c.get('base') or 0) < TREND_MIN_EDGE - 1e-9):
                continue
            xs = today_rows(sport, c, by_id, today, now_utc)
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


def trend_tip(sport, c):
    """The "i" circle, the same as the Trends page's: the card's title, what
    it means, the Fade line on Fade cards and the last game that fit."""
    fade = (sport.trends.get('tips') or {}).get('fade') or ''
    body = (f'<b>{esc(c["title"])}</b><br>{esc(c.get("meaning"))}'
            + (f'<br>{esc(fade)}' if c.get('dir') == 'Fade' else '')
            + (f'<br><i>{esc(c["last"])}</i>' if c.get('last') else ''))
    return f'<button type="button" class="info-tip" aria-label="About this trend">i<span class="tip-bubble" role="tooltip">{body}</span></button>'


def hot_card(sport, c, by_id, xs, root, now, show_sport=True):
    """A Hottest Trends card: the market in the purple bar ("NBA · 1H ML")
    with the "i" on the right, the title, the record and units, then up to
    3 game rows (games still to play first)."""
    xs = sorted(xs, key=lambda x: by_id[str(x['id'])].get('state') == 'final')[:HOT_ROWS]
    rows = ''.join(trend_row(sport, c, x, by_id[str(x['id'])], root, now) for x in xs)
    if not rows:
        return ''
    tag = esc(c['tag'].replace(' ATS', ' Spread'))
    rate, base = c['rate'] * 100, c['base'] * 100
    return (f'<div class="st-card tr-card ht-card"><div class="st-head"><h4><span>{esc(sport.label) + " &middot; " if show_sport else ""}{tag}</span>{trend_tip(sport, c)}</h4></div>'
            f'<h3 class="tr-title">{esc(c["title"])}</h3>'
            f'<p class="ht-rec"><span class="mono">{c["w"]}&ndash;{c["l"]}</span> &middot; {round(rate)}% &middot; league {round(base)}% &middot; '
            f'<span class="{unit_tone(c["units"])}">{fmt_units(c["units"])}</span></p>'
            f'<div class="tr-rows">{rows}</div></div>')


def hottest_trends(S, now_utc, root='', hub=False):
    """Exactly 3 of today's trend cards (hot_cards), nothing locked; one line
    when none qualify. More trends: /trends/ (a hub: its Trends page)."""
    cards = [h for h in (hot_card(sp, c, b, xs, root, now_utc, not hub) for sp, c, b, xs in hot_cards(S, now_utc)) if h][:HOT_SHOWN]
    href = root + (next(iter(S.values())).trends_page if hub and S else 'trends/')
    body = f'<div class="tr-cards ht-cards">{"".join(cards)}</div>' if cards else '<p class="fr-empty">No trends with games today.</p>'
    return (f'<section class="fr-sec" id="trends"><div class="fr-head"><h2>Hottest Trends</h2></div>'
            f'{body}<div class="fr-links">{more_link(href, "More trends")}</div></section>')


# ---------------------------------------------------- Matchup of the Day
def motd_pick(S, now_utc, hub=False):
    """(sport, pick, game) from each sport's hub.json (scripts/hub.py, 3+
    agreeing trends). Home: tonight's game, any sport, with the most
    agreeing trends, ties to the bigger edge over the league rate."""
    today = now_utc.astimezone(ET).date().isoformat()
    best = None
    for sport in S.values():
        m = sport.hub.get('motd')
        if not m:
            continue
        g = next((x for _, x in sport.all_games() if str(x['id']) == str(m['id'])), None) or m
        if not hub and (not today_game(g, today, now_utc) or g.get('state') == 'final'):
            continue
        score = (m.get('n') or 0, m.get('edge') or 0)
        if best is None or score > best[0]:
            best = (score, sport, m, g)
    return best[1:] if best else None


def motd_price(m):
    p = m.get('price') or {}
    if p.get('price') is None:
        return ''
    line = '' if p.get('line') is None else (('U ' if m.get('pick') == 'under' else 'O ') + line_txt(p['line']) + ' ' if m.get('mk') == 'total'
                                             else signed(p['line']) + ' ' if m.get('mk') == 'ats' else '')
    return f'{line}{price_txt(p["price"])}'


def motd(S, now_utc, root='', hub=False):
    pick = motd_pick(S, now_utc, hub)
    if not pick:
        return ''
    sport, m, g = pick
    today = now_utc.astimezone(ET).date().isoformat()
    big = 64

    def team(slug):
        return f'<span class="mo-team">{sport.badge(slug, big, root)}<b class="mo-name">{sport.name_html(slug)}</b></span>'
    price = motd_price(m)
    price = (f'<p class="mo-price">Best price <span class="mono">{esc(price)}</span> at {esc(m["price"]["book"])}</p>' if price else '')
    trends = ''.join(f'<li><span>{esc(t["text"])}</span>' + ('' if t.get('kind') == 'streak' else f'<span class="mono">{esc(t["rec"])}</span>') + '</li>'
                     for t in (m.get('trends') or [])[:MOTD_TRENDS])
    season = ((sport.hub.get('motdRecord') or {}).get('season')) or [0, 0]
    rec = f'<p class="mo-rec">Season: <span class="mono">{season[0]}&ndash;{season[1]}</span></p>' if season[0] > season[1] else ''
    q = f"week={sport.hub.get('slate')}" if sport.weekly and sport.hub.get('slate') else f"date={m.get('date')}"
    href = f"{root}{sport.trends_page}?{q}&seg={m['seg']}#mt-{m['id']}"
    title = 'Matchup of the Week' if hub and sport.weekly else 'Matchup of the Day'
    return (f'<section class="fr-sec mo" id="motd"><div class="fr-head"><h2>{title}</h2></div>'
            f'<div class="st-card mo-card"><div class="st-head"><h4><span>{esc(when_txt(sport, m.get("date") or today, g, today, now_utc))}</span>'
            f'<span class="sl-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span></h4></div>'
            f'<div class="mo-teams">{team(m["away"])}<span class="mo-at">@</span>{team(m["home"])}</div>'
            f'<p class="mo-bet"><span class="mo-n">{m["n"]} trends agree:</span> {esc(m["bet"])}</p>{price}'
            f'<ul class="mo-list">{trends}</ul>{rec}<div class="fr-links">{more_link(href, "See the full matchup")}</div></div></section>')


# --------------------------------------------------------- Team to Watch
STREAK_ORDER = {'ml': 0, 'ats': 1, 'total': 2, 'btts': 3, 'rfi': 4}   # ties: a win/loss run first


def streak_line(sport, slug, m, st, k):
    import hub as H
    s = H.seg_of(sport.doc, k)['label'].lower()
    n = f"{st['n']} straight"
    if m == 'ml':
        return f"{'Won' if st['kind'] == 'W' else 'Lost'} the {s} {n}."
    if m == 'ats':
        return f"{'Covered' if st['kind'] == 'W' else 'Failed to cover'} the {s} spread {n}."
    words = H.streak_words(sport.doc, slug, m, st, k)
    nm = H.short(sport.doc, slug)
    words = words[len(nm) + 1:] if words.startswith(nm + ' ') else words
    return words[:1].upper() + words[1:] + '.'


def team_watch(S, now_utc, root='', hub=False):
    """The longest active run (3+) among teams playing today."""
    import hub as H
    today = now_utc.astimezone(ET).date().isoformat()
    best = None
    for sport in S.values():
        games = [g for g in sport.games(today) if not started(g, now_utc) and game_lined(sport, g)]
        if not games:
            continue
        for k in sorted({x[0] for x in H.market_keys(sport.doc)}):
            seqs = H.team_seqs(sport.doc, today, k)
            for k2, m in H.market_keys(sport.doc):
                if k2 != k:
                    continue
                for g in games:
                    for side in ('away', 'home'):
                        st = H.streak_of(((seqs.get(g[side]) or {}).get(m)) or [])
                        if not st or st['n'] < 3:
                            continue
                        score = (st['n'], -STREAK_ORDER.get(m, 9))
                        if best is None or score > best[0]:
                            best = (score, sport, g, side, m, st, k)
    if not best:
        return ''
    _, sport, g, side, m, st, k = best
    slug, opp = g[side], g['home' if side == 'away' else 'away']
    href = sport.team_href(slug, root)
    link = f' &middot; {more_link(href, "See the team")}' if href else ''
    head = f'<div class="st-head"><h4><span class="sl-sport">{icons.sport_icon(sport.sp)}{esc(sport.label)}</span></h4></div>' if not hub else ''
    return (f'<section class="fr-sec tw" id="team-watch"><div class="fr-head"><h2>Team to Watch</h2></div>'
            f'<div class="st-card tw-card">{head}<div class="tw-main">{sport.badge(slug, 84, root)}<div class="tw-copy">'
            f'<b class="tw-name">{sport.name_html(slug)}</b><p class="tw-line">{esc(streak_line(sport, slug, m, st, k))}</p>'
            f'<p class="tw-next">Tonight vs {esc(sport.code(opp))}{link}</p></div></div></div></section>')


# ------------------------------------------------------ Biggest Line Move
def line_move(S, now_utc, root='', hub=False):
    """The biggest segment-moneyline move since open among games still to
    start today: the largest change in implied probability between the Open
    price and the current best price."""
    today = now_utc.astimezone(ET).date().isoformat()
    best = None
    for sport in S.values():
        for g in sport.games(today):
            if started(g, now_utc) or not game_lined(sport, g):
                continue
            og = sport.odds_game(today, g)
            for k in sport.seg_keys():
                o = ((og.get('open') or {}).get(k) or {}).get('ml') or {}
                c = ((og.get('best') or {}).get(k) or {}).get('ml') or {}
                for side in ('away', 'home'):
                    a, b = o.get(side), c.get(side)
                    if not all(isinstance(x, (int, float)) and abs(x) <= ML_CAP for x in (a, b)):
                        continue
                    ch = abs(implied(b) - implied(a))
                    if ch > 0 and (best is None or ch > best[0]):
                        best = (ch, sport, g, k, side, a, b)
    if not best:
        return ''
    _, sport, g, k, side, a, b = best
    label = f'{esc(sport.label)} &middot; {esc(sport.code(g["away"]))} @ {esc(sport.code(g["home"]))} &middot; {esc(time_et(g.get("start")))}'
    return (f'<section class="fr-sec lm" id="line-move"><div class="fr-head"><h2>Biggest Line Move</h2></div>'
            f'<div class="st-card lm-card"><div class="st-head"><h4>{label}</h4></div>'
            f'<p class="lm-line">{sport.badge(g[side], 22, root)} {esc(sport.code(g[side]))} {esc(seg_tag(sport, k))} moneyline opened '
            f'<span class="mono">{price_txt(a)}</span>, now <span class="mono">{price_txt(b)}</span></p>'
            f'<div class="fr-links">{more_link(f"{root}{sport.odds_page}?date={today}", "See all prices")}</div></div></section>')


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


def index_pills(S):
    links = '<a class="seg-btn" href="#ix-top">All</a>' + ''.join(
        f'<a class="seg-btn" href="#ix-{sport.key}">{esc(sport.label)}</a>' for sport in S.values())
    return f'<nav class="fr-pills ix-pills" aria-label="Sports">{links}</nav>'


def index_section(sport, inner, more_href, more_text, heading_extra=''):
    extra = f' <span class="ix-week">&middot; {esc(heading_extra)}</span>' if heading_extra else ''
    return (f'<section class="ix-group" id="ix-{sport.key}"><h2 class="ix-sport">{esc(sport.label)}{extra}</h2>'
            f'{inner}<div class="fr-links">{more_link(more_href, more_text)}</div></section>')


def index_page(kind, day, sections_html, S):
    return (f'<div class="ix" id="ix-top"><div class="ix-head"><h1>{esc(INDEX[kind]["h1"])}</h1><span class="sl-date">{esc(day_label(day))}</span></div>'
            f'{index_pills(S)}{sections_html}</div>')


def trends_index_body(S, now_utc, root='../'):
    """/trends/: per sport, the top 3 trends for its games (ranked by season
    units), Hottest Trends cards with the "i", up to 3 rows each. Fully open:
    the newsletter lock is on each sport's own Trends page."""
    out = ''
    for sport in S.values():
        found = sorted(hot_cards({sport.key: sport}, now_utc, bar=False), key=lambda f: -f[1]['units'])
        cards = [h for h in (hot_card(sp, c, b, xs, root, now_utc, False) for sp, c, b, xs in found) if h][:INDEX_CARDS]
        inner = (f'<div class="tr-cards ht-cards">{"".join(cards)}</div>' if cards
                 else f'<p class="fr-empty">No {esc(sport.label)} trends with games today.</p>')
        out += index_section(sport, inner, f'{root}{sport.trends_page}', f'More {esc(sport.label)} Trends',
                             week_label(index_games(sport, now_utc)) if sport.weekly else '')
    return index_page('trends', index_day(now_utc), out, S) + running_tab()


# ---------------------------------------------------- Yesterday's Results
def yesterdays_results(S, yday, root='', hub=False):
    """Pills per sport that played yesterday (home), then that sport's
    segment pills; each pane is the Matchups page's Results box."""
    panes, sport_opts = '', []
    for sport in S.values():
        games = sport.games(yday)
        segs = []
        for k in result_segments(sport):
            rows = result_rows(sport, games, k)
            if rows:
                segs.append((k, results_box(rows, results_title(yday))))
        if not segs:
            continue
        sport_opts.append((sport.key, sport.label))
        tags = [(k, 'NRFI · F5' if k == 'f5' and sport.doc.get('sportType') == 'baseball' else seg_tag(sport, k)) for k, _ in segs]
        inner = pills(f'{sport.label} segment', tags, segs[0][0])
        inner += ''.join(f'<div data-pane="{k}"{"" if i == 0 else " hidden"}>{box}</div>' for i, (k, box) in enumerate(segs))
        inner += f'<div class="fr-links">{more_link(f"{root}{sport.matchups}?date={yday}", esc(sport.label) + " Matchups")}</div>'
        panes += f'<div class="fr-res" data-pane="{sport.key}"{"" if not panes else " hidden"} data-sub>{inner}</div>'
    if not panes:
        return ''
    head = (f'<div class="fr-head"><h2>Yesterday&rsquo;s Results</h2><span class="fr-date">{esc(day_label(yday))}</span></div>'
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
    var empty = sec.querySelector('[data-empty]');
    if (empty) empty.hidden = keep.length > 0;
    sec.querySelectorAll('.fr-links [data-tab]').forEach(function(a) { a.hidden = a.getAttribute('data-tab') !== tab; });
    // "Next up in 1h 40m": the tab's next start today; hidden when none is left today
    var next = sec.querySelector('[data-next]'), left = mine.filter(function(c) { return c.getAttribute('data-day') === today; });
    if (next) {
      var t = left.length ? Math.min.apply(null, left.map(function(c) { return Date.parse(c.getAttribute('data-start')); })) : NaN;
      var mins = Math.max(1, Math.ceil((t - now()) / 60000));
      next.hidden = isNaN(t);
      if (!isNaN(t)) next.textContent = 'Next up in ' + (mins >= 60 ? Math.floor(mins / 60) + 'h ' + (mins % 60) + 'm' : mins + 'm');
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
  document.querySelectorAll('[data-trends-more]').forEach(function(b) {
    b.addEventListener('click', function() {
      b.parentNode.querySelectorAll('.tr-card[data-more]').forEach(function(c) { c.hidden = false; });
      b.remove();
    });
  });
  // "i" circles open on tap (sport pages: assets/sport.js does it)
  if (!document.getElementById('sportApp')) document.addEventListener('click', function(e) {
    var tip = e.target.closest ? e.target.closest('.info-tip') : null;
    document.querySelectorAll('.info-tip.open').forEach(function(t) { if (t !== tip) t.classList.remove('open'); });
    if (tip) tip.classList.toggle('open');
  });
  function rows() {
    document.querySelectorAll('.fr-trow[data-state="pre"]').forEach(function(r) {
      if (!isOn(r)) return;
      r.setAttribute('data-state', 'in');
      r.querySelector('.tr-time').textContent = 'LIVE';
    });
  }
  rows();
  setInterval(rows, 60000);
})();
</script>'''


def yesterday(now_utc):
    return (now_utc.astimezone(ET).date() - timedelta(days=1)).isoformat()


def sections(S, now_utc, root='', hub=False, learn=''):
    """The front page, home and every hub (a hub: that sport only). Phone
    order: slogan, hero (On Tap, else Yesterday's Best large), Yesterday's
    Best (not when the hero shows it), The Slate, Matchup of the Day,
    Hottest Trends, Team to Watch, Biggest Line Move, Get the Running Tab,
    Yesterday's Results, Learn (home). Desktop regroups them in rows
    (template.html .fv-*): hero | Yesterday's Best + Running Tab;
    Matchup of the Day | Team to Watch + Line Move; Results | Learn."""
    import daily
    yday = yesterday(now_utc)
    p = on_tap_piece(S, now_utc, next(iter(S)) if hub else daily.ALL)
    hero = on_tap_hero(p, root) if p else best_hero(S, yday, hub)
    best = yesterdays_best(S, yday) if p else ''

    def box(cls, html):
        return f'<div class="{cls}">{html}</div>' if html else ''
    # in phone reading order; desktop places them by grid area (template.html .fv)
    pair = box('fv-pair', box('fv-team', team_watch(S, now_utc, root, hub)) + box('fv-move', line_move(S, now_utc, root, hub)))
    return ('<div class="fv">' + box('fv-slogan', slogan(S, hub)) + box('fv-hero', hero) + box('fv-yb', best)
            + box('fv-slate', slate(S, now_utc, root, hub)) + box('fv-motd', motd(S, now_utc, root, hub))
            + box('fv-trends', hottest_trends(S, now_utc, root, hub)) + pair + box('fv-tab', running_tab())
            + box('fv-results', yesterdays_results(S, yday, root, hub)) + box('fv-learn', learn) + f'</div>{FRONT_JS}')
