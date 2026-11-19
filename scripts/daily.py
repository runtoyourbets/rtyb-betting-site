"""
Published pieces: previews, recaps and columns (Markdown with front matter).

Pieces are Markdown files with a front-matter block, in content/published/
(the admin's Publish button moves them there from content/drafts/ or
content/columns/):

  ---
  title: "NHL First Period Betting Preview — Nov 24, 2026"
  sport: nhl            (previews and recaps; 'all' = the every-sport preview)
  kind: preview         preview | recap | column
  date: 2026-11-24
  sports: ["nba", "nhl"]   (the 'all' preview: the sports it covers)
  lead: nba:401910018   (previews: the lead game, from the admin's dropdown)
  slug: why-the-first-period   (columns; else the file name)
  ---

Previews are Preview's pages (scripts/preview.py: /preview/ and
/{sport}/preview/, was On Tap). This file writes the others:
/column/{slug}/ and /{sport slug}/recap/{date}/ (while RECAP is on).
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
ALL = 'all'   # the home page's Preview: one across every sport
INDEX = 'preview'
KIND = {'recap': ('The Morning Run', 'recap'), 'preview': ('Preview', 'preview'), 'column': ('Running Tab', 'column')}
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
                else f"{sports.BY_KEY[sport]['slug']}/{INDEX}/{day}/" if kind == 'preview'
                else f"{sports.BY_KEY[sport]['slug']}/{kind}/{day}/")
        covers = meta.get('sports') if isinstance(meta.get('sports'), list) else None
        hook, teaser = hook_and_teaser(body)
        out.append({'kind': kind, 'sport': sport, 'date': day, 'slug': slug, 'path': path, 'body': body, 'covers': covers,
                    'title': meta.get('title') or hook or name[:-3], 'hook': hook, 'teaser': teaser, 'lead': meta.get('lead'),
                    'boxes': {k: meta[k] for k in ('stat_of_night', 'league_trend', 'edge_play') if isinstance(meta.get(k), dict)}})
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


def page_title(p):
    return f"{p['title']} | RTYB"


def write_pages(page, status, logo_svg, pieces=None):
    """Every column's and recap's own page (previews: scripts/preview.py).
    `page` is home.page."""
    pieces = [p for p in (load() if pieces is None else pieces) if p['kind'] != 'preview']
    for p in pieces:
        depth = '../' * p['path'].count('/')
        body = (f'<article class="hp-sec dp-piece"><span class="hd-kicker">{kicker(p)}</span>'
                f'<h1>{esc(p["title"])}</h1><p class="dp-date">{nice_date(p["date"])}</p>'
                f'<div class="dp-body">{to_html(p["body"])}</div>{FOOT}'
                f'<p class="dp-back"><a href="{depth}">&larr; Back to today&rsquo;s games</a></p></article>')
        desc = (p['hook'] + ' ' if p['hook'] else '') + p['teaser']
        out = page(page_title(p), desc[:300], body, status, depth=depth).replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, p['path']), exist_ok=True)
        with open(os.path.join(ROOT, p['path'], 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
    return len(pieces)
