"""
The Betting Guides' live numbers: in a content/betting-guides/*.md body,
{{sport.segment.stat:window}} becomes the current value at build time and
{{asof}} today's date in New York ("Thursday, Nov 19"). An unknown token
stops the build with the file and the token.

The counts come from the games the Trends and Stats pages read (NHL:
nhl/sport.json; the rest: {slug}/data.json), college games between two
Division I (FBS) teams only:

  over      the segment total's Over (O-U), pushes left out
  fav_ats   the segment favorite covering the segment spread (W-L)
  home_ml   the home team winning the segment, 2-way (W-L), ties left out
  btts_yes  both teams scoring in the period (Y-N)
  tie       segments that ended tied ("34% (117 of 346)")
  nrfi      first innings with no run ("49% (1,200 of 2,429)")
  top_score the most common period score ("1-0 (27%)")
  goal_share the period's share of all goals ("29%"; no shootout goals)

Windows: season, week and lastweek. Daily sports' week is Monday-Sunday in
New York so far, lastweek the Monday-Sunday before it; NFL and NCAAF use
this game week and the one before. An off-season sport shows the last full
season's final value in every window.

Empty numbers (a window with fewer than MIN_GAMES games) never show:
{{sport.segment.stat:window|label}} writes "label value" and drops the
label with an empty value ("{{nba.1q.over:week|; this week}}"); a list
item or sentence with an empty season value is dropped; any other empty
value shows the site's empty-value dash.
"""
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')
MIN_GAMES = 10
EMPTY = '-'
WINDOWS = ('season', 'week', 'lastweek')

# {sport: {segment: (stat, ...)}}: every token the guides may use
STATS = {
    'nhl': {'1p': ('over', 'btts_yes', 'tie', 'home_ml', 'top_score', 'goal_share')},
    'mlb': {'1i': ('nrfi',), 'f5': ('home_ml', 'tie', 'over')},
    'nba': {'1q': ('over', 'fav_ats', 'home_ml'), '1h': ('over', 'fav_ats')},
    'wnba': {'1q': ('over', 'fav_ats', 'home_ml'), '1h': ('over', 'fav_ats')},
    'ncaab': {'1h': ('over', 'fav_ats', 'home_ml')},
    'nfl': {'1q': ('over', 'fav_ats'), '1h': ('over', 'fav_ats', 'home_ml')},
    'ncaaf': {'1q': ('over', 'fav_ats'), '1h': ('over', 'fav_ats')},
}


class UnknownToken(ValueError):
    pass


def today_et():
    return datetime.now(ZoneInfo('America/New_York')).date()


def asof(day):
    """"Thursday, Nov 19"."""
    return f"{day.strftime('%A, %b')} {day.day}"


def num(n):
    return f'{n:,}'


def rate(w, l):
    """"59% (204-142)"."""
    return f'{round(100 * w / (w + l))}% ({num(w)}-{num(l)})'


def share(k, n):
    """"34% (117 of 346)"."""
    return f'{round(100 * k / n)}% ({num(k)} of {num(n)})'


def favorite(odds_seg):
    """'away' / 'home': the shorter moneyline, else the side laying points
    (the Stats page's rule, sport_build.favorite)."""
    ml = (odds_seg or {}).get('ml') or {}
    a, h = ml.get('away'), ml.get('home')
    if isinstance(a, (int, float)) and isinstance(h, (int, float)):
        ia = -a / (-a + 100) if a < 0 else 100 / (a + 100)
        ih = -h / (-h + 100) if h < 0 else 100 / (h + 100)
        if ia != ih:
            return 'away' if ia > ih else 'home'
    line = (((odds_seg or {}).get('ats') or {}).get('away') or {}).get('line')
    if isinstance(line, (int, float)) and line != 0:
        return 'away' if line < 0 else 'home'
    return None


FLIP = {'W': 'L', 'L': 'W'}


def value(stat, rows, seg):
    """The token's text for (game, segment result) rows, or EMPTY."""
    if stat == 'over':
        r = Counter(x.get('tot') for _, x in rows)
        return rate(r['O'], r['U']) if r['O'] + r['U'] >= MIN_GAMES else EMPTY
    if stat == 'btts_yes':
        r = Counter(x.get('btts') for _, x in rows)
        return rate(r['Y'], r['N']) if r['Y'] + r['N'] >= MIN_GAMES else EMPTY
    if stat == 'home_ml':
        r = Counter(FLIP.get(x.get('su')) for _, x in rows)
        return rate(r['W'], r['L']) if r['W'] + r['L'] >= MIN_GAMES else EMPTY
    if stat == 'fav_ats':
        r = Counter()
        for g, x in rows:
            fav = favorite((g.get('odds') or {}).get(seg))
            if fav and x.get('ats') in FLIP:
                r[x['ats'] if fav == 'away' else FLIP[x['ats']]] += 1
        return rate(r['W'], r['L']) if r['W'] + r['L'] >= MIN_GAMES else EMPTY
    if stat == 'tie':
        n = [x.get('su') for _, x in rows if x.get('su') in ('W', 'L', 'T')]
        return share(n.count('T'), len(n)) if len(n) >= MIN_GAMES else EMPTY
    if stat == 'nrfi':
        n = [x.get('rfi') for _, x in rows if x.get('rfi') in ('Y', 'N')]
        return share(n.count('N'), len(n)) if len(n) >= MIN_GAMES else EMPTY
    if stat == 'top_score':
        n = Counter('-'.join(str(v) for v in sorted(x['sc'], reverse=True)) for _, x in rows)
        if sum(n.values()) < MIN_GAMES:
            return EMPTY
        score, k = n.most_common(1)[0]
        return f'{score} ({round(100 * k / sum(n.values()))}%)'
    if stat == 'goal_share':
        seg = total = 0
        for g, x in rows:
            if isinstance(g.get('as'), int) and isinstance(g.get('hs'), int):
                seg += sum(x['sc'])
                total += g['as'] + g['hs'] - (g.get('ot') == 'SO')
        return f'{round(100 * seg / total)}%' if len(rows) >= MIN_GAMES and total else EMPTY
    raise KeyError(stat)


