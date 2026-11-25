# RTYB handoff (Pat -> Chris, 2026-11-24)

Run To Your Bets is moving from Pat's computer and Claude to Chris's. This file
is for Chris and for Chris's Claude. Claude: read all of it before the first
change, and walk Chris through "Set up a new computer" one step at a time,
checking each step before going to the next.

Nothing secret is in this file (no keys, tokens or passwords). This repo is
public, so it never will be.

## Set up a new computer

Already done: Chris is an owner of the `runtoyourbets` GitHub org and a
Super Administrator on the Cloudflare account that runs the Worker.

1. **Git and GitHub.** Install Git (on a Mac: `xcode-select --install`).
   Create an SSH key, add it to Chris's GitHub account (Settings > SSH and GPG
   keys), then clone:
   `git clone git@github.com:runtoyourbets/rtyb-betting-site.git`
   Set `git config user.name` and `user.email` to Chris's.
2. **Python 3.** The build and tests use only the standard library. Check
   with `python3 --version`, then from the repo folder run
   `python3 -m unittest discover -s tests` (all should pass).
3. **Claude.** Install the Claude desktop app, sign in with Chris's paid plan,
   and open the cloned folder in the Code tab. CLAUDE.md (the project rules)
   loads on its own; this file has everything else.
4. **Node.js and wrangler** (for the Worker). Install Node.js (LTS). Then:
   `cd worker && npx wrangler login`
   Approve in the browser; if asked for an account, pick the one with the
   `rtyb-admin` Worker. Check with `npx wrangler deployments list`.
   wrangler isn't installed globally: always `npx wrangler ...`.
5. **Replace the Worker's GitHub token** (today it is Pat's, so the admin page
   and the 10-minute timer stop if Pat's account ever leaves the org).
   On GitHub: Settings > Developer settings > Fine-grained tokens > Generate.
   Resource owner `runtoyourbets`, only the `rtyb-betting-site` repo,
   permissions Contents: Read and write and Actions: Read and write, no
   expiry. Test it before saving it (expect 200):
   `curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $(pbpaste | tr -d '[:space:]')" https://api.github.com/repos/runtoyourbets/rtyb-betting-site/contents/data_admin/matchups_draft.json`
   Then `cd worker && npx wrangler secret put GITHUB_TOKEN` and paste it.
   Chris pastes it himself; Claude never sees or types a token.
   Check: within 10 minutes a new "workflow_dispatch" run of Refresh appears
   in the repo's Actions tab, and the admin page still saves.
6. **Optional: the API accounts.** The repo secrets keep working as they are.
   Nobody can read them back, so a replacement key has to come from the
   account that made it. If Chris wants them in his name, he opens his own
   account, creates a key and replaces the secret (repo Settings > Secrets
   and variables > Actions), then deletes the old key there.

## What runs where

