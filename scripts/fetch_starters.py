"""
Starting pitchers (MLB) and starting goalies (NHL), from the leagues' free
public APIs (no keys).

MLB (statsapi.mlb.com): each finished game's starters from its box score
(the first pitcher each side used), and the probable pitchers for the next
7 days (the schedule's probablePitcher), matched to our games by ET date
and both teams' names (a doubleheader by start order). Saved in
data_feed/starters/mlb/{season}.json as {our game id: {away_sp, home_sp}},
each {id, name, throws}; a probable carries "probable": true until the
game's box score replaces it. sport_build puts them on data.json (asp / hsp).

NHL (api-web.nhle.com): the finished games' starters come with the period
backfill (backfill_periods.py -> awayGoalie / homeGoalie; the 2025-26
archive has them already). Tonight: a game starting within NHL_SOON hours
whose box score lists a starter is saved as "confirmed" on schedule_data.json;
until then nhl_sport marks the team's last starter "expected".

  python3 scripts/fetch_starters.py            the refresh: NHL every run,
                                               MLB once a day
  python3 scripts/fetch_starters.py --backfill both MLB seasons in full
"""
import json
import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_schedule import fetch_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
OUT = os.path.join(ROOT, 'data_feed', 'starters')
MLB_API = 'https://statsapi.mlb.com/api/v1'
MLB_TYPES = 'R,F,D,L,W'     # regular season and the postseason rounds
PROBABLE_DAYS = 7
NHL_SOON = 3                # hours before the start to look for a confirmed goalie
WORKERS = 8


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write('\n')


def norm(name):
    s = unicodedata.normalize('NFKD', name or '').encode('ascii', 'ignore').decode().lower()
    return ''.join(c for c in s if c.isalnum())


def et_date(iso):
    t = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return t.astimezone(ET).date().isoformat()


# -------------------------------------------------------------------- MLB
def mlb_seasons():
    """The two latest seasons we have games for (this one and last)."""
    d = os.path.join(ROOT, 'data_seed', 'games', 'mlb')
    return sorted(int(n[:4]) for n in os.listdir(d) if n[:4].isdigit() and n.endswith('.json'))[-2:] if os.path.isdir(d) else []


def mlb_games(season):
    """Our games for a season (data_seed/games/mlb/{season}.json)."""
    doc = read_json(os.path.join(ROOT, 'data_seed', 'games', 'mlb', f'{season}.json'), {})
    return [g for g in (doc.get('games') or {}).values() if g.get('season_type') in (2, 3)]


def mlb_schedule(start, end, probables=False):
    """[statsapi game] between two dates (local dates, inclusive)."""
    url = f'{MLB_API}/schedule?sportId=1&gameType={MLB_TYPES}&startDate={start}&endDate={end}'
    if probables:
        url += '&hydrate=probablePitcher'
    data = fetch_json(url, timeout=60) or {}
    return [g for d in data.get('dates') or [] for g in d.get('games') or []]


def match_mlb(ours, theirs):
    """{our id: statsapi game}: the same ET date and both teams' names; two
    games between the same teams that day pair up in start order."""
    by_key = {}
    for g in sorted(theirs, key=lambda g: (g.get('gameDate') or '', g.get('gameNumber') or 1)):
        if (g.get('status') or {}).get('detailedState') in ('Postponed', 'Cancelled'):
            continue
        t = g.get('teams') or {}
        key = (et_date(g['gameDate']), norm(t['away']['team']['name']), norm(t['home']['team']['name']))
        by_key.setdefault(key, []).append(g)
    out = {}
    for g in sorted(ours, key=lambda g: (g.get('start') or '', g['id'])):
        key = (g['date'], norm(g.get('away_name')), norm(g.get('home_name')))
        if by_key.get(key):
            out[str(g['id'])] = by_key[key].pop(0)
    return out


def box_starters(game_pk):
    """{away: id, home: id}: the first pitcher each side used, or None."""
    box = fetch_json(f'{MLB_API}/game/{game_pk}/boxscore', timeout=30)
    if not box:
        return None
    out = {}
    for side in ('away', 'home'):
        ps = ((box.get('teams') or {}).get(side) or {}).get('pitchers') or []
        if not ps:
            return None
        out[side] = ps[0]
    return out


def people(ids):
    """{id: {id, name, throws}} in batches of 100."""
    ids = sorted({i for i in ids if i})
    out = {}
    for i in range(0, len(ids), 100):
        data = fetch_json(f'{MLB_API}/people?personIds={",".join(map(str, ids[i:i + 100]))}', timeout=30) or {}
        for p in data.get('people') or []:
            out[p['id']] = {'id': p['id'], 'name': p.get('fullName'), 'last': p.get('lastName'),
                            'throws': (p.get('pitchHand') or {}).get('code')}
    return out


