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
after the page: index.md, glossary.md, first-segment-betting.md,
moneyline.md, ..., and nhl.md, nba.md ... for the sport guides. Front matter:

  ---
  title: "How Moneyline Bets Work"      (optional, general guides only: the
                                        sport guides' H1 is fixed, sports.h1)
  description: "One or two sentences for search and share cards."
  updated: 2026-11-20
  ---
  Body in Markdown: paragraphs, ## and ### headings, - lists, **bold**,
  *italic* and [links](/nhl/odds/).

The glossary is built from the Live "Markets & terms" entries in
content/definitions.json (the admin's Definitions tab): each term is a
"## Term" heading, anchored by the term in lowercase with dashes ("## 3-Way
Moneyline" -> #3-way-moneyline). Until a page's file exists it shows its title and "Guide
coming this week" and is noindexed.

Every sport page ends with a small Betting Guides block (sport_block): the
sport's guide and two or three bet-type guides for its markets.
"""
import html
import os
import re

import daily
import definitions
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, 'content', 'betting-guides')
INDEX_DIR = 'betting-guides'
INDEX_H1 = f'{sports.CROSS_WORDS} Betting Guides'

# (slug, default title, one line for the cards)
GENERAL = [
    ('first-segment-betting', 'First-Segment Betting', 'Why bet the 1st period, quarter, half, inning or first five.'),
    ('moneyline', 'Moneyline', 'Picking the winner, and what the price means.'),
    ('spread', 'Spread', 'Covering, pushes and the -110 price.'),
    ('totals', 'Totals', 'Overs, unders and whole-number pushes.'),
    ('btts', 'Both Teams to Score', 'Will each team score in the opening segment?'),
    ('3-way-moneyline', '3-Way Moneyline', 'Home, away or tie, with the tie as its own bet.'),
    ('nrfi-yrfi', 'NRFI / YRFI', 'A run in the 1st inning, or not.'),
    ('first-five', 'First Five', 'Baseball’s first five innings, before the bullpens.'),
    ('units', 'Units', 'How RTYB counts profit and loss.'),
]
GENERAL_BY = {g[0]: g for g in GENERAL}
GLOSSARY = ('glossary', 'Betting Glossary', 'Every term on the site, A to Z.')

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


def read(name):
    """(front matter, body) of content/betting-guides/{name}.md, or None."""
    path = os.path.join(CONTENT, f'{name}.md')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return daily.parse(f.read())


GLOSSARY_IDS = {}


def glossary_doc():
    """The glossary from the Live Markets & terms entries in the admin's
    Definitions tab (content/definitions.json), A to Z, one ## per term; the
    long definition, when there is one, follows the short one. None while
    no term is Live (the page says it's coming)."""
    terms = definitions.glossary_terms()
    GLOSSARY_IDS.clear()
    GLOSSARY_IDS.update({name: slug for slug, name, _, _ in terms})   # #btts, #units: the "i" boxes link here
    if not terms:
        return None
    body = 'Every betting term RTYB uses, A to Z. The ⓘ next to a market on any page links to its entry here.\n\n' + '\n\n'.join(f'## {name}\n\n{short}' + (f'\n\n{long}' if long else '') for _, name, short, long in terms)
    return ({'title': GLOSSARY[1], 'description': 'Every betting term on RTYB, A to Z: ' + ', '.join(t[1] for t in terms[:6]) + '…'}, body)


def glossary_html(md):
    """The glossary body: every '## Term' heading gets its anchor."""
    out = daily.to_html(md)
    def head(m):
        name = html.unescape(re.sub('<[^>]+>', '', m.group(1)))
        return f'<h2 id="{GLOSSARY_IDS.get(name) or anchor(name)}">{m.group(1)}</h2>'
    return re.sub(r'<h2>(.*?)</h2>', head, out)


def article(title, doc, kicker, back_href, is_glossary=False):
    """(body html, description, noindex) for one guide page."""
    if doc is None:
        return (f'<article class="hp-sec gd-page"><span class="hd-kicker">{kicker}</span><h1>{esc(title)}</h1>'
                f'<p class="lead">{COMING}.</p><p class="gd-back"><a href="{back_href}">&larr; All Betting Guides</a></p></article>',
                f'{title}: {COMING.lower()} from RTYB.', True)
    meta, body = doc
    content = glossary_html(body) if is_glossary else daily.to_html(body)
    updated = str(meta.get('updated') or '')
    when = (f'<p class="dp-date">Updated {daily.nice_date(updated)}</p>'
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', updated) else '')
    return (f'<article class="hp-sec gd-page"><span class="hd-kicker">{kicker}</span><h1>{esc(meta.get("title") or title)}</h1>{when}'
            f'<div class="dp-body">{content}</div><p class="gd-back"><a href="{back_href}">&larr; All Betting Guides</a></p></article>',
            meta.get('description') or daily.plain(body)[:200], False)


def card(href, title, line):
    return f'<a class="hl-card" href="{href}"><b>{esc(title)}</b><span>{esc(line)}</span></a>'


def index_body(root):
    """/betting-guides/: the general guides, every sport's guide, the glossary."""
    doc = read('index')
    intro = daily.to_html(doc[1]) if doc else ('<p class="lead">How first period, first quarter, first half, first inning and '
                                                 'first five bets work, and how RTYB counts them.</p>')
    gen = ''.join(card(f'{root}{INDEX_DIR}/{slug}/', t, d) for slug, t, d in GENERAL)
    sps = ''.join(card(root + sports.guide_path(sp).lstrip('/'), sport_title(sp), f"{sp['label']} {sports.segment_summary(sp)} bets.")
                  for sp in sports.LAUNCHED)
    return (f'<section class="hp-sec gd-index"><h1>{esc(INDEX_H1)}</h1>{intro}'
            f'<h2 class="gd-h">The basics</h2><div class="hl-grid">{gen}</div>'
            + (f'<h2 class="gd-h">By sport</h2><div class="hl-grid">{sps}</div>' if sps else '')
            + f'<h2 class="gd-h">Glossary</h2><div class="hl-grid">{card(f"{root}{INDEX_DIR}/glossary/", GLOSSARY[1], GLOSSARY[2])}</div></section>')


def sport_block(sp, root):
    """The small Betting Guides block at the bottom of every sport page."""
    links = [(root + sports.guide_path(sp).lstrip('/'), sport_title(sp))]
    links += [(f'{root}{INDEX_DIR}/{slug}/', GENERAL_BY[slug][1]) for slug in bet_guides(sp)]
    items = ''.join(f'<a class="gd-link" href="{h}">{esc(t)} &rarr;</a>' for h, t in links)
    return (f'<section class="gd-block" aria-label="Betting Guides"><h2 class="t-label">Betting Guides</h2>'
            f'<div class="gd-links">{items}</div></section>')


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
        body, desc, noindex = article(title, doc, 'Betting Guides', '__R__' + INDEX_DIR + '/', is_glossary=slug == 'glossary')
        save(f'{INDEX_DIR}/{slug}/', f'{title} | RTYB Betting Guides', desc, body, noindex)
        n += 1
    return n


def sport_page(sp):
    """(meta, body, noindex) for /{slug}/betting-guide/, drawn in the sport
    template (its page head carries the title)."""
    title = sport_title(sp)
    doc = read(sp['slug'])
    if doc is None:
        body, desc, noindex = '', f'{COMING}.', True
        h1 = title
    else:
        meta, md = doc
        h1 = title   # the H1 is fixed (sports.h1); front-matter titles are for the general guides
        updated = str(meta.get('updated') or '')
        when = (f'<p class="dp-date">Updated {daily.nice_date(updated)}</p>'
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', updated) else '')
        body, desc, noindex = f'{when}<div class="dp-body">{daily.to_html(md)}</div>', meta.get('description') or daily.plain(md)[:200], False
    more = ''.join(f'<a class="gd-link" href="/{INDEX_DIR}/{slug}/">{esc(GENERAL_BY[slug][1])} &rarr;</a>' for slug in bet_guides(sp))
    body = (f'<article class="gd-page gd-sport">{body}</article>'
            f'<section class="gd-block" aria-label="More guides"><h2 class="t-label">More guides</h2><div class="gd-links">{more}'
            f'<a class="gd-link" href="/{INDEX_DIR}/">All Betting Guides &rarr;</a></div></section>')
    meta = {'title': sports.page_title(h1), 'h1': esc(h1), 'desc': esc(desc), 'section': 'guide'}
    return meta, body, noindex
