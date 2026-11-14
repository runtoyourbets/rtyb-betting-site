"""The temporary footer switch (scripts/sports.py FOOTER): 'home-only' keeps
the bottom block (signup, 21+ line, about, Privacy / Terms) on the home page
alone; 'everywhere' brings it back on every page. The markup stays put."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import sports  # noqa: E402


class FooterSwitchTest(unittest.TestCase):
    def tearDown(self):
        sports.FOOTER = self.was

    def setUp(self):
        self.was = sports.FOOTER

    def test_home_only(self):
        sports.FOOTER = 'home-only'
        self.assertTrue(sports.footer_on(is_home=True))
        self.assertFalse(sports.footer_on())

    def test_everywhere(self):
        sports.FOOTER = 'everywhere'
        self.assertTrue(sports.footer_on())

    def test_markup_kept(self):
        with open(os.path.join(os.path.dirname(__file__), '..', 'template.html'), encoding='utf-8') as f:
            self.assertIn('<footer>', f.read())


if __name__ == '__main__':
    unittest.main()
