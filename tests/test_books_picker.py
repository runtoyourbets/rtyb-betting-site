"""
The Books picker (assets/sport.js "My books", sport_build.picker_books,
bignums' data-bn-px): unpicking a book removes its column and it never sets
the best price; the defaults follow the Books tab's groups (Sportsbooks on,
Offshore and Exchanges off); with storage blocked the page renders the
defaults; the browser's best price matches the build's (best_of) on the
same books.
"""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import books  # noqa: E402
import fetch_odds_unabated as feed  # noqa: E402
import sport_build  # noqa: E402
from test_game_log import NODE, SRC, function  # noqa: E402

PICKER = [{'id': '1', 'name': 'DraftKings', 'g': 'Sportsbook'}, {'id': '2', 'name': 'FanDuel', 'g': 'Sportsbook'},
          {'id': '4', 'name': 'BetMGM', 'g': 'Sportsbook'}, {'id': 'bovada', 'name': 'Bovada', 'g': 'Offshore'},
          {'id': '105', 'name': 'Kalshi', 'g': 'Exchange'}]
SOURCES = {'1': {}, '2': {}, '4': {}, 'bovada': {'off': 1, 'nb': 1}, '105': {'x': 1}}


def ml(a, h):
    return {'away': {'price': a}, 'home': {'price': h}}


def ats(line, a, h):
    return {'away': {'line': line, 'price': a}, 'home': {'line': -line, 'price': h}}


def tot(line, o, u):
    return {'line': line, 'over': {'price': o}, 'under': {'price': u}}


