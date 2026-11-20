"""
SEO page text: content/seo/*.md (one file per index, hub and sport page;
front matter path / title / description / description_offseason / intro)
and the team pages' text, written from each team's numbers (the spec is
content/seo/_team-pages.md). seo.finish runs apply() on every built page:

  <title> + meta description  from the file (off-season: "Today" and
                              "Week {{week}}" become "[YEAR] Season", the
                              description is description_offseason)
  intro                       replaces the line under the H1
  "Updated 1:05 PM ET"        under it (index and sport pages): the build
                              that last changed the page's numbers
                              (seo_updated_log.json); Odds and Matchups:
                              the last odds pull
  About block                 the body, closed (How to read's pattern), at
                              the page bottom above Betting Guides; "## More
                              ..." links become pills, "## ... in other
                              sports" a stacked list (sports.LAUNCHED), "##
                              FAQ" FAQPage data
  JSON-LD                     FAQPage, BreadcrumbList (sport and team
                              pages), WebSite + Organization (home)

A page with no file keeps its own text ("RTYB" in titles and descriptions
becomes "Run To Your Bets"). A file whose path isn't a built page, or an
unknown token, fails the build naming the file.

Tokens: the guides' ({{nhl.1p.over:season}}, |label, empties dropped: see
guide_stats) plus {{asof}}, {{season}} ("this season" / "in the 2026
season"), {{week}}, {{season_start}} ("Wednesday, March 24"), {{date}} and
{{headline}} (Preview pages).
"""
import hashlib
import html
import json
import os
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import daily
import guide_stats
import guides
import icons
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'content', 'seo')
TEAM_SPEC = '_team-pages.md'
LOG = os.path.join(ROOT, 'seo_updated_log.json')
SEASONS = os.path.join(ROOT, 'assets', 'seasons.json')
SITE = 'Run To Your Bets'
ET = ZoneInfo('America/New_York')
MIN_TEAM = 5   # graded games before a team page gets its full About and FAQ

PAGE_NAME = {'': 'Betting', 'odds/': 'Odds', 'matchups/': 'Matchups', 'trends/': 'Trends', 'stats/': 'Stats',
             'stats/splits/': 'Splits', 'teams/': 'Teams', 'preview/': 'Preview', 'betting-guide/': 'Betting Guide'}
SEG_WORD = {'1p': 'first period', '1q': 'first quarter', '1h': 'first half', '1i': 'first inning', 'f5': 'first five'}
SEG_PLURAL = {'1p': 'first periods', '1q': 'first quarters', '1h': 'first halves', '1i': 'first innings', 'f5': 'first fives'}

esc = lambda s: html.escape('' if s is None else str(s), quote=True)


class UnknownPath(ValueError):
    pass


def rel_of(path):
    """'/nhl/odds/' -> 'nhl/odds/'; '/' -> ''."""
    p = path.strip('/')
    return p + '/' if p else ''


def files():
    """{rel: (file name, front matter, body)} for every page file."""
    out = {}
    if not os.path.isdir(DIR):
        return out
    for name in sorted(os.listdir(DIR)):
        if not name.endswith('.md') or name == TEAM_SPEC:
            continue
        with open(os.path.join(DIR, name), encoding='utf-8') as f:
            meta, body = daily.parse(f.read())
        out[rel_of(str(meta.get('path') or ''))] = (f'content/seo/{name}', meta, body)
    return out


def sport_of(rel):
    first = rel.split('/')[0]
    return next((sp for sp in sports.SPORTS if sp['slug'] == first), None)


# --------------------------------------------------------------- tokens

def states():
    try:
        with open(SEASONS, encoding='utf-8') as f:
            return json.load(f).get('sports') or {}
    except (OSError, ValueError):
        return {}


def long_date(iso):
    """'Wednesday, March 24'."""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%A, %B')} {d.day}"


def week_number(doc):
    import hub
    w = hub.current_week(doc) if doc.get('schedule') == 'week' else None
    m = re.search(r'\d+', (w or {}).get('label') or '')
    return m.group(0) if m else ''


class Context:
    """A sport's season state for the page text."""
    def __init__(self, sp, st, doc):
        self.sp, self.doc = sp, doc
        self.off = (st or {}).get('layout') == 'off'
        last = (st or {}).get('last') or ''
        self.year = last[:4] or str(doc.get('seasonLabel') or '')[:4]
        self.season = f'in the {self.year} season' if self.off else 'this season'
        opening = (st or {}).get('opening') or (st or {}).get('first')
        self.season_start = long_date(opening) if opening else 'TBA'
        self.week = week_number(doc) if not self.off else ''


