"""
Streaks: /streaks/ (the index, every sport) and /{sport}/streaks/ (every
sport, hidden ones too). The build writes {slug}/streaks.json and
assets/sport.js (renderStreaks) draws the sport page from it: Tonight
(football: This Week), Still Running, Run's Over and Records, filtered by
Segment · Market · All / Home / Away. The index is static (index_html).

Every segment the sport has, the Full Run's too (Premium: the gold dot,
gold bar and PREMIUM tag, the same PREMIUM.fullRun flag as the Due Factor),
and every market:
  NBA, WNBA, NFL, NCAAF, NCAAB: Win / Loss, Spread, O/U in each segment.
  NHL: 1st Period ML, O/U 1.5, BTTS, 3-way; 2nd / 3rd Period results only
  (won the period, scored in it, Over 0.5 / 1.5 goals); Full Game ML, puck
  line, O/U.
  MLB: 1st Inning NRFI / YRFI; First 5 and Full Game ML, run line, O/U.

A streak is a team's run of the same result, oldest game to newest, the
same way the team pages count Current streaks: every graded game (college:
non-Division I opponents too), a tie or push ends it, 3-way a tie is a
loss. Home / road streaks count the team's home games only, or its road
games only. Only league teams (college: Division I / FBS) own a streak.

streaks.json:
  {sport, weekly, cur (in season), today, matchups, segs: [{k, label, short,
   tag, fr, m: [market id]}], markets: [{id, label, short}],
   running: [S] (3+, longest first), ended: {day, label, list: [E]},
   tonight: {mode: tonight / week / next, day, label, games: [{id, day,
     start, away, home, odds, fo, s: [S]}]} or null,
   records: [{label, list: {seg|market|venue: [R]}}] (this season, then last)}
  S: {t, k, m, kd (the result it repeats), n, v (all / home / away),
      gt (a home / road streak longer than the overall one: shown in All)}
  E: S + {day, opp, gid, ha (the team's side in the game that ended it)}
  R: {t, kd, n, a, b (first / last day), alive}
"""
import os
from datetime import date, datetime, timedelta

import due_factor
import front
import icons
import sport_build
import sports
from front import esc

ROOT = sport_build.ROOT
MIN_RUN = 3    # Still Running: 3+
MIN_HOT = 5    # Tonight and Run's Over: 5+
TOP = 5        # Records: the 5 longest per market
INDEX_TOP = 10  # the index's Still Running across sports
# mirrors assets/sport.js PREMIUM.fullRun (tests/test_streaks.py checks they agree)
FULL_RUN_LOCKED = False
VENUES = ('all', 'home', 'away')


# ------------------------------------------------------------ segments
def segments(sp):
    """[(seg key, label, phone label, words tag, Full Run?, [market id])]."""
    key = sp['key']
    if key == 'nhl':
        return [('1p', '1st Period', '1P', '1P', False, ['su', 'tot', 'btts', 'ml3']),
                ('2p', '2nd Period', '2P', '2P', True, ['su', 'scored', 'o05', 'tot']),
                ('3p', '3rd Period', '3P', '3P', True, ['su', 'scored', 'o05', 'tot']),
                ('game', 'Full Game', 'Game', 'Game', True, ['su', 'ats', 'tot'])]
    if key == 'mlb':
        return [('1i', '1st Inning', '1st Inn', '', False, ['rfi']),
                ('f5', 'First 5', 'F5', 'F5', False, ['su', 'ats', 'tot']),
                ('game', 'Full Game', 'Game', 'Game', True, ['su', 'ats', 'tot'])]
    out = []
    for s, fr in [(s, False) for s in sp['segments']] + [(s, True) for s in sp.get('full_run') or []]:
        tag = 'Game' if s['key'] == 'game' else s['tag']
        out.append((s['key'], s['label'], tag, tag, fr, ['su', 'ats', 'tot']))
    return out


def market_names(sp):
    """{id: (label, phone label)} in the Market bar's order."""
    ml = sp['key'] in ('nhl', 'mlb')
    spread = {'nhl': 'Puck Line', 'mlb': 'Run Line'}.get(sp['key'], 'Spread')
    names = {'rfi': ('NRFI / YRFI', 'NRFI'), 'su': ('ML' if ml else 'Win / Loss', 'ML' if ml else 'W/L'),
             'ats': (spread, {'nhl': 'PL', 'mlb': 'RL'}.get(sp['key'], 'Spread')), 'tot': ('O/U', 'O/U'),
             'btts': ('BTTS', 'BTTS'), 'ml3': ('3-way', '3-way'), 'scored': ('Scored', 'Scored'), 'o05': ('O/U 0.5', 'O/U 0.5')}
    order = []
    for *_, ms in segments(sp):
        order += [m for m in ms if m not in order]
    return {m: names[m] for m in order}


