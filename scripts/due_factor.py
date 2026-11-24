"""
Due Factor (/{sport}/due-factor/): every market of every segment, hot or
cold against its own season rate. The build writes {slug}/due.json and
assets/sport.js (renderDue) draws the page from it: View (Daily / Weekly /
Monthly; NFL and NCAAF Weekly only), Season (this one and last), the
segment pills (the Full Run's with the gold dot) and the market pills, a
summary line, then the Day by day / Week by week table or the month's
calendar.

due.json:
  {sport, weekly, matchups (the Matchups page path), regular (periods in
   regulation, for OT), segs: [{k, label, fr, m: [{id, label, a, b, ta, tb}]}],
   seasons: [{label, cur (the season being played now), post: [days],
              weeks: [[key, label, [days]]] (football), first, last,
              c: {seg: {market id: {ro, d: {day: [a, b, tie / push]}}}}}]}

Each market counts one side (a) against the other (b); ties and pushes
are the third number and stay out of every rate. ta / tb: the tint when
that side runs 10+ points over (warm: Over / Yes / YRFI, cool: Under / No /
NRFI, win: Home / Fav, dim: Away / Dog). A season's market counts only the
games with a line for it (CLAUDE.md); a market with no line in any of the
season's games for that segment counts every graded result instead
(ro: results only). College: Division I / FBS games only. Postseason games
count, and their days are listed (the calendar marks them).
"""
import json
import os
from datetime import date, timedelta

import front
import guide_stats
import sport_build
import sports
from front import esc

ROOT = sport_build.ROOT
MIN_GAMES = 15   # fewer graded games in the summary's period: "Small sample"
STRIP_MIN = 10   # the home / hub strip (sports.DUE_STRIP): only gaps this big
POST_WEEKS = {'nfl': {'1': 'Wild Card', '2': 'Divisional', '3': 'Conference', '5': 'Super Bowl'}}
REGULAR = {'nba': 4, 'wnba': 4, 'nfl': 4, 'ncaaf': 4, 'ncaab': 2}   # periods before OT


# ---------------------------------------------------------------- markets
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _ml(o):
    ml = o.get('ml') or {}
    return _num(ml.get('away')) and _num(ml.get('home'))


def home_ml(g, x, o):
    return {'L': 'a', 'W': 'b', 'T': 't'}.get(x.get('su'))


def fav_ml(g, x, o):
    fav, r = guide_stats.favorite(o), x.get('su')
    if not fav or r not in ('W', 'L', 'T'):
        return None
    return 't' if r == 'T' else 'a' if (r == 'W') == (fav == 'away') else 'b'


def home_ats(g, x, o):
    return {'L': 'a', 'W': 'b', 'P': 't'}.get(x.get('ats'))


def fav_ats(g, x, o):
    r = x.get('ats')
    fav = guide_stats.favorite(o) if r in ('W', 'L', 'P') else None
    if not fav:
        return None
    return 't' if r == 'P' else 'a' if (r == 'W') == (fav == 'away') else 'b'


def over(g, x, o):
    return {'O': 'a', 'U': 'b', 'P': 't'}.get(x.get('tot'))


def btts(g, x, o):
    return {'Y': 'a', 'N': 'b'}.get(x.get('btts'))


def nrfi(g, x, o):
    return {'N': 'a', 'Y': 'b'}.get(x.get('rfi'))


def ties(g, x, o):
    return ('a' if x.get('su') == 'T' else 'b') if x.get('su') in ('W', 'L', 'T') else None


def goals_over(n):
    def f(g, x, o):
        sc = x.get('sc')
        return ('a' if sc[0] + sc[1] > n else 'b') if sc and None not in sc[:2] else None
    return f


def went_ot(sport):
    def f(g, x, o):
        if x.get('su') not in ('W', 'L', 'T'):
            return None
        if sport == 'nhl':
            return 'a' if g.get('ot') else 'b'
        return 'a' if max(len(g.get('als') or []), len(g.get('hls') or [])) > REGULAR[sport] else 'b'
    return f


# line(o): the game has a line for the market (None: the market never has one)
LINES = {
    'home_ml': _ml, 'fav_ml': _ml, 'win': None, 'ties': None, 'ot': None, 'o05': None, 'o15': None,
    'home_ats': lambda o: bool(o.get('ats')), 'fav_ats': lambda o: bool(o.get('ats')),
    'pl': lambda o: bool(o.get('ats')), 'rl': lambda o: bool(o.get('ats')),
    'ou': lambda o: bool(o.get('total')),
    'btts': lambda o: _num((o.get('btts') or {}).get('yes')) or _num((o.get('btts') or {}).get('no')),
    'nrfi': lambda o: _num((o.get('nrfi_yrfi') or {}).get('nrfi')) or _num((o.get('nrfi_yrfi') or {}).get('yrfi')),
}


