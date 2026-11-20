"""One dash, site-wide (Nov 19 night): plain hyphens only. A stray en dash,
em dash or minus sign (character, HTML entity or JSON escape) is converted,
never a reason to stop the refresh: the admin converts on save, the drafter
as it writes, the build in everything it writes (content/ included). The
check is on the finished pages: the refresh runs this file again after
scripts/hyphens.py, right before it commits."""
import glob
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import hyphens  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')


def offenders(paths):
    out = []
    for path in paths:
        try:
            text = open(path, encoding='utf-8').read()
        except (UnicodeDecodeError, OSError):
            continue
        m = hyphens.DASHES.search(text)
        if m:
            out.append(f'{os.path.relpath(path, ROOT)}: ...{text[max(0, m.start() - 30):m.end() + 30]!r}...')
    return out


class PlainHyphenTest(unittest.TestCase):
    def test_no_dashes_in_finished_pages(self):
        pages = []
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in hyphens.SKIP]
            pages += [os.path.join(d, f) for f in files if f.endswith('.html')]
        self.assertTrue(pages)
        bad = offenders(pages)
        self.assertEqual(bad, [], f'{len(bad)} page(s) with an en/em dash or minus sign:\n' + '\n'.join(bad[:20]))

    def test_no_dashes_in_seo_text(self):
        # content/seo: the SEO page text (scripts/seo_text.py)
        paths = glob.glob(os.path.join(ROOT, 'content', 'seo', '*.md'))
        self.assertTrue(paths)
        self.assertEqual(offenders(paths), [])

    def test_build_converts_every_form_content_included(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, 'content', 'drafts'))
            files = {'a.html': ('<p>12–3 — −160 &ndash; &mdash; &minus; &#8211;</p>', '<p>12-3 - -160 - - - -</p>'),
                     'b.json': ('{"n": "Game 1 \\u2013 Makeup"}', '{"n": "Game 1 - Makeup"}'),
                     'content/drafts/nhl-preview.md': ('The Wild — again — at home.', 'The Wild - again - at home.')}
            for name, (src, _) in files.items():
                with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
                    f.write(src)
            self.assertEqual(hyphens.plain_files(tmp), 3)
            for name, (_, want) in files.items():
                self.assertEqual(open(os.path.join(tmp, name), encoding='utf-8').read(), want)
            self.assertEqual(hyphens.plain_files(tmp), 0)
        finally:
            shutil.rmtree(tmp)

    def test_build_and_drafter_convert(self):
        self.assertIn('hyphens.plain_files()', open(os.path.join(ROOT, 'scripts', 'build_site.py'), encoding='utf-8').read())
        drafter = open(os.path.join(ROOT, 'scripts', 'daily_content.py'), encoding='utf-8').read()
        self.assertEqual(drafter.count('hyphens.plain('), 2)

    def test_admin_converts_every_save(self):
        # every admin write goes through callWorker, which converts the body's strings
        admin = open(os.path.join(ROOT, 'admin', 'index.html'), encoding='utf-8').read()
        self.assertEqual(admin.count('fetch(WORKER_URL + path'), 1)
        self.assertRegex(admin, r'body: JSON\.stringify\(plainDashes\(body\)\)')
        self.assertIn('String.fromCharCode(8211, 8212, 8722)', admin)

    def test_refresh_converts_then_checks_before_commit(self):
        wf = open(os.path.join(ROOT, '.github', 'workflows', 'refresh.yml'), encoding='utf-8').read()
        step = wf.index('python3 scripts/hyphens.py')
        self.assertLess(wf.index('scripts/daily_content.py'), step)
        self.assertLess(step, wf.index('python3 -m unittest tests.test_plain_hyphen'))
        self.assertLess(wf.index('python3 -m unittest tests.test_plain_hyphen'), wf.index('git commit -m "Auto-refresh'))

    def test_writing_guide_says_so(self):
        guide = open(os.path.join(ROOT, 'content', 'preview_writing_guide.md'), encoding='utf-8').read()
        self.assertIn('Plain hyphens only; never en or em dashes.', guide)


if __name__ == '__main__':
    unittest.main()
