"""The Betting Guides' example games (content/betting-guides/examples.json):
every won / lost / push cell has to match its score and line, so a typo in
the file fails the build (spread, total, moneyline, run line, 3-way, BTTS,
NRFI / YRFI)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import guides  # noqa: E402
import sports  # noqa: E402


def outcome(ex, bet, cell):
    """'won' / 'lost' / 'push' for a cell, from the bet's score and the cell's text."""
    a, h = (int(x) for x in (bet.get('score') or ex['score']).split('-'))
    text = cell['text']
    three_way = '3-way' in bet['name'].lower()

    def by(x):
        return 'won' if x > 0 else 'push' if x == 0 else 'lost'
    m = re.fullmatch(r'(Over|Under) (\d+(?:\.\d+)?)', text)
    if m:
        d = a + h - float(m.group(2))
        return by(d if m.group(1) == 'Over' else -d)
    if text in ('Yes', 'No'):
        both = a > 0 and h > 0
        return 'won' if both == (text == 'Yes') else 'lost'
    if text in ('NRFI', 'YRFI'):
        scored = a + h > 0
        return 'won' if scored == (text == 'YRFI') else 'lost'
    if text == 'Tie':
        return 'won' if a == h else 'lost'
    mine, theirs = (a, h) if cell['team'] == 'away' else (h, a)
    m = re.fullmatch(r'\S+ ([+-]\d+(?:\.\d+)?)', text)
    if m:   # a spread or run line
        return by(mine - theirs + float(m.group(1)))
    if three_way:
        return 'won' if mine > theirs else 'lost'
    return by(mine - theirs)   # the 2-way moneyline: a tie pushes


class ExamplesTest(unittest.TestCase):
    def test_every_sport_has_two_examples(self):
        for sp in sports.SPORTS:
            self.assertEqual(len(guides.examples(sp['key'])), 2, sp['key'])

    def test_cells_match_the_score_and_line(self):
        for sp in sports.SPORTS:
            for ex in guides.examples(sp['key']):
                for bet in ex['bets']:
                    for c in bet['cells']:
                        self.assertEqual(c['res'], outcome(ex, bet, c), f"{sp['key']} {ex['label']} {bet['name']} {c['text']}")

    def test_label_score_matches(self):
        for sp in sports.SPORTS:
            for ex in guides.examples(sp['key']):
                self.assertIn(ex['score'], ex['label'], ex['label'])
                for bet in ex['bets']:
                    self.assertIn(bet.get('score') or ex['score'], ex['label'], f"{ex['label']} {bet['name']}")

    def test_the_checker_catches_a_typo(self):
        ex = {'score': '28-31', 'bets': []}
        bet = {'name': 'Spread', 'cells': []}
        self.assertEqual(outcome(ex, bet, {'team': 'home', 'text': 'NY -1.5'}), 'won')
        self.assertEqual(outcome(ex, bet, {'team': 'away', 'text': 'BOS +3'}), 'push')
        self.assertEqual(outcome(ex, {'name': 'Total'}, {'text': 'Over 59.5'}), 'lost')

    def test_whole_dollars(self):
        self.assertEqual(guides.money(10000 / 110), '$91')
        self.assertEqual(guides.money(10000 / 150), '$67')
        self.assertEqual(guides.money(100), '$100')


if __name__ == '__main__':
    unittest.main()
