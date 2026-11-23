"""
Due Factor (/{sport}/due-factor/): the league's first segments, hot or cold
against their own season rate. Static HTML, rebuilt with every refresh.

Each market is measured on one side:
  NHL 1P             Total 1.5 (Over), Winner (Home, ties out), BTTS (Yes),
                     Favorite (Fav, ties out), Ties (tied periods)
  spread sports      per segment: Spread (Home ATS), Spread (Favorite ATS),
                     Total (Over), ML (Home, ties out)
  MLB                NRFI (the YRFI rate), F5 Total (Over), F5 ML (Home),
                     F5 Run Line (Favorite)

The games are the Stats pages' (guide_stats.load / finals: college between
two Division I / FBS teams), regular season only, and only games with a line
for the market (CLAUDE.md). Pushes are out of every rate; ML ties are out of
the Winner / Favorite rates and counted on the Ties row. The favorite is the
Stats page's (the shorter segment moneyline, else the side laying points).

Windows: Daily = game days in the last 7 days (ET), or the last 7 game days
when there were none; Weekly = this week so far (the latest week with
games), Monday-Sunday ET for the daily sports, the game week for NCAAF;
NFL's weekly meters take its last 3 weeks (16 games a week is too few;
WEEKLY_SPAN). The Week by week table is a row per week everywhere.
Off-season sports show last season's final days and weeks. Day by day is
a row per game day of the meter's window, so its total row is the meter.

The gap is the window's rate minus the season's, in points. Chip: under 5
"On pace"; 5-9 "Leaning cold" (--heat-1) / "Leaning hot" (--heat-2); 10+
"Cold" / "Hot" (--heat-3; 15+ --heat-4). Under MIN_GAMES graded games in
the window there's no chip ("Small sample"), no strip entry and no Tonight. A table cell is tinted when the
side it shows is 10+ points above its season rate: side markets the win
fill, Over / Yes / YRFI warm; a total whose Under is 10+ above shows cool.
"""
import os
from datetime import date, timedelta

import bignums
import front
import guide_stats
import sports
from front import esc

WINDOW_DAYS = 7
TINT = 10        # points above the season rate that tint a cell
STRIP_MIN = 10   # the home / hub strip: only gaps this big
MIN_GAMES = 15   # fewer graded games in the window: "Small sample", no strip entry or Tonight
WEEKLY_SPAN = {'nfl': 3}   # weekly meters over the last N weeks (the rest: the latest week)


# ---------------------------------------------------------------- markets
class Market:
    """One market and the side it's measured on. outcome(g, x) returns
    's' (the side), 'o' (the other side), 't' (a tie / push: out of the
    rate) or None (no line, not graded)."""

    def __init__(self, mid, seg, tag, label, side, other, letters, kind, outcome, book):
        self.id, self.seg, self.tag, self.label = mid, seg, tag, label
        self.side, self.other = side, other
        self.letters = letters      # (side, other, tie) for "H 1 · A 3 · T 1"
        self.kind = kind            # 'total' (warm / cool) or 'side' (the win fill)
        self.outcome = outcome
        self.book = book            # (books market, side key, mirror key) for Tonight; None: no price

    @property
    def rec(self):
        return f'{self.letters[0]}-{self.letters[1]}'


def _odds(g, k):
    return (g.get('odds') or {}).get(k) or {}


def _has_ml(g, k):
    ml = _odds(g, k).get('ml') or {}
    return isinstance(ml.get('away'), (int, float)) and isinstance(ml.get('home'), (int, float))


def _over(k):
    return lambda g, x: {'O': 's', 'U': 'o', 'P': 't'}.get(x.get('tot'))


def _btts(k):
    def f(g, x):
        b = _odds(g, k).get('btts') or {}
        if not (isinstance(b.get('yes'), (int, float)) or isinstance(b.get('no'), (int, float))):
            return None
        return {'Y': 's', 'N': 'o'}.get(x.get('btts'))
    return f


