"""Definitions (Nov 19 spec): content/definitions.json holds every "i" box
text, only Live text reaches the site, the build lists new ids as Needs
definition, and the Betting Glossary comes from Live Markets & terms."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import definitions  # noqa: E402
import guides  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


def read(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
        return f.read()


class FileTest(unittest.TestCase):
    def test_entries_are_valid(self):
        doc = definitions.load()
        cats = {c for c, _ in definitions.CATEGORIES}
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'content', 'trend_tooltips.json')))
        for i, e in doc['entries'].items():
            self.assertRegex(i, r'^(label|trend|team|split|edge|term|feature):[A-Za-z0-9_-]+$')
            self.assertIn(e['category'], cats, i)
            self.assertIn(e['status'], ('needs', 'draft', 'live'), i)
            self.assertLessEqual(len(e.get('short') or ''), definitions.SHORT_MAX, i)
            if e['status'] == 'live':
                self.assertTrue(e.get('short'), i)
            if e['category'] != 'league':
                self.assertNotIn('show_last', e, i)

    def test_only_live_text_reaches_the_site(self):
        doc = {'config': {}, 'entries': {
            'trend:a': {'name': 'A', 'category': 'league', 'status': 'draft', 'short': 'draft text', 'group': 'side_angles'},
            'trend:b': {'name': 'B', 'category': 'league', 'status': 'live', 'short': 'live text', 'group': 'game_angles'},
            'term:units': {'name': 'Units', 'category': 'terms', 'status': 'live', 'short': 'u'},
            'term:push': {'name': 'Push', 'category': 'terms', 'status': 'draft', 'short': 'p'}}}
        T = definitions.tooltips(doc)
        self.assertEqual(T['side_angles']['a']['meaning'], '')
        self.assertEqual(T['side_angles']['a']['title'], 'A')
        self.assertEqual(T['game_angles']['b']['meaning'], 'live text')
        self.assertEqual([t[0] for t in definitions.glossary_terms(doc)], ['units'])

    def test_build_finds_new_ids(self):
        K = definitions.known()
        self.assertIn('label:lockdown', K)
        self.assertTrue(any(i.startswith('trend:') for i in K))
        self.assertTrue(any(i.startswith('split:') for i in K))
        self.assertEqual(K['team:btts_Y']['sports'], ['nhl'])


class AdminTest(unittest.TestCase):
    def test_tab_and_worker(self):
        html = read('admin', 'index.html')
        self.assertIn('data-view="defs"', html)
        for s in ("'/definitions/save'", "'/definitions/draft'", 'Draft all with AI', 'Discard and switch', "' / ' + DF.max"):
            self.assertIn(s, html)
        w = read('worker', 'rtyb-admin-worker.js')
        self.assertIn('case "/definitions/save":', w)
        self.assertIn('case "/definitions/draft":', w)
        self.assertIn('const DEF_SHORT_MAX = 200;', w)


class GlossaryTest(unittest.TestCase):
    def test_no_glossary_link_in_the_i_box(self):
        import build_site
        self.assertNotIn('glossary', build_site.SHELL_JS.lower())
        self.assertIn('data-term', read('assets', 'sport.js'))
        self.assertTrue(re.search(r'def glossary_doc\(', read('scripts', 'guides.py')))
        self.assertTrue(hasattr(guides, 'glossary_doc'))


if __name__ == '__main__':
    unittest.main()
