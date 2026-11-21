"""
Team page Game Log cells (assets/sport.js logCell): ML and 3-way show the
page team's own side and price, graded from its side; a market with no saved
price is a plain "-". The Last Game card still shows the side that won
(settledSide). The functions are pulled out of sport.js and run under Node.
"""
import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which('node')


def function(src, name):
    """The source of `function name(...) { ... }` (brace matched)."""
    i = src.index('function %s(' % name)
    depth, j = 0, src.index('{', i)
    while True:
        c = src[j]
        depth += c == '{'
        depth -= c == '}'
        j += 1
        if depth == 0:
            return src[i:j]


SRC = open(os.path.join(ROOT, 'assets', 'sport.js'), encoding='utf-8').read()
STUBS = """
var slug = 'wake', D = {sport: 'ncaaf'};
function tcode(s) { return s.toUpperCase(); }
function esc(s) { return String(s); }
function priceTxt(p) { return (p > 0 ? '+' : '') + p; }
function signedLine(l) { return (l > 0 ? '+' : '') + l; }
function num1(n) { return String(n); }
"""


def run(games, market, nhl=False):
    js = STUBS + (("D.sport = 'nhl';") if nhl else '') + '\n'.join(
        function(SRC, n) for n in ('lastSides', 'settledSide', 'lastSideCell', 'logCell')) + """
var games = %s;
console.log(JSON.stringify(games.map(function(g) {
  return {log: logCell(g, {k: '1q', m: '%s'}), last: (settledSide(lastSides(g, {k: '1q', m: '%s'})) || {}).ln};
})));""" % (json.dumps(games), market, market)
    return json.loads(subprocess.run([NODE, '-e', js], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(NODE, 'node is not installed')
class GameLog(unittest.TestCase):
    # Wake Forest at home, lost the 1st quarter 3-7 to Louisville (the away side won: su W)
    LOST = {'away': 'lou', 'home': 'wake', 'res': {'1q': {'sc': [7, 3], 'su': 'W'}},
            'odds': {'1q': {'ml': {'away': -215, 'home': 175}}}}

    def test_page_team_loses_the_ml(self):
        got = run([self.LOST], 'ml')[0]
        self.assertIn('>WAKE<', got['log'])
        self.assertIn('+175', got['log'])
        self.assertIn('tp-rc-n', got['log'])        # dimmed: Wake's side lost
        self.assertNotIn('LOU', got['log'])
        self.assertEqual(got['last'], 'LOU')        # the Last Game card still shows the winner

    def test_page_team_wins_and_ties(self):
        won = dict(self.LOST, res={'1q': {'sc': [0, 7], 'su': 'L'}})
        tied = dict(self.LOST, res={'1q': {'sc': [7, 7], 'su': 'T'}})
        got = run([won, tied], 'ml')
        self.assertIn('tp-rc-w', got[0]['log'])
        self.assertIn('tp-rc-p', got[1]['log'])

    def test_no_price_no_grade(self):
        none = dict(self.LOST, odds={})
        got = run([none], 'ml')[0]['log']
        self.assertIn('mc-dash', got)
        self.assertNotIn('tp-rc-', got)
        self.assertNotIn('WAKE', got)

    def test_three_way_is_the_page_teams_side(self):
        g = {'away': 'lou', 'home': 'wake', 'res': {'1q': {'sc': [1, 1], 'su': 'T'}},
             'odds': {'1q': {'ml3': {'away': 250, 'draw': 190, 'home': 120}}}}
        got = run([g], 'ml3', nhl=True)[0]
        self.assertIn('>WAKE<', got['log'])
        self.assertIn('+120', got['log'])
        self.assertIn('tp-rc-n', got['log'])        # a tied period loses the team's 3-way bet
        self.assertEqual(got['last'], 'Tie')

    def test_totals_still_show_what_happened(self):
        g = {'away': 'lou', 'home': 'wake', 'res': {'1q': {'sc': [7, 3], 'tot': 'U'}},
             'odds': {'1q': {'total': {'line': 13.5, 'over': -110, 'under': -110}}}}
        self.assertIn('tp-rc-cool', run([g], 'total')[0]['log'])


if __name__ == '__main__':
    unittest.main()
