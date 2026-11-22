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


class Matching(unittest.TestCase):
    def test_la_and_teams_outside_the_league(self):
        ev = {'commence_time': '2026-10-22T02:00:00Z', 'away_team': 'Los Angeles Lakers', 'home_team': 'Los Angeles Clippers'}
        pairs, missed = A.match('nba', [ev], [{'date': '2026-10-21', 'away': 'lal', 'home': 'lac', 'start': '2026-10-22T02:00Z'}])
        self.assertEqual((pairs[0][1]['home'], pairs[0][2], missed), ('lac', False, []))
        ev = {'commence_time': '2026-11-03T00:00:00Z', 'away_team': 'Bellarmine Knights', 'home_team': 'Louisville Cardinals'}
        game = {'date': '2026-11-02', 'away': 'espn-91', 'home': 'louisville-cardinals', 'start': '2026-11-03T00:00Z',
                'away_name': 'Bellarmine Knights', 'home_name': 'Louisville Cardinals'}
        self.assertEqual(len(A.match('ncaab', [ev], [game])[0]), 1)

    def test_college_names_the_api_spells_differently(self):
        """IUPUI is IU Indianapolis here; "St" is "State" inside a name."""
        ev = {'commence_time': '2026-11-15T00:00:00Z', 'away_team': 'IUPUI Jaguars', 'home_team': 'Morehead St Eagles'}
        game = {'date': '2026-11-14', 'away': 'iu-indianapolis-jaguars', 'home': 'morehead-state-eagles', 'start': '2026-11-15T00:00Z'}
        pairs, missed = A.match('ncaab', [ev], [game])
        self.assertEqual((len(pairs), missed), (1, []))
        self.assertEqual(A.api_name('wnba', 'Connecticut Sun'), 'Connecticut Sun')   # college only


def ml(e, a, h):
    return dict(e, bookmakers=[book('draftkings', h2h=[{'name': e['away_team'], 'price': a}, {'name': e['home_team'], 'price': h}])])


def fill(games, events, snaps, day='2026-11-14', event_odds=None):
    """backfill_oddsapi.fill_day for one NBA day with the API calls faked."""
    run = B.Run(None, False)
    run.files[('nba', 2027)], run.state = {'games': {}}, {}
    rep = {'filled': {}, 'no_market': {}, 'unmatched': [], 'unmatched_events': [], 'empty': [], 'big_ml': [], 'game_minutes': []}
    with mock.patch.object(A, 'historical_events', return_value={'data': events}), \
            mock.patch.object(A, 'historical_odds', side_effect=lambda sport, at, markets: {
                'timestamp': A.iso(at), 'data': snaps.get(A.iso(at), [])}), \
            mock.patch.object(A, 'historical_event_odds', side_effect=event_odds or (lambda *a: None)):
        B.fill_day(run, 'nba', 2027, day, games, rep)
    return run, rep


