"""
Starters (scripts/fetch_starters.py, nhl_sport.expected_goalies, the team
page's By Starting Pitcher / Goalie table in assets/sport.js): a game's
starter shows in its team's table, a pitcher traded mid-season shows only his
starts for that team, and an NHL goalie goes from expected to confirmed once
the box score lists him. MLB and NHL only.
"""
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_starters as fs  # noqa: E402
import nhl_sport  # noqa: E402
from test_game_log import NODE, SRC, function  # noqa: E402


def sched(pk, when, away, home, n=1):
    return {'gamePk': pk, 'gameDate': when, 'gameNumber': n, 'status': {'detailedState': 'Final'},
            'teams': {'away': {'team': {'name': away}}, 'home': {'team': {'name': home}}}}


class MlbMatchTest(unittest.TestCase):
    def test_et_date_teams_and_doubleheader_order(self):
        ours = [{'id': 'a', 'date': '2026-07-04', 'start': '2026-07-04T17:05Z', 'away_name': 'Boston Red Sox', 'home_name': 'New York Yankees'},
                {'id': 'b', 'date': '2026-07-04', 'start': '2026-07-04T23:05Z', 'away_name': 'Boston Red Sox', 'home_name': 'New York Yankees'},
                {'id': 'c', 'date': '2026-07-04', 'start': '2026-07-05T02:10Z', 'away_name': 'Athletics', 'home_name': 'Seattle Mariners'}]
        theirs = [sched(2, '2026-07-04T23:05:00Z', 'Boston Red Sox', 'New York Yankees', 2),
                  sched(1, '2026-07-04T17:05:00Z', 'Boston Red Sox', 'New York Yankees'),
                  sched(3, '2026-07-05T02:10:00Z', 'Athletics', 'Seattle Mariners')]   # 10:10 PM ET on Jul 4
        got = fs.match_mlb(ours, theirs)
        self.assertEqual({k: v['gamePk'] for k, v in got.items()}, {'a': 1, 'b': 2, 'c': 3})


class NhlStatusTest(unittest.TestCase):
    def games(self):
        return [nhl_sport.game({'id': 1, 'away': 'DAL', 'home': 'WPG', 'state': 'FINAL', 'startTimeUTC': '2026-11-20T00:00:00Z',
                                'awayGoalie': {'id': 30, 'name': 'J. Oettinger'}, 'homeGoalie': {'id': 37, 'name': 'C. Hellebuyck'}}, '2026-11-19'),
                nhl_sport.game({'id': 2, 'away': 'WPG', 'home': 'DAL', 'state': 'FUT', 'startTimeUTC': '2026-11-24T00:30:00Z'}, '2026-11-23')]

    def test_expected_is_the_last_starter(self):
        gs = self.games()
        nhl_sport.expected_goalies(gs)
        self.assertEqual(gs[1]['ag'], {'id': 37, 'name': 'C. Hellebuyck', 'last': 'Hellebuyck', 'status': 'expected'})
        self.assertEqual(gs[1]['hg']['status'], 'expected')
        self.assertNotIn('status', gs[0]['ag'])   # a final's starter has no status

    def test_expected_switches_to_confirmed(self):
        data = {'games': {'2026-11-23': [{'id': 2, 'away': 'WPG', 'home': 'DAL', 'state': 'FUT', 'startTimeUTC': '2026-11-24T00:30:00Z'}]}}
        now = datetime(2026, 11, 23, 23, 0, tzinfo=timezone.utc)   # 90 minutes before
        box = {'away': {'id': 33, 'name': 'E. Comrie'}, 'home': {'id': 30, 'name': 'J. Oettinger'}}
        writes = []
        with mock.patch.object(fs, 'read_json', lambda p, d: data), \
                mock.patch('builtins.open', mock.mock_open()), mock.patch.object(fs.json, 'dump', lambda d, f, **k: writes.append(d)):
            self.assertEqual(fs.nhl_tonight(now, fetch=lambda gid: None), 0)   # not listed yet: stays expected
            self.assertEqual(fs.nhl_tonight(now, fetch=lambda gid: box), 1)
        g = data['games']['2026-11-23'][0]
        self.assertEqual(g['awayGoalie'], {'id': 33, 'name': 'E. Comrie', 'status': 'confirmed'})
        out = nhl_sport.game(g, '2026-11-23')
        nhl_sport.expected_goalies(self.games()[:1] + [out])
        self.assertEqual((out['ag']['last'], out['ag']['status'], out['hg']['status']), ('Comrie', 'confirmed', 'confirmed'))


@unittest.skipUnless(NODE, 'node is not installed')
class StarterTableTest(unittest.TestCase):
    def rows(self, games, slug):
        js = "var D = {sportType: 'baseball', sport: 'mlb'};\n" + '\n'.join(
            function(SRC, n) for n in ('hasStarters', 'starterOf', 'starterRows')) + """
console.log(JSON.stringify(starterRows(%s, %s, 1).map(function(r) { return [r.p.name, r.games.map(function(g) { return g.id; })]; })));""" % (
            json.dumps(slug), json.dumps(games))
        return json.loads(subprocess.run([NODE, '-e', js], capture_output=True, text=True, check=True).stdout)

    def test_starter_in_his_teams_table_and_traded_pitcher(self):
        pivetta = {'id': 1, 'name': 'Nick Pivetta'}
        games = [{'id': 'g1', 'away': 'bos', 'home': 'nyy', 'asp': pivetta, 'hsp': {'id': 2, 'name': 'Gerrit Cole'}},
                 {'id': 'g2', 'away': 'bos', 'home': 'tor', 'asp': pivetta, 'hsp': {'id': 3, 'name': 'Kevin Gausman'}},
                 # traded to San Diego: his Padres start isn't Boston's
                 {'id': 'g3', 'away': 'sd', 'home': 'lad', 'asp': pivetta, 'hsp': {'id': 4, 'name': 'Tyler Glasnow'}}]
        self.assertEqual(self.rows(games, 'bos'), [['Nick Pivetta', ['g1', 'g2']]])
        self.assertEqual(self.rows(games, 'sd'), [['Nick Pivetta', ['g3']]])
        self.assertEqual(self.rows(games, 'nyy'), [['Gerrit Cole', ['g1']]])


if __name__ == '__main__':
    unittest.main()
