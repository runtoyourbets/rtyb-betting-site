# RTYB - Run to Your Bets

Static site on GitHub Pages, built by `scripts/build_site.py` and rebuilt by the
refresh job (`.github/workflows/refresh.yml`) every 10 minutes. Tests:
`python3 -m unittest discover -s tests`.

## Sport families

- Every page change applies to every sport through the shared config
  (`scripts/sports.py`: `FAMILY`, `FAMILY_MARKETS`, `calendar`) and the shared
  templates, in the same session. Never build a feature for one sport only.
- Period family: NHL, MLB. Spread family: NBA, WNBA, NCAAB, NFL, NCAAF.
- 3-way ML exists for NHL only (no 3-way tab, record or data anywhere else,
  including MLB's F5).
  Weekly: NFL, NCAAF (date bars, calendars and day records become weeks).
- If a change can't apply to a sport (missing data, or a market that doesn't
  exist there), say so in the summary instead of skipping it silently.
- Hidden sports (`launched: False`) stay out of menus and noindexed, but get
  every new layout so they're ready the day they're switched on. Off-season
  sports must render from last season's data.

## Naming rule (every page)

- Pro sports (NHL, NBA, WNBA, NFL, MLB): desktop shows the team nickname
  (Lightning, Celtics); mobile shows the abbreviation (TB, BOS).
- College sports (NCAAB, NCAAF): desktop shows the school name (Kentucky,
  Arizona), never the nickname; mobile shows the school abbreviation (UK, ARIZ).
- Inside cards, odds rows and records: abbreviations on every device.
- Exception: the Teams index (/{sport}/teams/) shows names on phones too:
  the nickname for pro teams (Oilers), the school for college (Kentucky).
  Names scan better than codes in that list. Desktop there: the full name
  for pro teams (Edmonton Oilers), the school name for college.
- Team abbreviations: one code per team, the same everywhere (badges, cards,
  tables, Slate). Pro teams use the league's standard code, 3 characters max
  (BOS, NY, GS, UTA); college teams 4 max (UCLA, IOWA, ORST). Teams outside
  the league get one made from the school name (`sports.other_code`, written
  to data.json as `otherCodes`), so a badge never disagrees with the text
  next to it. `sports.team_code` enforces the limits.
- In-season sports: `sports.LAUNCHED` (launched and between `season_start`
  and `season_end`) drives every menu, pill row and list of sports; never
  hard-code one.
- A game with no saved line for any market of its segment shows nowhere, and
  Results records count only games with a line for the market.