def mlb_season(season, full=False, today=None):
    """Fill the season's file: finished games' starters (box scores; full:
    every game, else only the ones not saved yet or saved as probables) and
    the probables for the next PROBABLE_DAYS days."""
    today = today or datetime.now(ET).date().isoformat()
    ours = mlb_games(season)
    if not ours:
        return 0
    path = os.path.join(OUT, 'mlb', f'{season}.json')
    saved = {} if full else read_json(path, {})
    dates = sorted(g['date'] for g in ours)
    # local dates run a day either side of ET dates
    first = (datetime.fromisoformat(dates[0]) - timedelta(days=1)).date().isoformat()
    last = (datetime.fromisoformat(dates[-1]) + timedelta(days=1)).date().isoformat()
    pairs = match_mlb(ours, mlb_schedule(first, last))
    finals = {str(g['id']) for g in ours if g.get('final') or g.get('state') == 'final'}
    todo = [gid for gid in pairs if gid in finals and (gid not in saved or saved[gid].get('probable'))]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        got = dict(zip(todo, pool.map(lambda gid: box_starters(pairs[gid]['gamePk']), todo)))
    # the probables: our games still to play in the next week
    end = (datetime.fromisoformat(today) + timedelta(days=PROBABLE_DAYS)).date().isoformat()
    soon = [g for g in ours if str(g['id']) not in finals and today <= g['date'] <= end]
    probs = {}
    if soon:
        for gid, sg in match_mlb(soon, mlb_schedule(today, end, probables=True)).items():
            t = sg.get('teams') or {}
            probs[gid] = {side: ((t.get(side) or {}).get('probablePitcher') or {}).get('id') for side in ('away', 'home')}
    who = people([i for x in list(got.values()) + list(probs.values()) if x for i in x.values()])
    for gid, x in got.items():
        if x and x['away'] in who and x['home'] in who:
            saved[gid] = {'away_sp': who[x['away']], 'home_sp': who[x['home']]}
    for gid, x in probs.items():
        if gid in finals:
            continue
        row = {f'{side}_sp': who[x[side]] for side in ('away', 'home') if x.get(side) in who}
        if row:
            saved[gid] = dict(row, probable=True)
        else:
            saved.pop(gid, None)
    write_json(path, saved)
    print(f'starters mlb {season}: {sum(1 for v in saved.values() if not v.get("probable"))} games with starters, '
          f'{sum(1 for v in saved.values() if v.get("probable"))} with probables, {len(todo) - sum(1 for v in got.values() if v)} box scores missing')
    return len(saved)


def load_mlb(season):
    """{our game id: {away_sp, home_sp, probable?}} (sport_build)."""
    return read_json(os.path.join(OUT, 'mlb', f'{season}.json'), {})


# -------------------------------------------------------------------- NHL
def nhl_box_goalies(game_id):
    """{away: {id, name}, home: ...} once the box score lists the starters, else None."""
    box = fetch_json(f'https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore') or {}
    out = {}
    for side, key in (('away', 'awayTeam'), ('home', 'homeTeam')):
        gs = ((box.get('playerByGameStats') or {}).get(key) or {}).get('goalies') or []
        st = next((g for g in gs if g.get('starter')), None)
        if not st:
            return None
        out[side] = {'id': st.get('playerId'), 'name': (st.get('name') or {}).get('default')}
    return out


def nhl_tonight(now=None, fetch=nhl_box_goalies):
    """Games starting within NHL_SOON hours (or under way) whose box score
    lists the starters: saved as confirmed on schedule_data.json."""
    now = now or datetime.now(timezone.utc)
    path = os.path.join(ROOT, 'schedule_data.json')
    data = read_json(path, None)
    if not data:
        return 0
    n = 0
    for gs in (data.get('games') or {}).values():
        for g in gs:
            if g.get('state') in ('FINAL', 'OFF') or not g.get('startTimeUTC') or not g.get('id'):
                continue
            if (g.get('awayGoalie') or {}).get('status') == 'confirmed':
                continue
            start = datetime.fromisoformat(g['startTimeUTC'].replace('Z', '+00:00'))
            if not (start - timedelta(hours=NHL_SOON) <= now <= start + timedelta(hours=4)):
                continue
            got = fetch(g['id'])
            if got:
                g['awayGoalie'] = dict(got['away'], status='confirmed')
                g['homeGoalie'] = dict(got['home'], status='confirmed')
                n += 1
    if n:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, separators=(',', ':'))
    print(f'starters nhl: {n} games with confirmed goalies')
    return n


def main(argv):
    full = '--backfill' in argv
    nhl_tonight()
    stamp = os.path.join(OUT, 'mlb', 'last_run.txt')
    today = datetime.now(ET).date().isoformat()
    last = open(stamp).read().strip() if os.path.exists(stamp) else ''
    if full or last != today:
        for season in mlb_seasons():
            mlb_season(season, full=full, today=today)
        os.makedirs(os.path.dirname(stamp), exist_ok=True)
        with open(stamp, 'w') as f:
            f.write(today + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])
