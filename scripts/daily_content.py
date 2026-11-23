"""
Preview's drafts (was On Tap), written by Claude from the site's own numbers:

  preview  Preview: today's slate, drafted from 8 AM ET, shown once published
  recap    The Morning Run: last night's results (off: daily.RECAP)

for every sport with games that day (scripts/sports.py), plus one across
every sport for the home page. Football is weekly: the Week Preview on
Thursday from 8 AM ET (and the Weekend Recap on Monday, while recaps are on).

Each run of the refresh workflow calls this (no arguments). A draft is
written once per sport and day, on the first run inside its window, to
content/drafts/{sport}-{kind}-{date}.md; nothing is published until
someone approves it in the admin's Preview tab. A draft already written (or
published) is never redone. Without the ANTHROPIC_API_KEY secret, or while
sports.PREVIEW_LIVE is False, it does nothing.

The packet sent to Claude holds every fact the piece may use: per game the
full team names and codes, the start, each trend's season record and rate
(10+ games), the streaks, the lines (open, now, best price and its book),
and which game is the Matchup of the Day and which the lead game; per team
every segment market's season rate (overall, home / road, favorite /
underdog); the league trends that fit tonight; the Edge plays; and the three
boxes already picked (scripts/preview.py). Every preview's instructions
carry content/preview_writing_guide.md in full; the drafter's STAT / TREND /
EDGE sentences go into the draft's front matter with their boxes. After writing, every number in the draft is checked
against the packet (times and dates aside); any that isn't there is listed
in the draft's `check:` line for the editor.

  python3 scripts/daily_content.py                     # the scheduled run
  python3 scripts/daily_content.py preview nba 2026-11-18 --dry-run   # print the packet
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import grading  # noqa: E402
import hyphens  # noqa: E402
import preview as pv  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
DRAFTS = os.path.join(ROOT, 'content', 'drafts')
PUBLISHED = os.path.join(ROOT, 'content', 'published')
SPORTS = tuple(sp['key'] for sp in sports.SPORTS)   # a sport with no games that day (or out of season) gets no draft
# kind -> (weekday, first ET hour, last ET hour) a scheduled run may write
# it; weekday None is every day. Football's pieces are weekly: the Weekend
# Recap on Monday, the Week Preview on Thursday. Preview is drafted from
# 8 AM so it's waiting in the admin's Preview tab by 10 AM; it shows as
# soon as it's published. The recap runs only while daily.RECAP is on.
WINDOWS = {'recap': (None, 8, 14), 'preview': (None, 8, 18)}
WEEKLY_WINDOWS = {'recap': (0, 8, 14), 'preview': (3, 8, 18)}
MODEL = 'claude-opus-5-5'
STREAK_MIN = 3   # runs this long are worth a mention


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def et_time(iso):
    if not iso:
        return None
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return t.strftime('%-I:%M %p ET')


def units(result, price):
    u = grading.bet_units(result, price) if price is not None else None
    return None if u is None else round(u, 2)


def trend_results(entry, games_on=None):
    """Graded picks from the league trends that were bets (not weak)."""
    out = []
    for t in (entry or {}).get('trends') or []:
        if not t.get('kind') or t.get('strength') == 'weak':
            continue
        for p in t.get('games') or []:
            out.append({'trend': t['title'], 'strength': t['strength'], 'season_record': t.get('record'),
                        'pick': p.get('label') or p.get('chip'), 'game': p.get('matchup'),
                        'result': {'W': 'hit', 'L': 'miss', 'P': 'push', 'NA': 'no action'}.get(p.get('status'), 'pending')})
    return out


def runs(seq):
    """(result, length) of the run ending at the last item."""
    if not seq:
        return None, 0
    n = 0
    for r in reversed(seq):
        if r != seq[-1]:
            break
        n += 1
    return seq[-1], n


def streak_changes(seqs, played, labels):
    """Streaks extended or snapped by the latest game, for teams in `played`.
    seqs: {(team, market): [results oldest first]}; labels: market -> {result: word}."""
    out = []
    for (team, market), seq in seqs.items():
        if team not in played or len(seq) < 2:
            continue
        r, n = runs(seq)
        pr, pn = runs(seq[:-1])
        word = labels[market]
        if r == pr and n >= STREAK_MIN:
            out.append({'team': team, 'market': market, 'streak': f'{word.get(r, r)} {n} straight', 'change': 'extended'})
        elif r != pr and pn >= STREAK_MIN:
            out.append({'team': team, 'market': market, 'streak': f'{word.get(pr, pr)} {pn} straight', 'change': 'snapped',
                        'snapped_by': word.get(r, r), 'was': pr})
    return sorted(out, key=lambda x: (x['change'], x['team']))


def active_streaks(seqs, teams, labels):
    out = []
    for (team, market), seq in seqs.items():
        r, n = runs(seq)
        if team in teams and n >= STREAK_MIN and r in labels[market]:
            out.append({'team': team, 'market': market, 'streak': f'{labels[market][r]} {n} straight'})
    return sorted(out, key=lambda x: (-int(x['streak'].split()[-2]), x['team']))


def best_and_worst(bets):
    graded = [b for b in bets if b.get('units') is not None]
    best = sorted([b for b in graded if b['units'] > 0], key=lambda b: -b['units'])[:3]
    worst = sorted([b for b in graded if b['units'] < 0 and (b.get('price') or 0) < -150], key=lambda b: b['price'])[:3]
    return {'best_paying_winners': best, 'biggest_favorites_that_lost': worst}


# ----------------------------------------------------------------- NHL

NHL_LABELS = {'1P ML': {'W': 'won the 1st period', 'L': 'lost the 1st period', 'T': 'tied the 1st period'},
              'Over 1.5': {'W': 'Over 1.5 1P', 'L': 'Under 1.5 1P'},
              'BTTS': {'W': 'both teams scored in the 1P', 'L': 'no BTTS in the 1P'}}


def nhl_seqs(D, through):
    seqs = {}
    for code, log in (D.get('gamelog') or {}).items():
        for e in log:
            if e['date'] > through:
                continue
            seqs.setdefault((code, '1P ML'), []).append('W' if e['p1t'] > e['p1o'] else 'L' if e['p1t'] < e['p1o'] else 'T')
            seqs.setdefault((code, 'Over 1.5'), []).append('W' if e['p1t'] + e['p1o'] > 1 else 'L')
            seqs.setdefault((code, 'BTTS'), []).append('W' if e.get('btts') else 'L')
    return seqs


def nhl_name(D, code):
    return (D.get('summary', {}).get(code) or {}).get('name', code)


def nhl_recap(day):
    D = read_json(os.path.join(ROOT, 'nhl', 'data.json'), {})
    games, bets = [], []
    for g in (D.get('schedule', {}).get('games') or {}).get(day, []):
        if g.get('state') not in ('OFF', 'FINAL') or g.get('awayP1') is None:
            continue
        a, h = g['away'], g['home']
        o = g.get('odds') or {}
        ml = o.get('ml') or {}
        ap, hp = g['awayP1'], g['homeP1']
        p1 = 'away' if ap > hp else 'home' if hp > ap else 'tie'
        tot = ap + hp
        over = ((o.get('totals') or {}).get('1.5') or {})
        res_a = 'W' if p1 == 'away' else 'L' if p1 == 'home' else 'T'
        res_h = {'W': 'L', 'L': 'W', 'T': 'T'}[res_a]
        row = {'matchup': f'{nhl_name(D, a)} at {nhl_name(D, h)}', 'final': f"{a} {g.get('awayFinal')} - {h} {g.get('homeFinal')}" + (' (OT)' if g.get('ot') == 'OT' else ' (SO)' if g.get('ot') == 'SO' else ''),
               'first_period': f'{a} {ap} - {h} {hp}', 'first_goal': g.get('firstGoal'),
               'markets': {
                   '1P moneyline (2-way, a tie is a push)': {
                       a: {'price': ml.get(a), 'result': res_a, 'units': units(res_a, ml.get(a))},
                       h: {'price': ml.get(h), 'result': res_h, 'units': units(res_h, ml.get(h))}},
                   '1P 3-way': {'prices': o.get('ml3'), 'winner': p1},
                   '1P total 1.5': {'goals': tot, 'result': 'Over' if tot > 1 else 'Under', 'over_price': over.get('over'), 'under_price': over.get('under'),
                                    'over_units': units('W' if tot > 1 else 'L', over.get('over')), 'under_units': units('L' if tot > 1 else 'W', over.get('under'))},
                   '1P BTTS': {'result': 'Yes' if ap and hp else 'No', 'yes_price': o.get('btts_yes'), 'no_price': o.get('btts_no')}}}
        games.append(row)
        for code, res in ((a, res_a), (h, res_h)):
            bets.append({'bet': f'{code} 1P moneyline', 'game': row['matchup'], 'price': ml.get(code), 'result': res, 'units': units(res, ml.get(code))})
        bets.append({'bet': 'Over 1.5 1P', 'game': row['matchup'], 'price': over.get('over'), 'result': 'W' if tot > 1 else 'L', 'units': units('W' if tot > 1 else 'L', over.get('over'))})
        bets.append({'bet': 'Under 1.5 1P', 'game': row['matchup'], 'price': over.get('under'), 'result': 'L' if tot > 1 else 'W', 'units': units('L' if tot > 1 else 'W', over.get('under'))})
    if not games:
        return None
    log = read_json(os.path.join(ROOT, 'league_trends_log.json'), {})
    played = {c for g in D['schedule']['games'][day] for c in (g['away'], g['home'])}
    today = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    tonight = (D.get('schedule', {}).get('games') or {}).get(today, [])
    return {'sport': 'NHL', 'segment': '1st period', 'date_of_games': day, 'games': games,
            'league_trends': {'record': (log.get(day) or {}).get('record'), 'picks': trend_results(log.get(day))},
            'streaks': streak_changes(nhl_seqs(D, day), played, NHL_LABELS),
            'night': best_and_worst(bets),
            'carries_into_today': {'date': today, 'games_today': len(tonight),
                                   'active_streaks_for_teams_playing_today': active_streaks(
                                       nhl_seqs(D, day), {c for g in tonight for c in (g['away'], g['home'])}, NHL_LABELS)[:8]}}


def nhl_preview(day):
    if not pv.slate(pv.sport_of('nhl'), day)[1]:
        return None
    return preview_packet('nhl', day)


# ------------------------------------------------- every other sport
# The shared data.json shape (scripts/sport_build.py), so one builder covers
# the NBA, WNBA, NCAAB and MLB by day and the NFL and NCAAF by week.

LABELS = {'su': {'W': 'won', 'L': 'lost'}, 'ats': {'W': 'covered', 'L': 'failed to cover'}, 'tot': {'O': 'Over', 'U': 'Under'},
          'rfi': {'Y': 'had a run in the 1st inning', 'N': 'had no run in the 1st inning'}}
FLIP = {'W': 'L', 'L': 'W'}


def doc_of(key):
    return read_json(os.path.join(ROOT, sports.BY_KEY[key]['slug'], 'data.json'), {})


def team_of(D, slug):
    t = D['teams'].get(slug)
    if t:
        return t.get('name', slug), t.get('code', slug.upper())
    name = D.get('otherTeams', {}).get(slug) or slug   # non-Division I opponents: a name only
    return name, name


def seqs_of(D, through):
    """{(team code, 'seg:market'): results oldest first}, games on or before `through`."""
    seqs = {}
    for d in sorted(D.get('games') or {}):
        if d > through:
            continue
        for g in D['games'][d]:
            for k, r in (g.get('res') or {}).items():
                for side in ('away', 'home'):
                    code = team_of(D, g[side])[1]
                    for m in LABELS:
                        x = r.get(m)
                        if x in (None, 'NA'):
                            continue
                        if m in ('su', 'ats') and side == 'home':
                            x = FLIP.get(x, x)
                        seqs.setdefault((code, f'{k}:{m}'), []).append(x)
    return seqs


def labels_of(D):
    out = {}
    for s in D['segments']:
        for m, words in LABELS.items():
            if m == 'rfi':
                out[f"{s['key']}:{m}"] = dict(words)
            else:
                out[f"{s['key']}:{m}"] = {r: f'{w} the {s["tag"]}' if m != 'tot' else f'{w} in the {s["tag"]}' for r, w in words.items()}
    return out


def seg_words(key):
    return ' and '.join(s['label'] for s in sports.BY_KEY[key]['segments']).lower()


def finals_between(D, first, last):
    return [g for d in sorted(D.get('games') or {}) if first <= d <= last for g in D['games'][d]
            if g.get('state') == 'final' and g.get('res')]


def results_packet(key, D, finals):
    """Every finished game's segment results, and the bets for best / worst."""
    seg_tag = {s['key']: s['tag'] for s in D['segments']}
    games, bets = [], []
    for g in finals:
        (an, ac), (hn, hc) = team_of(D, g['away']), team_of(D, g['home'])
        row = {'matchup': f'{an} at {hn}', 'final': f"{ac} {g['as']} - {hc} {g['hs']}", 'segments': {}}
        for k, r in g['res'].items():
            o = (g.get('odds') or {}).get(k) or {}
            u = {m: [None if x is None else round(x, 2) for x in v] for m, v in (r.get('u') or {}).items()}
            sc = r.get('sc') or [None, None]
            ats = o.get('ats') or {}
            tot = o.get('total') or {}
            seg = {'score': f'{ac} {sc[0]} - {hc} {sc[1]}'}
            if r.get('su') not in (None, 'NA'):
                seg['moneyline'] = {ac: {'price': (o.get('ml') or {}).get('away'), 'result': r['su'], 'units': (u.get('su') or [None])[0]},
                                    hc: {'price': (o.get('ml') or {}).get('home'), 'result': FLIP.get(r['su'], r['su']), 'units': (u.get('su') or [None, None])[1]}}
            if r.get('ats') not in (None, 'NA'):
                seg['spread'] = {ac: {'line': (ats.get('away') or {}).get('line'), 'price': (ats.get('away') or {}).get('price'), 'result': r['ats'], 'units': (u.get('ats') or [None])[0]},
                                 hc: {'line': (ats.get('home') or {}).get('line'), 'price': (ats.get('home') or {}).get('price'), 'result': FLIP.get(r['ats'], r['ats']), 'units': (u.get('ats') or [None, None])[1]}}
            if r.get('tot') not in (None, 'NA'):
                seg['total'] = {'line': tot.get('line'), 'result': {'O': 'Over', 'U': 'Under', 'P': 'Push'}[r['tot']],
                                'over_price': tot.get('over'), 'under_price': tot.get('under'),
                                'over_units': (u.get('tot') or [None])[0], 'under_units': (u.get('tot') or [None, None])[1]}
            if r.get('rfi') in ('Y', 'N'):
                seg['run_in_1st_inning'] = 'Yes' if r['rfi'] == 'Y' else 'No'
            row['segments'][seg_tag.get(k, k)] = seg
            for name in ('moneyline', 'spread'):
                for code, v in (seg.get(name) or {}).items():
                    bets.append({'bet': f"{code} {seg_tag.get(k, k)} {name}" + (f" {v['line']:+g}" if v.get('line') is not None else ''),
                                 'game': row['matchup'], 'price': v.get('price'), 'result': v['result'], 'units': v.get('units')})
            if seg.get('total'):
                t = seg['total']
                for side, res in (('Over', 'W' if t['result'] == 'Over' else 'L'), ('Under', 'W' if t['result'] == 'Under' else 'L')):
                    bets.append({'bet': f"{side} {t['line']} {seg_tag.get(k, k)}", 'game': row['matchup'], 'price': t[side.lower() + '_price'],
                                 'result': res if t['result'] != 'Push' else 'P', 'units': t[side.lower() + '_units']})
        games.append(row)
    return games, bets


