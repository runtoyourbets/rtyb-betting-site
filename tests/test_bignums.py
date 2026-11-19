"""The Big Numbers (scripts/bignums.py): the consensus line, the best price
at it, and the tie-breaks."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import bignums  # noqa: E402
import front  # noqa: E402
import sports  # noqa: E402


class FakeSport(front.Sport):
    def __init__(self, key):
        sp = sports.BY_KEY[key]
        self.sp, self.key, self.label, self.weekly, self.segments = sp, key, sp['label'], False, sp['segments']
        self.doc, self.sources = {'sport': key, 'segments': sp['segments'], 'games': {}, 'teams': {}}, {}


def game(gid, start, ats=None, ml=None, total=None):
    rows = {}
    for b in ('dk', 'fd', 'mgm'):
        if ats:
            line, price = ats
            rows.setdefault('ats', {})[b] = {'away': {'line': line, 'price': price.get(b, -110)}, 'home': {'line': -line, 'price': -110}}
        if ml:
            rows.setdefault('ml', {})[b] = {'away': {'price': ml}, 'home': {'price': -ml if ml > 0 else 120}}
        if total:
            line, price = total
            rows.setdefault('total', {})[b] = {'line': line, 'over': {'price': price}, 'under': {'price': -110}}
    return {'id': gid, 'away': f'A{gid}', 'home': f'H{gid}', 'start': start, 'state': 'pre', 'rows': rows}


class PickTest(unittest.TestCase):
    def setUp(self):
        self.S = FakeSport('nba')
        self.S.odds_game = lambda d, g: {'books': {'1q': g['rows']}}

    def rows(self, games):
        return {r['key']: r for r in bignums.rows_for(self.S, '1q', [('2026-11-19', g) for g in games])}

    def test_spread_ties_go_to_the_dearer_price_then_earlier(self):
        a = game(1, '2026-11-20T00:00Z', ats=(-5.5, {'dk': -110, 'fd': -110, 'mgm': -110}))
        b = game(2, '2026-11-20T01:00Z', ats=(-5.5, {'dk': -115, 'fd': -115, 'mgm': -112}))
        r = self.rows([a, b])['ats']
        self.assertIs(r['game'], b)
        self.assertEqual((r['top'], r['sub'], r['book']), ('-5.5', '-112', 'mgm'))   # the best price at the consensus line
        c = game(3, '2026-11-19T23:00Z', ats=(-5.5, {'dk': -115, 'fd': -115, 'mgm': -112}))
        self.assertIs(self.rows([a, b, c])['ats']['game'], c)

    def test_consensus_line(self):
        a = game(1, '2026-11-20T00:00Z', total=(58.5, -110))
        a['rows']['total']['dk']['line'] = 60.5   # one book off the market
        self.assertEqual(self.rows([a])['total']['top'], 'o58.5')

    def test_highest_total_and_heaviest_favorite(self):
        a = game(1, '2026-11-20T00:00Z', ml=-200, total=(57.5, -105))
        b = game(2, '2026-11-20T01:00Z', ml=-305, total=(58.5, -120))
        r = self.rows([a, b])
        self.assertIs(r['ml']['game'], b)
        self.assertEqual(r['ml']['label'], 'Moneyline')
        self.assertIs(r['total']['game'], b)
        self.assertEqual(r['total']['long'], 'Highest Total')
        self.assertEqual((r['ml']['top'], r['ml']['sub']), (self.S.code('A2'), '-305'))   # the favorite's code on top, the price below

    def test_one_book_never_flips_the_favorite(self):
        # three books: home -0.5; one outlier makes the away team -0.5 at +150
        a = game(1, '2026-11-20T00:00Z', ats=(0.5, {}))
        a['rows']['ats']['xx'] = {'away': {'line': -0.5, 'price': 150}, 'home': {'line': 0.5, 'price': -210}}
        r = self.rows([a])['ats']
        self.assertEqual((r['fav'], r['top'], r['sub']), ('home', '-0.5', '-110'))

    def test_football_board_is_the_next_game_day(self):
        S = FakeSport('nfl')
        S.weekly = True
        games = [('2026-11-19', {'id': 1}), ('2026-11-22', {'id': 2})]
        orig = front.upcoming
        front.upcoming = lambda sport, today, now: games
        try:
            from datetime import datetime, timezone
            day, got = bignums.board(S, datetime(2026, 11, 19, 17, tzinfo=timezone.utc))
        finally:
            front.upcoming = orig
        self.assertEqual((day, got), ('2026-11-19', games[:1]))


if __name__ == '__main__':
    unittest.main()
