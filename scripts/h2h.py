"""
Head to head pages: /{sport}/matchups/{a}-vs-{b}/, one per pair of teams,
the two names in alphabetical order (sports.matchup_slug); the other order
is a redirect stub with a canonical to the real page.

Which pairs: every pair in a pro league; college pairs (both Division I /
FBS) that played this season or last, or are scheduled.

The page is static HTML (written once per sport from a shell rendered
once, so ~8,000 pages build in seconds): the breadcrumb, the H1, the next
meeting (or the last one) and the meetings list, and last season's
meetings as JSON (#h2hPrev). assets/sport.js (renderH2H) draws the rest
from the sport's data.json (NHL: sport.json), odds files and
{slug}/h2h.json, written here by build_data:

  {angle: {game id: [{bet, n, trends: [{t, r}]}]},   the game's trends by bet,
                                                     the most agreeing first
   previewDays: [date, ...]}                         days with a Preview
"""
import html as html_lib
import json
import os
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from itertools import combinations

import sports
from sport_build import ET, read_json, write_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLEGE = ('ncaab', 'ncaaf')
ANGLE_DAYS = 4     # the angle: games in the next 4 days
ANGLE_BETS = 4     # bets per game
ANGLE_ROWS = 4     # trends per bet


def esc(s):
    return html_lib.escape(str(s or ''), quote=True)


# ------------------------------------------------------------ the data
def load_doc(sp):
    return read_json(os.path.join(ROOT, sp['slug'], 'sport.json' if sp['key'] == 'nhl' else 'data.json'), {}) or {}


def prev_season(sp):
    """(label, {date: [game]}) of last season, in the shared shape (NHL's
    history.json is its own shape: converted here)."""
    h = read_json(os.path.join(ROOT, sp['slug'], 'history.json'), {}) or {}
    games = h.get('games') or {}
    if isinstance(games, list):
        import nhl_sport
        out = {}
        for g in games:
            if g.get('awayFinal') is None or not g.get('date'):
                continue
            out.setdefault(g['date'], []).append(nhl_sport.game(dict(g, state='FINAL'), g['date']))
        games = out
    return h.get('seasonLabel') or '', games


def all_games(games):
    for d in sorted(games or {}):
        for g in games[d]:
            yield d, g


def name(doc, key):
    """Pro: the nickname (Celtics); college: the school (North Carolina)."""
    t = (doc.get('teams') or {}).get(key) or {}
    return t.get('short') or t.get('name') or key


def team_part(doc, key):
    t = (doc.get('teams') or {}).get(key) or {}
    return t.get('mu') or sports.team_slug(name(doc, key))


def pair_slug(doc, a, b):
    return sports.matchup_slug(name(doc, a), name(doc, b))


def path(sp, doc, a, b):
    """'/nba/matchups/celtics-vs-kings/', or None when there's no page."""
    teams = doc.get('teams') or {}
    if a not in teams or b not in teams or a == b:
        return None
    return f"{sports.section_path(sp, 'games')}{pair_slug(doc, a, b)}/"


def pairs(sp, doc, prev):
    """[(a, b)] with a page, a first by its URL name."""
    teams = doc.get('teams') or {}
    if sp['key'] in COLLEGE:
        seen = set()
        for games in (doc.get('games') or {}, prev):
            for _, g in all_games(games):
                if g.get('away') in teams and g.get('home') in teams and g['away'] != g['home']:
                    seen.add(frozenset((g['away'], g['home'])))
        out = [tuple(p) for p in seen]
    else:
        out = list(combinations(teams, 2))
    return sorted(tuple(sorted(p, key=lambda k: team_part(doc, k))) for p in out)


def meetings(games, a, b):
    """[(date, game)] between the two teams, oldest first."""
    return [(d, g) for d, g in all_games(games) if {g.get('away'), g.get('home')} == {a, b}]


def header_game(cur, prev):
    """(date, game, 'next' | 'last'): the next meeting this season, else the
    last one (this season or last); None when they never met."""
    nxt = next(((d, g) for d, g in cur if g.get('state') in ('pre', 'in')), None)
    if nxt:
        return nxt + ('next',)
    done = [(d, g) for d, g in prev + cur if g.get('state') == 'final']
    return done[-1] + ('last',) if done else None


# ------------------------------------------------------------ the words
def seg_h1(sp):
    """'1st Quarter & 1st Half', '1st Inning & First Five'."""
    return ' & '.join(s['label'].replace(' Innings', '') for s in sp['segments'])


