"""The shared front sections (scripts/front.py), team codes, in-season
sports and the Edges lead buckets (scripts/lead_cuts.py)."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import front  # noqa: E402
import lead_cuts  # noqa: E402
import sports  # noqa: E402


class FakeSport(front.Sport):
    def __init__(self, key, games):
        sp = sports.BY_KEY[key]
        self.sp, self.key, self.label, self.weekly = sp, key, sp['label'], False
        self.segments = sp['segments']
        self.doc = {'sport': key, 'segments': sp['segments'], 'games': games, 'teams': {}}
        self.trends, self.sources, self._odds = {}, {}, {}
        self.dir = ''
        self.matchups = self.odds_page = self.trends_page = ''

    def odds_game(self, d, g):
        return {}


def nhl_game(gid, p1, odds=True, home_u=0.9):
    g = {'id': gid, 'state': 'final', 'away': 'A', 'home': 'H', 'start': '2026-11-15T00:00:00Z',
         'res': {'1p': {'sc': p1, 'su': 'W' if p1[0] > p1[1] else 'L' if p1[0] < p1[1] else 'T',
                        'tot': 'O' if sum(p1) >= 2 else 'U', 'btts': 'Y' if min(p1) else 'N'}}}
    if odds:
        g['odds'] = {'1p': {'ml': {'away': 120, 'home': -140}, 'total': {'line': 1.5, 'over': -110, 'under': -110}}}
        g['res']['1p']['u'] = {'su': [-1.0, home_u] if p1[1] > p1[0] else [1.2, -1.0], 'tot': [0.91, -1.0] if sum(p1) >= 2 else [-1.0, 0.91]}
    return g


class ResultsTest(unittest.TestCase):
    def test_records_count_only_games_with_a_line(self):
        S = FakeSport('nhl', {})
        games = [nhl_game(1, [0, 1]), nhl_game(2, [0, 2], odds=False), nhl_game(3, [0, 1], odds=False)]
        home = next(r for r in front.result_rows(S, games, '1p') if r.label == 'Home teams')
        self.assertEqual((home.w, home.l, home.t, home.n), (1, 0, 0, 1))   # not 3-0-0 with units over 1 game

    def test_unlined_game_shows_nowhere(self):
        S = FakeSport('nhl', {})
        self.assertTrue(front.game_lined(S, nhl_game(1, [1, 0])))
        self.assertFalse(front.game_lined(S, nhl_game(1, [1, 0], odds=False)))


class BestTest(unittest.TestCase):
    def test_best_market_with_wording(self):
        games = [nhl_game(i, [1, 1]) for i in range(4)] + [nhl_game(9, [1, 0])]
        S = {'nhl': FakeSport('nhl', {'2026-11-15': games})}
        html = front.yesterdays_best(S, '2026-11-15')
        self.assertIn('Yesterday&rsquo;s Best', html)
        self.assertIn('1P O/U Over 1.5 went 4&ndash;1', html)

    def test_hidden_when_nothing_won(self):
        games = [nhl_game(i, [0, 0]) for i in range(3)]
        for g in games:
            g['res']['1p']['u'] = {'su': [-1.0, -1.0], 'tot': [-1.0, 0.91]}
        S = {'nhl': FakeSport('nhl', {'2026-11-15': games})}
        self.assertEqual(front.yesterdays_best(S, '2026-11-15'), '')


class PriceTest(unittest.TestCase):
    def test_moneylines_past_2000_are_a_dash(self):
        self.assertEqual(front.price_txt(-2700), '&mdash;')
        self.assertEqual(front.price_txt(2100), '&mdash;')
        self.assertEqual(front.price_txt(-205), '-205')


class CodesTest(unittest.TestCase):
    def test_limits(self):
        self.assertEqual(sports.team_code('nba', 'UTAH'), 'UTA')
        self.assertEqual(sports.team_code('nba', 'GS'), 'GS')
        self.assertEqual(sports.team_code('ncaab', 'UCLA'), 'UCLA')
        for name in ('Miami (OH) Middletown ThunderHawks', "St. Joseph's Long Island Golden Eagles", 'Reinhardt Eagles'):
            self.assertLessEqual(len(sports.other_code('ncaab', name)), 4)

    def test_every_saved_code_fits(self):
        import json
        for sp in sports.SPORTS:
            path = os.path.join(os.path.dirname(__file__), '..', 'data_seed', 'teams', f"{sp['key']}.json")
            if not os.path.exists(path):
                continue
            codes = [sports.team_code(sp['key'], t['code']) for t in json.load(open(path, encoding='utf-8'))['teams']]
            self.assertTrue(all(len(c) <= sports.code_max(sp['key']) for c in codes), sp['key'])
            self.assertEqual(len(codes), len(set(codes)), sp['key'])


class SeasonTest(unittest.TestCase):
    def test_in_season_by_month(self):
        nov = date(2026, 11, 16)
        on = [s['key'] for s in sports.SPORTS if sports.in_season(s, nov)]
        self.assertEqual(on, ['nhl', 'nba', 'ncaab', 'nfl', 'ncaaf'])
        self.assertTrue(sports.in_season(sports.BY_KEY['mlb'], date(2027, 4, 1)))
        self.assertFalse(sports.in_season(sports.BY_KEY['ncaaf'], date(2027, 3, 1)))


class LeadCutsTest(unittest.TestCase):
    def test_thirds(self):
        leads = [1] * 10 + [5] * 10 + [12] * 10
        self.assertEqual(lead_cuts.thirds(leads), [1, 5])

    def test_cutoff_moves_only_by_two(self):
        path = os.path.join(os.path.dirname(__file__), '_lead_cuts_test.json')
        old, lead_cuts.PATH = lead_cuts.PATH, path
        try:
            def games(cuts):
                out = []
                for i, x in enumerate(cuts):
                    out.append({'state': 'final', 'res': {'1h': {'sc': [x, 0]}}})
                return {'d': out}
            segs = [{'key': '1h'}]
            first = lead_cuts.update('nba', segs, games([3] * 20 + [8] * 20 + [15] * 20))['1h']
            nudged = lead_cuts.update('nba', segs, games([4] * 20 + [9] * 20 + [15] * 20))['1h']
            self.assertEqual(nudged, first)
            moved = lead_cuts.update('nba', segs, games([6] * 20 + [11] * 20 + [15] * 20))['1h']
            self.assertEqual(moved, [6, 11])
        finally:
            lead_cuts.PATH = old
            if os.path.exists(path):
                os.remove(path)


if __name__ == '__main__':
    unittest.main()