# ------------------------------------------------------------- results
FLIP = {'W': 'L', 'L': 'W', 'T': 'T', 'P': 'P'}


def outcome(m, k, x, side):
    """One team's result in a market: the value its streak repeats, 'T' / 'P'
    (ends a streak), or None (not graded in this market)."""
    home = side == 'home'
    sc = x.get('sc') or [0, 0]
    if m in ('su', 'ml3'):
        v = x.get('su')
        if not v or v == 'NA':
            return None
        v = FLIP.get(v, v) if home else v
        v = 'T' if v == 'P' else v
        return ('L' if v == 'T' else v) if m == 'ml3' else v   # 3-way: a tied segment loses
    if m == 'ats':
        v = x.get('ats')
        return None if not v or v == 'NA' else (FLIP.get(v, v) if home else v)
    if m == 'tot':
        if k in ('2p', '3p'):   # results only: the period's goals against 1.5
            return 'O' if sc[0] + sc[1] > 1.5 else 'U'
        v = x.get('tot')
        return None if not v or v == 'NA' else v
    if m == 'o05':
        return 'O' if sc[0] + sc[1] > 0.5 else 'U'
    if m == 'scored':
        return 'Y' if sc[1 if home else 0] > 0 else 'N'
    if m in ('btts', 'rfi'):
        v = x.get(m)
        return v if v in ('Y', 'N') else None
    return None


def seg_result(g, k):
    x = (g.get('res') or {}).get(k) or (g.get('fr') or {}).get(k)
    return x if x and x.get('sc') and not x.get('na') else None


def week_of(g, day):
    """A football game's week: its ESPN week, else its Tuesday-Monday week."""
    if g.get('wk'):
        return g['wk']
    d = date.fromisoformat(day)
    return 'd-' + (d - timedelta(days=(d.weekday() - 1) % 7)).isoformat()


# ------------------------------------------------------------- the runs
def sequences(sp, doc):
    """{(team, seg, market, venue): [(value, day, game, side)]}, oldest first,
    for every league team, from every graded segment (a game in progress
    counts its finished halves / periods, as the team pages do)."""
    league = doc.get('teams') or {}
    games = []
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            if g.get('res') or g.get('fr'):
                games.append((d, g))
    games.sort(key=lambda x: (x[0], x[1].get('start') or ''))
    out = {}
    for k, _, _, _, _, ms in segments(sp):
        for d, g in games:
            x = seg_result(g, k)
            if not x:
                continue
            for side in ('away', 'home'):
                t = g.get(side)
                if t not in league:
                    continue
                for m in ms:
                    v = outcome(m, k, x, side)
                    if v is None:
                        continue
                    for venue in ('all', side):
                        out.setdefault((t, k, m, venue), []).append((v, d, g, side))
    return out


def runs(seq):
    """[{kd, n, a, b, i (index of its last game), alive}] of a sequence; a tie
    or push is no run and ends the one before it."""
    out, cur = [], None
    for i, (v, d, _, _) in enumerate(seq):
        if v in ('T', 'P'):
            cur = None
            continue
        if cur and cur['kd'] == v:
            cur['n'] += 1
            cur['b'], cur['i'] = d, i
        else:
            cur = {'kd': v, 'n': 1, 'a': d, 'b': d, 'i': i}
            out.append(cur)
    for r in out:
        r['alive'] = r['i'] == len(seq) - 1
    return out


def running_of(seqs):
    """{(t, k, m, venue): run} of every streak still going."""
    out = {}
    for key, seq in seqs.items():
        rs = runs(seq)
        if rs and rs[-1]['alive']:
            out[key] = rs[-1]
    return out


def with_gt(items, overall):
    """Mark home / road streaks longer than the team's overall streak in the
    same segment, market and result (All shows only those)."""
    for s in items:
        if s['v'] != 'all':
            o = overall.get((s['t'], s['k'], s['m']))
            s['gt'] = 1 if not o or o['kd'] != s['kd'] or s['n'] > o['n'] else 0
    return items


