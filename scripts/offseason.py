"""
The hub blocks for a sport between seasons (scripts/seasons.py layout 'off':
the off-season, the preseason and the 14 days after the final), drawn from
the season just played (data.json; once the next season's schedule is in it,
history.json) and the Site settings' dates:

  Countdown card     "[YEAR] SEASON · OFF-SEASON": days / hours / minutes to
                     OPENING_DAY (ticking, front.FRONT_JS), the date, then the
                     MILESTONES with their dates and days left; no
                     OPENING_DAY: "Opening day: date TBA" and the milestones
  Champions card     the winner of the final series or game (never typed
                     in), the result line, then split pills (All · Home ·
                     Away · Favorite · Underdog) over one cell per market:
                     the team's season record and units
  Best Bet of last season   the season's best trend by units (55%+, 50+ games)
  Season in Review   the season's top 5 trends, one line each
  The RTYB Awards    every market's pill; per market Best team, Worst team,
                     Best underdog, Worst favorite (totals, BTTS, NRFI: the
                     two outcomes), 20+ games per team, else "Not enough
                     lines tracked" (the Champions cells too)

Records count the games graded in the market; units only the priced ones.
A season without saved prices (MLB and WNBA 2026 have F5 / 1Q lines for a
handful of games) ranks by win rate and shows units as a dash.
"""
import json
import os
from datetime import datetime, time as Time

import front
import icons
import seasons
import sport_build
import sports
import trends
from hub import pct_rec

esc = front.esc
ET = front.ET
BEST_MIN_RATE, BEST_MIN_N = 0.55, 50   # Best Bet and Season in Review: 55%+ over 50+ games
REVIEW_SHOWN = 5
AWARD_MIN = 20                         # games per team for an award
SMALL = 10                             # fewer games than this: "Small sample"
TITLE = {'mlb': 'World Series Champions', 'wnba': 'WNBA Champions', 'nba': 'NBA Champions', 'nhl': 'Stanley Cup Champions',
         'nfl': 'Super Bowl Champions', 'ncaab': 'National Champions', 'ncaaf': 'National Champions'}
SPLITS = (('all', 'All'), ('home', 'Home'), ('away', 'Away'), ('fav', 'Favorite'), ('dog', 'Underdog'))
SIDE_AWARDS = (('best', '\U0001F3C6', 'Best team'), ('worst', '\U0001F9CA', 'Worst team'),
               ('dog', '\U0001F436', 'Best underdog'), ('fav', '\U0001F4B8', 'Worst favorite'))
GAME_AWARDS = {'total': (('over', '\U0001F525', 'Most Overs'), ('under', '\U0001F9F1', 'Most Unders')),
               'btts': (('yes', '\U0001F3AF', 'Most BTTS Yes'), ('no', '\U0001F9E4', 'Most BTTS No')),
               'rfi': (('no', '\U0001F6AB', 'Most NRFI'), ('yes', '⚡', 'Most YRFI'))}


# ----------------------------------------------------------------- data
def season_doc(sport):
    """The season just played: data.json while it holds it, else history.json
    (the shared shape only; NHL's history.json has no results)."""
    if any(g.get('state') in ('final', 'post') for _, g in sport.all_games()):
        return sport.doc
    hist = sport_build.read_json(os.path.join(sport.dir, 'history.json'), None) or {}
    return hist if isinstance(hist.get('games'), dict) else sport.doc


def season_label(doc):
    return str(doc.get('seasonLabel') or doc.get('season') or '')


def markets(sport):
    """[(segment, market, pill label, cell label)] in the Awards' order:
    MLB F5 Moneyline · F5 Run Line · F5 Total · 1st Inning; NHL 1P
    Moneyline · Over 1.5 · BTTS · 3-Way; spread sports per segment Spread ·
    Moneyline · Total."""
    key = sport.key
    if key == 'mlb':
        return [('f5', 'ml', 'F5 Moneyline', 'F5 ML'), ('f5', 'ats', 'F5 Run Line', 'F5 Run Line'),
                ('f5', 'total', 'F5 Total', 'F5 Total'), ('1i', 'rfi', '1st Inning', '1st Inning')]
    if key == 'nhl':
        return [('1p', 'ml', '1P Moneyline', '1P ML'), ('1p', 'total', 'Over 1.5', '1P O/U 1.5'),
                ('1p', 'btts', 'BTTS', '1P BTTS'), ('1p', 'ml3', '3-Way', '1P 3-Way')]
    out = []
    for seg in sport.segments:
        tag = seg['tag']
        for m, word in (('ats', 'Spread'), ('ml', 'Moneyline'), ('total', 'Total')):
            if m == 'ml' and not sports.has_ml(seg):
                continue
            out.append((seg['key'], m, f'{tag} {word}', f'{tag} {"ML" if m == "ml" else word}'))
    return out