def sport_recap(key, day):
    """Daily sports: the night of `day`."""
    D = doc_of(key)
    finals = finals_between(D, day, day)
    if not finals:
        return None
    games, bets = results_packet(key, D, finals)
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    labels, seqs = labels_of(D), seqs_of(D, day)
    played = {team_of(D, g[s])[1] for g in finals for s in ('away', 'home')}
    today = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    tonight = (D.get('games') or {}).get(today, [])
    return {'sport': sports.BY_KEY[key]['label'], 'segments': seg_words(key), 'date_of_games': day, 'games': games,
            'league_trends': {'record': (log.get(day) or {}).get('record'), 'picks': trend_results(log.get(day))},
            'streaks': streak_changes(seqs, played, labels),
            'night': best_and_worst(bets),
            'carries_into_today': {'date': today, 'games_today': len(tonight),
                                   'active_streaks_for_teams_playing_today': active_streaks(
                                       seqs, {team_of(D, g[s])[1] for g in tonight for s in ('away', 'home')}, labels)[:8]}}


def preview_packet(key, day, ids=None):
    """A sport's Preview packet (scripts/preview.py packet_games); ids: only
    these games (the all-sports preview: a weekly sport's games that day)."""
    sp = sports.BY_KEY[key]
    sport = pv.sport_of(key)
    games = [g for g in pv.slate(sport, day)[1] if ids is None or str(g['id']) in ids]
    rows = pv.packet_games(key, day, ids)
    lead = next((g['matchup'] for g in rows if g['lead_game']), None)
    motd = next((g['matchup'] for g in rows if g['matchup_of_the_day']), None)
    out = {'sport': sports.seo_name(key), 'segments': seg_words(key), 'date': day, 'games_on_the_slate': len(games),
           'lead_game': lead, 'matchup_of_the_day': motd, 'games': rows, 'trends_page': f"/{sp['slug']}/trends/",
           **pv.more_data(key, day, {g['id'] for g in rows}),
           'boxes': pv.boxes(key, day)}
    wk = pv.week_of(sport, day) if sport.weekly else None
    if wk:
        out['week'] = wk['label']
    return out