def _home_ml(k):
    return lambda g, x: {'L': 's', 'W': 'o', 'T': 't'}.get(x.get('su')) if _has_ml(g, k) else None


def _fav_ml(k):
    def f(g, x):
        fav = guide_stats.favorite(_odds(g, k)) if _has_ml(g, k) else None
        r = x.get('su')
        if not fav or r not in ('W', 'L', 'T'):
            return None
        return 't' if r == 'T' else 's' if (r == 'W') == (fav == 'away') else 'o'
    return f


def _ties(k):
    return lambda g, x: ('s' if x.get('su') == 'T' else 'o') if _has_ml(g, k) and x.get('su') in ('W', 'L', 'T') else None


def _home_ats(k):
    return lambda g, x: {'L': 's', 'W': 'o', 'P': 't'}.get(x.get('ats'))


def _fav_ats(k):
    def f(g, x):
        r = x.get('ats')
        fav = guide_stats.favorite(_odds(g, k)) if r in ('W', 'L', 'P') else None
        if not fav:
            return None
        return 't' if r == 'P' else 's' if (r == 'W') == (fav == 'away') else 'o'
    return f


def _yrfi(k):
    def f(g, x):
        m = _odds(g, k).get('nrfi_yrfi') or {}
        if not (isinstance(m.get('yrfi'), (int, float)) or isinstance(m.get('nrfi'), (int, float))):
            return None
        return {'Y': 's', 'N': 'o'}.get(x.get('rfi'))
    return f


def groups(sp):
    """[(group key, pill label, [Market])]: one pane per segment pill (NHL
    and MLB: one pane)."""
    key = sp['key']
    if key == 'nhl':
        k = '1p'
        return [(k, '1st Period', [
            Market('over', k, '1P', 'Total 1.5', 'Over', 'Under', ('O', 'U', 'P'), 'total', _over(k), ('total', 'over', 'under')),
            Market('home', k, '1P', 'Winner', 'Home', 'Away', ('H', 'A', 'T'), 'side', _home_ml(k), ('ml', 'home', 'away')),
            Market('btts', k, '1P', 'BTTS', 'Yes', 'No', ('Y', 'N', ''), 'total', _btts(k), ('btts', 'yes', 'no')),
            Market('fav', k, '1P', 'Favorite', 'Fav', 'Dog', ('F', 'D', 'T'), 'side', _fav_ml(k), ('ml', 'fav', 'dog')),
            Market('ties', k, '1P', 'Ties', 'Tie', 'No tie', ('T', 'N', ''), 'side', _ties(k), None),
        ])]
    if key == 'mlb':
        return [('mlb', 'First Inning & First Five', [
            Market('yrfi', '1i', '1st Inn', 'NRFI', 'YRFI', 'NRFI', ('Y', 'N', ''), 'total', _yrfi('1i'), ('rfi', 'yrfi', 'nrfi')),
            Market('over', 'f5', 'F5', 'F5 Total', 'Over', 'Under', ('O', 'U', 'P'), 'total', _over('f5'), ('total', 'over', 'under')),
            Market('home', 'f5', 'F5', 'F5 ML', 'Home', 'Away', ('H', 'A', 'T'), 'side', _home_ml('f5'), ('ml', 'home', 'away')),
            Market('fav', 'f5', 'F5', 'F5 Run Line', 'Fav', 'Dog', ('F', 'D', 'P'), 'side', _fav_ats('f5'), ('ats', 'fav', 'dog')),
        ])]
    out = []
    for seg in sp['segments']:
        k, t = seg['key'], seg['tag']
        out.append((k, seg['label'], [
            Market('home_ats', k, t, 'Spread', 'Home ATS', 'Away ATS', ('H', 'A', 'P'), 'side', _home_ats(k), ('ats', 'home', 'away')),
            Market('fav_ats', k, t, 'Spread', 'Favorite ATS', 'Dog ATS', ('F', 'D', 'P'), 'side', _fav_ats(k), ('ats', 'fav', 'dog')),
            Market('over', k, t, 'Total', 'Over', 'Under', ('O', 'U', 'P'), 'total', _over(k), ('total', 'over', 'under')),
            Market('home', k, t, 'ML', 'Home', 'Away', ('H', 'A', 'T'), 'side', _home_ml(k), ('ml', 'home', 'away')),
        ]))
    return out


