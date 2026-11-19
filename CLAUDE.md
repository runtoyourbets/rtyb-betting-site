# RTYB — Run to Your Bets

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
- Muted text is `--text-muted` everywhere (4.5:1+ on cards in both themes);
  never `--text-faint` for words. Cards: one 1px `--card-border`, no card
  inside a card (template.html `.st-card`, shared by Stats, Matchups and Odds).

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
(1.65); its dek is `--fs-dek`. The 1200×630 image cards (`.pc-*`) use
`--pc-grad`, `--pc-text`, `--pc-muted`, `--fs-pc-name` and `--fs-pc-at`.
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
| card title bar | `--title-bg` | rgba(167,139,250,0.14) | #EFEAFE |
| card title text | `--title-text` | #D6CCFF | #4B2FB8 |

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
