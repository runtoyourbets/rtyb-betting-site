"""
On Tap (was The Daily): published previews, recaps and columns.

Pieces are Markdown files with a front-matter block, in content/published/
(the admin's Publish button moves them there from content/drafts/ or
content/columns/):

  ---
  title: "NHL First Period Preview — Nov 24, 2026"
  sport: nhl            (previews and recaps; 'all' = the every-sport preview)
  kind: preview         preview | recap | column
  date: 2026-11-24
  sports: ["nba", "nhl"]   (the 'all' preview: the sports it covers)
  slug: why-the-first-period   (columns; else the file name)
  ---
  **The hook line.** Then the body...

Pages: /on-tap/ (the newest preview on top, then the past ones newest first,
with sport pills), /on-tap/{date}/ (the every-sport preview, the home
page's hero), /on-tap/{date}/{sport slug}/ (one sport's, its hub's hero),
/{sport slug}/recap/{date}/ (while RECAP is on) and /column/{slug}/.
/daily/ forwards to /on-tap/ (build_site.MOVED). Football's are weekly (the
Week Preview). The latest preview also shows at the top of the sport's
Matchups page (inject_arena).
"""
import html
import json
import os
import re
from datetime import date

import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHED = os.path.join(ROOT, 'content', 'published')
# The Morning Run (recap) is off: it isn't drafted or shown. True brings it back.
RECAP = False
ALL = 'all'   # the home page's On Tap: one preview across every sport
INDEX = 'on-tap'
INDEX_H1 = 'On Tap: Today’s First-Segment Preview'
KIND = {'recap': ('The Morning Run', 'recap'), 'preview': ('On Tap', 'preview'), 'column': ('Running Tab', 'column')}
WEEKLY_KIND = {'recap': 'Weekend Recap', 'preview': 'Week Preview'}
FOOT = '<p class="dp-21">21+ only. Gambling problem? Call 1-800-GAMBLER.</p>'


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def parse(text):
    """(front matter dict, body) of a Markdown file."""
    meta, body = {}, text
    m = re.match(r'---\n(.*?)\n---\n?', text, re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ':' not in line:
                continue
            k, v = line.split(':', 1)
            v = v.strip()
            try:
                v = json.loads(v) if v[:1] in '"[{' else v
            except ValueError:
                pass
            meta[k.strip()] = v
    return meta, body.strip()


def inline(s):
    s = esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])', r'<em>\1</em>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)', r'<a href="\2">\1</a>', s)
    return s


