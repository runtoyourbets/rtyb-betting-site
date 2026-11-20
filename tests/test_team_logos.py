"""NHL logos (Nov 19): each SVG's viewBox is cropped to its artwork, one box
per team for light and dark, so a 22px badge shows the logo, not the empty
960x640 canvas NHL ships it on. fetch_team_logos.py crops on every run."""
import glob
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import fetch_team_logos as ftl  # noqa: E402

LOGOS = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logos')


def viewbox(path):
    return re.search(r'<svg\b[^>]*?\sviewBox="([^"]*)"', open(path, encoding='utf-8').read()).group(1)


class PathBoxTest(unittest.TestCase):
    def box(self, d):
        return tuple(round(v, 3) for v in ftl.artwork_box(f'<svg><path d="{d}"/></svg>'))

    def test_lines_relative_and_close(self):
        self.assertEqual(self.box('M10 10h20v5l-25 5zm0 0 1 1'), (5, 10, 30, 20))

    def test_curve_reaches_past_its_ends(self):
        # A cubic from (0,0) to (10,0) bowing up to y=-7.5.
        self.assertEqual(self.box('M0 0C0-10 10-10 10 0'), (0, -7.5, 10, 0))

    def test_arc_circle(self):
        b =ftl.artwork_box('<svg><path d="M0 50a50 50 0 1 0 100 0a50 50 0 1 0-100 0"/></svg>')
        for got, want in zip(b, (0, 0, 100, 100)):
            self.assertAlmostEqual(got, want, delta=0.1)


class CroppedLogosTest(unittest.TestCase):
    def test_every_nhl_logo_is_cropped_and_themes_match(self):
        darks = sorted(glob.glob(os.path.join(LOGOS, '*_dark.svg')))
        self.assertTrue(darks)
        for dark in darks:
            light = dark.replace('_dark.svg', '_light.svg')
            boxes = [ftl.artwork_box(open(p, encoding='utf-8').read()) for p in (dark, light)]
            with self.subTest(os.path.basename(dark)):
                self.assertNotEqual(viewbox(dark), '0 0 960 640')
                self.assertEqual(viewbox(dark), viewbox(light))
                self.assertEqual(viewbox(dark), ftl.cropped_viewbox(boxes))

    def test_crop_is_idempotent_and_touches_only_the_viewbox(self):
        tmp = tempfile.mkdtemp()
        try:
            paths = []
            for v in ('light', 'dark'):
                src = open(os.path.join(LOGOS, f'TOR_{v}.svg'), encoding='utf-8').read()
                p = os.path.join(tmp, f'TOR_{v}.svg')
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(re.sub(r'viewBox="[^"]*"', 'viewBox="0 0 960 640"', src, count=1))
                paths.append(p)
            self.assertEqual(ftl.crop_team(paths), 2)
            self.assertEqual(ftl.crop_team(paths), 0)
            for v, p in zip(('light', 'dark'), paths):
                self.assertEqual(open(p, encoding='utf-8').read(),
                                 open(os.path.join(LOGOS, f'TOR_{v}.svg'), encoding='utf-8').read())
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
