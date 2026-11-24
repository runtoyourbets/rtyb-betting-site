"""
The Odds API probe (step 1 of 3): which of our markets and books the API
has, live and in history, per sport. Run by hand from Actions (the
"oddsapi-probe" job, .github/workflows/oddsapi.yml); writes
data_feed/oddsapi/probe.json. Nothing on the site reads it yet.

Per sport:
- Live (in-season sports): the next 3 upcoming events, event_markets for each
  (which of our market keys each book lists, 1 credit), and the first one's
  odds for our first-segment markets (a sample line + price).
- History: a finished day last season and this season (MLB and WNBA: 2025 and
  2026); historical_events for that day, then one game's odds 5 minutes
  before its start with the sport's first-segment markets.
- The next segments (second half; NHL 2nd / 3rd period) and the full game:
  for 3 finished games this season, snapshots 10 minutes before the start
  and from the scheduled end of the first half / period until 30 minutes
  later (NHL: the 1st intermission with the full-game line, then the 2nd).
- One historical bulk snapshot of the full-game markets (the whole slate in
  one call) to price it against per-event calls.

BUDGET credits at most (oddsapi.py stops before a call would pass it).

--books (the "books" job): first-segment coverage of the books we could add
(probe_books, books_probe.json).
"""
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsapi as A  # noqa: E402
import sports  # noqa: E402

BUDGET = 5_000
OUT = os.path.join(A.OUT_DIR, 'probe.json')

# a day each season with a full slate (ET)
DAYS = {
    'nhl': {'last': '2026-01-15', 'this': '2026-11-14'},
    'nba': {'last': '2026-01-15', 'this': '2026-11-14'},
    'ncaab': {'last': '2026-01-17', 'this': '2026-11-14'},
    'nfl': {'last': '2025-11-16', 'this': '2026-11-15'},
    'ncaaf': {'last': '2025-11-15', 'this': '2026-11-14'},
    'mlb': {'last': '2025-06-20', 'this': '2026-06-20'},
    'wnba': {'last': '2025-06-20', 'this': '2026-06-20'},
}
SECOND = ['h2h_h2', 'spreads_h2', 'totals_h2']
NHL_P2 = ['h2h_p2', 'totals_p2', 'h2h_3_way_p2']
NHL_P3 = ['h2h_p3', 'totals_p3', 'h2h_3_way_p3']
FULL = ['h2h', 'spreads', 'totals']
NEXT = {'nhl': NHL_P2 + NHL_P3, 'mlb': []}
BREAK = {'nba': 75, 'wnba': 75, 'ncaab': 55, 'nfl': 100, 'ncaaf': 100}   # minutes from the start to halftime


def next_markets(sport):
    return NEXT.get(sport, SECOND)


def snapshots(sport):
    """[(minutes from the start, markets)] for the in-game check."""
    if sport == 'mlb':
        return [(-10, FULL)]
    if sport == 'nhl':
        return [(-10, NHL_P2 + NHL_P3 + FULL), (40, NHL_P2 + FULL), (50, NHL_P2 + FULL), (80, NHL_P3), (90, NHL_P3)]
    b = BREAK[sport]
    return [(-10, SECOND + FULL), (b, SECOND + FULL)] + [(b + m, SECOND) for m in (10, 20, 30)]


def et_day(day):
    d = date.fromisoformat(day)
    start = datetime.combine(d, time(0, 0), tzinfo=A.ET)
    return start, start + timedelta(days=1)


def books_by_market(bookmakers):
    """{market key: [books]} and {market key: a sample row} from a bookmakers list."""
    got, sample = {}, {}
    for b in bookmakers or []:
        for m in b.get('markets') or []:
            got.setdefault(m['key'], []).append(b['key'])
            if m['key'] not in sample:
                sample[m['key']] = {'book': b['key'], 'outcomes': [
                    {k: o.get(k) for k in ('name', 'description', 'point', 'price') if o.get(k) is not None}
                    for o in m.get('outcomes') or []]}
    return {k: sorted(v) for k, v in got.items()}, sample