def sport_preview(key, day):
    if not (doc_of(key).get('games') or {}).get(day):
        return None
    return preview_packet(key, day)


def all_preview(day):
    """The home page's Preview: every in-season sport's preview packet with
    games that day (football: its week preview on Thursday), in one, with
    the site's lead game and Matchup of the Day."""
    d = date.fromisoformat(day)
    parts, on = {}, []
    lead = pv.lead_of(daily.ALL, day)
    motd = pv.motd_of(daily.ALL, day)
    for sp in sports.shown(d):
        if weekly_preview(sp['key']):   # only that day's games; the week has its own preview
            ids = {str(g['id']) for g in pv.day_games(pv.sport_of(sp['key']), day)}
            x = preview_packet(sp['key'], day, ids) if ids else None
            if x:
                x['weekly_preview'] = f"{sports.seo_name(sp)} {x.get('week') or 'Week'} Preview"
        else:
            x = builder('preview', sp['key'])(day)
        if x:
            for g in x['games']:   # the home page's own lead and Matchup of the Day
                g['lead_game'] = bool(lead and (lead['sport'], lead['id']) == (sp['key'], g['id']))
                g['matchup_of_the_day'] = bool(motd and tuple(motd) == (sp['key'], g['id']))
            x.pop('lead_game', None)
            x.pop('matchup_of_the_day', None)
            x.pop('boxes', None)   # the home page picks its own, across sports
            parts[sports.seo_name(sp)] = x
            on.append(sp)
    if not parts:
        return None
    find = lambda flag: next((f"{n}: {g['matchup']}" for n, x in parts.items() for g in x['games'] if g[flag]), None)
    return {'sport': sports.sport_names(on), 'segments': 'first period, first quarter and first half', 'date': day,
            'lead_game': find('lead_game'), 'matchup_of_the_day': find('matchup_of_the_day'), 'sports': parts, 'trends_page': '/trends/',
            'boxes': pv.boxes(daily.ALL, day, [sp['key'] for sp in on])}