@unittest.skipUnless(NODE, 'node is not installed')
class PickerTest(unittest.TestCase):
    def run_js(self, body, storage='{}'):
        js = ('var localStorage = ' + storage + ';\nvar MB_KEY = "rtyb-mybooks", MB = null;\n' + '\n'.join(
            function(SRC, n) for n in ('mbLoad', 'mbSave', 'mbOn', 'mbDefault', 'mbPicked', 'mbColumns', 'mbImplied',
                                       'mbDropOutliers', 'mbBest', 'pickedBest')) +
              '\nvar PICKER = %s, SOURCES = %s;\n' % (json.dumps(PICKER), json.dumps(SOURCES)) + body)
        out = subprocess.run([NODE, '-e', js], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_defaults_follow_the_groups(self):
        got = self.run_js('MB = mbLoad(); console.log(JSON.stringify(PICKER.map(function(b) { return mbPicked(b.id, PICKER, SOURCES); })));')
        self.assertEqual(got, [True, True, True, False, False])

    def test_storage_blocked_renders_the_defaults(self):
        blocked = '{ getItem: function() { throw new Error("blocked"); }, setItem: function() { throw new Error("blocked"); } }'
        got = self.run_js("""MB = mbLoad();
var cols = mbColumns(['1', '2', '4', 'bovada', '105'], {'1': 1, '2': 1, '4': 1, 'bovada': 1, '105': 1}, PICKER, SOURCES);
mbSave(['1'], ['1', '2', '4', 'bovada', '105']);   // not remembered, but this page uses it
console.log(JSON.stringify([cols, mbColumns(['1', '2', '4'], {'1': 1, '2': 1, '4': 1}, PICKER, SOURCES)]));""", blocked)
        self.assertEqual(got, [['1', '2', '4'], ['1']])

    def test_unpicked_book_loses_its_column_and_never_sets_the_best_price(self):
        game = {'best': {'1h': {'ml': {'away': 120, 'home': -110}}},
                'books': {'1h': {'ml': {'1': ml(110, -120), '2': ml(120, -125), '4': ml(105, -110)},
                                 'ats': {'1': ats(2.5, -110, -110), '2': ats(2.5, -100, -115), '4': ats(2.5, -112, -108)},
                                 'total': {'1': tot(110.5, -110, -110), '2': tot(110.5, -102, -118), '4': tot(110.5, -115, -105)}}}}
        got = self.run_js("""var store = {};
var all = ['1', '2', '4', 'bovada', '105'];
localStorage = { getItem: function(k) { return store[k] || null; }, setItem: function(k, v) { store[k] = v; } };
var g = %s, before = pickedBest(g, '1h', 'ml', PICKER, SOURCES);
mbSave(['1', '4'], all);
MB = mbLoad();
console.log(JSON.stringify({ before: before, cols: mbColumns(all, {'1': 1, '2': 1, '4': 1, '105': 1}, PICKER, SOURCES),
  ml: pickedBest(g, '1h', 'ml', PICKER, SOURCES), ats: pickedBest(g, '1h', 'ats', PICKER, SOURCES), total: pickedBest(g, '1h', 'total', PICKER, SOURCES) }));""" % json.dumps(game))
        self.assertEqual(got['before'], {'away': 120, 'home': -110})   # nothing saved: the build's
        self.assertEqual(got['cols'], ['1', '4'])
        self.assertEqual(got['ml'], {'away': 110, 'home': -110})       # FanDuel's +120 is gone
        self.assertEqual(got['ats'], {'away': {'line': 2.5, 'price': -110}, 'home': {'line': -2.5, 'price': -108}})
        self.assertEqual(got['total'], {'line': 110.5, 'over': -110, 'under': -105})

    def test_exchange_picked_never_sets_the_best_price(self):
        game = {'books': {'1p': {'ml': {'1': ml(110, -130), '105': ml(150, -100)}}}}
        got = self.run_js("""MB = { on: ['1', '105'], known: ['1', '105'] };
console.log(JSON.stringify(pickedBest(%s, '1p', 'ml', PICKER, SOURCES)));""" % json.dumps(game))
        self.assertEqual(got, {'away': 110, 'home': -130})

    def test_same_best_price_as_the_build(self):
        cases = [('ml', {'1': ml(110, -130), '2': ml(115, -135), '4': ml(250, -300), '20': ml(112, -132)}),   # 4: an outlier
                 ('ats', {'1': ats(3.5, -110, -110), '2': ats(3.5, -105, -115), '4': ats(4.5, -120, 100), '20': ats(4.5, -118, -102)}),
                 ('total', {'1': tot(220.5, -110, -110), '2': tot(221.5, -108, -112), '4': tot(220.5, -105, -115), '20': tot(222.5, -110, -110)})]
        js = 'MB = { on: ["1", "2", "4", "20"], known: ["1", "2", "4", "20"] };\nconsole.log(JSON.stringify(%s.map(function(c) { return mbBest(c[0], c[1], [], {}); })));' % json.dumps(cases)
        got = self.run_js(js)
        self.assertEqual(got, [json.loads(json.dumps(feed.best_of(m, rows, ()))) for m, rows in cases])


class PickerListTest(unittest.TestCase):
    def test_admin_order_shown_books_and_groups(self):
        cfg = books.Settings([{'id': '2', 'name': 'FanDuel', 'group': 'Sportsbook'},
                              {'id': '105', 'name': 'Kalshi', 'group': 'Exchange'},
                              {'id': 'bovada', 'name': 'Bovada', 'group': 'Offshore', 'best': False},
                              {'id': '1', 'name': 'DraftKings', 'group': 'Sportsbook'},
                              {'id': '60', 'name': 'theScore CA', 'group': 'Sportsbook', 'show': False}])
        got = sport_build.picker_books(cfg, {'1', '2', '105', 'consensus'}, {})
        self.assertEqual([(b['id'], b['g']) for b in got], [('2', 'Sportsbook'), ('105', 'Exchange'), ('bovada', 'Offshore'), ('1', 'Sportsbook')])


class BigNumbersPricesTest(unittest.TestCase):
    def test_cell_choices_at_the_line(self):
        import bignums
        rows = {'1': ats(-6.5, -110, -110), '2': ats(-6.5, -105, -115), '4': ats(-7.5, 100, -120)}
        self.assertEqual(bignums.prices_at(rows, 'away', -6.5, bignums.side_line), {'1': -110, '2': -105})


if __name__ == '__main__':
    unittest.main()
