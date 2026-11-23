"""
The Odds API backfill (step 2 of 3): closing lines for every finished game
we have scores for, this season and last, where the Unabated feed has no
book rows (market by market; a market only the admin saved still gets its
book rows here, and the admin's line stays the graded one). Run by hand from Actions (the
"oddsapi-backfill" job, .github/workflows/oddsapi.yml).

Per sport, per game day (newest first):
- historical_events at 14:00 UTC for the ET day (1 credit); each event is
  matched to our game on the ET date and both teams (oddsapi.match).
  Unmatched events go to the report, never guessed.
- The full game (segment "game", every sport but MLB): one bulk
  /historical/sports/{sport}/odds snapshot (h2h, spreads, totals) per start
  time, 5 minutes before it, covers every game starting then (30 credits).
  A game is taken only from its own start time's snapshot, and only if that
  snapshot is before its start; one the bulk pass misses gets the full-game
  markets in its own historical_event_odds call (5 minutes before its start).
- The first segments: historical_event_odds per game, 5 minutes before its
  start, with only the markets still missing (10 x markets returned).
- The closing line per market by fetch_odds_unabated.best_of (spread / total:
  the line most books post, the best price at it; moneyline, 3-way, BTTS,
  NRFI / YRFI: the best price per side), so these grade like the live ones.
  Each line keeps `books` (how many books posted it): NHL 1P BTTS is saved
  even from one book (FanDuel), and the count shows which grades rest on it.

Writes data_feed/oddsapi/history/{sport}/{season}.json:
  {"games": {"date|away|home": {date, away, home, start, source: "oddsapi",
     snapshot, game_snapshot (the full-game line's), segments: {seg: {market: line}},
     books: {seg: {market: {book: row}}}}}}
and data_feed/oddsapi/backfill_state.json (every game done, or tried and
empty, is skipped by the next run; unmatched games are tried again; --retry-game
clears the games with no full-game line, --retry-missing the games still missing
a market no source has book rows for) and data_feed/oddsapi/backfill_report.json
(the last run's report, with the API's names for events that matched no game). sport_build.merge_odds and build_site.py
read the history files under admin and Unabated.

Budget: --max-credits per run (oddsapi.py stops before a call would pass it)
and oddsapi.py's 250,000 floor. Prints an estimate before the first paid call
and stops if it's over 1,500,000. Stops cleanly at 5h30m; with --commit it
commits and pushes the files every 30 minutes and at the end.
"""
import argparse
import glob
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsapi as A  # noqa: E402
import sports  # noqa: E402
from fetch_odds_unabated import best_of, read_json, write_json  # noqa: E402

HIST_DIR = os.path.join(A.OUT_DIR, 'history')
STATE = os.path.join(A.OUT_DIR, 'backfill_state.json')
REPORT = os.path.join(A.OUT_DIR, 'backfill_report.json')   # the last run's report per sport and season
ORDER = ['nhl', 'nba', 'ncaab', 'nfl', 'ncaaf', 'mlb', 'wnba']
MAX_ESTIMATE = 1_500_000
INDOOR = ('nba', 'wnba', 'ncaab', 'nhl')   # no weather delays: the game starts by ESPN's time
LATE = 15   # minutes after ESPN's start: an indoor game's snapshot this late is in-play
BIG_ML = ('nba', 'nhl', 'nfl', 'wnba')
PICKEM = 130   # a full-game ML with both sides plus is a pick'em up to +130 a side   # a full-game ML of 1000+ (or both sides plus) here is flagged
TIME_LIMIT = 5.5 * 3600
COMMIT_EVERY = 30 * 60
NHL_FINAL = ('FINAL', 'OFF')


# ------------------------------------------------------------ our games
def nhl_season_start():
    import periods
    return periods.SEASON_START