# ------------------------------------------------------------------ counts
class Count:
    def __init__(self):
        self.s = self.o = self.t = 0

    def add(self, r):
        if r:
            setattr(self, r, getattr(self, r) + 1)

    def __iadd__(self, other):
        self.s, self.o, self.t = self.s + other.s, self.o + other.o, self.t + other.t
        return self

    @property
    def n(self):
        return self.s + self.o

    @property
    def rate(self):
        return self.s / self.n if self.n else None


def season_games(sp):
    """(doc, [(day, game)]): the regular season's graded games, the season
    just played when the sport is between seasons."""
    doc = guide_stats.load(sp)
    return doc, [(d, g) for d, g in guide_stats.finals(doc, sp['key']) if not g.get('post')]


def by_day(markets, games):
    """{day: {market id: Count}} and {day: games played} (games with an
    outcome in any of the markets)."""
    days, gp = {}, {}
    for d, g in games:
        res = g.get('res') or {}
        hit = False
        for m in markets:
            x = res.get(m.seg)
            r = m.outcome(g, x) if x else None
            if r:
                days.setdefault(d, {}).setdefault(m.id, Count()).add(r)
                hit = True
        if hit:
            gp[d] = gp.get(d, 0) + 1
    return days, gp


def total(days, keys, mid):
    c = Count()
    for d in keys:
        if mid in days.get(d, {}):
            c += days[d][mid]
    return c


def window_days(game_days, today):
    """(days, label): game days in the last 7 days through today, else the
    last 7 game days."""
    start = (today - timedelta(days=WINDOW_DAYS - 1)).isoformat()
    recent = [d for d in game_days if start <= d <= today.isoformat()]
    if recent:
        return recent, 'last 7 days'
    return [d for d in game_days if d <= today.isoformat()][-WINDOW_DAYS:], 'last 7 game days'


def weeks_of(doc, sp, games, today):
    """[(key, label, [days])] oldest first: the game weeks (football: the
    regular season's, '2-*'), else Monday-Sunday ET weeks."""
    days = sorted({d for d, _ in games if d <= today.isoformat()})
    if sp.get('schedule') == 'week':
        wk_days = {}
        for d, g in games:
            if g.get('wk'):
                wk_days.setdefault(g['wk'], set()).add(d)
        return [(w['key'], w.get('label') or w['key'], sorted(wk_days[w['key']]))
                for w in doc.get('weeks') or [] if str(w.get('key', '')).startswith('2-') and w['key'] in wk_days]
    out = {}
    for d in days:
        mon = date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())
        out.setdefault(mon.isoformat(), []).append(d)
    return [(k, 'Week of ' + short_date(k), v) for k, v in sorted(out.items())]


def short_date(d):
    x = date.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}"


def day_name(d):
    x = date.fromisoformat(d)
    return f"{x.strftime('%a, %b')} {x.day}"


def pts(win, season):
    """The gap in points (the window's rate minus the season's)."""
    return None if win is None or season is None else round(100 * (win - season))


def chip(gap, n=None):
    """(text, heat class) for a gap of the measured side over n graded games."""
    if n is not None and n < MIN_GAMES:
        return 'Small sample', ''
    if gap is None or abs(gap) < 5:
        return 'On pace', ''
    if abs(gap) < 10:
        return ('Leaning hot', 'heat-2') if gap > 0 else ('Leaning cold', 'heat-1')
    return ('Hot' if gap > 0 else 'Cold'), ('heat-4' if abs(gap) >= 15 else 'heat-3')


