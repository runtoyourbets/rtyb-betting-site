"""
Live odds from The Odds API for every in-season sport (step 3 of 3), on
oddsapi.py. Writes data_feed/oddsapi/{sport}.json in the same shape as
data_feed/unabated/{sport}.json (fetch_odds_unabated.py):

  {"updated", "status": {"pulled": n, "failed": n}, "unmatched": [...],
   "games": {"date|away|home": {date, away, home, start, event, pulled,
      segments: {seg: {market: line}}, books: {seg: {market: {book: row}}},
      opens: {seg: {market: {book: row}}}}}}

Books: the sport's oddsapi.LIVE_BOOKS (10), plus DraftKings and FanDuel
when the list lacks them and Unabated has no price from one of them for a
game starting within SAFETY_HOURS (pull_sport; printed in the run log,
status.safety).
books are keyed by The Odds API's book keys (sport_build.ODDSAPI_BOOKS maps
them to the Odds page's sources) and carry no links: the Odds page's book
links stay Gambly's. A game's odds freeze at its start; its opens and closing
rows then move to data_feed/oddsapi/history/{sport}/{date}.json
(fetch_odds_unabated.archive_started). sport_build.merge_odds grades admin >
Unabated > The Odds API; build_site.py uses the NHL file for 1P ML, totals and
BTTS (The Odds API replaced SportsGameOdds for BTTS: btts_p1 is live at 3
books in probe.json).

Cadence (refresh.yml, every 10 minutes):
  --hourly (the run in the first 10 minutes after the hour): every game we
    show that starts in the next 36 hours
  every run: the closing capture, games starting in the next 20 minutes not
    pulled in the last 15
Only the markets probe.json shows live for the sport (first segments plus the
full game's h2h / spreads / totals, every sport), only games that
haven't started, only in-season sports and Division I / FBS college games.

Budget: MONTHLY_BUDGET credits a month for the live pulls, a daily share of
budget / days in the month; once today's live usage passes it, the hourly
pull runs every 2 hours for the rest of the day (the closing capture always
runs). oddsapi.py's 250,000 floor still applies. data_feed/oddsapi/status.json
holds used today / this month / remaining for the admin page.

Next-day capture (the second half; the NHL's live full-game line after the
1st), for grading only:
  - every run notes the games it sees at halftime (NBA, WNBA, NCAAB, NFL,
    NCAAF) or the 1st intermission (NHL) in data_feed/oddsapi/breaks.json:
    {sport: {game key: {break: "half" | "p1", seen_at}}}, no API call
  - the first run after 6 AM ET asks historical_event_odds, for yesterday's
    finished games, at seen_at (or the start + BREAK_MINUTES), then +5 and
    +10 minutes, for h2h_h2 / spreads_h2 / totals_h2 (NHL: h2h / spreads /
    totals); the line (best_of) is saved under segment "2h" (NHL "live_p1")
    in history/{sport}/{season}.json, or the game is marked "no line"

The key comes from env ODDS_API_KEY (a GitHub Actions secret) and is never
printed, logged or written to a file.
"""
import argparse
import calendar
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsapi as A  # noqa: E402
import backfill_oddsapi as B  # noqa: E402
import fetch_odds_unabated as U  # noqa: E402
import sports  # noqa: E402

# NHL names -> the schedule's codes (fetch_odds_unabated.team_aliases reads these)
TEAM_NAME_TO_ABBREV = {
    'Anaheim Ducks': 'ANH', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF',
    'Calgary Flames': 'CGY', 'Carolina Hurricanes': 'CAR', 'Chicago Blackhawks': 'CHI',
    'Colorado Avalanche': 'COL', 'Columbus Blue Jackets': 'CBJ', 'Dallas Stars': 'DAL',
    'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA',
    'Los Angeles Kings': 'LA', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MTL',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJ', 'New York Islanders': 'NYI',
    'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
    'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJ', 'Seattle Kraken': 'SEA',
    'St Louis Blues': 'STL', 'St. Louis Blues': 'STL', 'Tampa Bay Lightning': 'TB',
    'Toronto Maple Leafs': 'TOR', 'Utah Mammoth': 'UTA', 'Vancouver Canucks': 'VAN',
    'Vegas Golden Knights': 'VGK', 'Washington Capitals': 'WSH', 'Winnipeg Jets': 'WPG',
}

