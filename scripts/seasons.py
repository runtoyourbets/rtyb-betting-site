"""
Each sport's season state, worked out at build time from its schedule
(data.json; NHL: sport.json) and the dates in Site settings that the
schedule doesn't have (content/site_settings.json "seasons": OPENING_DAY and
up to two MILESTONES per sport, edited in the admin's Site settings tab).

  game_day     in season, games today
  no_games     in season, no games today (off days, All-Star break, holidays)
  weekly       NFL and College Football in season (run by the week)
  early        the first 21 days of the regular season
  postseason   playoffs, bowls, tournaments
  just_ended   the 14 days after the final game of the postseason
  off          no games in the coming 14+ days
  preseason    only exhibition games ahead (the schedule holds no
               exhibitions, so: a milestone named for spring training, the
               preseason or exhibitions has passed and opening day hasn't)

Each state picks one of three hub layouts (scripts/front.py sections):
'game_day', 'no_games' or 'off'. The build logs every sport's state and
writes them to assets/seasons.json (the admin's Site settings tab shows them).
"""
import os
import re
from datetime import date as Date, datetime, timezone
from zoneinfo import ZoneInfo

import sports
from sport_build import read_json, write_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
OUT = os.path.join(ROOT, 'assets', 'seasons.json')
EARLY_DAYS = 21     # the regular season's first days: "Early season"
ENDED_DAYS = 14     # after the final: "Season just ended"
AHEAD_DAYS = 14     # no games this far ahead: the off-season
LABELS = {'game_day': 'Game day', 'no_games': 'No games today', 'weekly': 'Weekly', 'early': 'Early season',
          'postseason': 'Postseason', 'just_ended': 'Season just ended', 'off': 'Off-season', 'preseason': 'Preseason'}
PRESEASON_WORDS = re.compile(r'spring training|preseason|pre-season|exhibition', re.I)
GAME_NO = re.compile(r'Game (\d+)')


def doc_path(sp):
    return os.path.join(ROOT, sp['slug'], 'sport.json' if sp['key'] == 'nhl' else 'data.json')


def dates_of(key):
    """{opening: 'YYYY-MM-DD' or None, milestones: [{label, date}]} from Site settings."""
    x = (sports.SEASON_DATES or {}).get(key) or {}
    ok = re.compile(r'\d{4}-\d{2}-\d{2}$')
    opening = str(x.get('OPENING_DAY') or '')
    ms = [{'label': str(m.get('label') or '').strip(), 'date': str(m.get('date') or '')}
          for m in (x.get('MILESTONES') or [])[:2] if isinstance(m, dict)]
    return {'opening': opening if ok.match(opening) else None,
            'milestones': [m for m in ms if m['label'] and ok.match(m['date'])]}


def played(g):
    return g.get('state') in ('in', 'final', 'post')


def series_of(post_games):
    """[[(date, game), ...]] postseason series: the same two teams, back to back."""
    out, idx = [], {}
    for d, g in post_games:
        pair = frozenset((g['away'], g['home']))
        if pair in idx and out[idx[pair]][-1] is not None:
            out[idx[pair]].append((d, g))
        else:
            idx[pair] = len(out)
            out.append([(d, g)])
    return out


def series_score(games):
    """{team: wins} over the series' final games."""
    wins = {}
    for _, g in games:
        a, h = g.get('as'), g.get('hs')
        if g.get('state') not in ('final', 'post') or not isinstance(a, (int, float)) or not isinstance(h, (int, float)) or a == h:
            continue
        w = g['away'] if a > h else g['home']
        wins[w] = wins.get(w, 0) + 1
    return wins


def decided(games):
    """Whether a series is over: a team has the wins its length needs
    (best of 7 from "Game 7" in the notes; a single game once it's final)."""
    nums = [int(m.group(1)) for _, g in games for m in [GAME_NO.search(str(g.get('note') or ''))] if m]
    need = max(nums) // 2 + 1 if nums else 1
    return any(w >= need for w in series_score(games).values())