def when_et(g, d):
    t = g.get('start')
    try:
        dt = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(ET)
    except (AttributeError, ValueError):
        return date.fromisoformat(d).strftime('%a, %b %-d, %Y')
    return dt.strftime('%a, %b %-d, %Y · %-I:%M %p ET')


def short_day(d):
    return date.fromisoformat(d).strftime('%b %-d, %Y')


def seg_won(sp, g):
    """The first segment's winner ('away' / 'home' / 'tie'), or None."""
    k = sp['segments'][-1]['key'] if sp['sport_type'] == 'baseball' else sp['segments'][0]['key']
    r = (g.get('res') or {}).get(k) or {}
    sc = r.get('sc')
    if not sc or r.get('na'):
        return None
    return 'away' if sc[0] > sc[1] else 'home' if sc[1] > sc[0] else 'tie'


def meta(sp, doc, a, b, cur, prev, prev_label, head):
    """{title, h1, desc}: the title names the header game's away team first."""
    away, home = (head[1]['away'], head[1]['home']) if head else (a, b)
    seg_tag = sp['segments'][-1]['tag'] if sp['sport_type'] == 'baseball' else sp['segments'][0]['tag']
    title = f'{name(doc, away)} vs {name(doc, home)} {sports.seg_words(sp)} Odds, Trends & Head to Head | Run To Your Bets'
    h1 = f'{name(doc, a)} vs {name(doc, b)}: {seg_h1(sp)} Matchup'
    done = [g for _, g in prev + cur if g.get('state') == 'final']
    wins = {a: 0, b: 0}
    for g in done:
        w = seg_won(sp, g)
        if w in ('away', 'home'):
            wins[g[w]] += 1
    since = f' since {prev_label}' if prev_label else ''
    if done:
        lead = max((a, b), key=lambda k: wins[k])
        tally = (f'; the {name(doc, lead)} won the {seg_tag} in {wins[lead]}' if wins[lead] else '')
        line = f"{len(done)} meeting{'s' if len(done) != 1 else ''}{since}{tally}."
    else:
        line = f'No meetings{since}.'
    if head and head[2] == 'next':
        line += f" Next game {date.fromisoformat(head[0]).strftime('%b %-d')}."
    desc = (f"{sp['label']} {name(doc, away)} vs {name(doc, home)} {sports.segment_summary(sp).lower()} odds, "
            f'trends and head to head: {line}')
    return {'title': title, 'h1': h1, 'desc': desc}


# ------------------------------------------------------------ the page
def game_line(doc, g):
    if g.get('state') == 'final' and g.get('as') is not None and g.get('hs') is not None:
        ot = f" {g['ot']}" if g.get('ot') else ''
        return f"{esc(name(doc, g['away']))} {g['as']} @ {esc(name(doc, g['home']))} {g['hs']}{esc(ot)}"
    return f"{esc(name(doc, g['away']))} @ {esc(name(doc, g['home']))}"


def body(sp, doc, a, b, cur, prev, prev_label, head, root):
    """The page's static content (assets/sport.js redraws #sportApp), then
    last season's meetings for the script."""
    crumb_name = f'{name(doc, a)} vs {name(doc, b)}'
    out = ''
    if head:
        d, g, which = head
        where = ' · '.join(x for x in (g.get('ven'), ', '.join(g.get('tv') or [])) if x)
        out += (f'<section class="tm-sec"><h2 class="team-section-title">{"Next meeting" if which == "next" else "Last meeting"}</h2>'
                f'<p class="h2h-static">{esc(when_et(g, d))} · {game_line(doc, g)}' + (f' · {esc(where)}' if where else '') + '</p></section>')
    rows = [(d, g) for d, g in prev + cur if g.get('state') == 'final']
    out += ('<section class="tm-sec"><h2 class="team-section-title">Head to head</h2>'
            + (''.join(f'<p class="h2h-static">{esc(short_day(d))} · {game_line(doc, g)}</p>' for d, g in reversed(rows))
               if rows else f'<p class="h2h-static">No meetings since {esc(prev_label or "last season")}.</p>')
            + '</section>')
    # sorted keys: the same bytes every build, so a page only changes when its pair plays
    data = json.dumps({'label': prev_label, 'games': [g for _, g in prev]}, separators=(',', ':'), sort_keys=True).replace('</', '<\\/')
    return (f'<div id="sportApp" data-section="h2h" data-a="{esc(a)}" data-b="{esc(b)}" data-pair="{esc(crumb_name)}">{out}</div>'
            f'<script type="application/json" id="h2hPrev">{data}</script>')