HISTORY_DIR = os.path.join(A.OUT_DIR, 'history')
PROBE = os.path.join(A.OUT_DIR, 'probe.json')
STATUS = os.path.join(A.OUT_DIR, 'status.json')
BREAKS = os.path.join(A.OUT_DIR, 'breaks.json')
UNABATED_DIR = os.path.join(A.ROOT, 'data_feed', 'unabated')
LOOKAHEAD = timedelta(hours=36)
CLOSE_WINDOW = timedelta(minutes=20)   # the closing capture: games starting this soon...
CLOSE_GAP = timedelta(minutes=15)      # ...not pulled this recently
MONTHLY_BUDGET = 150_000
SAFETY_HOURS = 6                       # DraftKings / FanDuel fallback: games starting this soon
CAPTURE_HOUR = 6                       # ET: the first run after this does yesterday's break lines
BREAK_MINUTES = {'nba': 75, 'wnba': 75, 'ncaab': 55, 'nfl': 100, 'ncaaf': 100, 'nhl': 40}
BREAK_SEG = {'nhl': ('live_p1', A.GAME)}   # the rest: the second half
H2 = {'ml': 'h2h_h2', 'ats': 'spreads_h2', 'total': 'totals_h2'}


def break_markets(sport):
    return BREAK_SEG.get(sport, ('2h', H2))


