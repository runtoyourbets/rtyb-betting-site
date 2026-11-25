"""
The Odds page's past days (sport_build.write_odds_page): a day with no
Unabated history takes The Odds API backfill's book rows and closing lines,
market by market, with no Open column (close: 1); the admin's saved line is
the best price. Every sport's history file has the same shape.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import sport_build  # noqa: E402
import sports  # noqa: E402

DAY = '2026-07-15'
ML = {'draftkings': {'away': {'price': 150}, 'home': {'price': -180}},
      'betrivers': {'away': {'price': 155}, 'home': {'price': -190}}}
ATS = {'draftkings': {'away': {'line': 4.5, 'price': -110}, 'home': {'line': -4.5, 'price': -110}}}
TOTAL = {'draftkings': {'line': 81.5, 'over': {'price': -110}, 'under': {'price': -110}}}


def history(sport, key, segs):
    """One game's backfill row: {seg: {market: book rows}} -> books and lines."""
    from fetch_odds_unabated import best_of
    books = {seg: dict(mk) for seg, mk in segs.items()}
    lines = {seg: {m: dict(best_of('ml' if m in ('btts', 'nrfi_yrfi') else m, by, ()), books=len(by)) for m, by in mk.items()}
             for seg, mk in segs.items()}
    return {'games': {key: {'date': DAY, 'segments': lines, 'books': books}}}


class PastDays(unittest.TestCase):
    def build(self, sport, segs, admin=None, away='lv', home='conn'):
        sp = sports.BY_KEY[sport]
        key = f'{DAY}|{away}|{home}'
        with tempfile.TemporaryDirectory() as tmp:
            hd = os.path.join(tmp, 'data_feed', 'oddsapi', 'history', sport)
            os.makedirs(hd)
            with open(os.path.join(hd, '2026.json'), 'w') as f:
                json.dump(history(sport, key, segs), f)
            if admin:
                os.makedirs(os.path.join(tmp, 'data_admin', 'odds'))
                with open(os.path.join(tmp, 'data_admin', 'odds', f'{sport}.json'), 'w') as f:
                    json.dump({key: {'segments': admin}}, f)
            sched = {DAY: [{'away': away, 'home': home, 'start': DAY + 'T23:00Z', 'state': 'final', 'score': None, 'res': None}]}
            with mock.patch.object(sport_build, 'ROOT', tmp):
                sport_build.write_odds_page(sp, os.path.join(tmp, 'site'), datetime(2026, 11, 22, tzinfo=timezone.utc), sched)
            with open(os.path.join(tmp, 'site', 'odds', f'{DAY}.json')) as f:
                day = json.load(f)
            with open(os.path.join(tmp, 'site', 'odds.json')) as f:
                index = json.load(f)
        return day['games'][0], index

    def test_backfill_only_day_has_books_and_best(self):
        g, index = self.build('wnba', {'1q': {'ml': ML, 'ats': ATS, 'total': TOTAL}, '1h': {'ml': ML},
                                       'game': {'ml': ML}})   # the full game stays off the Odds page
        self.assertEqual(sorted(g['books']), ['1h', '1q'])
        for seg, ms in (('1q', ('ml', 'ats', 'total')), ('1h', ('ml',))):
            for m in ms:
                self.assertTrue(g['books'][seg][m], (seg, m))
                self.assertTrue(g['best'][seg][m], (seg, m))
        self.assertEqual(set(g['books']['1q']['ml']), {'1', 'betrivers'})   # our source ids
        self.assertEqual(g['best']['1q']['ml'], {'away': 155, 'home': -180})
        self.assertEqual((g['open'], g['close']), ({}, 1))
        self.assertEqual(index['sources']['betrivers']['name'], 'BetRivers')
        self.assertIn(DAY, index['lineDays'])

    def test_admin_line_is_the_best(self):
        g, _ = self.build('wnba', {'1q': {'ml': ML}}, admin={'1q': {'ml': {'away': 160, 'home': -200}}})
        self.assertEqual(g['best']['1q']['ml'], {'away': 160, 'home': -200})

    def test_mlb_nrfi_and_nhl_btts(self):
        rfi = {'fanduel': {'nrfi': {'price': -140}, 'yrfi': {'price': 110}}}
        g, _ = self.build('mlb', {'1i': {'nrfi_yrfi': rfi}}, away='nyy', home='bos')
        self.assertEqual(g['best']['1i']['rfi'], {'nrfi': -140, 'yrfi': 110})
        btts = {'fanduel': {'yes': {'price': 170}, 'no': {'price': -230}}}
        g, _ = self.build('nhl', {'1p': {'btts': btts}}, away='SEA', home='CAR')
        self.assertEqual(g['best']['1p']['btts'], {'yes': 170, 'no': -230})


if __name__ == '__main__':
    unittest.main()