def week_of(D, day):
    """The week `day` falls in, else the next one."""
    weeks = D.get('weeks') or []
    return next((w for w in weeks if w['start'] <= day <= w['end']), None) or next((w for w in weeks if w['start'] > day), None)


def week_recap(key, day):
    """Football, Monday: the week's games through Sunday."""
    D = doc_of(key)
    yday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    wk = next((w for w in D.get('weeks') or [] if w['start'] <= yday <= w['end']), None)
    if not wk:
        return None
    finals = [g for g in finals_between(D, wk['start'], yday) if g.get('wk') == wk['key']]
    if not finals:
        return None
    games, bets = results_packet(key, D, finals)
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    labels, seqs = labels_of(D), seqs_of(D, yday)
    played = {team_of(D, g[s])[1] for g in finals for s in ('away', 'home')}
    return {'sport': sports.BY_KEY[key]['label'], 'segments': seg_words(key), 'week': wk['label'],
            'games_from': wk['start'], 'games_through': yday, 'games': games,
            'league_trends': {'record': (log.get(wk['key']) or {}).get('record'), 'picks': trend_results(log.get(wk['key']))},
            'streaks': streak_changes(seqs, played, labels),
            'weekend': best_and_worst(bets)}


def week_preview(key, day):
    """Football, Thursday: the week's games still to play."""
    if not pv.slate(pv.sport_of(key), day)[1]:
        return None
    return preview_packet(key, day)