- Every team shows its logo (scripts/fetch_sport_logos.py also fetches the
  non-Division I opponents'). No logo: a small colored badge with the
  abbreviation.
- Color rule (tokens in template.html):
  - Best price (Odds only) = soft green tint with a thin green outline
    (`--best-bg` + `--best`).
  - Win = soft green fill (`--good-dim`); loss = the cell dims to 50%;
    tie/push = soft yellow fill (`--push-dim`).
  - Units: green above +0.5u (`--good`), red below -0.5u (`--bad`), yellow in
    between (`--push`).
  - Never blue for results or units.
  - Streak counts (Streak Trends, Streaks to Watch, team-page Current
    streaks) are heat chips: `--heat-1..4` for 3-4, 5-6, 7-8, 9+.
  - Total, BTTS and NRFI results are never win/loss: Over/Yes/YRFI warm
    (`--warm-bg` + `--warm-line`), Under/No/NRFI purple (`--cool-bg` +
    `--cool-line`) in game logs, team-page Last game and Matchups results.
- Plain hyphen only; never en/em dashes or minus signs. Records 80% (12-3-8),
  scores 2-0, ranges 35-40, headers W-L-T, prices -160, empty cells "-"
  A stray dash is converted, never a reason to stop the refresh: the admin
  converts on save, the drafter as it writes, the build and the refresh's
  last step in everything written (scripts/hyphens.py); the check runs on
  the finished pages (tests/test_plain_hyphen.py).
- Muted text is `--text-muted` everywhere (4.5:1+ on cards in both themes);
  never `--text-faint` for words. Cards: one 1px `--card-border`, no card
  inside a card (template.html `.st-card`, shared by Stats, Matchups and Odds).

## Betting Guides

Content is Markdown in content/betting-guides/ (17 files: index.md, the
general guides and one per sport); the Glossary comes from the Definitions
tool (content/definitions.json), never a glossary.md. Guide text says
"Run To Your Bets" (not RTYB). Pipe tables render as the standard table; a
"## FAQ" ("### question" + answer) becomes FAQPage data; every guide page
but the index has a Betting Guides › [page] breadcrumb (BreadcrumbList).
General guides use the front-matter title as H1 and <title>; sport guides
keep their fixed H1. "Updated" and dateModified = the last build that
changed a number on the page (betting_guides_log.json).

Live numbers (scripts/guide_stats.py): `{{sport.segment.stat:window}}` and
`{{asof}}` ("Thursday, Nov 19", ET). An unknown token fails the build with
the file and the token. Windows: `season`, `week`, `lastweek` (daily sports:
Mon-Sun ET so far and the Mon-Sun before; NFL/NCAAF: this game week and the
one before). Off-season sports show the last full season in every window
(no season suffix). College counts Division I / FBS games only. Same data
as the Trends/Stats pages. Empty numbers (fewer than 10 games) never show:
`{{token:window|label}}` writes "label value" and drops both when empty
(`{{nba.1q.over:week|; this week}}`); a list item or sentence with an empty
season value is dropped; anything else empty shows "-".

Every site link in a guide goes through the root helper (guides.rooted), so
it works on GitHub Pages and the domain; tests/test_betting_guides.py checks
every guide link resolves. Section headers (## on every guide page, the
glossary and the index) are purple Barlow Condensed (`--accent-purple-text`),
no icon tile or underline, 36px above; "Where to go next" lists become pills
(with icon tiles). Sport guides show two example games per sport
(content/betting-guides/examples.json, tests/test_guide_examples.py checks
every won / lost / push cell against its score and line): NHL and MLB an
Example card under each bet with a row per game; spread sports one card
per game (first quarter, then first half) under "The bets", then any
example's `note`. Then "How to read the odds" (the first example only,
whole dollars). Body text max 720px.
Records and scores never wrap at the hyphen (`.nw`: seo.nowrap on the
built pages, SHELL_JS on what the sport pages draw).

- `nhl.1p`: `over` (O-U), `btts_yes` (Y-N), `tie` ("34% (117 of 346)"),
  `home_ml` (2-way W-L), `top_score` ("1-0 (27%)"), `goal_share` ("29%")
- `mlb.1i.nrfi` ("49% (1,200 of 2,429)"); `mlb.f5`: `home_ml`, `tie`, `over`
- `nba.1q`, `wnba.1q`: `over`, `fav_ats`, `home_ml`; `nba.1h`, `wnba.1h`:
  `over`, `fav_ats`
- `ncaab.1h`: `over`, `fav_ats`, `home_ml`
- `nfl.1q`: `over`, `fav_ats`; `nfl.1h`: `over`, `fav_ats`, `home_ml`
- `ncaaf.1q`, `ncaaf.1h`: `over`, `fav_ats`

`over` = the segment total's Over (O-U, pushes out); `fav_ats` = the
segment favorite covering the segment spread (W-L); `home_ml` = the home
team winning the segment, 2-way (W-L, ties out). Rates read "59% (204-142)".

## SEO page text