class FullGame(unittest.TestCase):
    def test_bulk_snapshot_takes_only_its_own_start_time(self):
        """The 8 PM snapshot also lists the 7 PM game, live by then: its in-play
        prices never become the 7 PM game's closing line."""
        early = {'id': 'e1', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        late = {'id': 'e2', 'commence_time': '2026-11-15T01:00:00Z', 'away_team': 'Denver Nuggets', 'home_team': 'Utah Jazz'}
        snaps = {'2026-11-14T23:55:00Z': [ml(early, -150, 130)],
                 '2026-11-15T00:55:00Z': [ml(early, 3500, -10000), ml(late, 110, -130)]}
        games = [({'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T00:00Z'}, [('game', 'ml', 'h2h')]),
                 ({'date': '2026-11-14', 'away': 'den', 'home': 'utah', 'start': '2026-11-15T01:00Z'}, [('game', 'ml', 'h2h')])]
        run, rep = fill(games, [early, late], snaps)
        saved = run.files[('nba', 2027)]['games']
        self.assertEqual(saved['2026-11-14|bos|mia']['segments']['game']['ml'], {'away': -150, 'home': 130, 'books': 1})
        self.assertEqual(saved['2026-11-14|bos|mia']['game_snapshot'], '2026-11-14T23:55:00Z')
        self.assertEqual(saved['2026-11-14|den|utah']['segments']['game']['ml'], {'away': 110, 'home': -130, 'books': 1})
        self.assertEqual(rep['big_ml'], [])

    def test_night_game_takes_its_own_snapshot_not_the_afternoon_one(self):
        """An 8 PM game is listed in the 12:55 PM snapshot too: it takes 7:55."""
        day = {'id': 'e1', 'commence_time': '2026-11-15T18:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        night = {'id': 'e2', 'commence_time': '2026-11-16T01:00:00Z', 'away_team': 'Denver Nuggets', 'home_team': 'Utah Jazz'}
        snaps = {'2026-11-15T17:55:00Z': [ml(day, -150, 130), ml(night, -120, 100)],
                 '2026-11-16T00:55:00Z': [ml(night, -180, 150)]}
        games = [({'date': '2026-11-15', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T18:00Z'}, [('game', 'ml', 'h2h')]),
                 ({'date': '2026-11-15', 'away': 'den', 'home': 'utah', 'start': '2026-11-16T01:00Z'}, [('game', 'ml', 'h2h')])]
        run, rep = fill(games, [day, night], snaps, day='2026-11-15')
        g = run.files[('nba', 2027)]['games']['2026-11-15|den|utah']
        self.assertEqual(g['segments']['game']['ml'], {'away': -180, 'home': 150, 'books': 1})
        self.assertEqual(g['game_snapshot'], '2026-11-16T00:55:00Z')
        self.assertEqual(sorted(rep['game_minutes']), [5, 5])

    def test_moved_start_and_the_fallback_call(self):
        """A start the snapshot moved (7:00 listed, 7:03 there) is still taken
        by id; a game the bulk pass misses gets its own call at its start - 5."""
        moved = {'id': 'e1', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        gone = {'id': 'e2', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': 'Denver Nuggets', 'home_team': 'Utah Jazz'}
        snaps = {'2026-11-14T23:55:00Z': [dict(ml(moved, -150, 130), commence_time='2026-11-15T00:03:00Z')]}
        games = [({'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T00:00Z'}, [('game', 'ml', 'h2h')]),
                 ({'date': '2026-11-14', 'away': 'den', 'home': 'utah', 'start': '2026-11-15T00:00Z'}, [('game', 'ml', 'h2h')])]
        calls = []

        def event_odds(sport, event_id, at, markets):
            calls.append((event_id, A.iso(at), markets))
            return {'timestamp': '2026-11-14T23:54:30Z', 'data': {'bookmakers': ml(gone, 120, -140)['bookmakers']}}
        run, rep = fill(games, [moved, gone], snaps, event_odds=event_odds)
        saved = run.files[('nba', 2027)]['games']
        self.assertEqual(saved['2026-11-14|bos|mia']['segments']['game']['ml']['away'], -150)
        self.assertEqual(calls, [('e2', '2026-11-14T23:55:00Z', ['h2h'])])
        self.assertEqual(saved['2026-11-14|den|utah']['segments']['game']['ml']['away'], 120)
        self.assertEqual(saved['2026-11-14|den|utah']['game_snapshot'], '2026-11-14T23:54:30Z')

    def test_unmatched_events_keep_the_api_names(self):
        stray = {'id': 'e9', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': 'UMKC Kangaroos', 'home_team': 'Nowhere Owls'}
        run, rep = fill([], [stray], {})
        self.assertEqual(rep['unmatched_events'], ['2026-11-14 UMKC Kangaroos @ Nowhere Owls'])

    def test_saved_full_game_lines_are_pregame(self):
        """No saved full-game moneyline has both sides plus (an in-play price),
        except a pick'em: the best prices across books can both be plus when
        the game is close to even (+115 / +102, ten books), so both sides
        +130 or less pass."""
        for path in glob.glob(os.path.join(ROOT, 'data_feed', 'oddsapi', 'history', '*', '*.json')):
            with open(path, encoding='utf-8') as f:
                games = json.load(f).get('games') or {}
            for key, g in games.items():
                ml = ((g.get('segments') or {}).get('game') or {}).get('ml')
                if ml:
                    self.assertFalse(ml['away'] > 0 and ml['home'] > 0 and max(ml['away'], ml['home']) > 130, f'{path}: {key} {ml}')


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
