"""
Due Factor v2 (scripts/due_factor.py writes {slug}/due.json; assets/sport.js
renderDue draws the page): the counts, the calendar against the Daily
table, Weekly only for NFL / NCAAF, the off-season (MLB opens on 2026's
last month, the note, no Today cell), the Full Run lock, the strip flag,
and no element wider than a 375px phone on any view.
"""
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import due_factor as df  # noqa: E402
import nav  # noqa: E402
import sports  # noqa: E402
from test_game_log import NODE, SRC, function  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TODAY = date(2026, 11, 23)
DOCS = {}


def doc(key):
    if key not in DOCS:
        DOCS[key] = df.build(sports.BY_KEY[key])
    return DOCS[key]


def game(su=None, ats=None, tot=None, odds=None, **kw):
    return dict({'state': 'final', 'res': {'1q': {'su': su, 'ats': ats, 'tot': tot, 'sc': [10, 12]}},
                 'odds': {'1q': odds or {}}}, **kw)


class CountTest(unittest.TestCase):
    def test_counts_by_hand(self):
        sp = sports.BY_KEY['nba']
        ml = {'ml': {'away': 120, 'home': -140}, 'total': {'line': 55.5}, 'ats': {'line': 1.5}}
        games = [('2026-11-20', game('W', 'W', 'O', ml)), ('2026-11-20', game('L', 'L', 'U', ml)),
                 ('2026-11-20', game('T', 'P', 'P', ml)), ('2026-11-21', game('W', 'L', 'O', {}))]
        c = df.season_counts(sp, {}, games)['1q']
        self.assertEqual(c['home_ml']['d'], {'2026-11-20': [1, 1, 1]})       # the game with no line is out
        self.assertEqual(c['fav_ml']['d'], {'2026-11-20': [1, 1, 1]})        # home is the favorite
        self.assertEqual(c['ou']['d'], {'2026-11-20': [1, 1, 1]})
        self.assertNotIn('ties', c)                                           # no Ties market (Chris, Nov 26)

    def test_every_segment_and_market_from_the_spec(self):
        want = {'nhl': [('1p', 0, ['home_ml', 'fav_ml', 'ou', 'btts']), ('game', 1, ['home_ml', 'fav_ml', 'pl', 'ou', 'ot']),
                        ('2p', 1, ['win', 'o05', 'o15']), ('3p', 1, ['win', 'o05', 'o15'])],
                'mlb': [('1i', 0, ['nrfi']), ('f5', 0, ['home_ml', 'fav_ml', 'rl', 'ou']), ('game', 1, ['home_ml', 'fav_ml', 'rl', 'ou'])],
                'ncaab': [('1h', 0, ['home_ats', 'fav_ats', 'ou', 'home_ml', 'fav_ml']),
                          ('game', 1, ['home_ats', 'fav_ats', 'ou', 'home_ml', 'fav_ml', 'ot']), ('2h', 1, ['home_ats', 'fav_ats', 'ou', 'home_ml', 'fav_ml'])]}
        for key in ('nba', 'wnba', 'nfl', 'ncaaf'):
            want[key] = [('1q', 0, want['ncaab'][0][2])] + want['ncaab']
        for key, segs in want.items():
            with self.subTest(key):
                got = [(k, int(fr), [m.id for m in ms]) for k, _, fr, ms in df.segments(sports.BY_KEY[key])]
                self.assertEqual(got, segs)

    def test_real_data_every_market_of_every_season(self):
        for sp in sports.SPORTS:
            d = doc(sp['key'])
            with self.subTest(sp['key']):
                self.assertTrue(d['seasons'])
                for s in d['seasons']:
                    for seg in d['segs']:
                        for m in seg['m']:
                            self.assertIn(m['id'], s['c'][seg['k']])
        self.assertEqual(doc('nfl')['weekly'], True)
        self.assertEqual(doc('nba')['weekly'], False)