def load(sp):
    """The sport's games doc: the current season's when it has finished
    games, else the last season's (history.json)."""
    names = ['sport.json'] if sp['key'] == 'nhl' else ['data.json']
    for name in names + ['history.json']:
        path = os.path.join(ROOT, sp['slug'], name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            doc = json.load(f)
        if any(g.get('res') for gs in (doc.get('games') or {}).values() for g in gs):
            return doc
    return {}


def finals(doc, sport_key):
    """[(day, game)] with a graded segment (as the Stats page counts them,
    live games included), oldest first; college: Division I (FBS) only."""
    league = doc.get('teams') or {}
    out = []
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            if not g.get('res'):
                continue
            if sport_key in sports.COLLEGE and league and not (g.get('away') in league and g.get('home') in league):
                continue
            out.append((d, g))
    return out


def windows(doc, games, today):
    """{window: [(day, game)]} for an in-season sport."""
    if doc.get('schedule') == 'week':
        keys = [w['key'] for w in doc.get('weeks') or []]
        cur = next((w['key'] for w in doc.get('weeks') or []
                    if any(g.get('wk') == w['key'] and g.get('state') in ('pre', 'in')
                           for gs in doc['games'].values() for g in gs)), keys[-1] if keys else None)
        i = keys.index(cur) if cur in keys else -1
        prev = keys[i - 1] if i > 0 else None
        return {'season': games,
                'week': [x for x in games if x[1].get('wk') == cur],
                'lastweek': [x for x in games if prev and x[1].get('wk') == prev]}
    mon = today - timedelta(days=today.weekday())
    a, b = mon.isoformat(), (mon - timedelta(days=7)).isoformat()
    return {'season': games,
            'week': [x for x in games if a <= x[0] <= today.isoformat()],
            'lastweek': [x for x in games if b <= x[0] < a]}


def table(today=None):
    """{'nhl.1p.over:season': '59% (204-142)', ..., 'asof': 'Thursday, Nov 19'}."""
    today = today or today_et()
    out = {'asof': asof(today)}
    for key, segs in STATS.items():
        sp = sports.BY_KEY[key]
        doc = load(sp)
        games = finals(doc, key)
        off = not sports.in_season(sp, today)
        wins = {w: games for w in WINDOWS} if off else windows(doc, games, today)
        for seg, stats in segs.items():
            for stat in stats:
                for w in WINDOWS:
                    rows = [(g, (g.get('res') or {}).get(seg)) for _, g in wins[w]]
                    rows = [(g, x) for g, x in rows if x and x.get('sc') and not x.get('na')]
                    v = value(stat, rows, seg)
                    out[f'{key}.{seg}.{stat}:{w}'] = v
    return out


DROP = '\x00'   # an empty season value: its list item or sentence goes


def fill(text, values, name):
    """text with every token replaced; an unknown one raises UnknownToken
    naming the file and the token. Empty numbers drop out (see above)."""
    def sub(m):
        tok, _, label = m.group(1).partition('|')
        tok = tok.strip()
        if tok not in values:
            raise UnknownToken(f'{name}: unknown token {{{{{m.group(1)}}}}}')
        v = values[tok]
        if v != EMPTY:
            return f'{label.strip()} {v}' if label else v
        if label:
            return ''
        return DROP if tok.endswith(':season') else EMPTY

    def line(ln):
        if DROP not in ln:
            return ln
        if re.match(r'\s*[-*]\s', ln):
            return None
        return ' '.join(x for x in re.split(r'(?<=[.!?])\s+', ln) if DROP not in x)
    out = [line(ln) for ln in TOKEN.sub(sub, text).split('\n')]
    return '\n'.join(ln for ln in out if ln is not None)


def key(tok):
    """The value's key for a token ("nba.1q.over:week|; this week" -> "nba.1q.over:week")."""
    return tok.partition('|')[0].strip()


if __name__ == '__main__':
    for k, v in table().items():
        print(f'{k:32} {v}')