def tint(m, c, season):
    """The cell's tint: the side it shows (the measured side's rate) 10+
    points above its season rate. Side markets: the win fill; totals: warm
    for Over / Yes / YRFI, cool when the Under / No / NRFI is 10+ above."""
    gap = pts(c.rate, season.rate)
    if gap is None:
        return ''
    if gap >= TINT:
        return 'df-warm' if m.kind == 'total' else 'df-win'
    if gap <= -TINT and m.kind == 'total':
        return 'df-cool'
    return ''


def meter(markets, days, keys, season_keys):
    """[(Market, window Count, season Count, gap)], the biggest gap first."""
    rows = []
    for m in markets:
        w, s = total(days, keys, m.id), total(days, season_keys, m.id)
        rows.append((m, w, s, pts(w.rate, s.rate)))
    return sorted(rows, key=lambda r: -abs(r[3]) if r[3] is not None else 1)


def compute(sp, today):
    """Everything the page and the strip draw, per group."""
    doc, games = season_games(sp)
    off = sp['key'] not in {x['key'] for x in sports.IN_SEASON}
    out = {'doc': doc, 'off': off, 'season': str(doc.get('seasonLabel') or doc.get('season') or ''), 'groups': []}
    for gk, glabel, markets in groups(sp):
        days, gp = by_day(markets, games)
        all_days = sorted(days)
        season_keys = all_days
        win, win_label = window_days(all_days, today)
        weeks = [(k, lab, [d for d in ds if d in days]) for k, lab, ds in weeks_of(doc, sp, games, today)]
        weeks = [w for w in weeks if w[2]]
        cur = weeks[-1] if weeks else None
        # football: the latest week still has games to play; the rest: this Monday's week
        if sp.get('schedule') == 'week':
            this_week = bool(cur) and not off and any(g.get('wk') == cur[0] and g.get('state') in ('pre', 'in')
                                                       for gs in (doc.get('games') or {}).values() for g in gs)
        else:
            this_week = bool(cur) and not off and cur[0] == (today - timedelta(days=today.weekday())).isoformat()
        span = WEEKLY_SPAN.get(sp['key'], 1)
        before = [d for d in all_days if d < today.isoformat()]
        last = before[-1] if before else (all_days[-1] if all_days else None)
        out['groups'].append({
            'key': gk, 'label': glabel, 'markets': markets, 'days': days, 'gp': gp, 'season_keys': season_keys,
            'win': win, 'win_label': win_label,
            'daily': meter(markets, days, win, season_keys),
            'weeks': weeks, 'week': cur, 'this_week': this_week,
            'weekly': meter(markets, days, [d for w in weeks[-span:] for d in w[2]], season_keys) if cur else [],
            'span': span, 'span_weeks': weeks[-span:],
            'last': last,
        })
    return out


_CACHE = {}


def data(sp, today):
    k = (sp['key'], today.isoformat())
    if k not in _CACHE:
        _CACHE[k] = compute(sp, today)
    return _CACHE[k]


# ---------------------------------------------------------------- Tonight
def _price(sport, d, g, m, side):
    """(line, best price, book) for one side of a market on today's game:
    the books' consensus line (spread: that side's), the best price at it;
    else the saved line."""
    bm = m.book[0]
    og = sport.odds_game(d, g)
    rows = bignums.books_of(sport, og, m.seg, bm)
    if rows:
        if bm == 'total':
            line = bignums.consensus([r.get('line') for r in rows.values() if isinstance(r.get('line'), (int, float))])
            got = bignums.best_at({b: r for b, r in rows.items() if r.get('line') == line}, side)
            return (line, got[0], got[1]) if got else None
        if bm == 'ats':
            line = bignums.consensus([x for x in (bignums.side_line(r, side) for r in rows.values()) if isinstance(x, (int, float))])
            got = bignums.best_at(rows, side, line, bignums.side_line)
            return (line, got[0], got[1]) if got else None
        got = bignums.best_at(rows, side)
        return (None, got[0], got[1]) if got else None
    o = _odds(g, m.seg)
    if bm == 'total' and o.get('total'):
        return o['total'].get('line'), o['total'].get(side), None
    if bm == 'ats' and (o.get('ats') or {}).get(side):
        return o['ats'][side].get('line'), o['ats'][side].get('price'), None
    if bm == 'ml' and o.get('ml'):
        return None, o['ml'].get(side), None
    if bm == 'btts' and o.get('btts'):
        return None, o['btts'].get(side), None
    if bm == 'rfi' and o.get('nrfi_yrfi'):
        return None, o['nrfi_yrfi'].get(side), None
    return None


