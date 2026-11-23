"""
The admin's Books tab (data_admin/books.json, scripts/books.py): hiding a
book removes its column everywhere, a book out of the best price never sets
or outlines it, and the saved order is the column order. Offshore books
never link out; a saved affiliate URL is every one of the book's links.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import books  # noqa: E402
import sport_build  # noqa: E402
import test_odds_past_days as past  # noqa: E402

ML, ATS = past.ML, past.ATS

ROWS = [{'id': 'betrivers', 'name': 'BetRivers', 'group': 'Sportsbook', 'show': True, 'best': True, 'link': ''},
        {'id': '1', 'name': 'DK', 'group': 'Sportsbook', 'show': True, 'best': True, 'link': ''}]


def using(rows):
    return mock.patch.object(books, '_settings', books.Settings(rows))


class Books(unittest.TestCase):
    build = past.PastDays.build   # one game's Odds page day and index

    def test_hidden_book_is_gone_everywhere(self):
        rows = [dict(ROWS[0], show=False), ROWS[1]]
        with using(rows):
            g, index = self.build('wnba', {'1q': {'ml': ML, 'ats': ATS}})
        self.assertNotIn('betrivers', g['books']['1q']['ml'])
        self.assertNotIn('betrivers', index['order'])
        self.assertNotIn('betrivers', index['sources'])

    def test_order_is_the_column_order(self):
        with using(ROWS):
            _, index = self.build('wnba', {'1q': {'ml': ML}})
        self.assertEqual(index['order'], ['betrivers', '1'])
        with using(list(reversed(ROWS))):
            _, index = self.build('wnba', {'1q': {'ml': ML}})
        self.assertEqual(index['order'], ['1', 'betrivers'])

    def test_best_off_never_outlines(self):
        rows = [dict(ROWS[0], best=False), ROWS[1]]
        with using(rows):
            _, index = self.build('wnba', {'1q': {'ml': ML}})
            # BetRivers has the better away price (+155), but can't set the best
            best = sport_build.best_price('ml', {'1': ML['draftkings'], 'betrivers': ML['betrivers']})
        self.assertEqual(index['sources']['betrivers'].get('nb'), 1)   # sport.js: never outlined
        self.assertNotIn('nb', index['sources']['1'])
        self.assertEqual(best['away'], 150)


class Settings(unittest.TestCase):
    def test_offshore_never_links(self):
        cfg = books.Settings([{'id': 'bovada', 'name': 'Bovada', 'group': 'Offshore', 'show': True, 'best': True, 'link': ''}])
        self.assertFalse(cfg.linked('bovada'))
        out = cfg.filter({'game': {'ml': {'bovada': {'away': {'price': 100, 'link': 'https://x'}}}}})
        self.assertNotIn('link', out['game']['ml']['bovada']['away'])

    def test_a_saved_url_links_every_cell_there(self):
        url = 'https://partner.example.com/rtyb?ref=chris'
        cfg = books.Settings([dict(ROWS[0], link=url), ROWS[1]])
        out = cfg.filter({'1q': {'ml': {'betrivers': {'away': {'price': 150}, 'home': {'price': -170}},
                                        '1': {'away': {'price': 140, 'link': 'https://www.gambly.com/x?utm_campaign=rtyb'}}}}})
        self.assertEqual(out['1q']['ml']['betrivers']['away']['link'], url)
        self.assertEqual(out['1q']['ml']['betrivers']['home']['link'], url)
        # empty: the Gambly link stays (with its partner code)
        self.assertEqual(out['1q']['ml']['1']['away']['link'], 'https://www.gambly.com/x?utm_campaign=rtyb')
        # offshore: locked empty, never links
        cfg = books.Settings([{'id': 'bovada', 'name': 'Bovada', 'group': 'Offshore', 'show': True, 'best': True, 'link': url}])
        self.assertEqual(cfg.url('bovada'), '')

    def test_unlisted_books_follow_the_listed_ones(self):
        cfg = books.Settings(ROWS)
        self.assertEqual(cfg.order(['20', '1', 'betrivers', '4'], sorted), ['betrivers', '1', '20', '4'])

    def test_the_saved_file_is_valid(self):
        rows = books.read()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(set(r), {'id', 'name', 'group', 'show', 'best', 'link'})
            self.assertIn(r['group'], books.GROUPS)
            self.assertIsInstance(r['link'], str)
            self.assertTrue(r['link'] == '' or r['link'].startswith('https://'))
            if r['group'] == 'Offshore':
                self.assertEqual(r['link'], '')


class Logos(unittest.TestCase):
    def test_a_dropped_in_file_is_the_logo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'assets', 'books'))
            with mock.patch.object(sport_build, 'ROOT', d):
                self.assertIsNone(sport_build.book_logo('betrivers'))   # none: the page shows the name badge
                open(os.path.join(d, 'assets', 'books', 'betrivers.webp'), 'wb').close()
                self.assertEqual(sport_build.book_logo('betrivers'), 'assets/books/betrivers.webp')

    def test_unabated_thumbnail_saves_under_the_odds_api_id_unless_chris_has_one(self):
        import tempfile
        import fetch_odds_unabated as U
        from datetime import datetime, timezone
        src = [{'id': 99, 'name': 'Hard Rock', 'thumbnailUrl': 'https://x.test/hr.png', 'modifiedOn': '1'}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(U, 'LOGO_DIR', d), \
                mock.patch.object(U, 'LOGO_MANIFEST', os.path.join(d, 'sources.json')):
            U.download_logos(src, datetime.now(timezone.utc), fetch=lambda url: b'png')
            self.assertTrue(os.path.exists(os.path.join(d, 'hardrockbet.png')))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(U, 'LOGO_DIR', d), \
                mock.patch.object(U, 'LOGO_MANIFEST', os.path.join(d, 'sources.json')):
            with open(os.path.join(d, 'hardrockbet.svg'), 'w') as f:
                f.write('<svg/>')
            U.download_logos(src, datetime.now(timezone.utc), fetch=lambda url: b'png')
            self.assertFalse(os.path.exists(os.path.join(d, 'hardrockbet.png')))   # Chris's file wins


if __name__ == '__main__':
    unittest.main()