class PageTest(unittest.TestCase):
    def test_every_sport_gets_the_page_reached_from_the_trends_hub(self):
        for sp in sports.SPORTS:
            with self.subTest(sp['key']), mock.patch.object(df, 'write_data', df.build):
                self.assertNotIn('due', [s for s, _, _ in sports.page_links(sp)])
                body = df.page_body(sp, TODAY)
                self.assertIn('<div id="sportApp" data-section="due">', body)
                self.assertTrue(df.page_meta(sp)['title'].startswith(f'{sports.seo_name(sp)} Due Factor: {sports.seg_words(sp)} Hot and Cold Trends'))
        self.assertEqual(nav.SECTION_TAB['due'], 'trends')

    def test_off_season_note(self):
        mlb = sports.BY_KEY['mlb']
        with mock.patch.dict(sports.SETTINGS['seasons']['mlb'], {'OPENING_DAY': '2027-03-26'}):
            self.assertEqual(df.off_note(mlb, doc('mlb'), TODAY),
                             'MLB is in the off-season. Showing the 2026 season (final). Opening Day: Fri, Mar 26, 2027')
        with mock.patch.dict(sports.SETTINGS['seasons']['mlb'], {'OPENING_DAY': ''}):
            self.assertEqual(df.off_note(mlb, doc('mlb'), TODAY),
                             'MLB is in the off-season. Showing the 2026 season (final). Next season: spring 2027')
        self.assertEqual(df.off_note(sports.BY_KEY['nhl'], doc('nhl'), TODAY), '')
        self.assertEqual(doc('mlb')['seasons'][0]['label'], '2026')
        self.assertFalse(doc('mlb')['seasons'][0]['cur'])

    def test_subtitle_week_by_week_for_weekly_sports(self):
        for sp in sports.SPORTS:
            desc = df.page_meta(sp)['desc']
            self.assertEqual('day by day' in desc, sp.get('schedule') != 'week', sp['key'])
            self.assertIn('week by week', desc)

    def test_short_phone_labels(self):
        got = {sp['key']: [m.out()['s'] for m in df.segments(sp)[0][3]] for sp in (sports.BY_KEY['nhl'], sports.BY_KEY['nba'])}
        self.assertEqual(got['nhl'], ['ML H/A', 'ML F/D', 'O/U 1.5', 'BTTS'])
        self.assertEqual(got['nba'], ['Spread H/A', 'Spread F/D', 'O/U', 'ML H/A', 'ML F/D'])

    def test_strip_off_renders_nothing(self):
        self.assertFalse(sports.DUE_STRIP)
        self.assertEqual(df.strip({}, TODAY, ''), '')
        with mock.patch.object(sports, 'DUE_STRIP', True):
            self.assertIsNone(df.strip_item(sports.BY_KEY['mlb'], TODAY))   # never an off-season sport


