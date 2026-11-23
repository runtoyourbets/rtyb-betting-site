"""
The Odds API (v4) client shared by the probe (scripts/oddsapi_probe.py),
the backfill and the live pulls.

The key comes from env ODDS_API_KEY (a GitHub Actions secret) and is never
printed, logged or written to a file: every call's usage goes to
data_feed/oddsapi/usage.jsonl as {time, endpoint, sport, credits, remaining,
job} with the endpoint's path only (job: "live" for the live pulls, whose
budget counts only those rows).

Safety: BUDGET (credits this run) raises BudgetExceeded before a call that
could pass it; nothing is called once x-requests-remaining is under FLOOR
(the reserve for a month of live pulls). 429 / 5xx back off and retry 3
times, then the call is skipped and logged. A network failure never raises
past this module (callers get None).

Books: bookmakers= (not regions), at most 10 so a call bills as one region.
Cost: event lists are free, event_markets and historical_events 1 credit,
event odds 1 x markets returned, historical event odds 10 x markets returned.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fetch_odds_unabated as U  # noqa: E402  (team aliases and matching)

BASE = 'https://api.the-odds-api.com/v4'
OUT_DIR = os.path.join(ROOT, 'data_feed', 'oddsapi')
USAGE = os.path.join(OUT_DIR, 'usage.jsonl')
ET = ZoneInfo('America/New_York')

SPORT_KEYS = {'nhl': 'icehockey_nhl', 'nba': 'basketball_nba', 'wnba': 'basketball_wnba', 'mlb': 'baseball_mlb',
              'ncaab': 'basketball_ncaab', 'nfl': 'americanfootball_nfl', 'ncaaf': 'americanfootball_ncaaf'}

# our segments -> the API's market keys (sports.py segments; ml / ats / total / ml3 / btts / nrfi_yrfi)
_QH = {'1q': {'ml': 'h2h_q1', 'ats': 'spreads_q1', 'total': 'totals_q1'},
       '1h': {'ml': 'h2h_h1', 'ats': 'spreads_h1', 'total': 'totals_h1'}}
MARKETS = {
    'nhl': {'1p': {'ml': 'h2h_p1', 'total': 'totals_p1', 'ml3': 'h2h_3_way_p1', 'btts': 'btts_p1'}},
    'nba': _QH, 'wnba': _QH, 'nfl': _QH, 'ncaaf': _QH,
    'ncaab': {'1h': _QH['1h']},
    # NRFI = Under 0.5, YRFI = Over 0.5 of the 1st-inning total
    'mlb': {'1i': {'nrfi_yrfi': 'totals_1st_1_innings'},
            'f5': {'ml': 'h2h_1st_5_innings', 'ats': 'spreads_1st_5_innings', 'total': 'totals_1st_5_innings'}},
}
GAME = {'ml': 'h2h', 'ats': 'spreads', 'total': 'totals'}   # the full game (segment "game")

BOOKS = ('draftkings', 'fanduel', 'betmgm', 'williamhill_us', 'espnbet', 'fanatics', 'betrivers', 'hardrockbet',
         'bovada', 'betonlineag')

FLOOR = 250_000      # never call below this many credits remaining
BUDGET = None        # credits this run may use (None: no cap); set by the caller
JOB = None           # "live" for fetch_odds_theoddsapi.py (its budget reads these rows)
TRIES = 3


class BudgetExceeded(Exception):
    pass


class BelowFloor(Exception):
    pass


_state = {'used': 0, 'remaining': None}


def key():
    return os.environ.get('ODDS_API_KEY', '').strip()


def market_keys(sport):
    """The sport's first-segment market keys, in order."""
    return [k for seg in MARKETS[sport].values() for k in seg.values()]


def used():
    """Credits this run has used."""
    return _state['used']


def remaining():
    return _state['remaining']


def log_usage(endpoint, sport, credits, left):
    os.makedirs(OUT_DIR, exist_ok=True)
    row = {'time': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'endpoint': endpoint, 'sport': sport,
           'credits': credits, 'remaining': left}
    if JOB:
        row['job'] = JOB
    with open(USAGE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def call(path, params, sport, cost):
    """GET BASE + path; cost = the most credits it can bill (checked against
    BUDGET first). Returns the JSON, or None on failure / an empty answer."""
    if not key():
        print(f'oddsapi: no ODDS_API_KEY; {path} skipped')
        return None
    if BUDGET is not None and _state['used'] + cost > BUDGET:
        raise BudgetExceeded(f'{path}: would pass this run\'s budget of {BUDGET} credits ({_state["used"]} used)')
    if _state['remaining'] is not None and _state['remaining'] < FLOOR:
        raise BelowFloor(f'{_state["remaining"]} credits remaining is under the {FLOOR} floor')
    query = dict(params, apiKey=key(), oddsFormat='american', dateFormat='iso')
    url = BASE + path + '?' + urllib.parse.urlencode(query)
    for attempt in range(TRIES + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'rtyb-oddsapi'})
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode('utf-8') or 'null')
                _account(path, sport, r.headers)
                return data
        except urllib.error.HTTPError as e:
            _account(path, sport, e.headers)
            if e.code in (429, 500, 502, 503, 504) and attempt < TRIES:
                time.sleep(2 ** attempt * 2)
                continue
            print(f'oddsapi: {path} HTTP {e.code}; skipped')
            return None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            if attempt < TRIES:
                time.sleep(2 ** attempt * 2)
                continue
            print(f'oddsapi: {path} failed ({type(e).__name__}); skipped')
            return None
    return None


def _account(path, sport, headers):
    if headers is None:
        return
    last, left = _int(headers.get('x-requests-last')), _int(headers.get('x-requests-remaining'))
    if left is not None:
        _state['remaining'] = left
    if last is not None:
        _state['used'] += last
        log_usage(path, sport, last, left)