def seasons_for(sport):
    """{'this': (season, games), 'last': (season, games)}; games: [{date, away, home, start}]
    finished with a score. NHL: build_site.py's schedule (this season) and
    the 2025-26 archive; the rest: data_seed/games/{sport}/{season}.json."""
    out = {}
    if sport == 'nhl':
        start = nhl_season_start()
        sched = read_json(os.path.join(A.ROOT, 'schedule_data.json'), {}).get('games') or {}
        this = [{'date': d, 'away': g['away'], 'home': g['home'], 'start': g.get('startTimeUTC')}
                for d, gs in sched.items() if d >= start for g in gs
                if g.get('state') in NHL_FINAL and g.get('awayFinal') is not None]
        last = [{'date': g['date'], 'away': g['away'], 'home': g['home'], 'start': g.get('startTimeUTC')}
                for g in read_json(os.path.join(A.ROOT, 'data_seed', 'nhl_2025_26_games.json'), [])
                if g.get('awayFinal') is not None]
        year = int(start[:4]) + 1
        out['this'] = (year, this)
        out['last'] = (year - 1, last)
        return out
    d = os.path.join(A.ROOT, 'data_seed', 'games', sport)
    years = sorted(int(n[:4]) for n in os.listdir(d) if n[:4].isdigit() and n.endswith('.json')) if os.path.isdir(d) else []
    league = None
    if sport in sports.COLLEGE:   # games involving a Division I / FBS team
        league = {t['slug'] for t in read_json(os.path.join(A.ROOT, 'data_seed', 'teams', sport + '.json'), {}).get('teams') or []}
    for which, year in (('this', years[-1] if years else None), ('last', years[-2] if len(years) > 1 else None)):
        if year is None:
            continue
        doc = read_json(os.path.join(d, f'{year}.json'), {})
        games = [{'date': g['date'], 'away': g['away'], 'home': g['home'], 'start': g.get('start'),
                  'away_name': g.get('away_name'), 'home_name': g.get('home_name')}
                 for g in (doc.get('games') or {}).values()
                 if g.get('season_type') in (2, 3) and g.get('final') and g.get('away_score') is not None
                 and (league is None or g['away'] in league or g['home'] in league)]
        out[which] = (year, games)
    return out


def have(sport):
    """{game key: {seg: {markets}}} that already have book rows on the Odds
    page: the Unabated feed (live and its history) and, for the NHL, the
    schedule's odds. The admin's saved lines don't count: they're one price
    with no books behind them, so the backfill fetches the book rows for
    those games too (the admin's line stays the graded one)."""
    out = {}

    def add(key, seg, market):
        out.setdefault(key, {}).setdefault(seg, set()).add(market)
    if sport == 'nhl':
        sched = read_json(os.path.join(A.ROOT, 'schedule_data.json'), {}).get('games') or {}
        for d, gs in sched.items():
            for g in gs:
                o, key = g.get('odds') or {}, f"{d}|{g['away']}|{g['home']}"
                if (o.get('ml') or {}).get(g['away']) is not None:
                    add(key, '1p', 'ml')
                if (o.get('totals') or {}).get('1.5'):
                    add(key, '1p', 'total')
                if o.get('ml3'):
                    add(key, '1p', 'ml3')
                if o.get('btts_yes') is not None:
                    add(key, '1p', 'btts')
        return out
    doc = read_json(os.path.join(A.ROOT, 'data_feed', 'unabated', f'{sport}.json'), {})
    for key, g in (doc.get('games') or {}).items():
        for seg, markets in ((g or {}).get('segments') or {}).items():
            for m, v in (markets or {}).items():
                if v is not None:
                    add(key, seg, m)
    for path in glob.glob(os.path.join(A.ROOT, 'data_feed', 'unabated', 'history', sport, '*.json')):
        day = os.path.basename(path)[:-5]
        for teams, g in (read_json(path, {}).get('games') or {}).items():
            for seg, markets in ((g or {}).get('close') or {}).items():
                for m, by in (markets or {}).items():
                    if by:
                        add(f'{day}|{teams}', seg, m)
    return out


def wanted(sport):
    """[(seg, market, api key)]: the first segments, then the full game."""
    out = [(seg, m, k) for seg, ms in A.MARKETS[sport].items() for m, k in ms.items()]
    if sport != 'mlb':
        out += [('game', m, k) for m, k in A.GAME.items()]
    return out


# ------------------------------------------------------------ closing lines
def _prob(p):
    return 100 / (p + 100) if p > 0 else -p / (-p + 100)


