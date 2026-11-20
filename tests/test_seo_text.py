"""SEO page text (content/seo/, scripts/seo_text.py) and the one footer
(scripts/nav.py footer()): titles and descriptions unique, descriptions
110-165 characters, every page with a file (and every sport and team page)
with its About block closed, no "RTYB", one FAQPage per page, the footer
and its 21+ line on every page."""
import collections
import html
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import guide_stats  # noqa: E402
import seo  # noqa: E402
import seo_text  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABOUT = re.compile(r'<details class="how-to-read seo-about"(?P<open>[^>]*)>.*?</details>', re.S)
_BUILT = None


def built():
    """[(rel, html)] for every built page but redirect stubs."""
    global _BUILT
    if _BUILT is None:
        _BUILT = []
        for rel in seo.pages():
            with open(os.path.join(ROOT, rel, 'index.html'), encoding='utf-8') as f:
                page = f.read()
            if 'http-equiv="refresh"' not in page:
                _BUILT.append((rel, page))
    return _BUILT


def head(page):
    t = re.search(r'<title>(.*?)</title>', page, re.S)
    return html.unescape(t.group(1).strip()) if t else '', seo.meta(page, 'description')


def team_page(rel):
    return re.fullmatch(r'[a-z-]+/teams/[^/]+/', rel) is not None and seo_text.sport_of(rel) is not None


class FilesTest(unittest.TestCase):
    def test_every_file_has_a_path_title_and_description(self):
        got = seo_text.files()
        self.assertEqual(len(got), 62)
        for rel, (name, meta, body) in got.items():
            with self.subTest(name):
                self.assertTrue(meta.get('title') and meta.get('description'))
                self.assertTrue(body.lstrip().startswith('## '))
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel, 'index.html')), rel)

    def test_every_token_is_known(self):
        vals = seo_text.sample_values()
        for rel, (name, meta, body) in seo_text.files().items():
            for text in (body, str(meta.get('title')), str(meta.get('description')), str(meta.get('description_offseason') or '')):
                guide_stats.fill(text, vals, name)   # raises UnknownToken

    def test_unknown_token_names_the_file(self):
        with self.assertRaises(guide_stats.UnknownToken) as e:
            guide_stats.fill('{{nhl.9p.over:season}}', seo_text.sample_values(), 'content/seo/x.md')
        self.assertIn('content/seo/x.md', str(e.exception))

    def test_unknown_path_fails(self):
        with self.assertRaises(seo_text.UnknownPath):
            seo_text.Pass({''}, {})

    # Chris's approved copy, loaded as written, runs under 110 here (flagged, not rewritten)
    SHORT_OK = {('content/seo/nhl__odds.md', 'description_offseason'), ('content/seo/nhl__teams.md', 'description_offseason')}

    def test_descriptions_110_to_165_with_sample_values(self):
        vals = seo_text.sample_values()
        for rel, (name, meta, body) in seo_text.files().items():
            if rel.endswith('preview/'):   # the day's headline: any length
                continue
            for key in ('description', 'description_offseason'):
                if meta.get(key) and (name, key) not in self.SHORT_OK:
                    d = seo_text.plain(guide_stats.fill(str(meta[key]), vals, name))
                    with self.subTest(f'{name} {key}'):
                        self.assertTrue(110 <= len(d) <= 165, f'{len(d)}: {d}')

    def test_off_season_title(self):
        ctx = type('C', (), {'off': True, 'year': '2026'})()
        title, _ = seo_text.head_text({'title': 'MLB First Inning & First Five Odds Today | Run To Your Bets', 'description': 'x'},
                                      ctx, seo_text.sample_values(), 'x')
        self.assertEqual(title, 'MLB First Inning & First Five Odds 2026 Season | Run To Your Bets')
        title, _ = seo_text.head_text({'title': 'NFL Odds Week {{week}} | Run To Your Bets', 'description': 'x'},
                                      ctx, seo_text.sample_values(), 'x')
        self.assertEqual(title, 'NFL Odds 2026 Season | Run To Your Bets')


