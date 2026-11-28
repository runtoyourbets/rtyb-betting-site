"""
Streaks (scripts/streaks.py writes {slug}/streaks.json; assets/sport.js
renderStreaks draws /{sport}/streaks/; streaks.index_html is /streaks/):
Still Running against the team pages' Current streaks, a streak moving to
Run's Over when it ends, venue streaks in Tonight, Ride / Fade, NHL 2nd /
3rd Period without prices, the Trends hub cards and six-item sport row, the
Full Run flag, and no element wider than a 375px phone on /streaks/.
"""
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site  # noqa: E402
import nav  # noqa: E402
import sports  # noqa: E402
import streaks  # noqa: E402
from test_due_factor import chrome  # noqa: E402
from test_game_log import NODE, SRC, function  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
NBA = sports.BY_KEY['nba']


def game(away, home, su, gid, state='final'):
    """An NBA game; su is the away side's 1st-quarter result."""
    return {'id': gid, 'away': away, 'home': home, 'state': state, 'start': '',
            'res': {'1q': {'su': su, 'sc': [30, 20] if su == 'W' else [20, 30]}} if state == 'final' else {}}


def season(days):
    return {'teams': {'a': {}, 'b': {}, 'c': {}}, 'games': days}


class RunningTest(unittest.TestCase):
    def test_still_running_matches_the_team_pages_current_streaks(self):
        kind = {'W': 'W', 'L': 'L', 'Over': 'O', 'Under': 'U', 'YRFI': 'Y', 'NRFI': 'N'}
        for sp in sports.SPORTS:
            with open(os.path.join(ROOT, sp['slug'], 'sport.json' if sp['key'] == 'nhl' else 'data.json')) as f:
                data = json.load(f)
            doc = streaks.build(sp)
            if not doc['cur']:
                continue
            running = {(s['t'], s['k'], s['m']): (s['n'], s['kd']) for s in doc['running'] if s['v'] == 'all'}
            # the page is fixed for the day (week): a team playing today may have a newer result on its team page
            playing = set((doc['tonight'] or {}).get('playing') or [])
            segm = {x['k']: x['m'] for x in doc['segs']}
            for t, lst in (data.get('streaks') or {}).items():
                if t not in data['teams'] or t in playing:
                    continue   # college: no team page for a non-D-I / non-FBS opponent
                for x in lst:
                    if x['n'] < doc['min_run'] or x['market'] not in segm.get(x['seg'], ()):
                        continue   # College Basketball: Still Running starts at 5, no moneyline
                    with self.subTest(sp['key'], team=t, seg=x['seg'], market=x['market']):
                        self.assertEqual(running.get((t, x['seg'], x['market'])), (x['n'], kind[x['kind']]))

    def test_an_ended_streak_moves_to_runs_over_on_the_next_build(self):
        days = {f'2026-11-{10 + i}': [game('a', 'b' if i % 2 else 'c', 'W', str(i))] for i in range(5)}
        before = streaks.season_doc(NBA, season(days), True, date(2026, 11, 15))
        mine = [s for s in before['running'] if s['t'] == 'a' and s['k'] == '1q' and s['m'] == 'su' and s['v'] == 'all']
        self.assertEqual([(s['n'], s['kd']) for s in mine], [(5, 'W')])
        self.assertEqual(before['ended']['list'], [])
        days['2026-11-16'] = [game('a', 'b', 'L', '9')]
        after = streaks.season_doc(NBA, season(days), True, date(2026, 11, 17))
        mine = [s for s in after['running'] if s['t'] == 'a' and s['k'] == '1q' and s['m'] == 'su' and s['v'] == 'all']
        self.assertEqual(mine, [])     # a 1-game run isn't a streak
        ended = [e for e in after['ended']['list'] if e['t'] == 'a' and e['k'] == '1q' and e['m'] == 'su' and e['v'] == 'all']
        self.assertEqual([(e['n'], e['kd'], e['opp'], e['day']) for e in ended], [(5, 'W', 'b', '2026-11-16')])
        self.assertEqual(after['ended']['label'], 'Mon, Nov 16')

    def test_a_tie_ends_a_streak(self):
        seq = [(v, f'2026-11-{10 + i}', {}, 'away') for i, v in enumerate('WWWPWW')]
        self.assertEqual([(r['kd'], r['n'], r['alive']) for r in streaks.runs(seq)], [('W', 3, False), ('W', 2, True)])

    def test_a_home_only_streak_never_shows_tonight_on_the_road(self):
        home = {'t': 'a', 'k': '1q', 'm': 'su', 'kd': 'W', 'n': 6, 'v': 'home', 'gt': 1}
        road_game = {'2026-11-24': [game('a', 'b', None, '1', state='pre')]}
        self.assertEqual(streaks.tonight(NBA, season(road_game), [home], '2026-11-24')['games'], [])
        home_game = {'2026-11-24': [game('b', 'a', None, '1', state='pre')]}
        got = streaks.tonight(NBA, season(home_game), [home], '2026-11-24')
        self.assertEqual([s['t'] for g in got['games'] for s in g['s']], ['a'])
        # a home streak no longer than the overall one stays out (All shows the overall)
        self.assertEqual(streaks.tonight(NBA, season(home_game), [dict(home, gt=0)], '2026-11-24')['games'], [])


