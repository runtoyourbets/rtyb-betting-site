"""
Sport registry: the one place every sport RTYB covers is defined.

The build (build_site.py) generates each sport's pages from this list:
/{slug}/matchups, /{slug}/stats, /{slug}/trends, /{slug}/teams and
/{slug}/teams/{team-slug}, plus the sport selector in the top nav. Adding a
sport means adding an entry here, not copying pages.

Field reference
  key            short id used in code and data files ("nfl")
  label          what people see in headers, nav and titles ("NCAAF")
  slug           URL folder ("college-football" -> /college-football/)
  sport_type     "period" (NHL), "spread" (football / basketball), "baseball" (MLB)
  segments       the bet windows tracked, in display order; each has a key,
                 a label, a short tag for chips and cards, and its markets
                 (a segment without 'ML' shows no moneyline / SU anywhere:
                 game cards, stats, teams, trends, picks, home, admin)
  season_start   month (1-12) the season starts, for "Soon" / return-month labels
  season_end     month (1-12) the last games are played (playoffs and bowls
                 included); between the two the sport is in season
  sections       URL folder for each section (the same for every sport)
  schedule       "day" (default) or "week": football's Matchups page and Admin
                 go week by week (ESPN's weeks: Week 1.., Wild Card, Bowls)
  launched       set from content/site_settings.json (below): False only
                 when the sport's switch is "off"

Site settings (content/site_settings.json, edited in admin's Site settings
tab): the main menu, the sports' order, menu labels and switches ("on" =
shown all year, off-season sports showing last season; "in_season" = shown
between season_start and season_end; "off" = hidden: its data is still
fetched, graded and built and its pages load by URL, noindexed, but nothing
links to them), each sport's page links, the phone bottom bar, and the
PREVIEW_LIVE / PICKS_LIVE / FOOTER switches. Every menu reads from here.
"""
import json
import os
import re

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'content', 'site_settings.json')
DEFAULT_SETTINGS = {
    'main_menu': [{'key': k, 'label': k.title()} for k in ('sports', 'matchups', 'odds', 'trends', 'stats', 'picks')],
    'sports': [],
    'sport_pages': [{'key': 'picks', 'label': 'Picks'}, {'key': 'games', 'label': 'Matchups'}, {'key': 'odds', 'label': 'Odds'},
                    {'key': 'trends', 'label': 'Trends'}, {'key': 'stats', 'label': 'Stats'}, {'key': 'teams', 'label': 'Teams'}],
    'bottom_bar': [{'key': k, 'label': k.title()} for k in ('matchups', 'odds', 'trends', 'stats')],
    'switches': {'PREVIEW_LIVE': True, 'PICKS_LIVE': False, 'FOOTER': 'home-only', 'ADS_ON': False},
    # Preview drafting (admin Site settings): the earliest time the refresh
    # job drafts (ET), the weekly sports' draft day, and each sport's mode
    # (missing: NFL and College Football weekly, the rest daily)
    'drafts': {'DRAFT_TIME_ET': '08:00', 'WEEKLY_DRAFT_DAY': 'Tuesday', 'PREVIEW_MODE': {}},
    # the hubs' off-season dates the schedule doesn't have (admin Site
    # settings), per sport: OPENING_DAY (YYYY-MM-DD, or '') and up to two
    # MILESTONES [{label, date}] (scripts/seasons.py)
    'seasons': {},
}


def load_settings(path=SETTINGS_PATH):
    """content/site_settings.json over the defaults (a missing or broken
    file falls back to them, key by key)."""
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(path, encoding='utf-8') as f:
            got = json.load(f)
    except (OSError, ValueError):
        got = {}
    for k, v in (got or {}).items():
        if k == 'switches' and isinstance(v, dict):
            v = dict(v)
            if 'ON_TAP_LIVE' in v:   # the old name (On Tap became Preview, 2026-11-18)
                v.setdefault('PREVIEW_LIVE', v['ON_TAP_LIVE'])
                del v['ON_TAP_LIVE']
            out['switches'].update(v)
        elif k == 'drafts' and isinstance(v, dict):
            out['drafts'].update({x: y for x, y in v.items() if x in out['drafts']})
        elif k == 'seasons' and isinstance(v, dict):
            out['seasons'] = v
        elif k in out and isinstance(v, list) and v:
            out[k] = v
    return out