# ------------------------------------------------------------ budget
def live_usage(now):
    """(today, this month) credits the live job used, ET days, from usage.jsonl."""
    today, month = 0, 0
    day = now.astimezone(A.ET).date()
    try:
        with open(A.USAGE, encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                t = A.parse(row.get('time'))
                if row.get('job') != 'live' or not t:
                    continue
                d = t.astimezone(A.ET).date()
                if (d.year, d.month) == (day.year, day.month):
                    month += row.get('credits') or 0
                    today += (row.get('credits') or 0) if d == day else 0
    except OSError:
        pass
    return today, month


def daily_share(now):
    day = now.astimezone(A.ET)
    return MONTHLY_BUDGET / calendar.monthrange(day.year, day.month)[1]


def write_status(now):
    today, month = live_usage(now)
    new = {'today': today, 'month': month, 'remaining': A.remaining(), 'budget': MONTHLY_BUDGET,
           'daily_share': round(daily_share(now))}
    old = U.read_json(STATUS, {})
    if new['remaining'] is None:
        new['remaining'] = old.get('remaining')
    if any(old.get(k) != v for k, v in new.items()):
        U.write_json(STATUS, dict(old, **new, updated=now.isoformat(timespec='seconds')))


# ------------------------------------------------------------ games
def live_keys(sport):
    """[(seg, market, api key)]: the first-segment markets probe.json shows
    live (or, for a sport the probe saw out of season, the ones it found in
    the historical snapshots), then the full game's."""
    probe = (U.read_json(PROBE, {}).get('sports') or {}).get(sport) or {}
    markets = probe.get('markets') or {}
    out = []
    for seg, m, k in B.wanted(sport):
        if seg == 'game':   # the full game's h2h / spreads / totals, every sport (B.wanted)
            out.append((seg, m, k))
            continue
        info = markets.get(k)
        if info is None:
            continue
        if info.get('live_books') or (not probe.get('in_season') and ((info.get('history') or {}).get('this'))):
            out.append((seg, m, k))
    return out


def shown_games(sport, now):
    """Games we show that haven't started and start within LOOKAHEAD
    (college: involving a Division I / FBS team)."""
    games = [g for g in U.upcoming_games(sport, now) if g['_start'] <= now + LOOKAHEAD]
    if sport in sports.COLLEGE:
        league = sports.league_slugs(sport, U.read_json(os.path.join(A.ROOT, 'data_seed', 'teams', sport + '.json'), {}).get('teams') or [])
        games = [g for g in games if g['away'] in league or g['home'] in league]
    return games


def due(rec, start, now, hourly):
    """Whether this run pulls the game: the hourly pull, or the closing capture."""
    if start <= now:
        return False
    if hourly:
        return True
    pulled = A.parse((rec or {}).get('pulled'))
    return start - now <= CLOSE_WINDOW and (not pulled or now - pulled >= CLOSE_GAP)


def unabated_gaps(sport, games, now):
    """Games starting within SAFETY_HOURS that Unabated has no DraftKings
    or FanDuel price for (no row in any market)."""
    feed = {(g.get('date'), g.get('away'), g.get('home')): g
            for g in (U.read_json(os.path.join(UNABATED_DIR, sport + '.json'), {}).get('games') or {}).values()}
    out = []
    for g in games:
        if g['_start'] - now > timedelta(hours=SAFETY_HOURS):
            continue
        have = {b for mk in ((feed.get((g['date'], g['away'], g['home'])) or {}).get('books') or {}).values()
                for by in mk.values() for b in (by or {})}
        if not {'1', '2'} <= have:
            out.append(g)
    return out


def pull_sport(sport, now, hourly):
    """The due games' odds from the sport's A.LIVE_BOOKS; when Unabated has no
    DraftKings or FanDuel price for a game starting within SAFETY_HOURS, this
    pull adds the A.SAFETY_BOOKS the list lacks (a second region) and says so."""
    path = os.path.join(A.OUT_DIR, sport + '.json')
    doc = U.read_json(path, {})
    games_doc = doc.get('games') or {}
    U.archive_started(sport, games_doc, now, HISTORY_DIR)   # odds freeze at the start
    status, unmatched = {'pulled': 0, 'failed': 0}, []
    keys = live_keys(sport)
    games = shown_games(sport, now)
    todo = [g for g in games if due(games_doc.get(f"{g['date']}|{g['away']}|{g['home']}"), g['_start'], now, hourly)]
    books = A.LIVE_BOOKS[sport]
    extra = tuple(b for b in A.SAFETY_BOOKS if b not in books)
    gaps = unabated_gaps(sport, todo, now) if todo and keys and extra else []
    if gaps:
        books += extra
        print(f"{sport}: DraftKings and FanDuel added to this pull (Unabated has no price from one of them for "
              f"{len(gaps)} game{'s' if len(gaps) != 1 else ''} starting within {SAFETY_HOURS} hours: "
              f"{', '.join(g['away'] + ' @ ' + g['home'] for g in gaps[:5])})")
    if todo and keys:
        events = A.events(sport, now, now + LOOKAHEAD)   # free
        pairs, missed = A.match(sport, events, [{k: v for k, v in g.items() if k != '_start'} for g in todo])
        unmatched = sorted(f"{e.get('away_team')} @ {e.get('home_team')}" for e in missed
                           if (A.parse(e.get('commence_time')) or now) > now)
        for e, g, flipped in pairs:
            if (A.parse(e.get('commence_time')) or now) <= now:   # skip events already started
                continue
            away_name, home_name = (e['home_team'], e['away_team']) if flipped else (e['away_team'], e['home_team'])
            data = A.event_odds(sport, e['id'], [k for _, _, k in keys], books)
            if not data:
                status['failed'] += 1
                continue
            lines, rows = B.closing(sport, data.get('bookmakers'), keys, away_name, home_name, books)
            key = f"{g['date']}|{g['away']}|{g['home']}"
            rec = games_doc.setdefault(key, {'date': g['date'], 'away': g['away'], 'home': g['home'], 'segments': {}})
            rec.update(start=g.get('start'), event=e['id'], pulled=now.isoformat(timespec='seconds'))
            for seg, mk in lines.items():
                for m, line in mk.items():
                    rec.setdefault('segments', {}).setdefault(seg, {})[m] = {k: v for k, v in line.items() if k != 'books'}
                    rec.setdefault('books', {}).setdefault(seg, {})[m] = rows[seg][m]
                    U.note_opens(rec, seg, m, rows[seg][m])
            status['pulled'] += 1
    if gaps:
        status['safety'] = len(gaps)
    new = {'status': status, 'unmatched': unmatched, 'games': games_doc}
    old = U.read_json(path, {})
    if any(old.get(k) != v for k, v in new.items() if k != 'status') or status['pulled']:
        U.write_json(path, dict(new, updated=now.isoformat(timespec='seconds')))
    print(f"{sport}: {len(games)} games in the next 36 hours, {len(todo)} due, {status['pulled']} pulled, "
          f"{status['failed']} failed, {len(unmatched)} unmatched events")


# ------------------------------------------------------------ breaks
def season_games(sport):
    """{game key: game} of this season, with ESPN's (or the NHL's) state and detail."""
    if sport == 'nhl':
        out = {}
        for name in ('schedule_data.json', 'schedule_fresh.json'):
            for d, gs in (U.read_json(os.path.join(A.ROOT, name), {}).get('games') or {}).items():
                for g in gs:
                    out[f"{d}|{g['away']}|{g['home']}"] = {'date': d, 'away': g['away'], 'home': g['home'],
                                                           'start': g.get('startTimeUTC'), 'detail': g.get('detail') or '',
                                                           'state': {'LIVE': 'in', 'CRIT': 'in', 'FINAL': 'final',
                                                                     'OFF': 'final'}.get(g.get('state'), 'pre')}
        return out
    season, games = (B.seasons_for(sport).get('this') or (None, []))
    d = os.path.join(A.ROOT, 'data_seed', 'games', sport, f'{season}.json')
    return {f"{g['date']}|{g['away']}|{g['home']}": g for g in (U.read_json(d, {}).get('games') or {}).values()}


def at_break(sport, g):
    detail = (g.get('detail') or '').lower()
    if g.get('state') not in ('in', 'live'):
        return None
    if sport == 'nhl':
        return 'p1' if detail.startswith('end 1st') else None
    return 'half' if detail.startswith('halftime') else None


def note_breaks(now, sps):
    doc = U.read_json(BREAKS, {})
    seen = 0
    for sport in sps:
        if sport == 'mlb':
            continue
        for key, g in season_games(sport).items():
            b = at_break(sport, g)
            if b and key not in doc.get(sport, {}):
                doc.setdefault(sport, {})[key] = {'break': b, 'seen_at': now.isoformat(timespec='seconds')}
                seen += 1
    if seen:
        U.write_json(BREAKS, doc)
    return seen


def capture_breaks(now, sps):
    """Yesterday's finished games: the line at the break, saved for grading."""
    status = U.read_json(STATUS, {})
    et = now.astimezone(A.ET)
    yesterday = (et.date() - timedelta(days=1)).isoformat()
    if et.hour < CAPTURE_HOUR or status.get('breaks_done') == yesterday:
        return None
    breaks, report = U.read_json(BREAKS, {}), {}
    for sport in sps:
        if sport == 'mlb':
            continue
        seg, markets = break_markets(sport)
        season = (B.seasons_for(sport).get('this') or (None,))[0]
        hist_path = os.path.join(HISTORY_DIR, sport, f'{season}.json')
        hist = U.read_json(hist_path, {'games': {}})
        live = U.read_json(os.path.join(A.OUT_DIR, sport + '.json'), {}).get('games') or {}
        finals = {k: g for k, g in season_games(sport).items() if g.get('date') == yesterday and g.get('state') in ('final', 'post')}
        mine = breaks.setdefault(sport, {})
        events = None
        got = missed = 0
        for key, g in finals.items():
            b = mine.setdefault(key, {'break': 'p1' if sport == 'nhl' else 'half'})
            if b.get('result'):
                continue
            event = (live.get(key) or {}).get('event')
            start = A.parse(g.get('start'))
            if not start:
                continue
            if not event:   # never pulled live: the day's events list (1 credit)
                if events is None:
                    day = datetime.fromisoformat(yesterday).replace(tzinfo=A.ET)
                    events = (A.historical_events(sport, start, day, day + timedelta(days=1)) or {}).get('data') or []
                pairs, _ = A.match(sport, events, [g])
                event = pairs[0][0]['id'] if pairs else None
            if not event:
                b['result'] = 'no line'
                missed += 1
                continue
            at = A.parse(b.get('seen_at')) or start + timedelta(minutes=BREAK_MINUTES[sport])
            line = None
            for extra in (0, 5, 10):
                resp = A.historical_event_odds(sport, event, at + timedelta(minutes=extra), list(markets.values())) or {}
                data = resp.get('data') or {}
                names = (data.get('away_team'), data.get('home_team'))
                lines, books = B.closing(sport, data.get('bookmakers'), [(seg, m, k) for m, k in markets.items()], *names)
                if lines:
                    line = (lines, books, resp.get('timestamp'))
                    break
            if not line:
                b['result'] = 'no line'
                missed += 1
                continue
            lines, books, snap = line
            row = hist['games'].setdefault(key, {'date': g['date'], 'away': g['away'], 'home': g['home'], 'start': g.get('start'),
                                                 'source': 'oddsapi', 'segments': {}, 'books': {}})
            if names_flipped(g, names, sport):
                lines, books = flip(lines), flip(books)
            row['segments'][seg] = lines[seg]
            row['books'][seg] = books[seg]
            row[seg + '_snapshot'] = snap
            b['result'] = 'saved'
            got += 1
        if got:
            U.write_json(hist_path, hist)
        report[sport] = {'saved': got, 'no_line': missed}
    U.write_json(BREAKS, breaks)
    U.write_json(STATUS, dict(U.read_json(STATUS, {}), breaks_done=yesterday,
                              breaks_report=dict(report, date=yesterday)))
    return report


def names_flipped(g, names, sport):
    """Whether the API lists the game's teams the other way round (a neutral site)."""
    if not all(names):
        return False
    pairs, _ = A.match(sport, [{'away_team': names[0], 'home_team': names[1], 'commence_time': g.get('start')}],
                       [{k: g.get(k) for k in ('date', 'away', 'home', 'start', 'away_name', 'home_name')}])
    return bool(pairs and pairs[0][2])


def flip(tree):
    """Swaps away and home everywhere in a lines or books tree."""
    if isinstance(tree, dict):
        return {{'away': 'home', 'home': 'away'}.get(k, k): flip(v) for k, v in tree.items()}
    return tree


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--hourly', action='store_true', help='the hourly pull (the closing capture always runs)')
    args = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    sps = [s['key'] for s in sports.IN_SEASON]
    print(f'breaks seen this run: {note_breaks(now, sps)}')
    if not A.key():
        print('WARN: ODDS_API_KEY not set -- skipping The Odds API live odds', file=sys.stderr)
        return 0
    A.JOB = 'live'
    today, _ = live_usage(now)
    hourly = args.hourly and (today <= daily_share(now) or now.astimezone(A.ET).hour % 2 == 0)
    if args.hourly and not hourly:
        print(f"today's live usage ({today:,}) is past the daily share ({daily_share(now):,.0f}): the hourly pull waits for an even hour")
    for sport in sps:
        try:
            pull_sport(sport, now, hourly)
        except (A.BudgetExceeded, A.BelowFloor) as e:
            print(f'{sport}: stopped -- {e}')
            break
        except Exception as e:   # one sport's surprise shouldn't stop the others
            print(f'{sport}: skipped -- {e.__class__.__name__}: {e}', file=sys.stderr)
    try:
        report = capture_breaks(now, sps)
        if report is not None:
            print(f'break lines for yesterday: {report}')
    except (A.BudgetExceeded, A.BelowFloor) as e:
        print(f'break lines: stopped -- {e}')
    write_status(now)
    print(f'The Odds API: {A.used():,} credits this run, {A.remaining() if A.remaining() is not None else "?"} remaining')
    return 0


if __name__ == '__main__':
    sys.exit(main())
