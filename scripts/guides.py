"""
Betting Guides (replace Learn; /learn/ forwards to /betting-guides/).

Pages:
  /betting-guides/                    the index: general guides, the sport
                                      guides and the glossary
  /betting-guides/glossary/           A-Z, one anchor per term (#btts, #push)
  /betting-guides/{slug}/             first-segment-betting and the bet types
                                      (GENERAL below)
  /{sport slug}/betting-guide/        one per sport ("NHL First Period
                                      Betting Guide")

Content is Markdown in content/betting-guides/, one file per page, named
after the page: index.md, first-segment-betting.md,
moneyline.md, ..., and nhl.md, nba.md ... for the sport guides. Front matter:

  ---
  title: "How Moneyline Bets Work"      (optional, general guides only: the
                                        sport guides' H1 is fixed, sports.h1)
  description: "One or two sentences for search and share cards."
  updated: 2026-11-20
  ---
  Body in Markdown: paragraphs, ## and ### headings, - lists, pipe tables
  (header, --- row, rows: the site's standard table), **bold**, *italic*
  and [links](/nhl/odds/). Live numbers ({{nhl.1p.over:season}},
  {{asof}}) are filled at build time (guide_stats.py); an unknown one
  stops the build. A "## FAQ" section ("### question", then the answer)
  becomes the page's FAQPage data.

Every guide page but the index opens with a breadcrumb (Betting Guides ›
the page; BreadcrumbList data). General guides use the front-matter title
as the H1 and <title>. "Updated" (and dateModified) is the date of the last
build that changed a number on the page, kept in betting_guides_log.json.

The glossary is built from the Live "Markets & terms" entries in
content/definitions.json (the admin's Definitions tab): each term is a
"## Term" heading, anchored by the term in lowercase with dashes ("## 3-Way
Moneyline" -> #3-way-moneyline). Until a page's file exists it shows its title and "Guide
coming this week" and is noindexed.

Every sport page ends with a small Betting Guides block (sport_block): the
sport's guide and two or three bet-type guides for its markets.
"""
import html
import json
import os
import re

import daily
import definitions
import guide_stats
import icons
import seo
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, 'content', 'betting-guides')
INDEX_DIR = 'betting-guides'
INDEX_H1 = f'{sports.CROSS_WORDS} Betting Guides'
LOG = os.path.join(ROOT, 'betting_guides_log.json')

# (slug, default title, one line for the cards)
GENERAL = [
    ('first-segment-betting', 'First-Segment Betting', 'Why bet the 1st period, quarter, half, inning or first five.'),
    ('moneyline', 'Moneyline', 'Picking the winner, and what the price means.'),
    ('spread', 'Spread', 'Covering, pushes and the -110 price.'),
    ('totals', 'Totals', 'Overs, unders and whole-number pushes.'),
    ('btts', 'Both Teams to Score (BTTS)', 'Will both score?'),
    ('3-way-moneyline', '3-Way Moneyline', 'Home, away or tie, with the tie as its own bet.'),
    ('nrfi-yrfi', 'NRFI / YRFI', 'A run in the 1st inning, or not.'),
    ('first-five', 'First Five', 'Baseball’s first five innings, before the bullpens.'),
    ('units', 'Units', 'How Run To Your Bets counts profit and loss.'),
]
GENERAL_BY = {g[0]: g for g in GENERAL}
GLOSSARY = ('glossary', 'Betting Glossary', 'Every term on the site, A to Z.')
# each guide's badge: its section headers' icon tile and its card on the index
BADGE = {'first-segment-betting': '1st', 'moneyline': 'ML', 'spread': '±', 'totals': 'O/U', 'btts': 'BT',
         '3-way-moneyline': '3W', 'nrfi-yrfi': 'NR', 'first-five': 'F5', 'units': 'u', 'glossary': 'A-Z'}