def last_period(sp, doc, cur):
    """The Run's Over window: (set of days, label). Daily: the last game day;
    football: the last week every game of which is final (else the last
    week with a final)."""
    finals, pending = {}, set()
    weekly = sp.get('schedule') == 'week'
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            key = week_of(g, d) if weekly else d
            if g.get('state') == 'final':
                finals.setdefault(key, set()).add(d)
            elif cur and g.get('state') not in ('postponed', 'canceled'):
                pending.add(key)
    if not finals:
        return set(), ''
    keys = sorted(finals, key=lambda k: max(finals[k]))
    done = [k for k in keys if k not in pending]
    key = (done or keys)[-1]
    days = finals[key]
    if weekly:
        labels = {w['key']: w.get('label') for w in doc.get('weeks') or []}
        return days, labels.get(key) or 'Last week'
    return days, day_label(key)


def day_label(day):
    d = date.fromisoformat(day)
    return f"{d.strftime('%a, %b')} {d.day}"


def short_day(day):
    d = date.fromisoformat(day)
    return f"{d.strftime('%b')} {d.day}"


def season_doc(sp, doc, cur, today):
    """One season's running, ended and records."""
    seqs = sequences(sp, doc)
    live = running_of(seqs)
    overall = {(t, k, m): r for (t, k, m, v), r in live.items() if v == 'all'}
    running = []
    if cur:
        for (t, k, m, v), r in live.items():
            if r['n'] >= MIN_RUN:
                running.append({'t': t, 'k': k, 'm': m, 'kd': r['kd'], 'n': r['n'], 'v': v, 'a': r['a']})
        with_gt(running, overall)
        running.sort(key=lambda s: (-s['n'], s['t'], s['k'], s['m'], s['v']))
    # Run's Over: the run before each team's last game, when that game falls
    # in the window and ended a run of 5+
    days, label = last_period(sp, doc, cur)
    ended, ended_all = [], {}
    for (t, k, m, v), seq in seqs.items():
        if len(seq) < 2 or seq[-1][1] not in days:
            continue
        rs = runs(seq[:-1])
        if not rs or not rs[-1]['alive']:
            continue
        r, last = rs[-1], seq[-1]
        if last[0] == r['kd'] or r['n'] < MIN_HOT:
            continue
        g, side = last[2], last[3]
        e = {'t': t, 'k': k, 'm': m, 'kd': r['kd'], 'n': r['n'], 'v': v, 'day': last[1], 'gid': str(g.get('id') or ''),
             'opp': g['home' if side == 'away' else 'away'], 'ha': side}
        ended.append(e)
        if v == 'all':
            ended_all[(t, k, m)] = r
    with_gt(ended, ended_all)
    ended.sort(key=lambda e: (e['day'], e['n']), reverse=True)
    # Records: the longest runs per segment, market and venue
    recs = {}
    for (t, k, m, v), seq in seqs.items():
        for r in runs(seq):
            if r['n'] >= 2:
                recs.setdefault(f'{k}|{m}|{v}', []).append({'t': t, 'kd': r['kd'], 'n': r['n'], 'a': r['a'], 'b': r['b'], 'alive': 1 if r['alive'] and cur else 0})
    for key in recs:
        recs[key] = sorted(recs[key], key=lambda r: (-r['n'], r['b'], r['t']))[:TOP]
    return {'running': running, 'ended': {'label': label, 'list': ended}, 'records': recs, 'seqs': seqs}


def tonight(sp, doc, running, today):
    """Tonight's games (football: this week's) with a streak of 5+ on the
    line, else the next game day with lines ('next'); None when neither."""
    weekly = sp.get('schedule') == 'week'
    by_team = {}
    for s in running:
        if s['n'] >= MIN_HOT and (s['v'] == 'all' or s.get('gt')):
            by_team.setdefault(s['t'], []).append(s)
    pre = []
    for d in sorted(doc.get('games') or {}):
        if d < today:
            continue
        for g in doc['games'][d]:
            if g.get('state') == 'pre':
                pre.append((d, g))

    def game_of(d, g):
        ss = [dict(s) for side in ('away', 'home') for s in by_team.get(g[side], []) if s['v'] in ('all', side)]
        if not ss:
            return None
        ss.sort(key=lambda s: (-s['n'], s['t'], s['k'], s['m']))
        return {'id': str(g.get('id') or ''), 'day': d, 'start': g.get('start'), 'away': g['away'], 'home': g['home'],
                'odds': g.get('odds') or {}, 'fo': g.get('fo') or {}, 's': ss}
    if weekly:
        wk = week_of(pre[0][1], pre[0][0]) if pre else None
        games = [x for x in (game_of(d, g) for d, g in pre if week_of(g, d) == wk) if x]
        labels = {w['key']: w.get('label') for w in doc.get('weeks') or []}
        return {'mode': 'week', 'day': pre[0][0], 'label': labels.get(wk) or 'This week', 'games': games} if games else None
    games = [x for x in (game_of(d, g) for d, g in pre if d == today) if x]
    if games:
        return {'mode': 'tonight', 'day': today, 'label': day_label(today), 'games': games}
    for d in sorted({d for d, _ in pre if d > today}):
        day_games = [(dd, g) for dd, g in pre if dd == d]
        if not any(g.get('odds') for _, g in day_games):
            continue
        games = [x for x in (game_of(dd, g) for dd, g in day_games) if x]
        return {'mode': 'next', 'day': d, 'label': day_label(d), 'games': games} if games else None
    return None


