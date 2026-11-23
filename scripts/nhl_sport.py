"""
NHL games in the shared sport shape (assets/sport.js, assets/situational.js),
so NHL's Stats page is drawn by the same code as every other sport's.

Written to nhl/sport.json by build_site.py. One segment, the 1st period:
  res['1p'] = {sc [away, home], su (away side W/L/T), tot O/U (1.5),
               btts Y/N, u {su [away, home], ml3 [away, home, tie],
               tot [over, under], btts [yes, no]}}
  odds['1p'] = {ml {away, home}, ml3 {away, draw, home},
                total {line 1.5, over, under}, btts {yes, no}}
als / hls are the period scores so far (1st, 2nd, 3rd; a live 1st period
counts the goals so far); detail the live clock; as / hs the final score,
which counts OT goals and the shootout winner, the way books grade it.
The same rules as nhlSitGame in template.html: a tied 1st period is a push
on the moneyline (0 units), a loss for both teams on the 3-way.
"""
import grading
import sports
from grading import bet_units, flip, num

STATE = {'LIVE': 'in', 'CRIT': 'in', 'FINAL': 'final', 'OFF': 'final'}
CONFERENCE = {'Atlantic': 'East', 'Metropolitan': 'East', 'Central': 'West', 'Pacific': 'West'}
SEGMENTS = [{'key': '1p', 'label': '1st Period', 'tag': '1P'}]
TWO_WORD = ('Blue Jackets', 'Maple Leafs', 'Red Wings', 'Golden Knights')


def nickname(name):
    return next((w for w in TWO_WORD if name.endswith(w)), name.split(' ')[-1])


def _won(yes):
    return 'W' if yes else 'L'


def full_run(g, odds):
    """NHL's Full Run, once the game is final: fr['2p'] / fr['3p'] the
    period's goals and who won it (W-L-T; results only, no lines) and
    fr['game'] the final (OT and the shootout winner included, the way books
    grade it) with the ML, puck line and total from `odds` (the merged
    "game" segment, the other sports' shape)."""
    import sport_build
    fr = {}
    for i, k in ((2, '2p'), (3, '3p')):
        a, h = num(g.get(f'awayP{i}')), num(g.get(f'homeP{i}'))
        if a is not None and h is not None:
            fr[k] = {'sc': [a, h], 'su': 'W' if a > h else 'L' if a < h else 'T'}
    a, h = num(g.get('awayFinal')), num(g.get('homeFinal'))
    if a is not None and h is not None:
        fr['game'] = sport_build.compact('game', 'period', grading.grade_spread_segment({'away': a, 'home': h}, odds))
    return fr


def goalie(x, status=None):
    """A starting goalie: {id, name, last, status?} ("S. Knight" -> last
    "Knight"); status "confirmed" (the NHL's box score lists him) or
    "expected" (the team's last starter) on a game still to finish."""
    if not x or not x.get('id'):
        return None
    name = x.get('name') or ''
    out = {'id': x['id'], 'name': name, 'last': name.split('. ', 1)[-1] if '. ' in name else name.split(' ')[-1]}
    if status or x.get('status'):
        out['status'] = status or x['status']
    return out


def expected_goalies(games):
    """Games still to finish (date order) get each team's last starter as
    "expected", unless the box score already confirmed one."""
    last = {}
    for g in sorted(games, key=lambda g: g.get('start') or ''):
        if g.get('state') == 'final':
            for side, k in (('away', 'ag'), ('home', 'hg')):
                if g.get(k):
                    last[g[side]] = {x: g[k][x] for x in ('id', 'name', 'last')}
        else:
            for side, k in (('away', 'ag'), ('home', 'hg')):
                if (g.get(k) or {}).get('status') == 'confirmed':
                    continue
                g[k] = dict(last[g[side]], status='expected') if g[side] in last else None


