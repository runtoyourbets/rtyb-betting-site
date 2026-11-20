"""
/stats/: every sport's Stats in one page, built into the HTML.

One section per sport on the site (sports.LAUNCHED, menu order), three
cards each in the Stats card style (template.html .st-card), then "More
[Sport] Stats ->" to /{sport}/stats/:

  Season Results  the headline market, home and away: NHL 1P Moneyline,
                  the spread sports' first segment's Spread (1Q; college
                  basketball 1H), MLB NRFI / YRFI. Only games with a line
                  for the market count (CLAUDE.md).
  Best split      the situation with the most units this season (20+
                  games), from the same situations Trends grades
                  (trends.side_angles / game_angles); links to Splits
  Edges           the top closer and the biggest fader: each team's record
                  over the rest of the game after the first segment (the
                  Edges page's Best Closers / Biggest Faders); links to Edges

Off-season sports show last season's numbers, labeled "2026 season".
"""
import html
import os

import icons
import sports
import trends

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INDEX_DIR = 'stats'
H1 = f'{sports.CROSS_WORDS} Betting Stats'
TITLE = sports.page_title(H1)
DESC = 'First period, first quarter and first half betting stats for every sport: season results, the best split and the top closers and faders.'
SPLIT_MIN = 20
CLOSER_MIN = {'ncaab': 8, 'ncaaf': 6}   # the Edges page's minimums (assets/sport.js)


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def pct(w, l):
    return f'{round(100 * w / (w + l))}%' if w + l else '&mdash;'


def units_html(u, priced):
    if not priced:
        return '<span class="st-u st-none">&mdash;</span>'
    r = round(u, 2)
    cls = 'pos' if r > 0.5 else 'neg' if r < -0.5 else 'mid'
    return f'<span class="st-u {cls}">{"+" if r > 0 else ""}{r:.2f}u</span>'


def row(label, rec, pct_txt, units):
    return (f'<div class="st-row"><span class="st-lbl">{label}</span><span class="st-rec mono">{rec}</span>'
            f'<span class="st-pct mono">{pct_txt}</span>{units}</div>')


def head(a, b, c):
    return f'<div class="st-row st-colhead"><span class="st-lbl"></span><span class="st-rec">{a}</span><span class="st-pct">{b}</span><span class="st-u">{c}</span></div>'


def card(title, body, href=None, go=None):
    more = f'<a class="st-go" href="{esc(href)}">{esc(go)} &rarr;</a>' if href else ''
    return f'<div class="st-card"><div class="st-head"><h4>{esc(title)}</h4></div>{body}{more}</div>'


def headline(sp):
    """(segment, market, [(label, kind, bet or side)]) for Season Results."""
    k = sp['segments'][0]['key']
    if sp['key'] == 'nhl':
        return k, 'ml', [('Home', 'side', 'home'), ('Away', 'side', 'away')]
    if sp['key'] == 'mlb':
        return '1i', 'rfi', [('NRFI', 'game', 'no'), ('YRFI', 'game', 'yes')]
    return k, 'ats', [('Home', 'side', 'home'), ('Away', 'side', 'away')]


def market_tag(sp, k, market):
    return trends.tag(sp, k, market)


def season_card(sp, G_all):
    k, market, rows = headline(sp)
    out = []
    for label, kind, x in rows:
        rec = trends.Rec()
        for G in G_all:
            r = trends.side_result(G['g'], k, market, x) if kind == 'side' else trends.game_result(G['g'], k, market, x)
            if r and r[1] is not None:   # a game counts only with a line for the market
                rec.add(*r)
        out.append(row(label, f'{rec.w}-{rec.l}' + (f'-{rec.t}' if rec.t else ''), pct(rec.w, rec.l), units_html(rec.units, rec.priced)))
    return card(f'Season Results · {market_tag(sp, k, market)}', head('Record', 'Win %', 'Units') + ''.join(out),
                sports.section_path(sp, 'stats'), 'Season Results')


def best_split(sp, G_all):
    """(label, Rec) for the situation with the most units, 20+ games."""
    T = trends.tips()
    best = None
    for seg in sp['segments']:
        k = seg['key']
        graded = [G for G in G_all if ((G['g'].get('res') or {}).get(k) or {}).get('sc')]
        for market, kind, bet in trends.bets_for(sp, k):
            if market == 'ml3':
                continue
            if kind == 'side':
                for aid, test in trends.side_angles(sp):
                    back, fade = trends.Rec(), trends.Rec()
                    for G in graded:
                        o = (G['g'].get('odds') or {}).get(k) or {}
                        f = trends.favorite(o)
                        fits = [c for c in G['sides'].values() if test(G, c, f, (o.get('ml') or {}).get(c['side']))]
                        if len(fits) != 1:
                            continue
                        for rec, s in ((back, fits[0]['side']), (fade, trends.other(fits[0]['side']))):
                            r = trends.side_result(G['g'], k, market, s)
                            if r and r[1] is not None:
                                rec.add(*r)
                    title = trends.angle_text(sp, T, 'side_angles', aid, k)[0]
                    for word, rec in (('Back', back), ('Fade', fade)):
                        best = pick(best, f'{word} {title[0].lower()}{title[1:]}', market_tag(sp, k, market), rec)
            else:
                for aid, test in trends.game_angles(sp):
                    rec = trends.Rec()
                    for G in graded:
                        if test(G, trends.favorite((G['g'].get('odds') or {}).get(k))):
                            r = trends.game_result(G['g'], k, market, bet)
                            if r and r[1] is not None:
                                rec.add(*r)
                    title = trends.angle_text(sp, T, 'game_angles', aid, k)[0]
                    word = trends.game_bet_word(sp, k, market, bet)
                    best = pick(best, f'{word}: {title[0].lower()}{title[1:]}', market_tag(sp, k, market), rec)
    return best


