"""
The Odds API's live feed (scripts/fetch_odds_theoddsapi.py): the same shape
as the Unabated file and through merge_odds, odds frozen at the start, the
closing capture, the daily budget and the next-day break lines. The API is
faked; nothing here calls it.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fetch_odds_theoddsapi as F  # noqa: E402
import fetch_odds_unabated as U  # noqa: E402
import oddsapi as A  # noqa: E402
import sport_build  # noqa: E402

NOW = datetime(2026, 11, 22, 23, 0, tzinfo=timezone.utc)
AWAY, HOME = 'Boston Celtics', 'Miami Heat'
GAME = {'date': '2026-11-22', 'away': 'bos', 'home': 'mia', 'start': '2026-11-23T00:30Z'}
EVENT = {'id': 'e1', 'commence_time': '2026-11-23T00:30:00Z', 'away_team': AWAY, 'home_team': HOME}


def odds(away=-150, home=130):
    def book(key):
        return {'key': key, 'markets': [
            {'key': 'h2h_q1', 'outcomes': [{'name': AWAY, 'price': away}, {'name': HOME, 'price': home}]},
            {'key': 'totals_q1', 'outcomes': [{'name': 'Over', 'point': 58.5, 'price': -110}, {'name': 'Under', 'point': 58.5, 'price': -110}]},
            {'key': 'h2h', 'outcomes': [{'name': AWAY, 'price': -200}, {'name': HOME, 'price': 170}]}]}
    return {'bookmakers': [book('draftkings'), book('espnbet')]}


class Live(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        out = self.tmp.name
        self.patches = [mock.patch.object(A, 'OUT_DIR', out), mock.patch.object(A, 'USAGE', os.path.join(out, 'usage.jsonl')),
                        mock.patch.object(F, 'HISTORY_DIR', os.path.join(out, 'history')),
                        mock.patch.object(F, 'STATUS', os.path.join(out, 'status.json')),
                        mock.patch.object(F, 'BREAKS', os.path.join(out, 'breaks.json')),
                        mock.patch.object(F, 'UNABATED_DIR', os.path.join(out, 'unabated')),
                        mock.patch.object(F, 'live_keys', lambda sport: [('1q', 'ml', 'h2h_q1'), ('1q', 'total', 'totals_q1'),
                                                                         ('game', 'ml', 'h2h')]),
                        mock.patch.object(F, 'shown_games', lambda sport, now: [dict(GAME, _start=A.parse(GAME['start']))]
                                          if A.parse(GAME['start']) > now else [])]
        for p in self.patches:
            p.start()
        self.calls = []

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def pull(self, now, hourly, data=None):
        def event_odds(sport, event_id, markets, books=None):
            self.calls.append((event_id, now))
            self.books = books
            return data or odds()
        with mock.patch.object(A, 'events', return_value=[EVENT]), mock.patch.object(A, 'event_odds', side_effect=event_odds):
            F.pull_sport('nba', now, hourly)
        return U.read_json(os.path.join(self.tmp.name, 'nba.json'), {})

    def test_same_shape_as_unabated_and_merges(self):
        doc = self.pull(NOW, True)
        self.assertLessEqual({'updated', 'status', 'unmatched', 'games'}, set(doc))
        g = doc['games']['2026-11-22|bos|mia']
        self.assertLessEqual({'date', 'away', 'home', 'start', 'segments', 'books', 'opens'}, set(g))
        self.assertEqual(g['segments']['1q']['ml'], {'away': -150, 'home': 130})
        self.assertEqual(set(g['books']['1q']['ml']), {'draftkings', 'espnbet'})
        self.assertNotIn('link', json.dumps(g))   # no links: the Odds page's book links stay Gambly's
        with mock.patch.object(sport_build, 'ROOT', self.tmp.name + '/x'), \
                mock.patch.object(sport_build, 'oddsapi_live', lambda sport: doc['games']):
            merged = sport_build.merge_odds({}, {}, sport_build.oddsapi_odds('nba', {'1q'}))
        self.assertEqual(merged['2026-11-22|bos|mia']['segments']['1q']['ml'], {'away': -150, 'home': 130})
        # the admin and Unabated still win
        merged = sport_build.merge_odds({'2026-11-22|bos|mia': {'segments': {'1q': {'ml': {'away': -140, 'home': 120}}}}},
                                        {}, {'2026-11-22|bos|mia': {'segments': g['segments']}})
        self.assertEqual(merged['2026-11-22|bos|mia']['segments']['1q']['ml'], {'away': -140, 'home': 120})

    def test_odds_freeze_at_the_start(self):
        self.pull(NOW, True)
        after = A.parse(GAME['start']) + timedelta(minutes=5)
        doc = self.pull(after, True, data=odds(-3000, 1500))
        g = doc['games']['2026-11-22|bos|mia']
        self.assertEqual(g['segments']['1q']['ml'], {'away': -150, 'home': 130})
        self.assertNotIn('books', g)   # moved to the day's history file
        day = U.read_json(os.path.join(self.tmp.name, 'history', 'nba', '2026-11-22.json'), {})
        self.assertIn('draftkings', day['games']['bos|mia']['close']['1q']['ml'])
        self.assertEqual(len(self.calls), 1)

    def test_closing_capture(self):
        self.pull(NOW, True)
        start = A.parse(GAME['start'])
        self.pull(start - timedelta(minutes=30), False)   # not within 20 minutes: no call
        self.assertEqual(len(self.calls), 1)
        self.pull(start - timedelta(minutes=12), False)   # within 20, last pull 78 minutes ago
        self.assertEqual(len(self.calls), 2)
        self.pull(start - timedelta(minutes=3), False)    # pulled 9 minutes ago
        self.assertEqual(len(self.calls), 2)

    def test_daily_share(self):
        with open(A.USAGE, 'w') as f:
            for credits, job in ((6000, 'live'), (90000, None)):   # the backfill's rows don't count
                f.write(json.dumps({'time': NOW.isoformat(), 'credits': credits, 'job': job}) + '\n')
        self.assertEqual(F.live_usage(NOW), (6000, 6000))
        self.assertEqual(round(F.daily_share(NOW)), 5000)   # 150,000 over November's 30 days

    def test_break_seen_then_captured_next_morning(self):
        live = {'2026-11-22|bos|mia': dict(GAME, state='in', detail='Halftime')}
        with mock.patch.object(F, 'season_games', lambda sport: live):
            self.assertEqual(F.note_breaks(NOW, ['nba']), 1)
            self.assertEqual(F.note_breaks(NOW + timedelta(minutes=10), ['nba']), 0)   # the first sighting stays
        breaks = U.read_json(F.BREAKS, {})
        self.assertEqual(breaks['nba']['2026-11-22|bos|mia'], {'break': 'half', 'seen_at': NOW.isoformat(timespec='seconds')})
        U.write_json(os.path.join(self.tmp.name, 'nba.json'), {'games': {'2026-11-22|bos|mia': dict(GAME, event='e1')}})
        final = {'2026-11-22|bos|mia': dict(GAME, state='final')}
        asked = []

        def hist_odds(sport, event, at, markets):
            asked.append(A.iso(at))
            if len(asked) < 2:
                return {'timestamp': A.iso(at), 'data': {'away_team': AWAY, 'home_team': HOME, 'bookmakers': []}}
            return {'timestamp': A.iso(at), 'data': {'away_team': AWAY, 'home_team': HOME, 'bookmakers': [
                {'key': 'fanduel', 'markets': [{'key': 'h2h_h2', 'outcomes': [{'name': AWAY, 'price': 120}, {'name': HOME, 'price': -140}]}]}]}}
        morning = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)   # 7 AM ET
        with mock.patch.object(F, 'season_games', lambda sport: final), \
                mock.patch.object(F.B, 'seasons_for', lambda sport: {'this': (2027, [])}), \
                mock.patch.object(A, 'historical_event_odds', side_effect=hist_odds):
            report = F.capture_breaks(morning, ['nba'])
            self.assertIsNone(F.capture_breaks(morning + timedelta(minutes=10), ['nba']))   # once a day
        self.assertEqual(report['nba'], {'saved': 1, 'no_line': 0})
        self.assertEqual(asked, ['2026-11-22T23:00:00Z', '2026-11-22T23:05:00Z'])   # seen_at, then +5
        row = U.read_json(os.path.join(self.tmp.name, 'history', 'nba', '2027.json'), {})['games']['2026-11-22|bos|mia']
        self.assertEqual(row['segments']['2h']['ml'], {'away': 120, 'home': -140, 'books': 1})


class LiveBooks(Live):
    """The live pull asks LIVE_BOOKS; DraftKings and FanDuel join only when
    Unabated has no price from one of them for a game starting soon."""
    def unabated(self, books):
        U.write_json(os.path.join(self.tmp.name, 'unabated', 'nba.json'),
                     {'games': {'k': dict(GAME, books={'1q': {'ml': {b: {} for b in books}}})}})

    def swapped(self):
        return {'bookmakers': odds()['bookmakers'] + [dict(odds()['bookmakers'][0], key='ballybet')]}

    def test_unabated_has_both_no_safety_books(self):
        self.unabated(['1', '2', '20'])
        doc = self.pull(NOW, True, self.swapped())
        self.assertEqual(self.books, A.LIVE_BOOKS)
        self.assertEqual(len(A.LIVE_BOOKS), 10)
        self.assertNotIn('safety', doc['status'])
        self.assertEqual(sorted(doc['games']['2026-11-22|bos|mia']['books']['1q']['ml']), ['ballybet', 'espnbet'])   # DraftKings' row isn't kept

    def test_missing_fanduel_adds_draftkings_and_fanduel(self):
        self.unabated(['1', '20'])
        doc = self.pull(NOW, True, self.swapped())
        self.assertEqual(self.books, A.LIVE_BOOKS + ('draftkings', 'fanduel'))
        self.assertEqual(A.regions(self.books), 2)
        self.assertEqual(doc['status']['safety'], 1)
        self.assertIn('draftkings', doc['games']['2026-11-22|bos|mia']['books']['1q']['ml'])

    def test_not_starting_soon_no_safety_books(self):
        self.unabated([])
        self.pull(NOW - timedelta(hours=7), True, self.swapped())
        self.assertEqual(self.books, A.LIVE_BOOKS)

    def test_new_books_map_to_sources(self):
        for b in ('ballybet', 'fliff', 'betparx', 'rebet', 'betus'):
            self.assertIn(b, A.LIVE_BOOKS)
            self.assertEqual(sport_build.ODDSAPI_BOOKS[b], b)
        self.assertEqual(sport_build.books_cfg.Settings().row('betus')['group'], 'Offshore')
        self.assertFalse(sport_build.books_cfg.Settings().counts('betus'))


class SeasonFilesOnly(unittest.TestCase):
    def test_day_files_are_not_read_as_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, 'data_feed', 'oddsapi', 'history', 'nba')
            os.makedirs(d)
            U.write_json(os.path.join(d, '2027.json'), {'games': {'k': {'segments': {'1q': {'ml': {'away': 1, 'home': 2}}}}}})
            U.write_json(os.path.join(d, '2026-11-22.json'), {'games': {'bos|mia': {'close': {}}}})
            with mock.patch.object(sport_build, 'ROOT', tmp):
                self.assertEqual([os.path.basename(p) for p in sport_build.oddsapi_seasons('nba')], ['2027.json'])


if __name__ == '__main__':
    unittest.main()