# one fixed example game per sport, shown under each bet in its guide
EXAMPLES = os.path.join(CONTENT, 'examples.json')
RES_CLS = {'won': 'tp-rc-w', 'push': 'tp-rc-p', 'lost': 'tp-rc-n'}

# bet-type guides shown on each sport's pages, after its own guide
SPORT_BET_GUIDES = {'nhl': ['moneyline', '3-way-moneyline', 'btts'], 'mlb': ['nrfi-yrfi', 'first-five', 'moneyline']}
SPREAD_BET_GUIDES = ['spread', 'moneyline', 'totals']
COMING = 'Guide coming this week'


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def anchor(term):
    """'3-Way Moneyline' -> '3-way-moneyline'."""
    return re.sub(r'[^a-z0-9]+', '-', term.lower()).strip('-')


def sport_title(sp):
    """'NHL First Period Betting Guide' (sports.h1)."""
    return sports.h1(sp, 'guide')


def bet_guides(sp):
    return SPORT_BET_GUIDES.get(sp['key'], SPREAD_BET_GUIDES)


_VALUES = {}


def values():
    """Every live number, worked out once per build (guide_stats.table)."""
    if not _VALUES:
        _VALUES.update(guide_stats.table())
    return _VALUES


def read(name):
    """(front matter, body) of content/betting-guides/{name}.md with its
    live numbers filled in, or None. An unknown token raises
    guide_stats.UnknownToken (file and token)."""
    path = os.path.join(CONTENT, f'{name}.md')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        meta, body = daily.parse(f.read())
    numbers = [values()[k] for k in map(guide_stats.key, guide_stats.TOKEN.findall(body)) if k in values() and k != 'asof']
    meta['_numbers'] = numbers
    return meta, guide_stats.fill(body, values(), f'content/betting-guides/{name}.md')


def updated(rel, numbers):
    """The date (New York) of the last build that changed a number on the
    page at `rel`; betting_guides_log.json keeps each page's numbers."""
    try:
        with open(LOG, encoding='utf-8') as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = {}
    row = log.get(rel)
    if row and row.get('numbers') == numbers and row.get('updated'):
        return row['updated']
    log[rel] = {'numbers': numbers, 'updated': guide_stats.today_et().isoformat()}
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write('\n')
    return log[rel]['updated']


def faq(md):
    """[(question, answer)] from the body's "## FAQ" section."""
    m = re.search(r'^##\s+FAQ\s*$(.*?)(?=^##\s|\Z)', md, re.M | re.S)
    if not m:
        return []
    out = []
    for part in re.split(r'^###\s+', m.group(1), flags=re.M)[1:]:
        q, _, a = part.partition('\n')
        a = ' '.join(daily.plain(x).strip() for x in a.strip().splitlines() if x.strip())
        if q.strip() and a:
            out.append((daily.plain(q).strip(), a))
    return out


def crumb(page, root):
    """Betting Guides › page."""
    return (f'<nav class="gd-crumb" aria-label="Breadcrumb"><a href="{root}{INDEX_DIR}/">Betting Guides</a>'
            f'<span aria-hidden="true">›</span><span aria-current="page">{esc(page)}</span></nav>')