def builder(kind, key):
    if key == daily.ALL:
        return all_preview
    if key == 'nhl':
        return nhl_recap if kind == 'recap' else nhl_preview
    if sports.BY_KEY[key].get('schedule') == 'week' and (kind == 'recap' or sports.preview_weekly(key)):
        return lambda day: (week_recap if kind == 'recap' else week_preview)(key, day)
    return lambda day: (sport_recap if kind == 'recap' else sport_preview)(key, day)


# --------------------------------------------------------------- writing

SYSTEM = """You write for Run to Your Bets (RTYB), a site of first-period, first-quarter and first-half betting stats. Your voice: a fun, confident bettor who knows the numbers cold, talking to other bettors.

Rules, all of them strict:
- Use only facts in the data packet. Every team, score, price, record, rate, line and streak you mention must appear in the packet exactly as given. If something isn't in the packet, leave it out.
- Never invent plays, goals, players, injuries, quotes or game moments.
- No guarantees. Never write 'lock', 'chase it', 'can't lose', 'free money', 'sure thing' or anything like them.
- Odds are American (-125, +150).
- Teams: the full name from the packet in the text (Milwaukee Bucks); the team code (MIL) only inside a bet or a stat.
- Don't add disclaimer lines; the site has its own.
- Markdown: short paragraphs, no bullet lists, no tables."""

GUIDE = os.path.join(ROOT, 'content', 'preview_writing_guide.md')


def system_for(kind):
    """The recap: SYSTEM. Every preview (all-sports and each sport): SYSTEM
    plus the full writing guide (content/preview_writing_guide.md)."""
    if kind != 'preview':
        return SYSTEM
    with open(GUIDE, encoding='utf-8') as f:
        return SYSTEM + '\n\nFollow this writing guide exactly:\n\n<writing_guide>\n' + f.read().strip() + '\n</writing_guide>'