class PageTest(unittest.TestCase):
    def test_no_ride_fade_and_never_a_second_half_top_streak(self):
        self.assertNotIn('sk-ride', SRC)
        self.assertNotIn('best price', SRC.split('// ------------------------------------------------------------- Streaks')[1].split('// ---------------------------------------------------------------- boot')[0])
        for k in ('2h', '2p', '3p'):
            self.assertIn("'%s': 1" % k, SRC.split('var SK_TOP_SKIP = ')[1].split(';')[0])


@unittest.skipUnless(NODE, 'node is not installed')
class QuietTest(unittest.TestCase):
    def test_one_segment_and_one_market_always_picked(self):
        js = '\n'.join([function(SRC, 'skMatch'), """
var rows = [{ k: '1p', m: 'su', v: 'all' }, { k: '1p', m: 'tot', v: 'all' }, { k: 'game', m: 'su', v: 'all' }, { k: '1p', m: 'su', v: 'home', gt: 1 }, { k: '1p', m: 'su', v: 'home', gt: 0 }], out = {};
[['1p', 'su', 'all'], ['1p', 'su', 'home'], ['game', 'su', 'all']].forEach(function(f) {
  SKF = { seg: f[0], m: f[1], v: f[2] };
  out[f.join(' ')] = rows.filter(skMatch).length;
});
console.log(JSON.stringify(out));"""])
        out = subprocess.run([NODE, '-e', 'var SKF; function confTeam() { return true; }' + js], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), {'1p su all': 1, '1p su home': 2, 'game su all': 1})   # All: the overall streak only
        self.assertNotIn('SK_QUIET', SRC)
        segs = {k: ms for k, *_, ms in streaks.segments(sports.BY_KEY['nhl'])}
        self.assertEqual(list(segs), ['1p', 'game'])   # no 2nd / 3rd Period, Scored or Over 0.5
        for key in sports.COLLEGE:
            self.assertTrue(all('su' not in ms for *_, ms in streaks.segments(sports.BY_KEY[key])))

    def test_the_index_leaves_them_out(self):
        html = streaks.index_html('../')
        self.assertNotIn('Over 0.5', html)
        self.assertNotIn('scored', html)

    def test_tonight_rows_have_no_premium_tag(self):
        body = function(SRC, 'skTonight')
        self.assertNotIn('skFrTag', body)


