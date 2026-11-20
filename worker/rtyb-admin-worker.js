/**
 * Cloudflare Worker behind RTYB's Admin page (Matchups Tool + Results
 * Tool). Same shape as thebettorline's "Pull now" worker: the GitHub token
 * and the admin password both live as Worker secrets (`wrangler secret
 * put`, never in this file, never shipped to the browser) -- the static
 * admin page never sees either one, it only knows the password long enough
 * to send it in a header.
 *
 * Unlike the "Pull now" worker (which just fires a repository_dispatch and
 * lets a workflow do the real work), this one commits directly to small
 * JSON data files in the repo via GitHub's Contents API -- Save writes a
 * draft, Publish writes the file scripts/build_site.py actually merges
 * into the live site. Both are ordinary git commits on `main`, so your
 * existing refresh.yml push-trigger (once `data_admin/**` is added to its
 * paths list -- see the README note) picks them up and rebuilds within a
 * minute or two, same as any other change to template.html/scripts.
 *
 * Deploy:
 *   cd worker
 *   npm install -g wrangler      # if you don't have it
 *   wrangler secret put GITHUB_TOKEN      # fine-grained PAT scoped to this repo: "Contents: write" and "Actions: write"
 *   wrangler secret put ADMIN_SECRET      # the password the admin page prompts for
 *   wrangler secret put ANTHROPIC_API_KEY # only needed for the "Parse Odds Data with AI" field -- console.anthropic.com
 *   wrangler deploy
 * Then put the deployed URL into admin/index.html's WORKER_URL constant.
 *
 * Timer: a Cron Trigger (wrangler.toml [triggers], or the dashboard's
 * Settings > Triggers) calls scheduled() every 10 minutes, which starts
 * refresh.yml. GitHub's own schedule is best-effort and under load skips
 * runs for hours (Nov 6-7, 2026: nothing between 10pm and 5am ET, so
 * Friday's results waited until morning); its cron stays on as a backup.
 *
 * Endpoints (all POST, all require header "X-Admin-Secret"):
 *   /matchups/save     body: {date, matchups: [{away,home,mlAway,mlHome,totalOver,totalUnder,bttsYes,bttsNo}, ...]}
 *   /matchups/publish   same body -- also writes data_admin/odds_overrides.json
 *   /matchups/parse      body: {date, text, games: [{away,home,awayName,homeName}, ...]} -- asks an LLM to pull
 *                         the six fields per matchup out of free-form pasted text; does NOT write anything,
 *                         just returns {ok, matchups} for the page to drop into the form
 *   /results/save       body: {date, results: [{away,home,awayScore,homeScore}, ...]}
 *   /results/publish    same body -- also writes data_admin/results_overrides.json
 *   /odds/parse         body: {sport, segment, mode, text, games: [{away, home, date, awayName, homeName}]} --
 *                         AI fills one segment's table for the other sports; writes nothing
 *   /content/list       body: {} -- every draft (content/drafts/) and column (content/columns/) with its text,
 *                         plus the last 3 days' published previews (live: true) so they stay editable
 *   /content/save       body: {path, text} -- saves an edited draft, column or published preview in place
 *   /content/publish    body: {path, text} -- writes it to content/published/ and removes the draft
 *   /content/redraft    body: {sport, date} -- starts draft.yml (Redraft / Draft now): drafts that
 *                         sport's Preview for that date and replaces the unpublished draft; a
 *                         published preview is refused (unpublish it first)
 *   /odds/save          body: {sport, rows: [{date, away, home, segment, ats, ml, total}], removes: [{date, away, home}]}
 *                         -- odds for the other sports (not NHL), one file per sport at
 *                         data_admin/odds/{sport}.json, stored per game + segment + market
 *                         (MLB: segment "1i" carries nrfi_yrfi {yrfi, nrfi}; "f5" a 0.5 run line)
 *   /settings/save      body: {bttsSourceBook} -- data_admin/settings.json: the sportsbook the
 *                         NHL BTTS prices are copied from ("consensus" = no book), which
 *                         labels the BTTS column on the NHL Odds page
 *   /site/get           body: {} -- content/site_settings.json (menus, sports, switches)
 *   /site/save          body: the whole settings object -- checked (validateSite), then
 *                         written to content/site_settings.json; the next refresh rebuilds
 *   /definitions/save   body: {entries: {id: {name, category, sports, short, long, status, show_last}}}
 *                        -- merges into content/definitions.json (the admin's Definitions tab)
 *   /definitions/draft  body: {items: [{id, name, category, sports, calc, short}]} (up to 25) -- asks Claude
 *                        for a short (max 200 characters) and long definition each; writes nothing
 */

const REPO_OWNER = "runtoyourbets"; // GitHub org that owns the repo (moved from captbosh-glitch 2026-11)
const REPO_NAME = "rtyb-betting-site";
const BRANCH = "main";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*", // tighten to your site's origin once it has a custom domain, if you want
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Secret",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

// --- base64 helpers (Workers don't have Node's Buffer) ---
function b64encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
function b64decode(str) {
  return decodeURIComponent(escape(atob(str)));
}

async function ghRequest(env, path, options) {
  return fetch(`https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/${path}`, {
    ...options,
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "rtyb-admin-worker",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options && options.headers),
    },
  });
}