PREVIEW = " Follow the writing guide: the STAT / TREND / EDGE lines for the packet's boxes, the headline and dek, then the body with one '###' subhead per game, at most 8 (the rest in one 'Also with trends:' sentence), each subhead on its own line with a blank line before and after."
TASK = {
    'recap': "Write The Morning Run, today's recap of last night's {sport} {seg} betting results, from this packet. Cover the biggest results, how RTYB's league trends did, the night's best and worst results, and the streaks that were extended or snapped. End with what carries into today (the 'carries_into_today' part).",
    'preview': "Write Preview, today's {sport} {seg} betting preview, from this packet." + PREVIEW,
    'all_preview': "Write Preview, today's betting preview across every sport on the slate ({sport}), for the {seg}, from this packet. "
                   "Follow the writing guide: the STAT / TREND / EDGE lines for the packet's boxes, the headline and dek, the intro, then one '##' section per sport with two paragraphs each.",
    'week_recap': "Write the Weekend Recap, the {sport} {seg} betting results of {week} so far, from this packet. Cover the biggest results, how RTYB's league trends did, the weekend's best and worst results, and the streaks that were extended or snapped.",
    'week_preview': "Write the {week} Preview, this week's {sport} {seg} betting preview, from this packet." + PREVIEW +
                    " Group the games by kickoff window ('##' lines, the games' `window`).",
}


def weekly(sport):
    return sport != daily.ALL and sports.BY_KEY[sport].get('schedule') == 'week'


def weekly_preview(sport):
    """A weekly Preview (NFL, College Football unless the admin's
    PREVIEW_MODE says daily): one per week, every game in it."""
    return weekly(sport) and sports.preview_weekly(sport)


def title(kind, sport, day, packet=None):
    if sport == daily.ALL:
        return f"First Period, Quarter & Half Betting Preview - {date.fromisoformat(day).strftime('%b %-d, %Y')}"
    sp = sports.BY_KEY[sport]
    seg = ' and '.join(s['label'].replace('1st ', 'First ') for s in sp['segments'])
    when = date.fromisoformat(day).strftime('%b %-d, %Y')
    if weekly(sport) and kind == 'recap':
        return f"{sp['label']} {seg} Betting Weekend Recap - {when}"
    if weekly_preview(sport) and kind == 'preview':   # "NFL Week 11 First Quarter & First Half Betting Preview"
        week = (packet or {}).get('week') or 'Week'
        return f"{sports.seo_name(sport)} {week} {sports.seg_words(sport)} Betting Preview"
    return f"{sp['label']} {seg} Betting {'Recap' if kind == 'recap' else 'Preview'} - {when}"


def numbers_in(text):
    return set(re.findall(r'[+-]?\d+(?:\.\d+)?', text))


# times ("7:30 PM", "10:00") and dates ("Nov 18", "11/18", "2026-11-18") aren't checked
TIME_OR_DATE = re.compile(r'\b\d{1,2}:\d{2}(?:\s*[AP]\.?M\.?)?(?:\s*ET)?|\b\d{1,2}\s*[AP]\.?M\.?\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b'
                          r'|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?\b', re.I)


def key(n):
    """A number without its sign, and without trailing zeros only after a
    decimal point (0.80 = 0.8, but 70 stays 70)."""
    n = n.lstrip('+-')
    return n.rstrip('0').rstrip('.') if '.' in n else n


def unchecked_numbers(body, packet):
    """Numbers in the draft that aren't in the packet (ignoring signs,
    trailing zeros, times and dates)."""
    have = {key(n) for n in numbers_in(json.dumps(packet, ensure_ascii=False))}
    have |= {'21', '1-800', '800', '4357'}
    out = []
    text = TIME_OR_DATE.sub(' ', re.sub(r'^---\n.*?\n---\n', '', body, flags=re.S).replace('1-800-GAMBLER', ''))
    for n in re.findall(r'[+-]?\d+(?:\.\d+)?', text):   # in reading order
        if key(n) not in have and n not in out:
            out.append(n)
    return out


# ---------------------------------------------------------- phrase check
# The admin flags these in a draft's article (admin/index.html phraseFlags,
# the same rules); they never block publishing. Line numbers count from the
# article's first line (after the headline and dek).
SEG_CODES = re.compile(r'(?<![\w-])(1Q|1H|1P|F5)(?![\w-])')


def banned_phrases(guide=None):
    """The writing guide's "Banned phrases" list."""
    if guide is None:
        with open(GUIDE, encoding='utf-8') as f:
            guide = f.read()
    m = re.search(r'^## Banned phrases\n(.*?)(?=^## )', guide, re.M | re.S)
    return [x.strip() for x in re.findall(r'^- (.+)$', m.group(1), re.M)] if m else []


def article_lines(md):
    """The article's lines: the body after the "# " headline and "> " dek."""
    lines = re.sub(r'^---\n.*?\n---\n?', '', md, flags=re.S).split('\n')
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith('# ') or lines[i].startswith('> ')):
        i += 1
    return lines[i:]


def sentences(text):
    return [x.strip() for x in re.split(r'(?<=[.!?])\s+', text.strip()) if x.strip()]


