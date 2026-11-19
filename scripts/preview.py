"""
Preview (was On Tap): the daily first-segment preview, written by Claude
from the site's numbers (scripts/daily_content.py, drafted from 8 AM ET),
approved in the admin's Preview tab and shown from 11 AM ET.

Pages (every one indexed and in the sitemap):
  /preview/                         today's all-sports preview (none today:
                                    the latest, with its date); canonical:
                                    the dated page
  /preview/YYYY-MM-DD/              each day's, kept for good
  /preview/archive/                 the past days, newest first
  /{sport}/preview/, /{sport}/preview/YYYY-MM-DD/, /{sport}/preview/archive/
                                    the same per sport (football: the
                                    Thursday Week Preview)
A sport with no games that day has no page for it.

The article: a yellow label, the H1 (the draft's headline), the dek, a
byline, the image card, then the body: the intro, the three boxes (Stat of the Night, League Trend,
Edge Play of the Night, from the draft's front matter), then all-sports:
an H2 per sport with its icon and game line, two paragraphs, "Also with
trends:" and "Read the full [sport] preview"; a sport: "The Matchups", a
yellow H3 per game with both logos and its venue / TV line. Then the
"more league trends" line, a muted line of the games with no trends
(sports with no games), and "Past previews". Desktop adds a right column: Tonight's
games and the Running Tab signup.

The draft's Markdown (daily_content.SYSTEM):
  # Headline
  > The dek, one sentence.
  Body paragraphs, ## / ### subheads (content/preview_writing_guide.md).
  Front matter: stat_of_night, league_trend, edge_play (each a JSON
  {sport, number, line, text}), picked by boxes() before drafting.
Older drafts (a bold first line) still work: the bold line is the headline,
the first short paragraph the dek.

The image card (assets/preview/{date}/{key}.png, 1200x630): the lead game's
sport and start, the RTYB wordmark, both teams' logos and full names, and a
yellow chip from its lead trend, on the brand purple. It's the page's
og:image too. Drawn from the site's own stylesheet (template.html .pc-*)
with headless Chrome; redrawn only when what's on it changes.

The lead game: among games with 2+ trends, the one with the strongest
season-rate trend (10+ games), never the Matchup of the Day (home: the
site's; a sport: its own) unless no other game has 2+ trends. A draft's
`lead:` line (the admin's dropdown) overrides it. Kept in
content/preview_leads.json so a page never changes its lead later.
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from datetime import date, datetime, timedelta, timezone

import daily
import front
import hub
import icons
import sports
import trends as tr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = front.ET
INDEX = 'preview'
ALL = daily.ALL
SHOW_HOUR = 11          # a preview dated today shows from 11 AM ET
MIN_TRENDS = 2          # the lead game needs 2+ trends
RATE_MIN = 10           # a season rate counts with 10+ games
PACKET_MAX = 15         # games in a sport's packet (college slates run 60+)
LEADS = os.path.join(ROOT, 'content', 'preview_leads.json')
CARD_DIR = 'assets/preview'
CARD_W, CARD_H = 600, 315   # CSS px, drawn at 2x: 1200x630
BIG_LOGO = 320              # px, the card's logos (assets/logos/{sport}/lg/)
CARD_VERSION = 1            # bump to redraw every card (a .pc-* style change)
FOOT = daily.FOOT


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write('\n')


def today_et(now_utc):
    return now_utc.astimezone(ET).date().isoformat()


def short_day(day):
    d = date.fromisoformat(day)
    return f"{d.strftime('%a, %b')} {d.day}"


def long_day(day):
    d = date.fromisoformat(day)
    return f"{d.strftime('%A, %b')} {d.day}, {d.year}"


_SPORTS = {}


def sport_of(key):
    if key not in _SPORTS:
        _SPORTS[key] = front.Sport(sports.BY_KEY[key])
    return _SPORTS[key]


# ------------------------------------------------------------ the slate
def week_of(sport, day):
    weeks = sport.doc.get('weeks') or []
    return next((w for w in weeks if w['start'] <= day <= w['end']), None) or next((w for w in weeks if w['start'] > day), None)


def weekly(sport):
    """A weekly preview (NFL, College Football unless the admin's
    PREVIEW_MODE says daily): one per week, every game in it."""
    return sport.weekly and sports.preview_weekly(sport.key)


def week_num(sport, day):
    """The ESPN week number ("Week 11" -> 11) of the week `day` falls in
    (else the next one), or None."""
    w = week_of(sport, day)
    m = re.search(r'(\d+)', (w or {}).get('label') or '')
    return int(m.group(1)) if m else None


def on_day(g, day):
    t = parse(g.get('start'))
    return bool(t) and t.astimezone(ET).date().isoformat() == day


def in_league(sport, g):
    """College: both teams in the league (Division I; College Football:
    FBS). A game against a school outside it is never the lead, the
    Matchup of the Day, a box, a game section or counted (it still shows on
    Matchups and Odds)."""
    teams = sport.doc.get('teams') or {}
    return sport.key not in sports.COLLEGE or (g['away'] in teams and g['home'] in teams)


def slate(sport, day):
    """(trends key, games, before): the day's games; football: the week's
    games from that day on (a weekly preview), or that day's (daily).
    College: games inside the league only (in_league)."""
    if sport.weekly:
        w = week_of(sport, day)
        if not w:
            return None, [], day
        games = [g for d, g in sport.all_games() if g.get('wk') == w['key'] and d >= day and in_league(sport, g)]
        if not weekly(sport):
            games = [g for g in games if on_day(g, day)]
        return w['key'], sorted(games, key=lambda g: g.get('start') or ''), w['start']
    return day, sorted((g for g in sport.games(day) if in_league(sport, g)), key=lambda g: (g.get('start') or '', g['away'])), day


def rate_of(t):
    """A trend's season record from hub.game_trends: "68% (58–27)" (league
    cards and team leans; older logs: "58–27", "... in 11 of 13")."""
    rec = t.get('rec') or ''
    m = re.search(r'\((\d+)\D+(\d+)\)', rec) if t['kind'] in ('league', 'matchup') else None
    if not m and t['kind'] == 'league':
        m = re.match(r'(\d+)\D+(\d+)$', rec)
    if m:
        w, l = int(m.group(1)), int(m.group(2))
        return {'w': w, 'l': l, 'n': w + l, 'pct': w / (w + l) if w + l else None}
    m = re.search(r' in (\d+) of (\d+)$', t.get('text') or '')
    if t['kind'] == 'matchup' and m:
        x, y = int(m.group(1)), int(m.group(2))
        return {'w': x, 'l': y - x, 'n': y, 'pct': x / y if y else None}
    return {'w': None, 'l': None, 'n': 0, 'pct': None}


_TRENDS = {}


def trends_on(sport, day):
    """{game id: [trend, ...]} for the slate: the Matchup of the Day's
    trends (hub.game_trends), each with its season rate. No 3-way."""
    if (sport.key, day) in _TRENDS:
        return _TRENDS[(sport.key, day)]
    key, games, before = slate(sport, day)
    cards = (((sport.trends.get('slates') or {}).get(key) or {}).get('cards')) or []
    seqs = {k: hub.team_seqs(sport.doc, before, k) for k in {x[0] for x in hub.market_keys(sport.doc)}}
    out = {}
    for g in games:
        items = []
        for (k, m, pick), ts in hub.game_trends(sport.doc, g, cards, seqs).items():
            if m == 'ml3':
                continue
            items += [dict(t, seg=k, mk=m, pick=pick, **rate_of(t)) for t in ts]
        out[str(g['id'])] = items
    _TRENDS[(sport.key, day)] = out
    return out


def strongest(items):
    rated = [t for t in items if t['pct'] is not None and t['n'] >= RATE_MIN]
    return max(rated, key=lambda t: (t['pct'], t['n'])) if rated else None


# ---------------------------------------------------- Matchup of the Day
def motd_of(key, day):
    """(sport key, game id) of the Matchup of the Day for that day: a
    sport's own (matchup_of_the_day_log.json); 'all': the site's, the
    sports' pick with the most agreeing trends (front.motd_pick's rule)."""
    log = read_json(hub.LOG_PATH, {}) or {}
    keys = [k for k in log if k in sports.BY_KEY] if key == ALL else [key]
    best = None
    for k in keys:
        sp = sport_of(k)
        sk = slate(sp, day)[0]
        e = (log.get(k) or {}).get(sk)
        if not e or (key == ALL and e.get('date') != day):
            continue
        score = (e.get('n') or 0, e.get('edge') or 0)
        if best is None or score > best[0]:
            best = (score, k, str(e['id']))
    return best[1:] if best else None


# ------------------------------------------------------------ the lead
def day_games(sport, day):
    """The all-sports preview's games for a sport: the ones that day
    (football's week slate holds the whole week)."""
    games = slate(sport, day)[1]
    if not sport.weekly:
        return games
    return [g for g in games if on_day(g, day)]


def candidates(key, day):
    """[(sport, game, trends)] for the preview's games."""
    keys = [k for k in covers(day)] if key == ALL else [key]
    out = []
    for k in keys:
        sp = sport_of(k)
        on = trends_on(sp, day)
        out += [(sp, g, on.get(str(g['id'])) or []) for g in (day_games(sp, day) if key == ALL else slate(sp, day)[1])]
    return out


def covers(day):
    """The sports the all-sports preview covers: on the site, with games that day."""
    d = date.fromisoformat(day)
    return [sp['key'] for sp in sports.shown(d) if day_games(sport_of(sp['key']), day)]


def pick_lead(cands, motd):
    """The game with the strongest season-rate trend among those with 2+
    trends, not the Matchup of the Day unless no other game has 2+."""
    ok = [c for c in cands if len(c[2]) >= MIN_TRENDS]
    other = [c for c in ok if motd is None or (c[0].key, str(c[1]['id'])) != tuple(motd)]
    pool = other or ok
    if not pool:
        return None

    def score(c):
        s = strongest(c[2])
        return ((s['pct'], s['n']) if s else (0, 0), len(c[2]))
    return max(pool, key=score)


def chip_text(sport, t):
    """The card's yellow chip from the lead trend: "SAC LOST 1H · 11 OF 13",
    "BACK ROAD FAVORITES · 1H ML · 58–27", "MIL UNDER 1Q · 10 STRAIGHT"."""
    if not t:
        return ''
    if t['kind'] == 'league':
        name, _, tag = t['text'].rpartition(' (')
        return f"{name} · {tag.rstrip(')')} · {t['rec']}".upper()
    text = t['text']
    for s in sport.segments:
        text = re.sub(rf"the {re.escape(s['label'].lower())}( spread| total)?", lambda m: s['tag'] + (m.group(1) or '').upper(), text)
    seg = '' if any(re.search(rf"\b{re.escape(s['tag'])}\b", text) for s in sport.segments) else ' ' + sport.segments[0]['tag']   # NHL's "Over 1.5" is the 1P's
    if t['kind'] == 'matchup':
        m = re.match(r'(\S+) has (?:gone )?(.*?)(?: in \d+ of \d+)?$', text)
        r = rate_of(t)
        if m and r['n']:
            return f"{m.group(1)} {m.group(2)}{seg} · {r['w']} of {r['n']}".upper()
    m = re.match(r'(.*) (\d+) straight$', text)
    return (f'{m.group(1)} · {m.group(2)} straight' if m else text).upper()


def lead_trend(items):
    return strongest(items) or next((t for t in items if t['kind'] == 'streak'), None) or (items[0] if items else None)


def find_game(key, day, lead):
    """(sport, game) from a `lead:` value: "nba:401910018" or a game id."""
    lead = str(lead or '').strip()
    if not lead:
        return None
    sk, _, gid = lead.rpartition(':')
    for sp, g, items in candidates(key, day):
        if str(g['id']) == gid and (not sk or sk == sp.key):
            return sp, g, items
    return None


def lead_of(key, day, override=None, now_utc=None):
    """{sport, id, chip, ...} for the preview's lead game. A draft's `lead:`
    wins; else the stored pick (content/preview_leads.json); else picked
    now and stored, so the dated page keeps it."""
    leads = read_json(LEADS, {}) or {}
    got = find_game(key, day, override) if override else None
    saved = (leads.get(day) or {}).get(key)
    if not got and saved:
        got = find_game(key, day, f"{saved['sport']}:{saved['id']}")
    if not got:
        got = pick_lead(candidates(key, day), motd_of(key, day))
    if not got:
        return None
    sp, g, items = got
    t = lead_trend(items)
    info = {'sport': sp.key, 'id': str(g['id']), 'away': g['away'], 'home': g['home'], 'start': g.get('start'),
            'chip': chip_text(sp, t), 'trend': t['text'] if t else ''}
    if not override and (leads.get(day) or {}).get(key) != info and day >= today_et(now_utc or datetime.now(timezone.utc)):
        leads.setdefault(day, {})[key] = info
        write_json(LEADS, {d: v for d, v in leads.items() if d >= (date.fromisoformat(day) - timedelta(days=60)).isoformat()})
    return info


# --------------------------------------------------------- the packet
def lines_of(sport, day, g):
    """{segment tag: {market: open / now (best) / book}} for the drafter."""
    og = sport.odds_game(day, g) if not sport.weekly else sport.odds_game(next((d for d, x in sport.all_games() if x is g), day), g)
    out = {}
    for s in sport.segments:
        k = s['key']
        o, b = ((og.get('open') or {}).get(k) or {}), ((og.get('best') or {}).get(k) or {})
        row = {}
        for side in ('away', 'home'):
            code = sport.code(g[side])
            ml = (b.get('ml') or {}).get(side)
            if isinstance(ml, (int, float)):
                row.setdefault('moneyline', {})[code] = {'open': (o.get('ml') or {}).get(side), 'now': ml,
                                                         'best_book': book_name(sport, front.book_of(sport, og, k, 'ml', side, ml))}
            a = (b.get('ats') or {}).get(side) or {}
            if a.get('line') is not None:
                row.setdefault('spread', {})[code] = {'open': ((o.get('ats') or {}).get(side) or {}).get('line'), 'now': a.get('line'),
                                                      'price': a.get('price'),
                                                      'best_book': book_name(sport, front.book_of(sport, og, k, 'ats', side, a.get('price'), a.get('line')))}
        t = b.get('total') or {}
        if t.get('line') is not None:
            row['total'] = {'open': (o.get('total') or {}).get('line'), 'now': t['line'], 'over': t.get('over'), 'under': t.get('under'),
                            'best_book_over': book_name(sport, front.book_of(sport, og, k, 'total', 'over', t.get('over'), t['line']))}
        if row:
            out[s['tag']] = row
    return out


def book_name(sport, b):
    return ((sport.sources.get(b) or {}).get('name') or b) if b else None


def packet_games(key, day, ids=None):
    """The games in a sport's packet (ids: only these): names, start, each
    trend's season rate (10+ games), the lines (open, now, best price and
    book), and which game is the Matchup of the Day and which the lead game."""
    sp = sport_of(key)
    on = trends_on(sp, day)
    motd = motd_of(key, day)
    lead = lead_of(key, day)
    games = [g for g in slate(sp, day)[1] if ids is None or str(g['id']) in ids]
    if len(games) > PACKET_MAX:   # the busiest games, in start order
        keep = sorted(games, key=lambda g: -len(on.get(str(g['id'])) or []))[:PACKET_MAX]
        if lead:
            keep = [g for g in keep if str(g['id']) != lead['id']][:PACKET_MAX - 1] + [g for g in games if str(g['id']) == lead['id']]
        games = [g for g in games if g in keep]
    out = []
    for g in games:
        items = on.get(str(g['id'])) or []
        t = parse(g.get('start'))
        when = t.astimezone(ET).strftime('%A %-I:%M %p ET' if sp.weekly else '%-I:%M %p ET') if t else None
        extra = {'window': kickoff_window(t)} if weekly(sp) and t else {}
        out.append({
            'id': str(g['id']), 'matchup': f"{sp.full_name(g['away'])} at {sp.full_name(g['home'])}",
            'away': {'code': sp.code(g['away']), 'name': sp.full_name(g['away'])},
            'home': {'code': sp.code(g['home']), 'name': sp.full_name(g['home'])},
            'start': when,
            'matchup_of_the_day': bool(motd and motd[1] == str(g['id'])),
            'lead_game': bool(lead and lead['id'] == str(g['id'])),
            'trends': [{'trend': x['text'], 'season_record': f"{x['w']}–{x['l']}", 'season_pct': f"{round(x['pct'] * 100)}%"}
                       for x in items if x['pct'] is not None and x['n'] >= RATE_MIN],
            'streaks': [x['text'] for x in items if x['kind'] == 'streak'],
            'lines': lines_of(sp, day, g), **extra})
    return out


def kickoff_window(t):
    """A weekly preview's group for a game: Thursday, Saturday, Sunday 1:00
    PM (noon to 3:59), Sunday 4:25 PM (4:00 to 6:59), Sunday Night, Monday
    Night; another day or time: the day (and the time on a Sunday morning)."""
    t = t.astimezone(ET)
    day = t.strftime('%A')
    if day == 'Sunday':
        if t.hour >= 19:
            return 'Sunday Night'
        if t.hour >= 16:
            return 'Sunday 4:25 PM'
        if t.hour >= 12:
            return 'Sunday 1:00 PM'
        return 'Sunday ' + t.strftime('%-I:%M %p')
    if day == 'Monday' and t.hour >= 19:
        return 'Monday Night'
    return day


def parse(iso):
    return front.parse(iso) if iso else None


# ------------------------------------------- the morning packet: more data
SPLIT_WORDS = {'season': 'this season', 'home': 'at home', 'road': 'on the road', 'favorite': 'as favorites', 'underdog': 'as underdogs'}
TIERS = {'A': 0, 'B': 1, 'C': 2}
START_WORD = {'nhl': 'puck drop', 'mlb': 'pitch', 'nfl': 'kickoff', 'ncaaf': 'kickoff'}   # else "tip"


def team_bets(sport):
    """[(segment, market, kind, bet, yes words, no words)] a team's rates
    are read in: won / covered / Over / both scored / a run. No 3-way."""
    out = []
    for s in sport.segments:
        k, tag = s['key'], s['tag']
        for m, kind, bet in tr.bets_for(sport.sp, k):
            if m == 'ml':
                out.append((k, m, kind, None, f'won the {tag}', f'lost the {tag}'))
            elif m == 'ats':
                out.append((k, m, kind, None, f'covered the {tag} spread', f'failed to cover the {tag} spread'))
            elif m == 'total' and bet == 'over':
                out.append((k, m, kind, bet, f'went Over the {tag} total', f'went Under the {tag} total'))
            elif m == 'btts' and bet == 'yes':
                out.append((k, m, kind, bet, f'had both teams score in the {tag}', f'had a team held scoreless in the {tag}'))
            elif m == 'rfi' and bet == 'yes':
                out.append((k, m, kind, bet, 'had a run in the 1st inning', 'had no run in the 1st inning'))
    return out


_PREP = {}


def prepared(sport):
    if sport.key not in _PREP:
        _PREP[sport.key] = tr.prepare(sport.sp, sport.doc)
    return _PREP[sport.key]


def split_rec(w, l):
    n = w + l
    return {'record': f'{w}–{l}', 'pct': f'{round(100 * w / n)}%', 'games': n, '_w': w, '_l': l} if n >= RATE_MIN else None


def team_rates(sport, day, slugs):
    """{slug: [rate]}: every segment market's season rate for these teams,
    overall and split home / road and favorite / underdog, each with its
    game count. Only splits of 10+ games."""
    tally = {}
    for G in prepared(sport):
        if G['date'] >= day:
            break
        g = G['g']
        for side in ('away', 'home'):
            slug = g[side]
            if slug not in slugs:
                continue
            for k, m, kind, bet, _, _ in team_bets(sport):
                r = tr.side_result(g, k, m, side) if kind == 'side' else tr.game_result(g, k, m, bet)
                if not r or r[0] not in ('W', 'L'):
                    continue
                fav = tr.favorite((g.get('odds') or {}).get(k))
                splits = ['season', 'home' if side == 'home' else 'road'] + ([('favorite' if fav == side else 'underdog')] if fav else [])
                for sp_ in splits:
                    t = tally.setdefault(slug, {}).setdefault((k, m), {}).setdefault(sp_, [0, 0])
                    t[0 if r[0] == 'W' else 1] += 1
    out = {}
    for slug in slugs:
        rows = []
        for k, m, kind, bet, yes, no in team_bets(sport):
            got = {sp_: split_rec(*wl) for sp_, wl in ((tally.get(slug) or {}).get((k, m)) or {}).items()}
            got = {sp_: v for sp_, v in got.items() if v}
            if got:
                rows.append({'seg': k, 'mk': m, 'yes': yes, 'no': no, 'splits': got})
        out[slug] = rows
    return out


def public(rows):
    """The packet's view of team_rates: no private keys."""
    return [{'rate': r['yes'], **{SPLIT_WORDS[k]: {x: v[x] for x in ('record', 'pct', 'games')} for k, v in r['splits'].items()}} for r in rows]


def league_cards(sport, day, games):
    """The Trends page's league cards for the slate (10+ games) with the
    games tonight that fit each."""
    key = slate(sport, day)[0]
    ids = {str(g['id']): g for g in games}
    out = []
    for c in (((sport.trends.get('slates') or {}).get(key) or {}).get('cards')) or []:
        n = c['w'] + c['l']
        fit = [ids[str(x['id'])] for x in c.get('games') or [] if str(x['id']) in ids]
        if n >= RATE_MIN and fit and c.get('mk') != 'ml3':
            out.append({'card': c, 'n': n, 'fit': fit})
    return out


def edge_plays(sport, day, games):
    """Today's Edge plays for these games (picks_log.json), best first."""
    import picks
    ids = {str(g['id']): g for g in games}
    plays = [p for p in ((read_json(picks.LOG_PATH, {}) or {}).get(day) or {}).get('plays') or []
             if p.get('sport') == sport.key and str(p.get('game', '')).split('|')[-1] in ids]
    plays.sort(key=lambda p: (TIERS.get(p.get('tier'), 9), -(p.get('edge') or 0)))
    return [(p, ids[str(p['game']).split('|')[-1]]) for p in plays]


def best_bet(sport, day, g, k, m, side):
    """(line, price, book) at the best price now (the Odds page)."""
    og = sport.odds_game(day, g)
    b = ((og.get('best') or {}).get(k) or {}).get(m) or {}
    if m == 'ats':
        x = b.get(side) or {}
        line, price = x.get('line'), x.get('price')
    elif m == 'total':
        line, price = b.get('line'), b.get(side)
    else:
        line, price = None, b.get(side)
    book = front.book_of(sport, og, k, m, side, price, line if m in ('ats', 'total') else None) if isinstance(price, (int, float)) else None
    return line, price, book_name(sport, book)


def fmt_line(x):
    return f'{x:+g}' if isinstance(x, (int, float)) else ''


def fmt_price(x):
    return f'{x:+d}' if isinstance(x, int) else (f'{x:+g}' if isinstance(x, float) else '')


def play_info(sport, day, p, g):
    """An Edge play as the box and packet show it: the bet, line, best price and book."""
    k, m, side = p['seg'], p['market'], p['side']
    tag = next((s['tag'] for s in sport.segments if s['key'] == k), k.upper())
    line, price, book = best_bet(sport, day, g, k, m, side)
    line = line if line is not None else p.get('line')
    price = price if price is not None else p.get('price')
    if m in ('ml', 'ats'):
        code = sport.code(g[side])
        bet = f'{code} {tag} ML' if m == 'ml' else f'{code} {tag} {fmt_line(line)}'
        big = fmt_price(price) if m == 'ml' else fmt_line(line)
    elif m == 'total':
        bet = f'{tag} {side.title()} {line:g}' if isinstance(line, (int, float)) else f'{tag} {side.title()}'
        big = f"{'O' if side == 'over' else 'U'} {line:g}" if isinstance(line, (int, float)) else side.title()
    elif m == 'rfi':
        bet = big = 'YRFI' if side == 'yes' else 'NRFI'
    else:
        bet = f'{tag} BTTS {side.title()}'
        big = f'BTTS {side.title()}'
    best = f'best {fmt_price(price)}' + (f' at {book}' if book else '') if isinstance(price, (int, float)) else ''
    return {'game': f"{sport.full_name(g['away'])} at {sport.full_name(g['home'])}", 'bet': bet, 'line': line, 'best_price': fmt_price(price) or None,
            'book': book, 'tier': p.get('tier'), 'rates_behind_it': [x for x in (angle_rate(a) for a in p.get('angles') or []) if x],
            '_big': big, '_small': ' · '.join(x for x in (bet, best) if x), '_score': p.get('est') or 0}


def angle_rate(a):
    """An Edge angle ["Boston 1P ML on the road", "5-2-2"] (W-L-push) as
    "Boston 1P ML, season: 62% (10–6)", percent first; 10+ games only."""
    m = re.match(r'(\d+)-(\d+)', str(a[1] if len(a) > 1 else ''))
    if not m:
        return None
    w, l = int(m.group(1)), int(m.group(2))
    if w + l < RATE_MIN:
        return None
    return f"{a[0]}: {round(100 * w / (w + l)) if w + l else 0}% ({w}–{l})"


# ----------------------------------------------------- the three boxes
def stat_pick(sport, day, games):
    """Stat of the Night: tonight's strongest team rate (10+ games), in the
    split that fits tonight (home / road, favorite / underdog) or the season."""
    slugs = {g[s] for g in games for s in ('away', 'home')}
    rates = team_rates(sport, day, slugs)
    best = None
    for g in games:
        for side in ('away', 'home'):
            for r in rates.get(g[side]) or []:
                fav = tr.favorite((g.get('odds') or {}).get(r['seg']))
                fits = ['season', 'home' if side == 'home' else 'road'] + ([('favorite' if fav == side else 'underdog')] if fav else [])
                for sp_ in fits:
                    v = r['splits'].get(sp_)
                    if not v:
                        continue
                    w, l = v['_w'], v['_l']
                    hi = w >= l
                    score = (max(w, l) / (w + l), w + l)
                    if best is None or score > best[0]:
                        best = (score, g, side, r, sp_, (w, l) if hi else (l, w), r['yes'] if hi else r['no'])
    if not best:
        return None
    (pct, n), g, side, r, sp_, (w, l), words = best
    code, name = sport.code(g[side]), sport.full_name(g[side])
    tail = '' if sp_ == 'season' else f' {SPLIT_WORDS[sp_]}'
    return {'sport': sport.key, 'number': f'{round(pct * 100)}%', 'line': f"{code} {words.replace('went ', '')} · {w}–{l}{tail}",
            'text': f'The {name} {words} in {w} of {n} games{tail or " this season"}.', '_score': pct}


def trend_pick(sport, day, games):
    """League Trend: the league card with the best record that fits tonight."""
    cards = league_cards(sport, day, games)
    if not cards:
        return None
    x = max(cards, key=lambda x: (x['card']['rate'], x['n']))
    c = x['card']
    names = [f"{sport.full_name(g['away'])} at {sport.full_name(g['home'])}" for g in x['fit']]
    tonight = names[0] if len(names) == 1 else f'{names[0]} and {len(names) - 1} more game{"s" if len(names) > 2 else ""}'
    return {'sport': sport.key, 'number': f"{round(c['rate'] * 100)}%", 'line': f"{c['title']} · {c['tag']} · {c['w']}–{c['l']}",
            'text': f"{c['title']} {c['w']}–{c['l']} this season; tonight it fits {tonight}.", 'id': c['id'], '_score': c['rate']}


SEG_SPELLED = {'1p': 'first period', '1q': 'first quarter', '1h': 'first half', '1i': 'first inning', 'f5': 'first five innings'}
EDGE_MIN = 0.40        # an Edge play's side must win / cover 40%+ of its season
MARKET_WORDS = {'ml': ' ML', 'ats': ' ATS', 'total': {'over': 'overs', 'under': 'unders'}, 'btts': 'BTTS', 'rfi': 'RFI'}


def season_rate(rates, slug, k, m):
    """(w, l) of a team's season rate in one segment market (10+ games), or None."""
    r = next((r for r in rates.get(slug) or [] if r['seg'] == k and r['mk'] == m), None)
    v = r and r['splits'].get('season')
    return (v['_w'], v['_l']) if v else None


def edge_why(sport, day, p, g, rates=None):
    """The reason an Edge play qualifies, from rates in its own market only
    ("Islanders have won the first period 62% (10–6); the Jets have won it
    23% (3–10)."), or None when it doesn't: no same-market rate of 10+
    games, or the side wins / covers under 40% of its season."""
    k, m, side = p['seg'], p['market'], p['side']
    if m in ('ml', 'ats'):
        rates = rates if rates is not None else team_rates(sport, day, {g['away'], g['home']})
        other = 'home' if side == 'away' else 'away'
        mine, theirs = season_rate(rates, g[side], k, m), season_rate(rates, g[other], k, m)
        if mine and mine[0] / sum(mine) < EDGE_MIN:
            return None
        if mine:
            verb, it = ('won', 'won it') if m == 'ml' else ('covered', 'covered it')
            what = SEG_SPELLED.get(k, k) + ('' if m == 'ml' else ' spread')
            have = 'has' if sport.key in sports.COLLEGE else 'have'

            def nick(slug):
                t = sport.team(slug)
                return t.get('short') or sport.full_name(slug)
            why = f"{'' if sport.key in sports.COLLEGE else 'The '}{nick(g[side])} {have} {verb} the {what} {round(100 * mine[0] / sum(mine))}% ({mine[0]}–{mine[1]})"
            if theirs:
                why += f"; {'' if sport.key in sports.COLLEGE else 'the '}{nick(g[other])} {have} {it} {round(100 * theirs[0] / sum(theirs))}% ({theirs[0]}–{theirs[1]})"
            return why + '.'
    word = MARKET_WORDS.get(m)
    word = word.get(side, '') if isinstance(word, dict) else word
    same = [x for x in (angle_rate(a) for a in p.get('angles') or [] if word and word in a[0]) if x]
    return ('; '.join(same[:2]) + '.') if same else None


def edge_pick(sport, day, games):
    """Edge Play of the Night: today's top Edge play backed by rates in its
    own market (edge_why)."""
    rates = team_rates(sport, day, {g[s] for g in games for s in ('away', 'home')})
    for p, g in edge_plays(sport, day, games):
        why = edge_why(sport, day, p, g, rates)
        if not why:
            continue
        info = play_info(sport, day, p, g)
        return {'sport': sport.key, 'number': info['bet'], 'bet': info['bet'], 'price': info['best_price'], 'book': info['book'], 'line': info['_small'],
                'text': why[:1].upper() + why[1:], '_score': info['_score']}
    return None


BOX_KEYS = (('stat_of_night', stat_pick), ('league_trend', trend_pick), ('edge_play', edge_pick))


def box_games(sport, key, day):
    return day_games(sport, day) if key == ALL else slate(sport, day)[1]


def boxes(key, day, keys=None):
    """{stat_of_night, league_trend, edge_play}: each {sport, number, line,
    text}. A sport page: all three from it. All sports (keys: the sports
    it covers): three different sports when 3+ play, two when two do
    (split 2 and 1), else one."""
    keys = (keys or covers(day)) if key == ALL else [key]
    lead = lead_of(key, day) or {}

    def games_for(k, b):
        """Stat of the Night skips the lead game (the headline's), unless it's the only one."""
        games = box_games(sport_of(k), key, day)
        rest = [g for g in games if not (b == 'stat_of_night' and lead.get('sport') == k and str(g['id']) == lead.get('id'))]
        return rest or games
    cand = {k: {b: f(sport_of(k), day, games_for(k, b)) for b, f in BOX_KEYS} for k in keys}
    import itertools
    best = None
    opts = [[k for k in keys if cand[k][b]] or [None] for b, _ in BOX_KEYS]
    for combo in itertools.product(*opts):
        used = {k for k in combo if k}
        score = (len(used), sum(cand[k][b]['_score'] for k, (b, _) in zip(combo, BOX_KEYS) if k))
        if best is None or score > best[0]:
            best = (score, combo)
    out = {}
    for k, (b, _) in zip(best[1] if best else (), BOX_KEYS):
        if k:
            out[b] = {x: v for x, v in cand[k][b].items() if not x.startswith('_')}
    return out


def more_data(key, day, ids=None):
    """The packet's added data for one sport (ids: its packet's games): team
    rates, league trends and Edge plays (10+ games for every rate)."""
    sport = sport_of(key)
    games = [g for g in slate(sport, day)[1] if ids is None or str(g['id']) in ids]
    slugs = {g[s] for g in games for s in ('away', 'home')}
    rates = team_rates(sport, day, slugs)
    return {
        'teams': {sport.code(s): {'name': sport.full_name(s), 'rates': public(rates.get(s) or [])} for s in sorted(slugs)},
        'league_trends': [{'trend': x['card']['title'], 'market': x['card']['tag'], 'record': f"{x['card']['w']}–{x['card']['l']}",
                           'pct': f"{round(x['card']['rate'] * 100)}%", 'games': x['n'],
                           'fits_tonight': [f"{sport.full_name(g['away'])} at {sport.full_name(g['home'])}" for g in x['fit']]}
                          for x in league_cards(sport, day, games)],
        'edge_plays': [dict({k: v for k, v in play_info(sport, day, p, g).items() if not k.startswith('_') and k != 'rates_behind_it'}, why=why)
                       for p, g in edge_plays(sport, day, games) for why in [edge_why(sport, day, p, g, rates)] if why],
    }


# ------------------------------------------------------------ the pieces
def visible(now_utc):
    """Published previews to show: today's only from 11 AM ET."""
    now = now_utc.astimezone(ET)
    today = now.date().isoformat()
    return [p for p in daily.load() if p['kind'] == 'preview' and p['date'] <= today
            and not (p['date'] == today and now.hour < SHOW_HOUR)]


def drafts(day):
    """Today's drafts ({key: piece}), for the admin's image cards."""
    out = {}
    folder = os.path.join(ROOT, 'content', 'drafts')
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        m = re.fullmatch(r'([a-z]+)-preview-(\d{4}-\d{2}-\d{2})\.md', name)
        if not m or m.group(2) != day:
            continue
        with open(os.path.join(folder, name), encoding='utf-8') as f:
            meta, body = daily.parse(f.read())
        out[m.group(1)] = {'sport': m.group(1), 'date': day, 'lead': meta.get('lead'), 'body': body}
    return out


def split(body):
    """(headline, dek, body Markdown). A "!!" line (the old callout) is dropped."""
    lines = body.strip().split('\n')
    head = dek = None
    rest = []
    for ln in lines:
        s = ln.strip()
        if head is None and s.startswith('# '):
            head = s[2:].strip()
        elif dek is None and s.startswith('> '):
            dek = s[2:].strip()
        elif s.startswith('!!'):
            continue
        else:
            rest.append(ln)
    md = '\n'.join(rest).strip()
    if head is None:   # older drafts: the bold first line, then a short first paragraph
        m = re.match(r'\*\*(.+?)\*\*\s*', md)
        if m:
            head, md = m.group(1).strip(), md[m.end():].strip()
        if dek is None:
            first, _, more = md.partition('\n\n')
            if first and len(daily.plain(first)) <= 220 and more:
                dek, md = daily.plain(first), more.strip()
    return head or '', dek or '', md


def page_dir(key, day=None):
    """/preview/, /nfl/preview/; a day's page: /preview/2026-11-18/; a
    weekly piece's (its `week:`, a number): /nfl/preview/week-11/."""
    base = INDEX if key == ALL else f"{sports.BY_KEY[key]['slug']}/{INDEX}"
    if isinstance(day, int):
        return f'{base}/week-{day}/'
    return f'{base}/{day}/' if day else f'{base}/'


def piece_week(p):
    """A weekly piece's week number (its `week:`, else from its date), or
    None for a daily piece."""
    key = p['sport']
    if key == ALL or not (p.get('week') or (sports.BY_KEY.get(key, {}).get('schedule') == 'week' and sports.preview_weekly(key))):
        return None
    m = re.search(r'(\d+)', str(p.get('week') or ''))
    return int(m.group(1)) if m else week_num(sport_of(key), p['date'])


def piece_dir(p):
    w = piece_week(p)
    return page_dir(p['sport'], w if w else p['date'])


def card_path(key, day):
    return f'{CARD_DIR}/{day}/{key}.png'


def has_card(key, day):
    return os.path.exists(os.path.join(ROOT, card_path(key, day)))


def label(key, day, week=None):
    if key == ALL:
        return f'Preview &middot; {esc(long_day(day))}'
    if week:
        return f"{esc(sports.seo_name(key))} Week {week} {esc(sports.seg_words(key))} Betting Preview"
    return f"{esc(sports.seo_name(key))} {esc(sports.seg_words(key))} Betting Preview &middot; {esc(short_day(day))}"


TITLE_WORDS = 10   # a headline longer than this isn't used in the tab title


def title(key, headline, day=None, week=None):
    """The browser tab: "[Sport] [segment words] Betting Preview: [headline]
    | RTYB", the headline only when it's 10 words or fewer; else (day given)
    "... Betting Preview · Nov 18 | RTYB". Weekly: "NFL Week 11 First
    Quarter & First Half Betting Preview", and the headline when it fits."""
    lead = 'First Period, Quarter & Half Betting Preview' if key == ALL else f'{sports.seo_name(key)} {sports.seg_words(key)} Betting Preview'
    if week:
        lead = f'{sports.seo_name(key)} Week {week} {sports.seg_words(key)} Betting Preview'
        return f'{lead}: {headline} | RTYB' if headline and len(headline.split()) <= TITLE_WORDS else f'{lead} | RTYB'
    if day and (not headline or len(headline.split()) > TITLE_WORDS):
        d = date.fromisoformat(day)
        return f"{lead} · {d.strftime('%b')} {d.day} | RTYB"
    return f'{lead}: {headline} | RTYB'


def published_txt(p):
    """"Published 8:59 PM ET · " from the piece's real publish time."""
    t = parse(p.get('published'))
    return f"Published {t.astimezone(ET).strftime('%-I:%M %p ET')} &middot; " if t else ''


def names_list(names):
    return names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' & ' + names[-1] if names else ''


# ------------------------------------------------------------ the article
def link_teams(body_html, keys, root, day=None):
    """Each team on the day's slate, its first time in the text, to its
    page: the full name, or the short one when it isn't the start of a
    longer name ("Houston" in "Houston Rockets" is not the Cougars)."""
    names = []
    for k in keys:
        sp = sport_of(k)
        playing = {g[side] for g in slate(sp, day)[1] for side in ('away', 'home')} if day else (sp.doc.get('teams') or {})
        for slug in playing:
            href = sp.team_href(slug, root)
            if href:
                names.append((sp.full_name(slug), href))
                t = sp.team(slug)
                if t.get('name') and t['name'] != sp.full_name(slug):
                    names.append((t['name'], href))
    names.sort(key=lambda x: -len(x[0]))
    done = set()
    parts = re.split(r'(<[^>]+>)', body_html)
    inside = 0
    for i, part in enumerate(parts):
        if part.startswith('<'):
            if re.match(r'<(a|h[1-6])\b', part):
                inside += 1
            elif re.match(r'</(a|h[1-6])>', part):
                inside = max(0, inside - 1)
            continue
        if inside:
            continue
        for name, href in names:
            if href in done or name not in part:
                continue
            new = re.sub(rf'(?<![\w>]){re.escape(name)}(?![\w<]| [A-Z][a-z])', lambda m: f'<a class="pv-team" href="{esc(href)}">{esc(name)}</a>', part, count=1)
            if new != part:
                part = new
                done.add(href)
            parts[i] = part
        parts[i] = part
    return ''.join(parts)


def sport_by_heading(text):
    t = text.lower()
    for sp in sports.SPORTS:
        for n in {sp['label'], sp['menu_label'], sports.seo_name(sp)}:
            if t.startswith(n.lower()):
                return sp
    return None


NUM_WORDS = {2: 'both', 3: 'all three', 4: 'all four', 5: 'all five', 6: 'all six', 7: 'all seven'}


def names_of(sport, slug):
    t = sport.team(slug)
    return {x for x in (sport.full_name(slug), t.get('short'), t.get('name')) if x}


def game_in(sport, text, games):
    """The game whose two teams the text names ("Bucks at Heat")."""
    for g in games:
        if all(any(n in text for n in names_of(sport, g[s])) for s in ('away', 'home')):
            return g
    return None


def venue_line(sport, g):
    """'Rocket Arena, Cleveland, OH · TV: ESPN' (no TV: the venue only)."""
    ven = g.get('ven')
    if ven and ',' not in ven:   # NHL: the arena; its city from the home team's name
        t = sport.team(g['home'])
        city = (t.get('name') or '')[:-len(t.get('short') or '')].strip() if t.get('short') and (t.get('name') or '').endswith(t['short']) else ''
        ven = f'{ven}, {city}' if city else ven
    tv = ', '.join(g.get('tv') or [])
    return ' &middot; '.join(x for x in (esc(ven) if ven else '', f'TV: {esc(tv)}' if tv else '') if x)


def mentioned(text, titles):
    low = text.lower()
    return {t for t in titles if t.lower() in low}


def more_trends(key, day, body_text, box_id, keys):
    """League trends that fit the night's games and aren't in the article."""
    n = 0
    for k in keys:
        sport = sport_of(k)
        for x in league_cards(sport, day, box_games(sport, key, day)):
            c = x['card']
            if c['id'] != box_id and c['title'].lower() not in body_text.lower():
                n += 1
    return n


def matchup_heads(body_html, key, day, root):
    """A sport page: "The Matchups" before the first game; each game's
    subhead gets both logos and, under it, the venue and TV."""
    sport = sport_of(key)
    games = slate(sport, day)[1]
    href = f"{root}{sport.matchups}?date={day}"
    motd = motd_of(key, day)

    def head(m):
        text = m.group(1)
        g = game_in(sport, re.sub(r'<[^>]+>', '', html.unescape(text)), games)
        if not g:
            return f'<h3><a href="{esc(href)}">{text}</a></h3>'
        logos = sport.badge(g['away'], 22, root) + sport.badge(g['home'], 22, root)
        line = venue_line(sport, g)
        to = f"{root}{sport.sp['slug']}/#motd" if motd and motd[1] == str(g['id']) else href   # the Matchup of the Day card
        return (f'<h3 class="pv-gh"><a href="{esc(to)}"><span class="pv-logos">{logos}</span><span>{text}</span></a></h3>'
                + (f'<p class="pv-ven">{line}</p>' if line else ''))
    body_html, n = re.subn(r'<h3>(.*?)</h3>', head, body_html)
    body_html = re.sub(r'<h2>(.*?)</h2>', r'<h2 class="pv-win">\1</h2>', body_html)   # a weekly piece's kickoff windows
    if n:
        body_html = re.sub(r'(<h2 class="pv-win"|<h3 )', '<h2 class="pv-mh">The Matchups</h2>\\1', body_html, count=1)
    return body_html


def sport_sections(body_html, day, root, have):
    """All sports: each "## NBA" gets its icon and a line ("12 games · first
    tip 7:00 PM ET · 6 with trends"), then after its paragraphs "Also with
    trends:" (its other games with 2+ trends) and "Read the full preview"."""
    parts = re.split(r'(?=<h2>)', body_html)
    out = []
    for part in parts:
        m = re.match(r'<h2>(.*?)</h2>', part)
        sp = sport_by_heading(re.sub(r'<[^>]+>', '', m.group(1))) if m else None
        if not sp:
            out.append(part)
            continue
        sport = sport_of(sp['key'])
        games = day_games(sport, day)
        on = trends_on(sport, day)
        first = min((g['start'] for g in games if g.get('start')), default=None)
        withs = sum(1 for g in games if on.get(str(g['id'])))
        meta = ' &middot; '.join(x for x in (f'{len(games)} game{"s" if len(games) != 1 else ""}',
                                              f"first {START_WORD.get(sp['key'], 'tip')} {esc(front.time_et(first))}" if first else '',
                                              f'{withs} with trends') if x)
        rest = part[m.end():]
        text = html.unescape(re.sub(r'<[^>]+>', '', rest))
        also = [g for g in sorted(games, key=lambda g: g.get('start') or '')
                if len(on.get(str(g['id'])) or []) >= MIN_TRENDS and not any(n in text for s in ('away', 'home') for n in names_of(sport, g[s]))][:6]
        href = f"{root}{sport.matchups}?date={day}"
        also_html = (f'<p class="pv-also">Also with trends: ' + ' &middot; '.join(
            f'<a href="{esc(href)}">{sport.name_html(g["away"])} at {sport.name_html(g["home"])}</a>'
            for g in also) + '</p>') if also else ''
        target = page_dir(sp['key'], day) if (sp['key'], day) in have else page_dir(sp['key'])
        read = f"Read the full {esc(sports.seo_name(sp))} preview"
        if weekly(sport):   # a weekly sport: that day's games here, the week in its own preview
            wk = week_num(sport, day)
            target, read = page_dir(sp['key'], wk) if wk else page_dir(sp['key']), f"Read the {esc(sports.seo_name(sp))} Week {wk} Preview"
        out.append(f'<h2 class="pv-sh">{icons.sport_icon(sp)}<span>{esc(sports.seo_name(sp))}</span></h2><p class="pv-smeta">{meta}</p>'
                   f'{rest}{also_html}<p class="pv-more"><a href="{root}{target}">{read} &rarr;</a></p>')
    return ''.join(out)


BOX_LABELS = (('stat_of_night', 'Stat of the Night', 'stat'), ('league_trend', 'League Trend', 'trend'), ('edge_play', 'Edge Play of the Night', 'edge'))


def edge_head(b, root):
    """Edge Play: the bet big ("BOS 1P ML"), then "Best -105 at [book logo]".
    Earlier front matter ("BOS 1P ML · best -105 at TheScore US") reads the same."""
    bet, price, book = b.get('bet'), b.get('price'), b.get('book')
    if not bet:
        m = re.match(r'(.*?) · best (\S+)(?: at (.+))?$', b.get('line') or '')
        bet, price, book = (m.group(1), m.group(2), m.group(3)) if m else (b.get('number'), None, None)
    if not price:
        return esc(bet or ''), ''
    sport = sport_of(b['sport'])
    sid = next((k for k, x in (sport.sources or {}).items() if (x or {}).get('name') == book), None)
    logo = front.book_html(sport, sid, root) if sid else esc(book or '')
    return esc(bet), f'Best {esc(price)}' + (f' at <span class="pv-book">{logo}</span>' if logo else '')


def boxes_html(p, root):
    """The three boxes (the draft's front matter): the sport's icon and the
    label, the big number, the record or bet line, the sentence. A box with
    "show": false (the admin's Show switch) is left out."""
    out = ''
    for key, words, cls in BOX_LABELS:
        b = (p.get('boxes') or {}).get(key)
        if not isinstance(b, dict) or b.get('sport') not in sports.BY_KEY or b.get('show') is False:   # admin's Show switch off
            continue
        text = link_teams(f'<p class="pv-box-text">{esc(b.get("text") or "")}</p>', [b['sport']], root, p['date'])
        num, small = esc(b.get('number') or ''), esc(b.get('line') or '')
        if key == 'edge_play':
            num, small = edge_head(b, root)
        out += (f'<div class="pv-box pv-box-{cls}"><p class="pv-box-h">{icons.sport_icon(b["sport"])}<span>{words}</span></p>'
                f'<p class="pv-box-num">{num}</p><p class="pv-box-line">{small}</p>{text}</div>')
    return f'<div class="pv-boxes">{out}</div>' if out else ''


def more_line(key, day, root, body_html, box_id, keys):
    n = more_trends(key, day, html.unescape(re.sub(r'<[^>]+>', '', body_html)), box_id, keys)
    if not n:
        return ''
    when = "this week&rsquo;s" if key != ALL and sport_of(key).weekly else "tonight&rsquo;s"
    if key == ALL:
        k = len(keys)
        across = f' across {NUM_WORDS[k]} sports' if k in NUM_WORDS else ''
        return (f'<p class="pv-mt">{n} more league trend{"s" if n != 1 else ""} fit{"s" if n == 1 else ""} {when} games{across}. '
                f'<a class="pv-go" href="{root}trends/">All trends &rarr;</a></p>')
    sp = sports.BY_KEY[key]
    name = esc(sports.seo_name(sp))
    return (f'<p class="pv-mt">{n} more {name} league trend{"s" if n != 1 else ""} fit{"s" if n == 1 else ""} {when} games. '
            f'<a class="pv-go" href="{root}{sports.section_path(sp, "trends").lstrip("/")}">All {name} trends &rarr;</a></p>')


AD_AFTER_SECTION = 3   # the in-article slot: after this many game sections


def ad_slot(name):
    """An empty, invisible ad slot (Site settings ADS_ON); nothing while it's off."""
    return f'<div class="ad-slot" data-ad="{name}" aria-hidden="true"></div>' if sports.ADS_ON else ''


GAME_HEAD = r'(?:<h2 class="pv-win">[^<]*</h2>\s*)?<h3 class="pv-gh"'   # a weekly game keeps its window line


def place_ad(body_html, before):
    """The in-article slot after the 3rd game section (before the 4th's
    heading; 3 sections: at the end). `before` is a regex for a section's
    heading."""
    slot = ad_slot('article')
    if not slot:
        return body_html
    at = [m.start() for m in re.finditer(before, body_html)]
    if len(at) < AD_AFTER_SECTION:
        return body_html
    i = at[AD_AFTER_SECTION] if len(at) > AD_AFTER_SECTION else len(body_html)
    return body_html[:i] + slot + body_html[i:]


def place_boxes(body_html, boxes, before):
    """The boxes after the intro: before the first `before` tag, else after
    the first paragraph."""
    if not boxes:
        return body_html
    i = body_html.find(before)
    if i < 0:
        j = body_html.find('</p>')
        i = j + 4 if j >= 0 else len(body_html)
    return body_html[:i] + boxes + body_html[i:]


def tonight(key, day, root):
    """The right column's games: all-sports, each sport's count and first
    start; a sport, each game and its time."""
    if key == ALL:
        rows = ''
        for k in covers(day):
            sp = sport_of(k)
            games = day_games(sp, day)
            first = min((g.get('start') for g in games if g.get('start')), default=None)
            when = front.time_et(first) if first else ''
            rows += (f'<a class="pv-trow" href="{root}{sp.matchups}?date={day}"><span class="pv-tsp">{icons.sport_icon(sp.sp)}{esc(sp.label)}</span>'
                     f'<span class="pv-tmeta">{len(games)} game{"s" if len(games) != 1 else ""} &middot; {esc(when)}</span></a>')
        return f'<section class="pv-side-card"><h2 class="pv-side-h">Tonight</h2>{rows}</section>' if rows else ''
    sp = sport_of(key)
    rows = ''
    for g in slate(sp, day)[1]:
        t = parse(g.get('start'))
        when = (t.astimezone(ET).strftime('%a %-I:%M %p' if sp.weekly else '%-I:%M %p ET') if t else 'TBD')
        rows += (f'<a class="pv-trow" href="{root}{sp.matchups}?date={day}"><span>{esc(sp.code(g["away"]))} @ {esc(sp.code(g["home"]))}</span>'
                 f'<span class="pv-tmeta">{esc(when)}</span></a>')
    return f'<section class="pv-side-card"><h2 class="pv-side-h">Tonight&rsquo;s games</h2>{rows}</section>' if rows else ''


def quiet_line(key, day):
    """Sport: the games with no trends; all-sports: the sports with no games."""
    if key == ALL:
        none = [sp['label'] for sp in sports.shown(date.fromisoformat(day)) if sp['key'] not in covers(day)]
        return f'<p class="pv-quiet">No games today: {esc(", ".join(none))}.</p>' if none else ''
    sp = sport_of(key)
    on = trends_on(sp, day)
    none = [f"{sp.code(g['away'])} @ {sp.code(g['home'])}" for g in slate(sp, day)[1] if not on.get(str(g['id']))]
    return f'<p class="pv-quiet">No trends on: {esc(", ".join(none))}.</p>' if none else ''


def past_line(key, day, days, root):
    older = [d for d in days if d < day][:2]
    weeks = {d: w for d, w in days.items()} if isinstance(days, dict) else {}
    links = ' &middot; '.join(f'<a href="{root}{page_dir(key, weeks.get(d) or d)}">{esc(f"Week {weeks[d]}" if weeks.get(d) else short_day(d))}</a>' for d in older)
    return (f'<p class="pv-past">Past previews: {links + " &middot; " if links else ""}'
            f'<a href="{root}{page_dir(key)}archive/">All &rarr;</a></p>')


def article(p, root, days, have):
    """The article page's body: the reading column and the right column."""
    key, day = p['sport'], p['date']
    head, dek, md = split(p['body'])
    body = daily.to_html(md)
    keys = [k for k in (p.get('covers') or covers(day)) if k in sports.BY_KEY] if key == ALL else [key]
    box_id = ((p.get('boxes') or {}).get('league_trend') or {}).get('id')
    if key == ALL:
        body = sport_sections(body, day, root, have)
    else:
        body = matchup_heads(body, key, day, root)
    body = link_teams(body, keys, root, day)
    section = '<h2' if key == ALL else '<h2 class="pv-mh"'
    body = place_ad(body, '<h2' if key == ALL else GAME_HEAD)
    bx = boxes_html(p, root)
    body = place_boxes(body, bx + (ad_slot('boxes') if bx else ''), section)
    body += more_line(key, day, root, body, box_id, keys)
    if key == ALL:
        what = names_list([sports.BY_KEY[k]['label'] for k in keys])
    else:
        n = len(slate(sport_of(key), day)[1])
        what = f'{n} game{"s" if n != 1 else ""}'
    img = (f'<img class="pv-img" src="{root}{card_path(key, day)}" width="1200" height="630" alt="{esc(head)}">'
           if has_card(key, day) else '')
    side = (tonight(key, day, root) + ad_slot('side') + '<section class="pv-side-card pv-tab"><h2 class="pv-side-h">Picks are coming with Premium</h2>'
            '<p>Get on the list and you&rsquo;ll hear first.</p><!--signup:tab--></section>')
    return (f'<div class="pv"><article class="pv-main"><p class="pv-label">{label(key, day, piece_week(p))}</p>'
            f'<h1 class="pv-h1">{esc(head)}</h1>' + (f'<p class="pv-dek">{esc(dek)}</p>' if dek else '') +
            f'<p class="pv-by">By RTYB &middot; {published_txt(p)}{esc(what)}</p>{img}'
            f'<div class="pv-body">{body}</div>{quiet_line(key, day)}{past_line(key, day, days, root)}{FOOT}</article>'
            f'<aside class="pv-side">{side}</aside></div>')


def empty(key, root):
    who = 'today&rsquo;s first-segment preview' if key == ALL else f"the {esc(sports.seo_name(key))} preview"
    return (f'<div class="pv"><article class="pv-main"><p class="pv-label">Preview</p><h1 class="pv-h1">Preview</h1>'
            f'<p class="pv-dek">The first Preview lands at 11 AM ET: {who}.</p></article></div>')


def archive(key, pieces, root):
    rows = ''.join(f'<a class="st-card pv-arow" href="{root}{piece_dir(p)}"><span class="pv-label">{esc(f"Week {piece_week(p)}" if piece_week(p) else short_day(p["date"]))}</span>'
                   f'<b class="pv-ahead">{esc(split(p["body"])[0])}</b></a>' for p in pieces)
    h1 = 'Past Previews' if key == ALL else f"Past {esc(sports.seo_name(key))} Previews"
    return f'<div class="pv pv-archive"><article class="pv-main"><h1 class="pv-h1">{h1}</h1><div class="pv-alist">{rows}</div></article></div>'


# ------------------------------------------------------------ the pages
def share_meta(path):
    return f'<meta name="rtyb:image" content="{esc(path)}">'


def pages(now_utc):
    """[(key, page dir, title, desc, body builder(root), canonical dir or
    None, share image or None, noindex)] for every Preview page."""
    pieces = visible(now_utc)
    by_key = {}
    for p in pieces:
        if p['sport'] == ALL or p['sport'] in sports.BY_KEY:
            by_key.setdefault(p['sport'], []).append(p)
    have = {(p['sport'], p['date']) for p in pieces}
    out = []
    for key in [ALL] + [sp['key'] for sp in sports.SPORTS]:
        mine, seen = [], set()
        for p in sorted(by_key.get(key) or [], key=lambda p: p['date'], reverse=True):   # one piece per week page: the newest
            if piece_dir(p) not in seen:
                seen.add(piece_dir(p))
                mine.append(p)
        days = {p['date']: piece_week(p) for p in mine}
        for i, p in enumerate(mine):
            head, dek, _ = split(p['body'])
            img = card_path(key, p['date']) if has_card(key, p['date']) else None
            for d, canon in ((piece_dir(p), None),) + (((page_dir(key), piece_dir(p)),) if i == 0 else ()):
                out.append((key, d, title(key, head, p['date'], piece_week(p)), dek or head,
                            (lambda root, p=p, days=days: article(p, root, days, have)), canon, img, False))
        if mine:
            out.append((key, page_dir(key) + 'archive/', title(key, 'Past Previews').replace(': Past Previews', ' Archive'),
                        'Every past preview, newest first.', (lambda root, mine=mine, key=key: archive(key, mine, root)), None, None, False))
        else:
            out.append((key, page_dir(key), title(key, 'Coming at 11 AM ET'), 'Our daily first-segment preview, from 11 AM ET.',
                        (lambda root, key=key: empty(key, root)), None, None, True))
    return out


def write_all(page, status, logo_svg, now_utc, render_sport):
    """Writes every Preview page: the all-sports ones with home.page, the
    sport ones with render_sport(sport, title, desc, body, page dir) (the
    sport template). Returns the count."""
    n = 0
    for key, d, t, desc, build, canon, img, noindex in pages(now_utc):
        if key == ALL:
            depth = '../' * d.count('/')
            out = page(t, desc[:300], build(depth), status, depth=depth, noindex=noindex, current='preview').replace('__LOGO_SVG__', logo_svg)
        else:
            out = render_sport(sports.BY_KEY[key], t, desc[:300], build('__ROOT__/'), d, noindex)
        extra = (f'<link rel="canonical" href="{esc(seo_url() + canon)}">' if canon else '') + (share_meta(img) if img else '')
        out = out.replace('</title>', '</title>' + extra, 1)
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
        with open(os.path.join(ROOT, d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
        n += 1
    return n


# ------------------------------------------------------ the admin's Preview tab
ADMIN_DAYS, ADMIN_WEEKS = 7, 4   # History: the last 7 days (weekly sports: the last 4 weeks)
ADMIN_DIR = 'admin/preview'      # each piece as it will publish (the Preview tab's frame)


def admin_pieces(now_utc):
    """[piece] for the admin: every preview draft and published preview in
    the History window, newest first (a draft and its published copy: the
    published one)."""
    today = today_et(now_utc)
    since = (date.fromisoformat(today) - timedelta(days=ADMIN_WEEKS * 7)).isoformat()
    stamps = dict(read_json(daily.PUBLISHED_AT, {}) or {})   # publish times from before the Worker stamped them
    out = {}
    for folder, live in (('drafts', False), ('published', True)):
        d = os.path.join(ROOT, 'content', folder)
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            m = re.fullmatch(r'([a-z]+)-preview-(\d{4}-\d{2}-\d{2})\.md', name)
            if not m or m.group(2) < since or (m.group(1) != ALL and m.group(1) not in sports.BY_KEY):
                continue
            with open(os.path.join(d, name), encoding='utf-8') as f:
                meta, body = daily.parse(f.read())
            out[(m.group(1), m.group(2))] = {
                'kind': 'preview', 'sport': m.group(1), 'date': m.group(2), 'body': body, 'live': live,
                'path': f'content/{folder}/{name}', 'lead': meta.get('lead'), 'week': meta.get('week'),
                'covers': meta.get('sports') if isinstance(meta.get('sports'), list) else None,
                'boxes': {k: meta[k] for k in ('stat_of_night', 'league_trend', 'edge_play') if isinstance(meta.get(k), dict)},
                'published': daily.published_at(name, meta, stamps) if live else None, 'written': meta.get('written')}
    keep = []
    for (key, day), p in sorted(out.items(), key=lambda x: x[0][1], reverse=True):
        weekly_key = key != ALL and weekly(sport_of(key))
        if weekly_key:
            weeks = sorted({q['date'] for (k, _), q in out.items() if k == key}, reverse=True)
            if day not in weeks[:ADMIN_WEEKS]:
                continue
        elif day < (date.fromisoformat(today) - timedelta(days=ADMIN_DAYS - 1)).isoformat():
            continue
        keep.append(p)
    return keep


def icon_css():
    """The league icons' colors for the admin (which has its own stylesheet):
    the site's dark-theme --ball-* values and its .sport-icon rules."""
    with open(os.path.join(ROOT, 'assets', 'site.css'), encoding='utf-8') as f:
        css = f.read()
    ball = {}
    for name, value in re.findall(r'(--ball-[\w-]+):\s*([^;]+);', css):
        ball.setdefault(name, value.strip())   # the first is the default (dark) theme's
    rules = re.findall(r'\.sport-icon \.bi-[^{]+\{[^}]*\}', css)
    return ':root { ' + ' '.join(f'{k}: {v};' for k, v in ball.items()) + ' }\n' + '\n'.join(r.strip() for r in rules)


def admin_dir(p):
    return f"{ADMIN_DIR}/{p['sport']}-{p['date']}/"


def admin_pages(page, status, logo_svg, now_utc, render_sport):
    """The admin's Preview tab: assets/preview/admin.json ({pieces: {key:
    [History rows]}, icons: {sport: svg}, iconCss}) and every piece's page as it will publish, with the
    live page's template and CSS, at admin/preview/{key}-{date}/ (noindex;
    the admin folder is disallowed in robots.txt)."""
    pieces = admin_pieces(now_utc)
    have = {(p['sport'], p['date']) for p in visible(now_utc)}
    index = {}
    for p in pieces:
        head, dek, _ = split(p['body'])
        d = admin_dir(p)
        if p['sport'] == ALL:
            depth = '../' * d.count('/')
            out = page(title(ALL, head, p['date']), (dek or head)[:300], article(p, depth, {}, have), status,
                       depth=depth, noindex=True, current='preview').replace('__LOGO_SVG__', logo_svg)
        else:
            out = render_sport(sports.BY_KEY[p['sport']], title(p['sport'], head, p['date'], piece_week(p)), (dek or head)[:300],
                               article(p, '__ROOT__/', {}, have), d, True)
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)
        with open(os.path.join(ROOT, d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
        index.setdefault(p['sport'], []).append({
            'date': p['date'], 'week': piece_week(p), 'path': p['path'], 'live': p['live'], 'page': d,
            'published': p['published'], 'written': p['written'], 'headline': head})
    icon = {sp['key']: icons.sport_icon(sp) for sp in sports.SPORTS}
    write_json(os.path.join(ROOT, CARD_DIR, 'admin.json'), {'pieces': index, 'icons': icon, 'iconCss': icon_css()})
    return len(pieces)


def seo_url():
    import seo
    return seo.site_url()


def dated_keys():
    """(key, date, page dir) of every preview showing (for the old
    /on-tap/ forwards, and a weekly piece's dated page to its week's);
    today's only from 11 AM ET, when its page goes up (visible)."""
    return [(p['sport'], p['date'], piece_dir(p)) for p in visible(datetime.now(timezone.utc)) if p['sport'] == ALL or p['sport'] in sports.BY_KEY]


# -------------------------------------------------- home and hub sections
def todays(key, now_utc):
    """The preview showing today for key (football: this week's), or None."""
    today = today_et(now_utc)
    pieces = [p for p in visible(now_utc) if p['sport'] == key]
    if key != ALL and sports.BY_KEY[key].get('schedule') == 'week' and sports.preview_weekly(key):
        sp = sport_of(key)
        now = (week_of(sp, today) or {}).get('key')
        return next((p for p in sorted(pieces, key=lambda p: p['date'], reverse=True)
                     if now and (week_of(sp, p['date']) or {}).get('key') == now), None)
    return next((p for p in pieces if p['date'] == today), None)


def hero(now_utc, root=''):
    """The home hero once the all-sports preview is up: the image card left,
    the label, headline, dek and link right (stacked on phones)."""
    p = todays(ALL, now_utc)
    if not p:
        return ''
    head, dek, _ = split(p['body'])
    img = (f'<img class="pv-hero-img" src="{root}{card_path(ALL, p["date"])}" width="1200" height="630" alt="">'
           if has_card(ALL, p['date']) else '')
    return (f'<section class="fr-sec pv-hero" id="preview">{img}<div class="pv-hero-copy"><p class="pv-label">{label(ALL, p["date"])}</p>'
            f'<h2 class="pv-hero-h">{esc(head)}</h2>' + (f'<p class="pv-dek">{esc(dek)}</p>' if dek else '') +
            f'<a class="pv-go" href="{root}{page_dir(ALL)}">Read the full preview &rarr;</a></div></section>')


def hub_section(key, now_utc, root=''):
    """A hub's "[SPORT] PREVIEW": the date, image card, headline, first
    paragraph and the link. Nothing when the sport has no preview today."""
    p = todays(key, now_utc)
    if not p:
        return ''
    head, dek, md = split(p['body'])
    first = next((b for b in re.split(r'\n\s*\n', md) if b.strip() and not b.strip().startswith(('#', '<<'))), '')
    img = (f'<img class="pv-img" src="{root}{card_path(key, p["date"])}" width="1200" height="630" alt="">'
           if has_card(key, p['date']) else '')
    name, wk = sports.seo_name(key), piece_week(p)
    when = f'Week {wk}' if wk else short_day(p['date'])   # a weekly preview shows all week
    return (f'<section class="fr-sec pv-hub" id="preview"><div class="fr-head fr-stack"><h2>{esc(name)} Preview</h2>'
            f'<span class="fr-date">{esc(when)}</span></div><div class="st-card pv-hub-card">{img}'
            f'<h3 class="pv-hub-h">{esc(head)}</h3><p class="pv-hub-p">{daily.inline(daily.plain(first))}</p>'
            f'<a class="pv-go" href="{root}{page_dir(key)}">Read the full {esc(name)} {"Week " + str(wk) + " " if wk else ""}preview &rarr;</a></div></section>')


# ------------------------------------------------------------ image cards
def chrome():
    for c in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        if shutil.which(c):
            return shutil.which(c)
    mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    return mac if os.path.exists(mac) else None


def big_logo(sport, slug):
    """The team's logo for the card: a 320px copy (fetched once, on the
    refresh job), else the site's 96px one. NHL: its SVG."""
    if sport.key == 'nhl':
        p = os.path.join(ROOT, 'assets', 'logos', f'{slug}_dark.svg')
        return p if os.path.exists(p) else None
    base = os.path.join(ROOT, 'assets', 'logos', sport.key)
    big = os.path.join(base, 'lg', f'{slug}.png')
    if not os.path.exists(big) and os.environ.get('GITHUB_ACTIONS'):
        fetch_big(sport.key, slug, big)
    for p in (big, os.path.join(base, f'{slug}-dark.png'), os.path.join(base, f'{slug}.png')):
        if os.path.exists(p):
            return p
    return None


def fetch_big(key, slug, out):
    """ESPN's dark logo (else the default) at BIG_LOGO px, the same source
    as scripts/fetch_sport_logos.py."""
    import fetch_sport_logos as F
    if key not in F.SOURCES:
        return
    folder = F.SOURCES[key][1]
    teams = read_json(os.path.join(F.TEAMS_DIR, f'{key}.json'), {}) or {}
    t = next((x for x in teams.get('teams') or [] if x.get('slug') == slug), None)
    ident = (slug[5:] if slug.startswith('espn-') else (t or {}).get('espn_id')) if folder == 'ncaa' else ((t or {}).get('code') or '').lower()
    if not ident:
        return
    for kind in ('500-dark', '500'):
        path = f'/i/teamlogos/{folder}/{kind}/{ident}.png'
        data = F.get(f'https://a.espncdn.com/combiner/i?img={urllib.parse.quote(path)}&h={BIG_LOGO}&w={BIG_LOGO}', tries=2)
        if data:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'wb') as f:
                f.write(data)
            return


def file_url(path):
    return 'file://' + urllib.parse.quote(os.path.abspath(path))


def card_team(sport, slug):
    src = big_logo(sport, slug)
    logo = (f'<img class="pc-logo" src="{file_url(src)}" alt="">' if src else sport.badge(slug, 110, ROOT + '/'))
    return f'<div class="pc-team">{logo}<b class="pc-name">{esc(sport.full_name(slug))}</b></div>'


def card_html(info, logo_svg):
    """The card's page: the site's stylesheet (template.html .pc-*), 600x315."""
    sp = sport_of(info['sport'])
    t = parse(info.get('start'))
    if t:
        local = t.astimezone(ET)
        when = local.strftime('%a %-I:%M %p ET').upper() if sp.weekly else ('TONIGHT ' if local.hour >= 17 else 'TODAY ') + local.strftime('%-I:%M %p ET')
    else:
        when = ''
    return (f'<!doctype html><html lang="en" data-theme="dark"><head><meta charset="utf-8">{front_fonts()}'
            f'<link rel="stylesheet" href="{file_url(os.path.join(ROOT, "assets", "site.css"))}"></head><body class="pc-body">'
            f'<div class="pc"><div class="pc-top"><span class="pc-when">{icons.sport_icon(sp.sp)}{esc(sp.label)} &middot; {esc(when)}</span>'
            f'<span class="pc-mark">{logo_svg}</span></div>'
            f'<div class="pc-teams">{card_team(sp, info["away"])}<span class="pc-at">@</span>{card_team(sp, info["home"])}</div>'
            + (f'<div class="pc-chip">{esc(info["chip"])}</div>' if info.get('chip') else '') + '</div></body></html>')


def front_fonts():
    import home
    return home.FONTS


def draw(jobs):
    """[(png path, html)] drawn with headless Chrome; returns how many."""
    exe = chrome()
    if not exe or not jobs:
        if jobs:
            print(f'preview cards: no Chrome found; {len(jobs)} card(s) not drawn')
        return 0
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (out, page_html) in enumerate(jobs):
            src = os.path.join(tmp, f'card{i}.html')
            with open(src, 'w', encoding='utf-8') as f:
                f.write(page_html)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            cmd = [exe, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-sandbox', '--allow-file-access-from-files',
                   f'--window-size={CARD_W},{CARD_H}', '--force-device-scale-factor=2', '--virtual-time-budget=6000',
                   f'--user-data-dir={os.path.join(tmp, "profile")}', f'--screenshot={out}', file_url(src)]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=90)
                done += os.path.exists(out)
            except (subprocess.SubprocessError, OSError) as e:
                print(f'preview card {out}: {e}')
    return done


def build_cards(now_utc, logo_svg):
    """Every card due: today's drafts and every visible preview, redrawn
    only when what's on it changes (assets/preview/index.json)."""
    today = today_et(now_utc)
    index_path = os.path.join(ROOT, CARD_DIR, 'index.json')
    index = read_json(index_path, {}) or {}
    want = {}
    for p in visible(now_utc):
        want[(p['sport'], p['date'])] = p.get('lead')
    for key, p in drafts(today).items():
        want.setdefault((key, today), p.get('lead'))
    jobs, keys = [], []
    for (key, day), override in sorted(want.items()):
        if key != ALL and key not in sports.BY_KEY:
            continue
        info = lead_of(key, day, override, now_utc)
        if not info:
            continue
        page_html = card_html(info, logo_svg)
        sig = hashlib.sha1(json.dumps([CARD_VERSION, info], sort_keys=True).encode()).hexdigest()[:12]
        if (index.get(day) or {}).get(key) == sig and has_card(key, day):
            continue
        jobs.append((os.path.join(ROOT, card_path(key, day)), page_html))
        keys.append((key, day, sig))
    # the admin's lead dropdowns and "Draft now": today's drafts, plus every sport with games to draft
    on = [k for k in [ALL] + [sp['key'] for sp in sports.shown(date.fromisoformat(today))]
          if (covers(today) if k == ALL else slate(sport_of(k), today)[1])]
    write_json(os.path.join(ROOT, CARD_DIR, today, 'games.json'),
               admin_games(today, list(dict.fromkeys([k for k, d in want if d == today] + on)), now_utc))
    drew = draw(jobs)
    for (key, day, sig), (out, _) in zip(keys, jobs):
        if os.path.exists(out):
            index.setdefault(day, {})[key] = sig
    if keys:
        write_json(index_path, index)
    return drew


def admin_games(day, keys, now_utc):
    """The admin's lead-game dropdowns (assets/preview/{day}/games.json):
    {key: {lead, motd, games: [{value "nba:401910018", label}]}}."""
    out = {}
    for key in keys:
        lead, motd = lead_of(key, day, None, now_utc), motd_of(key, day)
        games = []
        for sp, g, items in sorted(candidates(key, day), key=lambda c: (c[1].get('start') or '', c[0].key)):
            t = parse(g.get('start'))
            when = t.astimezone(ET).strftime('%-I:%M %p ET') if t else ''
            games.append({'value': f"{sp.key}:{g['id']}", 'trends': len(items),
                          'label': (f'{sp.label} · ' if key == ALL else '') + f"{sp.full_name(g['away'])} at {sp.full_name(g['home'])}" + (f' · {when}' if when else '')})
        codes = sorted({sp.code(g[s]) for sp, g, _ in candidates(key, day) for s in ('away', 'home')})
        out[key] = {'codes': codes,   # the phrase check's team codes
                    'lead': f"{lead['sport']}:{lead['id']}" if lead else None,
                    'motd': f'{motd[0]}:{motd[1]}' if motd else None, 'games': games}
        if key != ALL and weekly(sport_of(key)):   # the admin's "Draft now": one draft per week
            out[key]['week'] = week_num(sport_of(key), day)
    return out