def ld_json(rel, page, headline, desc, md, when):
    """The page's structured data: Article (dateModified), BreadcrumbList
    and, with a "## FAQ", FAQPage."""
    base = seo.site_url()
    graph = [{'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Betting Guides', 'item': f'{base}{INDEX_DIR}/'},
        {'@type': 'ListItem', 'position': 2, 'name': page, 'item': base + rel}]}]
    if when:
        graph.insert(0, {'@type': 'Article', 'headline': headline, 'description': desc,
                         'dateModified': when, 'mainEntityOfPage': base + rel})
    qa = faq(md)
    if qa:
        graph.append({'@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in qa]})
    data = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False).replace('</', '<\\/')
    return f'<script type="application/ld+json">{data}</script>'


GLOSSARY_IDS = {}


def glossary_doc():
    """The glossary from the Live Markets & terms entries in the admin's
    Definitions tab (content/definitions.json), A to Z, one ## per term with its
    long definition (the short one when there's no long one). None while
    no term is Live (the page says it's coming)."""
    terms = definitions.glossary_terms()
    GLOSSARY_IDS.clear()
    GLOSSARY_IDS.update({name: slug for slug, name, _, _ in terms})   # #btts, #units: the "i" boxes link here
    if not terms:
        return None
    body = 'Every betting term on Run To Your Bets, A to Z.\n\n' + '\n\n'.join(f'## {name}\n\n{long or short}' for _, name, short, long in terms)
    return ({'title': GLOSSARY[1], 'description': 'Every betting term on Run To Your Bets, A to Z: ' + ', '.join(t[1] for t in terms[:6]) + '…'}, body)


def glossary_html(md, root):
    """The glossary body: every '## Term' heading gets its anchor."""
    out = rooted(daily.to_html(md), root)
    def head(m):
        name = html.unescape(re.sub('<[^>]+>', '', m.group(1)))
        return f'<h2 class="gd-sh" id="{GLOSSARY_IDS.get(name) or anchor(name)}">{m.group(1)}</h2>'
    return re.sub(r'<h2>(.*?)</h2>', head, out)


def article(title, doc, rel, root, slug, is_glossary=False):
    """(body html, description, noindex, <title>) for one guide page at rel."""
    back = f'<p class="gd-back"><a href="{root}{INDEX_DIR}/">&larr; All Betting Guides</a></p>'
    if doc is None:
        return (f'<article class="hp-sec gd-page">{crumb(title, root)}<h1>{esc(title)}</h1>'
                f'<p class="lead">{COMING}.</p>{back}</article>',
                f'{title}: {COMING.lower()} from Run To Your Bets.', True, f'{title} | RTYB Betting Guides')
    meta, body = doc
    content = glossary_html(body, root) if is_glossary else guide_html(body, root)
    headline = meta.get('title') or title
    desc = meta.get('description') or daily.plain(body)[:200]
    day = updated(rel, meta['_numbers']) if '_numbers' in meta else str(meta.get('updated') or '')
    when = day if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) else ''
    date_html = f'<p class="dp-date">Updated {daily.nice_date(when)}</p>' if when else ''
    return (f'<article class="hp-sec gd-page">{crumb(title, root)}<h1>{esc(headline)}</h1>{date_html}'
            f'<div class="dp-body">{content}</div>{back}{ld_json(rel, title, headline, desc, body, when)}</article>',
            desc, False, (not is_glossary and meta.get('title')) or f'{title} | RTYB Betting Guides')


def card(href, title, line):
    return f'<a class="hl-card" href="{href}"><b>{esc(title)}</b><span>{esc(line)}</span></a>'


def badge(slug):
    """A guide's icon tile: its badge (ML, O/U...)."""
    return f'<span class="gd-tile gd-badge" aria-hidden="true">{esc(BADGE.get(slug, "All"))}</span>'


def sport_tile(sp):
    return f'<span class="gd-tile" aria-hidden="true">{icons.sport_icon(sp)}</span>'


def seg_caps(sp):
    """'1ST PERIOD', '1ST INNING · F5' (CSS sets the caps)."""
    return ' · '.join('F5' if seg['key'] == 'f5' else seg['label'] for seg in sp['segments'])


def rooted(out, root):
    """Every site link ("/nhl/odds/") made root-aware for the page."""
    return out.replace('href="/', f'href="{root}')


def headers(out):
    """Every ## header in the guides' purple section style (.gd-sh)."""
    return re.sub(r'<h2>(.*?)</h2>', r'<h2 class="gd-sh">\1</h2>', out)