_CTX = {}


def context(sp):
    if sp is None:
        return None
    if sp['key'] not in _CTX:
        _CTX[sp['key']] = Context(sp, states().get(sp['key']), guide_stats.load(sp))
    return _CTX[sp['key']]


def values(rel, ctx, base, preview_info):
    v = dict(base)
    v['season'] = ctx.season if ctx else 'this season'
    v['week'] = ctx.week if ctx else ''
    v['season_start'] = ctx.season_start if ctx else 'TBA'
    info = preview_info.get(rel) or {}
    v['date'], v['headline'] = info.get('date', ''), info.get('headline', '')
    return v


def sample_values():
    """Typical values, for checking description lengths (tests)."""
    v = {k: '59% (204-142)' for k in guide_stats.table()}
    v.update({'asof': 'Thursday, Nov 19', 'season': 'this season', 'week': '12', 'season_start': 'Wednesday, March 24',
              'date': 'Nov 20', 'headline': 'UTEP Takes Eight Straight First-Half Losses to Air Force'})
    return v


def plain(s):
    return re.sub(r'\s+', ' ', daily.plain(s)).strip()


def head_text(meta, ctx, vals, name):
    """(title, description) filled for the page."""
    title = str(meta.get('title') or '')
    desc = str(meta.get('description') or '')
    if ctx and ctx.off:
        title = re.sub(r'\b(Today|Week \{\{\s*week\s*\}\})(?= \||$)', f'{ctx.year} Season', title)
        desc = str(meta.get('description_offseason') or desc)
    fill = lambda s: plain(guide_stats.fill(s, vals, name)).replace('\x00', '')
    return fill(title), fill(desc)


# ------------------------------------------------------------- About block

def short_name(text, sp):
    for pre in ((sports.seo_name(sp), sp['label']) if sp else ()):
        if text.startswith(pre + ' '):
            return text[len(pre) + 1:]
    return text


def more_pills(out, h1s):
    """"## More ... betting": the links as pills, the short page name on
    the pill, the full name in aria-label and title."""
    def pills(m):
        links = re.findall(r'<a href="([^"]+)">(.*?)</a>', m.group(2))
        row = []
        for h, t in links:
            sp = sport_of(h.lstrip('/'))
            full = h1s.get(h.lstrip('/'), html.unescape(t))
            if h.endswith('preview/'):   # its H1 is the day's headline
                full = f'{sports.seo_name(sp)} {sports.seg_words(sp)} Betting Preview' if sp else 'First Period, Quarter & Half Betting Preview'
            row.append(f'<a class="gd-pill" href="{h}" aria-label="{esc(full)}" title="{esc(full)}">{guides.link_icon(h)}'
                       f'<span>{esc(short_name(html.unescape(t), sp))}</span></a>')
        return m.group(1) + '<div class="gd-pills">' + ''.join(row) + '</div>'
    return re.sub(r'(<h2>More [^<]*</h2>\s*)<p>(.*?)</p>', pills, out, flags=re.S)


def other_rows(out):
    """"## [Page] in other sports": one row per in-season sport (icon,
    sport name, segment + page name muted, ›); the whole row is the link."""
    live = {sp['key'] for sp in sports.LAUNCHED}

    def rows(m):
        items = []
        for h, _ in re.findall(r'<a href="([^"]+)">(.*?)</a>', m.group(2)):
            rel = h.lstrip('/')
            sp = sport_of(rel)
            if not sp or sp['key'] not in live:
                continue
            page = PAGE_NAME.get(rel[len(sp['slug']) + 1:], '')
            sub = f"{sports.seg_words(sp)} {page}".strip()
            full = f'{sports.seo_name(sp)} {sub}'
            items.append(f'<a class="seo-os" href="{h}" aria-label="{esc(full)}"><span class="seo-os-ic" aria-hidden="true">{icons.sport_icon(sp)}</span>'
                         f'<span class="seo-os-n">{esc(sports.seo_name(sp))}</span><span class="seo-os-s">{esc(sub)}</span>'
                         f'<span class="seo-os-go" aria-hidden="true">&rsaquo;</span></a>')
        return (m.group(1) + '<div class="seo-oss">' + ''.join(items) + '</div>') if items else ''
    return re.sub(r'(<h2>[^<]* in other sports</h2>\s*)<p>(.*?)</p>', rows, out, flags=re.S)


