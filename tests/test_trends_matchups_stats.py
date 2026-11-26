"""Trends, Matchups and Stats tweaks (Nov 19 spec): one "i" box everywhere,
matchup label texts, League / Streak / Matchup Trends, no-games days, the
Stats Leaders block and the league Splits layout."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_site  # noqa: E402
import definitions  # noqa: E402
import front  # noqa: E402
import trends  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


def read(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
        return f.read()


class TipBoxTest(unittest.TestCase):
    def test_one_box_on_every_page(self):
        shell = build_site.SHELL_JS
        self.assertIn("box.id = 'tipBox'", shell)
        self.assertIn("box.classList.toggle('tip-panel', panel)", shell)   # phones: the centered panel
        self.assertIn('class="tip-x" aria-label="Close"', shell)
        # the old per-file toggles are gone
        self.assertNotIn("tip.classList.toggle('open')", read('assets', 'sport.js'))
        self.assertNotIn("tip.classList.toggle('open')", read('scripts', 'front.py'))
        css = read('template.html')
        self.assertIn('.info-tip .tip-bubble { display: none !important; }', css)
        self.assertIn('.tip-box.tip-panel { left: 16px !important; right: 16px;', css)

    def test_trend_tip_is_title_definition_compare(self):
        c = {'title': 'Back home favorites', 'meaning': 'The home team is favored.', 'rate': 0.62, 'base': 0.5, 'w': 57, 'l': 35,
             'last': 'Last time: ...', 'angle': 'home_fav'}
        html = front.trend_tip(None, c)
        self.assertIn('<span class="tip-t">Back home favorites</span>', html)
        self.assertIn('This trend: 62% (57-35). League average: 50%.', html)
        self.assertNotIn('Last time', html)

    def test_last_time_behind_its_switch(self):
        T = definitions.tooltips()
        for grp in ('side_angles', 'game_angles'):
            for aid, x in T[grp].items():
                self.assertIs(x.get('show_last'), False, aid)
        self.assertEqual(trends.show_last_ids(T), [])
        js = read('assets', 'sport.js')
        self.assertIn('function showLast(c)', js)
        self.assertNotIn('class="tr-bar"', js)


class LabelTextTest(unittest.TestCase):
    def test_label_texts(self):
        L = definitions.tooltips()['matchup_labels']
        self.assertEqual(L['lockdown']['tooltip'], 'Both teams’ {segment}s have gone Under in 60%+ of their games (5+ played).')
        self.assertEqual(L['fireworks']['tooltip'], 'Both teams’ {segment}s have gone Over in 60%+ of their games (5+ played).')
        self.assertEqual(L['tug_of_war']['tooltip'], 'One team’s {segment}s have gone Over in 60%+ of its games, the other’s have gone Under in 60%+ (5+ played).')
        self.assertIn('gone BTTS No', L['lockdown']['tooltip_btts'])
        self.assertIn('gone BTTS Yes', L['fireworks']['tooltip_btts'])

    def test_plural_segment(self):
        x = {'tooltip': 'Both teams’ {segment}s have gone Under.'}
        self.assertEqual(front.label_text(x, '1st period'), 'Both teams’ 1st periods have gone Under.')
        self.assertEqual(front.label_text(x, 'first five'), 'Both teams’ first five have gone Under.')

    def test_chip_has_its_own_i(self):
        html = front.label_chip('🔒 Lockdown', 'Both teams…')
        self.assertIn('<span class="lbl-chip"><span class="mo-chip">🔒 Lockdown</span><button type="button" class="info-tip"', html)


class TrendsPageTest(unittest.TestCase):
    def test_rules(self):
        js = read('assets', 'sport.js')
        self.assertIn('var TR_OPEN = 6, TR_PHONE = 3, MT_GAMES = 5;', js)
        self.assertIn("'\">Show all ' + cards.length + ' trends</button>'", js)
        self.assertIn('League trends start once teams have played 10 games.', js)
        self.assertIn('See last season&rsquo;s trends &rarr;', js)
        self.assertIn("' season</span></div>'", js)
        self.assertIn('Show more games', js)
        self.assertIn("var RES_WORD = { hit: 'Hit', miss: 'Miss', push: 'Push' };", js)
        self.assertIn("STK_ORDER = { nhl: ['ml', 'total', 'btts', 'ml3'], mlb: ['rfi', 'ml', 'ats', 'total'] }", js)
        self.assertIn("|| ['ats', 'ml', 'total']", js)
        self.assertIn('All active streaks &rarr;', js)

    def test_last_season_cards(self):
        hist = {'season': 2026, 'seasonLabel': '2025-26', 'games': {}}
        sp = __import__('sports').BY_KEY['nba']
        out = trends.last_season(sp, hist)
        self.assertEqual(out['label'], '2025-26')
        self.assertIsNone(trends.last_season(sp, {}))


class NoGamesTest(unittest.TestCase):
    def test_card_on_matchups_and_odds(self):
        js = read('assets', 'sport.js')
        self.assertEqual(js.count('noGamesCard(cur, '), 5)   # the definition, Matchups (day / week), Odds (day / week)
        self.assertIn("Next games: ' + esc(name(next)) + ' &rarr;", js)
        self.assertIn("&larr; ' + esc(name(prev))", js)


class StatsTest(unittest.TestCase):
    def test_leaders(self):
        js = read('assets', 'sport.js')
        self.assertIn("stSection('leaders', 'Leaders', pills, body)", js)
        self.assertIn('var LEAD_MK = null, LEAD_MIN = 10;', js)
        self.assertIn("statsUrl() + '#leaders\">All leaders &rarr;</a>", js)

    def test_league_splits(self):
        js = read('assets', 'situational.js')
        self.assertIn("var LEAGUE_ORDER = ['Matchup', 'Opponent', 'Start time', 'Rest', 'Previous game'];", js)
        self.assertIn("rested: 'Team with more rest'", js)
        self.assertIn("label: 'Better record team'", js)
        sp = read('assets', 'sport.js')
        body = sp[sp.index('function renderSplits()'):sp.index('// /stats/edges/')]
        self.assertIn('eng.league(', body)
        self.assertNotIn('View as', body.replace('conference in situational.js', ''))


if __name__ == '__main__':
    unittest.main()
