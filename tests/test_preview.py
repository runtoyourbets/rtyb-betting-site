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
        head, dek, callout, md = preview.split('# Suns at Kings\n> One line.\n!! 10 | Straight Bucks unders\n\n### Bucks at Heat · 7:00 PM ET\n\nText.')
        self.assertEqual((head, dek, callout), ('Suns at Kings', 'One line.', ('10', 'Straight Bucks unders')))
        self.assertTrue(md.startswith('<<callout>>'))
        self.assertIn('### Bucks at Heat', md)

    def test_older_drafts(self):
        head, dek, callout, md = preview.split('**Twelve games tonight.**\n\nShort first paragraph.\n\nMore text.')
        self.assertEqual((head, dek, callout, md), ('Twelve games tonight.', 'Short first paragraph.', None, 'More text.'))


if __name__ == '__main__':
    unittest.main()
