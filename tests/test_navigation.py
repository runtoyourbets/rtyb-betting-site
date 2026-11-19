"""
The site nav, the index pages' day, Betting Guides anchors and Preview's
page titles (scripts/nav.py, front.py, guides.py, preview.py).
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
    def test_picks_link_everywhere(self):
        # Picks shows (gold) in every menu; while PICKS_LIVE is off it goes to Preview
        self.assertFalse(sports.PICKS_LIVE)
        html = nav.header('', status())
        self.assertIn('class="hn-link hn-gold" href="preview/">Picks', html)
        self.assertIn('class="hm-pill gold" href="nhl/preview/">Picks', html)
        self.assertIn('class="hn-picks-pill" href="preview/"', html)

    def test_page_order(self):
        self.assertEqual([s for s, _, _ in sports.page_links('nba')], ['picks', 'games', 'odds', 'trends', 'stats', 'teams'])

    def test_main_menu(self):
        self.assertEqual([k for k, _ in sports.MAIN_MENU], ['sports', 'matchups', 'odds', 'trends', 'stats', 'picks'])

    def test_no_on_tap(self):
        self.assertTrue(sports.PREVIEW_LIVE)
        html = nav.header('', status(), current='matchups')
        self.assertNotIn('on-tap', html)
        self.assertNotIn('On Tap', re.sub(r'<script\b.*?</script>', '', html, flags=re.S))

    def test_bottom_bar_current(self):
        html = nav.header('../', status(), current='odds')
        bar = html[html.index('<nav class="bb"'):]
        self.assertIn('href="../odds/" aria-current="page"', bar)
        self.assertEqual(bar.count('aria-current'), 1)
        self.assertEqual(re.findall(r'<span>(\w+)</span>', bar), ['Matchups', 'Odds', 'Trends', 'Stats'])
        # a sport's Stats page lights the Stats tab
        bar = nav.bottom_bar('/', nav.SECTION_TAB.get('stats'))
        self.assertIn('href="/stats/" aria-current="page"', bar)

    def test_rows(self):
        # home: no row 2; an index page: the section, All and the sports to the same section
        self.assertNotIn('class="hr2"', nav.header('', status()))
        html = nav.header('../', status(), current='odds')
        self.assertIn('<p class="hr2-label">Odds</p>', html)
        self.assertIn('href="../nhl/odds/"', html)
        # a sport page: its six links, the current one marked
        row = nav.sport_row('/', sports.BY_KEY['nhl'], 'games')
        self.assertEqual(len(re.findall(r'class="hr2-link[ "]', row)), 6)
        self.assertIn('href="/nhl/matchups/" aria-current="page"', row)

    def test_menu_has_no_learn(self):
        html = nav.header('', status())
        self.assertNotIn('learn/', html)
        self.assertIn('betting-guides/', html)


class SettingsTest(unittest.TestCase):
    def test_defaults_and_order(self):
        self.assertEqual([s['key'] for s in sports.SPORTS], ['nhl', 'nba', 'wnba', 'mlb', 'ncaab', 'nfl', 'ncaaf'])
        self.assertEqual(sports.BY_KEY['ncaab']['menu_label'], 'College Basketball')
        # every sport "on": WNBA and MLB stay on the site out of season
        self.assertTrue(sports.is_launched('mlb'))

    def test_bad_file_falls_back(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            f.write('{not json')
        self.assertEqual(sports.load_settings(f.name)['switches']['FOOTER'], 'home-only')
        os.remove(f.name)


class CodeTest(unittest.TestCase):
    def test_college_list(self):
        self.assertEqual(sports.college_code('ncaab', 'chattanooga-mocs', 'UTC'), 'CHAT')
        self.assertEqual(sports.college_code('nba', 'utah', 'UTAH'), 'UTA')
        sports.college_code('ncaab', 'not-a-team', 'ZZZ')
        self.assertIn(('ncaab', 'not-a-team', 'ZZZ'), sports.COLLEGE_FALLBACKS)


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


class PreviewTitleTest(unittest.TestCase):
    def test_titles(self):
        import preview
        self.assertEqual(preview.title('all', 'Suns at Kings'), 'First Period, Quarter & Half Betting Preview: Suns at Kings | RTYB')
        self.assertEqual(preview.title('nba', 'X'), 'NBA First Quarter & First Half Betting Preview: X | RTYB')
        self.assertEqual(preview.title('nhl', 'X'), 'NHL First Period Betting Preview: X | RTYB')
        self.assertEqual(preview.title('ncaab', 'X'), 'College Basketball First Half Betting Preview: X | RTYB')
        self.assertEqual(preview.title('ncaaf', 'X'), 'College Football First Quarter & First Half Betting Preview: X | RTYB')
        self.assertEqual(preview.title('mlb', 'X'), 'MLB First Inning & First Five Betting Preview: X | RTYB')

    def test_paths(self):
        import preview
        self.assertEqual(preview.page_dir('all', '2026-11-18'), 'preview/2026-11-18/')
        self.assertEqual(preview.page_dir('ncaab'), 'college-basketball/preview/')
        self.assertEqual(sports.preview_path(sports.BY_KEY['nba']), '/nba/preview/')

    def test_old_switch_name_still_reads(self):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            f.write('{"switches": {"ON_TAP_LIVE": false}}')
        sw = sports.load_settings(f.name)['switches']
        os.remove(f.name)
        self.assertFalse(sw['PREVIEW_LIVE'])
        self.assertNotIn('ON_TAP_LIVE', sw)

if __name__ == '__main__':
    unittest.main()