def build(sp, today=None):
    """The streaks.json document."""
    today = today or datetime.now(sport_build.ET).date()
    docs = due_factor.docs(sp)
    cur = sports.in_season(sp, today)
    out = {'sport': sp['key'], 'weekly': sp.get('schedule') == 'week', 'cur': cur, 'today': today.isoformat(),
           'matchups': sports.section_path(sp, 'games').lstrip('/'),
           'segs': [{'k': k, 'label': lab, 'short': sh, 'tag': tag, 'fr': 1 if fr else 0, 'm': ms} for k, lab, sh, tag, fr, ms in segments(sp)],
           'markets': [{'id': m, 'label': a, 'short': b} for m, (a, b) in market_names(sp).items()],
           'running': [], 'ended': {'label': '', 'list': []}, 'tonight': None, 'records': []}
    for i, (doc, is_cur) in enumerate(docs):
        s = season_doc(sp, doc, cur and is_cur, today)
        if i == 0:
            out['running'], out['ended'] = s['running'], s['ended']
            if cur and is_cur:
                out['tonight'] = tonight(sp, doc, s['running'], today.isoformat())
        out['records'].append({'label': str(doc.get('seasonLabel') or doc.get('season') or ''), 'list': s['records']})
    return out


def write_data(sp, today=None):
    doc = build(sp, today)
    sport_build.write_json(os.path.join(ROOT, sp['slug'], 'streaks.json'), doc)
    return doc


# ---------------------------------------------------------------- words
def what(sp, k, m, kd):
    """The streak, short: "Game no cover", "1Q Under", "2H losses", "NRFI"."""
    tag = next((x[3] for x in segments(sp) if x[0] == k), '')
    nhl15 = sp['key'] == 'nhl' and k != 'game'
    w = {'su': {'W': 'wins', 'L': 'losses'}, 'ml3': {'W': '3-way wins', 'L': '3-way losses'},
         'ats': {'W': 'covers', 'L': 'no cover'},
         'tot': {'O': 'Over 1.5' if nhl15 else 'Over', 'U': 'Under 1.5' if nhl15 else 'Under'},
         'o05': {'O': 'Over 0.5', 'U': 'Under 0.5'}, 'btts': {'Y': 'BTTS Yes', 'N': 'BTTS No'},
         'scored': {'Y': 'scored', 'N': 'scoreless'}, 'rfi': {'Y': 'YRFI', 'N': 'NRFI'}}[m][kd]
    return f'{tag} {w}'.strip()


def venue_tag(v):
    return {'home': 'at home', 'away': 'on the road'}.get(v, '')


# ---------------------------------------------------------------- pages
def off_note(sp, today):
    """"MLB is in the off-season. The 2026 season's longest streaks. Opening
    Day: Wed, Mar 24, 2027", or '' in season."""
    if sports.in_season(sp, today):
        return ''
    docs = due_factor.docs(sp)
    if not docs:
        return ''
    label = str(docs[0][0].get('seasonLabel') or docs[0][0].get('season') or '')
    return f"{sp['label']} is in the off-season. The {label} season's longest streaks. {due_factor.next_season(sp, today)}"


def page_body(sp, today, tabs=''):
    """The Trends hub cards, the off-season note bar, then the app
    assets/sport.js draws (renderStreaks)."""
    write_data(sp, today)
    note = off_note(sp, today)
    bar = f'<div class="df2-off" role="note">{esc(note)}</div>' if note else ''
    return (tabs + bar + '<div id="sportApp" data-section="streaks"><div class="no-games-note">Loading&hellip;</div>'
            '<noscript>This page needs JavaScript.</noscript></div>')


