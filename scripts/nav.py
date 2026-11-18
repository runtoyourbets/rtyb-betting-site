"""
The site nav, defined once for every page (home, the index pages, On Tap,
Betting Guides and every sport page; admin has its own).

Desktop, left to right:
  Logo · NHL · NBA · NCAAB · NFL · NCAAF (the sports in season; hovering one
  opens its pages, clicking it opens its hub; on touch screens the first tap
  opens the menu, the second goes to the hub) · divider · Matchups · Odds ·
  Trends · On Tap (the every-sport index pages) · Picks (Premium members,
  only while sports.PICKS_LIVE), then on the right:
    guest:          Sign in · Go Premium
    signed in:      Go Premium · avatar
    Premium:        avatar
Phones: ☰ · Logo, then the same account controls (Premium: Picks, gold
outline, while PICKS_LIVE), a fixed bottom bar (Matchups · Odds · Trends ·
On Tap) and the ☰ menu: SPORTS (each sport's name opens its hub, "+" its
pages as pills, 3 to a row) and MORE (Betting Guides, The Running Tab).
The avatar menu is scripts/account.py.

Styles live with the rest of the site's in template.html's <style> (the .hn,
.hm and .bb rules), which the build writes out as assets/site.css.

`base` prefixes every link: the relative depth on the home-style pages
('', '../'), '/' on sport pages (SITE_ROOT is added at load).
"""
import html

import account
import icons
import sports

# the every-sport index pages: (key, label, folder)
INDEX = [('matchups', 'Matchups', 'matchups/'), ('odds', 'Odds', 'odds/'),
         ('trends', 'Trends', 'trends/'), ('on-tap', 'On Tap', 'on-tap/')]
# a sport page's section -> the bottom-bar tab it lights up
SECTION_TAB = {'games': 'matchups', 'odds': 'odds', 'trends': 'trends'}

# simple stroke icons for the bottom bar
TAB_ICON = {
    'matchups': '<rect x="3" y="6" width="11" height="14" rx="2"/><path d="M8 4h11a2 2 0 0 1 2 2v12"/>',
    'odds': '<line x1="6" y1="20" x2="6" y2="13"/><line x1="12" y1="20" x2="12" y2="8"/><line x1="18" y1="20" x2="18" y2="4"/>',
    'trends': '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="15 7 21 7 21 13"/>',
    'on-tap': '<path d="M6 4h12l-1.5 16a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1z"/><line x1="6.6" y1="9" x2="17.4" y2="9"/>',
}


CUR = ' aria-current="page"'


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def links(base):
    """[(label, href)] for the index pages after the sports."""
    return [(label, base + folder) for _, label, folder in INDEX]


def _pages(base, sp):
    """The sport's pages in the site order (sports.page_links)."""
    return [(sec, label, base + path.lstrip('/')) for sec, label, path in sports.page_links(sp)]


def _sport_menu(base, sp, cur):
    items = ''
    for sec, label, href in _pages(base, sp):
        items += f'<a class="hn-sp-item{" gold" if sec == "picks" else ""}" href="{href}">{esc(label)}</a>'
        if sec == 'picks':
            items += f'<a class="hn-sp-item" href="{base}#premium">Premium</a>'
    hub = f"{base}{sp['slug']}/"
    return (f'<div class="hn-sp"><a class="hn-link hn-sp-link" href="{hub}" aria-haspopup="true"{CUR if cur else ""}>{esc(sp["label"])}</a>'
            f'<div class="hn-sp-menu">{items}</div></div>')


def _phone_sport(base, sp, i):
    pills = ''.join(f'<a class="hm-pill{" gold" if sec == "picks" else ""}" href="{href}">{esc(label)}</a>' for sec, label, href in _pages(base, sp))
    return (f'<div class="hm-sport"><div class="hm-row"><a class="hm-name" href="{base}{sp["slug"]}/">{icons.sport_icon(sp)}{esc(sp["label"])}</a>'
            f'<button class="hm-plus" type="button" aria-expanded="false" aria-controls="hmP{i}" aria-label="{esc(sp["label"])} pages">+</button></div>'
            f'<div class="hm-pills" id="hmP{i}" hidden>{pills}</div></div>')


