"""
Due Factor (scripts/due_factor.py): the meter against a hand count, the
last 7 game days when the last 7 days had none, and the tint rule.
"""
import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import due_factor as df  # noqa: E402
import nav  # noqa: E402
import sports  # noqa: E402

TODAY = date(2026, 11, 23)
ML = {'ml': {'away': -120, 'home': 100}}


def game(tot, su=None, ml=True):
    x = {'tot': tot}
    if su:
        x['su'] = su
    return {'away': 'a', 'home': 'h', 'state': 'final', 'odds': {'1q': dict(ML) if ml else {}}, 'res': {'1q': x}}


# NBA 1Q. Season: Nov 1 (4 games) + the last 7 days (Nov 20, Nov 22).
GAMES = ([('2026-11-01', game(t, s)) for t, s in (('O', 'W'), ('U', 'W'), ('U', 'W'), ('U', 'L'))]
         + [('2026-11-20', game('O', 'L')), ('2026-11-20', game('O', 'L'))]
         + [('2026-11-22', game('O', 'W')), ('2026-11-22', game('U', 'T')), ('2026-11-22', game('P', 'L', ml=False))])


def run(games, today=TODAY, key='nba'):
    df._CACHE.clear()
    doc = {'seasonLabel': '2026-27', 'games': {}}
    with mock.patch.object(df, 'season_games', lambda sp: (doc, games)):
        return df.compute(sports.BY_KEY[key], today)


class MeterTest(unittest.TestCase):
    def test_meter_matches_a_hand_count(self):
        g = run(GAMES)['groups'][0]
        self.assertEqual(g['key'], '1q')
        self.assertEqual(g['win'], ['2026-11-20', '2026-11-22'])
        self.assertEqual(g['win_label'], 'last 7 days')
        rows = {m.id: (w, s, gap) for m, w, s, gap in g['daily']}
        # Over: last 7 days O-U 3-1 (the push out) = 75%; season 4-4 = 50%
        w, s, gap = rows['over']
        self.assertEqual((w.s, w.o, w.t, s.s, s.o), (3, 1, 1, 4, 4))
        self.assertEqual(gap, 25)
        self.assertEqual(df.chip(gap), ('Hot', 'heat-4'))
        # Home ML (su is the away side; ties out, the game with no ML out):
        # last 7 days H-A 2-1 = 67%; season 3-4 = 43%: +24
        w, s, gap = rows['home']
        self.assertEqual((w.s, w.o, w.t, s.s, s.o), (2, 1, 1, 3, 4))
        self.assertEqual(gap, 24)
        # the biggest gap first
        self.assertEqual([m.id for m, _, _, _ in g['daily']][:2], ['over', 'home'])
        over = next(m for m in g['markets'] if m.id == 'over')
        self.assertEqual(df.rec_txt(over, rows['over'][0]), '3-1 O-U')

    def test_meter_matches_a_hand_count_on_the_real_nhl_data(self):
        df._CACHE.clear()
        sp = sports.BY_KEY['nhl']
        g = df.data(sp, TODAY)['groups'][0]
        _, games = df.season_games(sp)
        win = set(g['win'])
        o = u = so = su = 0
        for d, x in games:
            r = (x.get('res') or {}).get('1p') or {}
            if r.get('tot') in ('O', 'U'):
                so += r['tot'] == 'O'
                su += r['tot'] == 'U'
                if d in win:
                    o += r['tot'] == 'O'
                    u += r['tot'] == 'U'
        w, s = next((w, s) for m, w, s, _ in g['daily'] if m.id == 'over')
        self.assertEqual((w.s, w.o, s.s, s.o), (o, u, so, su))

    def test_chip_steps(self):
        self.assertEqual(df.chip(4), ('On pace', ''))
        self.assertEqual(df.chip(-4), ('On pace', ''))
        self.assertEqual(df.chip(5), ('Leaning hot', 'heat-2'))
        self.assertEqual(df.chip(-9), ('Leaning cold', 'heat-1'))
        self.assertEqual(df.chip(-10), ('Cold', 'heat-3'))
        self.assertEqual(df.chip(14), ('Hot', 'heat-3'))
        self.assertEqual(df.chip(-15), ('Cold', 'heat-4'))


