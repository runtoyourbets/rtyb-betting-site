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

    def test_round_numbers_match(self):
        packet = {'price': 330, 'pct': '70%', 'line': -170}
        self.assertEqual(dc.unchecked_numbers('+330, 70% and -170, but 80.', packet), ['80'])


class HeadlineCardTest(unittest.TestCase):
    """The share card prints the lead game's trend; the headline must carry
    its number (Chris's QA: headline "8 straight first halves", art "15 of 17
    1Q Unders")."""
    def test_card_number(self):
        self.assertEqual(dc.pv.card_number('MIL UNDER 1Q · 10 STRAIGHT'), '10')
        self.assertEqual(dc.pv.card_number('SAC LOST 1H · 11 OF 13'), '11')
        self.assertEqual(dc.pv.card_number('NYY NRFI F5 · 15 OF 17'), '15')

    def test_headline_without_the_cards_number_is_flagged(self):
        packet = {'games': [{'id': '1'}, {'id': '2', 'headline_trend': {'trend': 'MIL has gone Under the 1st quarter total in 15 of 17', 'card': 'MIL UNDER 1Q · 15 OF 17'}}]}
        self.assertEqual(dc.headline_check('# Bucks Have Lost 8 Straight First Halves\n> Dek.', packet),
                         ["headline isn't the card's trend (MIL UNDER 1Q · 15 OF 17)"])
        self.assertEqual(dc.headline_check('# Bucks 1Q Unders Hit in 15 of 17\n> Dek.', packet), [])
        home = {'sports': {'NBA': {'games': packet['games']}}}
        self.assertEqual(len(dc.headline_check('# Eight straight\n', home)), 1)


class EverySportTest(unittest.TestCase):
    def test_titles_follow_the_sport(self):
        self.assertEqual(dc.title('recap', 'ncaab', '2026-11-12'), 'NCAAB First Half Betting Recap - Nov 12, 2026')
        self.assertEqual(dc.title('preview', 'nfl', '2026-11-12', {'week': 'Week 11'}),
                         'NFL Week 11 First Quarter & First Half Betting Preview')
        self.assertEqual(dc.title('preview', 'ncaaf', '2026-11-17', {'week': 'Week 12'}),
                         'College Football Week 12 First Quarter & First Half Betting Preview')
        self.assertEqual(dc.title('recap', 'ncaaf', '2026-11-16'), 'NCAAF First Quarter and First Half Betting Weekend Recap - Nov 16, 2026')

    def test_weekly_previews_by_kickoff_window(self):
        import preview
        from datetime import datetime, timezone
        at = lambda iso: datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
        self.assertEqual([preview.kickoff_window(at(x)) for x in ('2026-11-20T01:15', '2026-11-22T18:00', '2026-11-22T21:25',
                                                                   '2026-11-23T01:20', '2026-11-24T01:15', '2026-11-21T17:00')],
                         ['Thursday', 'Sunday 1:00 PM', 'Sunday 4:25 PM', 'Sunday Night', 'Monday Night', 'Saturday'])
        self.assertEqual(preview.page_dir('nfl', 11), 'nfl/preview/week-11/')
        self.assertEqual(preview.page_dir('ncaaf', 12), 'college-football/preview/week-12/')

    def test_football_is_weekly(self):
        self.assertEqual(dc.WEEKLY_WINDOWS['recap'][0], 0)     # Monday
        self.assertEqual(dc.WEEKLY_WINDOWS['preview'][:2], (3, 8))   # Thursday from 8 AM ET (ready by 10)
        self.assertTrue(dc.weekly('nfl') and dc.weekly('ncaaf') and not dc.weekly('nba'))

    def test_preview_has_its_format_and_no_disclaimer(self):
        for kind in ('preview', 'week_preview', 'all_preview'):
            self.assertIn('STAT / TREND / EDGE', dc.TASK[kind])
        guide = open(dc.GUIDE, encoding='utf-8').read().strip()
        self.assertIn(guide, dc.system_for('preview'))   # the full writing guide, every preview
        self.assertNotIn('writing_guide', dc.system_for('recap'))
        self.assertNotIn('!!', dc.system_for('preview'))
        self.assertNotIn('not promises', dc.SYSTEM + ''.join(dc.TASK.values()))
        self.assertNotIn('On Tap', dc.SYSTEM + ''.join(dc.TASK.values()))

    def test_subheads_on_adjacent_lines(self):
        # the drafter's "### ..." right above its paragraph: still a subhead (QA fixes, Nov 19)
        import daily
        html = daily.to_html('## Friday\n\n### Oregon at Michigan State · Friday 8:00 PM ET\nHome underdogs have covered.')
        self.assertEqual(html, '<h2>Friday</h2>\n<h3>Oregon at Michigan State · Friday 8:00 PM ET</h3>\n<p>Home underdogs have covered.</p>')
        self.assertIn('at most 8', dc.PREVIEW)

    def test_all_preview_title(self):
        self.assertEqual(dc.title('preview', 'all', '2026-11-18'), 'First Period, Quarter & Half Betting Preview - Nov 18, 2026')

class PhraseCheckTest(unittest.TestCase):
    BANNED = ['headliner', 'fits that one', "let's dive in"]

    def flags(self, md, codes=('LR', 'HOU')):
        return [(i, what) for i, what, _ in dc.phrase_flags(dc.article_lines(md), codes, self.BANNED)]

    def test_banned_list_from_the_guide(self):
        got = dc.banned_phrases('## Voice\n- x\n\n## Banned phrases\n\nNever:\n\n- lock\n- night owls\n\n## Facts\n- y\n')
        self.assertEqual(got, ['lock', 'night owls'])
        self.assertIn('headliner', dc.banned_phrases())

    def test_lines_start_after_headline_and_dek(self):
        self.assertEqual(dc.article_lines('---\nsport: nba\n---\n# Head\n> Dek\n\nFirst.\nSecond.'), ['First.', 'Second.'])

    def test_rules(self):
        md = ('# H\n> D\n\n'
              'The headliner is here. Let\u2019s dive in.\n\n'
              '### Little Rock at Jacksonville \u00b7 1H\n\n'
              'LR won the 1H twice. That is where the numbers stack.\n\n'
              '### Houston at Texas\n\n'
              'Houston lost. That is where the numbers stack.')
        self.assertEqual(self.flags(md), [
            (1, 'Banned phrase: "headliner"'), (1, 'Banned phrase: "let\'s dive in"'),
            (5, '"where the numbers"'), (5, '1H in a sentence'), (5, 'Team code LR in a sentence'),
            (9, '"where the numbers"'), (9, 'Same closing sentence as line 5')])

    def test_clean_article(self):
        self.assertEqual(self.flags('# H\n> D\n\nLittle Rock won the first half at HOUSE.\n\n### LR at HOU\n\nThe total stayed low.'), [])


if __name__ == '__main__':
    unittest.main()
