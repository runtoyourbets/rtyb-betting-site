"""Hubs by season state (scripts/seasons.py), the off-season blocks
(scripts/offseason.py), Streaks to Watch and one gold."""
import os
import re
import subprocess
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import front  # noqa: E402
import nav  # noqa: E402
import offseason  # noqa: E402
import seasons  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
NOON = datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc)   # Thursday noon ET


def game(gid, away, home, start, state='pre', post=False, note=None, a=None, h=None):
    return {'id': gid, 'away': away, 'home': home, 'start': start, 'state': state, 'post': post, 'note': note, 'as': a, 'hs': h}


def doc(*games):
    out = {}
    for g in games:
        out.setdefault(g['start'][:10], []).append(g)
    return {'games': out}


def series(teams, results, start_day=1, month='2026-10', note='World Series'):
    """A best-of-7: results ('A' away wins / 'H' home wins), then the If Necessary games."""
    out = []
    for i in range(7):
        day = f'{month}-{start_day + i:02d}T23:00Z'
        n = f'{note} - Game {i + 1}' + ('' if i < len(results) else ' If Necessary')
        if i < len(results):
            a, h = (5, 2) if results[i] == 'A' else (1, 3)
            out.append(game(100 + i, teams[0], teams[1], day, 'final', True, n, a, h))
        else:
            out.append(game(100 + i, teams[0], teams[1], day, 'pre', True, n))
    return out


class StateTest(unittest.TestCase):
    sp = sports.BY_KEY['nba']

    def test_game_day_and_no_games(self):
        d = doc(game(1, 'a', 'b', '2026-10-01T23:00Z', 'final', a=1, h=2), game(2, 'a', 'b', '2026-11-19T23:00Z'))
        self.assertEqual(seasons.state(self.sp, d, NOON)['key'], 'game_day')
        d = doc(game(1, 'a', 'b', '2026-10-01T23:00Z', 'final', a=1, h=2), game(2, 'a', 'b', '2026-11-21T23:00Z'))
        st = seasons.state(self.sp, d, NOON)
        self.assertEqual((st['key'], st['layout'], st['next']), ('no_games', 'no_games', '2026-11-21'))

    def test_early_season_and_postseason(self):
        d = doc(game(1, 'a', 'b', '2026-11-05T23:00Z', 'final', a=1, h=2), game(2, 'a', 'b', '2026-11-19T23:00Z'))
        self.assertEqual(seasons.state(self.sp, d, NOON)['key'], 'early')
        d = doc(game(1, 'a', 'b', '2026-06-01T23:00Z', 'final', a=1, h=2), game(2, 'a', 'b', '2026-11-19T23:00Z', post=True, note='Second Round - Game 3'))
        self.assertEqual(seasons.state(self.sp, d, NOON)['key'], 'postseason')

    def test_off_season_ignores_a_decided_series_if_necessary_games(self):
        # 4-1 on Oct 1-5; Games 6 and 7 "If Necessary" never happen
        d = doc(*series(('tb', 'mil'), 'HHAHH'))
        st = seasons.state(sports.BY_KEY['mlb'], d, datetime(2026, 10, 6, 17, 0, tzinfo=timezone.utc))
        self.assertEqual((st['key'], st['layout']), ('just_ended', 'off'))
        st = seasons.state(sports.BY_KEY['mlb'], d, NOON)
        self.assertEqual((st['key'], st['layout']), ('off', 'off'))

    def test_weekly(self):
        d = doc(game(1, 'a', 'b', '2026-09-10T00:20Z', 'final', a=1, h=2), game(2, 'a', 'b', '2026-11-22T18:00Z'))
        self.assertEqual(seasons.state(sports.BY_KEY['nfl'], d, NOON)['key'], 'weekly')

    def test_preseason_from_a_milestone(self):
        old = sports.SEASON_DATES
        sports.SEASON_DATES = {'mlb': {'OPENING_DAY': '2027-03-25', 'MILESTONES': [{'label': 'Spring training games', 'date': '2026-11-01'}]}}
        try:
            st = seasons.state(sports.BY_KEY['mlb'], doc(*series(('tb', 'mil'), 'HHAHH')), NOON)
            self.assertEqual(st['key'], 'preseason')
            self.assertEqual(st['opening'], '2027-03-25')
        finally:
            sports.SEASON_DATES = old

    def test_champion_from_the_final_series(self):
        ch = seasons.champion(doc(*series(('tb', 'mil'), 'HHAHH')))
        self.assertEqual((ch['team'], ch['opp'], ch['wins'], ch['losses']), ('mil', 'tb', 4, 1))
        self.assertIsNone(seasons.champion(doc(*series(('tb', 'mil'), 'HHA'))))   # not decided yet