def link_icon(href):
    """A "Where to go next" pill's icon: the sport's ball for its pages,
    the badge for a guide."""
    m = re.match(r'/betting-guides/([^/]+)/', href)
    if m:
        return badge(m.group(1))
    sp = next((x for x in sports.SPORTS if href.startswith(f"/{x['slug']}/")), None)
    return sport_tile(sp) if sp else badge('')


def next_pills(out):
    """"Where to go next": the list's links as pills with icons."""
    def pills(m):
        links = re.findall(r'<a href="([^"]+)">(.*?)</a>', m.group(2))
        return m.group(1) + '<div class="gd-pills">' + ''.join(
            f'<a class="gd-pill" href="{h}">{link_icon(h)}<span>{t}</span></a>' for h, t in links) + '</div>'
    return re.sub(r'(<h2>Where to go next</h2>\s*)<ul>(.*?)</ul>', pills, out, flags=re.S)


def examples(key):
    """The sport's example games (content/betting-guides/examples.json), in order."""
    try:
        with open(EXAMPLES, encoding='utf-8') as f:
            return json.load(f).get(key) or []
    except (OSError, ValueError):
        return []


def ex_logo(sp, team, root):
    if sp['key'] == 'nhl':
        base = f"{root}assets/logos/{team['logo']}_"
        return icons.logo_html(base + 'light.svg', base + 'dark.svg', 18)
    return icons.team_logo(sp['key'], team['logo'], 18, root=root)


def ex_cells(sp, ex, bet, root):
    """A bet's cells in an example game, won / push / lost, then its result line."""
    cells = ''.join(
        f'<div class="cell {RES_CLS[c["res"]]}"><span class="ob-ln">'
        f'{ex_logo(sp, ex[c["team"]], root) if c.get("team") else ""}{esc(c["text"])}</span>'
        f'<span class="ob-pr">{esc(c["price"])}</span></div>' for c in bet['cells'])
    return (f'<div class="gd-ex-cells gd-ex-{len(bet["cells"])}">{cells}</div>'
            f'<p class="gd-ex-r">{esc(bet["result"])}</p>')


def ex_score(ex, bet):
    return bet.get('score') or ex['score']


def ex_card(sp, exs, heading, root):
    """NHL, MLB: the Example card under one bet, a row per example game
    ("EDM @ TB · 0-0", then "COL @ DAL · 2-1")."""
    rows = ''
    for ex in exs:
        bet = next((b for b in ex['bets'] if b['heading'] == heading), None)
        if bet:
            rows += (f'<div class="gd-ex-row"><p class="gd-ex-h">{esc(ex["away"]["code"])} @ {esc(ex["home"]["code"])} &middot; {esc(ex_score(ex, bet))}</p>'
                     + ex_cells(sp, ex, bet, root) + '</div>')
    return f'<div class="st-card gd-ex">{rows}</div>'


def game_card(sp, ex, root):
    """Spread sports: one card per example game, full width: the logos and
    "BOS @ NY · 1st Quarter 28-31" once, then a row per bet (its name, its
    cells, the result line under them)."""
    head = (f'<p class="gd-game-h">{ex_logo(sp, ex["away"], root)}{ex_logo(sp, ex["home"], root)}'
            f'<span>{esc(ex["label"])}</span></p>')
    rows = ''.join(f'<div class="gd-bet-row"><span class="gd-bet-n">{esc(b["name"])}</span><div class="gd-bet-c">{ex_cells(sp, ex, b, root)}</div></div>'
                   for b in ex['bets'])
    return f'<div class="st-card gd-ex gd-game">{head}{rows}</div>'


def money(x):
    """Whole dollars: $91, $95, $67."""
    return f'${int(x + 0.5):,}'