class BuiltPagesTest(unittest.TestCase):
    def test_titles_and_descriptions_unique(self):
        titles, descs = collections.defaultdict(list), collections.defaultdict(list)
        for rel, page in built():
            if 'content="noindex"' in page:
                continue
            t, d = head(page)
            titles[t].append(rel)
            descs[d].append(rel)
        self.assertEqual({t: r for t, r in titles.items() if len(r) > 1}, {})
        self.assertEqual({d: r for d, r in descs.items() if len(r) > 1}, {})

    def test_team_descriptions_110_to_165(self):
        n = 0
        for rel, page in built():
            if team_page(rel):
                n += 1
                d = head(page)[1]
                with self.subTest(rel):
                    self.assertTrue(110 <= len(d) <= 165, f'{len(d)}: {d}')
        self.assertGreater(n, 600)

    def test_about_block_closed(self):
        files = seo_text.files()
        for rel, page in built():
            if rel in files or team_page(rel):
                m = ABOUT.search(page)
                with self.subTest(rel):
                    self.assertIsNotNone(m)
                    self.assertNotIn('open', m.group('open'))
                    self.assertEqual(len(ABOUT.findall(page)), 1)

    def test_about_above_betting_guides_and_footer(self):
        for rel, page in built():
            m = ABOUT.search(page)
            if not m:
                continue
            with self.subTest(rel):
                for after in ('class="gd-block"', 'id="learn"', '<footer class="sf"'):
                    if after in page:
                        self.assertLess(m.start(), page.index(after), after)
                if 'class="how-to-read"' in page:
                    self.assertLess(page.index('class="how-to-read"'), m.start())

    def test_no_rtyb(self):
        for rel, page in built():
            t, d = head(page)
            m = ABOUT.search(page)
            with self.subTest(rel):
                self.assertNotIn('RTYB', t)
                self.assertNotIn('RTYB', d)
                self.assertNotIn('RTYB', m.group(0) if m else '')
                self.assertNotIn('RTYB', seo.meta(page, 'og:site_name'))

    def test_one_faqpage(self):
        for rel, page in built():
            with self.subTest(rel):
                self.assertLessEqual(page.count('"FAQPage"'), 1)

    def test_structured_data(self):
        pages = dict(built())
        self.assertIn('"WebSite"', pages[''])
        self.assertIn('"Organization"', pages[''])
        self.assertIn('"name": "Edmonton Oilers"', pages['nhl/teams/edm/'])
        self.assertIn('"BreadcrumbList"', pages['nhl/odds/'])

    def test_footer_on_every_page(self):
        for rel, page in built():
            with self.subTest(rel):
                self.assertEqual(page.count('<footer class="sf">'), 1)
                self.assertIn('class="sf-21">21+</span>', page)
                self.assertIn('href="tel:18004262537">1-800-GAMBLER</a>', page)


class TeamTextTest(unittest.TestCase):
    def test_bet_flips_for_home(self):
        g = {'away': 'a', 'home': 'h', 'res': {'1p': {'sc': [1, 0], 'su': 'W', 'tot': 'U', 'btts': 'N',
                                                    'u': {'su': [1.1, -1.0], 'tot': [-1.0, 0.8]}}}}
        self.assertEqual(seo_text.bet(g, '1p', 'ml', 'a')[:2], ('W', 1.1))
        self.assertEqual(seo_text.bet(g, '1p', 'ml', 'h')[:2], ('L', -1.0))
        self.assertEqual(seo_text.bet(g, '1p', 'total', 'h')[0], 'L')

    def test_rates_leave_ties_out(self):
        gs = [{'away': 'a', 'home': 'h', 'res': {'1p': {'sc': [0, 0], 'su': x}}} for x in ('W', 'W', 'L', 'T')]
        a = seo_text.Agg(gs, '1p', 'ml', 'a')
        self.assertEqual(a.rate(), '67% (2-1-1)')


if __name__ == '__main__':
    unittest.main()
