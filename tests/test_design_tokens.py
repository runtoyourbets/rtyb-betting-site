"""Design tokens (CLAUDE.md "Design tokens"): type, colors and spacing live in
the one shared stylesheet (template.html's <style>, written out as
assets/site.css). Nothing else (page scripts, the Python that writes pages,
the template's own markup and scripts, any other stylesheet) may set
font-family, font-size, font-weight or a hard-coded color. Team badges are
the one exception: they stand in for a missing logo, so their color comes
from the team's data and their letter size from the badge size."""
import glob
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONT = re.compile(r'font-(?:family|size|weight)\s*:|(?<![-\w])font\s*:|\.style\.font(?:Family|Size|Weight)\b')
COLOR = re.compile(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b|\brgba?\(|\bhsla?\(')
STYLE_ATTR = re.compile(r'style=\\?"([^"\\]*(?:\\.[^"\\]*)*)\\?"|style=\'([^\']*)\'', re.S)
STYLE_PROP = re.compile(r'\.style\.(?:color|background(?:Color)?|borderColor|font\w*)\s*=\s*([^;\n]+)')
BADGE = ('team-badge', 'team-logo-fallback')
TOKENS = ('--ff-display', '--ff-body', '--fs-title', '--fs-section', '--fs-team', '--fs-body', '--fs-num', '--fs-price',
          '--fs-label', '--cell', '--best-bg', '--good-dim', '--push-dim', '--cell-gap', '--cell-min-h', '--card-pad')


def near_badge(lines, i):
    return any(b in l for l in lines[max(0, i - 4):i + 4] for b in BADGE)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def offenders(path, text):
    lines = text.split('\n')
    out = []
    for m in STYLE_ATTR.finditer(text):
        css = m.group(1) or m.group(2) or ''
        i = text.count('\n', 0, m.start())
        if (FONT.search(css) or COLOR.search(css)) and not near_badge(lines, i):
            out.append(f'{path}:{i + 1}: {css.strip()[:80]}')
    for m in STYLE_PROP.finditer(text):
        i = text.count('\n', 0, m.start())
        if (FONT.search(m.group(0)) or COLOR.search(m.group(1))) and not near_badge(lines, i):
            out.append(f'{path}:{i + 1}: {m.group(0).strip()[:80]}')
    return out


class SharedStylesheetOnlyTest(unittest.TestCase):
    def test_no_type_or_color_outside_the_shared_stylesheet(self):
        bad = []
        files = (glob.glob(os.path.join(ROOT, 'assets', '*.js')) + glob.glob(os.path.join(ROOT, 'assets', 'splits', '*.js')) +
                 glob.glob(os.path.join(ROOT, 'scripts', '*.py')))
        for f in files:
            bad += offenders(os.path.relpath(f, ROOT), read(f))
        tpl = read(os.path.join(ROOT, 'template.html'))
        a, b = tpl.index('<style>'), tpl.index('</style>')
        bad += offenders('template.html', tpl[:a] + '\n' * tpl.count('\n', a, b) + tpl[b:])
        # no other stylesheet sets type or colors (assets/home.css is an empty stub)
        for css in glob.glob(os.path.join(ROOT, 'assets', '*.css')):
            if os.path.basename(css) == 'site.css':
                continue
            body = re.sub(r'/\*.*?\*/', '', read(css), flags=re.S)
            if FONT.search(body) or COLOR.search(body):
                bad.append(os.path.relpath(css, ROOT))
        self.assertEqual(bad, [], 'type or colors set outside the shared stylesheet')

    def test_shared_stylesheet_uses_only_the_six_type_styles(self):
        tpl = read(os.path.join(ROOT, 'template.html'))
        css = re.sub(r'/\*.*?\*/', '', tpl[tpl.index('<style>'):tpl.index('</style>')], flags=re.S)
        for t in TOKENS:
            self.assertIn(t + ':', css, t)
        self.assertNotIn('Mono', css)
        # every font-family / font-size / font-weight is a token (or inherit);
        # the logo's 800 is its own lettering (an SVG drawing), not a style
        loose = [d.strip() for d in re.findall(r'(?<![-\w])font-(?:family|size|weight)\s*:\s*([^;}]+)', css)
                 if not d.strip().startswith(('var(--', 'inherit')) and d.strip() != '800']
        self.assertEqual(loose, [])
        self.assertEqual(re.findall(r'(?<![-\w])font\s*:(?!\s*inherit)[^;}]+', css), [])


if __name__ == '__main__':
    unittest.main()