class Market:
    def __init__(self, mid, label, a, b, ta, tb, outcome):
        self.id, self.label, self.a, self.b, self.ta, self.tb, self.outcome = mid, label, a, b, ta, tb, outcome
        self.line = LINES[mid]

    def out(self):
        return {'id': self.id, 'label': self.label, 'a': self.a, 'b': self.b, 'ta': self.ta, 'tb': self.tb}


def M_HOME_ML():
    return Market('home_ml', 'ML Home / Away', 'Home', 'Away', 'win', 'dim', home_ml)


def M_FAV_ML():
    return Market('fav_ml', 'ML Fav / Dog', 'Fav', 'Dog', 'win', 'dim', fav_ml)


def M_OU(label='O/U'):
    return Market('ou', label, 'Over', 'Under', 'warm', 'cool', over)


def M_TIES():
    return Market('ties', 'Ties', 'Tie', 'No tie', 'win', 'dim', ties)


def segments(sp):
    """[(seg key, pill label, Full Run?, [Market])]: the first segments, then
    the Full Run's."""
    key = sp['key']
    if key == 'nhl':
        def period(k):
            return [Market('win', 'Winner Home / Away', 'Home', 'Away', 'win', 'dim', home_ml),
                    Market('o05', 'Over 0.5', 'Over', 'Under', 'warm', 'cool', goals_over(0.5)),
                    Market('o15', 'Over 1.5', 'Over', 'Under', 'warm', 'cool', goals_over(1.5)), M_TIES()]
        return [('1p', '1st Period', False, [M_HOME_ML(), M_FAV_ML(), M_OU('O/U 1.5'),
                                             Market('btts', 'BTTS', 'Yes', 'No', 'warm', 'cool', btts), M_TIES()]),
                ('2p', '2nd Period', True, period('2p')), ('3p', '3rd Period', True, period('3p')),
                ('game', 'Full Game', True, [M_HOME_ML(), M_FAV_ML(), Market('pl', 'Puck Line', 'Fav', 'Dog', 'win', 'dim', fav_ats),
                                             M_OU(), Market('ot', 'OT / SO', 'OT / SO', 'Regulation', 'win', 'dim', went_ot(key))])]
    if key == 'mlb':
        return [('1i', '1st Inning', False, [Market('nrfi', 'NRFI / YRFI', 'NRFI', 'YRFI', 'cool', 'warm', nrfi)]),
                ('f5', 'First 5', False, [M_HOME_ML(), M_FAV_ML(), Market('rl', 'Run Line', 'Fav', 'Dog', 'win', 'dim', fav_ats),
                                          M_OU(), M_TIES()]),
                ('game', 'Full Game', True, [M_HOME_ML(), M_FAV_ML(), Market('rl', 'Run Line', 'Fav', 'Dog', 'win', 'dim', fav_ats), M_OU()])]
    out = []
    for seg, fr in [(s, False) for s in sp['segments']] + [(s, True) for s in sp.get('full_run') or []]:
        last = seg['key'] == 'game'
        ms = [Market('home_ats', 'Spread Home / Away', 'Home', 'Away', 'win', 'dim', home_ats),
              Market('fav_ats', 'Spread Fav / Dog', 'Fav', 'Dog', 'win', 'dim', fav_ats),
              M_OU(), M_HOME_ML(), M_FAV_ML(),
              Market('ot', 'OT', 'OT', 'Regulation', 'win', 'dim', went_ot(key)) if last else M_TIES()]
        out.append((seg['key'], seg['label'], fr, ms))
    return out