def phrase_flags(lines, codes, banned):
    """[(line number, what, text)] for: a banned phrase, "where the numbers",
    a closing sentence used twice, 1Q / 1H / 1P / F5 or a team code inside a
    body sentence (subheads are left alone)."""
    out, closing = [], {}
    code_re = re.compile(r'(?<![\w-])(' + '|'.join(sorted({re.escape(c) for c in codes if 2 <= len(c) <= 4}, key=len, reverse=True)) + r')(?![\w-])') if codes else None
    for i, line in enumerate(lines, 1):
        text = line.strip()
        if not text:
            continue
        if text.startswith('#'):
            continue
        low = text.lower()
        for b in banned:
            if re.search(r'(?<![\w])' + re.escape(b.lower()) + r'(?![\w])', low.replace('\u2019', "'")):
                out.append((i, f'Banned phrase: "{b}"', text))
        if 'where the numbers' in low:
            out.append((i, '"where the numbers"', text))
        for m in SEG_CODES.finditer(text):
            out.append((i, f'{m.group(1)} in a sentence', text))
        for m in (code_re.finditer(text) if code_re else ()):
            out.append((i, f'Team code {m.group(1)} in a sentence', text))
        closing[i] = sentences(text)[-1]
    # a section's closing sentence: its last paragraph's last sentence
    ends, cur = [], None
    for i, line in enumerate(lines, 1):
        t = line.strip()
        if t.startswith('#'):
            if cur:
                ends.append(cur)
            cur = None
        elif t and i in closing:
            cur = (i, closing[i])
    if cur:
        ends.append(cur)
    seen = {}
    for i, sent in ends:
        k = re.sub(r'\W+', ' ', sent.lower()).strip()
        if k in seen:
            out.append((i, f'Same closing sentence as line {seen[k]}', sent))
        else:
            seen[k] = i
    return sorted(out)


def write_piece(kind, sport, day, packet):
    import anthropic   # only the scheduled run needs the SDK
    client = anthropic.Anthropic()
    seg = packet.get('segment') or packet.get('segments')
    task = TASK['all_preview' if sport == daily.ALL else ('week_' if (weekly_preview(sport) if kind == 'preview' else weekly(sport)) else '') + kind]
    prompt = task.format(sport=packet['sport'], seg=seg, week=packet.get('week')) + '\n\n<packet>\n' + json.dumps(packet, indent=1, ensure_ascii=False) + '\n</packet>'
    # A declined request falls back server-side to Anthropic's recommended model
    response = client.beta.messages.create(
        model=MODEL, max_tokens=16000,
        betas=['server-side-fallback-2026-07-01'], fallbacks='default',
        output_config={'effort': 'medium'},
        system=system_for(kind),
        messages=[{'role': 'user', 'content': prompt}],
    )
    if response.stop_reason == 'refusal':
        raise RuntimeError(f'{sport} {kind}: the model declined ({getattr(response.stop_details, "category", None)})')
    body = ''.join(b.text for b in response.content if b.type == 'text').strip()
    if not body:
        raise RuntimeError(f'{sport} {kind}: empty response ({response.stop_reason})')
    return body, response.model


def draft_path(kind, sport, day):
    return os.path.join(DRAFTS, f'{sport}-{kind}-{day}.md')


BOX_LINES = {'STAT': 'stat_of_night', 'TREND': 'league_trend', 'EDGE': 'edge_play'}


def box_front(body, packet):
    """(body without its STAT / TREND / EDGE lines, front matter lines): each
    box from the packet's pick, with the drafter's sentence when it wrote one."""
    said, keep = {}, []
    for line in body.split('\n'):
        m = re.match(r'\s*(STAT|TREND|EDGE):\s*(.+)$', line)
        if m and BOX_LINES[m.group(1)] not in said:
            said[BOX_LINES[m.group(1)]] = m.group(2).strip()
        else:
            keep.append(line)
    front = []
    for key, box in (packet.get('boxes') or {}).items():
        front.append(f'{key}: ' + json.dumps(dict(box, text=said.get(key) or box.get('text')), ensure_ascii=False))
    return '\n'.join(keep).strip(), front


