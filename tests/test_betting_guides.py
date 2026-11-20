"""Betting Guides (Nov 19): the 17 pages from content/betting-guides/, their
live numbers ({{sport.segment.stat:window}}, {{asof}}), pipe tables, FAQ and
breadcrumb data, and "Updated" from the last build that changed a number."""
import glob
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import daily  # noqa: E402
import guide_stats as gs  # noqa: E402
import guides  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
FILES = ['index', 'first-segment-betting', 'nhl', 'nba', 'wnba', 'mlb', 'college-basketball', 'nfl',
         'college-football', 'moneyline', 'spread', 'totals', '3-way-moneyline', 'btts', 'nrfi-yrfi',
         'first-five', 'units']


def pages():
    out = ['betting-guides/'] + [f'betting-guides/{s}/' for s, _, _ in guides.GENERAL]
    return out + [sports.guide_path(sp).lstrip('/') for sp in sports.SPORTS]


class TokenTest(unittest.TestCase):
    def test_every_guide_token_is_known(self):
        known = set(gs.table(date(2026, 11, 19)))
        for name in FILES:
            body = daily.parse(open(os.path.join(guides.CONTENT, f'{name}.md'), encoding='utf-8').read())[1]
            for tok in gs.TOKEN.findall(body):
                self.assertIn(tok, known, f'{name}.md: {tok}')

    def test_unknown_token_fails_with_file_and_token(self):
        with self.assertRaises(gs.UnknownToken) as e:
            gs.fill('Over {{nhl.1p.unders:season}} here.', {'asof': 'x'}, 'content/betting-guides/nhl.md')
        self.assertIn('content/betting-guides/nhl.md', str(e.exception))
        self.assertIn('{{nhl.1p.unders:season}}', str(e.exception))

    def test_formats(self):
        self.assertEqual(gs.asof(date(2026, 11, 19)), 'Thursday, Nov 19')
        self.assertEqual(gs.rate(204, 142), '59% (204-142)')
        self.assertEqual(gs.share(1200, 2429), '49% (1,200 of 2,429)')

    def test_pushes_ties_left_out_and_small_windows_dash(self):
        rows = [({}, {'sc': [1, 0], 'tot': 'O', 'su': 'W'})] * 6 + [({}, {'sc': [1, 1], 'tot': 'P', 'su': 'T'})] * 5 + \
               [({}, {'sc': [0, 1], 'tot': 'U', 'su': 'L'})] * 4
        self.assertEqual(gs.value('over', rows, '1p'), '60% (6-4)')
        self.assertEqual(gs.value('home_ml', rows, '1p'), '40% (4-6)')
        self.assertEqual(gs.value('tie', rows, '1p'), '33% (5 of 15)')
        self.assertEqual(gs.value('top_score', rows, '1p'), '1-0 (67%)')
        self.assertEqual(gs.value('over', rows[:9], '1p'), gs.EMPTY)

    def test_off_season_shows_last_season(self):
        t = gs.table(date(2026, 11, 19))
        for w in gs.WINDOWS:
            self.assertRegex(t[f'mlb.1i.nrfi:{w}'], r'^\d+% \([\d,]+ of [\d,]+\) \(\d{4} season\)$')
        self.assertEqual(t['mlb.1i.nrfi:week'], t['mlb.1i.nrfi:season'])


class MarkdownTest(unittest.TestCase):
    def test_pipe_table(self):
        out = daily.to_html('| A | B |\n| --- | --- |\n| 1 | [x](/nhl/odds/) |')
        self.assertIn('<div class="st-card gd-table"><table class="tp-table"><thead><tr><th>A</th><th>B</th></tr></thead>', out)
        self.assertIn('<td><a href="/nhl/odds/">x</a></td>', out)

    def test_faq(self):
        md = 'Intro.\n\n## FAQ\n\n### Is it?\nYes, **mostly**.\n\n### And?\nNo.\n\n## Where to go next\n\nMore.'
        self.assertEqual(guides.faq(md), [('Is it?', 'Yes, mostly.'), ('And?', 'No.')])

    def test_updated_moves_only_when_a_number_changes(self):
        tmp = tempfile.mkdtemp()
        old, guides.LOG = guides.LOG, os.path.join(tmp, 'log.json')
        try:
            with open(guides.LOG, 'w', encoding='utf-8') as f:
                json.dump({'x/': {'numbers': ['59% (1-0)'], 'updated': '2026-11-01'}}, f)
            self.assertEqual(guides.updated('x/', ['59% (1-0)']), '2026-11-01')
            self.assertEqual(guides.updated('x/', ['60% (2-0)']), gs.today_et().isoformat())
        finally:
            guides.LOG = old


class PagesTest(unittest.TestCase):
    def test_all_17_files(self):
        self.assertEqual(sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(guides.CONTENT, '*.md'))), sorted(FILES))
        self.assertFalse(os.path.exists(os.path.join(guides.CONTENT, 'glossary.md')))

    def test_built_pages_indexed_with_breadcrumbs(self):
        sitemap = open(os.path.join(ROOT, 'sitemap.xml'), encoding='utf-8').read()
        self.assertEqual(len(pages()), 17)
        for rel in pages():
            page = open(os.path.join(ROOT, rel, 'index.html'), encoding='utf-8').read()
            with self.subTest(rel):
                self.assertNotIn('content="noindex"', page)
                self.assertNotIn(guides.COMING, page)
                self.assertNotIn('{{', page)
                self.assertIn(f'{rel}</loc>', sitemap)
                if rel != 'betting-guides/':
                    self.assertIn('class="gd-crumb"', page)
                    self.assertIn('"BreadcrumbList"', page)
                    self.assertRegex(page, r'"dateModified": "\d{4}-\d{2}-\d{2}"')

    def test_general_titles_from_front_matter(self):
        page = open(os.path.join(ROOT, 'betting-guides', 'btts', 'index.html'), encoding='utf-8').read()
        title = daily.parse(open(os.path.join(guides.CONTENT, 'btts.md'), encoding='utf-8').read())[0]['title']
        self.assertIn(f'<title>{title}</title>', page.replace('&#x27;', "'"))
        self.assertIn('"FAQPage"', page)


if __name__ == '__main__':
    unittest.main()