# ------------------------------------------------------------------ seasons
def _read(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def docs(sp):
    """[(doc, current?)]: the season data.json holds (NHL: sport.json), then
    last season's (history.json; NHL: history-games.json), each with games
    {day: [game]}."""
    d = os.path.join(ROOT, sp['slug'])
    cur = _read(os.path.join(d, 'sport.json' if sp['key'] == 'nhl' else 'data.json'))
    info = cur.get('history') or {}
    prev = _read(os.path.join(d, info.get('file') or 'history.json'))
    out = [(cur, True)] if cur.get('games') else []
    if isinstance(prev.get('games'), dict) and prev['games']:
        out.append((prev, False))
    return out


def seg_of(g, k):
    """(result, odds) of a segment: the first segments' res / odds, the Full
    Run's fr / fo."""
    x = (g.get('res') or {}).get(k) or (g.get('fr') or {}).get(k)
    o = (g.get('odds') or {}).get(k) or (g.get('fo') or {}).get(k) or {}
    return x, o


def finals(doc, sp):
    """[(day, game)] of the season's finished games (college: Division I /
    FBS on both sides)."""
    league = doc.get('teams') or {}
    out = []
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            if g.get('state') != 'final' or not (g.get('res') or g.get('fr')):
                continue
            if sp['key'] in sports.COLLEGE and league and not (g.get('away') in league and g.get('home') in league):
                continue
            out.append((d, g))
    return out


def football_weeks(sp, doc, games):
    """[[key, label, [days]]] in order: the season's game weeks (the games'
    wk and data.json's weeks; last season's from its raw games file, else
    Tuesday-Monday game weeks by date)."""
    labels = {w['key']: w.get('label') or w['key'] for w in doc.get('weeks') or []}
    wk_of = {}
    if any(not g.get('wk') for _, g in games):
        raw = _read(os.path.join(ROOT, 'data_seed', 'games', sp['key'], f"{doc.get('season')}.json"))
        rows = [r for r in (raw.get('games') or {}).values() if r.get('season_type') in (2, 3) and r.get('week')]
        for w in sport_build.week_list(rows):
            labels.setdefault(w['key'], w['label'])
        wk_of = {str(r['id']): sport_build.week_key(r) for r in rows}
    order, n = {}, 0
    for d, g in games:
        k = g.get('wk') or wk_of.get(str(g.get('id')))
        if not k:   # no ESPN week: the Tuesday-Monday game week
            day = date.fromisoformat(d)
            tue = (day - timedelta(days=(day.weekday() - 1) % 7)).isoformat()
            k = ('3-' if g.get('post') else '2-') + tue
            if k not in labels:
                n += 0 if g.get('post') else 1
                labels[k] = 'Postseason' if g.get('post') else f'Week {n}'
        order.setdefault(k, set()).add(d)

    def sort_key(k):
        a, _, b = k.partition('-')
        return (int(a) if a.isdigit() else 0, int(b) if b.isdigit() else 0, b)
    def label(k):
        a, _, b = k.partition('-')
        return labels.get(k) or (f'Week {b}' if a == '2' else POST_WEEKS.get(sp['key'], {}).get(b, 'Postseason'))
    return [[k, label(k), sorted(order[k])] for k in sorted(order, key=sort_key)]


def season_counts(sp, doc, games):
    """{seg: {market id: {ro, d: {day: [a, b, t]}}}}."""
    out = {}
    for k, _, _, ms in segments(sp):
        for m in ms:
            lined = m.line is not None and any(m.line(seg_of(g, k)[1]) for _, g in games if seg_of(g, k)[0])
            days = {}
            for d, g in games:
                x, o = seg_of(g, k)
                if not x or (lined and not m.line(o)):
                    continue
                r = m.outcome(g, x, o)
                if r:
                    c = days.setdefault(d, [0, 0, 0])
                    c['abt'.index(r) if r != 't' else 2] += 1
            out.setdefault(k, {})[m.id] = {'ro': 0 if lined else 1, 'd': days}
    return out


def build(sp):
    """The due.json document."""
    seasons = []
    for doc, cur in docs(sp):
        games = finals(doc, sp)
        if not games:
            continue
        s = {'label': str(doc.get('seasonLabel') or doc.get('season') or ''), 'cur': cur and sports.in_season(sp),
             'post': sorted({d for d, g in games if g.get('post')}), 'first': games[0][0], 'last': games[-1][0],
             'c': season_counts(sp, doc, games)}
        if sp.get('schedule') == 'week':
            s['weeks'] = football_weeks(sp, doc, games)
        seasons.append(s)
    return {'sport': sp['key'], 'weekly': sp.get('schedule') == 'week',
            'matchups': sports.section_path(sp, 'games').lstrip('/'), 'regular': REGULAR.get(sp['key']),
            'segs': [{'k': k, 'label': lab, 'fr': 1 if fr else 0, 'm': [m.out() for m in ms]} for k, lab, fr, ms in segments(sp)],
            'seasons': seasons}


def write_data(sp):
    doc = build(sp)
    sport_build.write_json(os.path.join(ROOT, sp['slug'], 'due.json'), doc)
    return doc


# ------------------------------------------------------------------ the page
SEASON_WORDS = {12: 'winter', 1: 'winter', 2: 'winter', 3: 'spring', 4: 'spring', 5: 'spring',
                6: 'summer', 7: 'summer', 8: 'summer', 9: 'fall', 10: 'fall', 11: 'fall'}


def off_note(sp, doc, today):
    """"MLB is in the off-season. Showing the 2026 season (final). Opening
    Day: Thu, Mar 26, 2027", or '' in season."""
    if sports.in_season(sp, today):
        return ''
    final = next((s for s in doc['seasons'] if not s['cur']), None)
    if not final:
        return ''
    opening = ((sports.SETTINGS.get('seasons') or {}).get(sp['key']) or {}).get('OPENING_DAY') or ''
    try:
        d = date.fromisoformat(opening)
        nxt = f"Opening Day: {d.strftime('%a, %b')} {d.day}, {d.year}" if d >= today else ''
    except ValueError:
        nxt = ''
    if not nxt:
        m = sp['season_start']
        year = today.year if m > today.month else today.year + 1
        nxt = f"Next season: {SEASON_WORDS[m]} {year}"
    return f"{sp['label']} is in the off-season. Showing the {final['label']} season (final). {nxt}"


def page_body(sp, today, now=None, root='__ROOT__/'):
    """The off-season note bar, then the app assets/sport.js draws (renderDue)."""
    doc = write_data(sp)
    note = off_note(sp, doc, today)
    bar = f'<div class="df2-off" role="note">{esc(note)}</div>' if note else ''
    return (bar + '<div id="sportApp" data-section="due"><div class="no-games-note">Loading&hellip;</div>'
            '<noscript>This page needs JavaScript.</noscript></div>')


def page_meta(sp):
    h1 = f'{sports.seo_name(sp)} Due Factor'
    return {'title': f'{h1}: {sports.seg_words(sp)} Hot and Cold Trends | Run To Your Bets', 'h1': esc(h1), 'section': 'due',
            'desc': esc(f'{sp["label"]} {sports.segment_summary(sp)} markets running hot or cold against their season rate, day by day and week by week.')}


# --------------------------------------------------------- home / hub strip
# Off (sports.DUE_STRIP False): nothing calls strip(). On: the biggest gap
# per in-season sport among its first segments' markets, Daily (football:
# the last 3 weeks) against the season, 10+ points over MIN_GAMES+ games.
def _sum(days, keys):
    a = b = 0
    for d in keys:
        c = days.get(d)
        if c:
            a, b = a + c[0], b + c[1]
    return a, b


def strip_item(sp, today):
    if not sports.in_season(sp, today):
        return None
    doc = _read(os.path.join(ROOT, sp['slug'], 'due.json')) or build(sp)
    s = next((x for x in doc.get('seasons') or [] if x.get('cur')), None)
    if not s:
        return None
    if doc.get('weekly'):
        keys = [d for w in (s.get('weeks') or [])[-3:] for d in w[2]]
    else:
        keys = [(today - timedelta(days=i)).isoformat() for i in range(7)]
    best = None
    for seg in doc['segs']:
        if seg['fr']:
            continue
        for m in seg['m']:
            days = s['c'][seg['k']][m['id']]['d']
            wa, wb = _sum(days, keys)
            sa, sb = _sum(days, days.keys())
            if wa + wb < MIN_GAMES or not sa + sb:
                continue
            gap = round(100 * (wa / (wa + wb) - sa / (sa + sb)))
            if best is None or abs(gap) > abs(best[2]):
                best = (seg, m, gap)
    if not best or abs(best[2]) < STRIP_MIN:
        return None
    seg, m, gap = best
    return f"{sp['label']} {seg['label']} {m['a']} {'+' if gap > 0 else ''}{gap}", gap, sports.section_path(sp, 'due').lstrip('/')


def strip(S, today, root):
    """"Due Factor today" (sports.DUE_STRIP): the biggest gap per in-season
    sport (10+ only); '' when off or none."""
    if not sports.DUE_STRIP:
        return ''
    items = []
    for sport in S.values():
        it = strip_item(sport.sp, today)
        if it:
            text, gap, href = it
            items.append(f'<a class="df-strip-item" href="{root}{href}">{icon_of(sport.sp)}<span class="nw">{esc(text)}</span></a>')
    if not items:
        return ''
    return (f'<section class="fr-sec df-strip"><div class="fr-head"><h2>Due Factor today</h2></div>'
            f'<div class="df-strip-row">{"".join(items)}</div></section>')


def icon_of(sp):
    import icons
    return icons.sport_icon(sp)
