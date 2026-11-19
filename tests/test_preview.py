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
        saved = preview.sport_of, preview.box_games, preview.BOX_KEYS
        preview.sport_of, preview.box_games = (lambda k: k), (lambda sport, key, day: [])
        preview.BOX_KEYS = tuple((b, pick) for b, _ in saved[2])
        try:
            for keys, want in ((['nhl', 'nba', 'ncaab', 'nfl'], 3), (['nhl', 'nba'], 2), (['nba'], 1)):
                got = preview.boxes('all', '2026-11-18', keys)
                self.assertEqual(len(got), 3)
                self.assertEqual(len({b['sport'] for b in got.values()}), want)
        finally:
            preview.sport_of, preview.box_games, preview.BOX_KEYS = saved

    def test_box_lines_go_to_front_matter(self):
        import daily_content as dc
        body, front = dc.box_front('STAT: The Bucks keep going Under.\n# Head\n> Dek.\n\nBody.',
                                   {'boxes': {'stat_of_night': {'sport': 'nba', 'number': '93%', 'line': 'x', 'text': 'default'}}})
        self.assertEqual(body, '# Head\n> Dek.\n\nBody.')
        self.assertIn('"text": "The Bucks keep going Under."', front[0])


if __name__ == '__main__':
    unittest.main()