class HubTest(unittest.TestCase):
    def test_the_three_hub_cards_link_on_every_sport(self):
        for sp in sports.SPORTS:
            for current in ('trends', 'streaks', 'due'):
                with self.subTest(sp['key'], page=current):
                    html = build_site.trends_tabs_html(sp, current)
                    hrefs = re.findall(r'href="__ROOT__([^"]+)"', html)
                    self.assertEqual(hrefs, [sports.section_path(sp, s).lstrip('/') for s in ('trends', 'streaks', 'due')])
                    self.assertEqual(re.findall(r'<span class="stc-name">(\w[\w ]*)', html), ['Trends', 'Streaks', 'Due Factor'])
                    self.assertEqual(html.count('aria-current="page"'), 1)
                    self.assertEqual(html.count('stc-go'), 2)
                    self.assertIn(f'href="__ROOT__{sports.section_path(sp, current).lstrip("/")}" aria-current="page"', html)

    def test_the_sport_row_has_six_items_on_every_sport(self):
        for sp in sports.SPORTS:
            with self.subTest(sp['key']):
                row = nav.sport_row('/', sp, 'streaks')
                self.assertEqual(re.findall(r'class="hr2-link[^"]*"[^>]*>([^<]+)<', row), ['Picks', 'Matchups', 'Odds', 'Trends', 'Stats', 'Teams'])

    def test_full_run_flag_matches_sport_js(self):
        flag = re.search(r'var PREMIUM = \{[^}]*\bfullRun: (true|false)', SRC).group(1)
        self.assertEqual(streaks.FULL_RUN_LOCKED, flag == 'true')

    def test_streaks_to_watch_links_to_the_streaks_pages(self):
        src = open(os.path.join(ROOT, 'scripts', 'front.py')).read()
        self.assertIn('section_path(top.sp, "streaks")', src)
        self.assertIn('streaks/', src)


HARNESS = """<!doctype html><meta charset="utf-8"><body><pre id="out">running</pre>
<iframe id="f" src="/streaks/index.html" style="width:375px;height:812px;border:0"></iframe><script>
var f = document.getElementById('f');
f.onload = function() {
  setTimeout(function() {
    var doc = f.contentDocument, bad = [], w = doc.documentElement.clientWidth;
    function measure(tag) {
      if (doc.documentElement.scrollWidth > w) bad.push(tag + ' page ' + doc.documentElement.scrollWidth);
      Array.prototype.forEach.call(doc.querySelectorAll('main *'), function(el) {
        var r = el.getBoundingClientRect();
        if (r.width && (r.right > w + 0.5 || r.left < -0.5)) bad.push(tag + ' ' + el.tagName + '.' + el.className + ' ' + Math.round(r.left) + '-' + Math.round(r.right));
      });
    }
    Array.prototype.forEach.call(doc.querySelectorAll('[data-skp]'), function(p) { p.click(); measure(p.getAttribute('data-skp')); });
    document.getElementById('out').textContent = JSON.stringify(bad.slice(0, 8));
  }, 300);
};
</script>"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="../assets/site.css"></head><body><main style="padding:0 16px">%s</main></body></html>"""


@unittest.skipUnless(chrome(), 'Chrome is not installed')
class PhoneWidthTest(unittest.TestCase):
    def test_nothing_wider_than_a_375px_phone_on_the_index(self):
        tmp = tempfile.mkdtemp()
        try:
            os.symlink(os.path.abspath(os.path.join(ROOT, 'assets')), os.path.join(tmp, 'assets'))
            for sp in sports.SPORTS:
                src = os.path.abspath(os.path.join(ROOT, sp['slug']))
                if os.path.isdir(src):
                    os.symlink(src, os.path.join(tmp, sp['slug']))
            os.makedirs(os.path.join(tmp, 'streaks'))
            body = streaks.index_html('../')
            with open(os.path.join(tmp, 'streaks', 'index.html'), 'w') as f:
                f.write(PAGE % body)
            with open(os.path.join(tmp, 'harness.html'), 'w') as f:
                f.write(HARNESS)

            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=tmp))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                dom = subprocess.run([chrome(), '--headless=new', '--disable-gpu', '--no-first-run', '--window-size=420,900',
                                      f'--user-data-dir={os.path.join(tmp, "profile")}', '--virtual-time-budget=30000', '--dump-dom',
                                      f'http://127.0.0.1:{srv.server_address[1]}/harness.html'],
                                     capture_output=True, text=True, timeout=180).stdout
            finally:
                srv.shutdown()
                srv.server_close()
            got = json.loads(dom.split('<pre id="out">', 1)[1].split('</pre>', 1)[0].replace('&amp;', '&'))
            self.assertEqual(got, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