def coldest(rows):
    """(Market, the cold side's label, its book side key, gap): the biggest
    gap's cold side (the measured side when it runs cold, else its mirror).
    Ties have no price on the Odds page's 2-way rows and stay out, and so
    does a market under MIN_GAMES games in the window."""
    rows = [r for r in rows if r[3] is not None and r[0].book and r[1].n >= MIN_GAMES]
    if not rows:
        return None
    m, _, _, gap = max(rows, key=lambda r: abs(r[3]))
    if gap <= 0:
        return m, m.side, m.book[1], gap
    return m, m.other, m.book[2], -gap


def tonight(sport, grp, today, now, root):
    """The coldest side on today's games still to start, best price and
    book, each linking to its game on the Odds page; '' with no games."""
    c = coldest(grp['daily'])
    if not c:
        return ''
    m, label, side_key, gap = c
    d = today.isoformat()
    todays = [g for g in sport.games(d) if front.game_lined(sport, g, m.seg) and not front.started(g, now)]
    rows = []
    for g in sorted(todays, key=lambda g: (g.get('start') or '', g['away'])):
        side = side_key
        if side_key in ('fav', 'dog'):
            fav = guide_stats.favorite(_odds(g, m.seg)) or front.seg_fav(g, m.seg)
            if not fav:
                continue
            side = fav if side_key == 'fav' else ('home' if fav == 'away' else 'away')
        got = _price(sport, d, g, m, side)
        if not got or not isinstance(got[1], (int, float)):
            continue
        line, price, book = got
        who = esc(sport.code(g[side])) if side in ('away', 'home') else esc(label)
        if m.book[0] == 'total':
            top = f'{"O" if side == "over" else "U"} {front.line_txt(line)}'
        elif m.book[0] == 'ats':
            top = f'{who} {front.signed(line)}'
        elif m.book[0] == 'ml':
            top = who
        else:
            top = esc(label)
        q = f"?week={g['wk']}" if sport.weekly and g.get('wk') else f'?date={d}'
        href = f"{root}{sport.odds_page}{q}&seg={m.seg}&mkt={m.book[0]}#og-{g['away']}-{g['home']}"
        rows.append(f'<a class="df-tn-row" href="{esc(href)}"><span class="df-tn-teams">{sport.badge(g["away"], 20, root)}'
                    f'<span>{esc(sport.code(g["away"]))}</span><span class="df-at">@</span>{sport.badge(g["home"], 20, root)}'
                    f'<span>{esc(sport.code(g["home"]))}</span></span><span class="df-tn-time">{esc(front.time_et(g.get("start")) if g.get("start") else "TBD")}</span>'
                    f'<span class="df-tn-bet">{front.cell(top, esc(front.price_txt(price)), front.book_html(sport, book, root))}</span></a>')
    if not rows:
        return ''
    return (f'<section class="st-sec"><div class="st-sec-head"><h2>Tonight</h2></div>'
            f'<p class="st-sec-sub">The coldest side: {esc(m.tag)} {esc(m.label)} {esc(label)}, {abs(gap)} pts under its season rate. Best price on today&rsquo;s games.</p>'
            f'<div class="st-card df-tn">{"".join(rows)}</div></section>')


# ------------------------------------------------------------------ the page
def pct_txt(r):
    return '-' if r is None else f'{round(100 * r)}%'