def about_html(md, root, h1s):
    """The About block: the first ## heading is the summary row."""
    m = re.match(r'\s*##\s+(.*)\n?', md)
    head, rest = (m.group(1).strip(), md[m.end():]) if m else ('About this page', md)
    out = guides.headers(other_rows(more_pills(daily.to_html(rest), h1s)))
    return (f'<details class="how-to-read seo-about"><summary><h2>{daily.inline(head)}</h2><i class="htr-caret" aria-hidden="true">&#9662;</i></summary>'
            f'<div class="gd-page"><div class="dp-body">{guides.rooted(out, root)}</div></div></details>')


def place_about(page_html, block):
    """At the page bottom: under How to read, above Betting Guides, then
    the footer. Hubs and home: their Betting Guides row moves under it."""
    if '<section class="gd-block"' in page_html:
        return page_html.replace('<section class="gd-block"', block + '\n  <section class="gd-block"', 1)
    m = re.search(r'<section class="fr-sec" id="learn">.*?</section>', page_html, re.S)
    if m:
        page_html = re.sub(r'<div class="fv-[a-z]+"></div>', '', page_html[:m.start()] + page_html[m.end():])
        block += f'<div class="seo-learn">{m.group(0)}</div>'
    i = page_html.rfind('</main>')
    return page_html[:i] + block + page_html[i:] if i >= 0 else page_html


# ------------------------------------------------------------ head pieces

def set_head(page_html, title, desc):
    page_html = re.sub(r'<title>.*?</title>', lambda m: f'<title>{esc(title)}</title>', page_html, count=1, flags=re.S)
    return re.sub(r'<meta name="description" content="[^"]*">', lambda m: f'<meta name="description" content="{esc(desc)}">', page_html, count=1)


def own_name(s):
    """RTYB -> Run To Your Bets in a title or description."""
    s = s.replace('RTYB - Run to Your Bets', SITE).replace('Run to Your Bets', SITE)
    return re.sub(r'\bRTYB\b', SITE, s)


def rename(page_html):
    page_html = re.sub(r'<title>(.*?)</title>', lambda m: f'<title>{own_name(m.group(1))}</title>', page_html, count=1, flags=re.S)
    return re.sub(r'<meta name="description" content="([^"]*)">', lambda m: f'<meta name="description" content="{own_name(m.group(1))}">', page_html, count=1)


def set_intro(page_html, intro):
    """The line under the H1 (sport pages' description paragraph)."""
    m = re.search(r'</h1>(.*?)(\n  </div>)', page_html, re.S)
    if not m:
        return page_html
    inner = m.group(1)
    p = re.search(r'\n    <p>.*?</p>', inner, re.S)
    new = (inner[:p.start()] + f'\n    <p>{intro}</p>' + inner[p.end():]) if p else inner.rstrip() + f'\n    <p>{intro}</p>'
    return page_html[:m.start(1)] + new + page_html[m.end(1):]


def set_updated(page_html, when):
    line = f'<p class="seo-upd t-price">Updated {when}</p>'
    if '<h1 class="page-title">' in page_html:
        m = re.search(r'</h1>.*?(?=\n  </div>)', page_html, re.S)
        return page_html[:m.end()] + '\n    ' + line + page_html[m.end():] if m else page_html
    m = re.search(r'</h1>.*?</div>', page_html, re.S)
    return page_html[:m.end()] + line + page_html[m.end():] if m and 'class="pv-h1"' not in page_html else page_html


def crumbs(rel, sp, team_name=None):
    base = seo_site()
    items = [('Home', base)]
    if sp:
        items.append((sports.seo_name(sp), f"{base}{sp['slug']}/"))
        sub = rel[len(sp['slug']) + 1:]
        if sub.startswith('stats/'):
            items.append(('Stats', f"{base}{sp['slug']}/stats/"))
            if sub != 'stats/':
                items.append((PAGE_NAME.get(sub, sub.strip('/').title()), base + rel))
        elif sub.startswith('teams/'):
            items.append(('Teams', f"{base}{sp['slug']}/teams/"))
            if team_name:
                items.append((team_name, base + rel))
        elif sub:
            items.append((PAGE_NAME.get(sub, sub.strip('/').title()), base + rel))
    return {'@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': u} for i, (n, u) in enumerate(items)]}


def seo_site():
    import seo
    return seo.site_url()


def ld(graph):
    data = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False).replace('</', '<\\/')
    return f'<script type="application/ld+json" data-seo-text>{data}</script>'


def home_graph():
    base = seo_site()
    return [{'@type': 'WebSite', 'name': SITE, 'url': base},
            {'@type': 'Organization', 'name': SITE, 'url': base, 'logo': f'{base}assets/share/home.jpg'}]