def book_row(market, api_key, outcomes, away_name, home_name):
    """One book's market as a fetch_odds_unabated.best_of row, or None."""
    price = {}
    for o in outcomes or []:
        if o.get('price') is None:
            return None
    if market in ('ml', 'ml3'):
        for o in outcomes:
            side = 'away' if o['name'] == away_name else 'home' if o['name'] == home_name else 'draw' if o['name'] == 'Draw' else None
            if side is None:
                return None
            price[side] = {'price': int(o['price'])}
        need = {'away', 'home', 'draw'} if market == 'ml3' else {'away', 'home'}
        return price if set(price) == need else None
    if market == 'btts':
        for o in outcomes:
            price[str(o['name']).lower()] = {'price': int(o['price'])}
        return {k: price[k] for k in ('yes', 'no')} if {'yes', 'no'} <= set(price) else None
    if market == 'nrfi_yrfi':   # the 1st-inning total at 0.5: Under = NRFI, Over = YRFI
        for o in outcomes:
            if o.get('point') == 0.5:
                price['nrfi' if o['name'] == 'Under' else 'yrfi'] = {'price': int(o['price'])}
        return price if set(price) == {'nrfi', 'yrfi'} else None
    pairs = []
    if market == 'ats':
        aw = [o for o in outcomes if o['name'] == away_name and o.get('point') is not None]
        hm = [o for o in outcomes if o['name'] == home_name and o.get('point') is not None]
        for a in aw:
            for h in hm:
                if a['point'] == -h['point']:
                    pairs.append({'away': {'line': a['point'], 'price': int(a['price'])},
                                  'home': {'line': h['point'], 'price': int(h['price'])}})
        side = ('away', 'home')
    else:   # total
        ov = {o['point']: o for o in outcomes if o['name'] == 'Over' and o.get('point') is not None}
        un = {o['point']: o for o in outcomes if o['name'] == 'Under' and o.get('point') is not None}
        pairs = [{'line': p, 'over': {'price': int(ov[p]['price'])}, 'under': {'price': int(un[p]['price'])}}
                 for p in ov if p in un]
        side = ('over', 'under')
    if not pairs:
        return None
    # a book's main line: the pair priced nearest even (alternates are lopsided)
    return min(pairs, key=lambda r: abs(_prob(r[side[0]]['price']) - _prob(r[side[1]]['price'])))


ALT_GAP = 0.15   # implied probability: this much further from even than the main line = an alternate


def _gap(market, r):
    a, b = (r['away'], r['home']) if market == 'ats' else (r['over'], r['under'])
    return abs(_prob(a['price']) - _prob(b['price']))


def main_lines(market, rows, sport=None):
    """Spreads and totals: drops a book whose only pair is an alternate (Hard
    Rock and BetRivers sometimes send just alternates in the main market):
    its line isn't the one most books post and it's priced ALT_GAP further
    from even than that line's books, or (spreads) it has the other team
    favored by a point or more. MLB's F5 run line is always 0.5 (closing
    keeps only that), so it's left alone. {book: row} -> {book: row}."""
    if market not in ('ats', 'total') or len(rows) < 2 or (sport == 'mlb' and market == 'ats'):
        return rows
    key = (lambda r: r['away']['line']) if market == 'ats' else (lambda r: r['line'])
    by = {}
    for b, r in rows.items():
        by.setdefault(key(r), []).append(b)

    def evenness(x):
        return sum(_gap(market, rows[b]) for b in by[x]) / len(by[x])
    main = max(by, key=lambda x: (len(by[x]), -evenness(x)))
    even = evenness(main)
    out = {}
    for b, r in rows.items():
        x = key(r)
        flipped = market == 'ats' and x * main < 0 and min(abs(x), abs(main)) >= 1
        if x != main and (flipped or _gap(market, r) > even + ALT_GAP):
            continue
        out[b] = r
    return out


def closing(sport, bookmakers, keys, away_name, home_name):
    """{seg: {market: line}}, {seg: {market: {book: row}}} from a bookmakers list.
    keys: [(seg, market, api key)]."""
    lines, books = {}, {}
    for seg, market, api_key in keys:
        rows = {}
        for b in bookmakers or []:
            if b.get('key') not in A.BOOKS:
                continue
            m = next((x for x in b.get('markets') or [] if x.get('key') == api_key), None)
            row = m and book_row(market, api_key, m.get('outcomes'), away_name, home_name)
            if row and sport == 'mlb' and market == 'ats' and abs(row['away']['line']) != 0.5:
                row = None   # RTYB's F5 run line is always 0.5 (as the Unabated feed keeps it)
            if row:
                rows[b['key']] = row
        rows = main_lines(market, rows, sport)
        if not rows:
            continue
        best = best_of('ml' if market in ('btts', 'nrfi_yrfi') else market, rows, ())
        if not best:
            continue
        lines.setdefault(seg, {})[market] = dict(best, books=len(rows))
        books.setdefault(seg, {})[market] = rows
    return lines, books


