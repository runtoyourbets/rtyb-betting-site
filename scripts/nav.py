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
bottom bar (sports.BOTTOM_BAR) and the ☰ menu: SPORTS (a name opens the
hub, "+" its pages as pills, two rows of three) and MORE (Betting Guides,
The Running Tab). While sports.PICKS_LIVE is False every Picks link opens the
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
SECTION_TAB = {'games': 'matchups', 'odds': 'odds', 'trends': 'trends', 'stats': 'stats', 'picks': 'picks', 'preview': 'picks',
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
    pills = ''.join(f'<a class="hm-pill{" gold" if sec == "picks" else ""}" href="{href}">{esc(label)}</a>' for sec, label, href in _pages(base, sp))
    return (f'<div class="hm-sport"><div class="hm-row"><a class="hm-name" href="{base}{sp["slug"]}/">{icons.sport_icon(sp)}{esc(sp["menu_label"])}</a>'
            f'<button class="hm-plus" type="button" aria-expanded="false" aria-controls="hmP{i}" aria-label="{esc(sp["menu_label"])} pages">+</button></div>'
            f'<div class="hm-pills" id="hmP{i}" hidden>{pills}</div></div>')


def bottom_bar(base, current=None):
    tabs = ''.join(
        f'<a class="bb-tab" href="{index_href(base, key)}"{CUR if key == current else ""}>'
        f'<svg viewBox="0 0 24 24" aria-hidden="true">{TAB_ICON[key]}</svg><span>{esc(label)}</span></a>'
        for key, label in sports.BOTTOM_BAR)
    return f'<nav class="bb" aria-label="Sections">{tabs}</nav>'


def index_row(base, key, sps):
    """Row 2 on an index page: the section's name, then All and the sports.
    Phones keep only the sports in season (sports.IN_SEASON)."""
    label = dict(sports.MAIN_MENU).get(key, key.title())
    live = {s['key'] for s in sports.IN_SEASON}
    n = sum(1 for sp in sps if sp['key'] in live)
    links = f'<a class="hr2-link" href="{index_href(base, key)}"{CUR}>All</a>' + ''.join(
        f'<a class="hr2-link{"" if sp["key"] in live else " hr2-off"}" href="{sport_href(base, sp, INDEX_SECTION[key])}">{_names(sp)}</a>'
        for sp in sps)
    return (f'<div class="hr2"><div class="hr2-inner"><p class="hr2-label">{esc(label)}</p>'
            f'<nav class="hr2-links hr2-sports{" hr2-many" if n > 5 else ""}" aria-label="Sports">{links}</nav></div></div>')


def sport_row(base, sp, section):
    """Row 2 on a sport page: the sport (its hub), then its pages."""
    links = ''.join(f'<a class="hr2-link" href="{href}"{CUR if sec == section or (sec, section) == ("picks", "preview") else ""}>{esc(label)}</a>'
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
  menu.querySelectorAll('.hm-plus').forEach(function(b) {
    b.addEventListener('click', function() {
      var open = b.getAttribute('aria-expanded') !== 'true';
      b.setAttribute('aria-expanded', String(open));
      b.textContent = open ? '\\u2212' : '+';
      document.getElementById(b.getAttribute('aria-controls')).hidden = !open;
    });
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
