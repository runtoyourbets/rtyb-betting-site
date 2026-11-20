"""One dash, site-wide (Nov 19 night): plain hyphens only. No en dash, em
dash or minus sign (as a character, an HTML entity or a JSON escape) in any
generated page or in content/; the build's last step (build_site.plain_dashes)
swaps any that fetched text brings in."""
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_site  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
SKIP = {'.git', '.github', '.claude', 'scripts', 'tests', 'node_modules'}


def offenders(paths):
    out = []
    for path in paths:
        try:
            text = open(path, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        m = build_site.DASHES.search(text)
        if m:
            out.append(f'{os.path.relpath(path, ROOT)}: ...{text[max(0, m.start() - 30):m.end() + 30]!r}...')
    return out


class PlainHyphenTest(unittest.TestCase):
    def test_no_dashes_in_generated_pages(self):
        pages = []
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in SKIP]
            pages += [os.path.join(d, f) for f in files if f.endswith('.html')]
        self.assertTrue(pages)
        bad = offenders(pages)
        self.assertEqual(bad, [], f'{len(bad)} page(s) with an en/em dash or minus sign:\n' + '\n'.join(bad[:20]))

    def test_no_dashes_in_content(self):
        files = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(ROOT, 'content')) for f in fs]
        self.assertTrue(files)
        bad = offenders(files)
        self.assertEqual(bad, [], f'{len(bad)} content file(s) with an en/em dash or minus sign:\n' + '\n'.join(bad[:20]))

    def test_build_swaps_every_form(self):
        tmp = tempfile.mkdtemp()
        try:
            src = ('<p>12–3 — −160 &ndash; &mdash; &minus; &#8211;</p>', '{"n": "Game 1 \\u2013 Makeup"}')
            for name, text in zip(('a.html', 'b.json'), src):
                with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write(text)
            self.assertEqual(build_site.plain_dashes(tmp), 2)
            self.assertEqual(open(os.path.join(tmp, 'a.html'), encoding='utf-8').read(), '<p>12-3 - -160 - - - -</p>')
            self.assertEqual(open(os.path.join(tmp, 'b.json'), encoding='utf-8').read(), '{"n": "Game 1 - Makeup"}')
            self.assertEqual(build_site.plain_dashes(tmp), 0)
        finally:
            shutil.rmtree(tmp)


if __name__ == '__main__':
    unittest.main()