content/seo/ holds one Markdown file per index, hub and sport page (77;
front matter path / title / description / description_offseason / intro);
scripts/seo_text.py applies them in seo.finish. A path with no built page or
an unknown token fails the build. Titles end "| Run To Your Bets" (every
page; og:site_name too). Off-season: "Today" / "Week {{week}}" become
"[YEAR] Season" and description_offseason is used. Tokens: the guides' plus
`{{asof}}`, `{{season}}`, `{{week}}`, `{{season_start}}`, `{{date}}`,
`{{headline}}`. The body is the About block: closed (How to read's pattern),
at the page bottom (How to read · About · Betting Guides · footer); "## More
..." links become gd-pills (short name, full name in aria-label/title), "##
... in other sports" a stacked list of sports.LAUNCHED, "## FAQ" FAQPage
data. Team pages (~640) get their title, description, intro, About and FAQ
from their own numbers (content/seo/_team-pages.md is the spec). "Updated
1:05 PM ET" under the intro: seo_updated_log.json (Odds and Matchups: the
last odds pull). tests/test_seo_text.py: unique titles and descriptions,
110-165 characters, no "RTYB".

## Footer

One footer on every page (scripts/nav.py footer(); sports.FOOTER is
'everywhere'): logo + line and the Running Tab signup, six link columns
(Sports, Odds, Trends, Stats: sports.LAUNCHED; Learn; Run To Your Bets),
the 21+ line, small print, copyright and legal links. Phones: stacked, the
columns as tap-to-open rows.

## Design tokens