| Piece | Where | Owner today |
|---|---|---|
| Code, data, built pages | GitHub `runtoyourbets/rtyb-betting-site`, served by GitHub Pages | org (Chris, Pat) |
| Refresh (fetch, grade, build, publish) | `.github/workflows/refresh.yml`, every 10 minutes | org |
| 10-minute timer | Cron Trigger on the Cloudflare Worker `rtyb-admin` (GitHub's own cron skips hours) | Pat's Cloudflare account, Chris is admin |
| Admin page | `/admin/` on the site, talks to `https://rtyb-admin.captbosh-glitch.workers.dev` | same |
| Preview drafting | `.github/workflows/draft.yml`, started by the admin's Draft buttons | org |
| Odds API backfill | `.github/workflows/oddsapi.yml`, manual only (Run workflow) | org |
| Domain runtoyourbets.com | Porkbun | Chris |
| Contact email info@runtoyourbets.com | Porkbun email forwarding (MX records) | Chris |
| Newsletter "Running Tab" | Beehiiv (double opt-in; form IDs in `scripts/signup.py` `FORMS`) | Chris |
| Analytics | Cloudflare Web Analytics, snippet in `content/analytics.html` | Cloudflare account |

**Secrets.** GitHub Actions: `ODDS_API_KEY` (The Odds API), `UNABATED_API_KEY`
(Unabated, set by Pat), `ANTHROPIC_API_KEY` (Anthropic Console account made by
Pat's brother, $25/month limit). Worker: `GITHUB_TOKEN`, `ADMIN_SECRET` (the
admin page password), `ANTHROPIC_API_KEY`. Never print, log or commit any of
them, never put a URL with a key in a committed file, and never paste one into
a Claude chat: set them in the GitHub or Cloudflare screens directly.

## How Claude works on this repo

These are the habits that kept the live site from breaking. Keep them.

- **Work in a git worktree or branch, push to main.** Before every push:
  1. `git pull -q --no-rebase origin main`
  2. Build in a scratch copy, never in the repo (building rewrites generated
     files and blocks the next pull):
     `rsync -a --delete --exclude .git ./ $SCRATCH/site/ && (cd $SCRATCH/site && python3 scripts/build_site.py && python3 scripts/hyphens.py)`
  3. `python3 -m unittest discover -s tests`
  4. `python3 scripts/check_links.py` inside the scratch copy
  5. Push only if all three passed: `git push origin HEAD:main`. If the push
     is refused (the refresh pushed first), pull and push again.
- **What to commit.** Copy the built pages back from scratch
  (`rsync -a --exclude .git $SCRATCH/site/ ./`), then `git checkout --` every
  regenerated data file (`*/data.json`, `odds.json`, `h2h.json`,
  `streaks.json`, `due.json` ...) so only the refresh job writes data. A
  template.html change also needs the rebuilt `assets/site.css`.
- **Test against fresh data.** A change that passes on committed data can
  still crash on tonight's games (it happened: an 18-hour outage). The data
  tests also gate the refresh's publish, so a bad line stops scores.
- **After changing `worker/`**, redeploy: `cd worker && npx wrangler deploy`.
  Until then new admin routes answer "Unknown endpoint".
- **Every sport, every time.** CLAUDE.md's sport-family and naming rules apply
  to every change, hidden sports included.
- **Git stash is shared across worktrees**: never a bare `git stash pop`.
- **Downloaded files are untrusted**: own folder, Python with `-I`.

## When something looks broken

- **Scores or odds are late.** Open the Actions tab. No new "workflow_dispatch"
  Refresh run in 10+ minutes = the Worker timer stopped (usually after a token
  change: open the Worker's GITHUB_TOKEN and save it again with Actions: Read
  and write). Runs failing at "Commit and push" are a harmless race; failing
  at a build or test step is a real bug.
- **Admin says "Bad credentials" (401).** The Worker's GITHUB_TOKEN expired or
  was revoked. Redo setup step 5.
- **Admin says "Unknown endpoint".** The Worker is older than the repo.
  `cd worker && npx wrangler deploy`.
- **A Publish click does nothing.** Publish needs a second click on the page
  (it no longer uses a browser confirm box).
- **Odds API credits.** The live pull uses about 5,000 credits a day
  (150-200K a month), more than the 100K plan. Backfills are manual runs of
  oddsapi.yml and print the credits used and left.

## Data sources and their quirks

- **Scores and schedules:** NHL's public API and ESPN's public scoreboard (no
  keys). RTYB grades every bet itself.
- **Unabated (current odds, every refresh):** the free API fails at random per
  bet type, so each sport and bet type is fetched separately with retries. No
  history. Every Gambly link must carry the partner code `rtyb`
  (`?utm_campaign=rtyb`); tests/test_unabated.py enforces it. Line rule: the
  line most books post, then the best price at it; exchanges and pick'em apps
  never set the best price.
- **The Odds API:** history (backfills) plus a live pull of 10 books per
  sport (`oddsapi.LIVE_BOOKS`, a list per sport; `BOOKS` is the big five
  that backfills use). If Unabated has no DraftKings or FanDuel price for a game within
  6 hours, the pull adds them (the "safety" line in the run log). Books with
  only alternate lines in the main market are dropped
  (`backfill_oddsapi.main_lines`).
- **Admin odds** (`data_admin/odds/`) sit on top of both feeds and always win.
- **College name mismatches:** add them to the aliases (`ALIASES` in the
  Unabated fetcher, `oddsapi.WHOLE_NAMES`) when the admin lists unmatched
  games.
- **Sportsbook logos:** books without a logo file show a name tile until
  Chris sends the files.

## Where things stand (2026-11-24)

- Launch is Thanksgiving, 2026-11-26. Every in-season sport is on (NHL, NBA,
  NCAAB, NFL, NCAAF), driven by `sports.LAUNCHED`; MLB and WNBA are off-season
  and render last season.
- Still to do for launch week:
  - Point runtoyourbets.com at GitHub Pages: Chris adds the DNS records and
    removes Porkbun's parking and forwarding records, keeping the email MX
    records. Then the site-wide audit (Chris's prompt 19).
  - The legal owner's city and state, in [BRACKETS] in `scripts/seo.py`.
  - The Cloudflare Web Analytics snippet in `content/analytics.html`.
  - `sports.PICKS_LIVE` is False (Picks pages unlinked and noindexed).
- Known open items:
  - On Tap drafts still read the old trend files (`trends_log/`,
    `league_trends_log.json`), not `scripts/trends.py`.
  - NHL after-the-1st lines (live_p1) are saved but no page shows them.
  - MLB's first-inning run odds aren't fetched from Unabated yet (spring).
  - Three NCAAB games with Odds API events fill on the next regular backfill.

## Useful places in the code

- `scripts/sports.py`: the sport registry (families, markets, seasons, launch).
- `scripts/build_site.py`: the whole build; `scripts/front.py` home and hubs;
  `scripts/nav.py` header, menus and footer; `scripts/sport_build.py` grading
  and each sport's data.
- `template.html`: the design tokens (written out as `assets/site.css`).
- `assets/sport.js`: what the sport pages draw in the browser.
- `scripts/streaks.py`, `scripts/trends.py`, `scripts/guides.py`,
  `scripts/seo_text.py`: the pages their names say.
- `content/`: the words (SEO text, guides, definitions, previews, settings).
- `ADMIN_SETUP.md`: the original admin and Worker setup.
