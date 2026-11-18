"""
The site nav, the index pages' day, Betting Guides anchors and On Tap's
page titles (scripts/nav.py, front.py, guides.py, daily.py).
"""
import os
import re
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import daily  # noqa: E402
import front  # noqa: E402
import guides  # noqa: E402
import nav  # noqa: E402
import sports  # noqa: E402


def status():
    return [(sp, True, 'LIVE') for sp in sports.LAUNCHED]


class NavTest(unittest.TestCase):
    def tearDown(self):
        sports.PICKS_LIVE = False

    def test_no_picks_link_until_live(self):
        sports.PICKS_LIVE = False
        html = re.sub(r'<script\b.*?</script>', '', nav.header('', status()), flags=re.S)
        self.assertNotIn('picks/', html)
        sports.PICKS_LIVE = True
        html = nav.header('', status())
        self.assertIn('class="hn-link hn-picks"', html)
        self.assertIn('hm-pill gold', html)

    def test_page_order(self):
        sports.PICKS_LIVE = True
        self.assertEqual([s for s, _, _ in sports.page_links('nba')], ['picks', 'games', 'odds', 'trends', 'stats', 'teams'])
        sports.PICKS_LIVE = False
        self.assertEqual([s for s, _, _ in sports.page_links('nba')], ['games', 'odds', 'trends', 'stats', 'teams'])

    def test_bottom_bar_current(self):
        html = nav.header('../', status(), current='odds')
        bar = html[html.index('<nav class="bb"'):]
        self.assertIn('href="../odds/" aria-current="page"', bar)
        self.assertEqual(bar.count('aria-current'), 1)
        # a sport's Trends page lights the Trends tab
        bar = nav.bottom_bar('/', nav.SECTION_TAB.get('trends'))
        self.assertIn('href="/trends/" aria-current="page"', bar)

    def test_menu_has_no_learn(self):
        html = nav.header('', status())
        self.assertNotIn('learn/', html)
        self.assertIn('betting-guides/', html)


class HeadingTest(unittest.TestCase):
    def test_h1s(self):
        self.assertEqual(sports.h1('nhl', 'hub'), 'NHL First Period Betting')
        self.assertEqual(sports.h1('ncaab', 'trends'), 'College Basketball First Half Betting Trends')
        self.assertEqual(sports.h1('mlb', 'odds'), 'MLB First Inning & First Five Odds')
        self.assertEqual(sports.h1('nba', 'edges'), 'NBA First Quarter & First Half Edges: Closers & Faders')

    def test_titles(self):
        self.assertEqual(sports.sport_title('nhl', 'odds'), 'NHL First Period Odds Today | RTYB')
        self.assertEqual(sports.sport_title('nhl', 'teams'), 'NHL First Period Team Records | RTYB')
        # past 65 characters "Today" goes first
        long = sports.sport_title('ncaaf', 'trends')
        self.assertNotIn('This Week', long)
        self.assertEqual(front.INDEX['odds']['title'], 'First Period, Quarter & Half Odds Today | RTYB')

    def test_hottest_trends_need_55(self):
        self.assertEqual(front.TREND_MIN_RATE, 0.55)


class IndexDayTest(unittest.TestCase):
    def test_rolls_over_at_6am_et(self):
        # 5:59 AM ET on Nov 18 is still Nov 17's page; 6:00 AM is Nov 18's
        self.assertEqual(front.index_day(datetime(2026, 11, 18, 10, 59, tzinfo=timezone.utc)), '2026-11-17')
        self.assertEqual(front.index_day(datetime(2026, 11, 18, 11, 0, tzinfo=timezone.utc)), '2026-11-18')

    def test_week_label(self):
        self.assertEqual(front.week_label([('2026-11-19', {'wk': '2-12'})]), 'Week 12')
        self.assertEqual(front.week_label([]), '')


class GuidesTest(unittest.TestCase):
    def test_anchors(self):
        self.assertEqual(guides.anchor('3-Way Moneyline'), '3-way-moneyline')
        self.assertEqual(guides.anchor('BTTS'), 'btts')
        html = guides.glossary_html('## Push\n\nThe line lands exactly.\n\n## BTTS\n\nBoth teams score.')
        self.assertIn('<h2 id="push">Push</h2>', html)
        self.assertIn('<h2 id="btts">BTTS</h2>', html)

    def test_sport_titles(self):
        self.assertEqual(guides.sport_title(sports.BY_KEY['nhl']), 'NHL First Period Betting Guide')
        self.assertEqual(guides.sport_title(sports.BY_KEY['nba']), 'NBA First Quarter & First Half Betting Guide')

    def test_missing_file_is_noindexed(self):
        _, body, noindex = guides.article('Units', None, 'Betting Guides', '../')
        self.assertTrue(noindex)
        self.assertIn(guides.COMING, _)


class OnTapTitleTest(unittest.TestCase):
    def test_all_preview_title(self):
        p = {'kind': 'preview', 'sport': daily.ALL, 'date': '2026-11-17', 'covers': ['nba', 'nhl'], 'title': 'x'}
        self.assertEqual(daily.page_title(p), 'On Tap, Tue Nov 17: NBA First Quarter & NHL First Period Preview | RTYB')

    def test_paths(self):
        self.assertEqual(daily.INDEX, 'on-tap')


if __name__ == '__main__':
    unittest.main()