def _books(books):
    return ','.join((books or BOOKS)[:10])


def iso(t):
    return t.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ------------------------------------------------------------ endpoints
def events(sport, start=None, end=None):
    """Upcoming events (free)."""
    p = {}
    if start:
        p['commenceTimeFrom'] = iso(start)
    if end:
        p['commenceTimeTo'] = iso(end)
    return call(f'/sports/{SPORT_KEYS[sport]}/events', p, sport, 0) or []


def event_markets(sport, event_id, books=None):
    """{book: [market keys]} the books list for an event (1 credit)."""
    data = call(f'/sports/{SPORT_KEYS[sport]}/events/{event_id}/markets', {'bookmakers': _books(books)}, sport, 1)
    return {b['key']: [m['key'] for m in b.get('markets') or []] for b in (data or {}).get('bookmakers') or []}


def event_odds(sport, event_id, markets, books=None):
    """An event's odds now (1 x markets returned)."""
    return call(f'/sports/{SPORT_KEYS[sport]}/events/{event_id}/odds',
                {'markets': ','.join(markets), 'bookmakers': _books(books)}, sport, len(markets))


def historical_events(sport, at, start=None, end=None):
    """The events listed at snapshot time `at` (1 credit): {timestamp, data: [...]}."""
    p = {'date': iso(at)}
    if start:
        p['commenceTimeFrom'] = iso(start)
    if end:
        p['commenceTimeTo'] = iso(end)
    return call(f'/historical/sports/{SPORT_KEYS[sport]}/events', p, sport, 1)


def historical_event_odds(sport, event_id, at, markets, books=None):
    """An event's odds at snapshot time `at` (10 x markets returned): {timestamp, data: {bookmakers: [...]}}."""
    return call(f'/historical/sports/{SPORT_KEYS[sport]}/events/{event_id}/odds',
                {'date': iso(at), 'markets': ','.join(markets), 'bookmakers': _books(books)}, sport, 10 * len(markets))


def historical_odds(sport, at, markets, books=None):
    """A whole slate's featured-market odds at `at` (10 x markets x regions)."""
    return call(f'/historical/sports/{SPORT_KEYS[sport]}/odds',
                {'date': iso(at), 'markets': ','.join(markets), 'bookmakers': _books(books)}, sport, 10 * len(markets))


# ------------------------------------------------------------ matching
def parse(s):
    return U.parse_time(s)


COLLEGE = ('ncaab', 'ncaaf')


def api_name(sport, name):
    """An event's team name as our names read it. College only: "St" is
    "State" anywhere in the name ("Morehead St Eagles"), and a school the
    feeds spell differently is renamed by its leading words (U.ALIASES:
    "IUPUI Jaguars" -> "iu indianapolis jaguars")."""
    n = U.norm(name)
    if sport not in COLLEGE:
        return name
    n = re.sub(r' st(?= |$)', ' state', n)
    if n in WHOLE_NAMES:
        return WHOLE_NAMES[n]
    for k in sorted(U.ALIASES, key=len, reverse=True):
        if n == k or n.startswith(k + ' '):
            return U.ALIASES[k] + n[len(k):]
    return n


# a college name the API gives with no nickname, renamed only when it's the whole name
# ("Albany", never "Albany State Golden Rams")
WHOLE_NAMES = {'albany': 'ualbany great danes'}
NEXT_DAY_HOUR = 6   # a placeholder-start game can tip after midnight ET, up to this hour


def tbd(t):
    """ESPN's placeholder start for a game with no time yet: 11:59 PM ET."""
    t = t.astimezone(ET)
    return (t.hour, t.minute) == (23, 59)


def match(sport, api_events, games):
    """Odds API events -> our games: the same ET date and both teams (the
    Unabated feed's aliases and match_event, which wants the starts within 4
    hours; a game whose start is ESPN's 11:59 PM ET placeholder matches on the
    date and both teams alone, or on both teams and a tip before NEXT_DAY_HOUR
    ET the next day: Hawai'i and West Coast late tips). Returns ([(event, game,
    flipped)], [unmatched events]); unmatched events are listed, never guessed.
    games: [{away, home, start, away_name?, home_name?}]."""
    aliases = {slug: set(names) for slug, names in U.team_aliases(sport).items()}
    for names in aliases.values():   # "LA Clippers" is "Los Angeles Clippers" here
        names |= {'los angeles ' + n[3:] for n in names if n.startswith('la ')}
    for g in games:   # teams outside the league (non-Division I opponents): the game's own names
        for side in ('away', 'home'):
            if g.get(side) not in aliases and g.get(side + '_name'):
                aliases[g[side]] = {U.norm(g[side + '_name'])}
    pool = []
    for g in games:
        t = parse(g.get('start'))
        if t:
            pool.append(dict(g, _start=t))
    pairs, missed = [], []
    for e in api_events or []:
        t = parse(e.get('commence_time'))
        day = t.astimezone(ET).date() if t else None
        late = t and t.astimezone(ET).hour < NEXT_DAY_HOUR
        same_day = [dict(g, _start=t) if tbd(g['_start']) else g for g in pool if day and (
            g['_start'].astimezone(ET).date() == day
            or late and tbd(g['_start']) and g['_start'].astimezone(ET).date() == day - timedelta(days=1))]
        g, flipped = U.match_event(api_name(sport, e.get('away_team')), api_name(sport, e.get('home_team')), t, same_day, aliases) if t else (None, False)
        if g:
            pairs.append((e, {k: v for k, v in g.items() if k != '_start'}, flipped))
        else:
            missed.append(e)
    return pairs, missed


def before(t, minutes):
    return t - timedelta(minutes=minutes)