Every new page or component uses these tokens only (CSS variables and `.t-*`
classes in template.html's `<style>`, written out as assets/site.css). No page,
script or other stylesheet sets its own font-family, font-size, font-weight or
colors for text, cells or units; tests/test_design_tokens.py enforces it. Team
badges (logo stand-ins) are the one exception.

Type: two families. Barlow Condensed (bold) for page titles and section
headings, Source Sans 3 for everything else, numbers included, with tabular
figures on the body. No mono font. No bold numbers: emphasis is color and fill.
Preview's article text (scripts/preview.py `.pv-body`) is Source Sans 3
(`--ff-read`) at `--fs-read` (18px, 17px phone), line-height `--lh-read`
(1.65); its dek is `--fs-dek`. The 1200×630 image cards (`.pc-*`, scripts/preview.py
card_html) use `--pc-grad` (no background image), `--pc-over` / `--pc-over-ice`
over the sport's assets/share/bg/ image, `--pc-text`, `--pc-muted`,
`--pc-box-bg`, `--pc-box-line`, `--fw-pc-heavy` and the `--fs-pc-*` sizes;
`--gold` only for the big number and the line chip.
The home page's product line under the H1 is `--fs-lede` (17px, 16px phone);
the sport row's label (nav) is Barlow Condensed at `--fs-row-label` (16px).
Odds tables' segment and market labels (1Q, ATS, ML...) are the `.mk-h` chip:
`--mkh-text` on `--mkh-bg` (gold in dark, purple in light).

One gold: `--gold` (#F5C542, both themes) for the logo, PICKS, GO PREMIUM,
labels, chips, pills, push pills and the dark odds-header accent; no other
gold anywhere. Light mode never puts gold text on a light background: dark
text (`--on-gold`) on a gold chip, or dark text with a gold underline or left
bar (template.html "One gold, light mode" rules).

| Token | Use | Font | Weight | Size |
|---|---|---|---|---|
| hero | Home page brand H1 only | Barlow Condensed | 700 | 40px (30px phone) |
| title | Page title | Barlow Condensed | 700 | 32px (26px phone) |
| section | Section heading | Barlow Condensed | 700 | 20px (18px phone) |
| team | Card title, team names, segment scores next to teams | Source Sans 3 | 600 | 15px |
| body / num | Body and table text; main numbers (lines, records, %, units) | Source Sans 3 | 400 text / 500 numbers | 14px |
| price | Prices under lines, secondary numbers, notes | Source Sans 3 | 400, muted | 13px |
| label | Column headers, small caps labels, status | Source Sans 3 | 600, caps, 0.6px spacing, muted | 11px |

Colors:

| Token | CSS variable | Dark | Light |
|---|---|---|---|
| page bg | `--bg` | #0B0F15 | #F5F7FA |
| card bg | `--panel` | #131921 | #FFFFFF |
| card border | `--card-border` | #2A3442 | #D5DCE5 |
| divider | `--border-soft` | #1F2731 | #E6EBF1 |
| text | `--text` | #E8EDF3 | #141B24 |
| muted text | `--text-muted` | #A3AFBE (7.9:1 on cards) | #5A6676 (5.8:1) |
| cell | `--cell` | #1A212B | #F1F4F8 |
| win fill | `--good-dim` | rgba(34,197,94,0.16) | #DFF3E6 |
| best bg | `--best-bg` | rgba(34,197,94,0.10) | #EEFAF2 |
| best outline | `--best` | rgba(74,222,128,0.55) | #7FCF9C |
| units up | `--good` | #4ADE80 | #15803D |
| units down | `--bad` | #F87171 | #B91C1C |
| units even | `--push` | #F5C542 | #F5C542 fill; the number in `--on-gold` on a gold chip |
| push fill | `--push-dim` | rgba(245,197,66,0.14) | #FBF3D6 |
| brand gold | `--gold` | #F5C542 | #F5C542 |
| text on gold | `--on-gold` | #0B0F15 | #0B0F15 |
| footer bg | `--foot-bg` | #0E131A | #EEF1F5 |
| tab bar bg | `--bb-bg` | #1D1733 | #4B2FB8 |
| tab bar top line | `--bb-line` | rgba(167,139,250,0.40) | #4B2FB8 |
| tab off | `--bb-off` | #C9C2E6 | #D9D0FF |
| tab on | `--bb-on` | #FFFFFF | #FFFFFF |
| active tab chip | `--bb-chip` | rgba(167,139,250,0.32) | rgba(255,255,255,0.20) |
| active tab bar (3px) | `--bb-mark` | #A78BFA | `--gold` |
| card title bar | `--title-bg` | rgba(167,139,250,0.14) | #EFEAFE |
| card title text | `--title-text` | #D6CCFF | #4B2FB8 |
| guide section heading | `--accent-purple-text` | #A78BFA | #4B2FB8 |
| streak heat 3-4 | `--heat-1` | #F8E3A0 | #F8E3A0 (dark text) |
| streak heat 5-6 | `--heat-2` | #F5C542 | #F5C542 (dark text) |
| streak heat 7-8 | `--heat-3` | #F59E0B | #F59E0B (dark text) |
| streak heat 9+ | `--heat-4` | #EA580C | #EA580C (white text, `--on-heat-4`) |
| Over / Yes / YRFI result | `--warm-bg`, `--warm-line` | rgba(245,158,11,0.18) / 0.55 | same |
| Under / No / NRFI result | `--cool-bg`, `--cool-line` | rgba(167,139,250,0.18) / 0.55 | same |

Spacing:

| Token | Value |
|---|---|
| `--cell-gap` | 8px between every odds/result cell, side to side and row to row |
| `--cell-min-h`, `--cell-pad`, `--cell-radius` | cells: 48px min height, 4px 6px padding, 8px radius; line on top, price under |
| `--open-gap` | 12px extra after the Open column |
| `--odds-pad-x`, `--game-pad-top`, `--game-pad-bottom` | Odds tables: 24px left/right, 12px above and 14px below each game, a divider between games |
| `--card-pad`, `--card-radius` | cards: 16px 18px padding (`--card-pad-y`, `--card-pad-x`), 1px `--card-border`, 14px radius |

Every Stats card (Overview, Splits groups, Edges, team-page Splits) opens with a title bar:
a soft purple band (`--title-bg`) across the top with the title in label style
(`--title-text`). Stat rows keep label / record / % / units at 1.4 / 1.2 / 0.8 / 1.
