"""
Edges lead buckets (Stats > Edges, "Does the leader hold on?"): the cutoffs
per sport and segment that split the season's leads into three buckets of
about a third of the games each -- small (1..a), medium (a+1..b), big (b+1+).

Recomputed from the data every build, but a saved cutoff only moves when the
new one is 2+ points away, so the labels don't jump around day to day. The
saved values live in content/lead_cuts.json; data.json carries them as
leadCuts and assets/sport.js reads them (its LEAD_CUTS table is the
fallback). NHL and MLB keep their fixed 1 / 2 / 3+ goals or runs: leads that
small can't be split into thirds.
"""
import os

from sport_build import read_json, write_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'content', 'lead_cuts.json')
FIXED = {'nhl': {'1p': [1, 2]}, 'mlb': {'1i': [1, 2], 'f5': [1, 3]}}
MOVE = 2      # a cutoff changes only when the data moves it this far
MIN_GAMES = 30


def thirds(leads):
    """[a, b]: the whole-number cutoffs that leave the counts at or under each
    closest to a third and two thirds of the games."""
    leads = sorted(leads)
    n = len(leads)

    def upto(c):
        return sum(1 for x in leads if x <= c)
    vals = sorted(set(leads))
    a = min(vals, key=lambda c: (abs(upto(c) - n / 3), c))
    b = min((c for c in vals if c > a), key=lambda c: (abs(upto(c) - 2 * n / 3), c), default=a + 1)
    return [a, b]


def leads(games, k):
    """The leader's margin after segment k in every finished, graded game."""
    out = []
    for day in (games or {}).values():
        for g in day:
            r = (g.get('res') or {}).get(k) or {}
            sc = r.get('sc')
            if g.get('state') == 'final' and sc and not r.get('na') and sc[0] != sc[1]:
                out.append(abs(sc[0] - sc[1]))
    return out


def update(sport_key, segments, games):
    """{segment: [a, b]} for the sport, saved to content/lead_cuts.json."""
    if sport_key in FIXED:
        return FIXED[sport_key]
    saved = read_json(PATH, {})
    mine = saved.setdefault(sport_key, {})
    for s in segments:
        k = s['key']
        found = leads(games, k)
        if len(found) < MIN_GAMES:
            continue
        new = thirds(found)
        old = mine.get(k)
        if not old:
            mine[k] = new
        else:
            mine[k] = [n if abs(n - o) >= MOVE else o for n, o in zip(new, old)]
            if mine[k][1] <= mine[k][0]:
                mine[k] = new
    write_json(PATH, saved)
    return {k: v for k, v in mine.items() if k in {s['key'] for s in segments}}