// Read-modify-write a JSON file in the repo. `mutate(current)` gets the
// file's current parsed content (or {} if the file doesn't exist yet) and
// must return the new content to write. Returns {ok, status, detail}.
async function commitJsonFile(env, filePath, message, mutate) {
  const getResp = await ghRequest(env, `contents/${filePath}?ref=${BRANCH}`, { method: "GET" });

  let sha = undefined;
  let current = {};
  if (getResp.status === 200) {
    const info = await getResp.json();
    sha = info.sha;
    try {
      current = JSON.parse(b64decode(info.content.replace(/\n/g, "")));
    } catch {
      current = {};
    }
  } else if (getResp.status !== 404) {
    const text = await getResp.text();
    return { ok: false, status: getResp.status, detail: `GET ${filePath}: ${text.slice(0, 300)}` };
  }

  const updated = mutate(current);
  const putResp = await ghRequest(env, `contents/${filePath}`, {
    method: "PUT",
    body: JSON.stringify({
      message,
      content: b64encode(JSON.stringify(updated, null, 0)),
      branch: BRANCH,
      ...(sha ? { sha } : {}),
    }),
  });

  if (putResp.status === 200 || putResp.status === 201) {
    return { ok: true };
  }
  const text = await putResp.text();
  return { ok: false, status: putResp.status, detail: `PUT ${filePath}: ${text.slice(0, 300)}` };
}

// --- Preview: drafts and columns (Markdown) ---------------------------------
// Drafts are written by scripts/daily_content.py into content/drafts/;
// columns are hand-written into content/columns/. Publishing moves a file
// to content/published/, which the next refresh turns into its page.
const CONTENT_PATH = /^content\/(drafts|columns)\/[a-z0-9][a-z0-9-]*\.md$/;
// a published preview (editable after it goes live): content/published/{sport}-preview-{date}.md
const LIVE_PATH = /^content\/published\/[a-z0-9]+-preview-(\d{4}-\d{2}-\d{2})\.md$/;
const LIVE_DAYS = 3;

async function getFile(env, filePath) {
  const resp = await ghRequest(env, `contents/${filePath}?ref=${BRANCH}`, { method: "GET" });
  if (resp.status !== 200) return { ok: false, status: resp.status, detail: `GET ${filePath}: ${(await resp.text()).slice(0, 300)}` };
  const info = await resp.json();
  return { ok: true, sha: info.sha, text: b64decode(info.content.replace(/\n/g, "")) };
}

async function putText(env, filePath, message, text) {
  const cur = await getFile(env, filePath);
  const resp = await ghRequest(env, `contents/${filePath}`, {
    method: "PUT",
    body: JSON.stringify({ message, content: b64encode(text), branch: BRANCH, ...(cur.ok ? { sha: cur.sha } : {}) }),
  });
  if (resp.status === 200 || resp.status === 201) return { ok: true };
  return { ok: false, status: resp.status, detail: `PUT ${filePath}: ${(await resp.text()).slice(0, 300)}` };
}

async function deleteFile(env, filePath, message) {
  const cur = await getFile(env, filePath);
  if (!cur.ok) return cur.status === 404 ? { ok: true } : cur;
  const resp = await ghRequest(env, `contents/${filePath}`, {
    method: "DELETE",
    body: JSON.stringify({ message, sha: cur.sha, branch: BRANCH }),
  });
  if (resp.status === 200) return { ok: true };
  return { ok: false, status: resp.status, detail: `DELETE ${filePath}: ${(await resp.text()).slice(0, 300)}` };
}

// content/site_settings.json (admin's Site settings tab; scripts/sports.py reads it)
const SITE_SETTINGS = "content/site_settings.json";

// --- Definitions (content/definitions.json, scripts/definitions.py) ---------
const DEFINITIONS = "content/definitions.json";
const DEF_ID = /^(label|trend|team|split|edge|term|feature):[A-Za-z0-9_-]{1,60}$/;
const DEF_CATS = ["labels", "league", "team", "splits", "edges", "terms", "features"];
const DEF_STATUS = ["needs", "draft", "live"];
const DEF_SHORT_MAX = 200;

function validateDefinitions(body) {
  const entries = body && body.entries;
  if (!entries || typeof entries !== "object" || Array.isArray(entries)) return "entries must be an object";
  const ids = Object.keys(entries);
  if (!ids.length || ids.length > 400) return "send 1 to 400 entries";
  for (const id of ids) {
    const e = entries[id];
    if (!DEF_ID.test(id)) return `bad id: ${id}`;
    if (!e || typeof e.name !== "string" || !e.name.trim() || e.name.length > 120) return `${id}: name is required (120 characters max)`;
    if (!DEF_CATS.includes(e.category)) return `${id}: unknown category`;
    if (!DEF_STATUS.includes(e.status)) return `${id}: status must be needs, draft or live`;
    if (typeof (e.short || "") !== "string" || (e.short || "").length > DEF_SHORT_MAX) return `${id}: the short definition is ${DEF_SHORT_MAX} characters max`;
    if (typeof (e.long || "") !== "string" || (e.long || "").length > 2000) return `${id}: the long definition is 2000 characters max`;
    if (e.status === "live" && !(e.short || "").trim()) return `${id}: a Live entry needs a short definition`;
    if (!Array.isArray(e.sports || []) || (e.sports || []).some((x) => !/^[a-z]{2,6}$/.test(x))) return `${id}: bad sports list`;
  }
  return null;
}

async function saveDefinitions(env, body) {
  const cur = await getFile(env, DEFINITIONS);
  let doc = { config: {}, entries: {} };
  if (cur.ok) { try { doc = JSON.parse(cur.text); } catch { return { ok: false, status: 500, detail: "definitions.json isn't valid JSON" }; } }
  doc.entries = doc.entries || {};
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const keep = ["name", "category", "sports", "short", "long", "status", "show_last", "group", "where"];
  for (const [id, e] of Object.entries(body.entries)) {
    const next = { ...(doc.entries[id] || {}) };
    for (const k of keep) if (e[k] !== undefined) next[k] = e[k];
    if (next.category !== "league") delete next.show_last;
    next.edited = today;
    doc.entries[id] = next;
  }
  doc.entries = Object.fromEntries(Object.entries(doc.entries).sort(([a], [b]) => (a < b ? -1 : 1)));
  const ids = Object.keys(body.entries);
  return putText(env, DEFINITIONS, `Definitions: ${ids.length === 1 ? ids[0] : ids.length + " entries"} (admin)`, JSON.stringify(doc, null, 1) + "\n");
}