class WindowTest(unittest.TestCase):
    def test_no_games_in_the_last_7_days_shows_the_last_7_game_days(self):
        days = [f'2026-10-{d:02d}' for d in range(1, 11)]
        games = [(d, game('O' if i % 2 else 'U', 'W')) for i, d in enumerate(days)]
        g = run(games, today=date(2026, 11, 23))['groups'][0]
        self.assertEqual(g['win_label'], 'last 7 game days')
        self.assertEqual(g['win'], days[-7:])
        self.assertEqual(g['game_days'], days[-7:])
        w = next(w for m, w, _, _ in g['daily'] if m.id == 'over')
        self.assertEqual(w.n, 7)

    def test_postseason_is_out(self):
        post = dict(game('O', 'W'), post=True)
        with mock.patch.object(df.guide_stats, 'load', lambda sp: {'games': {}}), \
                mock.patch.object(df.guide_stats, 'finals', lambda doc, key: [('2026-11-20', post), ('2026-11-20', game('U', 'W'))]):
            _, games = df.season_games(sports.BY_KEY['nba'])
        self.assertEqual(len(games), 1)


class TintTest(unittest.TestCase):
    def count(self, s, o):
        c = df.Count()
        c.s, c.o = s, o
        return c

    def test_tint_only_on_the_side_10_above_its_season_rate(self):
        ms = {m.id: m for m in df.groups(sports.BY_KEY['nba'])[0][2]}
        season = self.count(50, 50)
        # Over 10+ above: warm; the Under 10+ above: cool; within 10: none
        self.assertEqual(df.tint(ms['over'], self.count(6, 4), season), 'df-warm')
        self.assertEqual(df.tint(ms['over'], self.count(4, 6), season), 'df-cool')
        self.assertEqual(df.tint(ms['over'], self.count(59, 41), season), '')
        # side markets: the win fill when the side shown (Home) is 10+ above;
        # never when it's the other side (Away) that's above
        self.assertEqual(df.tint(ms['home'], self.count(6, 4), season), 'df-win')
        self.assertEqual(df.tint(ms['home'], self.count(4, 6), season), '')
        self.assertEqual(df.tint(ms['fav_ats'], self.count(2, 8), season), '')

    def test_tinted_cells_in_the_day_table(self):
        g = run(GAMES)['groups'][0]
        html = df.table_html(g, [(df.day_name(d), [d]) for d in reversed(g['game_days'])], 'Last 7 days', g['win'], 'Day')
        # Nov 20: Over 2-0 (100% vs 50%) warm, Home 2-0 (100% vs 43%) win fill
        nov20 = html.split('Fri, Nov 20')[1].split('</tr>')[0]
        self.assertIn('df-c df-warm', nov20)
        self.assertIn('df-c df-win', nov20)
        self.assertNotIn('df-cool', nov20)


class PageTest(unittest.TestCase):
    def test_every_sport_gets_the_page_and_the_menu_link(self):
        now = datetime(2026, 11, 23, 17, tzinfo=timezone.utc)
        for sp in sports.SPORTS:
            with self.subTest(sp['key']):
                self.assertEqual(sports.section_path(sp, 'due'), f"/{sp['slug']}/due-factor/")
                self.assertIn(('due', 'Due Factor', f"/{sp['slug']}/due-factor/"), sports.page_links(sp))
                body = df.page_body(sp, TODAY, now)
                self.assertIn('data-view-btn="daily"', body)
                self.assertIn(f'data-view="{"weekly" if sp.get("schedule") == "week" else "daily"}"', body)
                self.assertNotIn('about to hit</', body.replace('not a sign that a side is about to hit.</p>', ''))
                meta = df.page_meta(sp)
                self.assertTrue(meta['title'].startswith(f'{sports.seo_name(sp)} Due Factor: {sports.seg_words(sp)} Hot and Cold Trends'))
        self.assertEqual(nav.SECTION_TAB['due'], 'trends')

    def test_off_season_pages_say_the_season(self):
        now = datetime(2026, 11, 23, 17, tzinfo=timezone.utc)
        body = df.page_body(sports.BY_KEY['mlb'], TODAY, now)
        self.assertIn('2026 season · Last 7 game days', body)

    def test_strip_only_for_gaps_of_10_or_more(self):
        df._CACHE.clear()
        with mock.patch.object(df, 'compute', lambda sp, today: {'off': False, 'groups': [{'daily': [(df.groups(sp)[0][2][0], None, None, 9)], 'weekly': []}]}):
            self.assertIsNone(df.strip_item(sports.BY_KEY['nba'], TODAY))
        df._CACHE.clear()
        with mock.patch.object(df, 'compute', lambda sp, today: {'off': False, 'groups': [{'daily': [(df.groups(sp)[0][2][2], None, None, -14)], 'weekly': []}]}):
            self.assertEqual(df.strip_item(sports.BY_KEY['nba'], TODAY)[0], 'NBA 1Q Over -14')
        df._CACHE.clear()


if __name__ == '__main__':
    unittest.main()