def page_meta(sp):
    h1 = f'{sports.seo_name(sp)} Betting Streaks'
    return {'title': f'{h1}: {sports.seg_words(sp)} Win, Cover and Over Streaks | Run To Your Bets', 'h1': esc(h1), 'section': 'streaks',
            'desc': esc(f"{sp['label']} streaks still running, the ones that just ended and the season's longest, in every segment and market.")}


# ---------------------------------------------------------------- index
def _row(sport, s, root, sport_tag=True, alt=False):
    """One Still Running row on the index: heat chip, sport, logo + name
    (phones: code), the streak and its home / road tag."""
    fr = next((x[4] for x in segments(sport.sp) if x[0] == s['k']), False)
    tag = venue_tag(s['v'])
    return (f'<li class="sk2-row{" sk2-frow" if fr else ""}{" sk2-alt" if alt else ""}" data-sport="{esc(sport.key)}">'
            f'<span class="sk-len {front.heat_cls(s["n"])}">{s["n"]}</span>'
            f'<span class="sk2-who">{icons.sport_icon(sport.sp) if sport_tag else ""}{sport.link(s["t"], sport.badge(s["t"], 22, root) + sport.name_html(s["t"]), root, "sk2-team")}</span>'
            f'<span class="sk2-what">{esc(what(sport.sp, s["k"], s["m"], s["kd"]))}'
            + (f' <span class="sk2-vt">{tag}</span>' if tag else '') + ('<span class="fr-tag">Premium</span>' if fr else '') + '</span></li>')


def _ended_row(sport, e, root, sport_tag=True):
    fr = next((x[4] for x in segments(sport.sp) if x[0] == e['k']), False)
    tag = venue_tag(e['v'])
    opp = sport.code(e['opp'])
    href = None
    ta, tb = sport.team(e['t']), sport.team(e['opp'])
    if ta.get('mu') and tb.get('mu'):
        a, b = sorted([ta['mu'], tb['mu']])
        href = f"{root}{sport.matchups}{a}-vs-{b}/"
    game = (f'<a href="{esc(href)}">{"vs" if e["ha"] == "home" else "@"} {esc(opp)}</a>' if href
            else f'{"vs" if e["ha"] == "home" else "@"} {esc(opp)}')
    return (f'<li class="sk2-row sk2-ended{" sk2-frow" if fr else ""}" data-sport="{esc(sport.key)}">'
            f'<span class="sk-len sk-over">{e["n"]}</span>'
            f'<span class="sk2-who">{icons.sport_icon(sport.sp) if sport_tag else ""}{sport.link(e["t"], sport.badge(e["t"], 22, root) + sport.name_html(e["t"]), root, "sk2-team")}</span>'
            f'<span class="sk2-what">{esc(what(sport.sp, e["k"], e["m"], e["kd"]))}' + (f' <span class="sk2-vt">{tag}</span>' if tag else '')
            + f' &middot; ended at {e["n"]} &middot; <span class="sk2-opp">{game}</span></span></li>')