# ------------------------------------------------------------ the run
class Run:
    def __init__(self, max_credits, commit):
        self.t0 = time.monotonic()
        self.last_commit = self.t0
        self.commit = commit
        self.state = read_json(STATE, {})
        self.files = {}
        self.report = {}
        A.BUDGET = max_credits

    def out_of_time(self):
        return time.monotonic() - self.t0 > TIME_LIMIT

    def hist(self, sport, season):
        k = (sport, season)
        if k not in self.files:
            self.files[k] = read_json(os.path.join(HIST_DIR, sport, f'{season}.json'), {'games': {}})
        return self.files[k]

    def done(self, sport, season):
        return self.state.setdefault(sport, {}).setdefault(str(season), {})

    def save(self, push=False):
        for (sport, season), doc in self.files.items():
            write_json(os.path.join(HIST_DIR, sport, f'{season}.json'), doc)
        write_json(STATE, self.state)
        if self.report:
            write_json(REPORT, {'generated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                                'credits_used': A.used(), 'credits_remaining': A.remaining(),
                                'sports': list(self.report.values())})
        if push and self.commit:
            git_push()
            self.last_commit = time.monotonic()

    def maybe_commit(self):
        if self.commit and time.monotonic() - self.last_commit > COMMIT_EVERY:
            self.save(push=True)


def git_push():
    def git(*args):
        return subprocess.run(['git', *args], cwd=A.ROOT, capture_output=True, text=True)
    git('add', 'data_feed/oddsapi')
    if git('diff', '--cached', '--quiet').returncode == 0:
        return
    git('commit', '-q', '-m', 'The Odds API backfill (progress)')
    for _ in range(5):
        if git('push', '-q').returncode == 0:
            return
        git('fetch', '-q', 'origin', 'main')
        if git('rebase', 'origin/main').returncode != 0:
            git('rebase', '--abort')
            git('pull', '--no-rebase', '-X', 'theirs', 'origin', 'main', '--no-edit')   # a conflict: the refresh's side wins
        time.sleep(3)
    print('backfill: push failed; the files are saved and the next push takes them')


def pending(run, sport, which):
    """(season, {date: [(game, missing [(seg, market, api key)])]}) still to do."""
    seasons = seasons_for(sport)
    if which not in seasons:
        return None, {}
    season, games = seasons[which]
    today = datetime.now(A.ET).date().isoformat()
    got, done = have(sport), run.done(sport, season)
    for key, g in run.hist(sport, season)['games'].items():   # what earlier runs saved
        for seg, markets in (g.get('segments') or {}).items():
            got.setdefault(key, {}).setdefault(seg, set()).update(markets)
    keys = wanted(sport)
    days = {}
    for g in games:
        key = f"{g['date']}|{g['away']}|{g['home']}"
        if g['date'] >= today or done.get(key) in ('filled', 'empty'):   # unmatched games are tried again
            continue
        has = got.get(key) or {}
        missing = [x for x in keys if x[1] not in has.get(x[0], set())]
        if missing:
            days.setdefault(g['date'], []).append((g, missing))
    return season, days


def estimate(days, sport):
    """Most credits the days can cost: events, a bulk snapshot per start time, event odds."""
    total = 0
    for gs in days.values():
        total += 1
        if sport != 'mlb':
            total += 10 * len(A.GAME) * len({g['start'] for g, miss in gs if any(s == 'game' for s, _, _ in miss)})
        total += sum(10 * sum(1 for s, _, _ in miss if s != 'game') for _, miss in gs)
    return total


def start_of(e, seen=None):
    """An event's start: the earliest commence_time the events list or a snapshot gave it."""
    times = [t for t in (A.parse(e.get('commence_time')), A.parse((seen or {}).get('commence_time'))) if t]
    return min(times) if times else None


def pregame(snapshot, e, seen=None):
    t, start = A.parse(snapshot) if snapshot else None, start_of(e, seen)
    return bool(t and start and t < start)


def minutes_before(snapshot, e):
    t, start = A.parse(snapshot) if snapshot else None, start_of(e)
    return round((start - t).total_seconds() / 60) if t and start else None