class OffSeasonTest(unittest.TestCase):
    def test_off_season_hubs_never_say_games_are_underway(self):
        for key in ('mlb', 'wnba'):
            sport = front.Sport(sports.BY_KEY[key])
            st = dict(seasons.state(sport.sp, sport.doc, NOON), key='off', layout='off')
            seasons._CACHE[key] = st
            try:
                html = front.sections({key: sport}, NOON, '../', hub=True).split('<script>')[0]   # the page, not its script
            finally:
                seasons._CACHE.pop(key, None)
            self.assertNotIn('underway', html)
            self.assertNotIn('No more games', html)
            self.assertIn('id="countdown"', html)
            self.assertIn('Opening day', html)

    def test_countdown_without_an_opening_day(self):
        sport = front.Sport(sports.BY_KEY['wnba'])
        html = offseason.countdown(sport, {'label': 'Off-season', 'opening': None, 'milestones': [{'label': 'Draft', 'date': '2027-04-14'}]},
                                   {'season': 2026}, NOON)
        self.assertIn('Opening day: date TBA', html)
        self.assertIn('2027 Season &middot; Off-season', html)
        self.assertIn('Draft', html)
        self.assertNotIn('data-countdown', html)

    def test_result_line(self):
        sport = front.Sport(sports.BY_KEY['mlb'])
        self.assertEqual(offseason.result_line(sport, {'opp': 'tb', 'wins': 4, 'losses': 1, 'score': [4, 1]}), 'Beat the Tampa Bay Rays 4–1')


class HubFollowUpTest(unittest.TestCase):
    """Hubs follow-up fixes (Nov 19 afternoon)."""

    def test_awards_show_every_market_and_card(self):
        sport = front.Sport(sports.BY_KEY['mlb'])
        doc = offseason.season_doc(sport)
        html = offseason.awards(sport, doc, '../')
        if not html:
            self.skipTest('no MLB season data')
        for pill in ('F5 Moneyline', 'F5 Run Line', 'F5 Total', '1st Inning'):
            self.assertIn(pill, html)
        self.assertEqual(html.count('class="st-card aw-card'), 4 + 4 + 2 + 2)
        self.assertIn('Not enough lines tracked', html)   # MLB 2026 saved F5 lines for a handful of games

    def test_champion_cell_under_20_games(self):
        t = offseason.Tally()
        for _ in range(5):
            t.add('W', 1.0)
        self.assertIn('Not enough lines tracked', offseason.cell('F5 Total', 'Over', t))
        for _ in range(20):
            t.add('L', -1.0)
        html = offseason.cell('F5 ML', 'Win', t)
        self.assertIn('<span class="os-big">20%</span><span class="os-rec">5–20</span>', html)
        self.assertIn('os-ub', html)

    def test_football_hub_shows_last_week(self):
        sport = front.Sport(sports.BY_KEY['nfl'])
        week = {'key': 'x', 'label': 'Week 10'}
        sport.doc = {'weeks': [dict(week, start='2026-11-12', end='2026-11-16')],
                     'games': {'2026-11-16': [dict(game(1, 'a', 'b', '2026-11-16T18:00Z', 'final', a=1, h=2), wk='x')]}}
        self.assertEqual(front.last_week(sport, '2026-11-19'), sport.doc['weeks'][0])
        sport.doc['games']['2026-11-16'][0]['state'] = 'pre'
        self.assertIsNone(front.last_week(sport, '2026-11-19'))


class StreaksTest(unittest.TestCase):
    def test_title_rows_and_lead_team(self):
        S = front.load(NOON, keys=['nba'])
        xs = front.streaks(S, NOON, hub=True)
        for x in xs:
            self.assertGreaterEqual(x['st']['n'], front.STREAK_MIN)
        html = front.streaks_watch(S, NOON, '../', hub=True)
        if xs:
            self.assertIn('Streak to Watch' if len(xs) == 1 else 'Streaks to Watch', html)
            self.assertEqual(html.count('class="sw-item'), min(len(xs), front.STREAK_ROWS + 1))
            self.assertFalse(xs[0].get('lead'))


class GoldTest(unittest.TestCase):
    def test_one_gold(self):
        out = subprocess.run(['git', 'grep', '-n', '-i', '-E', 'FACC15|A87400|A16207', '--', '*.py', '*.js', 'template.html', 'admin', 'worker',
                              ':!assets/site.css', ':!tests'], cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(out, '')
        tpl = open(os.path.join(ROOT, 'template.html'), encoding='utf-8').read()
        hexes = [ln for ln in tpl.splitlines() if re.search(r'#F5C542', ln, re.I) and '--gold:' not in ln and 'One gold' not in ln]
        self.assertEqual(hexes, [])

    def test_picks_is_not_gold_in_the_sport_row(self):
        row = nav.sport_row('/', sports.BY_KEY['nba'], 'games')
        self.assertNotIn('gold', row)


if __name__ == '__main__':
    unittest.main()