def index_html(root=''):
    """/streaks/: the sport pills (All + the sports in season), Still Running
    across sports, Run's Over from the last game day, a card per sport in
    season, then the off-season sports with last season's longest."""
    today = datetime.now(sport_build.ET).date()
    live, off = [], []
    for sp in sports.LAUNCHED:
        doc = front.read_json(os.path.join(ROOT, sp['slug'], 'streaks.json'), None) or write_data(sp, today)
        (live if doc.get('cur') else off).append((front.Sport(sp), doc))
    pills = '<button type="button" class="sk2-pill" data-skp="all" aria-pressed="true">All</button>' + ''.join(
        f'<button type="button" class="sk2-pill" data-skp="{esc(s.key)}" aria-pressed="false">{icons.sport_icon(s.sp)}{esc(s.label)}</button>'
        for s, _ in live)

    def shown(xs):
        return [x for x in xs if x['v'] == 'all' or x.get('gt')]
    run = sorted([(s, x) for s, d in live for x in shown(d['running'])], key=lambda p: -p[1]['n'])
    # the top INDEX_TOP across sports (All), and each sport's own top INDEX_TOP (its pill)
    per, rows = {}, ''
    for i, (s, x) in enumerate(run):
        per[s.key] = per.get(s.key, 0) + 1
        if i < INDEX_TOP or per[s.key] <= INDEX_TOP:
            rows += _row(s, x, root, alt=i >= INDEX_TOP)
    ended = sorted([(s, x) for s, d in live for x in shown(d['ended']['list'])], key=lambda p: -p[1]['n'])
    erows = ''.join(_ended_row(s, x, root) for s, x in ended)
    still = (f'<section class="st-card sk2-card" aria-labelledby="skRun"><div class="st-head"><h4 id="skRun">Still Running</h4></div>'
             f'<ul class="sk2-list">{rows}</ul>' + ('' if rows else '<p class="tp-none">No streaks of 3 or more right now.</p>') + '</section>')
    over = (f'<section class="st-card sk2-card" aria-labelledby="skOver"><div class="st-head"><h4 id="skOver">Run&rsquo;s Over</h4></div>'
            f'<ul class="sk2-list">{erows}</ul>' + ('' if erows else '<p class="tp-none">No streak of 5 or more ended last night.</p>') + '</section>')
    cards = ''
    for s, d in live:
        top = next(iter(shown(d['running'])), None)
        body = f'<ul class="sk2-list">{_row(s, top, root, False)}</ul>' if top else '<p class="tp-none">No streaks of 3 or more right now.</p>'
        cards += (f'<section class="st-card sk2-card sk2-sport" data-sport="{esc(s.key)}"><div class="st-head"><h4>{icons.sport_icon(s.sp)}{esc(s.label)}</h4></div>'
                  f'<p class="sk2-lab">Longest running</p>{body}<p class="sk2-more"><a href="{root}{sports.section_path(s.sp, "streaks").lstrip("/")}">All {esc(s.label)} streaks &rarr;</a></p></section>')
    offc = ''
    for s, d in off:
        rec = (d['records'] or [{}])[0]
        best = sorted([(k, r) for k, rs in (rec.get('list') or {}).items() if k.endswith('|all') for r in rs[:1]], key=lambda p: -p[1]['n'])
        body = ''
        if best:
            k, r = best[0]
            seg, m, _ = k.split('|')
            body = (f'<ul class="sk2-list"><li class="sk2-row"><span class="sk-len {front.heat_cls(r["n"])}">{r["n"]}</span>'
                    f'<span class="sk2-who">{s.link(r["t"], s.badge(r["t"], 22, root) + s.name_html(r["t"]), root, "sk2-team")}</span>'
                    f'<span class="sk2-what">{esc(what(s.sp, seg, m, r["kd"]))} &middot; {esc(short_day(r["a"]))} - {esc(short_day(r["b"]))}</span></li></ul>')
        offc += (f'<section class="st-card sk2-card sk2-sport sk2-offs"><div class="st-head"><h4>{icons.sport_icon(s.sp)}{esc(s.label)}</h4></div>'
                 f'<p class="sk2-lab">{esc(rec.get("label") or "")} longest</p>{body or "<p class=tp-none>No streaks last season.</p>"}'
                 f'<p class="sk2-more"><a href="{root}{sports.section_path(s.sp, "streaks").lstrip("/")}">All {esc(s.label)} streaks &rarr;</a></p></section>')
    off_block = (f'<h2 class="sk2-h">Off-season</h2><div class="sk2-grid">{offc}</div>') if offc else ''
    return (f'<div class="sk2-index" id="skIndex"><div class="sk2-pills" role="group" aria-label="Sports">{pills}</div>'
            f'<div class="sk2-two">{still}{over}</div><div class="sk2-grid">{cards}</div>{off_block}</div>' + INDEX_JS)


INDEX_JS = '''<script>
(function() {
  // the sport pills: All, or one sport's rows and card
  var box = document.getElementById('skIndex');
  if (!box) return;
  function show(sp) {
    box.querySelectorAll('[data-skp]').forEach(function(b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-skp') === sp)); });
    box.querySelectorAll('.sk2-two [data-sport]').forEach(function(r) {
      r.hidden = sp === 'all' ? r.classList.contains('sk2-alt') : r.getAttribute('data-sport') !== sp;
    });
    box.querySelectorAll('.sk2-sport[data-sport]').forEach(function(c) { c.hidden = sp !== 'all' && c.getAttribute('data-sport') !== sp; });
  }
  box.addEventListener('click', function(e) { var b = e.target.closest('[data-skp]'); if (b) show(b.getAttribute('data-skp')); });
  show('all');
})();
</script>'''


def index_meta():
    return {'title': 'Betting Streaks: First Period, Quarter & Half Win, Cover and Over Streaks | Run To Your Bets',
            'h1': 'Betting Streaks', 'section': 'streaks',
            'desc': 'Every team streak still running across the NHL, NBA, NFL, college and MLB, the ones that just ended, and the longest of the season.'}