def bulk_game_lines(sport, events):
    """{event id: (snapshot time, event)} from one bulk full-game snapshot per
    start time, 5 minutes before it. An event is taken (by id) only from the
    snapshot for its own start time, the latest one before it starts: an
    earlier one isn't its closing line, and one at or after its start is live
    (in-play prices). Events it misses get their own call (fill_day)."""
    by_start = {}
    for e in events:
        if start_of(e):
            by_start.setdefault(start_of(e), {})[e['id']] = e
    out = {}
    for t in sorted(by_start):
        data = A.historical_odds(sport, A.before(t, 5), list(A.GAME.values())) or {}
        snap = data.get('timestamp') or A.iso(A.before(t, 5))
        for ev in data.get('data') or []:
            e = by_start[t].get(ev.get('id'))
            if e and pregame(snap, e, ev):
                out[e['id']] = (snap, ev)
    return out


def fill_day(run, sport, season, day, todo, rep):
    """One ET day: events, the bulk full-game snapshots, then each game's first segments."""
    start = datetime.fromisoformat(day).replace(tzinfo=A.ET)
    snap = A.historical_events(sport, datetime.fromisoformat(day).replace(hour=14, tzinfo=timezone.utc),
                               start, start + timedelta(days=1)) or {}
    evs = snap.get('data') or []
    games = [dict(g, _miss=miss) for g, miss in todo]
    pairs, missed = A.match(sport, evs, games)
    for e in missed:   # the API's names, so missing aliases can be added
        rep['unmatched_events'].append(f"{day} {e.get('away_team')} @ {e.get('home_team')}")
    matched = {f"{g['date']}|{g['away']}|{g['home']}" for _, g, _ in pairs}
    done, hist = run.done(sport, season), run.hist(sport, season)['games']
    for g in games:
        key = f"{g['date']}|{g['away']}|{g['home']}"
        if key not in matched:
            rep['unmatched'].append(key)
            done[key] = 'unmatched'
    if sport in INDOOR:   # an indoor game starts by ESPN's time even when the API lists it later (SA @ SAC, Mar 17)
        for i, (e, g, flipped) in enumerate(pairs):
            ours, theirs = A.parse(g.get('start')), A.parse(e.get('commence_time'))
            if ours and theirs and not A.tbd(ours) and ours < theirs:
                pairs[i] = (dict(e, commence_time=A.iso(ours)), g, flipped)
    # the full game: one bulk snapshot per start time
    bulk = {} if sport == 'mlb' else bulk_game_lines(sport, [e for e, g, _ in pairs if any(s == 'game' for s, _, _ in g['_miss'])])
    for e, g, flipped in pairs:
        key = f"{g['date']}|{g['away']}|{g['home']}"
        away_name, home_name = (e['home_team'], e['away_team']) if flipped else (e['away_team'], e['home_team'])
        lines, books, snapshot, game_snapshot = {}, {}, None, None
        game_keys = [x for x in g['_miss'] if x[0] == 'game']
        if game_keys and e['id'] in bulk:
            game_snapshot, ev = bulk[e['id']]
            lines, books = closing(sport, ev.get('bookmakers'), game_keys, away_name, home_name)
        first = [x for x in g['_miss'] if x[0] != 'game']
        if game_keys and 'game' not in lines:   # not in a pregame bulk snapshot: ask for it with the event's own call
            first += game_keys
        if first:
            resp = A.historical_event_odds(sport, e['id'], A.before(A.parse(e['commence_time']), 5), [k for _, _, k in first]) or {}
            snapshot = resp.get('timestamp')
            if snapshot and not pregame(snapshot, e):   # never a live price
                resp = {}
            ln, bk = closing(sport, (resp.get('data') or {}).get('bookmakers'), first, away_name, home_name)
            if 'game' in ln and 'game' not in lines:
                game_snapshot = snapshot
            for seg, v in ln.items():
                lines.setdefault(seg, {}).update(v)
            for seg, v in bk.items():
                books.setdefault(seg, {}).update(v)
        ml = (lines.get('game') or {}).get('ml')
        if ml and min(ml['away'], ml['home']) > 0 and max(ml['away'], ml['home']) > PICKEM:
            # both sides plus past a pick'em: in-play or mixed books. Never saved, so
            # the refresh's check (tests/test_oddsapi.py) can't stop the publish
            rep['big_ml'].append(f"{key} {ml['away']:+d}/{ml['home']:+d} (not saved)")
            lines['game'].pop('ml')
            books.get('game', {}).pop('ml', None)
            if not lines['game']:
                lines.pop('game')
        if lines:
            row = hist.setdefault(key, {'date': g['date'], 'away': g['away'], 'home': g['home'], 'start': g.get('start'),
                                        'source': 'oddsapi', 'segments': {}, 'books': {}})
            row['snapshot'] = snapshot or row.get('snapshot') or A.iso(A.before(A.parse(e['commence_time']), 5))
            if 'game' in lines:   # which snapshot the full-game line came from, and how long before the start
                row['game_snapshot'] = game_snapshot
                gap = minutes_before(game_snapshot, e)
                if gap is not None:
                    rep['game_minutes'].append(gap)
            for seg, v in lines.items():
                row['segments'].setdefault(seg, {}).update(v)
                for m in v:
                    rep['filled'][f'{seg}.{m}'] = rep['filled'].get(f'{seg}.{m}', 0) + 1
            for seg, v in books.items():
                row['books'].setdefault(seg, {}).update(v)
            done[key] = 'filled'
            ml = (lines.get('game') or {}).get('ml')
            if ml and sport in BIG_ML and (max(abs(ml['away']), abs(ml['home'])) >= 1000 or min(ml['away'], ml['home']) > 0):
                rep['big_ml'].append(f"{key} {ml['away']:+d}/{ml['home']:+d}")
            for seg, market, _ in g['_miss']:
                if market not in (lines.get(seg) or {}):
                    rep['no_market'][f'{seg}.{market}'] = rep['no_market'].get(f'{seg}.{market}', 0) + 1
        else:
            done[key] = 'empty'
            rep['empty'].append(key)