def pick_games(evs, n=3):
    """n events nearest 7:30 PM ET (prime time: the most books)."""
    def gap(e):
        t = A.parse(e.get('commence_time'))
        return abs((t.astimezone(A.ET).hour * 60 + t.astimezone(A.ET).minute) - 19 * 60 - 30) if t else 9999
    return sorted(evs or [], key=gap)[:n]


def slim(e):
    return {k: e.get(k) for k in ('id', 'commence_time', 'away_team', 'home_team')}


def probe_live(sport, out):
    evs = [e for e in A.events(sport) if (A.parse(e.get('commence_time')) or datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc)]
    evs = sorted(evs, key=lambda e: e['commence_time'])[:3]
    out['live_events'] = [slim(e) for e in evs]
    wanted = set(A.market_keys(sport)) | set(next_markets(sport)) | set(FULL)
    for e in evs:
        for book, keys in A.event_markets(sport, e['id']).items():
            for k in keys:
                if k in wanted:
                    out['markets'].setdefault(k, blank()).setdefault('live_books', [])
                    if book not in out['markets'][k]['live_books']:
                        out['markets'][k]['live_books'].append(book)
    if evs:
        data = A.event_odds(sport, evs[0]['id'], A.market_keys(sport)) or {}
        _, sample = books_by_market(data.get('bookmakers'))
        for k, row in sample.items():
            out['markets'].setdefault(k, blank())['sample_live'] = row


def blank():
    return {'live_books': [], 'history': {}}


def probe_history(sport, out):
    """Each season: the day's events (kept for the next-segment check) and one game's first-segment odds."""
    days = {}
    for season, day in DAYS[sport].items():
        start, end = et_day(day)
        snap = A.historical_events(sport, datetime.combine(start.date(), time(14), tzinfo=timezone.utc), start, end) or {}
        evs = snap.get('data') or []
        games = pick_games(evs)
        days[season] = games
        out['history_games'][season] = {'day': day, 'events_listed': len(evs), 'games': [slim(e) for e in games]}
        if not games:
            continue
        g = games[0]
        at = A.before(A.parse(g['commence_time']), 5)
        data = (A.historical_event_odds(sport, g['id'], at, A.market_keys(sport)) or {}).get('data') or {}
        got, sample = books_by_market(data.get('bookmakers'))
        out['history_games'][season]['odds_game'] = slim(g)
        for k in A.market_keys(sport):
            m = out['markets'].setdefault(k, blank())
            m['history'][season] = got.get(k, [])
            if k in sample:
                m.setdefault('sample_history', {})[season] = sample[k]
    return days


def probe_next(sport, games, out):
    """In-game snapshots for up to 3 finished games this season."""
    res = out['next'] = {'markets': next_markets(sport) + FULL, 'games': []}
    for g in games[:3]:
        t0 = A.parse(g['commence_time'])
        row = {'game': slim(g), 'snapshots': {}}
        res['games'].append(row)
        for off, markets in snapshots(sport):
            try:
                data = (A.historical_event_odds(sport, g['id'], t0 + timedelta(minutes=off), markets) or {}).get('data') or {}
            except A.BudgetExceeded:
                res.setdefault('skipped_budget', []).append(f"{g['id']} {off:+d} min")
                continue
            got, sample = books_by_market(data.get('bookmakers'))
            row['snapshots'][str(off)] = {k: len(v) for k, v in got.items()}
            for k, s in sample.items():
                res.setdefault('samples', {}).setdefault(k, dict(s, minute=off))
    # when each market first / last showed, and the most books
    seen = {}
    for row in res['games']:
        for off, got in row['snapshots'].items():
            for k, n in got.items():
                x = seen.setdefault(k, {'first': int(off), 'last': int(off), 'max_books': 0, 'games': 0})
                x['first'], x['last'], x['max_books'] = min(x['first'], int(off)), max(x['last'], int(off)), max(x['max_books'], n)
        for k in {k for got in row['snapshots'].values() for k in got}:
            seen[k]['games'] += 1
    res['seen'] = seen


def probe_bulk(sport, games, out):
    """One whole-slate full-game snapshot: what it costs and how many events it covers."""
    if not games:
        return
    t0 = A.parse(games[0]['commence_time'])
    before = A.used()
    data = A.historical_odds(sport, A.before(t0, 10), FULL) or {}
    evs = data.get('data') or []
    out['bulk'] = {'at': A.iso(A.before(t0, 10)), 'credits': A.used() - before, 'events': len(evs),
                   'events_with_lines': sum(1 for e in evs if e.get('bookmakers'))}


