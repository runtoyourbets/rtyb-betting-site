"""
Preview (scripts/preview.py): the lead game, the draft's parts and the
image card's chip.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import preview  # noqa: E402


class Sp:
    def __init__(self, key):
        self.key = key


def trend(pct, n):
    return {'pct': pct, 'n': n, 'kind': 'streak', 'text': 'x'}


class LeadTest(unittest.TestCase):
    def setUp(self):
        sp = Sp('nba')
        self.motd = (sp, {'id': 1}, [trend(0.9, 20), trend(0.6, 12)])
        self.other = (sp, {'id': 2}, [trend(0.7, 15), trend(0.6, 12)])
        self.one = (sp, {'id': 3}, [trend(0.95, 30)])

    def test_never_the_motd(self):
        got = preview.pick_lead([self.motd, self.other, self.one], ('nba', '1'))
        self.assertEqual(got[1]['id'], 2)

    def test_needs_two_trends(self):
        got = preview.pick_lead([self.other, self.one], None)
        self.assertEqual(got[1]['id'], 2)

    def test_motd_when_no_other_game_has_two(self):
        got = preview.pick_lead([self.motd, self.one], ('nba', '1'))
        self.assertEqual(got[1]['id'], 1)

    def test_rates_need_ten_games(self):
        self.assertIsNone(preview.strongest([trend(1.0, 9)]))


class SplitTest(unittest.TestCase):
    def test_parts(self):
        head, dek, md = preview.split('# Suns at Kings\n> One line.\n!! 10 | The old callout\n\n### Bucks at Heat · 7:00 PM ET\n\nText.')
        self.assertEqual((head, dek), ('Suns at Kings', 'One line.'))
        self.assertNotIn('!!', md)   # the callout is gone
        self.assertTrue(md.startswith('### Bucks at Heat'))

    def test_older_drafts(self):
        head, dek, md = preview.split('**Twelve games tonight.**\n\nShort first paragraph.\n\nMore text.')
        self.assertEqual((head, dek, md), ('Twelve games tonight.', 'Short first paragraph.', 'More text.'))


class BoxTest(unittest.TestCase):
    def test_spread_across_sports(self):
        # 3+ sports: three different ones; 2: split 2 and 1; 1: all from it
        pick = lambda sport, day, games: {'_score': 0.6, 'sport': sport}
        saved = preview.sport_of, preview.box_games, preview.BOX_KEYS, preview.lead_of
        preview.sport_of, preview.box_games, preview.lead_of = (lambda k: k), (lambda sport, key, day: []), (lambda key, day: None)
        preview.BOX_KEYS = tuple((b, pick) for b, _ in saved[2])
        try:
            for keys, want in ((['nhl', 'nba', 'ncaab', 'nfl'], 3), (['nhl', 'nba'], 2), (['nba'], 1)):
                got = preview.boxes('all', '2026-11-18', keys)
                self.assertEqual(len(got), 3)
                self.assertEqual(len({b['sport'] for b in got.values()}), want)
        finally:
            preview.sport_of, preview.box_games, preview.BOX_KEYS, preview.lead_of = saved

    def test_edge_play_needs_its_own_market(self):
        # the side's season rate under 40% skips it; a total needs over / under rates
        class S:
            key = 'nhl'
            def team(self, slug): return {'short': slug.title()}
            def full_name(self, slug): return slug.title()
        g = {'away': 'islanders', 'home': 'jets'}
        rate = lambda w, l: [{'seg': '1p', 'mk': 'ml', 'splits': {'season': {'_w': w, '_l': l}}}]
        why = preview.edge_why(S(), '2026-11-19', {'seg': '1p', 'market': 'ml', 'side': 'away'}, g,
                               {'islanders': rate(10, 6), 'jets': rate(3, 10)})
        self.assertEqual(why, 'The Islanders have won the first period 62% (10-6); the Jets have won it 23% (3-10).')
        self.assertIsNone(preview.edge_why(S(), '2026-11-19', {'seg': '1p', 'market': 'ml', 'side': 'home'}, g,
                                           {'islanders': rate(10, 6), 'jets': rate(3, 10)}))
        total = {'seg': '1p', 'market': 'total', 'side': 'under', 'angles': [['Jets 1P ML, season', '12-2'], ['Jets 1P unders, season (1.5)', '11-4']]}
        self.assertEqual(preview.edge_why(S(), '2026-11-19', total, g, {}), 'Jets 1P unders, season (1.5): 73% (11-4).')

    def test_box_lines_go_to_front_matter(self):
        import daily_content as dc
        body, front = dc.box_front('STAT: The Bucks keep going Under.\n# Head\n> Dek.\n\nBody.',
                                   {'boxes': {'stat_of_night': {'sport': 'nba', 'number': '93%', 'line': 'x', 'text': 'default'}}})
        self.assertEqual(body, '# Head\n> Dek.\n\nBody.')
        self.assertIn('"text": "The Bucks keep going Under."', front[0])


class Sport:
    def __init__(self, key, teams):
        self.key, self.doc = key, {'teams': {t: {} for t in teams}}


class LeagueTest(unittest.TestCase):
    def test_college_needs_both_teams_in_the_league(self):
        sp = Sport('ncaab', ['UK', 'ARIZ'])
        self.assertTrue(preview.in_league(sp, {'away': 'UK', 'home': 'ARIZ'}))
        self.assertFalse(preview.in_league(sp, {'away': 'UK', 'home': 'BERE'}))

    def test_pro_games_always_count(self):
        self.assertTrue(preview.in_league(Sport('nba', []), {'away': 'BOS', 'home': 'NY'}))


class BoxesAndAdsTest(unittest.TestCase):
    def piece(self, show):
        box = {'sport': 'nba', 'number': '86%', 'line': 'Under 1H', 'text': 'Low starts.'}
        if show is not None:
            box['show'] = show
        return {'date': '2026-11-19', 'boxes': {'stat_of_night': box}}

    def test_show_switch_hides_a_box(self):
        self.assertIn('86%', preview.boxes_html(self.piece(None), '../'))
        self.assertIn('86%', preview.boxes_html(self.piece(True), '../'))
        self.assertEqual(preview.boxes_html(self.piece(False), '../'), '')

    def test_ads_render_nothing_while_off(self):
        body = ''.join(f'<h3 class="pv-gh">G{i}</h3><p>x</p>' for i in range(5))
        old = preview.sports.ADS_ON
        try:
            preview.sports.ADS_ON = False
            self.assertEqual(preview.ad_slot('side'), '')
            self.assertEqual(preview.place_ad(body, preview.GAME_HEAD), body)
            preview.sports.ADS_ON = True
            got = preview.place_ad(body, preview.GAME_HEAD)
            self.assertLess(got.index('data-ad="article"'), got.index('G3'))
            self.assertGreater(got.index('data-ad="article"'), got.index('G2'))
            win = '<h3 class="pv-gh">A</h3><h3 class="pv-gh">B</h3><h3 class="pv-gh">C</h3><h2 class="pv-win">Sunday</h2><h3 class="pv-gh">D</h3>'
            got = preview.place_ad(win, preview.GAME_HEAD)
            self.assertLess(got.index('data-ad="article"'), got.index('Sunday'))
        finally:
            preview.sports.ADS_ON = old


if __name__ == '__main__':
    unittest.main()