def run_sport(run, sport, which):
    season, days = pending(run, sport, which)
    rep = {'sport': sport, 'season': season, 'games_todo': sum(len(v) for v in days.values()), 'filled': {},
           'no_market': {}, 'unmatched': [], 'unmatched_events': [], 'empty': [], 'big_ml': [], 'game_minutes': [],
           'credits': 0}
    run.report[(sport, which)] = rep
    if season is None:
        rep['note'] = f'no {which}-season games with scores in the repo'
        return rep
    used0 = A.used()
    try:
        for day in sorted(days, reverse=True):   # newest day first
            if run.out_of_time():
                rep['stopped'] = 'time limit (5h30m); the next run resumes'
                break
            fill_day(run, sport, season, day, days[day], rep)
            rep['credits'] = A.used() - used0
            run.save()
            run.maybe_commit()
    except (A.BudgetExceeded, A.BelowFloor) as e:
        rep['credits'], rep['stopped'] = A.used() - used0, f'stopped: {e}; the next run resumes'
        print(summary(rep))
        raise
    return rep


def clear_game(run, sport, season):
    """Drops the saved full-game lines (segment "game") and their games' state,
    so the next run pulls them again; the first segments stay. Returns how many."""
    done, n = run.done(sport, season), 0
    for key, g in run.hist(sport, season)['games'].items():
        if 'game' in (g.get('segments') or {}):
            g['segments'].pop('game')
            (g.get('books') or {}).pop('game', None)
            done.pop(key, None)
            n += 1
    return n


def retry_game(run, sport, season):
    """Clears the state of every game that has no full-game line saved, so
    the next run asks for it again (it pulls only what's still missing; the
    first segments stay). Returns how many."""
    if sport == 'mlb':
        return 0
    done, hist, n = run.done(sport, season), run.hist(sport, season)['games'], 0
    for key in [k for k, v in done.items() if v in ('filled', 'empty')]:
        if 'game' not in ((hist.get(key) or {}).get('segments') or {}):
            done.pop(key)
            n += 1
    return n


def retry_missing(run, sport, season):
    """Clears the state of every filled game still missing a market that no
    source has book rows for (the games only the admin had lines for), so the
    next run asks for just those markets. Returns how many."""
    done, hist, got, n = run.done(sport, season), run.hist(sport, season)['games'], have(sport), 0
    for key in [k for k, v in done.items() if v == 'filled']:
        saved = ((hist.get(key) or {}).get('segments') or {})
        if any(m not in saved.get(seg, {}) and m not in got.get(key, {}).get(seg, set()) for seg, m, _ in wanted(sport)):
            done.pop(key)
            n += 1
    return n


