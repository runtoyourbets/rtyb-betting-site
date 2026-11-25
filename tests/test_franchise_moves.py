"""
Franchise moves (sports.MOVES): the Connecticut Sun (slug conn, code CON)
become the Houston Comets (slug hou, code HOU) from the 2027 WNBA season.
2026 and earlier games keep the Sun; 2027 games file under the Comets, and
the Comets' team page shows the Sun's 2026 season as its Last season.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import sports  # noqa: E402
import fetch_sport_games  # noqa: E402
import fetch_odds_unabated  # noqa: E402


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def wnba_teams():
    return json.loads(read(os.path.join(ROOT, 'data_seed', 'teams', 'wnba.json')))['teams']


def event(year, away_id='18', home_id='9'):
    return {'id': '1', 'date': f'{year}-06-01T23:00Z', 'season': {'year': year, 'type': 2},
            'competitions': [{'status': {'type': {'name': 'STATUS_SCHEDULED', 'state': 'pre'}}, 'competitors': [
                {'homeAway': 'away', 'team': {'id': away_id, 'displayName': 'Away'}},
                {'homeAway': 'home', 'team': {'id': home_id, 'displayName': 'Home'}}]}]}


class Moves(unittest.TestCase):
    def test_the_sun_keep_their_slug_and_code_through_2026(self):
        sun = next(t for t in wnba_teams() if t['espn_id'] == '18')
        self.assertEqual((sun['slug'], sun['code'], sun['name']), ('conn', 'CON', 'Connecticut Sun'))
        self.assertEqual(sports.season_teams('wnba', [sun], 2026), [sun])
        self.assertEqual(sports.franchise_slug('wnba', 'conn', 2026), 'conn')

    def test_2027_on_the_franchise_is_the_houston_comets(self):
        t = next(t for t in sports.season_teams('wnba', wnba_teams(), 2027) if t['espn_id'] == '18')
        self.assertEqual((t['slug'], t['code'], t['name'], t['short']), ('hou', 'HOU', 'Houston Comets', 'Comets'))
        self.assertEqual(t['formerly']['slug'], 'conn')
        self.assertEqual(t['formerly']['code'], 'CON')
        self.assertEqual(sports.franchise_slug('wnba', 'conn', 2028), 'hou')

    def test_fetched_games_file_under_the_team_of_their_season(self):
        slugs = fetch_sport_games.load_teams('wnba')
        for year, want in ((2026, 'conn'), (2027, 'hou')):
            g = fetch_sport_games.parse_event('wnba', event(year), slugs)
            self.assertEqual(g['away'], want, year)

    def test_the_odds_feeds_know_the_comets(self):
        aliases = fetch_odds_unabated.team_aliases('wnba')
        self.assertIn('houston comets', aliases['hou'])
        self.assertIn('connecticut sun', aliases['conn'])
        self.assertIn('hou', sports.league_slugs('wnba', wnba_teams()))

    def test_no_logo_for_the_comets_until_one_is_added(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'assets', 'logos', 'wnba', 'hou.png')))
        self.assertTrue(os.path.exists(os.path.join(ROOT, 'assets', 'logos', 'wnba', 'conn.png')))

    def test_the_team_page_reads_last_season_as_the_old_team(self):
        js = read(os.path.join(ROOT, 'assets', 'sport.js'))
        self.assertIn("var slug = TP.which === 'last' && (D.formerSlugs || {})[TEAM] || TEAM;", js)
        self.assertIn('if ((D.formerTeams || {})[slug]) return D.formerTeams[slug];', js)


if __name__ == '__main__':
    unittest.main()
