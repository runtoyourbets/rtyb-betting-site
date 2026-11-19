"""
The Big Numbers: the most extreme lines on the board for each market, games
not started only (front.upcoming: today's, then the next game day's;
football: the rest of the week). Home (in Line Mover's old place, sport
pills), each hub, and the top of every sport's Odds page.

Rows per sport and segment:
  spread sports   SPREAD (largest favorite), MONEYLINE (shortest favorite
                  price), TOTAL (highest total)
  NHL (1P)        1P MONEYLINE (biggest favorite), 1P OVER 1.5 (the most
                  expensive Over price), 1P 3-WAY (biggest team favorite,
                  never the tie), 1P TIE (shortest tie price)
  MLB             1st inning and First 5, the same three rows where the
                  markets exist

The line is the consensus across the sportsbooks (the line most books
hang); the price shown is the best one at that line, with its book's logo.
Ties: spread -> the more expensive favorite price, then the earlier start;
moneyline -> the earlier start; total -> the higher Over price, then the
earlier start.
"""
import json
from datetime import timedelta
from statistics import median

import front
import icons
import sports
import sport_build

esc = front.esc
ET = front.ET

# (market key, side picker, phone label, desktop card label)
SPREAD_ROWS = (('ats', 'Spread', 'Largest Spread'), ('ml', 'Moneyline', 'Heaviest Favorite'), ('total', 'Total', 'Highest Total'))
NHL_ROWS = (('ml', '1P Moneyline', 'Heaviest Favorite'), ('total', '1P Over 1.5', 'Heaviest Over 1.5'),
            ('ml3', '1P 3-Way', 'Heaviest 3-Way Favorite'), ('tie', '1P Tie', 'Shortest Tie Price'))


def books_of(sport, og, k, m):
    """{book: row} for one market from the sportsbooks (no exchanges, no
    book left out of the best price); the exchanges only when no book has it."""
    rows = ((og.get('books') or {}).get(k) or {}).get(m) or {}
    keep = {b: r for b, r in rows.items() if isinstance(r, dict) and b not in sport_build.NO_BEST and not (sport.sources.get(b) or {}).get('x')}
    return keep or {b: r for b, r in rows.items() if isinstance(r, dict) and b not in sport_build.NO_BEST}


def price(v):
    p = (v or {}).get('price') if isinstance(v, dict) else None
    return p if isinstance(p, (int, float)) and abs(p) <= front.ML_CAP else None


def consensus(values):
    """The value most books have (ties: the one nearest the median)."""
    if not values:
        return None
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    mid = median(values)
    return max(counts, key=lambda v: (counts[v], -abs(v - mid)))


def best_at(rows, side, line=None, line_of=None):
    """(best price, book) on one side at that line."""
    best = None
    for b, r in rows.items():
        p = price(r.get(side))
        if p is None or (line is not None and line_of(r, side) != line):
            continue
        if best is None or p > best[0]:
            best = (p, b)
    return best


def side_line(r, side):
    return ((r.get(side) or {}).get('line'))


def spread_pick(sport, og, k):
    """(line, price, book, side): the favorite's consensus spread."""
    rows = books_of(sport, og, k, 'ats')
    lines = {s: [side_line(r, s) for r in rows.values() if isinstance(side_line(r, s), (int, float))] for s in ('away', 'home')}
    fav = {s: consensus([x for x in v if x < 0]) for s, v in lines.items()}
    side = min((s for s in fav if fav[s] is not None), key=lambda s: fav[s], default=None)
    if not side:
        return None
    got = best_at(rows, side, fav[side], side_line)
    return (fav[side], got[0], got[1], side) if got else None


def ml_pick(sport, og, k, m='ml', sides=('away', 'home')):
    """(consensus price, best price, book, side): the favorite (the lower
    consensus price) on a moneyline (3-way: the teams, never the tie)."""
    rows = books_of(sport, og, k, m)
    med = {}
    for s in sides:
        ps = [price(r.get(s)) for r in rows.values()]
        ps = [p for p in ps if p is not None]
        if ps:
            med[s] = median(ps)
    if not med:
        return None
    side = min(med, key=lambda s: med[s])
    got = best_at(rows, side)
    return (med[side], got[0], got[1], side) if got else None


def total_pick(sport, og, k, at=None):
    """(line, consensus Over price, best Over price, book) at the consensus
    total (NHL: at 1.5 only)."""
    rows = books_of(sport, og, k, 'total')
    lines = [r.get('line') for r in rows.values() if isinstance(r.get('line'), (int, float))]
    line = at if at is not None else consensus(lines)
    if line is None:
        return None
    rows = {b: r for b, r in rows.items() if r.get('line') == line}
    overs = [price(r.get('over')) for r in rows.values()]
    overs = [p for p in overs if p is not None]
    got = best_at(rows, 'over')
    return (line, median(overs), got[0], got[1]) if got and overs else None