def faq_graph(md):
    qa = guides.faq(md)
    return [{'@type': 'FAQPage', 'mainEntity': [
        {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in qa]}] if qa else []


# ---------------------------------------------------------- Updated times

def et_time(iso):
    """'1:05 PM ET' today, else 'Nov 19, 1:05 PM ET'."""
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    clock = t.strftime('%I:%M %p').lstrip('0') + ' ET'
    return clock if t.date() == datetime.now(ET).date() else f"{t.strftime('%b')} {t.day}, {clock}"


def updated_times(now_iso):
    """{sport key: (numbers time, odds time)}; the numbers time is the
    build that last changed the sport's graded results."""
    try:
        with open(LOG, encoding='utf-8') as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = {}
    out = {}
    for sp in sports.SPORTS:
        doc = context(sp).doc
        h = hashlib.sha1(json.dumps([(g.get('id'), g.get('res')) for _, g in guide_stats.finals(doc, sp['key'])],
                                    sort_keys=True).encode()).hexdigest()
        row = log.get(sp['key'])
        if not row or row.get('hash') != h:
            log[sp['key']] = row = {'hash': h, 'updated': now_iso}
        odds = None
        try:
            with open(os.path.join(ROOT, sp['slug'], 'odds.json'), encoding='utf-8') as f:
                odds = json.load(f).get('updated')
        except (OSError, ValueError):
            pass
        out[sp['key']] = (row['updated'], odds or row['updated'])
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, indent=1, sort_keys=True)
        f.write('\n')
    return out


