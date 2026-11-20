"""
Definitions: every word the site explains in an "i" box, the Splits
glossary or the Betting Glossary, edited in the admin's Definitions tab.

content/definitions.json (the admin saves it through the Worker):

  {"config": {...the tooltip settings that aren't definitions...},
   "entries": {id: {name, category, sports: [keys], short, long, status,
                    show_last (league trends only), edited (YYYY-MM-DD),
                    + per category: group (league trends), label_of (BTTS
                    label wording)}}}

  ids: label:{key}[_btts] · trend:{angle} · team:{market}_{kind} ·
  split:{row id} · edge:{name} · term:{anchor} · feature:{name}
  status: needs (no text yet) · draft · live. Only Live text reaches the
  site; anything else shows its title (and a trend's comparison line).

The build (write_meta) adds assets/definitions_meta.json for the admin: each
entry's "How it's calculated" and "Where it appears", plus every trend,
label and split the code knows about, so a new one shows up in the admin as
Needs definition; and assets/definitions.json, the Live text the pages read
in the browser (the Splits glossary).

tooltips() hands the older readers (trends.py, hub.py, front.py) the shape
content/trend_tooltips.json had, with Live text only.
"""
import json
import os
import re
from datetime import date

import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, 'content', 'definitions.json')
META = os.path.join(ROOT, 'assets', 'definitions_meta.json')
PUBLIC = os.path.join(ROOT, 'assets', 'definitions.json')

CATEGORIES = [
    ('labels', 'Matchup labels'),
    ('league', 'League trends'),
    ('team', 'Team trends & streaks'),
    ('splits', 'Splits & situations'),
    ('edges', 'Edges'),
    ('terms', 'Markets & terms'),
    ('features', 'Site features'),
]
SHORT_MAX = 200
SPLIT_FILES = {'nhl': ['nhl'], 'basketball': ['nba', 'wnba'], 'ncaab': ['ncaab'], 'nfl': ['nfl'], 'ncaaf': ['ncaaf'], 'mlb': ['mlb']}
ALL = [sp['key'] for sp in sports.SPORTS]


def load():
    try:
        with open(FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'config': {}, 'entries': {}}


def live(e):
    return (e or {}).get('status') == 'live'


def text(e):
    """The entry's short definition if it's Live, else ''."""
    return (e.get('short') or '') if live(e) else ''


def tooltips(doc=None):
    """The shape content/trend_tooltips.json had (Live text only)."""
    doc = doc or load()
    E, cfg = doc.get('entries') or {}, doc.get('config') or {}
    out = {k: cfg[k] for k in ('direction', 'last_time_format', 'record_line', 'streaks') if k in cfg}
    out['side_angles'], out['game_angles'], out['team_trends'] = {}, {}, {}
    labels = {'lean_rule': cfg.get('lean_rule', '')}
    for i, e in E.items():
        kind, _, key = i.partition(':')
        if kind == 'trend':
            out[e.get('group') or 'side_angles'][key] = {'title': e['name'], 'meaning': text(e), 'show_last': bool(e.get('show_last'))}
        elif kind == 'team':
            out['team_trends'][key] = {'title': e['name'], 'meaning': text(e)}
        elif kind == 'label' and not key.endswith('_btts'):
            b = E.get(i + '_btts') or {}
            labels[key] = {'label': e['name'], 'tooltip': text(e), 'tooltip_btts': text(b)}
    out['matchup_labels'] = labels
    return out


# ---------------------------------------------------------------- the code's list
def split_rows():
    """{row id: {name, def, group, sports}} from assets/splits/*.js."""
    out = {}
    row_re = re.compile(r"\{ id: '([a-z0-9]+)', label: (?:'((?:[^'\\]|\\.)*)'|[a-zA-Z(]).*?group: '([a-z0-9]+)'(.*?)(?:test:|\}\s*,?\s*$)", re.S | re.M)
    short_re = re.compile(r"short: '((?:[^'\\]|\\.)*)'")
    def_re = re.compile(r"def: '((?:[^'\\]|\\.)*)'")
    for name, keys in SPLIT_FILES.items():
        path = os.path.join(ROOT, 'assets', 'splits', f'{name}.js')
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            js = f.read()
        hidden = set(re.findall(r"\{ id: '([a-z0-9]+)', label: '[^']*', hidden: true", js))
        for m in row_re.finditer(js):
            rid, label, group, rest = m.group(1), m.group(2), m.group(3), m.group(4)
            if group in hidden:
                continue
            s, d = short_re.search(m.group(0)), def_re.search(m.group(0))
            x = out.setdefault(rid, {'name': (label or (s.group(1) if s else rid)).replace("\\'", "'"),
                                     'def': d.group(1).replace("\\'", "'") if d else '', 'group': group, 'sports': []})
            x['sports'] += [k for k in keys if k not in x['sports']]
    return out