# --books: books The Odds API carries that Unabated doesn't, as candidates to
# swap in for the 5 we pull from both (DraftKings, FanDuel, BetMGM, Caesars,
# Fanatics); about 1 credit per event (event_markets)
CANDIDATES = ['ballybet', 'betparx', 'fliff', 'betus', 'lowvig', 'mybookieag', 'betanysports', 'rebet',
              'windcreek', 'betopenly']
BOOKS_OUT = os.path.join(A.OUT_DIR, 'books_probe.json')
BOOKS_EVENTS = 10


def probe_books():
    """Per in-season sport: the next BOOKS_EVENTS events, and per candidate
    the events it lists any market for, the events it lists a first-segment
    market for, and which first-segment markets (data_feed/oddsapi/books_probe.json)."""
    A.BUDGET = 300
    doc = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'candidates': CANDIDATES, 'sports': {}, 'stopped': None}
    try:
        for sport in ['nhl', 'nba', 'ncaab', 'nfl', 'ncaaf', 'mlb', 'wnba']:
            if not sports.in_season(sports.BY_KEY[sport]):
                continue
            now = datetime.now(timezone.utc)
            evs = sorted((e for e in A.events(sport, now, now + timedelta(days=3)) if e.get('commence_time')),
                         key=lambda e: e['commence_time'])[:BOOKS_EVENTS]
            first = set(A.market_keys(sport))
            out = doc['sports'][sport] = {'events': len(evs), 'first_segment_markets': sorted(first), 'books': {}}
            for e in evs:
                for book, keys in A.event_markets(sport, e['id'], CANDIDATES).items():
                    b = out['books'].setdefault(book, {'any': 0, 'first': 0, 'markets': []})
                    b['any'] += 1
                    mine = sorted(first & set(keys))
                    if mine:
                        b['first'] += 1
                    b['markets'] = sorted(set(b['markets']) | set(mine))
            print(f'{sport}: {len(evs)} events, {A.used()} credits used')
    except (A.BudgetExceeded, A.BelowFloor) as e:
        doc['stopped'] = str(e)
        print(f'stopped: {e}')
    doc['credits_used'], doc['credits_remaining'] = A.used(), A.remaining()
    os.makedirs(A.OUT_DIR, exist_ok=True)
    with open(BOOKS_OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f'books probe: {A.used()} credits used; wrote {os.path.relpath(BOOKS_OUT, A.ROOT)}')


def main():
    if '--books' in sys.argv[1:]:
        probe_books()
        return
    A.BUDGET = BUDGET
    order = ['nhl', 'nba', 'ncaab', 'nfl', 'ncaaf', 'mlb', 'wnba']
    doc = {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'budget': BUDGET,
           'books': list(A.BOOKS), 'days': DAYS, 'sports': {}, 'stopped': None}
    days = {}
    try:
        # the first-segment check for every sport first, then the next segments
        for sport in order:
            out = doc['sports'][sport] = {'markets': {}, 'history_games': {}, 'in_season': sports.in_season(sports.BY_KEY[sport])}
            if out['in_season']:
                probe_live(sport, out)
            days[sport] = probe_history(sport, out)
            print(f'{sport}: first segments done, {A.used()} credits used')
        for sport in order:
            probe_bulk(sport, days[sport].get('this') or [], doc['sports'][sport])
        for sport in order:
            probe_next(sport, days[sport].get('this') or [], doc['sports'][sport])
            print(f'{sport}: next segments done, {A.used()} credits used')
    except (A.BudgetExceeded, A.BelowFloor) as e:
        doc['stopped'] = str(e)
        print(f'stopped: {e}')
    doc['credits_used'], doc['credits_remaining'] = A.used(), A.remaining()
    os.makedirs(A.OUT_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f'probe: {A.used()} credits used, {A.remaining()} remaining; wrote {os.path.relpath(OUT, A.ROOT)}')


if __name__ == '__main__':
    main()