def pick(best, label, tag, rec):
    if rec.w + rec.l + rec.t < SPLIT_MIN or not rec.priced:
        return best
    if best is None or rec.units > best[2].units:
        return (label, tag, rec)
    return best


def split_card(sp, G_all):
    b = best_split(sp, G_all)
    href = sports.section_path(sp, 'stats') + 'splits/'
    if not b:
        return card('Best split', '<p class="st-note">No split has 20 games with a line yet.</p>', href, 'Splits')
    label, tag, rec = b
    body = (f'<p class="st-split">{esc(label)} <span class="st-tag">{esc(tag)}</span></p>' + head('Record', 'Win %', 'Units') +
            row('This season', f'{rec.w}-{rec.l}' + (f'-{rec.t}' if rec.t else ''), pct(rec.w, rec.l), units_html(rec.units, rec.priced)))
    return card('Best split', body, href, 'Splits')


def closers(sp, doc, G_all):
    """(best closer, biggest fader): each {slug, w, l, t, p, q} or None."""
    k = sp['segments'][0]['key']
    later = {}
    for G in G_all:
        g = G['g']
        r = (g.get('res') or {}).get(k) or {}
        if g.get('state') != 'final' or not r.get('sc') or not isinstance(g.get('as'), (int, float)) or not isinstance(g.get('hs'), (int, float)):
            continue
        a, h = r['sc']
        for side, mine, theirs in (('away', g['as'] - a, g['hs'] - h), ('home', g['hs'] - h, g['as'] - a)):
            t = later.setdefault(g[side], {'w': 0, 'l': 0, 't': 0, 'm': 0})
            t['w' if mine > theirs else 'l' if mine < theirs else 't'] += 1
            t['m'] += mine - theirs
    teams = doc.get('teams') or {}
    least = CLOSER_MIN.get(sp['key'], 3)
    rows = []
    for slug, x in later.items():
        d, gp = x['w'] + x['l'], x['w'] + x['l'] + x['t']
        if slug in teams and gp >= least and d:
            rows.append(dict(x, slug=slug, p=x['w'] / d, q=x['l'] / d, avg=x['m'] / gp))
    if not rows:
        return None, None
    best = sorted(rows, key=lambda e: (-e['p'], -e['avg'], e['slug']))[0]
    worst = sorted(rows, key=lambda e: (-e['q'], e['avg'], e['slug']))[0]
    return best, worst


def edges_card(sport, sp, doc, G_all, root):
    best, worst = closers(sp, doc, G_all)
    href = sports.section_path(sp, 'stats') + 'edges/'
    if not best:
        return card('Edges', '<p class="st-note">Closers and faders start once games are final.</p>', href, 'Edges')
    rest = {'1p': 'Periods 2&ndash;3', '1q': 'Quarters 2&ndash;4', '1h': '2nd half', '1i': 'Innings 2&ndash;9', 'f5': 'Innings 6&ndash;9'}

    def team(e):
        inner = f'{sport.badge(e["slug"], 22, root)}{sport.name_html(e["slug"])}'
        href = sport.team_href(e['slug'], root)
        return f'<a class="gm-team st-teamlink" href="{esc(href)}">{inner}</a>' if href else f'<span class="st-teamlink">{inner}</span>'
    body = (head('Record', 'Win %', '') +
            row(f'<span class="st-kind">Top closer</span>{team(best)}', f'{best["w"]}-{best["l"]}-{best["t"]}', f'{round(100 * best["p"])}%', '<span class="st-u"></span>') +
            row(f'<span class="st-kind">Biggest fader</span>{team(worst)}', f'{worst["w"]}-{worst["l"]}-{worst["t"]}', f'{round(100 * worst["p"])}%', '<span class="st-u"></span>'))
    return card(f"Edges · {html.unescape(rest.get(sp['segments'][0]['key'], 'rest of game'))}", body, href, 'Edges')


def section(sport, root):
    sp = sport.sp
    G_all = trends.prepare(sp, sport.doc)
    off = not sports.in_season(sp)
    label = f'<span class="ix-week">&middot; {esc(sport.doc.get("seasonLabel") or "")} season</span>' if off and sport.doc.get('seasonLabel') else ''
    cards = season_card(sp, G_all) + split_card(sp, G_all) + edges_card(sport, sp, sport.doc, G_all, root)
    stats = root + sports.section_path(sp, 'stats').lstrip('/')
    cards = cards.replace('href="/', 'href="' + root)   # the cards' root-relative links, from this page's depth
    return (f'<section class="ix-group" id="ix-{sp["key"]}"><h2 class="ix-sport">{icons.sport_icon(sp)}{esc(sp["menu_label"])} {label}</h2>'
            f'<div class="st-grid">{cards}</div>'
            f'<div class="fr-links"><a class="fr-more" href="{esc(stats)}">More {esc(sp["menu_label"])} Stats &rarr;</a></div></section>')


def body(root='../'):
    import front
    S = {sp['key']: front.Sport(sp) for sp in sports.LAUNCHED}
    return (f'<div class="ix" id="ix-top"><div class="ix-head"><h1>{esc(H1)}</h1></div>'
            + ''.join(section(s, root) for s in S.values()) + '</div>')


def write(page, status, logo_svg):
    out = page(TITLE, DESC, body(), status, depth='../', current='stats').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, INDEX_DIR), exist_ok=True)
    with open(os.path.join(ROOT, INDEX_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(out)