def known():
    """Every entry the code has: {id: {name, category, sports, ...}}."""
    import trends
    T = load()
    out = {}
    for key in ('tug_of_war', 'fireworks', 'lockdown', 'mismatch', 'heavyweights'):
        old = (T.get('entries') or {}).get('label:' + key) or {}
        out['label:' + key] = {'name': old.get('name') or key.replace('_', ' ').title(), 'category': 'labels', 'sports': ALL}
        if key in ('tug_of_war', 'fireworks', 'lockdown'):
            out['label:' + key + '_btts'] = {'name': (old.get('name') or key) + ' (BTTS)', 'category': 'labels', 'sports': ['nhl']}
    for sp in sports.SPORTS:
        for grp, fn in (('side_angles', trends.side_angles), ('game_angles', trends.game_angles)):
            for aid, _ in fn(sp):
                x = out.setdefault('trend:' + aid, {'name': aid, 'category': 'league', 'sports': [], 'group': grp})
                if sp['key'] not in x['sports']:
                    x['sports'].append(sp['key'])
    for m, kinds in (('ml', 'WLT'), ('ats', 'WL'), ('total', 'OU'), ('btts', 'YN'), ('rfi', 'YN')):
        for k in kinds:
            sp_keys = ['nhl'] if m == 'btts' or (m == 'ml' and k == 'T') else ['mlb'] if m == 'rfi' else ALL
            out[f'team:{m}_{k}'] = {'name': f'{m}_{k}', 'category': 'team', 'sports': sp_keys}
    for rid, r in split_rows().items():
        out['split:' + rid] = {'name': r['name'], 'category': 'splits', 'sports': r['sports'], 'def': r['def'], 'group': r['group']}
    return out


# ---------------------------------------------------------------- calc / where
SEG_WORD = 'the opening segment (1st period, 1st quarter or half, 1st inning or first five)'


def calc(i, e, extra):
    kind = i.split(':')[0]
    if kind == 'label':
        return ('From both teams’ leans in ' + SEG_WORD + ': a lean is a result in 60%+ of a team’s games, 5+ played. '
                'Totals and BTTS: both Over (Fireworks), both Under (Lockdown), one each (Tug of war). '
                'Moneyline: one wins / one loses (Mismatch), both win (Heavyweights).')
    if kind == 'trend':
        return ('Every graded game this season where the angle fit, before the slate’s date. The card shows when the bet’s record '
                'beats the league rate for the same bet by 5+ points over 20+ decisions and made money at the closing prices (1 unit a bet).')
    if kind == 'team':
        return ('Per team, its games this season in ' + SEG_WORD + '. A lean: this result in 60%+ of 5+ games (pushes left out, '
                'ties count on the moneyline). A streak: 3+ straight from the most recent game; a tie or push ends it.')
    if kind == 'split':
        return ('Situational Results: every team-game this season that fits the row (' + (extra.get('def') or 'see the row') + '). '
                'Records leave ties and pushes out of the %; units at the closing price. Rows under 5 games stay hidden.')
    if kind == 'edge':
        return 'Stats › Edges: finished games grouped by the score at the break, then how the full game ended.'
    return ''


def where(i, e):
    kind, key = i.split(':', 1)
    sp = e.get('sports') or []
    pages = ', '.join(s.upper() for s in sp) if sp and len(sp) < len(ALL) else 'every sport'
    return {
        'label': [f'Trends › Matchup Trends ({pages})', 'Sport hubs › Matchup of the Day', 'Home › Matchup of the Day'],
        'trend': [f'Trends › League Trends ({pages})', 'Sport hubs and Home › Hottest Trends', 'Previews'],
        'team': [f'Trends › Matchup Trends and Streak Trends ({pages})', 'Team pages › Streaks'],
        'split': [f'Stats › Splits ({pages})', 'Team pages › Situational Results', 'How to read › Glossary'],
        'edge': [f'Stats › Edges ({pages})'],
        'term': ['Betting Guides › Glossary', '"i" boxes on market terms (Units, BTTS, NRFI...)'],
        'feature': [e.get('where') or 'Site pages'],
    }.get(kind, [])


def write_meta():
    """assets/definitions_meta.json (admin) and assets/definitions.json (pages)."""
    doc = load()
    E = doc.get('entries') or {}
    K = known()
    meta = {}
    for i in sorted(set(E) | set(K)):
        e = dict(K.get(i) or {}, **{k: v for k, v in (E.get(i) or {}).items() if v not in (None, '')})
        meta[i] = {'calc': calc(i, e, K.get(i) or {}), 'where': where(i, e), 'sports': (K.get(i) or {}).get('sports') or e.get('sports') or ALL}
        if i not in E:   # the build found it; the admin lists it as Needs definition
            meta[i]['new'] = {'name': e.get('name') or i, 'category': e.get('category') or 'features'}
    os.makedirs(os.path.dirname(META), exist_ok=True)
    with open(META, 'w', encoding='utf-8') as f:
        json.dump({'categories': CATEGORIES, 'sports': [[sp['key'], sp['label']] for sp in sports.SPORTS], 'shortMax': SHORT_MAX, 'entries': meta}, f, ensure_ascii=False, separators=(',', ':'))
    pub = {'live': {i: {'name': e.get('name'), 'short': e.get('short')} for i, e in E.items() if live(e)},
           'known': sorted(E)}
    with open(PUBLIC, 'w', encoding='utf-8') as f:
        json.dump(pub, f, ensure_ascii=False, separators=(',', ':'))


def glossary_terms(doc=None):
    """Live Markets & terms entries, A to Z: [(anchor, name, short, long)]."""
    E = (doc or load()).get('entries') or {}
    out = [(i.split(':', 1)[1], e['name'], e.get('short') or '', e.get('long') or '') for i, e in E.items()
           if i.startswith('term:') and live(e)]
    return sorted(out, key=lambda x: x[1].lower())


def today():
    return date.today().isoformat()
