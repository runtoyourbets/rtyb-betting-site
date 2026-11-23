"""
The sportsbooks: one row per book from both odds sources (Unabated and The
Odds API), set in the admin's Books tab and saved to data_admin/books.json:

  {"books": [{"id": "1", "name": "DraftKings", "group": "Sportsbook",
              "show": true, "best": true, "link": ""}, ...]}

  order   the list order is the column order everywhere (Odds pages, the
          Next game card's book, the Slate)
  name    the display name
  group   Sportsbook / Offshore / Exchange
  show    false: the book's column and rows are gone from every page
  best    false: the book never sets or outlines the best price
  link    the book's affiliate URL: every one of its cells links there
          (Odds pages); empty: its Gambly links (if it has any), else no
          link; always empty for offshore books, which never link

A book the file doesn't list yet (a new source) shows with the defaults
below, after the listed ones. The build writes data_feed/books_status.json
for the tab: each book's source, coverage over the last 7 days per sport
and the last day it had a line.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data_admin', 'books.json')
STATUS = os.path.join(ROOT, 'data_feed', 'books_status.json')
GROUPS = ('Sportsbook', 'Offshore', 'Exchange')
OFFSHORE = {'bovada', 'betonlineag', 'mybookieag', 'lowvig', 'betus'}
# theScore CA shows, but RTYB is for US bettors: it never sets the best price
DEFAULT_NO_BEST = {'60'}


def read():
    try:
        with open(PATH, encoding='utf-8') as f:
            return json.load(f).get('books') or []
    except (OSError, ValueError, AttributeError):
        return []


def default_group(b):
    import sport_build
    return 'Exchange' if b in sport_build.EXCHANGES else 'Offshore' if b in OFFSHORE else 'Sportsbook'


class Settings:
    def __init__(self, rows=None):
        rows = read() if rows is None else rows
        self.rows = {str(r['id']): r for r in rows if isinstance(r, dict) and r.get('id') is not None}
        self.listed = list(self.rows)

    def row(self, b):
        r = self.rows.get(b) or {}
        group = r.get('group') if r.get('group') in GROUPS else default_group(b)
        return {'id': b, 'name': r.get('name'), 'group': group,
                'show': r.get('show', True) is not False,
                'best': r.get('best', b not in DEFAULT_NO_BEST) is not False,
                'link': '' if group == 'Offshore' else url(r.get('link'))}

    def shown(self, b):
        return self.row(b)['show']

    def counts(self, b):
        """Can set (and be outlined as) the best price."""
        r = self.row(b)
        return r['show'] and r['best']

    def linked(self, b):
        return self.row(b)['group'] != 'Offshore'

    def url(self, b):
        """The saved affiliate URL, or ''."""
        return self.row(b)['link']

    def name(self, b, fallback):
        return self.row(b)['name'] or fallback

    def order(self, ids, fallback):
        """The listed books in the file's order, then the rest by `fallback` (a sorter)."""
        ids = [b for b in ids if self.shown(b)]
        first = [b for b in self.listed if b in ids]
        return first + fallback([b for b in ids if b not in self.rows])

    def filter(self, books):
        """{seg: {market: {book: row}}} without hidden books, offshore books
        without links, and a book with an affiliate URL linking every cell
        there."""
        out = {}
        for seg, mk in (books or {}).items():
            for m, by in (mk or {}).items():
                keep = {}
                for b, row in (by or {}).items():
                    if not self.shown(b):
                        continue
                    keep[b] = (relinked(row, self.url(b)) if self.url(b) else row) if self.linked(b) else unlinked(row)
                out.setdefault(seg, {})[m] = keep
        return out


def url(v):
    """An https:// URL (the admin checks it too), else ''."""
    v = v.strip() if isinstance(v, str) else ''
    return v if v.startswith('https://') and len(v) <= 500 and not any(c.isspace() for c in v) else ''


def relinked(row, link):
    """Every priced side of a row links to `link`."""
    if isinstance(row, dict):
        out = {k: relinked(v, link) for k, v in row.items() if k != 'link'}
        if 'price' in row:
            out['link'] = link
        return out
    return row


def unlinked(row):
    if isinstance(row, dict):
        return {k: unlinked(v) for k, v in row.items() if k != 'link'}
    return row


_settings = None


def settings():
    """The saved settings, read once per build."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset():
    global _settings
    _settings = None


# ---------------------------------------------------------- coverage status

_seen = {}


def note(sport, day, games):
    """One Odds page day: per book, how many games it had a line for."""
    for g in games:
        ids = {b for mk in (g.get('books') or {}).values() for by in mk.values() for b in (by or {})}
        if not ids:
            continue
        s = _seen.setdefault(sport, {})
        tot = s.setdefault('_games', {})
        tot[day] = tot.get(day, 0) + 1
        for b in ids:
            d = s.setdefault(b, {})
            d[day] = d.get(day, 0) + 1


def write_status(today, names, oddsapi_ids, unabated_ids):
    """data_feed/books_status.json: {updated, books: {id: {name, source,
    group, coverage: {sport: % of the last 7 days' games}, last_seen}}}."""
    from datetime import date, timedelta
    start = (date.fromisoformat(today) - timedelta(days=6)).isoformat()
    cfg = settings()
    out = {}
    ids = set(cfg.rows)
    for s in _seen.values():
        ids.update(b for b in s if b != '_games')
    for b in ids:
        src = [n for n, have in (('Unabated', b in unabated_ids), ('The Odds API', b in oddsapi_ids)) if have]
        cov, last = {}, None
        for sport, s in _seen.items():
            days = s.get(b) or {}
            seen = [d for d in days if d <= today]
            if seen:
                last = max([last] + seen) if last else max(seen)
            total = sum(n for d, n in s['_games'].items() if start <= d <= today)
            if total:
                cov[sport] = round(100 * sum(n for d, n in days.items() if start <= d <= today) / total)
        row = cfg.row(b)
        out[b] = {'name': names.get(b, b), 'source': ' + '.join(src) or 'Unabated', 'group': row['group'],
                  'coverage': cov, 'last_seen': last}
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS, 'w', encoding='utf-8') as f:
        json.dump({'updated': today, 'books': out}, f, indent=1, sort_keys=True)
        f.write('\n')
    return out