def norm(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(timezone.utc)


def when_for(rel, sp, times):
    odds_page = rel.rstrip('/').split('/')[-1] in ('odds', 'matchups')
    pick = 1 if odds_page else 0
    if sp:
        return et_time(times[sp['key']][pick])
    got = [times[s['key']][pick] for s in sports.LAUNCHED if s['key'] in times]
    return et_time(max(got, key=norm)) if got else None


# --------------------------------------------------------------- team text

FLIP = {'W': 'L', 'L': 'W'}

# per sport: line 1's (segment, market); the description's three markets
LINE1 = {'nhl': ('1p', 'ml'), 'mlb': ('f5', 'ml'), 'ncaab': ('1h', 'ats')}
DESC = {
    'nhl': [('moneyline', '1p', 'ml'), ('Over 1.5', '1p', 'total'), ('BTTS Yes', '1p', 'btts')],
    'mlb': [('F5 moneyline', 'f5', 'ml'), ('NRFI', '1i', 'rfi'), ('F5 Over', 'f5', 'total')],
    'ncaab': [('1H ATS', '1h', 'ats'), ('1H Over', '1h', 'total'), ('1H moneyline', '1h', 'ml')],
    'ncaaf': [('1Q ATS', '1q', 'ats'), ('1Q Over', '1q', 'total'), ('1H Over', '1h', 'total')],
}
DESC_SPREAD = [('1Q ATS', '1q', 'ats'), ('1Q Over', '1q', 'total'), ('1H ATS', '1h', 'ats')]


def bet(g, k, m, me):
    """(result W/L/T, units, kind) of team `me`'s bet, as the team page counts it."""
    r = (g.get('res') or {}).get(k)
    if not r or not r.get('sc') or r.get('na'):
        return None
    home = g.get('home') == me
    i, u = (1 if home else 0), r.get('u') or {}

    def side(x):
        if not x or x == 'NA':
            return None
        x = FLIP.get(x, x) if home else x
        return 'T' if x == 'P' else x

    def units(key, j):
        v = u.get(key)
        return v[j] if isinstance(v, list) and len(v) > j else None
    if m == 'ml':
        x = side(r.get('su'))
        return (x, units('su', i), x) if x else None
    if m == 'ats':
        x = side(r.get('ats'))
        return (x, units('ats', i), x) if x else None
    if m == 'total':
        t = {'O': 'W', 'U': 'L', 'P': 'T'}.get(r.get('tot'))
        return (t, units('tot', 0), r['tot']) if t else None
    if m == 'btts':
        b = r.get('btts')
        return ('W' if b == 'Y' else 'L', units('btts', 0), b) if b in ('Y', 'N') else None
    if m == 'rfi':
        b = r.get('rfi')
        return ('W' if b == 'N' else 'L', units('rfi', 1), b) if b in ('Y', 'N') else None
    return None


class Agg:
    def __init__(self, games, k, m, me, side='all', fav=None):
        self.w = self.l = self.t = self.priced = 0
        self.units, self.seq, self.m = 0.0, [], m
        for g in games:
            if (side == 'home' and g.get('home') != me) or (side == 'away' and g.get('away') != me):
                continue
            if fav is not None:
                f = guide_stats.favorite((g.get('odds') or {}).get(k))
                if not f or (f == ('home' if g.get('home') == me else 'away')) != fav:
                    continue
            b = bet(g, k, m, me)
            if not b:
                continue
            self.seq.append(b[2])
            self.w += b[0] == 'W'
            self.l += b[0] == 'L'
            self.t += b[0] == 'T'
            if b[1] is not None:
                self.units += b[1]
                self.priced += 1

    @property
    def gp(self):
        return self.w + self.l + self.t

    @property
    def pct(self):
        return round(100 * self.w / (self.w + self.l)) if self.w + self.l else None

    def rec(self):
        return f'{self.w}-{self.l}' + (f'-{self.t}' if self.m in ('ml', 'ats') else '')

    def rate(self):
        return f'{self.pct}% ({self.rec()})' if self.pct is not None else None

    def units_txt(self):
        return f'{self.units:+.2f} units' if self.priced else None


def league_pct(doc, k, m):
    """The market's league-wide rate (every team's side counted)."""
    w = l = 0
    for _, g in guide_stats.finals(doc, ''):
        for me in (g.get('away'), g.get('home')):
            if me in doc.get('teams', {}):
                b = bet(g, k, m, me)
                if b:
                    w += b[0] == 'W'
                    l += b[0] == 'L'
    return round(100 * w / (w + l)) if w + l else None


def over_pct(doc, k):
    n = [((g.get('res') or {}).get(k) or {}).get('tot') for _, g in guide_stats.finals(doc, '')]
    o, u = n.count('O'), n.count('U')
    return round(100 * o / (o + u)) if o + u else None


def team_name(sp, t):
    """Pro: the full name (Edmonton Oilers); college: the school (Kentucky)."""
    return t.get('short') if sp['key'] in sports.COLLEGE else t.get('name')


def place_name(sp, doc, key):
    """Next up's opponent: the city for pro (Tampa Bay), the school for college."""
    t = (doc.get('teams') or {}).get(key)
    if not t:
        return None
    if sp['key'] in sports.COLLEGE:
        return t.get('short') or t.get('name')
    name, short = t.get('name') or '', t.get('short') or ''
    return name[:-len(short)].strip() if short and name.endswith(short) and name != short else name


def code_of(sp, doc, key):
    t = (doc.get('teams') or {}).get(key)
    if t:
        return t.get('code') or key.upper()
    return (doc.get('otherCodes') or {}).get(key) or str(key).upper()


def team_dir(sp, key):
    return key.lower() if sp['key'] == 'nhl' else key


def price(p):
    return f'{p:+d}' if isinstance(p, int) else (f'{int(p):+d}' if isinstance(p, float) else '')


def streak_text(sp, k, m, kind):
    tag = ('' if m == 'rfi' else 'F5 ') if sp['key'] == 'mlb' else next(s['tag'] for s in sp['segments'] if s['key'] == k) + ' '
    if m == 'ml':
        return tag + ('wins' if kind == 'W' else 'losses')
    if m == 'ats':
        return tag + ('covers' if kind == 'W' else 'non-covers')
    if m == 'total':
        return tag + ('Over' if kind == 'O' else 'Under') + (' 1.5' if sp['key'] == 'nhl' else '')
    if m == 'btts':
        return 'BTTS ' + ('Yes' if kind == 'Y' else 'No')
    return 'YRFI' if kind == 'Y' else 'NRFI'


def markets(sp, doc):
    """[(segment, market)] the sport tracks."""
    out = []
    for seg in sp['segments']:
        for m in ('ml', 'ats', 'total', 'btts', 'rfi'):
            if any(bet(g, seg['key'], m, g.get('away')) for _, g in guide_stats.finals(doc, '')[-60:]):
                out.append((seg['key'], m))
    return out


def longest_run(sp, doc, games, me):
    best = None
    for k, m in markets(sp, doc):
        seq = Agg(games, k, m, me).seq
        if not seq or seq[-1] in ('T', 'P'):
            continue
        n = 0
        for x in reversed(seq):
            if x != seq[-1]:
                break
            n += 1
        if n >= 3 and (not best or n > best[0]):
            best = (n, streak_text(sp, k, m, seq[-1]))
    return best


def et_when(iso):
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return f"{t.strftime('%A')} {t.strftime('%I:%M %p').lstrip('0')}"


def team_doc(sp, doc, key, ctx, base_url_dirs):
    """(meta {title, description, intro}, body md, team display name) for one team page."""
    t = doc['teams'][key]
    me, T = key, team_name(sp, t)
    college = sp['key'] in sports.COLLEGE
    the = T if college else f'the {T}'
    do = 'Does' if college else 'Do'
    family = sports.FAMILY.get(sp['key'])
    k1, m1 = LINE1.get(sp['key'], ('1q', 'ats'))
    seg1 = SEG_WORD[k1]
    segs = sports.seg_words(sp).lower()
    season = ctx.season
    games = [g for _, g in sorted(((g.get('start') or '', g) for gs in (doc.get('games') or {}).values() for g in gs
                                   if me in (g.get('away'), g.get('home'))), key=lambda x: x[0])]
    graded = [g for g in games if g.get('res')]
    a1 = Agg(graded, k1, m1, me)
    few = a1.gp < MIN_TEAM
    sname = sports.seo_name(sp)
    slug = sp['slug']

    # description: three markets, the third dropped when it runs long
    parts = [(lbl, Agg(graded, k, m, me).rate()) for lbl, k, m in DESC.get(sp['key'], DESC_SPREAD)]
    parts = [f'{lbl} {r}' for lbl, r in parts if r]
    tail = 'Odds, streaks, splits and game log.'
    desc = ''
    for n in (3, 2, 1):
        if len(parts) >= n:
            desc = f"{T} {segs} record {season}: {', '.join(parts[:n])}. {tail}"
            if len(desc) <= 160:
                break
    if not parts:
        desc = f'{T} {segs} record {season}: no graded games yet. {tail[:-1]}, updated every night.'
    if len(desc) < 110:   # one market so far: say how it's graded
        desc += ' Every game graded at the closing line.'
    meta = {'title': f'{T} {sports.seg_words(sp)} Stats, Record & Trends | {SITE}', 'description': desc,
            'intro': f'{T} {segs} record, odds, streaks, splits and game log {season}.'}

    # About
    lines = []
    if ctx.off:
        verb = {'nhl': f'They won the {seg1}', 'mlb': 'They led after five'}.get(sp['key'], f'They covered the {seg1} spread')
        if sp['key'] == 'nhl':
            tot = (f'their {SEG_PLURAL["1p"]} went Over 1.5', Agg(graded, '1p', 'total', me).rate())
        elif sp['key'] == 'mlb':
            tot = (f'their {SEG_PLURAL["1i"]} stayed scoreless', Agg(graded, '1i', 'rfi', me).rate())
        else:
            tot = (f'their {SEG_PLURAL[k1]} went Over', Agg(graded, k1, 'total', me).rate())
        if a1.rate():
            s = f'Run To Your Bets tracked every {T} {seg1} {season}. {verb} {a1.rate()}'
            s += f', and {tot[0]} {tot[1]}.' if tot[1] and not few else '.'
            lines.append(s)
        lines.append(f'{ctx.year} season final. Next season starts {ctx.season_start}.')
    else:
        if a1.rate():
            u = a1.units_txt()
            if family == 'spread':
                s = f"They've covered the {seg1} spread {a1.rate()}" + (f', {u} betting them every game.' if u else '.')
            else:
                won = "They've led after five" if sp['key'] == 'mlb' else f"They've won the {seg1}"
                s = f'{won} {a1.rate()}' + (f', {u} betting them every game at the closing price.' if u else '.')
            lines.append(f'Run To Your Bets has tracked every {T} {seg1} {season}. {s}')
        if not few:
            if sp['key'] == 'nhl':
                o, b = Agg(graded, '1p', 'total', me).rate(), Agg(graded, '1p', 'btts', me).rate()
                if o and b:
                    lines.append(f'Their first periods have gone Over 1.5 {o}, and both teams have scored {b}.')
            elif sp['key'] == 'mlb':
                n, o = Agg(graded, '1i', 'rfi', me).rate(), Agg(graded, 'f5', 'total', me).rate()
                if n and o:
                    lines.append(f'Their first innings have stayed scoreless (NRFI) {n}, and their first fives have gone Over {o}.')
            elif sp['key'] == 'ncaab':
                o = Agg(graded, '1h', 'total', me).rate()
                if o:
                    lines.append(f'Their first halves have gone Over {o}.')
            else:
                q, h = Agg(graded, '1q', 'total', me).rate(), Agg(graded, '1h', 'total', me).rate()
                if q and h:
                    lines.append(f'Their first quarters have gone Over {q}; their first halves, {h}.')
        hm, rd = Agg(graded, k1, m1, me, 'home').rate(), Agg(graded, k1, m1, me, 'away').rate()
        if hm and rd:
            lines.append(f"At home they're {hm}; on the road, {rd}.")
        if not few:
            lg = league_pct(doc, k1, m1)
            if lg is not None and a1.pct is not None and abs(a1.pct - lg) >= 5:
                mk = f'the {seg1} spread' if family == 'spread' else ('the F5 moneyline' if sp['key'] == 'mlb' else f'the {seg1} moneyline')
                gap = a1.pct - lg
                lines.append(f"League-wide, {mk} is {lg}%, so they're {abs(gap)} points {'above' if gap > 0 else 'below'} average.")
            run = longest_run(sp, doc, graded, me)
            if run:
                lines.append(f'Current streak: {run[1]} ({run[0]} straight).')
            elif a1.gp:
                lines.append(f'Last 10: {Agg(graded[-10:], k1, m1, me).rec()}.')
        nxt = next((g for g in games if g.get('state') in ('pre', 'in') and not g.get('res')), None)
        if nxt:
            opp = nxt['home'] if nxt.get('away') == me else nxt['away']
            at = '@' if nxt.get('away') == me else 'vs'
            name = place_name(sp, doc, opp) or (nxt.get('homeName') if at == '@' else nxt.get('awayName')) or code_of(sp, doc, opp)
            link = f"[{name}](/{slug}/teams/{team_dir(sp, opp)}/)" if team_dir(sp, opp) in base_url_dirs else name
            lines.append(f"Next up: {at} {link}, {et_when(nxt['start'])}." if nxt.get('start') else f'Next up: {at} {link}.')
    body = [f'## Run To Your Bets: {the} in the {segs}', ' '.join(lines)]

    # Example: the last graded game in line 1's market
    last = next((g for g in reversed(graded) if bet(g, k1, m1, me)), None)
    if last:
        opp = last['home'] if last.get('away') == me else last['away']
        at = '@' if last.get('away') == me else 'vs'
        r = last['res'][k1]
        mine, theirs = (r['sc'][0], r['sc'][1]) if at == '@' else (r['sc'][1], r['sc'][0])
        o = ((last.get('odds') or {}).get(k1) or {})
        side = 'away' if at == '@' else 'home'
        code = code_of(sp, doc, me)
        if m1 == 'ml':
            p = price((o.get('ml') or {}).get(side))
            what = f'{code} ML' + (f' {p}' if p else '')
        else:
            a = (o.get('ats') or {}).get(side) or {}
            ln = a.get('line')
            what = code + (f' {ln:+g}' if isinstance(ln, (int, float)) else ' ATS') + (f" {price(a.get('price'))}" if price(a.get('price')) else '')
        res = {'W': 'won', 'L': 'lost', 'T': 'push'}[bet(last, k1, m1, me)[0]]
        seg_label = next(s['label'] for s in sp['segments'] if s['key'] == k1)
        body += ['### Example', f'Last game: {at} {code_of(sp, doc, opp)}, {seg_label} {mine}-{theirs}. {what}: {res}.']

    # FAQ
    if not few:
        qa = []
        ml = Agg(graded, k1, 'ml', me)
        if ml.rate():
            u = ml.units_txt()
            hm, rd = Agg(graded, k1, 'ml', me, 'home').rate(), Agg(graded, k1, 'ml', me, 'away').rate()
            a = f'{ml.rec()} on the moneyline ({ml.pct}%)' + (f', {u}' if u else '') + '.'
            if hm and rd:
                a += f' At home {hm}, on the road {rd}.'
            qa.append((f'What is {"the " if not college else ""}{T} {seg1} record {season}?', a))
        if sp['key'] == 'mlb':
            o, y = Agg(graded, 'f5', 'total', me), Agg(graded, '1i', 'rfi', me)
            if o.rate() and y.w + y.l:
                qa.append((f'{do} {the} go Over in the first five?',
                           f'Their first fives have gone Over {o.rate()} {season}, and their first innings have gone YRFI '
                           f'{round(100 * y.l / (y.w + y.l))}% ({y.l}-{y.w}).'))
        else:
            ko = '1p' if sp['key'] == 'nhl' else k1
            o = Agg(graded, ko, 'total', me)
            if o.rate():
                lg = over_pct(doc, ko)
                line = ' 1.5' if sp['key'] == 'nhl' else ''
                qa.append((f'{do} {the} go Over in the {SEG_WORD[ko]}?',
                           f'Their {SEG_PLURAL[ko]} have gone Over{line} {o.rate()} {season}.' + (f' The league average is {lg}%.' if lg is not None else '')))
        if family == 'spread' and a1.rate():
            fv, dg = Agg(graded, k1, 'ats', me, fav=True).rate(), Agg(graded, k1, 'ats', me, fav=False).rate()
            u = a1.units_txt()
            a = f'{a1.rate()} {season}' + (f', {u}' if u else '') + '.'
            if fv and dg:
                a += f' As a favorite, {fv}; as an underdog, {dg}.'
            qa.append((f'{do} {the} cover the {seg1} spread?', a[0].upper() + a[1:]))
        if qa:
            body.append('## FAQ')
            for q, a in qa:
                body += [f'### {q}', a]

    links = [f'[{sname} Teams](/{slug}/teams/)', f'[{sname} Trends](/{slug}/trends/)', f'[{sname} Odds](/{slug}/odds/)',
             f'[{sname} Splits](/{slug}/stats/splits/)', f'[{sname} Betting Guide](/{slug}/betting-guide/)']
    if not ctx.off:
        nxt = next((g for g in games if g.get('state') in ('pre', 'in') and not g.get('res')), None)
        if nxt:
            opp = nxt['home'] if nxt.get('away') == me else nxt['away']
            if team_dir(sp, opp) in base_url_dirs:
                links.append(f"[{team_name(sp, doc['teams'][opp])}](/{slug}/teams/{team_dir(sp, opp)}/)")
    body += [f'## More {sname} {segs} betting', ' · '.join(links)]
    return meta, '\n\n'.join(body), T


def team_pages(rels):
    """{rel: (name, meta, body, team name)} for every team page that was built."""
    out = {}
    for sp in sports.SPORTS:
        ctx = context(sp)
        doc = ctx.doc
        dirs = {r.split('/')[2] for r in rels if r.startswith(f"{sp['slug']}/teams/") and r.count('/') == 3}
        for key in doc.get('teams') or {}:
            d = team_dir(sp, key)
            if d in dirs:
                meta, body, name = team_doc(sp, doc, key, ctx, dirs)
                out[f"{sp['slug']}/teams/{d}/"] = (f'content/seo/{TEAM_SPEC} ({sp["slug"]}/{d})', meta, body, name)
    return out


# ------------------------------------------------------------------ apply

class Pass:
    """One finish() run: the files, token values and times, built once."""
    def __init__(self, rels, h1s, preview_info=None):
        self.files = files()
        unknown = [name for rel, (name, _, _) in self.files.items() if rel not in rels]
        if unknown:
            raise UnknownPath('content/seo: no built page for ' + ', '.join(unknown))
        self.teams = team_pages(rels)
        self.h1s = h1s
        self.base = guide_stats.table()
        self.preview = preview_info or {}
        self.times = updated_times(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.counts = {'title': 0, 'description': 0, 'about': 0}

    def apply(self, rel, page_html):
        page_html = rename(page_html)
        sp = sport_of(rel)
        ctx = context(sp)
        root = '../' * rel.count('/')
        graph = []
        if rel in self.teams:
            name, meta, body, tname = self.teams[rel]
            vals = values(rel, ctx, self.base, self.preview)
            body = guide_stats.fill(body, vals, name)
            page_html = set_head(page_html, meta['title'], meta['description'])
            page_html = set_intro(page_html, daily.inline(meta['intro']))
            graph += faq_graph(body) + [crumbs(rel, sp, tname)]
        elif rel in self.files:
            name, meta, body = self.files[rel]
            vals = values(rel, ctx, self.base, self.preview)
            body = guide_stats.fill(body, vals, name)
            title, desc = head_text(meta, ctx, vals, name)
            if rel.endswith('preview/') and not (self.preview.get(rel) or {}).get('headline'):
                pass   # a Preview page with no piece yet keeps its "Coming" title
            else:
                page_html = set_head(page_html, title, desc)
            if meta.get('intro'):
                page_html = set_intro(page_html, daily.inline(guide_stats.fill(str(meta['intro']), vals, name)))
            when = when_for(rel, sp, self.times)
            if when and rel:
                page_html = set_updated(page_html, when)
            graph += faq_graph(body)
            graph += home_graph() if rel == '' else [crumbs(rel, sp)] if sp else []
        else:
            return page_html
        self.counts['title'] += 1
        self.counts['description'] += 1
        self.counts['about'] += 1
        page_html = place_about(page_html, about_html(body, root, self.h1s))
        if graph:
            page_html = page_html.replace('</head>', ld(graph) + '</head>', 1)
        return page_html
