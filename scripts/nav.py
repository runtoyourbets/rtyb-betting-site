"""
The site nav, defined once for every page (home, the index pages, Betting
Guides, every sport page; admin has its own). Every list in it comes from
content/site_settings.json through sports.py (MAIN_MENU, LAUNCHED,
page_links, BOTTOM_BAR).

Desktop, row 1 (every page):
  Logo · SPORTS · MATCHUPS · ODDS · TRENDS · STATS · PICKS (gold), then on
  the right: the sun/moon switch (guests) · SIGN IN · GO PREMIUM, or the
  avatar when signed in. SPORTS opens one menu of the sports (league icon +
  name, each to its hub); the rest go to the index pages. The current one
  has a purple bar under it.
Row 2:
  home            none
  index pages     a yellow label row with the section name, then All and
                  the sports, each to that sport's page for the section
  sport pages     a yellow row with the sport's icon and name (its hub),
                  then its pages: Picks · Matchups · Odds · Trends ·
                  Stats · Teams
Phones: ☰ · Logo, then the account controls (guest: sun/moon · Sign in ·
GO PREMIUM; free: GO PREMIUM · avatar; Premium: PICKS · avatar), row 2 as
on desktop (the index sports row keeps only the sports in season), a fixed
bottom bar (sports.BOTTOM_BAR) and the ☰ menu: ALL SPORTS (the index pages
as one row of five buttons, Picks gold), SPORTS (icon + name; tapping a row
opens "[SPORT] Home →" and its pages as pills, two rows of three, all white, one sport
at a time) and MORE (Betting Guides, The Running Tab). While sports.PICKS_LIVE is False every Picks link opens the
Preview pages (/preview/, /{sport}/preview/), which light up Picks.
The avatar menu is scripts/account.py.

Styles live with the rest of the site's in template.html's <style> (the .hn,
.hr2, .hm and .bb rules), which the build writes out as assets/site.css.

`base` prefixes every link: the relative depth on the home-style pages
('', '../'), '/' on sport pages (SITE_ROOT is added at load).
"""
import html

import account
import icons
import sports

# a sport page's section -> the main-menu item it lights up
SECTION_TAB = {'games': 'matchups', 'odds': 'odds', 'trends': 'trends', 'due': 'trends', 'streaks': 'trends', 'stats': 'stats', 'picks': 'picks', 'preview': 'picks',
               'hub': 'sports', 'teams': 'sports', 'guide': 'sports'}
# the sport page each index page's sports row opens
INDEX_SECTION = {'matchups': 'games', 'odds': 'odds', 'trends': 'trends', 'stats': 'stats', 'picks': 'picks', 'preview': 'preview'}

# simple stroke icons for the bottom bar, all on a 24px grid
TAB_ICON = {
    'matchups': '<rect x="3" y="5" width="8" height="14" rx="2"/><rect x="13" y="5" width="8" height="14" rx="2"/>',
    'odds': '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    'trends': '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/>',
    'stats': '<line x1="4" y1="20" x2="20" y2="20"/><line x1="7" y1="16" x2="7" y2="12"/><line x1="12" y1="16" x2="12" y2="7"/><line x1="17" y1="16" x2="17" y2="10"/>',
    'picks': '<polygon points="12 3 14.8 8.8 21 9.7 16.5 14 17.6 20.2 12 17.3 6.4 20.2 7.5 14 3 9.7 9.2 8.8"/>',
}
SUN = ('<svg class="ht-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
       '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>')
MOON = '<svg class="ht-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'

CUR = ' aria-current="page"'


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def index_href(base, key):
    return base + sports.INDEX_FOLDERS[key]


def sport_href(base, sp, sec):
    """The sport's page for a section ('hub' = /{slug}/)."""
    if sec == 'hub':
        return f"{base}{sp['slug']}/"
    if sec == 'preview' or sec == 'picks' and not sports.PICKS_LIVE:
        path = sports.preview_path(sp)
    else:
        path = sports.picks_path(sp) if sec == 'picks' else sports.section_path(sp, sec)
    return base + path.lstrip('/')


def _pages(base, sp):
    """The sport's pages in the settings' order (sports.page_links)."""
    return [(sec, label, base + path.lstrip('/')) for sec, label, path in sports.page_links(sp)]


def _names(sp):
    """'College Basketball' on desktop, 'NCAAB' on phones."""
    if sp['menu_label'] == sp['label']:
        return esc(sp['label'])
    return f'<span class="nm-full">{esc(sp["menu_label"])}</span><span class="nm-abbr">{esc(sp["label"])}</span>'