async function draftDefinitions(env, body) {
  const items = (body && body.items) || [];
  if (!Array.isArray(items) || !items.length || items.length > 25) return { ok: false, status: 400, detail: "send 1 to 25 items" };
  const list = items.map((x) => ({ id: String(x.id || ""), name: String(x.name || "").slice(0, 120), category: String(x.category || ""),
    sports: (x.sports || []).slice(0, 7), how_calculated: String(x.calc || "").slice(0, 600), current: String(x.short || "").slice(0, 300) }));
  if (list.some((x) => !DEF_ID.test(x.id))) return { ok: false, status: 400, detail: "bad id" };
  // the writing guide's voice (the same guide Preview's drafts follow)
  const guide = await getFile(env, "content/preview_writing_guide.md");
  const voice = guide.ok ? `\n\nWrite in the voice of RTYB's writing guide:\n<guide>\n${guide.text.slice(0, 8000)}\n</guide>` : "";
  const prompt = `You write the short definitions shown in the "i" boxes on RTYB, a sports betting stats site about the opening segment of games (NHL 1st period, NBA/WNBA/college basketball 1st quarter and 1st half, NFL/college football 1st quarter and 1st half, MLB 1st inning and first five innings).

For each item below, write:
- "short": one to three plain sentences, at most ${DEF_SHORT_MAX} characters, saying what the term, trend, label or split means for a bettor. Use {segment} where the opening segment's name belongs (the site fills in "1st period", "1st half"...) and {sport} for the league's name, only when needed. No hype, no advice, no emoji, no "this trend".
- "long": two to four sentences with more detail (how it's counted, an example). Optional: "" when the short one says it all.

Base the wording on how_calculated and keep any current text's meaning.${voice}

Answer with JSON only: {"drafts": {"<id>": {"short": "...", "long": "..."}}}

Items:
${JSON.stringify(list, null, 1)}`;
  const res = await askClaude(env, prompt);
  if (!res.ok) return res;
  const drafts = (res.parsed && res.parsed.drafts) || {};
  const out = {};
  for (const x of list) {
    const d = drafts[x.id];
    if (!d || typeof d.short !== "string") continue;
    out[x.id] = { short: d.short.trim().slice(0, DEF_SHORT_MAX), long: typeof d.long === "string" ? d.long.trim().slice(0, 2000) : "" };
  }
  return { ok: true, drafts: out };
}
const SITE_KEYS = {
  main_menu: ["sports", "matchups", "odds", "trends", "stats", "picks"],
  sports: ["nhl", "nba", "wnba", "mlb", "ncaab", "nfl", "ncaaf"],
  sport_pages: ["picks", "games", "odds", "trends", "stats", "teams"],
  bottom_bar: ["matchups", "odds", "trends", "stats", "picks"],
};
// the settings object, cleaned, or a string saying what's wrong
function validateSite(b) {
  if (!b || typeof b !== "object") return "settings must be an object";
  const out = {};
  for (const [list, keys] of Object.entries(SITE_KEYS)) {
    const items = b[list];
    if (!Array.isArray(items) || !items.length) return `${list} must be a list`;
    const seen = new Set();
    out[list] = [];
    for (const x of items) {
      if (!x || !keys.includes(x.key) || seen.has(x.key)) return `${list}: unknown or repeated item ${x && x.key}`;
      seen.add(x.key);
      const label = String(x.label || "").trim();
      if (!label || label.length > 30) return `${list}: ${x.key} needs a label (30 characters max)`;
      const item = { key: x.key, label };
      if (list === "sports") {
        if (!["on", "off", "in_season"].includes(x.status)) return `sports: ${x.key} status must be on, off or in_season`;
        item.status = x.status;
      }
      out[list].push(item);
    }
  }
  if (out.bottom_bar.length !== 4) return "bottom_bar needs exactly 4 tabs";
  const sw = b.switches || {};
  const preview = typeof sw.PREVIEW_LIVE === "boolean" ? sw.PREVIEW_LIVE : sw.ON_TAP_LIVE;   // ON_TAP_LIVE: the old name
  if (typeof preview !== "boolean" || typeof sw.PICKS_LIVE !== "boolean") return "switches: PREVIEW_LIVE and PICKS_LIVE must be true or false";
  if (!["home-only", "everywhere"].includes(sw.FOOTER)) return "switches: FOOTER must be home-only or everywhere";
  if (sw.ADS_ON !== undefined && typeof sw.ADS_ON !== "boolean") return "switches: ADS_ON must be true or false";
  out.switches = { PREVIEW_LIVE: preview, PICKS_LIVE: sw.PICKS_LIVE, FOOTER: sw.FOOTER, ADS_ON: sw.ADS_ON === true };
  // Preview drafting: the earliest draft time (ET), the weekly sports' day,
  // and each sport's mode (weekly only where the schedule has weeks)
  const dr = b.drafts || {};
  const time = dr.DRAFT_TIME_ET || "08:00";
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return "drafts: DRAFT_TIME_ET must be HH:MM (24-hour, ET)";
  const day = dr.WEEKLY_DRAFT_DAY || "Tuesday";
  if (!DAYS.includes(day)) return "drafts: WEEKLY_DRAFT_DAY must be a day of the week";
  const mode = {};
  for (const k of SITE_KEYS.sports) {
    const m = (dr.PREVIEW_MODE || {})[k] || (WEEKLY_SPORTS.includes(k) ? "weekly" : "daily");
    if (!["daily", "weekly"].includes(m) || (m === "weekly" && !WEEKLY_SPORTS.includes(k))) return `drafts: ${k} can't be ${m}`;
    mode[k] = m;
  }
  out.drafts = { DRAFT_TIME_ET: time, WEEKLY_DRAFT_DAY: day, PREVIEW_MODE: mode };
  // Seasons (scripts/seasons.py): each sport's OPENING_DAY ("" or a date) and
  // up to two MILESTONES {label, date} for the hubs' off-season countdown
  const se = b.seasons || {};
  out.seasons = {};
  for (const k of SITE_KEYS.sports) {
    const x = se[k] || {};
    const opening = String(x.OPENING_DAY || "");
    if (opening && !ISO_DAY.test(opening)) return `seasons: ${k} OPENING_DAY must be YYYY-MM-DD`;
    const ms = Array.isArray(x.MILESTONES) ? x.MILESTONES : [];
    if (ms.length > 2) return `seasons: ${k} takes two milestones at most`;
    const clean = [];
    for (const m of ms) {
      const label = String((m && m.label) || "").trim(), date = String((m && m.date) || "");
      if (!label || label.length > 40 || !ISO_DAY.test(date)) return `seasons: ${k} milestones need a label (40 characters max) and a YYYY-MM-DD date`;
      clean.push({ label, date });
    }
    out.seasons[k] = { OPENING_DAY: opening, MILESTONES: clean };
  }
  return out;
}
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const WEEKLY_SPORTS = ["nfl", "ncaaf"];   // weekly needs the schedule's weeks (ESPN)