def rec_txt(m, c):
    if m.id == 'ties':
        return f'{c.s} of {c.n}'
    return f'{c.s}-{c.o} {m.rec}'


def meter_card(m, w, s, gap, when):
    text, heat = chip(gap, w.n)
    fill = 0 if w.rate is None else round(100 * w.rate)
    tick = None if s.rate is None else round(100 * s.rate)
    gap_txt = '-' if gap is None else f'{"+" if gap > 0 else ""}{gap} pts'
    return (f'<div class="st-card df-card"><div class="st-head"><h4>{esc(m.tag)} {esc(m.label)}</h4></div>'
            f'<div class="df-top"><span class="df-side">{esc(m.side)}</span><span class="df-chip{" " + heat if heat else ""}">{text}</span></div>'
            f'<p class="df-vs">{esc(when)} {pct_txt(w.rate)} vs season {pct_txt(s.rate)}</p>'
            f'<div class="df-bar" role="img" aria-label="{esc(when)} {pct_txt(w.rate)}, season {pct_txt(s.rate)}">'
            f'<span class="df-fill" style="width:{fill}%"></span>'
            + (f'<span class="df-tick" style="left:{tick}%"></span>' if tick is not None else '') + '</div>'
            f'<p class="df-gap"><span class="df-gap-n">{gap_txt}</span><span class="nw">{esc(rec_txt(m, w))}</span></p></div>')


def meter_html(rows, when):
    return '<div class="df-grid">' + ''.join(meter_card(m, w, s, gap, when) for m, w, s, gap in rows) + '</div>'


def counts_txt(m, c):
    """"H 1 · A 3 · T 1", "O 2 · U 3"."""
    if m.id == 'ties':
        return f'T {c.s} of {c.n}'
    parts = [f'{m.letters[0]} {c.s}', f'{m.letters[1]} {c.o}']
    if c.t and m.letters[2]:
        parts.append(f'{m.letters[2]} {c.t}')
    return ' · '.join(parts)


def last_night(grp):
    d = grp['last']
    if not d:
        return ''
    items = ''.join(f'<li><span class="df-ln-m">{esc(m.tag)} {esc(m.label)}: {esc(m.side)}</span><span class="df-ln-c nw">{esc(counts_txt(m, grp["days"][d].get(m.id) or Count()))}</span></li>'
                    for m in grp['markets'])
    return (f'<section class="st-sec"><div class="st-sec-head"><h2>Last night</h2></div><p class="st-sec-sub">{esc(day_name(d))} · {grp["gp"].get(d, 0)} games</p>'
            f'<div class="st-card"><ul class="df-ln">{items}</ul></div></section>')


def cell_html(m, c, season):
    if not c.n:
        return '<td class="df-c">-</td>'
    cls = tint(m, c, season)
    txt = f'{c.s} of {c.n}' if m.id == 'ties' else f'{c.s}-{c.o}'
    return f'<td class="df-c{" " + cls if cls else ""}"><span class="nw">{txt}</span> <span class="df-p">{pct_txt(c.rate)}</span></td>'


def table_html(grp, rows, total_label, total_keys, first_col):
    """rows: [(label, [days])], newest first, then the total row."""
    ms = grp['markets']
    season = {m.id: total(grp['days'], grp['season_keys'], m.id) for m in ms}
    head = (f'<tr><th scope="col">{first_col}</th><th scope="col">GP</th>'
            + ''.join(f'<th scope="col">{esc(m.tag)} {esc(m.side)}</th>' for m in ms) + '</tr>')

    def tr(label, keys, cls=''):
        gp = sum(grp['gp'].get(d, 0) for d in keys)
        return (f'<tr{" class=" + chr(34) + cls + chr(34) if cls else ""}><th scope="row">{esc(label)}</th><td class="df-c">{gp}</td>'
                + ''.join(cell_html(m, total(grp['days'], keys, m.id), season[m.id]) for m in ms) + '</tr>')

    body = ''.join(tr(lab, keys) for lab, keys in rows) + tr(total_label, total_keys, 'df-total')
    return f'<div class="st-card df-tcard"><div class="df-scroll"><table class="df-table"><thead>{head}</thead><tbody>{body}</tbody></table></div></div>'


