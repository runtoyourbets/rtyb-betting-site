"""The Odds API backfill (scripts/backfill_oddsapi.py): the closing-line rule,
the merge order (admin > Unabated > The Odds API) and no key in any file."""
import glob
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import backfill_oddsapi as B  # noqa: E402
import build_site  # noqa: E402
import oddsapi as A  # noqa: E402
import sport_build  # noqa: E402
from fetch_odds_unabated import best_of  # noqa: E402

AWAY, HOME = 'Boston Celtics', 'Miami Heat'


def book(key, **markets):
    return {'key': key, 'markets': [{'key': k, 'outcomes': v} for k, v in markets.items()]}


BOOKMAKERS = [
    book('draftkings',
         h2h_q1=[{'name': AWAY, 'price': -120}, {'name': HOME, 'price': 100}],
         spreads_q1=[{'name': AWAY, 'point': -1.5, 'price': -110}, {'name': HOME, 'point': 1.5, 'price': -110}],
         totals_q1=[{'name': 'Over', 'point': 58.5, 'price': -112}, {'name': 'Under', 'point': 58.5, 'price': -108}]),
    book('fanduel',
         h2h_q1=[{'name': AWAY, 'price': -125}, {'name': HOME, 'price': 105}],
         spreads_q1=[{'name': AWAY, 'point': -1.5, 'price': -105}, {'name': HOME, 'point': 1.5, 'price': -115},
                     {'name': AWAY, 'point': -4.5, 'price': 170}, {'name': HOME, 'point': 4.5, 'price': -230}],
         totals_q1=[{'name': 'Over', 'point': 58.5, 'price': -110}, {'name': 'Under', 'point': 58.5, 'price': -110}]),
    book('betmgm',
         spreads_q1=[{'name': AWAY, 'point': -2.5, 'price': 105}, {'name': HOME, 'point': 2.5, 'price': -125}],
         totals_q1=[{'name': 'Over', 'point': 59.5, 'price': -105}, {'name': 'Under', 'point': 59.5, 'price': -115}]),
    book('someexchange', h2h_q1=[{'name': AWAY, 'price': 500}, {'name': HOME, 'price': 500}]),   # not in BOOKS
]
KEYS = [('1q', 'ml', 'h2h_q1'), ('1q', 'ats', 'spreads_q1'), ('1q', 'total', 'totals_q1')]


class Closing(unittest.TestCase):
    def test_same_answer_as_best_of(self):
        lines, books = B.closing('nba', BOOKMAKERS, KEYS, AWAY, HOME)
        rows = {
            'ml': {'draftkings': {'away': {'price': -120}, 'home': {'price': 100}},
                   'fanduel': {'away': {'price': -125}, 'home': {'price': 105}}},
            'ats': {'draftkings': {'away': {'line': -1.5, 'price': -110}, 'home': {'line': 1.5, 'price': -110}},
                    'fanduel': {'away': {'line': -1.5, 'price': -105}, 'home': {'line': 1.5, 'price': -115}},
                    'betmgm': {'away': {'line': -2.5, 'price': 105}, 'home': {'line': 2.5, 'price': -125}}},
            'total': {'draftkings': {'line': 58.5, 'over': {'price': -112}, 'under': {'price': -108}},
                      'fanduel': {'line': 58.5, 'over': {'price': -110}, 'under': {'price': -110}},
                      'betmgm': {'line': 59.5, 'over': {'price': -105}, 'under': {'price': -115}}},
        }
        for market, r in rows.items():
            self.assertEqual(books['1q'][market], r)   # FanDuel's alternate -4.5 isn't its main line
            want = dict(best_of(market, r, ()), books=len(r))
            self.assertEqual(lines['1q'][market], want)
        self.assertEqual(lines['1q']['ml'], {'away': -120, 'home': 105, 'books': 2})
        self.assertEqual(lines['1q']['ats']['away'], {'line': -1.5, 'price': -105})
        self.assertEqual(lines['1q']['total'], {'line': 58.5, 'over': -110, 'under': -108, 'books': 3})

    def test_flipped_event(self):
        """Our away team is the API's home team: sides follow the names."""
        lines, _ = B.closing('nba', BOOKMAKERS[:1], KEYS[:1], HOME, AWAY)
        self.assertEqual(lines['1q']['ml'], {'away': 100, 'home': -120, 'books': 1})

    def test_btts_from_one_book(self):
        bm = [book('fanduel', btts_p1=[{'name': 'Yes', 'price': 172}, {'name': 'No', 'price': -225}])]
        lines, _ = B.closing('nhl', bm, [('1p', 'btts', 'btts_p1')], AWAY, HOME)
        self.assertEqual(lines['1p']['btts'], {'yes': 172, 'no': -225, 'books': 1})

    def test_nrfi_only_at_half_a_run(self):
        bm = [book('draftkings', totals_1st_1_innings=[{'name': 'Over', 'point': 0.5, 'price': 110}, {'name': 'Under', 'point': 0.5, 'price': -140}]),
              book('fanduel', totals_1st_1_innings=[{'name': 'Over', 'point': 1.5, 'price': 300}, {'name': 'Under', 'point': 1.5, 'price': -500}])]
        lines, books = B.closing('mlb', bm, [('1i', 'nrfi_yrfi', 'totals_1st_1_innings')], AWAY, HOME)
        self.assertEqual(lines['1i']['nrfi_yrfi'], {'nrfi': -140, 'yrfi': 110, 'books': 1})
        self.assertEqual(list(books['1i']['nrfi_yrfi']), ['draftkings'])

    def test_no_3way_rows_in_a_2way_market(self):
        bm = [book('draftkings', h2h_1st_5_innings=[{'name': AWAY, 'price': 150}, {'name': HOME, 'price': 120}, {'name': 'Draw', 'price': 450}])]
        lines, _ = B.closing('mlb', bm, [('f5', 'ml', 'h2h_1st_5_innings')], AWAY, HOME)
        self.assertEqual(lines, {})