// Redraft / Draft now: start draft.yml for one sport and date (it replaces
// the unpublished draft). A published preview is refused: unpublish first.
const DRAFT_WORKFLOW = "draft.yml";
async function startDraft(env, body) {
  const sport = body && body.sport, day = body && body.date;
  if (![...SITE_KEYS.sports, "all"].includes(sport) || !/^\d{4}-\d{2}-\d{2}$/.test(day || "")) {
    return { ok: false, status: 400, detail: "sport and date (YYYY-MM-DD) required" };
  }
  const pub = await ghRequest(env, `contents/content/published/${sport}-preview-${day}.md?ref=${BRANCH}`, { method: "GET" });
  if (pub.status === 200) return { ok: false, status: 409, detail: "This preview is published. Unpublish it before redrafting." };
  const r = await ghRequest(env, `actions/workflows/${DRAFT_WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: BRANCH, inputs: { sport, date: day } }),
  });
  if (r.status !== 204) return { ok: false, status: r.status, detail: `Couldn't start the draft: ${(await r.text()).slice(0, 300)}` };
  return { ok: true };
}

// Every draft and column, with its text: {ok, files: [{path, text}]}
async function listContent(env) {
  const files = [];
  for (const dir of ["content/drafts", "content/columns"]) {
    const resp = await ghRequest(env, `contents/${dir}?ref=${BRANCH}`, { method: "GET" });
    if (resp.status === 404) continue;
    if (resp.status !== 200) return { ok: false, status: resp.status, detail: `GET ${dir}: ${(await resp.text()).slice(0, 300)}` };
    for (const f of await resp.json()) {
      if (f.type !== "file" || !CONTENT_PATH.test(f.path)) continue;
      const got = await getFile(env, f.path);
      if (got.ok) files.push({ path: f.path, text: got.text });
    }
  }
  const resp = await ghRequest(env, `contents/content/published?ref=${BRANCH}`, { method: "GET" });
  if (resp.status === 200) {
    const since = new Date(Date.now() - LIVE_DAYS * 86400000).toISOString().slice(0, 10);
    for (const f of await resp.json()) {
      const m = f.type === "file" && LIVE_PATH.exec(f.path);
      if (!m || m[1] < since) continue;
      const got = await getFile(env, f.path);
      if (got.ok) files.push({ path: f.path, text: got.text, live: true });
    }
  }
  return { ok: true, files };
}

function validateContent(body, live) {
  const ok = body && typeof body.path === "string" && (CONTENT_PATH.test(body.path) || (live && LIVE_PATH.test(body.path)));
  if (!ok) return live ? "path must be a .md file in content/drafts/, content/columns/ or a published preview" : "path must be a .md file in content/drafts/ or content/columns/";
  if (typeof body.text !== "string" || !body.text.trim() || body.text.length > 50000) return "text must be 1-50,000 characters";
  return null;
}

// Publish: write the (edited) text to content/published/ and remove the
// draft (and the fact packet beside it). Columns publish as column-{name}.md.
async function publishContent(env, body) {
  const name = body.path.split("/").pop();
  const isColumn = body.path.startsWith("content/columns/");
  const target = `content/published/${isColumn && !name.startsWith("column-") ? "column-" + name : name}`;
  // the real publish time, for the page's "Published 8:59 PM ET" (front matter)
  const stamp = `published: ${new Date().toISOString().slice(0, 19)}Z`;
  const text = body.text.startsWith("---\n") && !/^published:/m.test(body.text.split("\n---")[0])
    ? body.text.replace("---\n", `---\n${stamp}\n`) : body.text;
  const put = await putText(env, target, `Publish ${name} (admin)`, text);
  if (!put.ok) return put;
  const del = await deleteFile(env, body.path, `Remove ${name} after publishing (admin)`);
  if (!del.ok) return del;
  if (!isColumn) await deleteFile(env, body.path.replace(/\.md$/, ".packet.json"), `Remove ${name}'s packet after publishing (admin)`);
  return { ok: true };
}

function matchupKey(date, away, home) {
  return `${date}|${away}|${home}`;
}

function validateMatchups(body) {
  if (!body || typeof body.date !== "string" || !Array.isArray(body.matchups)) return "expected {date, matchups: []}";
  for (const m of body.matchups) {
    if (!m || typeof m.away !== "string" || typeof m.home !== "string") return "each matchup needs away/home codes";
  }
  return null;
}

function validateResults(body) {
  if (!body || typeof body.date !== "string" || !Array.isArray(body.results)) return "expected {date, results: []}";
  for (const r of body.results) {
    if (!r || typeof r.away !== "string" || typeof r.home !== "string") return "each result needs away/home codes";
  }
  return null;
}

// Save: stash this day's edited field values as a draft, keyed by matchup,
// so reloading the admin page (or coming back tomorrow) shows what was
// last typed in, even before Publish.
async function saveMatchupsDraft(env, body) {
  return commitJsonFile(env, "data_admin/matchups_draft.json", `Admin: save matchups draft ${body.date}`, (current) => {
    const dayMap = {};
    body.matchups.forEach((m) => {
      dayMap[`${m.away}|${m.home}`] = {
        mlHome: m.mlHome ?? null, mlAway: m.mlAway ?? null,
        totalOver: m.totalOver ?? null, totalUnder: m.totalUnder ?? null,
        bttsYes: m.bttsYes ?? null, bttsNo: m.bttsNo ?? null,
      };
    });
    return { ...current, [body.date]: dayMap };
  });
}

// Publish: same draft write, PLUS pushing the odds live via
// data_admin/odds_overrides.json, in the exact shape build_site.py already
// expects from an odds source (ml / totals / btts_yes / btts_no) -- it
// applies this one AFTER the normal fetched-odds merge, so a published
// admin value always wins.
async function publishMatchups(env, body) {
  const draftResult = await saveMatchupsDraft(env, body);
  if (!draftResult.ok) return draftResult;

  return commitJsonFile(env, "data_admin/odds_overrides.json", `Admin: publish matchups ${body.date}`, (current) => {
    const next = { ...current };
    body.matchups.forEach((m) => {
      const key = matchupKey(body.date, m.away, m.home);
      const entry = {};
      if (m.mlAway != null && m.mlHome != null) {
        entry.ml = { [m.away]: m.mlAway, [m.home]: m.mlHome };
      }
      if (m.totalOver != null && m.totalUnder != null) {
        entry.totals = { "1.5": { over: m.totalOver, under: m.totalUnder } };
      }
      if (m.bttsYes != null) entry.btts_yes = m.bttsYes;
      if (m.bttsNo != null) entry.btts_no = m.bttsNo;
      next[key] = entry;
    });
    return next;
  });
}

async function saveResultsDraft(env, body) {
  return commitJsonFile(env, "data_admin/results_draft.json", `Admin: save results draft ${body.date}`, (current) => {
    const dayMap = {};
    body.results.forEach((r) => {
      dayMap[`${r.away}|${r.home}`] = { awayScore: r.awayScore ?? null, homeScore: r.homeScore ?? null };
    });
    return { ...current, [body.date]: dayMap };
  });
}

// Publish: writes data_admin/results_overrides.json keyed the same way as
// odds_overrides.json. build_site.py merges awayP1/homeP1 from here onto
// the matching game, overriding whatever the live NHL schedule fetch has
// (or filling it in early, before the live fetcher would otherwise have a
// 1st-period score) -- that's the whole point of entering it by hand.
async function publishResults(env, body) {
  const draftResult = await saveResultsDraft(env, body);
  if (!draftResult.ok) return draftResult;

  return commitJsonFile(env, "data_admin/results_overrides.json", `Admin: publish results ${body.date}`, (current) => {
    const next = { ...current };
    body.results.forEach((r) => {
      if (r.awayScore == null || r.homeScore == null) return; // incomplete row, skip rather than publish a half result
      const key = matchupKey(body.date, r.away, r.home);
      next[key] = { awayP1: r.awayScore, homeP1: r.homeScore };
    });
    return next;
  });
}

// ---- Other sports' odds ----
// Segments each sport takes odds for; mirrors scripts/sports.py. MLB's
// 1st inning is NRFI/YRFI only; its First Five uses a fixed 0.5 run line.
const SPORT_SEGMENTS = {
  nfl: ["1q", "1h"], nba: ["1q", "1h"], wnba: ["1q", "1h"],
  ncaaf: ["1q", "1h"], ncaab: ["1h"], mlb: ["1i", "f5"],
};
const NRFI_SEGMENTS = { mlb: ["1i"] };
const HALF_POINT_LINE_SEGMENTS = { mlb: ["f5"] };
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TEAM_RE = /^[a-z0-9-]{1,60}$/;

function isNum(n) { return typeof n === "number" && Number.isFinite(n); }
function isHalf(n) { return Math.abs(n * 2 - Math.round(n * 2)) < 1e-9; }
function isOdds(n) { return isNum(n) && Math.abs(n) >= 100; }

// Same checks as the admin page; returns an error string or null.
function checkOddsRow(r, sport) {
  const where = r && `${r.date} ${r.away} @ ${r.home} ${r.segment}`;
  if (!r || !DATE_RE.test(r.date) || !TEAM_RE.test(r.away) || !TEAM_RE.test(r.home)) return "each row needs date, away and home";
  if (r.away === r.home) return `${where}: away and home are the same team`;
  if (!SPORT_SEGMENTS[sport].includes(r.segment)) return `${where}: unknown segment`;
  if ((NRFI_SEGMENTS[sport] || []).includes(r.segment)) {
    if (r.nrfi_yrfi != null && (!isOdds(r.nrfi_yrfi.yrfi) || !isOdds(r.nrfi_yrfi.nrfi))) return `${where}: needs both YRFI and NRFI prices`;
    return null;
  }
  if (r.ats != null) {
    if ((HALF_POINT_LINE_SEGMENTS[sport] || []).includes(r.segment)) {
      const a = r.ats.away || {};
      if (Math.abs(a.line) !== 0.5) return `${where}: F5 line is always 0.5`;
      if (r.ats.fav_override != null && !["away", "home"].includes(r.ats.fav_override)) return `${where}: fav_override must be away or home`;
    }
    const a = r.ats.away || {}, h = r.ats.home || {};
    if (!isNum(a.line) || !isNum(h.line)) return `${where}: ATS needs both lines`;
    if (a.line !== -h.line) return `${where}: ATS lines must be opposites`;
    if (!isHalf(a.line)) return `${where}: ATS line should be a whole or half point`;
    if (!isOdds(a.price) || !isOdds(h.price)) return `${where}: ATS prices look wrong`;
  }
  if (r.ml != null && (!isOdds(r.ml.away) || !isOdds(r.ml.home))) return `${where}: ML needs both sides`;
  if (r.total != null) {
    if (!isNum(r.total.line) || r.total.line <= 0 || !isHalf(r.total.line)) return `${where}: total should be a positive whole or half point`;
    if (!isOdds(r.total.over) || !isOdds(r.total.under)) return `${where}: total prices look wrong`;
  }
  return null;
}

function validateOdds(body) {
  if (!body || !SPORT_SEGMENTS[body.sport] || !Array.isArray(body.rows)) return "expected {sport, rows: []}";
  if (body.removes != null && !Array.isArray(body.removes)) return "removes must be a list";
  if (body.rows.length > 2000) return "too many rows in one save";
  for (const r of body.rows) {
    const err = checkOddsRow(r, body.sport);
    if (err) return err;
  }
  for (const x of body.removes || []) {
    if (!x || !DATE_RE.test(x.date) || !TEAM_RE.test(x.away) || !TEAM_RE.test(x.home)) return "each remove needs date, away and home";
  }
  return null;
}

// Each row replaces that game's odds for that one segment (other segments
// are kept). A market sent as null is cleared.
async function saveSportOdds(env, body) {
  const dates = [...new Set(body.rows.map((r) => r.date).concat((body.removes || []).map((x) => x.date)))].sort();
  const label = dates.length === 1 ? dates[0] : `${dates[0]}..${dates[dates.length - 1]}`;
  return commitJsonFile(env, `data_admin/odds/${body.sport}.json`, `Admin: ${body.sport} odds ${label}`, (current) => {
    const next = { ...current };
    for (const r of body.rows) {
      const key = matchupKey(r.date, r.away, r.home);
      const game = next[key] || { date: r.date, away: r.away, home: r.home, segments: {} };
      const pick = (m, fields) => (m == null ? null : Object.fromEntries(fields.map((f) => [f, m[f]])));
      const stored = (NRFI_SEGMENTS[body.sport] || []).includes(r.segment)
        ? { nrfi_yrfi: pick(r.nrfi_yrfi, ["yrfi", "nrfi"]) }
        : {
          ats: r.ats == null ? null : {
            away: pick(r.ats.away, ["line", "price"]), home: pick(r.ats.home, ["line", "price"]),
            ...((HALF_POINT_LINE_SEGMENTS[body.sport] || []).includes(r.segment) ? { fav_override: r.ats.fav_override ?? null } : {}),
          },
          ml: pick(r.ml, ["away", "home"]),
          total: pick(r.total, ["line", "over", "under"]),
        };
      game.segments = { ...game.segments, [r.segment]: stored };
      next[key] = game;
    }
    for (const x of body.removes || []) delete next[matchupKey(x.date, x.away, x.home)];
    return next;
  });
}

// ---- Other sports' AI parser: fills one segment's table in the admin ----
const PARSE_SHAPES = {
  // spread sports (NFL, NBA, WNBA, NCAAF, NCAAB)
  spread: {
    fields: `- atsAway, atsHome: the point spread for each side (e.g. -3.5 and 3.5; they must be opposites)
- atsAwayPrice, atsHomePrice: the price on each spread side, if shown (e.g. -110, -105)
- mlAway, mlHome: moneyline odds for each side (e.g. -150, 130)
- total: the over/under line (e.g. 44.5)
- overPrice, underPrice: the price on the over and the under, if shown`,
    example: '{"away": "...", "home": "...", "date": "YYYY-MM-DD", "atsAway": -3.5, "atsAwayPrice": -110, "atsHome": 3.5, "atsHomePrice": -110, "mlAway": -150, "mlHome": 130, "total": 44.5, "overPrice": -110, "underPrice": -110}',
  },
  // MLB First Five: the run line is always 0.5, so only its prices matter
  f5: {
    fields: `- atsAwayPrice, atsHomePrice: the PRICES on the first-five run line (the line itself is always +/-0.5), e.g. -105, -115
- fav: "away" or "home" -- which side is laying -0.5 on the run line, only if the text says so
- mlAway, mlHome: first-five moneyline odds
- total: the first-five over/under line (whole number or .5)
- overPrice, underPrice: the price on the over and the under, if shown`,
    example: '{"away": "...", "home": "...", "date": "YYYY-MM-DD", "atsAwayPrice": -105, "atsHomePrice": -115, "fav": "away", "mlAway": -130, "mlHome": 110, "total": 4.5, "overPrice": -110, "underPrice": -110}',
  },
  // MLB 1st inning
  rfi: {
    fields: `- yrfi: the price for YES, a run scores in the 1st inning (YRFI)
- nrfi: the price for NO, no run in the 1st inning (NRFI)`,
    example: '{"away": "...", "home": "...", "date": "YYYY-MM-DD", "yrfi": 110, "nrfi": -135}',
  },
};

function validateSportParse(body) {
  if (!body || !SPORT_SEGMENTS[body.sport] || !PARSE_SHAPES[body.mode]) return "expected {sport, segment, mode, text, games: []}";
  if (!SPORT_SEGMENTS[body.sport].includes(body.segment)) return "unknown segment";
  if (typeof body.text !== "string" || !body.text.trim()) return "text is empty";
  if (body.text.length > 60000) return "text is too long -- paste fewer games at once";
  if (!Array.isArray(body.games) || !body.games.length || body.games.length > 400) return "expected the games to match against";
  for (const g of body.games) {
    if (!g || !TEAM_RE.test(g.away) || !TEAM_RE.test(g.home) || !DATE_RE.test(g.date)) return "each game needs away, home and date";
  }
  return null;
}

async function parseSportOddsWithAI(env, body) {
  const shape = PARSE_SHAPES[body.mode];
  const clean = (x) => String(x || "").replace(/["\n]/g, " ").slice(0, 80);
  const gameList = body.games
    .map((g) => `- away="${g.away}" (${clean(g.awayName)}), home="${g.home}" (${clean(g.homeName)}), date="${g.date}"`)
    .join("\n");
  const prompt = `You extract ${clean(body.label)} ${clean(body.segmentLabel)} betting odds from pasted text (it may be a spreadsheet dump, a sportsbook screen, a picks message, or anything else) and match each game to one of the known games below.

Only use odds for the ${clean(body.segmentLabel)} -- ignore full-game odds and other segments.

Known games for ${clean(body.view)} (use these exact "away"/"home"/"date" values in your output, don't invent new ones):
${gameList}

Pasted text:
"""
${body.text}
"""

For each known game you can find odds for, extract:
${shape.fields}

Rules:
- Only include a field if you actually found a number for it in the text -- leave it out, never guess.
- Only include games from the known list that you found data for.
- Odds are plain numbers (no + sign; negative numbers keep their -).
- Respond with ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{"games": [${shape.example}]}`;

  const answer = await askClaude(env, prompt);
  if (!answer.ok) return answer;
  const games = answer.parsed && answer.parsed.games;
  if (!Array.isArray(games)) return { ok: false, status: 502, detail: "AI response didn't contain a games array" };
  // Keep only known games and numeric fields.
  const known = new Set(body.games.map((g) => `${g.date}|${g.away}|${g.home}`));
  const pairs = new Set(body.games.map((g) => `${g.away}|${g.home}`));
  const out = [];
  for (const g of games) {
    if (!g || !pairs.has(`${g.away}|${g.home}`)) continue;
    const row = { away: g.away, home: g.home };
    if (g.date && known.has(`${g.date}|${g.away}|${g.home}`)) row.date = g.date;
    for (const [k, v] of Object.entries(g)) {
      if (k === "fav" && (v === "away" || v === "home")) row.fav = v;
      else if (!["away", "home", "date", "fav"].includes(k) && isNum(v)) row[k] = v;
    }
    out.push(row);
  }
  return { ok: true, games: out };
}

function validateParse(body) {
  if (!body || typeof body.date !== "string" || typeof body.text !== "string" || !Array.isArray(body.games)) {
    return "expected {date, text, games: []}";
  }
  if (!body.text.trim()) return "text is empty";
  for (const g of body.games) {
    if (!g || typeof g.away !== "string" || typeof g.home !== "string") return "each game needs away/home codes";
  }
  return null;
}

// Sends one prompt to Claude and parses its JSON answer. Shared by the NHL
// parser and the other sports' parser. Returns {ok, parsed} or
// {ok: false, status, detail}.
async function askClaude(env, prompt) {
  if (!env.ANTHROPIC_API_KEY) {
    return { ok: false, status: 501, detail: "ANTHROPIC_API_KEY isn't set as a Worker secret yet -- wrangler secret put ANTHROPIC_API_KEY" };
  }
  let resp;
  try {
    resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        // If a safety classifier declines the request, retry it server-side
        // on Anthropic's recommended fallback model instead of failing.
        "anthropic-beta": "server-side-fallback-2026-07-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-5-5",
        // Room for the model's thinking plus the JSON answer; a simple
        // extraction like this doesn't need deep reasoning, so effort is low.
        max_tokens: 16000,
        output_config: { effort: "low" },
        fallbacks: "default",
        messages: [{ role: "user", content: prompt }],
      }),
    });
  } catch (e) {
    return { ok: false, status: 502, detail: `Anthropic API request failed: ${e.message}` };
  }

  if (!resp.ok) {
    const text = await resp.text();
    return { ok: false, status: resp.status, detail: `Anthropic API: ${text.slice(0, 300)}` };
  }

  const data = await resp.json();
  if (data.stop_reason === "refusal") {
    return { ok: false, status: 502, detail: "The AI declined to parse this text -- try trimming it to just the odds, or enter them manually" };
  }
  if (data.stop_reason === "max_tokens") {
    return { ok: false, status: 502, detail: "The AI's response was cut off -- try pasting fewer games at once" };
  }
  // The response can start with thinking blocks; the answer is in the text block(s).
  const raw = (data.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text)
    .join("");
  let parsed;
  try {
    // Strip accidental markdown fences just in case, then parse.
    const cleaned = raw.trim().replace(/^```(json)?/i, "").replace(/```$/, "").trim();
    parsed = JSON.parse(cleaned);
  } catch (e) {
    return { ok: false, status: 502, detail: `Couldn't parse the AI's response as JSON: ${raw.slice(0, 200)}` };
  }
  return { ok: true, parsed };
}