def regrade(run, sport, season):
    """Picks a saved game's line again from its saved book rows wherever
    best_of's outlier guard changes it (a line the guard doesn't touch stays
    as saved); a market every book was dropped from loses its line. Returns
    {changed, dropped (lines)}."""
    import fetch_odds_unabated as U
    out = {'changed': 0, 'dropped': 0}
    for g in run.hist(sport, season)['games'].values():
        for seg, mk in (g.get('books') or {}).items():
            for market, rows in mk.items():
                m = 'ml' if market in ('btts', 'nrfi_yrfi') else market
                guard, U.OUTLIER = U.OUTLIER, float('inf')
                unguarded = rows and best_of(m, rows, ())
                U.OUTLIER = guard
                best = rows and best_of(m, rows, ())
                if best == unguarded:
                    continue
                new = dict(best, books=len(rows)) if best else None
                out['changed'] += 1
                if new:
                    g.setdefault('segments', {}).setdefault(seg, {})[market] = new
                else:
                    out['dropped'] += 1
                    g.get('segments', {}).get(seg, {}).pop(market, None)
    return out


def alt_lines(sport):
    """Runs main_lines over every saved book row of the sport (the live file,
    the day files and the season files) and picks a game's saved line again
    where its rows changed. No API calls. Returns {games, rows: {book: n},
    lines (saved lines that changed)}."""
    out = {'games': 0, 'rows': {}, 'lines': 0}
    paths = [os.path.join(A.OUT_DIR, sport + '.json')] + sorted(glob.glob(os.path.join(HIST_DIR, sport, '*.json')))
    for path in paths:
        doc = read_json(path, {})
        touched = False
        for g in (doc.get('games') or {}).values():
            hit = False
            for field in ('books', 'close', 'open', 'opens'):
                for seg, mk in (g.get(field) or {}).items():
                    for market, rows in (mk or {}).items():
                        keep = main_lines(market, rows or {}, sport)
                        if keep == rows:
                            continue
                        for b in set(rows) - set(keep):
                            out['rows'][b] = out['rows'].get(b, 0) + 1
                        mk[market] = keep
                        hit = True
                        saved = (g.get('segments') or {}).get(seg) or {}
                        if field == 'books' and market in saved:
                            best = keep and best_of(market, keep, ())
                            new = best and (dict(best, books=len(keep)) if 'books' in saved[market] else best)
                            if new != saved[market]:
                                strip = lambda v: {k: x for k, x in (v or {}).items() if k != 'books'}
                                out['lines'] += strip(new) != strip(saved[market])
                                if new:
                                    saved[market] = new
                                else:
                                    saved.pop(market)
            if hit:
                out['games'] += 1
                touched = True
        if touched:
            write_json(path, doc)
    return out


