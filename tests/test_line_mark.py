"""
The Stats cards' "*" (assets/sport.js lineShort / leagueOnly) and the
Situational table's dagger (assets/situational.js lineShortSit): the mark
shows only when the market has a line on fewer than 98% of the card's graded
games, and a college game against a non-D-I / non-FBS opponent isn't part of
the total.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_game_log import NODE, SRC, function  # noqa: E402

SIT = open(os.path.join(os.path.dirname(__file__), '..', 'assets', 'situational.js')).read()


@unittest.skipUnless(NODE, 'node is not installed')
class LineMarkTest(unittest.TestCase):
    def run_js(self, body):
        js = '\n'.join([function(SRC, 'tlCollege'), function(SRC, 'lineShort'), function(SRC, 'leagueOnly'), function(SIT, 'lineShortSit'), body])
        out = subprocess.run([NODE, '-e', js], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_98_percent(self):
        got = self.run_js('console.log(JSON.stringify([lineShort(98, 100), lineShort(97, 100), lineShort(49, 50), lineShort(100, 100),'
                          'lineShortSit({ lg: 100, lined: 98 }), lineShortSit({ lg: 100, lined: 97 }), lineShortSit({ lg: 0, lined: 0 })]));')
        self.assertEqual(got, [False, True, False, False, False, True, False])

    def test_college_non_league_opponent_is_not_in_the_total(self):
        body = """var games = [{ home: 'a', away: 'b' }, { home: 'a', away: 'x' }];
var D = { sport: 'ncaab', teams: { a: {}, b: {} } };
var college = leagueOnly(games).length;
D = { sport: 'nba', teams: { a: {}, b: {} } };
console.log(JSON.stringify([college, leagueOnly(games).length]));"""
        self.assertEqual(self.run_js(body), [1, 2])


if __name__ == '__main__':
    unittest.main()
