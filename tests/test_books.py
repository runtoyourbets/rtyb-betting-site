"""
The admin's Books tab (data_admin/books.json, scripts/books.py): hiding a
book removes its column everywhere, a book out of the best price never sets
or outlines it, and the saved order is the column order. Offshore books
never link out.
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

ROWS = [{'id': 'betrivers', 'name': 'BetRivers', 'group': 'Sportsbook', 'show': True, 'best': True, 'link': True},
        {'id': '1', 'name': 'DK', 'group': 'Sportsbook', 'show': True, 'best': True, 'link': True}]


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
        cfg = books.Settings([{'id': 'bovada', 'name': 'Bovada', 'group': 'Offshore', 'show': True, 'best': True, 'link': True}])
        self.assertFalse(cfg.linked('bovada'))
        out = cfg.filter({'game': {'ml': {'bovada': {'away': {'price': 100, 'link': 'https://x'}}}}})
        self.assertNotIn('link', out['game']['ml']['bovada']['away'])

    def test_unlisted_books_follow_the_listed_ones(self):
        cfg = books.Settings(ROWS)
        self.assertEqual(cfg.order(['20', '1', 'betrivers', '4'], sorted), ['betrivers', '1', '20', '4'])

    def test_the_saved_file_is_valid(self):
        rows = books.read()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(set(r), {'id', 'name', 'group', 'show', 'best', 'link'})
            self.assertIn(r['group'], books.GROUPS)
            if r['group'] == 'Offshore':
                self.assertFalse(r['link'])


if __name__ == '__main__':
    unittest.main()