def segments_of(sport):
    """[(segment key, tag, label)] with a Big Numbers card: NHL 1P; MLB
    1st inning and First 5 (where the markets exist); the rest every segment."""
    return [(s['key'], s['tag'], s['label']) for s in sport.segments]


def rows_for(sport, k, games):
    """[{key, label, long, game, day, top, sub, book, fav}] for one segment,
    in the sport's row order; a market no game has is left out."""
    nhl = sport.key == 'nhl'
    out = []
    for m, label, long in (NHL_ROWS if nhl else SPREAD_ROWS):
        best = None
        for d, g in games:
            og = sport.odds_game(d, g)
            start = g.get('start') or ''
            if m == 'ats':
                x = spread_pick(sport, og, k)
                if not x:
                    continue
                score = (x[0], x[1], start)            # most negative line, then the dearer price (-115 before -110), then earlier
                row = {'top': front.signed(x[0]), 'sub': front.price_txt(x[1]), 'book': x[2], 'fav': x[3]}
            elif m in ('ml', 'ml3'):
                x = ml_pick(sport, og, k, m)
                if not x:
                    continue
                score = (x[0], start)
                row = {'top': front.price_txt(x[1]), 'sub': '', 'book': x[2], 'fav': x[3]}
            elif m == 'tie':
                rows = books_of(sport, og, k, 'ml3')
                ps = [price(r.get('draw')) for r in rows.values()]
                ps = [p for p in ps if p is not None]
                got = best_at(rows, 'draw')
                if not ps or not got:
                    continue
                score = (median(ps), start)
                row = {'top': front.price_txt(got[0]), 'sub': 'Tie', 'book': got[1], 'fav': None}
            else:
                x = total_pick(sport, og, k, 1.5 if nhl else None)
                if not x:
                    continue
                # NHL: every total is 1.5, so the dearest Over wins; else the highest total, then the dearer Over
                score = (x[1], start) if nhl else (-x[0], -x[2], start)
                row = {'top': 'o' + front.line_txt(x[0]), 'sub': front.price_txt(x[2]), 'book': x[3], 'fav': None}
            if best is None or score < best[0]:
                best = (score, dict(row, game=g, day=d))
        if best:
            out.append(dict(best[1], key=m, label=label, long=long))
    return out


def board(sport, now_utc):
    """(day, [(date, game)]): the games still to start on the board (front.upcoming)."""
    today = now_utc.astimezone(ET).date().isoformat()
    games = front.upcoming(sport, today, now_utc)
    if not games:
        return None, []
    if not sport.weekly:   # the first game day only
        games = [x for x in games if x[0] == games[0][0]]
    return games[0][0], games


def when(g, day, first):
    t = front.parse(g.get('start'))
    if not t:
        return 'TBD'
    t = t.astimezone(ET)
    return (t.strftime('%a ') if day != first else '') + t.strftime('%-I:%M %p')


def odds_href(sport, r, k, root):
    g = r['game']
    m = {'tie': 'ml3'}.get(r['key'], r['key'])
    q = f"?week={g['wk']}" if sport.weekly and g.get('wk') else f"?date={r['day']}"
    return f"{root}{sport.odds_page}{q}&seg={k}&mkt={m}#og-{g['away']}-{g['home']}"


def teams_html(sport, r, root, big=False):
    g, size = r['game'], 40 if big else 20
    out = []
    for s in ('away', 'home'):
        code = esc(sport.code(g[s]))
        out.append(f'<span class="bn-team{" bn-fav" if r["fav"] == s else ""}">{sport.badge(g[s], size, root)}<span>{code}</span></span>')
    return f'<span class="bn-teams">{out[0]}<span class="bn-at">@</span>{out[1]}</span>'


def odds_html(sport, r, root):
    return (f'<span class="bn-odds"><span class="bn-book">{front.book_html(sport, r["book"], root)}</span>'
            f'<span class="bn-cell">{front.cell(r["top"], r["sub"])}</span></span>')


def row_html(sport, r, k, first, root):
    """A phone row: the yellow market label and time, both teams (the
    favorite bold); the book's logo and the odds cell on the right."""
    return (f'<a class="bn-row" href="{esc(odds_href(sport, r, k, root))}"><span class="bn-left">'
            f'<span class="bn-label">{esc(r["label"])} &middot; {esc(when(r["game"], r["day"], first))}</span>{teams_html(sport, r, root)}</span>'
            f'{odds_html(sport, r, root)}</a>')


