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

    def test_two_spread_pairs_keep_the_mirrored_pair_nearest_even(self):
        bm = [book('hardrockbet', spreads_q1=[
            {'name': AWAY, 'point': -4.5, 'price': 170}, {'name': HOME, 'point': 4.5, 'price': -230},
            {'name': AWAY, 'point': -1.5, 'price': -108}, {'name': HOME, 'point': 1.5, 'price': -112},
            {'name': HOME, 'point': -3.5, 'price': 105}])]   # no mirror: never mixed into a pair
        _, books = B.closing('nba', bm, KEYS[1:2], AWAY, HOME)
        self.assertEqual(books['1q']['ats']['hardrockbet'],
                         {'away': {'line': -1.5, 'price': -108}, 'home': {'line': 1.5, 'price': -112}})

    def test_a_book_with_only_alternates_is_dropped(self):
        """Hard Rock sends just an alternate pair (+275 / -375 at 66.5 when
        the books post 60.5 near even): its row goes, the others stay."""
        bm = BOOKMAKERS[:2] + [book('hardrockbet',
            totals_q1=[{'name': 'Over', 'point': 66.5, 'price': 275}, {'name': 'Under', 'point': 66.5, 'price': -375}],
            spreads_q1=[{'name': AWAY, 'point': 3.5, 'price': -175}, {'name': HOME, 'point': -3.5, 'price': 140}])]
        _, books = B.closing('nba', bm, KEYS[1:], AWAY, HOME)
        self.assertEqual(sorted(books['1q']['ats']), ['draftkings', 'fanduel'])
        self.assertEqual(sorted(books['1q']['total']), ['draftkings', 'fanduel'])
        # a different line priced near even is a real line, not an alternate
        _, books = B.closing('nba', BOOKMAKERS, KEYS[1:], AWAY, HOME)
        self.assertIn('betmgm', books['1q']['ats'])

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

    def test_mlb_full_game_run_line_is_one_and_a_half(self):
        """MLB's full game (h2h / spreads / totals) is wanted like every
        sport's; its run line is 1.5, while the F5 run line stays 0.5."""
        self.assertEqual([x for x in B.wanted('mlb') if x[0] == 'game'],
                         [('game', 'ml', 'h2h'), ('game', 'ats', 'spreads'), ('game', 'total', 'totals')])
        bm = [book(b, spreads=[{'name': AWAY, 'point': 1.5, 'price': -160}, {'name': HOME, 'point': -1.5, 'price': 135}],
                   spreads_1st_5_innings=[{'name': AWAY, 'point': 0.5, 'price': -120}, {'name': HOME, 'point': -0.5, 'price': 100}])
              for b in ('draftkings', 'fanduel')]
        lines, _ = B.closing('mlb', bm, [('game', 'ats', 'spreads'), ('f5', 'ats', 'spreads_1st_5_innings')], AWAY, HOME)
        self.assertEqual(lines['game']['ats']['away']['line'], 1.5)
        self.assertEqual(lines['f5']['ats']['away']['line'], 0.5)

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

    def test_run_4_unmatched_names(self):
        """The API names run #4 left unmatched, each against its school here."""
        for sport, api, slug in (('ncaab', "Mt. St. Mary's Mountaineers", 'mount-st-marys-mountaineers'),
                                 ('ncaab', 'Seattle Redhawks', 'seattle-u-redhawks'),
                                 ('ncaab', 'Cal Baptist Lancers', 'california-baptist-lancers'),
                                 ('ncaab', 'Albany Great Danes', 'ualbany-great-danes'),
                                 ('ncaab', 'Boston Univ. Terriers', 'boston-university-terriers'),
                                 ('ncaab', 'Loyola (Chi) Ramblers', 'loyola-chicago-ramblers'),
                                 ('ncaab', 'CSU Bakersfield Roadrunners', 'cal-state-bakersfield-roadrunners'),
                                 ('ncaab', 'CSU Fullerton Titans', 'cal-state-fullerton-titans'),
                                 ('ncaaf', 'Southern Mississippi Golden Eagles', 'southern-miss-golden-eagles')):
            other = 'duke-blue-devils' if sport == 'ncaab' else 'mississippi-state-bulldogs'
            ev = {'commence_time': '2026-11-15T00:00:00Z', 'away_team': api,
                  'home_team': 'Duke Blue Devils' if sport == 'ncaab' else 'Mississippi State Bulldogs'}
            game = {'date': '2026-11-14', 'away': slug, 'home': other, 'start': '2026-11-15T00:00Z'}
            self.assertEqual(len(A.match(sport, [ev], [game])[0]), 1, api)


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

    def test_a_game_an_earlier_run_did_is_not_unmatched(self):
        """Celtics @ Heat was filled before (not in this run's todo): the
        day's events list it, but it's one of our games, so it isn't a miss."""
        done = {'id': 'e1', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        run = B.Run(None, False)
        run.day_games[('nba', '2026-11-14')] = [{'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T00:00Z'}]
        run.files[('nba', 2027)], run.state = {'games': {}}, {}
        rep = {'filled': {}, 'no_market': {}, 'unmatched': [], 'unmatched_events': [], 'empty': [], 'big_ml': [], 'game_minutes': []}
        with mock.patch.object(A, 'historical_events', return_value={'data': [done]}), \
                mock.patch.object(A, 'historical_odds', return_value={'data': []}):
            B.fill_day(run, 'nba', 2027, '2026-11-14', [], rep)
        self.assertEqual(rep['unmatched_events'], [])

    def test_indoor_game_starts_by_espns_time(self):
        """SA @ SAC, Mar 17: the API listed the tip an hour after ESPN's
        start, so its 'pregame' snapshot was in-play. Indoor sports take the
        earlier of the two."""
        late = {'id': 'e1', 'commence_time': '2026-11-15T01:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        snaps = {'2026-11-14T23:55:00Z': [ml(late, -150, 130)], '2026-11-15T00:55:00Z': [ml(late, -10000, 3300)]}
        games = [({'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T00:00Z'}, [('game', 'ml', 'h2h')])]
        run, rep = fill(games, [late], snaps)
        g = run.files[('nba', 2027)]['games']['2026-11-14|bos|mia']
        self.assertEqual(g['segments']['game']['ml'], {'away': -150, 'home': 130, 'books': 1})
        self.assertEqual(g['game_snapshot'], '2026-11-14T23:55:00Z')

    def test_tbd_start_matches_on_the_date(self):
        """ESPN's 11:59 PM ET placeholder is hours from the real tip: the date
        and both teams match it; a real start still needs the 4 hours."""
        ev = {'commence_time': '2026-11-15T00:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        tbd = {'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T04:59Z'}
        self.assertEqual(len(A.match('nba', [ev], [tbd])[0]), 1)
        self.assertEqual(len(A.match('nba', [ev], [dict(tbd, start='2026-11-15T04:30Z')])[0]), 0)

    def test_tbd_start_matches_a_tip_after_midnight(self):
        """Hawai'i's home games tip after midnight ET: ESPN's 11:59 PM
        placeholder matches the API's next-day tip up to 6 AM ET, not later."""
        game = {'date': '2025-11-12', 'away': 'mississippi-valley-state-delta-devils', 'home': 'hawaii-rainbow-warriors',
                'start': '2025-11-13T04:59Z'}
        ev = {'commence_time': '2025-11-13T05:00:00Z', 'away_team': 'Miss Valley St Delta Devils', 'home_team': "Hawai'i Rainbow Warriors"}
        self.assertEqual(len(A.match('ncaab', [ev], [game])[0]), 1)
        self.assertEqual(len(A.match('ncaab', [dict(ev, commence_time='2025-11-13T12:00:00Z')], [game])[0]), 0)
        self.assertEqual(len(A.match('ncaab', [ev], [dict(game, start='2025-11-13T00:00Z')])[0]), 0)   # a real start: 4 hours

    def test_liu_fiu_and_albany(self):
        for sport, (api_a, api_h), (a, h) in (
                ('ncaab', ('LIU Sharks', "Florida Int'l Golden Panthers"), ('long-island-university-sharks', 'florida-international-panthers')),
                ('ncaaf', ('Albany', 'Buffalo Bulls'), ('espn-399', 'buffalo-bulls'))):   # FCS: ESPN's name
            ev = {'commence_time': '2025-12-20T22:00:00Z', 'away_team': api_a, 'home_team': api_h}
            game = {'date': '2025-12-20', 'away': a, 'home': h, 'start': '2025-12-20T22:00Z', 'away_name': 'UAlbany Great Danes'}
            self.assertEqual(len(A.match(sport, [ev], [game])[0]), 1, api_a)

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


class Outliers(unittest.TestCase):
    """fetch_odds_unabated.best_of drops a book more than 8 points of implied
    probability from the other books' median on a side (Morehead State @ UL
    Monroe: BetOnline +219 while six books sat near even)."""

    def test_stale_book_is_dropped(self):
        rows = {b: {'away': {'price': -130}, 'home': {'price': 100}} for b in ('dk', 'fd', 'mgm')}
        rows['bol'] = {'away': {'price': -265}, 'home': {'price': 219}}
        self.assertEqual(best_of('ml', rows, ()), {'away': -130, 'home': 100})

    def test_two_books_are_kept(self):
        rows = {'dk': {'away': {'price': -130}, 'home': {'price': 100}}, 'bol': {'away': {'price': -265}, 'home': {'price': 219}}}
        self.assertEqual(best_of('ml', rows, ()), {'away': -130, 'home': 219})

    def test_spread_outlier_at_the_chosen_line(self):
        rows = {b: {'away': {'line': -3.5, 'price': -110}, 'home': {'line': 3.5, 'price': -110}} for b in ('dk', 'fd', 'mgm')}
        rows['hr'] = {'away': {'line': -3.5, 'price': 150}, 'home': {'line': 3.5, 'price': -190}}
        self.assertEqual(best_of('ats', rows, ())['away'], {'line': -3.5, 'price': -110})

    def test_tied_lines_pick_the_one_nearest_even_whatever_the_order(self):
        a = {'line': 57.5, 'over': {'price': -104}, 'under': {'price': -115}}
        b = {'line': 58.5, 'over': {'price': -110}, 'under': {'price': -110}}
        c = {'line': 59.5, 'over': {'price': -110}, 'under': {'price': -110}}
        one = best_of('total', {'x': a, 'y': c, 'z': b, 'w': a, 'v': c}, ())
        two = best_of('total', {'v': c, 'w': a, 'z': b, 'y': c, 'x': a}, ())
        self.assertEqual(one, two)
        self.assertEqual(one['line'], 59.5)


class RefreshWins(unittest.TestCase):
    """Run #4's Morehead State line stopped the refresh for an hour (its tests
    gate the publish): the backfill never saves a full-game ML with both
    sides past a pick'em."""

    def test_both_plus_ml_is_not_saved(self):
        e = {'id': 'e1', 'commence_time': '2026-11-15T00:00:00Z', 'away_team': AWAY, 'home_team': HOME}
        snaps = {'2026-11-14T23:55:00Z': [ml(e, 100, 219)]}
        games = [({'date': '2026-11-14', 'away': 'bos', 'home': 'mia', 'start': '2026-11-15T00:00Z'}, [('game', 'ml', 'h2h')])]
        run, rep = fill(games, [e], snaps)
        self.assertNotIn('2026-11-14|bos|mia', run.files[('nba', 2027)]['games'])
        self.assertEqual(rep['big_ml'], ['2026-11-14|bos|mia +100/+219 (not saved)'])

    def test_usage_log_merges_as_a_union(self):
        with open(os.path.join(ROOT, '.gitattributes'), encoding='utf-8') as f:
            self.assertIn('data_feed/oddsapi/usage.jsonl merge=union', f.read())