def _sports_menu(base, sps, cur):
    items = ''.join(f'<a class="hn-sp-item" href="{base}{sp["slug"]}/">{icons.sport_icon(sp)}{esc(sp["menu_label"])}</a>' for sp in sps)
    return (f'<div class="hn-sp"><button class="hn-link hn-sp-link" type="button" aria-haspopup="true" aria-expanded="false"'
            f'{CUR if cur else ""}>{esc(dict(sports.MAIN_MENU).get("sports", "Sports"))}</button>'
            f'<div class="hn-sp-menu">{items}</div></div>')


def _phone_sport(base, sp, i):
    """A ☰ sport row: icon + name; tapping it opens its Home button and its
    pages as pills (two rows of three) right under it."""
    pills = ''.join(f'<a class="hm-pill" href="{href}">{esc(label)}</a>' for sec, label, href in _pages(base, sp))
    return (f'<div class="hm-sport"><button class="hm-row" type="button" aria-expanded="false" aria-controls="hmP{i}">'
            f'<span class="hm-name">{icons.sport_icon(sp)}{esc(sp["menu_label"])}</span></button>'
            f'<div class="hm-open" id="hmP{i}" hidden><a class="hm-home" href="{base}{sp["slug"]}/">{esc(sp["label"])} Home &rarr;</a>'
            f'<div class="hm-pills">{pills}</div></div></div>')


def _phone_all(base):
    """ALL SPORTS: the index pages as one row of five equal buttons (Picks gold)."""
    return '<div class="hm-all">' + ''.join(
        f'<a class="hm-all-btn{" gold" if key == "picks" else ""}" href="{index_href(base, key)}">{esc(label)}</a>'
        for key, label in sports.MAIN_MENU if key != 'sports') + '</div>'


def bottom_bar(base, current=None):
    tabs = ''.join(
        f'<a class="bb-tab" href="{index_href(base, key)}"{CUR if key == current else ""}>'
        f'<span class="bb-chip"><svg viewBox="0 0 24 24" aria-hidden="true">{TAB_ICON[key]}</svg><span>{esc(label)}</span></span></a>'
        for key, label in sports.BOTTOM_BAR)
    return f'<nav class="bb" aria-label="Sections">{tabs}</nav>'


def index_row(base, key, sps):
    """Row 2 on an index page: the section's name, then All and the sports.
    Phones keep only the sports in season (sports.IN_SEASON)."""
    label = dict(sports.MAIN_MENU).get(key, key.title())
    live = {s['key'] for s in sports.IN_SEASON}
    n = sum(1 for sp in sps if sp['key'] in live)
    links = f'<a class="hr2-link" href="{index_href(base, key)}"{CUR}>All</a>' + ''.join(
        f'<a class="hr2-link{"" if sp["key"] in live else " hr2-off"}" href="{sport_href(base, sp, INDEX_SECTION[key])}">{icons.sport_icon(sp)}{_names(sp)}</a>'
        for sp in sps)
    return (f'<div class="hr2"><div class="hr2-inner"><p class="hr2-label">{esc(label)}</p>'
            f'<nav class="hr2-links hr2-sports{" hr2-many" if n > 5 else ""}" aria-label="Sports">{links}</nav></div></div>')


PHONE_PAGE_NAMES = {}   # the sport row on phones: a shorter name for a page, when one needs it


def _page_name(sec, label):
    if sec not in PHONE_PAGE_NAMES:
        return esc(label)
    return f'<span class="nm-full">{esc(label)}</span><span class="nm-abbr">{esc(PHONE_PAGE_NAMES[sec])}</span>'


# pages reached through another page's hub cards light up that page
ROW_PARENT = {'preview': 'picks', 'due': 'trends', 'streaks': 'trends'}


def sport_row(base, sp, section):
    """Row 2 on a sport page: the sport (its hub), then its pages (Trends
    stays lit on Streaks and Due Factor)."""
    on = ROW_PARENT.get(section, section)
    links = ''.join(f'<a class="hr2-link" href="{href}"{CUR if sec == on else ""}>{_page_name(sec, label)}</a>'
                    for sec, label, href in _pages(base, sp))
    return (f'<div class="hr2"><div class="hr2-inner"><a class="hr2-label hr2-sport" href="{base}{sp["slug"]}/">{icons.sport_icon(sp)}{_names(sp)}</a>'
            f'<nav class="hr2-links hr2-pages" aria-label="{esc(sp["menu_label"])} pages">{links}</nav></div></div>')