def card_html(sport, r, k, first, root):
    """A desktop card (Odds pages, home, hubs): the long label, large logos, the book
    and the odds cell, the time."""
    return (f'<a class="st-card bn-dcard" href="{esc(odds_href(sport, r, k, root))}"><span class="bn-label">{esc(r["long"])}</span>'
            f'{teams_html(sport, r, root, big=True)}{odds_html(sport, r, root)}'
            f'<span class="bn-time">{esc(when(r["game"], r["day"], first))}</span></a>')


def seg_panes(sport, games, first, root, odds_page=False):
    """The segment toggle (where the sport has two) and a pane per segment."""
    segs = [(k, tag, label, rows_for(sport, k, games)) for k, tag, label in segments_of(sport)]
    segs = [x for x in segs if x[3]]
    if not segs:
        return '', []
    panes = ''
    for i, (k, tag, label, rows) in enumerate(segs):
        inner = ''.join(row_html(sport, r, k, first, root) for r in rows)
        if odds_page:
            inner = (f'<div class="bn-rows">{inner}</div>'
                     f'<div class="bn-dcards">{"".join(card_html(sport, r, k, first, root) for r in rows)}</div>')
        panes += f'<div data-pane="{k}"{"" if i == 0 else " hidden"}>{inner}</div>'
    toggle = front.pills(f'{sport.label} segment', [(k, tag) for k, tag, _, _ in segs], segs[0][0]) if len(segs) > 1 else ''
    return toggle + panes, segs


def sport_card(sport, now_utc, root):
    """Home / hub: "[icon] NBA · 1st Quarter" with the 1Q / 1H toggle, the
    rows, "All NBA odds →"; desktop: the Odds page's cards in a full-width
    row (3 across, NHL 4; template.html .fv-bn)."""
    day, games = board(sport, now_utc)
    if not games:
        return '', None
    first = games[0][0]
    body, segs = seg_panes(sport, games, first, root, odds_page=True)   # desktop: the Odds page's cards, full width
    if not segs:
        return '', None
    title = f'{icons.sport_icon(sport.sp)}{esc(sport.label)}'
    names = {k: label for k, _, label, _ in segs}
    return (f'<div class="st-card bn-card" data-bn-names=\'{esc(json.dumps(names))}\'><div class="st-head"><h4>{title} &middot; <span data-bn-seg>{esc(segs[0][2])}</span></h4></div>'
            f'<div class="bn-body">{body}</div>'
            f'<div class="fr-links">{front.more_link(f"{root}{sport.odds_page}", f"All {esc(sport.label)} odds")}</div></div>'), day


def section(S, now_utc, root='', hub=False):
    """Home: THE BIG NUMBERS + date, a pill per sport with games that day,
    a card per sport; a hub: its own card."""
    cards = []
    for sport in S.values():
        html, day = sport_card(sport, now_utc, root)
        if html:
            cards.append((sport, html, day))
    if not cards:
        return ''
    day = min(d for _, _, d in cards)
    pill = '' if hub or len(cards) == 1 else front.pills('Sport', [(s.key, s.label) for s, _, _ in cards], cards[0][0].key)
    panes = ''.join(f'<div data-pane="{s.key}"{"" if i == 0 else " hidden"}>{h}</div>' for i, (s, h, _) in enumerate(cards))
    return (f'<section class="fr-sec bn" id="big-numbers"><div class="fr-head fr-stack"><h2>The Big Numbers</h2>'
            f'<span class="fr-date">{esc(front.day_label(day))}</span></div>{pill}{panes}</section>')


def odds_top(sp, now_utc, root):
    """The top of /{sport}/odds/: THE BIG NUMBERS + date with the segment
    toggle; desktop one card per market, phones the rows in one card."""
    sport = front.Sport(sp)
    day, games = board(sport, now_utc)
    if not games:
        return ''
    body, segs = seg_panes(sport, games, games[0][0], root, odds_page=True)
    if not segs:
        return ''
    date = 'This week' if sport.weekly else front.day_label(day)
    return (f'<section class="bn bn-odds-top" id="big-numbers"><div class="fr-head fr-stack"><h2>The Big Numbers</h2>'
            f'<span class="fr-date">{esc(date)}</span></div><div class="st-card bn-card">{body}</div></section>')


# the Odds page's segment toggle (sport pages run assets/sport.js, not front.FRONT_JS)
ODDS_JS = '''<script>
document.querySelectorAll('#big-numbers [data-pills]').forEach(function(g) {
  g.addEventListener('click', function(e) {
    var b = e.target.closest('[data-pick]'); if (!b) return;
    var v = b.getAttribute('data-pick');
    g.querySelectorAll('[data-pick]').forEach(function(x) { x.setAttribute('aria-pressed', String(x === b)); });
    [].forEach.call(g.parentNode.children, function(el) { if (el.hasAttribute('data-pane')) el.hidden = el.getAttribute('data-pane') !== v; });
  });
});
</script>'''