// Asks Claude to pull the six odds fields per matchup out of whatever text
// was pasted in (a Google Sheets block, a picks message, anything). Doesn't
// touch the repo -- just returns parsed values for the admin page to drop
// into the Matchups Tool inputs, which are reviewed and Saved like any
// manual edit.
async function parseMatchupsWithAI(env, body) {
  if (!env.ANTHROPIC_API_KEY) {
    return { ok: false, status: 501, detail: "ANTHROPIC_API_KEY isn't set as a Worker secret yet -- wrangler secret put ANTHROPIC_API_KEY" };
  }

  const gameList = body.games
    .map((g) => `- away="${g.away}" (${g.awayName || g.away}), home="${g.home}" (${g.homeName || g.home})`)
    .join("\n");

  const prompt = `You extract 1st-period NHL betting odds from pasted text (it may be a spreadsheet dump, a picks/Discord message, or anything else) and match each game to one of the known matchups below.

Known matchups for ${body.date} (use these exact "away"/"home" codes in your output, don't invent new ones):
${gameList}

Pasted text:
"""
${body.text}
"""

For each matchup you can find odds for, extract:
- mlAway, mlHome: moneyline odds for the away/home team (e.g. -120, 135)
- totalOver, totalUnder: 1st-period Over/Under 1.5 goals odds
- bttsYes, bttsNo: Both Teams To Score odds

Rules:
- Only include a field if you actually found a number for it in the text -- use null, never guess or invent a value.
- Only include matchups from the known list above that you found data for. Skip matchups you can't find.
- Odds are plain numbers (no + sign in your output; negative numbers keep their -).
- Respond with ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{"matchups": [{"away": "...", "home": "...", "mlAway": -120, "mlHome": 135, "totalOver": -130, "totalUnder": 100, "bttsYes": 155, "bttsNo": -205}]}`;

  const answer = await askClaude(env, prompt);
  if (!answer.ok) return answer;
  const parsed = answer.parsed;
  if (!parsed || !Array.isArray(parsed.matchups)) {
    return { ok: false, status: 502, detail: "AI response didn't contain a matchups array" };
  }
  return { ok: true, matchups: parsed.matchups };
}