def save(kind, sport, day, body, model, packet):
    os.makedirs(DRAFTS, exist_ok=True)
    check = unchecked_numbers(body, packet)   # the box sentences too
    body, boxes = box_front(body, packet) if kind == 'preview' else (body, [])
    front = ['---', f'title: {json.dumps(title(kind, sport, day, packet), ensure_ascii=False)}', f'sport: {sport}', f'kind: {kind}',
             f'date: {day}', f"written: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}", f'model: {model}',
             f'check: {json.dumps(check)}']
    if sport == daily.ALL:   # the sports it covers
        front.append(f"sports: {json.dumps([sp['key'] for sp in sports.SPORTS if sports.seo_name(sp) in (packet.get('sports') or {})])}")
    m = re.search(r'(\d+)', str(packet.get('week') or '')) if kind == 'preview' and weekly_preview(sport) else None
    if m:   # a weekly piece's page: /nfl/preview/week-11/
        front.append(f'week: {m.group(1)}')
    if kind == 'preview':   # the lead game (the admin's dropdown changes it) and the Matchup of the Day
        lead, motd = pv.lead_of(sport, day), pv.motd_of(sport, day)
        if lead:
            front.append(f"lead: {lead['sport']}:{lead['id']}")
        if motd:
            front.append(f'motd: {motd[0]}:{motd[1]}')
    front += boxes + ['---', '']
    # plain hyphens only: Claude's long dashes become "-" here, not a failed refresh
    with open(draft_path(kind, sport, day), 'w', encoding='utf-8') as f:
        f.write(hyphens.plain('\n'.join(front) + body + '\n'))
    # the packet beside the draft, so the editor can check every number
    with open(draft_path(kind, sport, day)[:-3] + '.packet.json', 'w', encoding='utf-8') as f:
        f.write(hyphens.plain(json.dumps(packet, indent=1, ensure_ascii=False)))
    print(f'wrote {os.path.relpath(draft_path(kind, sport, day), ROOT)}' + (f' (check: {", ".join(check)})' if check else ''))


def exists(kind, sport, day):
    """A draft or published piece for that day; a weekly preview: for that week."""
    name = f'{sport}-{kind}-{day}.md'
    if os.path.exists(os.path.join(DRAFTS, name)) or os.path.exists(os.path.join(PUBLISHED, name)):
        return True
    if kind == 'preview' and weekly_preview(sport):
        sp = pv.sport_of(sport)
        wk = (pv.week_of(sp, day) or {}).get('key')
        for folder in (DRAFTS, PUBLISHED):
            for f in os.listdir(folder) if os.path.isdir(folder) else []:
                m = re.fullmatch(rf'{sport}-preview-(\d{{4}}-\d{{2}}-\d{{2}})\.md', f)
                if wk and m and (pv.week_of(sp, m.group(1)) or {}).get('key') == wk:
                    return True
    return False


def published(kind, sport, day):
    return os.path.exists(os.path.join(PUBLISHED, f'{sport}-{kind}-{day}.md'))


def lines_posted(packet):
    """A weekly preview waits until the week's lines are up."""
    return any(g.get('lines') for g in packet.get('games') or [])


def packet_for(kind, sport, day):
    """The recap dated `day` covers the games the night before."""
    if weekly(sport) and (kind == 'recap' or weekly_preview(sport)):   # the week's own rules (week_recap / week_preview)
        return builder(kind, sport)(day)
    games_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat() if kind == 'recap' else day
    return builder(kind, sport)(games_day)


def scheduled(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(ET)
    if not sports.PREVIEW_LIVE:   # content/site_settings.json switches Preview off: no drafts, no API calls
        print('Preview is off (PREVIEW_LIVE); no drafts written')
        return
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY not set; no drafts written')
        return
    day = now.date().isoformat()
    on = {sp['key'] for sp in sports.shown(now.date())}
    for kind in WINDOWS:
        if kind == 'recap' and not daily.RECAP:
            continue
        for sport in [s for s in SPORTS if s in on] + ([daily.ALL] if kind == 'preview' else []):
            wday, start, end = (WEEKLY_WINDOWS if weekly(sport) else WINDOWS)[kind]
            if kind == 'preview':   # the admin's DRAFT_TIME_ET (and WEEKLY_DRAFT_DAY for a weekly preview)
                wday = sports.weekly_draft_day() if weekly_preview(sport) else None
                if (now.hour, now.minute) < sports.draft_time() or now.hour > end:
                    continue
                start = 0
            if (wday is not None and now.weekday() != wday) or not start <= now.hour <= end:
                continue
            if exists(kind, sport, day):
                continue
            packet = packet_for(kind, sport, day)
            if not packet:
                print(f'{sport} {kind} {day}: no games')
                continue
            if kind == 'preview' and weekly_preview(sport) and not lines_posted(packet):
                print(f'{sport} {kind} {day}: the week\'s lines aren\'t posted yet')
                continue
            try:
                body, model = write_piece(kind, sport, day, packet)
            except Exception as e:   # one failed draft never stops the refresh; the next run retries
                print(f'{sport} {kind} {day} failed: {e}')
                continue
            save(kind, sport, day, body, model, packet)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        scheduled()
    else:
        kind, sport = args[0], args[1]
        day = args[2] if len(args) > 2 else datetime.now(ET).date().isoformat()
        if published(kind, sport, day) and '--dry-run' not in sys.argv:   # the admin's Redraft: unpublish first
            sys.exit(f'{sport}-{kind}-{day} is published; unpublish it before redrafting')
        packet = packet_for(kind, sport, day)
        if '--dry-run' in sys.argv or not packet:
            print(json.dumps(packet, indent=1, ensure_ascii=False))
        else:
            body, model = write_piece(kind, sport, day, packet)
            save(kind, sport, day, body, model, packet)