def odds_table(ex):
    """"How to read the odds": every price in the example game, what $100
    wins and what it costs to win $100."""
    rows = ''
    for bet in ex['bets']:
        for c in bet['cells']:
            p = int(c['price'])
            win, risk = (p, 10000 / p) if p > 0 else (10000 / -p, -p)
            rows += (f'<tr><td>{esc(bet["name"])} {esc(c["text"])} {esc(c["price"])}</td>'
                     f'<td>{money(win)}</td><td>{money(risk)}</td></tr>')
    return ('<h2>How to read the odds</h2><div class="st-card gd-table"><table class="tp-table"><thead><tr>'
            '<th>Price</th><th>Risk $100, you win</th><th>To win $100, you risk</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def with_examples(out, sp, root):
    """The sport guide's "The bets" with its example games -- NHL, MLB: an
    Example card under each bet, a row per game; spread sports: a card per
    game under the list (the first quarter, then the first half) and the
    examples' notes -- then "How to read the odds" (the first example's)."""
    exs = examples(sp['key'])
    m = re.search(r'<h2>The bets</h2>(.*?)(?=<h2>|\Z)', out, re.S)
    if not exs or not m:
        return out
    sec = m.group(1)
    parts = re.split(r'(?=<h3>)', sec)
    used = False
    for i, part in enumerate(parts):
        h = re.match(r'<h3>(.*?)</h3>', part)
        bet = h and next((b for b in exs[0]['bets'] if html.unescape(h.group(1)).startswith(b['heading'])), None)
        if bet:
            parts[i] = part.rstrip() + '\n' + ex_card(sp, exs, bet['heading'], root) + '\n'
            used = True
    sec = ''.join(parts)
    if not used:
        notes = ''.join(f'<p class="gd-ex-note">{esc(ex["note"])}</p>' for ex in exs if ex.get('note'))
        sec = sec.rstrip() + '\n' + ''.join(game_card(sp, ex, root) for ex in exs) + notes + '\n'
    return out[:m.start(1)] + sec + odds_table(exs[0]) + '\n' + out[m.end(1):]


def guide_html(md, root, sp=None):
    """A guide's body: Example cards (sport guides), purple section headers,
    "Where to go next" pills, root-aware links."""
    out = daily.to_html(md)
    if sp:
        out = with_examples(out, sp, root)
    return rooted(headers(next_pills(out)), root)


def index_body(root):
    """/betting-guides/: one line and two pills, a card per sport (its
    segments in gold caps), a card per guide with its badge."""
    doc = read('index')
    intro = daily.to_html(doc[1]) if doc else ''
    pills = (f'<div class="gd-pills"><a class="gd-pill" href="{root}{INDEX_DIR}/first-segment-betting/">{badge("first-segment-betting")}'
             f'<span>New here? What is first-segment betting</span></a>'
             f'<a class="gd-pill" href="{root}{INDEX_DIR}/glossary/">{badge("glossary")}<span>Glossary</span></a></div>')
    sps = ''.join(f'<a class="gi-sport" href="{root}{sports.guide_path(sp).lstrip("/")}">{sport_tile(sp)}'
                  f'<span class="gi-txt"><b>{esc(sports.seo_name(sp))}</b><span class="gi-seg">{esc(seg_caps(sp))}</span></span>'
                  f'<span class="gi-go" aria-hidden="true">&rarr;</span></a>' for sp in sports.LAUNCHED)
    bets = ''.join(f'<a class="gi-bet" href="{root}{INDEX_DIR}/{slug}/">{badge(slug)}'
                   f'<span class="gi-txt"><b>{esc(t)}</b><span>{esc(d)}</span></span></a>' for slug, t, d in GENERAL)
    return (f'<section class="hp-sec gd-index"><h1>{esc(INDEX_H1)}</h1><div class="gd-intro">{rooted(intro, root)}{pills}</div>'
            + (f'<h2 class="gd-h">By sport</h2><div class="gi-sports">{sps}</div>' if sps else '')
            + f'<h2 class="gd-h">The bets</h2><div class="gi-bets">{bets}</div></section>')


def guide_cards(sp, root):
    """The sport's guide, then its bet guides, as the home page's cards."""
    cards = card(root + sports.guide_path(sp).lstrip('/'), sport_title(sp), f"{sp['label']} {sports.segment_summary(sp)} bets.")
    return cards + ''.join(card(f'{root}{INDEX_DIR}/{slug}/', GENERAL_BY[slug][1], GENERAL_BY[slug][2]) for slug in bet_guides(sp))


def sport_block(sp, root):
    """The Betting Guides block at the bottom of every sport page: the home
    page's cards."""
    return (f'<section class="gd-block" aria-label="Betting Guides"><h2 class="t-label">Betting Guides</h2>'
            f'<div class="hl-grid">{guide_cards(sp, root)}</div></section>')


def hub_block(sp, root):
    """A hub's Betting Guides: the home page's cards (title + one line), the
    sport's guide first, then its bet guides, and "All guides"."""
    import front
    cards = guide_cards(sp, root)
    return (f'<section class="fr-sec" id="learn"><div class="fr-head"><h2>Betting Guides</h2></div>'
            f'<div class="hl-grid">{cards}</div><div class="fr-links">{front.more_link(root + INDEX_DIR + "/", "All guides")}</div></section>')


def write(page, status, logo_svg):
    """Every guide page except the sport guides (build_site writes those in
    the sport template). `page` is home.page. Returns the pages written."""
    def save(rel, title, desc, body, noindex):
        depth = '../' * rel.count('/')
        out = page(title, desc, body.replace('__R__', depth), status, depth=depth, noindex=noindex).replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, rel), exist_ok=True)
        with open(os.path.join(ROOT, rel, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)

    doc = read('index')
    save(f'{INDEX_DIR}/', sports.page_title(INDEX_H1),
         (doc[0].get('description') if doc else None) or 'How first period, first quarter and first half bets work: moneylines, spreads, totals, BTTS, NRFI, First Five and units.',
         index_body('__R__'), False)
    n = 1
    for slug, title, _ in GENERAL + [GLOSSARY]:
        doc = glossary_doc() if slug == 'glossary' else read(slug)
        rel = f'{INDEX_DIR}/{slug}/'
        body, desc, noindex, head = article(title, doc, rel, '__R__', slug, is_glossary=slug == 'glossary')
        save(rel, head, desc, body, noindex)
        n += 1
    return n


def sport_page(sp):
    """(meta, body, noindex) for /{slug}/betting-guide/, drawn in the sport
    template (its page head carries the title)."""
    title = sport_title(sp)
    doc = read(sp['slug'])
    h1 = title   # the H1 is fixed (sports.h1); front-matter titles are for the general guides
    name = sports.seo_name(sp)
    if doc is None:
        body, desc, noindex = '', f'{COMING}.', True
    else:
        meta, md = doc
        rel = sports.guide_path(sp).lstrip('/')
        desc = meta.get('description') or daily.plain(md)[:200]
        when = updated(rel, meta['_numbers'])
        body = (f'<p class="dp-date">Updated {daily.nice_date(when)}</p><div class="dp-body">{guide_html(md, "__ROOT__/", sp)}</div>'
                + ld_json(rel, name, h1, desc, md, when))
        noindex = False
    more = ''.join(f'<a class="gd-link" href="__ROOT__/{INDEX_DIR}/{slug}/">{esc(GENERAL_BY[slug][1])} &rarr;</a>' for slug in bet_guides(sp))
    body = (f'<article class="gd-page gd-sport">{body}</article>'
            f'<section class="gd-block" aria-label="More guides"><h2 class="t-label">More guides</h2><div class="gd-links">{more}'
            f'<a class="gd-link" href="__ROOT__/{INDEX_DIR}/">All Betting Guides &rarr;</a></div></section>')
    meta = {'title': sports.page_title(h1), 'h1': esc(h1), 'desc': esc(desc), 'section': 'guide', 'crumb': crumb(name, '__ROOT__/')}
    return meta, body, noindex