def to_html(md):
    """Paragraphs, headings, simple lists, bold, italic and links -- what
    the drafts and columns use."""
    out = []
    for block in re.split(r'\n\s*\n', md.strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue
        h = re.match(r'(#{2,3})\s+(.*)', lines[0])
        if h and len(lines) == 1:
            n = len(h.group(1))
            out.append(f'<h{n}>{inline(h.group(2))}</h{n}>')
        elif all(re.match(r'[-*]\s+', x) for x in lines):
            items = [inline(re.sub(r'^[-*]\s+', '', x)) for x in lines]
            out.append('<ul>' + ''.join(f'<li>{x}</li>' for x in items) + '</ul>')
        else:
            out.append(f'<p>{inline(" ".join(x.strip() for x in lines))}</p>')
    return '\n'.join(out)


def plain(md):
    return re.sub(r'[*_#`]|\[([^\]]+)\]\([^)]*\)', lambda m: m.group(1) or '', md).strip()


def hook_and_teaser(body):
    """The bold first line (the headline on cards) and the next sentence."""
    m = re.match(r'\*\*(.+?)\*\*\s*', body)
    hook = m.group(1).strip() if m else None
    rest = plain(body[m.end():] if m else body)
    first = re.match(r'(.+?[.!?])(\s|$)', rest)
    teaser = (first.group(1) if first else rest)[:200]
    return hook, teaser


def load():
    """Published pieces, newest first."""
    out = []
    if not os.path.isdir(PUBLISHED):
        return out
    for name in sorted(os.listdir(PUBLISHED)):
        if not name.endswith('.md'):
            continue
        with open(os.path.join(PUBLISHED, name), encoding='utf-8') as f:
            meta, body = parse(f.read())
        kind = meta.get('kind') or ('column' if name.startswith('column-') else None)
        if kind not in KIND or (kind == 'recap' and not RECAP):
            continue
        day = str(meta.get('date') or '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            continue
        sport = meta.get('sport') if kind != 'column' else None
        if kind != 'column' and sport not in sports.BY_KEY and not (sport == ALL and kind == 'preview'):
            continue
        slug = re.sub(r'[^a-z0-9-]+', '-', str(meta.get('slug') or name[:-3].replace('column-', '')).lower()).strip('-')
        path = (f'column/{slug}/' if kind == 'column' else f'{INDEX}/{day}/' if sport == ALL
                else f"{INDEX}/{day}/{sports.BY_KEY[sport]['slug']}/" if kind == 'preview'
                else f"{sports.BY_KEY[sport]['slug']}/{kind}/{day}/")
        covers = meta.get('sports') if isinstance(meta.get('sports'), list) else None
        hook, teaser = hook_and_teaser(body)
        out.append({'kind': kind, 'sport': sport, 'date': day, 'slug': slug, 'path': path, 'body': body, 'covers': covers,
                    'title': meta.get('title') or hook or name[:-3], 'hook': hook, 'teaser': teaser})
    out.sort(key=lambda p: (p['date'], {'column': 2, 'preview': 1, 'recap': 0}[p['kind']]), reverse=True)
    return out


def nice_date(day):
    return date.fromisoformat(day).strftime('%A, %B %-d, %Y')


def kicker(p):
    if not p['sport'] or p['sport'] == ALL:
        return KIND[p['kind']][0]
    sp = sports.BY_KEY[p['sport']]
    name = WEEKLY_KIND[p['kind']] if sp.get('schedule') == 'week' else KIND[p['kind']][0]
    return f"{name} &middot; {sp['label']}"


def card(p, href, label=None):
    return (f'<a class="hd-card dp-card" href="{href}"><span class="hd-kicker">{label or kicker(p)}</span>'
            f'<b>{esc(p["hook"] or p["title"])}</b><span class="muted">{esc(p["teaser"])}</span>'
            f'<span class="dp-more">Read the {KIND[p["kind"]][1]} &rarr;</span></a>')


def latest(pieces, kind, sport=None):
    return next((p for p in pieces if p['kind'] == kind and (sport is None or p['sport'] == sport)), None)


def home_cards(pieces):
    """Up to three cards for the home page: the newest recap, preview and column."""
    out = []
    for kind in ('recap', 'preview', 'column'):
        p = latest(pieces, kind)
        if p:
            out.append(card(p, p['path']))
    return out


def heading(p):
    """A sport's dated preview: 'NBA First Quarter & First Half Preview: Tue,
    Nov 17' (sports.h1). Other pieces keep their own title."""
    if p['kind'] != 'preview' or p['sport'] == ALL:
        return p['title']
    d = date.fromisoformat(p['date'])
    return f"{sports.h1(p['sport'], 'preview')}: {d.strftime('%a, %b')} {d.day}"


def page_title(p):
    """'[H1] | RTYB'; the every-sport preview: 'On Tap, Tue Nov 17: NBA First
    Quarter & NHL First Period Preview | RTYB'."""
    if p['kind'] != 'preview':
        return f"{p['title']} | RTYB"
    if p['sport'] != ALL:
        return sports.page_title(heading(p))
    d = date.fromisoformat(p['date'])
    keys = [k for k in (p.get('covers') or []) if k in sports.BY_KEY] or [sp['key'] for sp in sports.LAUNCHED]
    words = ' & '.join(f"{sports.BY_KEY[k]['label']} {sports.BY_KEY[k]['segments'][0]['label'].replace('1st ', 'First ')}" for k in keys)
    return f"On Tap, {d.strftime('%a %b')} {d.day}: {words} Preview | RTYB"


def list_item(p, depth):
    d = date.fromisoformat(p['date'])
    who = 'All sports' if p['sport'] == ALL else sports.BY_KEY[p['sport']]['label']
    return (f'<a class="st-card ot-item" href="{depth}{p["path"]}" data-pane="{esc(p["sport"])}">'
            f'<span class="ot-label">{esc(who)} &middot; {d.strftime("%a, %b")} {d.day}</span>'
            f'<b class="ot-item-title">{esc(p["hook"] or p["title"])}</b><span class="ot-sum">{esc(p["teaser"])}</span></a>')


def index_body(previews, depth, pills_html):
    """/on-tap/: the newest preview (the every-sport one when there is one),
    then the rest newest first, with sport pills."""
    head = (f'<div class="ix-head"><h1>{esc(INDEX_H1)}</h1><p class="lead">Our daily first period, first quarter and first half preview, '
            'every sport in season. New at 11 AM ET.</p></div>')
    if not previews:
        return (f'<section class="ix ot-index">{head}'
                '<p class="lead">The first On Tap lands at 11 AM ET on launch day.</p></section>')
    top = next((p for p in previews if p['date'] == previews[0]['date'] and p['sport'] == ALL), previews[0])
    d = date.fromisoformat(top['date'])
    hero = (f'<a class="st-card ot-card" href="{depth}{top["path"]}"><span class="ot-label">On Tap &middot; {d.strftime("%A")}, {d.strftime("%b")} {d.day}</span>'
            f'<h2 class="ot-title">{esc(top["hook"] or top["title"])}</h2><p class="ot-sum">{esc(top["teaser"])}</p>'
            f'<span class="ot-more">Read the preview &rarr;</span></a>')
    rest = [p for p in previews if p is not top]
    past = (f'<h2 class="ot-past-h">Past previews</h2><div class="ot-list">{pills_html}{"".join(list_item(p, depth) for p in rest)}</div>'
            if rest else '')
    return f'<section class="ix ot-index">{head}{hero}{past}</section>'


def write_pages(page, status, logo_svg, pieces=None, pills=None, script=''):
    """Every piece's own page, and the /on-tap/ index (noindexed while
    sports.ON_TAP_LIVE is False). `page` is home.page;
    pills(name, opts) draws the sport pills (front.pills), script switches
    them (front.FRONT_JS)."""
    pieces = load() if pieces is None else pieces
    for p in pieces:
        depth = '../' * p['path'].count('/')
        back = (f'<a href="{depth}{INDEX}/">&larr; More from On Tap</a>' if p['kind'] == 'preview'
                else f'<a href="{depth}">&larr; Back to today&rsquo;s games</a>')
        body = (f'<article class="hp-sec dp-piece"><span class="hd-kicker">{kicker(p)}</span>'
                f'<h1>{esc(heading(p))}</h1><p class="dp-date">{nice_date(p["date"])}</p>'
                f'<div class="dp-body">{to_html(p["body"])}</div>{FOOT}'
                f'<p class="dp-back">{back}</p></article>')
        desc = (p['hook'] + ' ' if p['hook'] else '') + p['teaser']
        out = page(page_title(p), desc[:300], body, status, depth=depth,
                   noindex=not sports.ON_TAP_LIVE).replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, p['path']), exist_ok=True)
        with open(os.path.join(ROOT, p['path'], 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
    previews = [p for p in pieces if p['kind'] == 'preview']
    keys = {p['sport'] for p in previews}
    opts = [('all', 'All')] + [(sp['key'], sp['label']) for sp in sports.SPORTS if sp['key'] in keys]
    pills_html = pills('Sport', opts) if pills and len(opts) > 2 else ''
    out = page(sports.page_title(INDEX_H1),
               'On Tap, RTYB’s daily preview: the first period, first quarter and first half games, trends and prices to know, for every sport in season.',
               index_body(previews, '../', pills_html) + script, status, depth='../', noindex=not sports.ON_TAP_LIVE).replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, INDEX), exist_ok=True)
    with open(os.path.join(ROOT, INDEX, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(out)
    return len(pieces)


def arena_html(pieces, sport, today):
    """The latest preview and recap for one sport, as two cards."""
    out = []
    weekly = sports.BY_KEY[sport].get('schedule') == 'week'
    for kind, when in (('preview', "today's preview"), ('recap', 'yesterday')):
        p = latest(pieces, kind, sport)
        if not p:
            continue
        name = WEEKLY_KIND[kind] if weekly else KIND[kind][0]
        label = f"{name} &middot; {when if p['date'] == today and not weekly else esc(date.fromisoformat(p['date']).strftime('%b %-d'))}"
        out.append(card(p, '/' + p['path'], label))
    return f'<div class="dp-arena">{"".join(out)}</div>' if out else ''


def inject_arena(sport_dirs, today, pieces=None):
    """Put the cards at the top of each sport's Matchups page, under its menu.
    sport_dirs: {sport: Matchups page dir}."""
    pieces = load() if pieces is None else pieces
    for sport, d in sport_dirs.items():
        path = os.path.join(ROOT, d, 'index.html')
        cards = arena_html(pieces, sport, today)
        if not cards or not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            page = f.read()
        if 'class="dp-arena"' in page:
            continue
        m = re.search(r'<div class="hr2">.*?</nav></div></div>', page, re.S)
        if not m:
            continue
        page = page[:m.end()] + f'<div class="dp-arena-wrap">{cards}</div>' + page[m.end():]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