@unittest.skipUnless(NODE, 'node is not installed')
class ViewTest(unittest.TestCase):
    FUNCS = ('esc', 'dfAdd', 'dfSum', 'dfRate', 'dfRec', 'dfShift', 'dfDow', 'dfShort', 'dfDayLabel', 'dfGameDays', 'dfTint', 'dfDayTint',
             'dfDaily', 'dfWeekly', 'dfMonths', 'dfMonth', 'dfWins', 'dfSummary', 'dfPeriod', 'dfViews', 'dfDefaultMonth', 'dfSegOf',
             'dfBar', 'dfCalendar', 'premiumLocked')

    def run_js(self, body, due, premium='{ fullRun: false }'):
        js = ("var ROOT = '/', IS_PREMIUM = false, PREMIUM = %s, FR_LOCK = '<svg class=\"fr-lock\"></svg>', DUE = %s;\n"
              "var DF_TINT = { win: 'df-win', dim: 'df-dim', warm: 'df-warm', cool: 'df-cool' };\n"
              "var DF_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];\n"
              % (premium, json.dumps(due)) + '\n'.join(function(SRC, n) for n in self.FUNCS) + '\n' + body)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
            f.write(js)
        try:
            out = subprocess.run([NODE, f.name], capture_output=True, text=True)
        finally:
            os.unlink(f.name)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_calendar_day_records_match_the_daily_table(self):
        for key in ('nhl', 'nba', 'mlb'):
            d = doc(key)
            with self.subTest(key):
                got = self.run_js("""var out = [];
DUE.seasons.forEach(function(s) { DUE.segs.forEach(function(seg) { seg.m.forEach(function(m) {
  var days = s.c[seg.k][m.id].d, daily = dfDaily(days).rows, cal = {};
  dfMonths(s).forEach(function(ym) { dfMonth(days, ym, null, s.post).forEach(function(x) { if (x.c) cal[x.day] = dfRec(x.c); }); });
  daily.forEach(function(r) { if (cal[r.key] !== dfRec(r.c)) out.push([seg.k, m.id, r.key, cal[r.key], dfRec(r.c)]); });
}); }); });
console.log(JSON.stringify(out));""", d)
                self.assertEqual(got, [])

    def test_weekly_only_for_nfl_and_ncaaf(self):
        for sp in sports.SPORTS:
            d = doc(sp['key'])
            got = self.run_js("console.log(JSON.stringify(dfViews(DUE.weekly).map(function(v) { return v.k; })));", {'weekly': d['weekly']})
            with self.subTest(sp['key']):
                self.assertEqual(got, ['weekly'] if sp['key'] in ('nfl', 'ncaaf') else ['daily', 'weekly', 'monthly'])
        weeks = doc('nfl')['seasons'][0]['weeks']
        self.assertEqual([w[1] for w in weeks[:2]], ['Week 1', 'Week 2'])

    def test_off_season_mlb_opens_on_october_with_no_today_cell(self):
        d = doc('mlb')
        got = self.run_js("""var s = DUE.seasons[0], seg = DUE.segs[0], m = seg.m[0], ym = dfDefaultMonth(s, '2026-11-23');
var html = dfCalendar(s, seg, m, s.c[seg.k][m.id].d, ym, '2026-11-23');
console.log(JSON.stringify({ ym: ym, today: html.indexOf('df2-today') !== -1, post: html.indexOf('Postseason') !== -1,
  link: html.indexOf('mlb/matchups/?date=2026-10-01') !== -1, next: /data-df-month=""\\s*disabled aria-label="Next month"/.test(html),
  sum: dfSummary({ period: dfPeriod('monthly', s, s.c[seg.k][m.id].d, '2026-11-23', ym).label, side: m.a, c: [30, 20, 0], season: [1200, 1100, 0], prevRate: null }) }));""", d)
        self.assertEqual(got['ym'], '2026-10')
        self.assertFalse(got['today'])
        self.assertTrue(got['post'])
        self.assertTrue(got['link'])
        self.assertTrue(got['next'])
        self.assertEqual(got['sum'], 'October (final): NRFI 30-20 60% · Season 1200-1100 52% · +8 pts')

    def test_in_season_calendar_today_cell(self):
        s = {'cur': True, 'first': '2026-11-01', 'last': '2026-11-22', 'post': [], 'c': {}}
        d = {'matchups': 'nba/matchups/', 'seasons': [s], 'segs': []}
        m = {'a': 'Over', 'b': 'Under', 'ta': 'warm', 'tb': 'cool'}
        got = self.run_js("""var days = {'2026-11-21': [9, 2, 0], '2026-11-22': [3, 3, 0]};
var html = dfCalendar(DUE.seasons[0], null, %s, days, '2026-11', '2026-11-23');
console.log(JSON.stringify({ today: (html.match(/df2-today/g) || []).length, warm: html.indexOf('df2-day df-warm" href="/nba/matchups/?date=2026-11-21"') !== -1,
  even: html.indexOf('df2-day " href="/nba/matchups/?date=2026-11-22"') !== -1, future: (html.match(/df2-future/g) || []).length,
  legend: html.indexOf('More Overs') !== -1 && html.indexOf('More Unders') !== -1 }));""" % json.dumps(m), d)
        self.assertEqual(got, {'today': 1, 'warm': True, 'even': True, 'future': 7, 'legend': True})

    def test_summary_small_sample_and_early_season(self):
        got = self.run_js("""console.log(JSON.stringify([
  dfSummary({ period: 'Last 7 days', side: 'Over', c: [8, 6, 1], season: [100, 90, 4], prevRate: null }),
  dfSummary({ period: 'Last 7 days', side: 'Over', c: [20, 10, 0], season: [40, 40, 0], prevRate: 58 })]));""", {})
        self.assertEqual(got, ['Last 7 days: Over 8-6-1 57% · Season 100-90-4 53% · Small sample',
                               'Last 7 days: Over 20-10 67% · vs last season 58% · +9 pts'])

    def test_full_run_segment_with_the_flag_on_shows_the_lock(self):
        segs = [{'k': x['k'], 'label': x['label'], 'fr': x['fr']} for x in doc('nhl')['segs']]
        body = "console.log(JSON.stringify(dfBar('Segment', 'data-df-seg', %s, '1p')));" % json.dumps(segs)
        on = self.run_js(body, {}, '{ fullRun: true }')
        off = self.run_js(body, {}, '{ fullRun: false }')
        self.assertEqual(on.count('fr-lock'), 3)
        self.assertEqual(on.count('fr-pill'), 3)
        self.assertNotIn('fr-lock', off)
        self.assertEqual(off.count('fr-pill'), 3)


