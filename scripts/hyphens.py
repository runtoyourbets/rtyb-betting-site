"""
Plain hyphen only (CLAUDE.md): an en dash, em dash or minus sign -- as a
character, an HTML entity or a JSON escape -- becomes "-". Dashes come in
from fetched text (an MLB game note), the admin and Claude's Preview
drafts; none of them may stop the refresh, so they're converted, never
refused:

  - the admin converts every save (admin/index.html callWorker)
  - daily_content.py converts a draft as it writes it
  - the build's last step converts everything it wrote, content/ included
  - the refresh runs this file again right before it commits (after the
    drafts step), then checks the finished pages (tests/test_plain_hyphen.py)

  python3 scripts/hyphens.py      convert the site's text files in place
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHES = re.compile('|'.join(re.escape(x) for x in (
    '–', '—', '−', '&ndash;', '&mdash;', '&minus;', '&#8211;', '&#8212;', '&#8722;',
    '\\u2013', '\\u2014', '\\u2212')), re.I)
SKIP = {'.git', '.github', '.claude', 'scripts', 'tests', 'node_modules'}
EXT = ('.html', '.json', '.js', '.css', '.xml', '.txt', '.md')


def plain(text):
    """text with every dash form as "-"."""
    return DASHES.sub('-', text)


def plain_files(root=ROOT):
    """Convert every text file under root (but code and tests) in place;
    returns how many files changed."""
    changed = 0
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP]
        for f in files:
            if not f.endswith(EXT):
                continue
            path = os.path.join(d, f)
            try:
                with open(path, encoding='utf-8', newline='') as fh:
                    text = fh.read()
            except (UnicodeDecodeError, OSError):
                continue
            new = plain(text)
            if new != text:
                with open(path, 'w', encoding='utf-8', newline='') as fh:
                    fh.write(new)
                changed += 1
    return changed


if __name__ == '__main__':
    n = plain_files()
    print(f'plain hyphens: {n} file(s) had an en/em dash or minus sign' if n else 'plain hyphens: no dashes')
