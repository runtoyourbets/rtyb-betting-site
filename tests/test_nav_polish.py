"""Navigation polish (Nov 19): the phone ☰ menu (ALL SPORTS row, sport rows
that open in place) and the league icons before sport names."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import front  # noqa: E402
import nav  # noqa: E402
import sports  # noqa: E402


class MenuTest(unittest.TestCase):
    def setUp(self):
        self.html = nav.header('/', [(sp,) for sp in sports.LAUNCHED], current='matchups')

    def test_order_and_all_sports_row(self):
        h = self.html
        self.assertLess(h.index('>All sports</p>'), h.index('>Sports</p>'))
        self.assertLess(h.index('>Sports</p>'), h.index('>More</p>'))
        all_row = h[h.index('<div class="hm-all">'):h.index('>Sports</p>')]
        self.assertEqual(all_row.count('class="hm-all-btn'), 5)
        self.assertIn('hm-all-btn gold', all_row)
        self.assertIn('/' + sports.INDEX_FOLDERS['picks'], all_row)

    def test_sport_rows(self):
        h = self.html
        self.assertNotIn('hm-plus', h)
        sp = sports.LAUNCHED[0]
        self.assertIn(f'{sp["label"]} Home &rarr;</a>', h)
        self.assertIn("rows.forEach(function(x) {", h)   # one sport open at a time

    def test_icons(self):
        self.assertIn('class="sport-icon', self.html[self.html.index('hr2-sports'):])
        self.assertIn('<svg', front.pills('Sport', [('nhl', 'NHL', '<svg class="sport-icon"></svg>')]))


if __name__ == '__main__':
    unittest.main()