def chrome():
    for c in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        if shutil.which(c):
            return shutil.which(c)
    mac = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    return mac if os.path.exists(mac) else None


HARNESS = """<!doctype html><meta charset="utf-8"><body><pre id="out">running</pre>
<iframe id="f" style="width:375px;height:812px;border:0"></iframe><script>
var SLUGS = %s, out = {}, f = document.getElementById('f');
function wait(test, then) { var n = 0; (function go() { if (test() || ++n > 200) then(); else setTimeout(go, 25); })(); }
function measure(doc, tag) {
  var bad = [], w = doc.documentElement.clientWidth;
  if (doc.documentElement.scrollWidth > w) bad.push(tag + ' page ' + doc.documentElement.scrollWidth);
  Array.prototype.forEach.call(doc.querySelectorAll('#sportApp *'), function(el) {
    if (el.closest('.tr-frow') && !el.classList.contains('tr-frow')) return;   // pills scroll sideways inside their row
    var r = el.getBoundingClientRect();
    if (r.width && (r.right > w + 0.5 || r.left < -0.5)) bad.push(tag + ' ' + el.tagName + '.' + el.className + ' ' + Math.round(r.left) + '-' + Math.round(r.right));
  });
  return bad.slice(0, 5);
}
function next(i) {
  if (i >= SLUGS.length) { document.getElementById('out').textContent = JSON.stringify(out); return; }
  var slug = SLUGS[i];
  f.src = '/' + slug + '/due.html';
  f.onload = function() {
    var doc = f.contentDocument;
    wait(function() { return doc.querySelector('.df-ctrl'); }, function() {
      var bad = [];
      if (!doc.querySelector('.df-ctrl')) bad.push('no app');
      ['daily', 'weekly', 'monthly'].forEach(function(v) {
        var b = doc.querySelector('[data-df-view="' + v + '"]');
        if (!b) return;
        b.click();
        Array.prototype.forEach.call(doc.querySelectorAll('[data-df-seg]'), function(s, j) {
          doc.querySelectorAll('[data-df-seg]')[j].click();
          bad = bad.concat(measure(doc, v + ' ' + doc.querySelectorAll('[data-df-seg]')[j].getAttribute('data-df-seg')));
        });
      });
      out[slug] = bad;
      next(i + 1);
    });
  };
}
next(0);
</script>"""

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="../assets/site.css"></head><body data-sport-slug="%s"><main style="padding:0 16px">
<div id="sportApp" data-section="due"></div></main><script src="../assets/sport.js"></script></body></html>"""


@unittest.skipUnless(chrome(), 'Chrome is not installed')
class PhoneWidthTest(unittest.TestCase):
    def test_nothing_wider_than_a_375px_phone(self):
        tmp = tempfile.mkdtemp()
        try:
            os.symlink(os.path.abspath(os.path.join(ROOT, 'assets')), os.path.join(tmp, 'assets'))
            slugs = []
            for sp in sports.SPORTS:
                os.makedirs(os.path.join(tmp, sp['slug']))
                with open(os.path.join(tmp, sp['slug'], 'due.json'), 'w') as f:
                    json.dump(doc(sp['key']), f)
                with open(os.path.join(tmp, sp['slug'], 'due.html'), 'w') as f:
                    f.write(PAGE % sp['slug'])
                slugs.append(sp['slug'])
            with open(os.path.join(tmp, 'harness.html'), 'w') as f:
                f.write(HARNESS % json.dumps(slugs))
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *a):
                    pass
            handler = functools.partial(Quiet, directory=tmp)
            srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                dom = subprocess.run([chrome(), '--headless=new', '--disable-gpu', '--no-first-run', '--window-size=420,900',
                                      f'--user-data-dir={os.path.join(tmp, "profile")}', '--virtual-time-budget=60000', '--dump-dom',
                                      f'http://127.0.0.1:{srv.server_address[1]}/harness.html'],
                                     capture_output=True, text=True, timeout=180).stdout
            finally:
                srv.shutdown()
                srv.server_close()
            got = json.loads(dom.split('<pre id="out">', 1)[1].split('</pre>', 1)[0].replace('&amp;', '&'))
            self.assertEqual(sorted(got), sorted(slugs))
            for slug, bad in got.items():
                with self.subTest(slug):
                    self.assertEqual(bad, [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