def bottom_bar(base, current=None):
    tabs = ''.join(
        f'<a class="bb-tab" href="{base}{folder}"{CUR if key == current else ""}>'
        f'<svg viewBox="0 0 24 24" aria-hidden="true">{TAB_ICON[key]}</svg><span>{esc(label)}</span></a>'
        for key, label, folder in INDEX)
    return f'<nav class="bb" aria-label="Sections">{tabs}</nav>'


def header(base, status, sport=None, section=None, home_href=None, current=None):
    """The nav bar, phone menu and bottom bar. status: [(sport, ...)] for the
    sports in season; sport/section: the sport page being shown; current:
    the index page being shown ('matchups', 'odds', 'trends', 'on-tap')."""
    home_href = home_href or base or './'
    sps = [x[0] for x in status]
    cur_key = (sport or {}).get('key')
    current = current or (SECTION_TAB.get(section) if sport else None)
    desk = ''.join(_sport_menu(base, sp, sp['key'] == cur_key) for sp in sps)
    desk += '<span class="hn-div" aria-hidden="true"></span>'
    desk += ''.join(f'<a class="hn-link" href="{base}{folder}"{CUR if key == current else ""}>{esc(label)}</a>'
                    for key, label, folder in INDEX)
    picks = sports.PICKS_LIVE
    if picks:
        desk += f'<a class="hn-link hn-picks" href="{base}picks/">Picks</a>'
    phone = ''.join(_phone_sport(base, sp, i) for i, sp in enumerate(sps))
    premium = f'{base}#premium'
    return f'''
<header class="hn">
  <div class="hn-inner">
    <button class="hn-burger" id="hnBurger" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="hnMenu">
      <span class="hb-lines" aria-hidden="true"><span></span><span></span><span></span></span><span class="hb-x" aria-hidden="true">&times;</span></button>
    <a class="brand" href="{home_href}" aria-label="RTYB home">__LOGO_SVG__</a>
    <nav class="hn-links" aria-label="Main">{desk}</nav>
    <div class="hn-right">
      <a class="hn-signin" href="{premium}">Sign in</a>
      <a class="hn-premium" href="{premium}">Go Premium</a>
      {f'<a class="hn-picks-pill" href="{base}picks/">Picks</a>' if picks else ''}
      {account.account_html(base)}
    </div>
  </div>
</header>
<div class="hm" id="hnMenu" hidden>
  <div class="hm-body">
    <p class="hm-label">Sports</p>
    {phone}
    <p class="hm-label">More</p>
    <a class="hm-item" href="{base}betting-guides/">Betting Guides</a>
    <a class="hm-item" href="{premium}">The Running Tab</a>
  </div>
</div>
{bottom_bar(base, current)}{JS}'''


# Menus and the phone sheet. The theme switch lives in the avatar menu
# (scripts/account.py); each page's own script wires it.
JS = '''
<script>
(function() {
  'use strict';
  // desktop sport menus: hover (CSS); touch screens: the first tap opens the
  // menu, the second follows the link to the hub
  var touch = window.matchMedia && window.matchMedia('(hover: none)').matches;
  var sps = document.querySelectorAll('.hn-sp');
  function closeAll(except) { sps.forEach(function(s) { if (s !== except) s.classList.remove('open'); }); }
  sps.forEach(function(s) {
    s.querySelector('.hn-sp-link').addEventListener('click', function(e) {
      if (!touch || s.classList.contains('open')) return;
      e.preventDefault(); closeAll(s); s.classList.add('open');
    });
  });
  document.addEventListener('click', function(e) { if (!e.target.closest('.hn-sp')) closeAll(); });
  var menu = document.getElementById('hnMenu'), burger = document.getElementById('hnBurger');
  function setMenu(open) {
    menu.hidden = !open;
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    document.body.classList.toggle('hm-open', open);
  }
  burger.addEventListener('click', function() { setMenu(menu.hidden); });
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape') { if (!menu.hidden) setMenu(false); closeAll(); } });
  menu.querySelectorAll('a').forEach(function(a) { a.addEventListener('click', function() { setMenu(false); }); });
  menu.querySelectorAll('.hm-plus').forEach(function(b) {
    b.addEventListener('click', function() {
      var open = b.getAttribute('aria-expanded') !== 'true';
      b.setAttribute('aria-expanded', String(open));
      b.textContent = open ? '\\u2212' : '+';
      document.getElementById(b.getAttribute('aria-controls')).hidden = !open;
    });
  });
})();
</script>'''
