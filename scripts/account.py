"""
Account controls in the header, shared by every page (desktop and phone):
the avatar and its menu. The Sign in / Go Premium links next to it are in
scripts/nav.py; this script switches them by state (classes on <html>):

  guest:      Sign in · Go Premium; the site follows the device's light /
              dark setting
  signed in:  Go Premium · avatar (html.rtyb-signed-in)
  Premium:    avatar, plus Picks while sports.PICKS_LIVE (html.rtyb-premium)

The avatar menu: name and plan, then Profile · Plan & billing · Alerts
(Premium) · Newsletter settings · Dark mode (the switch, #themeToggle, which
each page's own script wires) · Sign out, and a gold Go Premium box for
free members.

There are no accounts yet, so the signed-in state comes from a small hook
the sign-in flow will call once it exists:

  window.rtybAccount.set({name: 'Pat D', photo: null, premium: false})
  window.rtybAccount.set(null)          // sign out

It keeps the user in localStorage ('rtyb-user'). Preview it on any page with
?user=1 (or ?user=premium); the preview isn't saved.

Every tap target is at least 44x44. CSS lives in template.html (site.css).
"""


def account_html(root):
    """The avatar and its menu; `root` prefixes the links ('/' on sport
    pages, the relative depth on the home-style pages)."""
    href = f'{root}#premium'
    return f'''<div class="acct" id="acctM">
      <div class="acct-user" hidden>
        <button class="acct-avatar" id="acctAvatar" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="acctMenu" aria-label="Account menu"><span class="acct-face" id="acctFace"></span></button>
        <div class="acct-menu" id="acctMenu" hidden>
          <div class="acct-head"><span class="acct-name" id="acctName"></span><span class="acct-plan" id="acctPlan"></span></div>
          <a class="acct-item" href="{href}">Profile</a>
          <a class="acct-item" href="{href}">Plan &amp; billing</a>
          <a class="acct-item" href="{href}">Alerts</a>
          <a class="acct-item" href="{href}">Newsletter settings</a>
          <button class="acct-item acct-dark" id="themeToggle" type="button" role="switch" aria-checked="false">Dark mode <span class="acct-switch" aria-hidden="true"></span></button>
          <button class="acct-item" id="acctSignOut" type="button">Sign out</button>
        </div>
      </div>
    </div>'''


ACCOUNT_JS = '''<script>
(function() {
  'use strict';
  var KEY = 'rtyb-user', preview = null;
  try {
    var m = /[?&]user=([^&#]*)/.exec(window.location.search);
    if (m) preview = { name: 'Test User', premium: m[1] === 'premium' };
  } catch (e) {}
  function current() {
    if (preview) return preview;
    try { var u = JSON.parse(localStorage.getItem(KEY) || 'null'); return u && u.name ? u : null; } catch (e) { return null; }
  }
  function initials(name) {
    var p = String(name).trim().split(/\\s+/);
    return ((p[0] || '').charAt(0) + (p.length > 1 ? p[p.length - 1].charAt(0) : '')).toUpperCase() || '?';
  }
  function render() {
    var box = document.getElementById('acctM');
    if (!box) return;
    var u = current(), signedIn = !!u, root = document.documentElement;
    root.classList.toggle('rtyb-signed-in', signedIn);
    root.classList.toggle('rtyb-premium', !!(u && u.premium));
    box.querySelector('.acct-user').hidden = !signedIn;
    if (!signedIn) return;   // guests switch with the sun/moon in the top bar (scripts/nav.py)
    syncDark();
    var face = document.getElementById('acctFace');
    face.innerHTML = '';
    if (u.photo) { var img = document.createElement('img'); img.src = u.photo; img.alt = ''; face.appendChild(img); }
    else face.textContent = initials(u.name);
    document.getElementById('acctName').textContent = u.name;
    document.getElementById('acctPlan').textContent = u.premium ? 'Premium' : 'Free';
    var go = document.getElementById('acctGo'); if (go) go.hidden = !!u.premium;
  }
  function isDark() {
    var t = document.documentElement.getAttribute('data-theme');
    return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  function syncDark() {
    var b = document.getElementById('themeToggle');
    if (b) b.setAttribute('aria-checked', String(isDark()));
  }
  function setMenu(open) {
    var menu = document.getElementById('acctMenu'), btn = document.getElementById('acctAvatar');
    if (!menu) return;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  window.rtybAccount = {
    get: current,
    set: function(u) {
      preview = null;
      try { if (u) localStorage.setItem(KEY, JSON.stringify(u)); else localStorage.removeItem(KEY); } catch (e) {}
      setMenu(false); render();
    }
  };
  function init() {
    render();
    var btn = document.getElementById('acctAvatar');
    if (!btn) return;
    btn.addEventListener('click', function(e) { e.stopPropagation(); setMenu(document.getElementById('acctMenu').hidden); });
    document.getElementById('acctSignOut').addEventListener('click', function() { window.rtybAccount.set(null); });
    // the page's own script flips the theme on this click; show the new state after it
    document.getElementById('themeToggle').addEventListener('click', function(e) { e.stopPropagation(); setTimeout(syncDark, 0); });
    document.addEventListener('click', function(e) { if (!e.target.closest('.acct-user')) setMenu(false); });
    document.addEventListener('keydown', function(e) { if (e.key === 'Escape') setMenu(false); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>'''
