"""The shared front sections (scripts/front.py), team codes, in-season
sports and the Edges lead buckets (scripts/lead_cuts.py)."""
import os
import sys
import unittest
from datetime import date, datetime, timezone

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
    def test_rows_most_units_first(self):
        games = [nhl_game(i, [1, 1]) for i in range(4)] + [nhl_game(9, [1, 0])]
        S = {'nhl': FakeSport('nhl', {'2026-11-15': games})}
        html = front.yesterdays_best(S, '2026-11-15')
        self.assertIn('Yesterday&rsquo;s Best', html)
        # the road teams' +6.0u first; then at most 2 rows from one sport (QA fixes, Nov 19)
        self.assertIn('<span class="yb-mk">1P Road ML</span>', html)
        self.assertEqual(html.count('class="yb-row"'), 2)
        self.assertNotIn('1P Under 1.5', html)   # -2.64u: under +1.0u

    def test_rows_need_55_percent(self):
        x = front.Row('1H Road ML')
        for _ in range(17):
            x.add('W', 3.0)
        for _ in range(31):
            x.add('L', -1.0)
        self.assertGreater(x.u, front.BEST_SHOW_U)
        self.assertLess(x.pct, front.BEST_MIN_PCT)   # +20u at 35% isn't a best bet
        self.assertIn('BEST_MIN_PCT', open(front.__file__).read().split('def best_cands')[1].split('def best_row')[0])

    def test_hidden_when_nothing_won(self):
        games = [nhl_game(i, [0, 0]) for i in range(3)]
        for g in games:
            g['res']['1p']['u'] = {'su': [-1.0, -1.0], 'tot': [-1.0, 0.3]}   # Unders +0.9u: under +1.0u
        S = {'nhl': FakeSport('nhl', {'2026-11-15': games})}
        self.assertEqual(front.yesterdays_best(S, '2026-11-15'), '')

    def test_needs_one_unit(self):
        # one Over at +0.91u: under +1.0u, no card
        S = {'nhl': FakeSport('nhl', {'2026-11-15': [nhl_game(1, [1, 1])]})}
        for g in S['nhl'].doc['games']['2026-11-15']:
            g['res']['1p']['u']['su'] = [-1.0, -1.0]
        self.assertEqual(front.yesterdays_best(S, '2026-11-15'), '')


class PreviewHeroTest(unittest.TestCase):
    def test_shows_from_11am(self):
        import daily
        import preview
        old = daily.load
        daily.load = lambda: [{'kind': 'preview', 'sport': 'all', 'date': '2026-11-17', 'path': 'preview/2026-11-17/',
                               'title': 'T', 'body': '# Suns at Kings tops the night\n> One line.\n\nBody.'}]
        try:
            at = lambda h, d=17: datetime(2026, 11, d, h, 0, tzinfo=timezone.utc)   # UTC; ET is 5 hours behind
            self.assertEqual(preview.hero(at(15)), '')                   # 10 AM ET: Yesterday's Best stays the hero
            self.assertIn('Suns at Kings tops the night', preview.hero(at(16)))   # 11 AM ET
            self.assertIn('Preview &middot; Tuesday, Nov 17, 2026', preview.hero(at(16)))
            self.assertEqual(preview.hero(at(16, 18)), '')               # the next day: not today's
        finally:
            daily.load = old


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


def card(cid, units, games, seg='1h', mk='ml', angle='x', d='Back', n=30, rate=0.7, base=0.5):
    return {'id': cid, 'title': cid, 'tag': '1H ML', 'seg': seg, 'mk': mk, 'angle': angle, 'dir': d,
            'w': 20, 'l': 10, 't': 0, 'n': n, 'rate': rate, 'base': base, 'units': units,
            'games': [{'id': i, 'side': side} for i, side in games]}


def nba_game(gid, start='2026-11-18T00:30:00Z', state='pre'):
    return {'id': gid, 'away': 'A', 'home': 'H', 'start': start, 'state': state,
            'odds': {k: {'ml': {'away': 120, 'home': -140}} for k in ('1q', '1h')}}


class HotTrendsTest(unittest.TestCase):
    NOW = datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc)   # 5 PM ET

    def hot(self, cards, games):
        S = FakeSport('nba', {'2026-11-17': games})
        S.trends = {'slates': {'2026-11-17': {'cards': cards}}}
        return [c['id'] for _, c, _, _ in front.hot_cards({'nba': S}, self.NOW)]

    def test_today_only_and_bar(self):
        games = [nba_game('1'), nba_game('2', start='2026-11-19T00:30:00Z')]
        cards = [card('today', 5, [('1', 'home')]), card('later', 9, [('2', 'home')], seg='1q'),
                 card('few', 9, [('1', 'away')], seg='1q', n=19), card('losing', -1.5, [('1', 'away')], mk='ats'),
                 card('thin', 9, [('1', 'away')], mk='tot', rate=0.54), card('3way', 9, [('1', 'away')], mk='ml3')]
        self.assertEqual(self.hot(cards, games), ['today'])

    def test_mirror_keeps_more_units(self):
        games = [nba_game('1'), nba_game('2')]
        cards = [card('fade_dogs', 3, [('1', 'home')], angle='tier4', d='Fade'),
                 card('back_favs', 6, [('1', 'home'), ('2', 'away')], angle='tier1')]
        self.assertEqual(self.hot(cards, games), ['back_favs'])

    def test_same_bets_as_a_card_above_are_skipped_and_top3_vary(self):
        games = [nba_game(str(i)) for i in range(5)]
        cards = [card('a', 9, [('0', 'home'), ('1', 'home')], angle='a'),
                 card('dup', 8, [('1', 'home')], angle='b'),
                 card('same_mk', 7, [('2', 'home')], angle='c'),
                 card('other_mk', 6, [('3', 'home')], seg='1q', angle='d'),
                 card('third', 5, [('4', 'home')], mk='ats', angle='e')]
        self.assertEqual(self.hot(cards, games), ['a', 'other_mk', 'third', 'same_mk'])

    def test_left_drops_started_games(self):
        # Hottest Trends on home and hubs: only games still to start
        games = [nba_game('1', start='2026-11-17T21:00:00Z'), nba_game('2')]
        S = FakeSport('nba', {'2026-11-17': games})
        S.trends = {'slates': {'2026-11-17': {'cards': [card('gone', 9, [('1', 'home')]), card('left', 5, [('2', 'home')], seg='1q')]}}}
        self.assertEqual([c['id'] for _, c, _, _ in front.hot_cards({'nba': S}, self.NOW, left=True)], ['left'])


class LinkCheckTest(unittest.TestCase):
    def test_targets(self):
        import check_links
        page = os.path.join(check_links.ROOT, 'nba', 'index.html')
        pre = check_links.site_prefixes()
        self.assertEqual(check_links.target(page, '/daily/', pre), os.path.join(check_links.ROOT, 'daily', 'index.html'))
        self.assertEqual(check_links.target(page, '../odds/?d=1#x', pre), os.path.join(check_links.ROOT, 'odds', 'index.html'))
        self.assertIsNone(check_links.target(page, 'https://example.com/a', pre))
        self.assertIsNone(check_links.target(page, 'mailto:a@b.c', pre))
        self.assertIsNone(check_links.target(page, '#top', pre))


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