def pane_html(sport, grp, data_, today, now, root, view):
    off_lab = f'{data_["season"]} season · ' if data_['off'] else ''
    if view == 'daily':
        when = grp['win_label'].capitalize()
        sub = f'{off_lab}{when}: {short_date(grp["win"][0])}-{short_date(grp["win"][-1])}' if grp['win'] else ''
        return (f'<section class="st-sec"><div class="st-sec-head"><h2>Due meter</h2></div><p class="st-sec-sub">{esc(sub)} vs the season rate</p>'
                + meter_html(grp['daily'], when) + '</section>'
                + last_night(grp)
                + f'<section class="st-sec"><div class="st-sec-head"><h2>Day by day</h2></div>'
                + f'<p class="st-sec-sub">A cell 10+ pts above its season rate is tinted.</p>'
                + table_html(grp, [(day_name(d), [d]) for d in reversed(grp['win'])], 'Last 7 days' if grp['win_label'] == 'last 7 days' else 'Last 7 game days', grp['win'], 'Day')
                + '</section>' + ('' if data_['off'] else tonight(sport, grp, today, now, root)))
    if not grp['week']:
        return '<p class="st-sec-sub">No games yet.</p>'
    wk = grp['week']
    when = 'This week so far' if grp['this_week'] else wk[1]
    sub = f'{when}{"" if when == wk[1] else " (" + wk[1] + ")"}'
    if grp['span'] > 1:
        when = f'Last {grp["span"]} weeks'
        sub = f'{when} ({span_txt(grp["span_weeks"])})'
    return (f'<section class="st-sec"><div class="st-sec-head"><h2>Due meter</h2></div><p class="st-sec-sub">{esc(off_lab + sub)} vs the season rate</p>'
            + meter_html(grp['weekly'], when) + '</section>'
            + f'<section class="st-sec"><div class="st-sec-head"><h2>Week by week</h2></div>'
            + f'<p class="st-sec-sub">A cell 10+ pts above its season rate is tinted.</p>'
            + table_html(grp, [(lab, ds) for _, lab, ds in reversed(grp['weeks'])], 'Season', grp['season_keys'], 'Week')
            + '</section>')


def span_txt(weeks):
    """"Weeks 9-11", else "Week 9 to Week 11"."""
    a, b = weeks[0][1], weeks[-1][1]
    if a == b:
        return a
    if a.startswith('Week ') and b.startswith('Week '):
        return f'Weeks {a[5:]}-{b[5:]}'
    return f'{a} to {b}'


TOGGLE_JS = """<script>
(function() {
  var app = document.getElementById('dueApp');
  if (!app) return;
  function show() {
    var v = app.getAttribute('data-view'), g = app.getAttribute('data-group');
    app.querySelectorAll('[data-pane]').forEach(function(p) {
      p.hidden = p.getAttribute('data-pane') !== g + ':' + v;
    });
    app.querySelectorAll('[data-view-btn]').forEach(function(b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-view-btn') === v)); });
    app.querySelectorAll('[data-group-btn]').forEach(function(b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-group-btn') === g)); });
  }
  app.addEventListener('click', function(e) {
    var b = e.target.closest('[data-view-btn],[data-group-btn]');
    if (!b) return;
    if (b.hasAttribute('data-view-btn')) app.setAttribute('data-view', b.getAttribute('data-view-btn'));
    else app.setAttribute('data-group', b.getAttribute('data-group-btn'));
    show();
  });
  var q = new URLSearchParams(location.search);
  if (q.get('view') === 'daily' || q.get('view') === 'weekly') app.setAttribute('data-view', q.get('view'));
  if (q.get('seg') && app.querySelector('[data-group-btn="' + q.get('seg') + '"]')) app.setAttribute('data-group', q.get('seg'));
  show();
})();
</script>"""