// --- the 10-minute timer: start a refresh unless one is already queued or running ---
const REFRESH_WORKFLOW = "refresh.yml";

async function startRefresh(env) {
  for (const status of ["in_progress", "queued"]) {
    const r = await ghRequest(env, `actions/workflows/${REFRESH_WORKFLOW}/runs?status=${status}&per_page=1`);
    if (r.ok && (await r.json()).total_count > 0) {
      console.log(`refresh already ${status}; skipping`);
      return;
    }
  }
  const r = await ghRequest(env, `actions/workflows/${REFRESH_WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ref: BRANCH }),
  });
  if (r.status !== 204) console.log(`refresh dispatch failed: ${r.status} ${await r.text()}`);
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(startRefresh(env));
  },

  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }
    if (request.method !== "POST") {
      return json({ ok: false, error: "Method not allowed" }, 405);
    }

    const providedSecret = request.headers.get("X-Admin-Secret") || "";
    if (!env.ADMIN_SECRET || providedSecret !== env.ADMIN_SECRET) {
      return json({ ok: false, error: "Unauthorized" }, 401);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Invalid JSON body" }, 400);
    }

    const url = new URL(request.url);
    let result;
    switch (url.pathname) {
      case "/matchups/save": {
        const err = validateMatchups(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveMatchupsDraft(env, body);
        break;
      }
      case "/matchups/publish": {
        const err = validateMatchups(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await publishMatchups(env, body);
        break;
      }
      case "/matchups/parse": {
        const err = validateParse(body);
        if (err) return json({ ok: false, error: err }, 400);
        const parseResult = await parseMatchupsWithAI(env, body);
        if (parseResult.ok) return json({ ok: true, matchups: parseResult.matchups });
        return json({ ok: false, error: parseResult.detail || "Parse failed", status: parseResult.status }, 502);
      }
      case "/results/save": {
        const err = validateResults(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveResultsDraft(env, body);
        break;
      }
      case "/results/publish": {
        const err = validateResults(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await publishResults(env, body);
        break;
      }
      case "/odds/parse": {
        const err = validateSportParse(body);
        if (err) return json({ ok: false, error: err }, 400);
        const parseResult = await parseSportOddsWithAI(env, body);
        if (parseResult.ok) return json({ ok: true, games: parseResult.games });
        return json({ ok: false, error: parseResult.detail || "Parse failed", status: parseResult.status }, 502);
      }
      case "/odds/save": {
        const err = validateOdds(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveSportOdds(env, body);
        break;
      }
      case "/settings/save": {
        if (!body || typeof body.bttsSourceBook !== "string" || !/^[a-z0-9]{1,20}$/.test(body.bttsSourceBook)) {
          return json({ ok: false, error: "bttsSourceBook must be a source id or \"consensus\"" }, 400);
        }
        result = await commitJsonFile(env, "data_admin/settings.json", `Admin: BTTS source book ${body.bttsSourceBook}`,
          (current) => ({ ...current, bttsSourceBook: body.bttsSourceBook }));
        break;
      }
      case "/site/get": {
        const got = await getFile(env, SITE_SETTINGS);
        if (!got.ok) { result = got; break; }
        try { return json({ ok: true, settings: JSON.parse(got.text) }); } catch { return json({ ok: false, error: "site_settings.json isn't valid JSON" }, 500); }
      }
      case "/site/save": {
        const clean = validateSite(body);
        if (typeof clean === "string") return json({ ok: false, error: clean }, 400);
        result = await putText(env, SITE_SETTINGS, "Admin: site settings", JSON.stringify(clean, null, 2) + "\n");
        break;
      }
      case "/content/list": {
        const listed = await listContent(env);
        if (listed.ok) return json({ ok: true, files: listed.files });
        result = listed;
        break;
      }
      case "/content/save": {
        const err = validateContent(body, true);
        if (err) return json({ ok: false, error: err }, 400);
        result = await putText(env, body.path, `Edit ${body.path.split("/").pop()} (admin)`, body.text);
        break;
      }
      case "/content/redraft": {
        result = await startDraft(env, body);
        if (!result.ok && (result.status === 400 || result.status === 409)) return json({ ok: false, error: result.detail }, result.status);
        break;
      }
      case "/content/publish": {
        const err = validateContent(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await publishContent(env, body);
        break;
      }
      case "/definitions/save": {
        const err = validateDefinitions(body);
        if (err) return json({ ok: false, error: err }, 400);
        result = await saveDefinitions(env, body);
        break;
      }
      case "/definitions/draft": {
        const drafted = await draftDefinitions(env, body);
        if (drafted.ok) return json({ ok: true, drafts: drafted.drafts });
        return json({ ok: false, error: drafted.detail || "Draft failed", status: drafted.status }, drafted.status === 400 ? 400 : 502);
      }
      default:
        return json({ ok: false, error: "Unknown endpoint" }, 404);
    }

    if (result.ok) return json({ ok: true });
    return json({ ok: false, error: result.detail || "GitHub commit failed", status: result.status }, 502);
  },
};
