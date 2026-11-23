"""Team pages (Chris's Nov 19 spec): the header, the season state the build
hands assets/sport.js, the champion's badge, and the Situational splits each
sport's registry (assets/splits/) adds."""
import json
import os
import re
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_site  # noqa: E402
import seasons  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


def read(*p):
    return open(os.path.join(ROOT, *p), encoding='utf-8').read()


class HeaderTest(unittest.TestCase):
    def test_no_line_under_the_h1_and_a_team_dropdown(self):
        sp = sports.BY_KEY['nba']
        team = {'slug': 'bos', 'code': 'BOS', 'name': 'Boston Celtics', 'nickname': 'Celtics', 'division': 'Atlantic', 'conference': 'Eastern Conference'}
        other = dict(team, slug='atl', code='ATL', name='Atlanta Hawks', nickname='Hawks')
        meta = build_site.sport_team_meta(sp, team, '2025-26')
        self.assertEqual(meta['desc'], '')
        self.assertNotIn('sub_html', meta)
        body = build_site.team_detail_html(sp, team, [team, other])
        self.assertNotIn('sport-team-back', body)
        self.assertIn('All NBA teams &rarr;</a>', body)
        menu = body[body.index('tp-pick-menu'):]
        self.assertLess(menu.index('>Celtics<'), menu.index('>Hawks<'))   # A to Z by the name shown
        self.assertIn('aria-current="page"', body)

    def test_college_dropdown_starts_with_the_conference(self):
        sp = sports.BY_KEY['ncaab']
        a = {'slug': 'uk', 'code': 'UK', 'name': 'Kentucky Wildcats', 'location': 'Kentucky', 'conference': 'Southeastern Conference'}
        b = {'slug': 'duke', 'code': 'DUKE', 'name': 'Duke Blue Devils', 'location': 'Duke', 'conference': 'Atlantic Coast Conference'}
        body = build_site.team_picker(sp, a, [a, b])
        self.assertLess(body.index('Southeastern Conference</p>'), body.index('All teams</p>'))

    def test_champion_title_only_for_the_title_winner_between_seasons(self):
        sp = sports.BY_KEY['mlb']
        st, doc = build_site.season_info(sp)
        ch = seasons.champion(doc)
        if st['layout'] != 'off' or not ch:
            self.skipTest('MLB is not between seasons with a champion')
        self.assertIn('World Series Champions', build_site.champion_title(sp, {'slug': ch['team'], 'name': ''}))
        self.assertEqual(build_site.champion_title(sp, {'slug': ch['opp'], 'name': ''}), '')


class SeasonStateTest(unittest.TestCase):
    def test_team_page_carries_the_state(self):
        for sp in sports.SPORTS:
            team = {'slug': 'x', 'code': 'X', 'name': 'X'}
            html = build_site.team_detail_html(sp, team)
            st, _ = build_site.season_info(sp)
            want = 'off' if st['layout'] == 'off' else 'early' if st['key'] == 'early' else ''
            self.assertIn(f'data-season="{want}"', html, sp['key'])
            self.assertIn('data-opening="', html)
            self.assertNotIn('Matchup trends', html)


