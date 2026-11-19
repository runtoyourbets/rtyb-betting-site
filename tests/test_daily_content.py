"""
Preview's drafts (scripts/daily_content.py): streaks extended or snapped
by last night's game, and the check that flags any number in a draft that
isn't in the packet Claude was given.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import daily_content as dc  # noqa: E402

LABELS = {'ml': {'W': 'won', 'L': 'lost'}}


class StreakTest(unittest.TestCase):
    def test_extended_and_snapped(self):
        seqs = {('BOS', 'ml'): ['L', 'W', 'W', 'W'], ('CHI', 'ml'): ['L', 'L', 'L', 'W'], ('NY', 'ml'): ['W', 'W']}
        got = dc.streak_changes(seqs, {'BOS', 'CHI', 'NY'}, LABELS)
        self.assertEqual([(x['team'], x['change'], x['streak']) for x in got],
                         [('BOS', 'extended', 'won 3 straight'), ('CHI', 'snapped', 'lost 3 straight')])

    def test_only_teams_that_played(self):
        self.assertEqual(dc.streak_changes({('BOS', 'ml'): ['W', 'W', 'W']}, set(), LABELS), [])


class NumberCheckTest(unittest.TestCase):
    def test_flags_numbers_not_in_packet(self):
        packet = {'price': -125, 'units': 0.8, 'streak': 'won 3 straight'}
        body = 'Boston won at -125 for +0.80u, 3 straight now, and trends went 9-4. 21+. Call 1-800-GAMBLER.'
        self.assertEqual(dc.unchecked_numbers(body, packet), ['9', '-4'])

    def test_times_and_dates_are_not_numbers(self):
        body = 'Suns at Kings (10:00 PM ET), Bucks at Heat at 7:30 PM and a 9 PM tip on Nov 18, 2026 (11/18).'
        self.assertEqual(dc.unchecked_numbers(body, {}), [])


class EverySportTest(unittest.TestCase):
    def test_titles_follow_the_sport(self):
        self.assertEqual(dc.title('recap', 'ncaab', '2026-11-12'), 'NCAAB First Half Betting Recap — Nov 12, 2026')
        self.assertEqual(dc.title('preview', 'nfl', '2026-11-12', {'week': 'Week 11'}),
                         'NFL First Quarter and First Half Betting Week 11 Preview — Nov 12, 2026')
        self.assertEqual(dc.title('recap', 'ncaaf', '2026-11-16'), 'NCAAF First Quarter and First Half Betting Weekend Recap — Nov 16, 2026')

    def test_football_is_weekly(self):
        self.assertEqual(dc.WEEKLY_WINDOWS['recap'][0], 0)     # Monday
        self.assertEqual(dc.WEEKLY_WINDOWS['preview'][:2], (3, 8))   # Thursday from 8 AM ET (ready by 10)
        self.assertTrue(dc.weekly('nfl') and dc.weekly('ncaaf') and not dc.weekly('nba'))

    def test_preview_has_its_format_and_no_disclaimer(self):
        for kind in ('preview', 'week_preview', 'all_preview'):
            self.assertIn('lead game', dc.TASK[kind])
        self.assertIn('# The headline', dc.SYSTEM)
        self.assertIn('!! NUMBER |', dc.SYSTEM)
        self.assertNotIn('not promises', dc.SYSTEM + ''.join(dc.TASK.values()))
        self.assertNotIn('On Tap', dc.SYSTEM + ''.join(dc.TASK.values()))

    def test_all_preview_title(self):
        self.assertEqual(dc.title('preview', 'all', '2026-11-18'), 'First Period, Quarter & Half Betting Preview — Nov 18, 2026')

if __name__ == '__main__':
    unittest.main()