class Merge(unittest.TestCase):
    def test_priority_market_by_market(self):
        def game(segs):
            return {'k': {'date': 'd', 'away': 'a', 'home': 'h', 'segments': segs}}
        admin = game({'1h': {'ml': {'away': 100, 'home': -120}, 'total': None}})
        feed = game({'1h': {'ml': {'away': 130, 'home': -150}, 'total': {'line': 110.5, 'over': -110, 'under': -110}}})
        api = game({'1h': {'ml': {'away': 140, 'home': -160}, 'total': {'line': 111.5, 'over': -105, 'under': -115},
                           'ats': {'away': {'line': 3.5, 'price': -110}, 'home': {'line': -3.5, 'price': -110}}},
                    '1q': {'ml': {'away': 120, 'home': -140}}})
        segs = sport_build.merge_odds(admin, feed, api)['k']['segments']
        self.assertEqual(segs['1h']['ml'], {'away': 100, 'home': -120})      # admin
        self.assertEqual(segs['1h']['total']['line'], 110.5)                  # Unabated
        self.assertEqual(segs['1h']['ats']['away']['line'], 3.5)              # The Odds API
        self.assertEqual(segs['1q']['ml'], {'away': 120, 'home': -140})
        only = sport_build.merge_odds({}, {}, api)['k']
        self.assertEqual((only['away'], only['home']), ('a', 'h'))

    def test_history_files_read_without_book_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, 'data_feed', 'oddsapi', 'history', 'nhl')
            os.makedirs(d)
            with open(os.path.join(d, '2027.json'), 'w') as f:
                json.dump({'games': {'2026-11-14|SEA|CAR': {'date': '2026-11-14', 'away': 'SEA', 'home': 'CAR', 'segments': {
                    '1p': {'ml': {'away': 120, 'home': -140, 'books': 6}, 'btts': {'yes': 172, 'no': -225, 'books': 1},
                           'total': {'line': 1.5, 'over': -150, 'under': 125, 'books': 7}},
                    'game': {'ml': {'away': 150, 'home': -170, 'books': 10}}}}}}, f)
            with mock.patch.object(sport_build, 'ROOT', tmp):
                got = sport_build.oddsapi_odds('nhl', {'1p'})
        segs = got['2026-11-14|SEA|CAR']['segments']
        self.assertEqual(list(segs), ['1p'])
        self.assertEqual(segs['1p']['ml'], {'away': 120, 'home': -140})
        self.assertEqual(build_site.nhl_oddsapi('2026-11-14|SEA|CAR', got), {
            'ml': {'SEA': 120, 'CAR': -140}, 'totals': {'1.5': {'over': -150, 'under': 125}},
            'btts_yes': 172, 'btts_no': -225})
        games = [{'away': 'SEA', 'home': 'CAR', 'odds': {'ml': {'SEA': 200, 'CAR': -240}}}]
        build_site.fill_from_oddsapi(games, lambda g: '2026-11-14|SEA|CAR', got)
        self.assertEqual(games[0]['odds']['ml'], {'SEA': 200, 'CAR': -240})   # the saved line stays
        self.assertEqual(games[0]['odds']['btts_yes'], 172)


class NoKey(unittest.TestCase):
    def test_usage_log_has_no_key_or_url(self):
        class Resp(io.BytesIO):
            headers = {'x-requests-last': '30', 'x-requests-remaining': '4990000'}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {'ODDS_API_KEY': 'secret-test-key'}), \
                mock.patch.object(A, 'OUT_DIR', tmp), mock.patch.object(A, 'USAGE', os.path.join(tmp, 'usage.jsonl')), \
                mock.patch.object(A.urllib.request, 'urlopen', return_value=Resp(b'{"data": []}')), \
                mock.patch.dict(A._state, {'used': 0, 'remaining': None}):
            A.historical_odds('nba', A.parse('2026-11-15T00:30:00Z'), ['h2h'])
            with open(os.path.join(tmp, 'usage.jsonl')) as f:
                text = f.read()
        self.assertIn('"credits": 30', text)
        self.assertNotIn('secret-test-key', text)
        self.assertNotIn('apiKey', text)
        self.assertNotIn('http', text)

    def test_committed_files_have_no_key_or_links(self):
        for path in glob.glob(os.path.join(ROOT, 'data_feed', 'oddsapi', '**', '*.json*'), recursive=True):
            with open(path, encoding='utf-8') as f:
                text = f.read()
            self.assertNotIn('apiKey', text, path)
            self.assertNotIn('http', text, path)


if __name__ == '__main__':
    unittest.main()