def lined(g, k, m):
    """A saved line for the market (records count only those, CLAUDE.md);
    a moneyline and NRFI grade from the score alone, as the Stats pages do."""
    if m in ('ml', 'rfi'):
        return True
    o = ((g.get('odds') or {}).get(k) or {}).get('ml3' if m == 'ml3' else m)
    return bool(o)


class Tally:
    """A record (W / L, pushes left out) and the units of its priced games."""

    def __init__(self):
        self.w = self.l = self.priced = 0
        self.units = 0.0

    def add(self, res, units):
        if res == 'W':
            self.w += 1
        elif res == 'L':
            self.l += 1
        else:
            return
        if units is not None:
            self.units += units
            self.priced += 1

    @property
    def n(self):
        return self.w + self.l

    @property
    def rate(self):
        return self.w / self.n if self.n else 0

    @property
    def all_priced(self):
        return self.n > 0 and self.priced >= self.n


def team_tallies(sport, doc, k, m):
    """{team: {split: {outcome: Tally}}}: each team's season in one market.
    Side markets: outcome 'side' (the team's bet); game markets: 'over' /
    'under', 'yes' / 'no'."""
    out = {}
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            if g.get('state') not in ('final', 'post') or not lined(g, k, m):
                continue
            fav = trends.favorite((g.get('odds') or {}).get(k))
            for side in ('away', 'home'):
                splits = ['all', side] + (['fav' if fav == side else 'dog'] if fav else [])
                if m in ('ml', 'ats', 'ml3'):
                    x = trends.side_result(g, k, m, side)
                    got = {'side': x} if x else {}
                else:
                    bets = {'total': ('over', 'under'), 'btts': ('yes', 'no'), 'rfi': ('yes', 'no')}[m]
                    got = {b: trends.game_result(g, k, m, b) for b in bets}
                for split in splits:
                    t = out.setdefault(g[side], {}).setdefault(split, {})
                    for outcome, x in got.items():
                        if x:
                            t.setdefault(outcome, Tally()).add(*x)
    return out


def units_html(t):
    """Units in the color rule's tones; a dash when some games had no price."""
    if not t.all_priced:
        return '<span class="os-u">&mdash;</span>'
    return f'<span class="os-u {front.unit_tone(t.units)}">{front.fmt_units(t.units)}</span>'


# ------------------------------------------------------------ Countdown
def opening_at(day):
    """Opening day's midnight in New York, as an ISO time with its offset."""
    return datetime.combine(datetime.fromisoformat(day).date(), Time(0), ET).isoformat()


