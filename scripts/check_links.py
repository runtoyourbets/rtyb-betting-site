"""
Link check, run by the refresh job after the build and before the commit:
opens every built page, follows every internal <a href> and fails (exit 1)
when one points to a page that wasn't built, printing each broken link and
the page it's on. External links, mail/phone links and #anchors are skipped.

Links that sport.js draws in the browser aren't in the HTML (and links
inside <script> blocks are skipped), so they aren't checked here;
everything the build writes into a page is.

With --staged (how the refresh job runs it, after `git add`), a page also
has to be in the commit, not just on disk: a page the build wrote but the
job didn't add is broken on the live site, so it fails the check too.

    python3 scripts/check_links.py [--staged]
"""
import html
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit, unquote

import seo

ROOT = seo.ROOT
SCRIPT = re.compile(r'<script\b.*?</script>', re.I | re.S)
HREF = re.compile(r'<a\b[^>]*?\bhref\s*=\s*(["\'])(.*?)\1', re.I | re.S)
SKIP_SCHEMES = ('mailto:', 'tel:', 'javascript:', 'data:', 'sms:')


def pages():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in seo.SKIP_DIRS and not x.startswith('.')]
        for f in files:
            if f.endswith('.html'):
                yield os.path.join(d, f)


def site_prefixes():
    """Absolute URLs (and root paths) that mean this site."""
    out = []
    for base in {seo.site_url(), seo.PAGES_URL}:
        u = urlsplit(base)
        out.append((u.netloc, u.path))
    return out


def target(page, href, prefixes):
    """The file path the link needs on disk, or None when it isn't internal."""
    href = html.unescape(href).strip()
    if not href or href.startswith('#') or href.lower().startswith(SKIP_SCHEMES) or '__' in href:
        return None
    u = urlsplit(href)
    path = unquote(u.path)
    if u.scheme or u.netloc:
        for host, base in prefixes:
            if u.netloc == host and path.startswith(base):
                rel = path[len(base):]
                break
        else:
            return None                                  # another site
        full = os.path.join(ROOT, rel)
    elif path.startswith('/'):
        for _, base in prefixes:
            if path.startswith(base):
                path = path[len(base):]
                break
        else:
            path = path.lstrip('/')
        full = os.path.join(ROOT, path)
    elif not path:
        return None                                      # ?query on the same page
    else:
        full = os.path.join(os.path.dirname(page), path)
    full = os.path.normpath(full)
    if path.endswith('/') or os.path.isdir(full):
        return os.path.join(full, 'index.html')
    return full


def staged_files():
    """Every path in the index (what the commit will hold)."""
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    return {os.path.normpath(os.path.join(ROOT, p)) for p in out.decode().split('\0') if p}


def broken(staged=False):
    prefixes = site_prefixes()
    have = staged_files() if staged else None
    out = []
    for page in pages():
        if have is not None and os.path.normpath(page) not in have:
            continue                                     # not published, so not linked from the live site
        with open(page, encoding='utf-8', errors='replace') as f:
            text = SCRIPT.sub('', f.read())
        for m in HREF.finditer(text):
            t = target(page, m.group(2), prefixes)
            if t and (not os.path.exists(t) or (have is not None and t not in have)):
                out.append((os.path.relpath(page, ROOT), m.group(2)))
    return sorted(set(out))


def main():
    bad = broken(staged='--staged' in sys.argv)
    n = sum(1 for _ in pages())
    if bad:
        print(f'Link check FAILED: {len(bad)} broken internal link(s) across {n} pages')
        for page, href in bad:
            print(f'  {page}: {href}')
        return 1
    print(f'Link check passed: {n} pages, every internal link resolves')
    return 0


if __name__ == '__main__':
    sys.exit(main())
