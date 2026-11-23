"""
Head to head pages (scripts/h2h.py): the URL helper, every matchup link the
pages draw resolves to a built page (the other order to its stub), and a
pair with no meeting yet this season shows last season's meetings and the
next scheduled game.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import h2h  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


class SlugTest(unittest.TestCase):
    def test_alphabetical_and_the_same_for_both_orders(self):
        self.assertEqual(sports.matchup_slug('Kings', 'Celtics'), 'celtics-vs-kings')
        self.assertEqual(sports.matchup_slug('Celtics', 'Kings'), 'celtics-vs-kings')
        self.assertEqual(sports.matchup_slug('North Carolina', 'Duke'), 'duke-vs-north-carolina')
        self.assertEqual(sports.matchup_slug('Duke', 'North Carolina'), 'duke-vs-north-carolina')

    def test_college_duplicates_stay_distinct(self):
        self.assertEqual(sports.team_slug('Miami (OH)'), 'miami-oh')
        self.assertEqual(sports.team_slug('Miami'), 'miami')
        self.assertEqual(sports.matchup_slug('Miami (OH)', 'Miami'), 'miami-vs-miami-oh')
        self.assertEqual(sports.team_slug("Saint Mary's"), 'saint-marys')
        self.assertEqual(sports.team_slug('Texas A&M'), 'texas-a-and-m')

    def test_every_team_has_its_own_url_name(self):
        for sp in sports.SPORTS:
            doc = h2h.load_doc(sp)
            parts = [h2h.team_part(doc, k) for k in doc.get('teams') or {}]
            with self.subTest(sp['key']):
                self.assertEqual(len(parts), len(set(parts)))


class LinksTest(unittest.TestCase):
    def test_every_matchup_link_resolves(self):
        """Every game this season with both teams in the league links to a
        built page (Matchups cards, Odds rows, team pages, Slate, Preview);
        the other order is a stub with a canonical to it."""
        for sp in sports.SPORTS:
            doc = h2h.load_doc(sp)
            seen = set()
            for _, g in h2h.all_games(doc.get('games')):
                p = h2h.path(sp, doc, g['away'], g['home'])
                if not p or p in seen:
                    continue
                seen.add(p)
                with self.subTest(p):
                    self.assertTrue(os.path.exists(os.path.join(ROOT, p.strip('/'), 'index.html')))
                    a, b = re.match(r'(.+)-vs-(.+)', p.strip('/').split('/')[-1]).groups()
                    stub = open(os.path.join(ROOT, p.strip('/').rsplit('/', 1)[0], f'{b}-vs-{a}', 'index.html'), encoding='utf-8').read()
                    self.assertIn(f'<link rel="canonical" href="../{a}-vs-{b}/">', stub)
            with self.subTest(sp['key']):
                self.assertTrue(seen or not doc.get('games'))


def game(gid, away, home, state, start, a=None, h=None):
    return {'id': gid, 'away': away, 'home': home, 'state': state, 'start': start, 'as': a, 'hs': h,
            'res': {'1q': {'sc': [30, 25], 'su': 'W'}} if state == 'final' else None}


class NoMeetingYetTest(unittest.TestCase):
    def test_last_season_and_the_next_game(self):
        sp = sports.BY_KEY['nba']
        doc = {'teams': {'bos': {'short': 'Celtics', 'name': 'Boston Celtics'}, 'sac': {'short': 'Kings', 'name': 'Sacramento Kings'}},
               'games': {'2026-12-04': [game(3, 'bos', 'sac', 'pre', '2026-12-05T03:00:00Z')]}}
        prev = {'2026-01-01': [game(1, 'bos', 'sac', 'final', '2026-01-02T03:00:00Z', 120, 106)],
                '2026-01-30': [game(2, 'sac', 'bos', 'final', '2026-01-31T00:30:00Z', 93, 112)]}
        prev['2026-01-30'][0]['res']['1q']['sc'] = [25, 40]   # the home Celtics' 1Q
        a, b = h2h.pairs(sp, doc, prev)[0]
        cur, old = h2h.meetings(doc['games'], a, b), h2h.meetings(prev, a, b)
        head = h2h.header_game(cur, old)
        self.assertEqual((head[1]['id'], head[2]), (3, 'next'))
        body = h2h.body(sp, doc, a, b, cur, old, '2025-26', head, '')
        self.assertIn('Next meeting', body)
        self.assertIn('Fri, Dec 4, 2026 · 10:00 PM ET · Celtics @ Kings', body)
        self.assertIn('Jan 30, 2026 · Kings 93 @ Celtics 112', body)
        self.assertIn('Jan 1, 2026 · Celtics 120 @ Kings 106', body)
        self.assertIn('"id":1', body)   # last season's meetings for the page script
        m = h2h.meta(sp, doc, a, b, cur, old, '2025-26', head)
        self.assertEqual(m['title'], 'Celtics vs Kings First Quarter & First Half Odds, Trends & Head to Head | Run To Your Bets')
        self.assertEqual(m['h1'], 'Celtics vs Kings: 1st Quarter & 1st Half Matchup')
        self.assertIn('2 meetings since 2025-26; the Celtics won the 1Q in 2. Next game Dec 4.', m['desc'])

    def test_college_pairs_only_when_they_met_or_are_scheduled(self):
        sp = sports.BY_KEY['ncaab']
        doc = {'teams': {k: {'short': k.title()} for k in ('duke', 'unc', 'iowa')},
               'games': {'2026-12-01': [game(1, 'duke', 'unc', 'pre', '2026-12-01T23:00:00Z')]}}
        prev = {'2026-02-01': [game(2, 'iowa', 'duke', 'final', '2026-02-01T23:00:00Z', 70, 80),
                               game(3, 'iowa', 'other-school', 'final', '2026-02-01T23:00:00Z', 70, 50)]}
        self.assertEqual(h2h.pairs(sp, doc, prev), [('duke', 'iowa'), ('duke', 'unc')])
        self.assertEqual(len(h2h.pairs(sports.BY_KEY['nba'], doc, {})), 3)   # pro: every pair


if __name__ == '__main__':
    unittest.main()