def game(g, date, full_odds=None):
    """One game in the shared shape; full_odds: this game's Full Run lines
    ({'game': {ml, ats, total}}, from The Odds API)."""
    out = {'id': g.get('id'), 'start': g.get('startTimeUTC') or date + 'T23:00:00Z',
           'state': STATE.get(g.get('state'), 'pre'), 'away': g['away'], 'home': g['home'],
           'as': g.get('awayFinal'), 'hs': g.get('homeFinal'), 'ot': g.get('ot') or '',
           'firstGoal': g.get('firstGoal'), 'ag': goalie(g.get('awayGoalie')), 'hg': goalie(g.get('homeGoalie')),
           'fml': g.get('fgMl'), 'detail': g.get('detail') or '',
           'ven': g.get('venue'), 'tv': g.get('tv') or None,   # Preview's game lines
           # postseason: the NHL's game id carries the type (2025030111: 03 = playoffs)
           'post': str(g.get('id') or '')[4:6] == '03'}
    periods = [(g.get(f'awayP{i}'), g.get(f'homeP{i}')) for i in (1, 2, 3)]
    known = []
    for a, h in periods:   # the periods scored so far, in order
        if a is None or h is None:
            break
        known.append((a, h))
    if not known and out['state'] == 'in' and g.get('period') == 1 and out['as'] is not None:
        known = [(out['as'], out['hs'])]   # the 1st period in progress
    if known:
        out['als'] = [a for a, _ in known]
        out['hls'] = [h for _, h in known]
    o = g.get('odds') or {}
    ml = o.get('ml') or {}
    t = (o.get('totals') or {}).get('1.5') or {}
    m3 = o.get('ml3') or {}
    pa, ph = num(ml.get(g['away'])), num(ml.get(g['home']))
    po, pu = num(t.get('over')), num(t.get('under'))
    py, pn = num(o.get('btts_yes')), num(o.get('btts_no'))
    ta, td, th = num(m3.get('away')), num(m3.get('draw')), num(m3.get('home'))
    odds = {}
    if pa is not None and ph is not None:
        odds['ml'] = {'away': pa, 'home': ph}
    if ta is not None and td is not None and th is not None:
        odds['ml3'] = {'away': ta, 'draw': td, 'home': th}
    if po is not None and pu is not None:
        odds['total'] = {'line': 1.5, 'over': po, 'under': pu}
    if py is not None and pn is not None:
        odds['btts'] = {'yes': py, 'no': pn}
    if odds:
        out['odds'] = {'1p': odds}
    if full_odds:
        out['fo'] = full_odds
    if out['state'] == 'final':
        out['fr'] = full_run(g, (full_odds or {}).get('game')) or None
    a, h = periods[0]
    if a is None or h is None:
        return out
    su = 'W' if a > h else 'L' if a < h else 'T'
    over, btts = a + h > 1, a >= 1 and h >= 1
    u = {}
    if 'ml' in odds:
        u['su'] = [bet_units(su, pa), bet_units(flip(su), ph)]
    if 'ml3' in odds:
        u['ml3'] = [bet_units(_won(su == 'W'), ta), bet_units(_won(su == 'L'), th), bet_units(_won(su == 'T'), td)]
    if 'total' in odds:
        u['tot'] = [bet_units(_won(over), po), bet_units(_won(not over), pu)]
    if 'btts' in odds:
        u['btts'] = [bet_units(_won(btts), py), bet_units(_won(not btts), pn)]
    out['res'] = {'1p': {'sc': [a, h], 'su': su, 'tot': 'O' if over else 'U', 'btts': 'Y' if btts else 'N', 'u': u}}
    return out


def doc(games_by_date, season_start, season_label, summary, divisions, colors, tz, generated, full_odds=None):
    """nhl/sport.json; full_odds: {"date|away|home": {segment: lines}}, the
    Full Run's lines (sport_build.oddsapi_odds)."""
    full_odds = full_odds or {}
    teams = {}
    for div, codes in divisions.items():
        for code in codes:
            name = (summary.get(code) or {}).get('name') or code
            teams[code] = {'name': name, 'short': nickname(name), 'mu': sports.team_slug(nickname(name)), 'code': code, 'svg': 1,
                           'color': (colors.get(code) or '').lstrip('#') or None,
                           'division': div, 'conference': CONFERENCE.get(div)}
    games = {d: [game(g, d, (full_odds.get(f"{d}|{g['away']}|{g['home']}") or {}).get('segments')) for g in gs]
             for d, gs in sorted(games_by_date.items()) if d >= season_start}
    expected_goalies([g for gs in games.values() for g in gs])
    return {
        'sport': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'sportType': 'period', 'segments': SEGMENTS,
        'fullRun': sports.BY_KEY['nhl']['full_run'],
        'markets': [list(m) for m in sports.BY_KEY['nhl']['family_markets']],
        'schedule': 'day', 'season': int(season_start[:4]) + 1, 'seasonLabel': season_label,
        'generated': generated, 'teams': teams, 'tz': tz,
        'games': games,
    }