def schedule(doc, today):
    """(played, ahead): the season's games played, and the ones still to
    come from today on (a decided series' "If necessary" games left out)."""
    games = [(d, g) for d in sorted(doc.get('games') or {}) for g in doc['games'][d]
             if g.get('state') not in ('postponed', 'canceled', 'cancelled')]
    done = [(d, g) for d, g in games if played(g)]
    skip = set()
    for s in series_of([(d, g) for d, g in games if g.get('post')]):
        if decided(s):
            skip |= {id(g) for _, g in s if not played(g)}
    ahead = [(d, g) for d, g in games if d >= today and not played(g) and id(g) not in skip]
    ahead += [(d, g) for d, g in games if d == today and g.get('state') == 'in']
    return done, sorted(ahead, key=lambda x: (x[0], x[1].get('start') or ''))


def days_between(a, b):
    return (Date.fromisoformat(b) - Date.fromisoformat(a)).days


def state(sp, doc, now_utc=None):
    """{key, label, layout, next, opening, milestones, first, last}: the sport's
    state today. next: the next game day (in season); first: the regular
    season's first game day; last: the final game day played."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    done, ahead = schedule(doc, today)
    soon = [x for x in ahead if days_between(today, x[0]) < AHEAD_DAYS]
    reg = sorted(d for d in (doc.get('games') or {}) for g in doc['games'][d] if not g.get('post'))
    first = reg[0] if reg else None
    last = done[-1][0] if done else None
    dates = dates_of(sp['key'])
    weekly = sp.get('schedule') == 'week'
    out = {'next': soon[0][0] if soon else None, 'first': first, 'last': last, **dates}
    if soon:
        today_games = any(d == today for d, _ in soon)
        if any(g.get('post') for _, g in soon):
            key = 'postseason'
        elif first and 0 <= days_between(first, today) < EARLY_DAYS:
            key = 'early'
        elif weekly:
            key = 'weekly'
        else:
            key = 'game_day' if today_games else 'no_games'
        layout = 'game_day' if today_games or weekly else 'no_games'
    else:
        final_post = done and done[-1][1].get('post')
        passed = [m for m in dates['milestones'] if PRESEASON_WORDS.search(m['label']) and m['date'] <= today]
        if final_post and days_between(last, today) <= ENDED_DAYS:
            key = 'just_ended'
        elif passed and dates['opening'] and dates['opening'] > today:
            key = 'preseason'
        else:
            key = 'off'
        layout = 'off'
    return dict(out, key=key, label=LABELS[key], layout=layout)


def champion(doc):
    """{team, opp, wins, losses, score, date, note} for the season's final
    (the winner of the last postseason series or game), or None."""
    if not isinstance(doc.get('games'), dict):
        return None   # NHL's history.json is its own shape (no playoffs)
    post = [(d, g) for d in sorted(doc['games']) for g in doc['games'][d] if g.get('post')]
    final = next((s for s in reversed(series_of(post)) if any(g.get('state') in ('final', 'post') for _, g in s)), None)
    if not final or not decided(final):
        return None
    wins = series_score(final)
    team = max(wins, key=wins.get)
    last = [x for x in final if x[1].get('state') in ('final', 'post')][-1]
    g = last[1]
    opp = g['home'] if g['away'] == team else g['away']
    mine, theirs = (g['as'], g['hs']) if g['away'] == team else (g['hs'], g['as'])
    return {'team': team, 'opp': opp, 'wins': wins.get(team, 0), 'losses': wins.get(opp, 0),
            'score': [mine, theirs], 'date': last[0], 'note': g.get('note') or ''}


def all_states(now_utc=None):
    """{key: state} for every sport (hidden ones too), logged and written to
    assets/seasons.json for the admin."""
    now_utc = now_utc or datetime.now(timezone.utc)
    out = {}
    for sp in sports.SPORTS:
        doc = read_json(doc_path(sp), {}) or {}
        out[sp['key']] = state(sp, doc, now_utc)
    write_json(OUT, {'generated': now_utc.strftime('%Y-%m-%dT%H:%MZ'),
                     'sports': {k: {x: v[x] for x in ('key', 'label', 'layout', 'next', 'first', 'last', 'opening')} for k, v in out.items()}})
    print('season states: ' + ', '.join(f"{k} {v['label']}" for k, v in out.items()))
    return out


_CACHE = {}


def of(sp, doc=None, now_utc=None):
    """One sport's state (computed once per build)."""
    if sp['key'] not in _CACHE:
        _CACHE[sp['key']] = state(sp, doc if doc is not None else (read_json(doc_path(sp), {}) or {}), now_utc)
    return _CACHE[sp['key']]