def header(base, status, sport=None, section=None, home_href=None, current=None):
    """The nav bar, row 2, phone menu and bottom bar. status: [(sport, ...)]
    for the sports shown; sport/section: the sport page being shown;
    current: the index page being shown ('matchups', 'odds', 'trends',
    'stats', 'picks')."""
    home_href = home_href or base or './'
    sps = [x[0] for x in status]
    tab = SECTION_TAB.get(current, current) if current else (SECTION_TAB.get(section) if sport else None)
    desk = ''
    for key, label in sports.MAIN_MENU:
        if key == 'sports':
            desk += _sports_menu(base, sps, tab == 'sports')
        else:
            desk += (f'<a class="hn-link{" hn-gold" if key == "picks" else ""}" href="{index_href(base, key)}"'
                     f'{CUR if key == tab else ""}>{esc(label)}</a>')
    phone = ''.join(_phone_sport(base, sp, i) for i, sp in enumerate(sps))
    premium = f'{base}#premium'
    row2 = sport_row(base, sport, section) if sport else index_row(base, current, sps) if current in INDEX_SECTION else ''
    return f'''
<header class="hn">
  <div class="hn-inner">
    <button class="hn-burger" id="hnBurger" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="hnMenu">
      <span class="hb-lines" aria-hidden="true"><span></span><span></span><span></span></span><span class="hb-x" aria-hidden="true">&times;</span></button>
    <a class="brand" href="{home_href}" aria-label="RTYB home">__LOGO_SVG__</a>
    <nav class="hn-links" aria-label="Main">{desk}</nav>
    <div class="hn-right">
      <button class="hn-theme" type="button" aria-label="Switch to light mode">{SUN}{MOON}</button>
      <a class="hn-signin" href="{premium}">Sign in</a>
      <a class="hn-premium" href="{premium}">Go Premium</a>
      <a class="hn-picks-pill" href="{index_href(base, 'picks')}">Picks</a>
      {account.account_html(base)}
    </div>
  </div>
</header>{row2}
<div class="hm" id="hnMenu" hidden>
  <div class="hm-body">
    <p class="hm-label">All sports</p>
    {_phone_all(base)}
    <p class="hm-label">Sports</p>
    {phone}
    <p class="hm-label">More</p>
    <a class="hm-item" href="{base}betting-guides/">Betting Guides</a>
    <a class="hm-item" href="{premium}">The Running Tab</a>
  </div>
</div>
{bottom_bar(base, tab)}{JS}'''


# The Sports menu, the phone sheet and the guests' sun/moon switch. Signed-in
# people switch the theme in the avatar menu (scripts/account.py); each
# page's own script wires that one.
JS = '''
<script>
(function() {
  'use strict';
  var sp = document.querySelector('.hn-sp');
  if (sp) {
    var b = sp.querySelector('.hn-sp-link');
    function setSp(open) { sp.classList.toggle('open', open); b.setAttribute('aria-expanded', String(open)); }
    b.addEventListener('click', function(e) { e.stopPropagation(); setSp(!sp.classList.contains('open')); });
    document.addEventListener('click', function(e) { if (!e.target.closest('.hn-sp')) setSp(false); });
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') setSp(false); });
  }
  var menu = document.getElementById('hnMenu'), burger = document.getElementById('hnBurger');
  function setMenu(open) {
    menu.hidden = !open;
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    document.body.classList.toggle('hm-open', open);
  }
  burger.addEventListener('click', function() { setMenu(menu.hidden); });
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape' && !menu.hidden) setMenu(false); });
  menu.querySelectorAll('a').forEach(function(a) { a.addEventListener('click', function() { setMenu(false); }); });
  // one sport open at a time; tapping the open row again closes it
  var rows = menu.querySelectorAll('.hm-row');
  rows.forEach(function(b) {
    b.addEventListener('click', function() {
      var open = b.getAttribute('aria-expanded') !== 'true';
      rows.forEach(function(x) {
        var on = x === b && open;
        x.setAttribute('aria-expanded', String(on));
        x.parentNode.classList.toggle('open', on);
        document.getElementById(x.getAttribute('aria-controls')).hidden = !on;
      });
    });
  });
  // the sport row on phones fades at the right edge until it's scrolled to the end
  document.querySelectorAll('.hr2-pages').forEach(function(r) {
    function edge() { r.classList.toggle('hr2-end', r.scrollLeft + r.clientWidth >= r.scrollWidth - 2); }
    r.addEventListener('scroll', edge, { passive: true });
    window.addEventListener('resize', edge);
    edge();
  });
  // dark is the default; the choice is kept on the device
  var root = document.documentElement, tb = document.querySelector('.hn-theme');
  function label() { if (tb) tb.setAttribute('aria-label', root.getAttribute('data-theme') === 'light' ? 'Switch to dark mode' : 'Switch to light mode'); }
  label();
  // the page's own theme script (wired to the avatar menu's #themeToggle) flips and saves it
  if (tb) tb.addEventListener('click', function() { var t = document.getElementById('themeToggle'); if (t) t.click(); label(); });
})();
</script>'''

# First thing in every page's <head>: the saved theme, else dark, before
# anything paints.
THEME_HEAD = ("<script>(function(){var t='dark';try{if(localStorage.getItem('rtyb-theme')==='light')t='light';}catch(e){}"
              "document.documentElement.setAttribute('data-theme',t);})();</script>")