SETTINGS = load_settings()
SWITCHES = SETTINGS['switches']
# the every-sport pages behind the main menu: key -> folder
# (while PICKS_LIVE is False, Picks links open the Preview pages)
PICKS_LIVE = bool(SWITCHES.get('PICKS_LIVE'))
INDEX_FOLDERS = {'matchups': 'matchups/', 'odds': 'odds/', 'trends': 'trends/', 'stats': 'stats/',
                 'picks': 'picks/' if PICKS_LIVE else 'preview/', 'preview': 'preview/'}
MAIN_MENU = [(m['key'], m.get('label') or m['key'].title()) for m in SETTINGS['main_menu']
             if m.get('key') == 'sports' or m.get('key') in INDEX_FOLDERS]
BOTTOM_BAR = [(m['key'], m.get('label') or m['key'].title()) for m in SETTINGS['bottom_bar'] if m.get('key') in INDEX_FOLDERS][:4]

SPREAD_MARKETS = ['ATS', 'ML', 'Total']
NO_ML_MARKETS = ['ATS', 'Total']

# The bottom block (newsletter signup, 21+ line, about and commission lines,
# Privacy · Terms · email) on every page's footer. 'home-only' keeps it on
# the home page alone (until launch); 'everywhere' brings it back on every page.
FOOTER = SWITCHES.get('FOOTER') or 'home-only'


def footer_on(is_home=False):
    return FOOTER == 'everywhere' or is_home


# Picks (/picks/ and /{sport}/picks/). Picks links show in every menu (gold)
# either way. False: they open the Preview pages (/preview/, /{sport}/preview/)
# and the Picks pages forward there, out of the sitemap; True swaps in the
# real Picks pages. (PICKS_LIVE is read above, with INDEX_FOLDERS.)

# Preview (/preview/, /{sport}/preview/; was On Tap). True: drafted from
# 8 AM ET, shown as soon as it's published (the home hero, each hub's
# Preview section). False: no drafts (no API calls) and Yesterday's Best is
# the hero.
PREVIEW_LIVE = bool(SWITCHES.get('PREVIEW_LIVE', True))

# Ad slots (admin Site settings): False (the default) renders nothing; True
# writes the empty, invisible slots into the Preview pages (preview.ad_slot)
ADS_ON = bool(SWITCHES.get('ADS_ON', False))

# Drafting (content/site_settings.json "drafts"): the refresh job drafts at
# or after DRAFT_TIME_ET; weekly sports on WEEKLY_DRAFT_DAY.
DRAFTS = SETTINGS['drafts']
SEASON_DATES = SETTINGS['seasons']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def draft_time():
    """(hour, minute) of DRAFT_TIME_ET; a bad value falls back to 8:00."""
    m = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d)', str(DRAFTS.get('DRAFT_TIME_ET') or ''))
    return (int(m.group(1)), int(m.group(2))) if m else (8, 0)


def weekly_draft_day():
    """WEEKLY_DRAFT_DAY as a weekday number (Monday 0); default Tuesday."""
    d = str(DRAFTS.get('WEEKLY_DRAFT_DAY') or '').title()
    return DAYS.index(d) if d in DAYS else 1


def preview_mode(key):
    """'weekly' or 'daily'. Weekly needs the schedule's weeks (ESPN), so
    only NFL and College Football can be weekly (their default)."""
    sp = BY_KEY.get(key) or {}
    if sp.get('schedule') != 'week':
        return 'daily'
    return 'daily' if (DRAFTS.get('PREVIEW_MODE') or {}).get(key) == 'daily' else 'weekly'


def preview_weekly(key):
    return preview_mode(key) == 'weekly'


