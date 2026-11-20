---
path: "/[sport]/teams/[team]/"
title: "[Full team name] [Segment] Stats, Record & Trends | Run To Your Bets"
description: "[Team] [segment] record {{season}}: [market 1] [rate], [market 2] [rate], [market 3] [rate]. Odds, streaks, splits and game log."
---
TEAM PAGES (about 640). Written by the build from each team's own numbers, so every page is different and stays current.
Words in [brackets] are filled from the page's data. A line whose number is missing (fewer than 5 graded games) is dropped.

TITLE
- Pro: "Edmonton Oilers First Period Stats, Record & Trends | Run To Your Bets"
- College: the school name, the way the Teams index shows it on desktop: "Kentucky First Half Stats, Record & Trends | Run To Your Bets"
- Over 60 characters is fine: the team name and segment come first.

DESCRIPTION (140 to 160 characters; drop market 3 if it runs long)
- NHL: moneyline, Over 1.5, BTTS Yes
- NBA, WNBA, NFL, College Football: 1Q ATS, 1Q Over, 1H ATS (College Football: 1Q ATS, 1Q Over, 1H Over)
- College Basketball: 1H ATS, 1H Over, 1H moneyline
- MLB: F5 moneyline, NRFI, F5 Over
- Example: "Edmonton Oilers first period record this season: moneyline 80% (12-3-8), Over 1.5 52% (12-11), BTTS Yes 22% (5-18). Odds, streaks, splits and game log."

INTRO (one line under the H1, as today's subtitle): "[Team] [segment] record, odds, streaks, splits and game log {{season}}."

ABOUT BLOCK (bottom of the page, closed by default like "How to read this page", above Betting Guides)

## Run To Your Bets: the [Team] in the [segment]

1. Season line: "Run To Your Bets has tracked every [Team] [segment] {{season}}. They've won the [segment] [rate], [units] betting them every game at the closing price."
   - Spread family: use the first segment's spread: "They've covered the first quarter spread [rate], [units] betting them every game."
   - MLB: the F5 moneyline: "They've led after five [rate] ..."
2. Totals line:
   - NHL: "Their first periods have gone Over 1.5 [rate], and both teams have scored [rate]."
   - MLB: "Their first innings have stayed scoreless (NRFI) [rate], and their first fives have gone Over [rate]."
   - Spread family: "Their first quarters have gone Over [rate]; their first halves, [rate]." (College Basketball: first halves only.)
3. Home and road: "At home they're [rate]; on the road, [rate]." (Same market as line 1.)
4. Compared with the league: "League-wide, [the same market] is [league rate], so they're [N] points [above/below] average." Only when the gap is 5 points or more.
5. Right now: "Current streak: [streak text] ([N] straight)." Only when it's 3 or more; else "Last 10: [record]."
6. Next: "Next up: [@/vs] [Opponent], [day] [time]." Linked to the opponent's team page. Off-season: "[YEAR] season final. Next season starts {{season_start}}."

### Example

One line from the team's most recent graded game, using the same wording as the Last game card:
"Last game: [@/vs] [Opponent], [segment] [score]. [Market] [line] [price]: [won/lost/push]."
Example: "Last game: @ TB, 1st Period 1-0. EDM ML +113: won."

## FAQ   (FAQPage data, answered from the team's numbers)

### What is the [Team] [segment] record {{season}}?
"[Record] on the moneyline ([rate]), [units]. At home [rate], on the road [rate]."

### Do the [Team] go Over in the [segment]?
- NHL: "Their first periods have gone Over 1.5 [rate] {{season}}. The league average is [league rate]."
- MLB: "Their first fives have gone Over [rate] {{season}}, and their first innings have gone YRFI [rate]."
- Spread family: "Their first quarters have gone Over [rate] {{season}}. The league average is [league rate]."

### Do the [Team] cover the [first segment] spread?   (spread family only)
"[Rate] {{season}}, [units]. As a favorite, [rate]; as an underdog, [rate]."

## More [Sport] [segment] betting
[Sport] Teams · [Sport] Trends · [Sport] Odds · [Sport] Splits · [Sport] Betting Guide · [Next opponent] (team page)

FULL EXAMPLES (real numbers from Nov 19, shape only; the build fills its own)

Oilers: "Run To Your Bets has tracked every Edmonton Oilers first period this season. They've won the first period 80% (12-3-8), +6.43 units betting them every game at the closing price. Their first periods have gone Over 1.5 52% (12-11), and both teams have scored 22% (5-18). At home they're 67% (4-2-6); on the road, 89% (8-1-2). Current streak: BTTS No (5 straight). Next up: @ Tampa Bay, Thursday 7:30 PM."

Brewers (off-season): "Run To Your Bets tracked every Milwaukee Brewers first five in the 2026 season. They led after five 61% (89-57-29), and their first innings stayed scoreless 53% (92-83). 2026 season final. Next season starts Wednesday, March 24."

College: same template; teams with fewer than 5 graded games show only lines 1, 3 and 6 and no FAQ. Non-Division I / non-FBS opponents don't get pages (as now).