# ------------------------------------------------------------------ footer
# One footer on every page (sports.FOOTER). Desktop: the logo and its line
# with the Running Tab signup on the right; six link columns; the 21+ line,
# the small print, copyright and legal links. Phones: stacked, the columns
# as tap-to-open rows (closed; the links are in the HTML). Links are site
# paths made root-aware with __ROOT__ (seo.finish fills it in).

def seg_short(sp):
    """'1st Period', '1Q & 1H', 'NRFI & F5', '1H'."""
    if sp['key'] == 'nhl':
        return sp['segments'][0]['label']
    return ' & '.join(s['tag'] for s in sp['segments'])


LEARN = [('Betting Guides', ''), ('First-Segment Betting', 'first-segment-betting/'), ('Glossary', 'glossary/'),
         ('Moneyline', 'moneyline/'), ('Spread', 'spread/'), ('Totals', 'totals/'), ('NRFI & YRFI', 'nrfi-yrfi/'),
         ('Both Teams to Score', 'btts/'), ('Units', 'units/')]


def footer_columns():
    live = sports.LAUNCHED
    cols = [('Sports', [(sports.seo_name(sp), f"/{sp['slug']}/") for sp in live])]
    for sec, word in (('odds', 'Odds'), ('trends', 'Trends'), ('stats', 'Stats')):
        cols.append((word, [(f"{sports.seo_name(sp)}{'' if sp['key'] in sports.COLLEGE else ' ' + seg_short(sp)} {word}", f"/{sp['slug']}/{sec}/") for sp in live]))
    cols.append(('Learn', [(t, f'/betting-guides/{p}') for t, p in LEARN]))
    rtyb = [('Preview', '/preview/'), ('Matchups', '/matchups/')]
    if sports.PICKS_LIVE:
        rtyb.append(('Picks · Premium', '/picks/'))
    rtyb += [('The Running Tab', '#running-tab'), ('Contact', 'mailto:info@runtoyourbets.com'),
             ('Privacy', '/privacy/'), ('Terms', '/terms/')]
    cols.append(('Run To Your Bets', rtyb))
    return cols


def rooted(href):
    return '__ROOT__' + href[1:] if href.startswith('/') else href


def footer():
    cols = ''.join(
        f'<div class="sf-col"><h2 class="sf-h"><button type="button" class="sf-tog" aria-expanded="false">'
        f'<span>{esc(head)}</span><i class="sf-pm" aria-hidden="true"></i></button></h2>'
        f'<ul class="sf-links">' + ''.join(f'<li><a href="{rooted(h)}">{esc(t)}</a></li>' for t, h in links) + '</ul></div>'
        for head, links in footer_columns())
    return f'''<footer class="sf">
  <div class="sf-inner">
    <div class="sf-top">
      <div class="sf-brand"><a class="sf-logo" href="__ROOT__" aria-label="Run To Your Bets home">__LOGO_SVG__</a>
        <p class="sf-line"><span class="sf-long">First period, quarter and half betting. Odds, stats and trends for 7 sports, graded every night. Run to yours with the numbers.</span><span class="sf-short">First period, quarter and half betting. Run to yours with the numbers.</span></p></div>
      <div class="sf-signup" id="running-tab"><h2>Get the Running Tab</h2><p>Free newsletter: last night&rsquo;s results, tonight&rsquo;s spots.</p><!--signup:footer--></div>
    </div>
    <div class="sf-cols">{cols}</div>
    <div class="sf-bottom">
      <p class="sf-rg"><span class="sf-21">21+</span><span>Gambling problem? Call <a href="tel:18004262537">1-800-GAMBLER</a>. Please bet responsibly.</span></p>
      <p class="sf-small">Run To Your Bets is for information and entertainment. We don&rsquo;t take bets and we&rsquo;re not affiliated with any league, team or sportsbook. Records and units are for tracking only; past results don&rsquo;t predict future ones. Run To Your Bets may earn a commission from sportsbook links.</p>
      <div class="sf-legal"><p class="sf-copy">&copy; 2026 Run To Your Bets</p><p class="sf-meta"><a href="__ROOT__privacy/">Privacy</a> &middot; <a href="__ROOT__terms/">Terms</a> &middot; <a href="mailto:info@runtoyourbets.com">info@runtoyourbets.com</a></p></div>
    </div>
  </div>
  <script>
  (function() {{
    // phones: each column opens and closes on its own
    document.querySelectorAll('.sf-tog').forEach(function(b) {{
      b.addEventListener('click', function() {{
        var col = b.closest('.sf-col'), open = !col.classList.contains('open');
        col.classList.toggle('open', open);
        b.setAttribute('aria-expanded', open ? 'true' : 'false');
      }});
    }});
  }})();
  </script>
</footer>'''