def page_body(sp, today, now, root='__ROOT__/'):
    """The page under the H1: Daily / Weekly, the segment pills, a pane per
    (segment, view). Football opens on Weekly."""
    sport = front.Sport(sp)
    d = data(sp, today)
    view = 'weekly' if sp.get('schedule') == 'week' else 'daily'
    gs = d['groups']
    if not any(g['days'] for g in gs):
        return '<p class="st-sec-sub">No games yet this season.</p>'
    ctrl = ('<div class="seg-toggle" role="group" aria-label="View">'
            + ''.join(f'<button class="seg-btn" type="button" data-view-btn="{v}" aria-pressed="{str(v == view).lower()}">{lab}</button>'
                      for v, lab in (('daily', 'Daily'), ('weekly', 'Weekly'))) + '</div>')
    if len(gs) > 1:
        ctrl += ('<div class="seg-toggle" role="group" aria-label="Segment">'
                 + ''.join(f'<button class="seg-btn" type="button" data-group-btn="{g["key"]}" aria-pressed="{str(i == 0).lower()}">{esc(g["label"])}</button>'
                           for i, g in enumerate(gs)) + '</div>')
    panes = ''.join(f'<div class="df-pane" data-pane="{g["key"]}:{v}"{"" if (i == 0 and v == view) else " hidden"}>{pane_html(sport, g, d, today, now, root, v)}</div>'
                    for i, g in enumerate(gs) for v in ('daily', 'weekly'))
    note = ('<p class="df-note">Each market against its own season rate. Running cold or hot is where the league sits now, '
            'not a sign that a side is about to hit.</p>')
    return (f'<div class="df-app" id="dueApp" data-view="{view}" data-group="{gs[0]["key"]}"><div class="df-ctrl">{ctrl}</div>{note}{panes}</div>'
            + TOGGLE_JS)


def page_meta(sp):
    h1 = f'{sports.seo_name(sp)} Due Factor'
    return {'title': f'{h1}: {sports.seg_words(sp)} Hot and Cold Trends | Run To Your Bets', 'h1': esc(h1), 'section': 'due',
            'desc': esc(f'{sp["label"]} {sports.segment_summary(sp)} markets running hot or cold against their season rate, day by day and week by week.')}


# --------------------------------------------------------- home / hub strip
def strip_item(sp, today):
    """(text, gap, href) for the sport's biggest gap in its default view, or
    None under STRIP_MIN (markets with MIN_GAMES+ games in the window)."""
    d = data(sp, today)
    if d['off']:
        return None
    view = 'weekly' if sp.get('schedule') == 'week' else 'daily'
    best = None
    for g in d['groups']:
        for m, w, s, gap in g[view]:
            if gap is not None and w.n >= MIN_GAMES and (best is None or abs(gap) > abs(best[1])):
                best = (m, gap)
    if not best or abs(best[1]) < STRIP_MIN:
        return None
    m, gap = best
    return f'{sp["label"]} {m.tag} {m.side} {"+" if gap > 0 else ""}{gap}', gap, sports.section_path(sp, 'due').lstrip('/')


def strip(S, today, root):
    """"Due Factor today": the biggest gap per sport (10+ only); '' when none."""
    items = []
    for sport in S.values():
        it = strip_item(sport.sp, today)
        if it:
            text, gap, href = it
            items.append(f'<a class="df-strip-item" href="{root}{href}">{icon_of(sport.sp)}<span class="nw">{esc(text)}</span>'
                         f'<span class="df-chip {chip(gap)[1]}">{chip(gap)[0]}</span></a>')
    if not items:
        return ''
    return (f'<section class="fr-sec df-strip"><div class="fr-head"><h2>Due Factor today</h2></div>'
            f'<div class="df-strip-row">{"".join(items)}</div></section>')


def icon_of(sp):
    import icons
    return icons.sport_icon(sp)