def retry_late(run, sport, season):
    """Indoor sports: drops every saved game whose snapshot is more than LATE
    minutes after ESPN's start (in-play prices) and clears its state, so the
    next run asks again at ESPN's start minus 5. Returns the keys."""
    if sport not in INDOOR:
        return []
    done, hist, out = run.done(sport, season), run.hist(sport, season)['games'], []
    for key, g in list(hist.items()):
        ours = A.parse(g.get('start'))
        if not ours or A.tbd(ours):
            continue
        snaps = [A.parse(g.get(f)) for f in ('snapshot', 'game_snapshot') if g.get(f)]
        if any(t and (t - ours).total_seconds() > LATE * 60 for t in snaps):
            hist.pop(key)
            done.pop(key, None)
            out.append(key)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--sport', default='all')
    ap.add_argument('--season', default='this', choices=('this', 'last', 'both'))
    ap.add_argument('--max-credits', type=int, default=400_000)
    ap.add_argument('--commit', action='store_true', help='commit and push every 30 minutes and at the end')
    ap.add_argument('--clear-game', action='store_true', help='drop the saved full-game lines (no API calls)')
    ap.add_argument('--retry-game', action='store_true', help='retry the games with no full-game line (no API calls)')
    ap.add_argument('--retry-late', action='store_true',
                    help='drop and retry the indoor games saved from a snapshot after ESPN\'s start (no API calls)')
    ap.add_argument('--regrade', action='store_true', help='pick every saved line again from its book rows (no API calls)')
    ap.add_argument('--retry-missing', action='store_true',
                    help='retry the filled games still missing a market with no book rows (no API calls)')
    ap.add_argument('--alt-lines', action='store_true',
                    help='drop the saved alternate spread / total rows and pick those lines again (no API calls)')
    args = ap.parse_args(argv)
    todo_sports = ORDER if args.sport == 'all' else [args.sport]
    if args.alt_lines:
        for s in todo_sports:
            r = alt_lines(s)
            print(f"{s}: {r['games']} games, {r['lines']} saved lines changed, rows dropped: "
                  + (', '.join(f'{b} {n}' for b, n in sorted(r['rows'].items(), key=lambda x: -x[1])) or 'none'))
        return 0
    whiches = ['this', 'last'] if args.season == 'both' else [args.season]
    run = Run(args.max_credits, args.commit)
    if args.regrade:
        import fetch_odds_unabated as U
        for s in todo_sports:
            for w in whiches:
                season = (seasons_for(s).get(w) or (None,))[0]
                if season is not None:
                    print(f'{s} {season}: {regrade(run, s, season)}')
        print('books dropped as outliers (rows): ' + ', '.join(f'{b} {n}' for b, n in sorted(U.OUTLIERS.items(), key=lambda x: -x[1])))
        run.save()
        return 0
    if args.retry_late:
        for s in todo_sports:
            for w in whiches:
                season = (seasons_for(s).get(w) or (None,))[0]
                keys = retry_late(run, s, season) if season is not None else []
                if keys:
                    print(f'{s} {season}: {len(keys)} games saved after the start will be tried again: {", ".join(keys)}')
        run.save()
        return 0
    if args.clear_game or args.retry_game or args.retry_missing:
        for s in todo_sports:
            for w in whiches:
                season = (seasons_for(s).get(w) or (None,))[0]
                if season is not None and args.clear_game:
                    print(f'{s} {season}: cleared the full-game line of {clear_game(run, s, season)} games')
                elif season is not None and args.retry_game:
                    print(f'{s} {season}: {retry_game(run, s, season)} games with no full-game line will be tried again')
                elif season is not None:
                    print(f'{s} {season}: {retry_missing(run, s, season)} games missing a market will be tried again')
        run.save()
        return 0
    plan = [(s, w) for w in whiches for s in todo_sports]   # this season (all sports) first, then last
    est = {}
    for s, w in plan:
        season, days = pending(run, s, w)
        est[(s, w)] = estimate(days, s)
        print(f"estimate {s} {w} season ({season}): {sum(len(v) for v in days.values())} games on {len(days)} days, "
              f"at most {est[(s, w)]:,} credits")
    total = sum(est.values())
    print(f'estimate total: at most {total:,} credits (this run stops at {args.max_credits:,})')
    if total > MAX_ESTIMATE:
        print(f'stopped: the estimate is over {MAX_ESTIMATE:,}')
        return 1
    reports = []
    try:
        for s, w in plan:
            if run.out_of_time():
                break
            reports.append(run_sport(run, s, w))
            print(summary(reports[-1]))
    except (A.BudgetExceeded, A.BelowFloor) as e:
        print(f'stopped: {e}')
    finally:   # a crash keeps what it did
        run.save(push=True)
    print(f'backfill: {A.used():,} credits used this run, {A.remaining() if A.remaining() is not None else "?"} remaining')
    return 0


def summary(rep):
    lines = [f"{rep['sport']} {rep['season']}: {rep['games_todo']} games to fill, {rep['credits']:,} credits"]
    if rep.get('note'):
        lines.append('  ' + rep['note'])
    if rep['filled']:
        lines.append('  filled: ' + ', '.join(f'{k} {v}' for k, v in sorted(rep['filled'].items())))
    if rep['no_market']:
        lines.append('  no line from the API: ' + ', '.join(f'{k} {v}' for k, v in sorted(rep['no_market'].items())))
    if rep['unmatched']:
        lines.append(f"  unmatched games: {len(rep['unmatched'])} (e.g. {', '.join(rep['unmatched'][:5])})")
    if rep['empty']:
        lines.append(f"  matched but no lines: {len(rep['empty'])} (e.g. {', '.join(rep['empty'][:5])})")
    if rep['unmatched_events']:
        lines.append(f"  API events with no game of ours: {len(rep['unmatched_events'])}")
        lines += ['    ' + x for x in rep['unmatched_events']]
    if rep['game_minutes']:
        m = sorted(rep['game_minutes'])
        lines.append(f"  full-game snapshot before the start: median {m[len(m) // 2]} min, max {m[-1]} min")
    if rep['big_ml']:
        lines.append(f"  check: full-game ML 1000+ or both sides plus: {len(rep['big_ml'])} ({', '.join(rep['big_ml'][:10])})")
    if rep.get('stopped'):
        lines.append('  ' + rep['stopped'])
    return '\n'.join(lines)


if __name__ == '__main__':
    sys.exit(main())