class SplitsTest(unittest.TestCase):
    def ids(self, name):
        return set(re.findall(r"\{ id: '([a-z0-9]+)', label", read('assets', 'splits', f'{name}.js')))

    def test_new_splits(self):
        self.assertTrue({'vo500', 'vu500', 'tb2b', 'nb2b', 'pl3'} <= self.ids('nhl'))
        self.assertTrue({'v500', 'vsub', 'b2b2', 'nb2b', 'pl15'} <= self.ids('basketball'))
        self.assertIn("label: 'Vs. teams over .500'", read('assets', 'splits', 'basketball.js'))
        self.assertTrue({'vo500', 'vu500', 'pl15'} <= self.ids('ncaab'))
        for f in ('nfl', 'ncaaf'):
            self.assertTrue({'vo500', 'vu500', 'pl14'} <= self.ids(f), f)
        self.assertTrue({'home', 'away', 'fav', 'dog', 'vo500', 'vu500', 'dan', 'pw', 'pl', 'pl3', 'pshut'} <= self.ids('mlb'))

    def test_mlb_registry_on_the_splits_page(self):
        js = read('assets', 'splits', 'mlb.js')
        self.assertNotIn('teamOnly: true', js)   # Stats consistency: /mlb/stats/splits/ is on
        self.assertIn("id: 'rfi'", js)
        self.assertIn('function leagueSit()', read('assets', 'sport.js'))

    def test_consistency_splits(self):
        # Stats consistency spec: the same groups in every sport
        self.assertTrue({'dayg', 'nightg', 'wkday', 'wkend', 'offday', 'dh2', 'tripl', 'hometrip', 'tz', 'coors', 'psegf5', 'tlow', 'tmid', 'thigh'} <= self.ids('mlb'))
        self.assertTrue({'pseg', 'fs0', 'fs3', 'fs7', 'ds0', 'ds3', 'ds7', 'tlow', 'tmid', 'thigh', 'altden', 'tz'} <= self.ids('nfl'))
        self.assertTrue({'pseg', 'tlow', 'tmid', 'thigh'} <= self.ids('ncaaf'))
        self.assertTrue({'pseg1p', 'tlow', 'tmid', 'thigh', 'wkday', 'sat', 'sun'} <= self.ids('nhl'))
        self.assertTrue({'wkday', 'sat', 'sun', 'tz'} <= self.ids('basketball'))
        self.assertIn('tz: true', read('assets', 'splits', 'nba.js'))
        self.assertNotIn('tz: true', read('assets', 'splits', 'wnba.js'))
        for key in ('nba', 'nfl', 'mlb'):
            zones = json.load(open(os.path.join(ROOT, 'data_seed', 'conferences', f'{key}_timezones.json')))['zones']
            self.assertEqual(len(zones), 30 if key != 'nfl' else 32, key)

    def test_mlb_local_time_and_rest_buckets(self):
        # Day / Night by the park's clock (Arizona keeps standard time); each
        # sport's Rest buckets and Day of week tiles
        script = (read('assets', 'splits', 'mlb.js') + '''
          var R = window.RTYB_SPLITS.mlb, day = R.rows.filter(function(r) { return r.id === 'dayg'; })[0];
          function ctx(home, tz, mins, month) { return { g: { home: home }, venueTz: tz, mins: mins, month: month }; }
          var out = { nyy4pm: day.test(ctx('nyy', -5, 16 * 60, 6)), sea740: day.test(ctx('sea', -8, 19 * 60 + 40, 6)),
                      ari740: day.test(ctx('ari', -7, 19 * 60 + 40, 6)), ari840: day.test(ctx('ari', -7, 20 * 60 + 40, 6)) };
          console.log(JSON.stringify(out));
        ''')
        out = subprocess.run(['node', '-e', 'global.window = global; global.document = {};' + script], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        # 4:00 PM ET in New York: day; 7:40 PM ET in Seattle is 4:40 PM there: day;
        # 7:40 PM ET in June is 4:40 PM in Phoenix: day; 8:40 PM ET is 5:40 PM: night
        self.assertEqual(got, {'nyy4pm': True, 'sea740': True, 'ari740': True, 'ari840': False})
        js = read('assets', 'situational.js')
        self.assertIn("nfl: [4, 6, 0, 1], ncaaf: [2, 3, 4, 5, 6]", js)
        for bucket in ("['Short week', between(0, 5)], ['Normal', between(6, 7)], ['Extra rest', between(8, 999)]",
                       "['Short week', between(0, 5)], ['Normal', between(6, 8)], ['Extra rest', between(9, 999)]",
                       "['1 day', between(-1, 1)], ['2-3 days', between(2, 3)], ['4+ days', between(4, 999)]",
                       "['No off day', between(-1, 0)], ['After an off day', between(1, 999)]",
                       "['Back-to-back', between(0, 0)], ['1 day', between(1, 1)], ['2 days', between(2, 2)], ['3+ days', between(3, 999)]"):
            self.assertIn(bucket, js)
        self.assertIn("'Next game'", js)
        self.assertIn(' record by day of the week.', js)
        self.assertIn(' record by rest.', js)

    def test_goalie_group_hidden(self):
        self.assertIn("{ id: 'goalie', label: 'Goalie', hidden: true }", read('assets', 'splits', 'nhl.js'))
        self.assertIn('if (G.hidden) HIDDEN[G.id] = 1;', read('assets', 'situational.js'))


class TeamScriptTest(unittest.TestCase):
    def test_spec_order_and_removed_pieces(self):
        js = read('assets', 'sport.js')
        body = js[js.index('function renderTeam()'):js.index('function tpUse(')]
        self.assertIn("nextHtml() + lastHtml() + marketsHtml() + streaksHtml() + '<div id=\"tmLogBox\"></div><div id=\"tpHABox\"></div>' + sitHtml()", body)
        self.assertIn('linesHtml() + resultsHtml()', body)
        for gone in ('Matchup trends', 'tm-edge-rank', 'sit-tag', '✓'):
            self.assertNotIn(gone, body)
        self.assertIn('No active streaks of 3 or more.</p>', body)
        self.assertIn("'Show 10 more' : 'Load more'", body)


class TeamsIndexTest(unittest.TestCase):
    """Teams index redesign (Nov 19): no dimming, times only with Today, Leaders, college paging."""

    def body(self):
        js = read('assets', 'sport.js')
        return js[js.index('// ----------------------------------------------------------- Teams list'):js.index('// ------------------------------------------------------------ team page')]

    def test_rules(self):
        js = self.body()
        self.assertNotIn('tl-few', js)
        self.assertNotIn('pct-bar', js)
        self.assertNotIn('>small sample<', js)   # Evening fixes (Nov 19): no "small sample" anywhere
        self.assertIn('var TL_PAGE = 50;', js)
        self.assertIn(">Show ' + Math.min(TL_PAGE", js)
        self.assertIn("' of ' + list.length", js)
        self.assertIn('var TL_LEAD_MIN = 10;', js)
        self.assertIn("' Leaders</h2>'", js)
        self.assertIn('All leaders &rarr;', js)
        self.assertIn("placeholder=\"Search ' + nTeams + ' teams\"", js)
        self.assertIn("tlCollege() ? 'All conferences' : 'All teams'", js)
        self.assertIn("' % (' + tpSides(p.m) + ')'", js)
        for key in ('name', 'pct', 'l10', 'streak', 'units'):
            self.assertIn(f"th('{key}'", js)

    def test_today_is_todays_date_only(self):
        js = read('assets', 'sport.js')
        self.assertIn('function tmSlate() { return D.games[todayET()] || []; }', js)
        self.assertNotIn('tmShortTime', js)   # no game times in the list without Today

    def test_ties_note_per_market(self):
        js = self.body()
        self.assertIn('win % leaves ties out', js)
        self.assertIn('3-Way: win % counts ties', js)
        self.assertIn('cover % leaves pushes out', js)

    def test_gold_streak_chip_in_light_mode(self):
        self.assertEqual(read('template.html').count('.tl-streak.flat)'), 2)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(__import__('shutil').which('node'), 'node is not installed')
class FullRunPremiumTest(unittest.TestCase):
    """PREMIUM.fullRun (assets/sport.js): off (the default) shows every Full
    Run row; on, a free visitor sees the first row, the rest blurred behind
    "Unlock with Premium", and a lock on the Game Log's Full Run pills."""

    def run_js(self, flag, premium, body):
        src = read('assets', 'sport.js')

        def one(name):
            m = re.search(r'^  function %s\([^)]*\) \{.*\}$' % name, src, re.M)
            self.assertIsNotNone(m, name)
            return m.group(0)
        fr_lock = re.search(r"^  var FR_LOCK = .*;$", src, re.M).group(0)
        js = ('var ROOT = "/", PREMIUM = {fullRun: %s}, IS_PREMIUM = %s;\n' % (json.dumps(flag), json.dumps(premium)) +
              'function esc(s) { return String(s); }\n' + fr_lock + '\n' +
              '\n'.join(one(n) for n in ('premiumLocked', 'lockFrom', 'segPill')) + '\n' + body)
        return subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True).stdout

    ROWS = 'console.log(lockFrom(["<1Q>", "<1H>", "<2H>", "<GAME>"], 3, "fullRun"));'
    PILL = 'console.log(segPill({key: "game", label: "Full Game"}, false, true, "data-log-seg"));'

    def test_flag_off_shows_every_row(self):
        self.assertEqual(self.run_js(False, False, self.ROWS).strip(), '<1Q><1H><2H><GAME>')
        self.assertNotIn('fr-lock', self.run_js(False, False, self.PILL))
        self.assertIn('fr-pill', self.run_js(False, False, self.PILL))   # the gold dot either way

    def test_flag_on_shows_the_first_full_run_row_and_the_lock(self):
        out = self.run_js(True, False, self.ROWS).strip()
        self.assertTrue(out.startswith('<1Q><1H><2H><div class="pm-blur" aria-hidden="true"><GAME></div>'))
        self.assertIn('Unlock with Premium', out)
        self.assertIn('fr-lock', self.run_js(True, False, self.PILL))

    def test_premium_visitors_see_everything(self):
        self.assertEqual(self.run_js(True, True, self.ROWS).strip(), '<1Q><1H><2H><GAME>')