def countdown(sport, st, doc, now_utc):
    """The countdown card: "[YEAR] SEASON · [STATE]" title bar, OPENING DAY
    with days / hours / minutes boxes (front.FRONT_JS ticks them), the date,
    then each milestone with its date and days left."""
    nxt = int(doc.get('season') or now_utc.astimezone(ET).year) + 1
    year = sport_build.season_label(sport.key, nxt)
    today = now_utc.astimezone(ET).date()
    if st.get('opening'):
        d = datetime.fromisoformat(st['opening']).date()
        left = max(0, int((datetime.fromisoformat(opening_at(st['opening'])) - now_utc).total_seconds() // 60))
        boxes = ''.join(f'<span class="cd-box"><span class="cd-n" data-cd="{u}">{v}</span><span class="cd-u">{w}</span></span>'
                        for u, v, w in (('d', left // 1440, 'Days'), ('h', left // 60 % 24, 'Hours'), ('m', left % 60, 'Minutes')))
        opening = (f'<p class="cd-l">Opening day</p><div class="cd-boxes" data-countdown="{esc(opening_at(st["opening"]))}">{boxes}</div>'
                   f'<p class="cd-date">{d.strftime("%A, %B")} {d.day}, {d.year}</p>')
    else:
        opening = '<p class="cd-l">Opening day</p><p class="cd-date">Opening day: date TBA</p>'
    ms = ''
    for m in st.get('milestones') or []:
        d = datetime.fromisoformat(m['date']).date()
        n = (d - today).days
        left = f' &middot; <span data-days="{esc(m["date"])}">{n} day{"" if n == 1 else "s"}</span>' if n > 0 else ''
        ms += f'<li><span class="cd-ml">{esc(m["label"])}</span><span class="cd-md">{d.strftime("%b")} {d.day}{left}</span></li>'
    ms = f'<ul class="cd-ms">{ms}</ul>' if ms else ''
    return (f'<section class="fr-sec cd" id="countdown"><div class="st-card cd-card"><div class="st-head"><h4>'
            f'{esc(year)} Season &middot; {esc(st["label"])}</h4></div>{opening}{ms}</div></section>')


# ------------------------------------------------------------ Champions
def result_line(sport, ch):
    """"Beat the Tampa Bay Rays 4–1" (a series); "Beat the Miami Hurricanes 27–21" (one game)."""
    opp = sport.full_name(ch['opp'])
    the = '' if sport.key in sports.COLLEGE else 'the '
    w, l = (ch['wins'], ch['losses']) if ch['wins'] + ch['losses'] > 1 else ch['score']
    return f'Beat {the}{opp} {w}–{l}'


def big_html(t):
    """The big Barlow %, the record under it, the units under that."""
    pct = round(100 * t.w / t.n) if t.n else 0
    small = '<span class="os-small">Small sample</span>' if t.n < SMALL else ''
    return (f'<span class="os-big">{pct}%</span><span class="os-rec">{t.w}–{t.l}</span>{small}'
            f'{units_html(t).replace("os-u", "os-u os-ub", 1)}')


NOT_ENOUGH = '<span class="os-none">Not enough lines tracked</span>'


def cell(label, side, t):
    """One market: fewer than AWARD_MIN tracked games says so instead."""
    body = big_html(t) if t and t.n >= AWARD_MIN else NOT_ENOUGH
    side = f'<span class="os-side">{esc(side)}</span>' if t and t.n >= AWARD_MIN else ''
    return f'<div class="os-cell"><span class="os-cl">{esc(label)}</span>{side}{body}</div>'


def champ_cells(sport, doc, team):
    """{split: html}: one cell per market with the champion's record there
    (every market, every split with at least one market tracked)."""
    out, live = {}, set()
    for k, m, _, label in markets(sport):
        tal = (team_tallies(sport, doc, k, m).get(team)) or {}
        for split, _ in SPLITS:
            t = tal.get(split) or {}
            if m in ('ml', 'ats', 'ml3'):
                x = t.get('side')
                side = 'Cover' if m == 'ats' else 'Win'
            else:
                names = {'total': ('over', 'Over', 'under', 'Under'), 'btts': ('yes', 'Yes', 'no', 'No'),
                         'rfi': ('no', 'NRFI', 'yes', 'YRFI')}[m]
                a, b = t.get(names[0]), t.get(names[2])
                x, side = (a, names[1]) if (a.rate if a else 0) >= (b.rate if b else 0) else (b, names[3])
            if x and x.n >= AWARD_MIN:
                live.add(split)
            out[split] = out.get(split, '') + cell(label, side, x)
    return {v: h for v, h in out.items() if v in live}


def champions(sport, doc, root):
    ch = seasons.champion(doc)
    if not ch:
        return ''
    team = ch['team']
    cells = champ_cells(sport, doc, team)
    opts = [(v, t) for v, t in SPLITS if cells.get(v)]
    panes = ''.join(f'<div class="os-cells" data-pane="{v}"{"" if i == 0 else " hidden"}>{cells[v]}</div>' for i, (v, _) in enumerate(opts))
    name = sport.full_name(team)
    href = sport.team_href(team, root)
    links = (front.more_link(href, f'{esc(name)} team page') if href else '') + front.more_link(f'{root}{sport.sp["slug"]}/{sport.sp["sections"]["teams"]}/', f'All {esc(sport.label)} teams')
    return (f'<section class="fr-sec ch" id="champions"><div class="st-card ch-card"><div class="st-head"><h4>\U0001F3C6 Congratulations</h4></div>'
            f'<div class="ch-main">{sport.link(team, sport.badge(team, 84, root), root, "ch-logo")}<div class="ch-copy">'
            f'{sport.link(team, esc(name), root, "ch-name")}<p class="ch-title">{esc(ch["date"][:4])} {esc(TITLE[sport.key])}</p>'
            f'<p class="ch-res">{esc(result_line(sport, ch))}</p></div></div>'
            + (f'<div class="ch-splits" data-tabs>{front.pills("Split", opts, opts[0][0])}{panes}</div>' if opts else '')
            + f'<div class="fr-links">{links}</div></div></section>')


# ------------------------------------------------- the season's trends
def season_trends(sport, doc):
    """Every trend's record over the whole season (55%+ over 50+ games),
    best first: by units when the season has prices, else by win rate."""
    def bar(rec, base):
        if rec.n < BEST_MIN_N or rec.rate is None or rec.rate < BEST_MIN_RATE:
            return None
        return {'w': rec.w, 'l': rec.l, 't': rec.t, 'rate': round(rec.rate, 4), 'base': round(base, 4),
                'units': round(rec.units, 2), 'n': rec.n, 'priced': rec.priced}
    G = trends.prepare(sport.sp, doc)
    cards = trends.generate(sport.sp, doc, G, G, '9999-12-31', trends.tips(), bar=bar)
    priced = any(c['priced'] >= c['n'] for c in cards)
    if priced:
        cards = [c for c in cards if c['priced'] >= c['n'] and c['units'] > 0]
    cards.sort(key=lambda c: (-c['units'], -c['rate']) if priced else (-c['rate'], -c['n']))
    for c in cards:
        c['all_priced'] = c['priced'] >= c['n']
        c.pop('games', None)
    return cards


def last_season_records(sport):
    """{trend id: {w, l, units, all_priced}} over last season (history.json),
    for the early-season "Last season" toggle; {} when there's no shared-shape
    history (NHL's history.json has no results)."""
    hist = sport_build.read_json(os.path.join(sport.dir, 'history.json'), None) or {}
    if not isinstance(hist.get('games'), dict):
        return {}
    def bar(rec, base):
        return {'w': rec.w, 'l': rec.l, 'units': round(rec.units, 2), 'all_priced': rec.n > 0 and rec.priced >= rec.n,
                'rate': rec.rate or 0, 'base': base, 'n': rec.n, 't': rec.t} if rec.n else None
    G = trends.prepare(sport.sp, hist)
    return {c['id']: {k: c[k] for k in ('w', 'l', 'units', 'all_priced')}
            for c in trends.generate(sport.sp, hist, G, G, '9999-12-31', trends.tips(), bar=bar)}


def trend_units(c):
    if not c['all_priced']:
        return '<span class="os-u">&mdash;</span>'
    return f'<span class="os-u {front.unit_tone(c["units"])}">{front.fmt_units(c["units"])}</span>'


def best_bet(sport, doc, cards, root):
    if not cards:
        return ''
    c = cards[0]
    return (f'<section class="fr-sec bb-sec" id="best-bet"><div class="fr-head"><h2>Best Bet of Last Season</h2></div>'
            f'<div class="st-card bb-card"><div class="st-head"><h4>{icons.sport_icon(sport.sp)}{esc(sport.label)} &middot; {esc(season_label(doc))}</h4></div>'
            f'<p class="bb-name">{esc(c["title"])} <span class="mk-h">{esc(c["tag"])}</span></p>'
            f'<p class="bb-rec"><span class="os-rec">{esc(pct_rec(c["w"], c["l"]))}</span>{trend_units(c)}</p>'
            f'<p class="bb-say">{esc(c.get("meaning") or "")}</p></div></section>')


def review(sport, doc, cards, root):
    if not cards:
        return ''
    rows = ''.join(f'<li>{icons.sport_icon(sport.sp)}<span class="sr-t">{esc(c["tag"])} &middot; {esc(c["title"])}</span>'
                   f'<span class="sr-r"><span class="os-rec">{esc(pct_rec(c["w"], c["l"]))}</span>{trend_units(c)}</span></li>'
                   for c in cards[:REVIEW_SHOWN])
    link = front.more_link(f'{root}{sport.trends_page}', f'All {esc(season_label(doc))} {esc(sport.label)} trends')
    return (f'<section class="fr-sec sr" id="season-review"><div class="fr-head"><h2>Season in Review</h2></div>'
            f'<div class="st-card sr-card"><ul class="sr-list">{rows}</ul><div class="fr-links">{link}</div></div></section>')


# ----------------------------------------------------------- the Awards
def award_card(sport, emoji, label, team, t, root):
    if not team:
        return (f'<div class="st-card aw-card aw-empty"><p class="aw-l"><span aria-hidden="true">{emoji}</span> {esc(label)}</p>'
                f'{NOT_ENOUGH}</div>')
    return (f'<div class="st-card aw-card"><p class="aw-l"><span aria-hidden="true">{emoji}</span> {esc(label)}</p>'
            f'<div class="aw-team">{sport.link(team, sport.badge(team, 40, root), root, "aw-logo")}'
            f'{sport.link(team, esc(sport.full_name(team)), root, "aw-name")}</div>'
            f'<p class="aw-rec">{big_html(t)}</p></div>')


def ranked(cands, priced, worst=False):
    """Best first (worst=True: worst first), by units when priced, else by rate."""
    key = (lambda x: (x[1].units, x[1].rate)) if priced else (lambda x: (x[1].rate, x[1].n))
    return sorted(cands, key=key, reverse=not worst)


def award_cards(sport, doc, k, m, root):
    """Every card of the market; one no team has 20+ games for says so."""
    tal = team_tallies(sport, doc, k, m)
    out = ''
    if m in ('ml', 'ats', 'ml3'):
        for kind, emoji, label in SIDE_AWARDS:
            split = {'best': 'all', 'worst': 'all', 'dog': 'dog', 'fav': 'fav'}[kind]
            cands = [(team, (x.get(split) or {}).get('side')) for team, x in tal.items()]
            cands = [(team, t) for team, t in cands if t and t.n >= AWARD_MIN]
            team, t = ranked(cands, all(t.all_priced for _, t in cands), worst=kind in ('worst', 'fav'))[0] if cands else (None, None)
            out += award_card(sport, emoji, label, team, t, root)
    else:
        for outcome, emoji, label in GAME_AWARDS[m]:
            cands = [(team, (x.get('all') or {}).get(outcome)) for team, x in tal.items()]
            cands = [(team, t) for team, t in cands if t and t.n >= AWARD_MIN]
            team, t = ranked(cands, all(t.all_priced for _, t in cands))[0] if cands else (None, None)
            out += award_card(sport, emoji, label, team, t, root)
    return out


def awards(sport, doc, root):
    """Every market's pill, even one without a team at 20+ games."""
    if not any(g.get('state') in ('final', 'post') for gs in (doc.get('games') or {}).values() for g in gs):
        return ''
    panes = [(f'{k}-{m}', pill, award_cards(sport, doc, k, m, root)) for k, m, pill, _ in markets(sport)]
    first = next((v for v, _, h in panes if 'aw-team' in h), panes[0][0])   # open on a market with a winner
    body = ''.join(f'<div class="aw-cards" data-pane="{v}"{"" if v == first else " hidden"}>{h}</div>' for v, _, h in panes)
    link = front.more_link(f'{root}{sport.sp["slug"]}/{sport.sp["sections"]["stats"]}/', f'Full {esc(season_label(doc))} {esc(sport.label)} stats')
    return (f'<section class="fr-sec aw" id="awards" data-tabs><div class="fr-head"><h2>The RTYB Awards</h2>'
            f'<span class="fr-date">{esc(season_label(doc))} season</span></div>'
            f'{front.pills("Market", [(v, p) for v, p, _ in panes], first)}{body}<div class="fr-links">{link}</div></section>')


# ------------------------------------------------- Learn + the Running Tab
def guide_card(sport, root):
    """The sport's Betting Guide, promoted to a full card."""
    import guides
    sp = sport.sp
    return (f'<section class="fr-sec" id="learn"><div class="fr-head"><h2>Betting Guide</h2></div><div class="hl-grid os-guide">'
            + guides.card(root + sports.guide_path(sp).lstrip('/'), guides.sport_title(sp),
                          f"How {sp['label']} {sports.segment_summary(sp)} bets work, and how RTYB counts them.")
            + '</div></section>')


def running_tab(sport):
    import signup
    return ('<section class="fr-sec rt" id="premium"><div class="st-card rt-card"><h2>Get the Running Tab</h2>'
            f'<p class="rt-line">We&rsquo;ll email you when the {esc(sport.label)} season starts.</p>'
            f'{signup.box("tab")}</div></section>')


def blocks(sport, st, now_utc, root):
    """{slot: html} for the off-season layout."""
    doc = season_doc(sport)
    cards = season_trends(sport, doc)
    return {'countdown': countdown(sport, st, doc, now_utc), 'champions': champions(sport, doc, root),
            'best': best_bet(sport, doc, cards, root), 'review': review(sport, doc, cards, root),
            'awards': awards(sport, doc, root), 'guide': guide_card(sport, root), 'tab': running_tab(sport)}