# in nav order (menus, pills): NHL, NBA, NCAAB, NFL, NCAAF, then WNBA and MLB
SPORTS = [
    {
        'key': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'sport_type': 'period',
        'launched': True,
        'segments': [
            {'key': '1p', 'label': '1st Period', 'tag': '1P', 'markets': ['ML', 'O/U 1.5', 'BTTS']},
        ],
        'season_start': 10, 'season_end': 6,
        'sections': {'games': 'matchups', 'stats': 'stats', 'trends': 'trends', 'odds': 'odds', 'teams': 'teams'},
    },
    {
        'key': 'nba', 'label': 'NBA', 'slug': 'nba', 'sport_type': 'spread',
        'launched': True,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 10, 'season_end': 6,
    },
    {
        'key': 'ncaab', 'label': 'NCAAB', 'slug': 'college-basketball', 'sport_type': 'spread',
        'launched': True,
        'segments': [
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 11, 'season_end': 4,
    },
    {
        'key': 'nfl', 'label': 'NFL', 'slug': 'nfl', 'sport_type': 'spread', 'schedule': 'week',
        'launched': True,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 9, 'season_end': 2,
    },
    {
        'key': 'ncaaf', 'label': 'NCAAF', 'slug': 'college-football', 'sport_type': 'spread', 'schedule': 'week',
        'launched': True,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 8, 'season_end': 1,
    },
    {
        'key': 'wnba', 'label': 'WNBA', 'slug': 'wnba', 'sport_type': 'spread',
        'launched': True,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 5, 'season_end': 10,
    },
    {
        'key': 'mlb', 'label': 'MLB', 'slug': 'mlb', 'sport_type': 'baseball',
        'launched': True,
        'segments': [
            {'key': '1i', 'label': '1st Inning', 'tag': 'NRFI', 'markets': ['NRFI/YRFI']},
            {'key': 'f5', 'label': 'First Five Innings', 'tag': 'F5', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 3, 'season_end': 10,
    },
]

# 'odds' is the book-by-book comparison page (Unabated feed). The 'games'
# section is the Matchups page (/{slug}/matchups/; /{slug}/games/ forwards).
DEFAULT_SECTIONS = {'games': 'matchups', 'stats': 'stats', 'trends': 'trends', 'odds': 'odds', 'teams': 'teams'}
SECTION_LABELS = {'games': 'Matchups', 'stats': 'Stats', 'trends': 'Trends', 'odds': 'Odds', 'teams': 'Teams'}
OLD_SECTION_DIRS = {'games': 'games'}   # moved sections: old folder -> a forwarding stub
# Every sport's pages, in the order they're listed everywhere (menus, pills,
# the sport bar): Picks · Matchups · Odds · Trends · Stats · Teams. Picks
# only while PICKS_LIVE.
SITE_SECTIONS = ['picks', 'games', 'odds', 'trends', 'stats', 'teams']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

for _s in SPORTS:
    _s.setdefault('sections', dict(DEFAULT_SECTIONS))
    _s.setdefault('schedule', 'day')

# order, menu labels and switches from the settings file; sports it doesn't
# list keep their place after the listed ones, switched on
_ORDER = {x.get('key'): i for i, x in enumerate(SETTINGS['sports'])}
_SET = {x.get('key'): x for x in SETTINGS['sports']}
SPORTS.sort(key=lambda s: _ORDER.get(s['key'], len(_ORDER)))
for _s in SPORTS:
    _x = _SET.get(_s['key']) or {}
    _s['status'] = _x.get('status') if _x.get('status') in ('on', 'off', 'in_season') else 'on'
    _s['menu_label'] = _x.get('label') or _s['label']
    _s['launched'] = _s['status'] != 'off'

def has_ml(seg):
    """Whether a segment tracks the moneyline (SU); one with NO_ML_MARKETS doesn't."""
    return 'ML' in (seg.get('markets') or ['ML'])


# ---- Sport families (see CLAUDE.md) --------------------------------------
# Pages are driven from these, never from per-sport copies: a page change
# applies to every sport in the same session.
#
#   period  NHL, MLB: Yes/No style markets (BTTS, YRFI / NRFI)
#   spread  NBA, WNBA, NCAAB, NFL, NCAAF: Spread, Total, Moneyline
#
# calendar: 'daily', or 'weekly' (NFL, NCAAF: the date bar, calendar and
# day records become weeks).
# markets: the Odds / Trends / Stats tabs in order, as (segment, feed key,
# label, kind). kind 'yn' = a two-row Over/Yes over Under/No market (top row
# is always Over / Yes); 'ml3' = 3-way (away, Tie, home); 'side' = away/home.
# A market only shows where there's data for it.
FAMILY = {'nhl': 'period', 'mlb': 'period',
          'nba': 'spread', 'wnba': 'spread', 'ncaab': 'spread', 'nfl': 'spread', 'ncaaf': 'spread'}
# 3-way ML is NHL only (CLAUDE.md)
SPREAD_FAMILY_MARKETS = [('ats', 'Spread', 'side'), ('total', 'Total', 'yn'), ('ml', 'Moneyline', 'side')]
FAMILY_MARKETS = {
    'nhl': [('1p', 'ml', 'Moneyline', 'side'), ('1p', 'total', 'Total 1.5', 'yn'), ('1p', 'btts', 'BTTS', 'yn'),
            ('1p', 'ml3', '3-way ML', 'ml3')],
    'mlb': [('1i', 'rfi', 'NRFI/YRFI', 'yn'), ('f5', 'ml', 'F5 Moneyline', 'side'), ('f5', 'ats', 'F5 Run Line', 'side'),
            ('f5', 'total', 'F5 Total', 'yn')],
}
# Yes/No labels per yn market (top row first)
YES_NO = {'total': ('Over', 'Under'), 'btts': ('Yes', 'No'), 'rfi': ('YRFI', 'NRFI')}
# the words each sport uses for its segments
SEGMENT_WORDS = {'1p': '1st period', '1i': '1st inning', 'f5': 'First 5', '1q': '1st quarter', '1h': '1st half'}

for _s in SPORTS:
    _s['family'] = FAMILY[_s['key']]
    _s['calendar'] = 'weekly' if _s.get('schedule') == 'week' else 'daily'
    _s['family_markets'] = FAMILY_MARKETS.get(_s['key']) or [
        (seg['key'], m, label, kind) for seg in _s['segments'] for m, label, kind in SPREAD_FAMILY_MARKETS
        if m != 'ml' or has_ml(seg)]

BY_KEY = {s['key']: s for s in SPORTS}


def in_season(sp, day=None):
    """Whether `day` (a date; default today in New York) falls between the
    sport's season_start and season_end months (a season can span New Year)."""
    if day is None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        day = datetime.now(ZoneInfo('America/New_York')).date()
    a, b, m = sp['season_start'], sp.get('season_end') or sp['season_start'], day.month
    return a <= m <= b if a <= b else m >= a or m <= b


def shown(day=None):
    """The sports on the site today, in menu order: switched "on", or
    "in_season" and in season."""
    return [s for s in SPORTS if s['status'] == 'on' or s['status'] == 'in_season' and in_season(s, day)]


# the sports shown on the site, in menu order (menus, home, index pages,
# hubs' indexing, the sitemap): every page builds its list from this
LAUNCHED = shown()
# ...of those, the ones in season now (the phone sports row on index pages)
IN_SEASON = [s for s in LAUNCHED if in_season(s)]


def is_launched(key):
    return any(s['key'] == key for s in LAUNCHED)


def sport_names(sps=None):
    """'NHL, NBA, NCAAB, NFL and NCAAF' for copy that lists the sports."""
    labels = [s['label'] for s in (LAUNCHED if sps is None else sps)]
    return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1] if labels else ''


# ---- Team codes (CLAUDE.md "Team abbreviations") ---------------------------
# One code per team, the same everywhere: pro teams the league's standard
# code, 3 characters max; college teams 4 max. Teams outside the league
# (non-Division I opponents) get one made from the school name, so a badge
# and the text next to it never disagree.
COLLEGE = ('ncaab', 'ncaaf')
CODE_FIX = {'UTAH': 'UTA'}   # pro only: college Utah stays UTAH (UT Arlington is UTA)


def code_max(sport_key):
    return 4 if sport_key in COLLEGE else 3


def team_code(sport_key, code):
    code = str(code or '').upper()
    if sport_key not in COLLEGE:
        code = CODE_FIX.get(code, code)
    return code[:code_max(sport_key)]


_COLLEGE_CODES = None
COLLEGE_FALLBACKS = []   # (sport, slug, code) for teams not in the curated list


def college_code(sport_key, slug, code):
    """A team's code: college teams from the curated list
    (data_seed/college_codes.json, by slug), else their current code (logged
    in COLLEGE_FALLBACKS); pro teams through team_code."""
    global _COLLEGE_CODES
    if sport_key not in COLLEGE:
        return team_code(sport_key, code)
    if _COLLEGE_CODES is None:
        try:
            with open(os.path.join(os.path.dirname(SETTINGS_PATH), '..', 'data_seed', 'college_codes.json'), encoding='utf-8') as f:
                _COLLEGE_CODES = json.load(f)
        except (OSError, ValueError):
            _COLLEGE_CODES = {}
    got = (_COLLEGE_CODES.get(sport_key) or {}).get(slug)
    if got:
        return team_code(sport_key, got)
    if (sport_key, slug, code) not in COLLEGE_FALLBACKS:
        COLLEGE_FALLBACKS.append((sport_key, slug, code))
    return team_code(sport_key, code)


def other_code(sport_key, name):
    """A code for a team outside the league, from its school name: the
    first word's letters ('Reinhardt' -> REIN), or the initials of a
    longer name ('North American' -> NA); 4 characters max (3 for pro)."""
    words = re.findall(r"[A-Za-z]+", re.sub(r"\(.*?\)|'s\b|[.'’]", ' ', str(name or '')))
    if not words:
        return '?'
    n = code_max(sport_key)
    stop = {'of', 'the', 'at', 'and'}
    words = [w for w in words if w.lower() not in stop] or words
    if len(words) >= 2 and words[0].lower() in ('st', 'saint', 'north', 'south', 'east', 'west', 'new', 'san', 'santa', 'fort', 'mount', 'mt', 'la'):
        return ''.join(w[0] for w in words[:n]).upper()
    return words[0][:n].upper()


def section_path(sport, section):
    """Root-relative URL for a sport's section, e.g. ('nfl', 'stats') -> /nfl/stats/."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/{s['sections'][section]}/"


def page_links(sport):
    """[(section, label, root-relative path)] for the sport's pages in the
    settings' order and labels (sport_pages): Picks · Matchups · Odds ·
    Trends · Stats · Teams. Picks opens the Preview while PICKS_LIVE is False."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    out = []
    for x in SETTINGS['sport_pages']:
        sec = x.get('key')
        if sec == 'picks':
            out.append(('picks', x.get('label') or 'Picks', picks_path(s) if PICKS_LIVE else preview_path(s)))
        elif sec in s['sections']:
            out.append((sec, x.get('label') or SECTION_LABELS[sec], section_path(s, sec)))
    return out


def preview_path(sport):
    """The sport's Preview, /{slug}/preview/."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/preview/"


def picks_path(sport):
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/picks/"


def guide_path(sport):
    """The sport's Betting Guide, /{slug}/betting-guide/."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/betting-guide/"


# H1s and page titles (every page): "[name] [segment words] [topic]".
# Pills, menus, tags and badges keep the short label.
SEO_NAME = {'ncaab': 'College Basketball', 'ncaaf': 'College Football'}
H1_TOPIC = {'hub': 'Betting', 'picks': 'Picks', 'games': 'Matchups', 'odds': 'Odds', 'trends': 'Betting Trends',
            'stats': 'Stats', 'splits': 'Splits', 'edges': 'Edges: Closers & Faders', 'teams': 'Team Records',
            'guide': 'Betting Guide', 'preview': 'Preview'}
DAILY_TOPICS = {'hub', 'picks', 'games', 'odds', 'trends'}   # "... Today" in the title
TITLE_MAX = 77   # 65 before the suffix became "Run To Your Bets"
CROSS_WORDS = 'First Period, Quarter & Half'   # the every-sport pages


def seo_name(sport):
    """'NHL', 'College Basketball'."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return SEO_NAME.get(s['key'], s['label'])


def seg_words(sport):
    """'First Period', 'First Quarter & First Half', 'First Inning & First Five'."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return ' & '.join(seg['label'].replace('1st ', 'First ').replace(' Innings', '') for seg in s['segments'])


def h1(sport, topic):
    """'NHL First Period Odds'. The same text every day: dates, "Today",
    "Week N" and counts go on the line under it."""
    return f'{seo_name(sport)} {seg_words(sport)} {H1_TOPIC[topic]}'


def page_title(heading, daily=False, weekly=False):
    """'[H1] Today | Run To Your Bets' (weekly sports: 'This Week') for the daily pages,
    '[H1] | Run To Your Bets' for evergreen ones; past TITLE_MAX the "Today" goes first."""
    if daily:
        t = f"{heading} {'This Week' if weekly else 'Today'} | Run To Your Bets"
        if len(t) <= TITLE_MAX:
            return t
    return f'{heading} | Run To Your Bets'


def sport_title(sport, topic):
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return page_title(h1(s, topic), topic in DAILY_TOPICS, s.get('schedule') == 'week')


def segment_summary(sport):
    """'1st Quarter and 1st Half' -- for page descriptions."""
    labels = [seg['label'] for seg in sport['segments']]
    return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]