def crumb(sp, pair_name, root):
    m = sports.section_path(sp, 'games')
    return (f'<nav class="gd-crumb" aria-label="Breadcrumb"><a href="{root}{sp["slug"]}/">{esc(sports.seo_name(sp))}</a>'
            f'<span aria-hidden="true">›</span><a href="{root}{m.lstrip("/")}">Matchups</a>'
            f'<span aria-hidden="true">›</span><span aria-current="page">{esc(pair_name)}</span></nav>')


# the shell's title, H1 and body (the body has #sportApp, so lighten() adds the page code)
TOKENS = ('@@H2H_TITLE@@', '@@H2H_H1@@', '<div id="sportApp" data-h2h-body></div>')


def write_pages(sp, shell):
    """Every pair's page and its stub; folders of pairs no longer shown are
    removed. shell: the sport's page, rendered once with TOKENS (and the
    __META_DESC__ meta tag), already lightened. Returns the page count."""
    doc = load_doc(sp)
    if not doc.get('teams'):
        return 0
    from build_site import redirect_page_html
    prev_label, prev = prev_season(sp)
    folder = sports.section_path(sp, 'games').strip('/')
    base = os.path.join(ROOT, folder)
    root = '../' * 3
    want = set()
    for a, b in pairs(sp, doc, prev):
        slug = pair_slug(doc, a, b)
        cur, old = meetings(doc.get('games'), a, b), meetings(prev, a, b)
        head = header_game(cur, old)
        m = meta(sp, doc, a, b, cur, old, prev_label, head)
        page = shell.replace(TOKENS[0], esc(m['title'])).replace(TOKENS[1], esc(m['h1']))
        page = re.sub(r'<meta name="description" content="[^"]*">', lambda x: f'<meta name="description" content="{esc(m["desc"])}">', page, count=1)
        page = page.replace('<div class="page-head">', crumb(sp, f'{name(doc, a)} vs {name(doc, b)}', root) + '<div class="page-head">', 1)
        page = page.replace(TOKENS[2], body(sp, doc, a, b, cur, old, prev_label, head, root))
        write(os.path.join(base, slug, 'index.html'), page)
        other = f'{team_part(doc, b)}-vs-{team_part(doc, a)}'
        write(os.path.join(base, other, 'index.html'), redirect_page_html(f'../{slug}/', keep_query=True, canonical=f'../{slug}/'))
        want.update((slug, other))
    for d in os.listdir(base) if os.path.isdir(base) else []:
        if '-vs-' in d and d not in want and os.path.isdir(os.path.join(base, d)):
            shutil.rmtree(os.path.join(base, d))
    return len(want) // 2


def write(p, text):
    """Writes only when the text changed (the refresh rebuilds every page)."""
    try:
        with open(p, encoding='utf-8') as f:
            if f.read() == text:
                return
    except OSError:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)


# ------------------------------------------------------------ h2h.json
def build_data(sp, doc, trends_doc, slug_dir, now_utc=None):
    """{slug}/h2h.json: the angle (the game's trends, by bet) for the games
    in the next ANGLE_DAYS days, and the days with a Preview."""
    import hub
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    end = (date.fromisoformat(today) + timedelta(days=ANGLE_DAYS)).isoformat()
    key, slate_games, before = hub.slate(doc, today) if doc.get('games') else (None, [], today)
    slate_ids = {str(g['id']) for g in slate_games}
    cards = ((trends_doc.get('slates') or {}).get(key) or {}).get('cards') or [] if key else []
    angle = {}
    seqs = {k: hub.team_seqs(doc, before, k) for k in {x[0] for x in hub.market_keys(doc)}}
    for d, g in all_games(doc.get('games')):
        if g.get('state') != 'pre' or d < today or (d > end and str(g['id']) not in slate_ids):
            continue
        groups = hub.game_trends(doc, g, cards if str(g['id']) in slate_ids else [], seqs)
        bets = []
        for (k, m, pick), ts in groups.items():
            rates = [t['rate'] for t in ts if t.get('rate')]
            bets.append((len(ts), sum(rates) / len(rates) if rates else 0, {
                'bet': hub.bet_words(doc, g, k, m, pick), 'n': len(ts),
                'trends': [{'t': t.get('short') or t['text'], 'r': t['rec']} for t in ts[:ANGLE_ROWS]]}))
        bets.sort(key=lambda x: (-x[0], -x[1]))
        if bets:
            angle[str(g['id'])] = [x[2] for x in bets[:ANGLE_BETS]]
    pv = os.path.join(slug_dir, 'preview')
    days = sorted(x for x in os.listdir(pv) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', x)) if os.path.isdir(pv) else []
    write_json(os.path.join(slug_dir, 'h2h.json'), {'angle': angle, 'previewDays': days})
