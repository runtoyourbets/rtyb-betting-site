/*
 * Situational Results: the split table every sport's Stats page uses (and
 * NFL / NCAAF team pages). Rows come from the sport's registry
 * (assets/splits/{sport}.js, window.RTYB_SPLITS[sport]); this file builds a
 * context `c` for every team-game in a segment and counts each row's games.
 *
 *   var sit = RTYBSit.create(src)
 *   sit.render(box, view)            view = {mode: 'league'} | {mode: 'team', slug}
 *   sit.contexts(k, 'current')       [{c, r}] for the team-page game log
 *   sit.tags(c)                      registry rows a team-game counts toward
 *   sit.nextFits(k, slug, gameId)    registry rows a team's upcoming game fits
 *   sit.spots(k, slug, gameId, mkt)  those rows that are real edges (the hub's Team to Watch)
 *
 * src: {sport, segments [{key, label, tag}], teams {slug: {name, conference,
 *   division}}, seasons: [{key: 'current', label, games: {date: [game]}},
 *   {key: 'prev', label, load: () => Promise<{date: [game]}>}], conf, rivals,
 *   tz {team: utc offset}, totalCuts {k: [lo, hi]}, locked, lockHtml, url,
 *   today (ET date), comboLocked () => true when combining Splits filters is
 *   premium-locked,
 *   onSeg(k, section) (a segment change; return false to let this file redraw),
 *   ties (true: a tied segment is its own result with a Tie %; false: a push),
 *   tonightLocked () => true when "Tonight only" is premium-locked}
 * League view extras (the Splits page): view.range ({from, to} | {wk} |
 * {post: true | false} (postseason / regular season) | {none}), view.noSeg (the page has its own segment toggle), view.controls /
 * view.line (HTML for the header), view.after(box) (wire them after a redraw).
 * Team view extras: view.next = {id, label} (the team's next game and how
 * to say it: "Tonight vs MTL"); its rows get a Tonight tag.
 *
 * Games are in sport.js's shape: {id, start, state, away, home, as, hs,
 * als, hls, neutral, intl, note, post, wk, fs (home full-game spread),
 * fml {away, home}, tvn, ar, hr, ag / hg (NHL starting goalies),
 * firstGoal, ot, odds {k: {...}}, res {k: {sc, su, ats, tot, btts, u}}}.
 * res is from the away side; u[market] = [away units, home units]
 * ([over, under] / [yes, no]).
 *
 * Definitions (Chris's spec): rest days = days between games minus 1;
 * back-to-back = played the previous ET calendar day; 3 games in 4 nights =
 * 3rd game within a 4-day window ending today; road trip game number =
 * consecutive away games counting this one (a home game resets it); time
 * zones crossed = previous venue's zone vs this one (venue = home team);
 * previous game = the team's last game in the same season.
 */
(function() {
  'use strict';
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function flip(r) { return { W: 'L', L: 'W' }[r] || r; }
  function fmtU(u) { var r = Math.round(u * 100) / 100; return (r > 0 ? '+' : '') + r.toFixed(2) + 'u'; }
  // tone: 1 / -1 colors the pill green / red (a real edge); else neutral gray
  function pill(u, n, prefix, tone) {
    if (!n) return '<span class="u-pill u-none">&mdash;</span>';
    var r = Math.round(u * 100) / 100;
    var cls = tone > 0 ? 'u-pos2' : tone < 0 ? 'u-neg2' : 'u-zero';
    return '<span class="u-pill ' + cls + '">' + (prefix || '') + fmtU(r) + '</span>';
  }
  var ET_FMT = null, DATE_FMT = null;
  function etParts(iso) {
    ET_FMT = ET_FMT || new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    var o = {};
    ET_FMT.formatToParts(new Date(iso)).forEach(function(x) { o[x.type] = x.value; });
    return { dow: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(o.weekday), mins: (+o.hour % 24) * 60 + (+o.minute) };
  }
  function etDate(iso) { DATE_FMT = DATE_FMT || new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }); return DATE_FMT.format(new Date(iso)); }
  function dayDiff(a, b) { return Math.round((new Date(b + 'T12:00:00Z') - new Date(a + 'T12:00:00Z')) / 864e5); }
  function regWeek(g) { var m = /^2-(\d+)$/.exec(g.wk || ''); return m ? +m[1] : null; }
  function fbU(res) { return res === 'W' ? 0.9091 : res === 'L' ? -1 : 0; }   // -110 when only the line was saved
  function implied(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
  // favorite by a segment's own odds (moneyline, else the spread line)
  function segFav(o) {
    var ml = (o || {}).ml || {}, a = ml.away, h = ml.home;
    if (typeof a === 'number' && typeof h === 'number' && implied(a) !== implied(h)) return implied(a) > implied(h) ? 'away' : 'home';
    var line = (((o || {}).ats || {}).away || {}).line;
    if (typeof line === 'number' && line !== 0) return line < 0 ? 'away' : 'home';
    return null;
  }

  // Market definitions: how a result reads for a team-game and its units.
  var MARKETS = {
    su: { label: 'Moneyline', url: 'moneyline', head: 'W-L-T', pctHead: 'Win %' },
    // 3-way: the same games as su, but a tie is a loss; Tie % = how often the tie bet won
    ml3: { label: '3-way ML', url: '3-way', head: 'W-L', pctHead: 'Win %' },
    ats: { label: 'Spread', url: 'spread', head: 'W-L-P', pctHead: 'Cover %' },
    tot: { label: 'O/U', url: 'total', head: 'W-L-P', pctHead: 'Over %', pair: ['O', 'U'] },
    btts: { label: 'BTTS', url: 'btts', head: 'W-L', pctHead: 'Yes %', pair: ['Y', 'N'] },
    rfi: { label: 'NRFI', url: 'nrfi', head: 'N-Y', pctHead: 'NRFI %', pair: ['N', 'Y'] },
  };

  function create(src) {
    var REG = (window.RTYB_SPLITS || {})[src.sport];
    if (!REG) return null;
    // groups marked hidden (NHL's Goalie, until the starter / backup data is
    // checked) stay off every page: the Stats page, team pages, game log tags
    var HIDDEN = {};
    REG.groups.forEach(function(G) { if (G.hidden) HIDDEN[G.id] = 1; });
    if (Object.keys(HIDDEN).length) {
      REG = Object.assign({}, REG, { groups: REG.groups.filter(function(G) { return !HIDDEN[G.id]; }),
                                     rows: REG.rows.filter(function(r) { return !HIDDEN[r.group]; }) });
    }
    var C = REG.config || {};
    var markets = (REG.markets || ['su', 'ats', 'tot']).map(function(m) {
      var id = typeof m === 'string' ? m : m.id;
      var base = MARKETS[id] || {};
      var o = {}; for (var x in base) o[x] = base[x];
      if (typeof m === 'object') for (var y in m) o[y] = m[y];
      o.id = id;
      return o;
    });
    var RIVAL = {};
    (src.rivals || []).forEach(function(p) { RIVAL[p[0] + '|' + p[1]] = RIVAL[p[1] + '|' + p[0]] = 1; });
    function isRival(a, b) { return !!RIVAL[a + '|' + b]; }
    var memberOf = null;
    function confOf(slug) {
      var m = (src.conf || {}).members;
      if (m) {
        if (!memberOf) { memberOf = {}; Object.keys(m).forEach(function(c) { m[c].forEach(function(s) { memberOf[s] = c; }); }); }
        return memberOf[slug] || null;
      }
      return (src.teams[slug] || {}).conference || null;
    }
    function isP4(slug) {
      var cf = src.conf || {}, c = confOf(slug);
      return (cf.power4 || []).indexOf(c) !== -1 || (cf.power4_teams || []).indexOf(slug) !== -1;
    }
    function isPower(slug) { return ((src.conf || {}).power || []).indexOf(confOf(slug)) !== -1; }
    function fgLine(g, side) { return g.fs == null ? null : side === 'home' ? g.fs : -g.fs; }
    function mlFav(ml) {
      ml = ml || {};
      if (typeof ml.away !== 'number' || typeof ml.home !== 'number' || ml.away === ml.home) return null;
      return implied(ml.away) > implied(ml.home) ? 'away' : 'home';
    }
    // the favorite, by the registry's rule: 'seg-ml' = the segment's own
    // moneyline, else the full-game one; 'fg-ml' = the full-game moneyline
    function fullFav(g, k) {
      if (REG.favBy === 'seg-ml') return mlFav(((g.odds || {})[k] || {}).ml) || mlFav(g.fml);
      if (REG.favBy === 'fg-ml') return mlFav(g.fml);
      if (REG.favBy === 'fg-spread') return g.fs ? (g.fs < 0 ? 'home' : 'away') : null;
      // football: the segment's own line, else the full-game spread
      return segFav((g.odds || {})[k]) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null);
    }

    var cache = {}, todayCtx = {}, upcoming = {};
    // [{c, r}] for one season's games in segment k
    function seasonContexts(games, k, seasonKey) {
      var dates = Object.keys(games).sort();
      var byTeam = {};
      dates.forEach(function(d) {
        games[d].forEach(function(g) {
          if (g.state === 'postponed' || g.state === 'canceled') return;
          ['away', 'home'].forEach(function(side) { (byTeam[g[side]] = byTeam[g[side]] || []).push({ g: g, side: side, date: etDate(g.start) }); });
        });
      });
      var info = {};
      Object.keys(byTeam).forEach(function(slug) {
        var list = byTeam[slug].sort(function(a, b) { return a.g.start < b.g.start ? -1 : 1; });
        var w = 0, l = 0, streak = 0, trip = 0, starts = {};
        list.forEach(function(e, i) {
          var p = list[i - 1], n = list[i + 1], prev = null;
          if (p && p.g.state === 'final' && p.g.as != null && p.g.hs != null) {
            var pf = p.side === 'away' ? p.g.as : p.g.hs, pa = p.side === 'away' ? p.g.hs : p.g.as, pe = etParts(p.g.start);
            var pr = (p.g.res || {})[k];
            prev = { res: pf > pa ? 'W' : pf < pa ? 'L' : 'T', pf: pf, pa: pa, side: p.side, dow: pe.dow, mins: pe.mins,
                     ot: !!p.g.ot || Math.max((p.g.als || []).length, (p.g.hls || []).length) > (REG.periods || 4),
                     otType: typeof p.g.ot === 'string' ? p.g.ot : '', neutral: !!p.g.neutral,
                     fs: fgLine(p.g, p.side), rival: isRival(p.g.away, p.g.home),
                     scoredFirst: p.g.firstGoal ? p.g.firstGoal === p.side : null,
                     segRes: pr && pr.su ? (p.side === 'away' ? pr.su : flip(pr.su)) : null,
                     venue: p.g.home };
          }
          var three = 1;
          for (var j = i - 1; j >= 0 && dayDiff(list[j].date, e.date) <= 3; j--) three++;
          var mine = e.side === 'away' ? e.g.ag : e.g.hg;
          var top = null, best = 0;
          Object.keys(starts).forEach(function(id) { if (starts[id] > best) { best = starts[id]; top = id; } });
          info[e.g.id + '|' + slug] = {
            prev: prev, days: p ? dayDiff(p.date, e.date) : null, threeIn4: three >= 3,
            nextDays: n ? dayDiff(e.date, n.date) : null,
            prevWk: p ? regWeek(p.g) : null, nextWk: n ? regWeek(n.g) : null,
            next: n ? { rival: isRival(n.g.away, n.g.home), oppRank: n.side === 'away' ? n.g.hr : n.g.ar } : null,
            w: w, l: l, streak: streak,
            trip: e.side === 'away' ? trip + 1 : 0, tripEnded: e.side === 'home' ? trip : 0,
            goalie: mine ? mine.id : null, starter: mine ? (top == null || String(mine.id) === top) : null
          };
          // after this game: record, streak, road trip, goalie starts
          if (e.g.state === 'final' && e.g.as != null && e.g.hs != null) {
            var my = e.side === 'away' ? e.g.as : e.g.hs, th = e.side === 'away' ? e.g.hs : e.g.as;
            if (my > th) { w++; streak = streak > 0 ? streak + 1 : 1; } else if (my < th) { l++; streak = streak < 0 ? streak - 1 : -1; } else streak = 0;
          }
          trip = e.side === 'away' ? trip + 1 : 0;
          if (mine && mine.id != null) starts[mine.id] = (starts[mine.id] || 0) + 1;
        });
      });
      var out = [], today = [];
      dates.forEach(function(d) {
        games[d].forEach(function(g) {
          var r = (g.res || {})[k];
          var pending = seasonKey === 'current' && g.state !== 'final' && g.state !== 'postponed' && g.state !== 'canceled' && !!g.start;
          var isToday = !!src.today && pending && etDate(g.start) === src.today;
          var done = r && r.sc && !r.na;
          if (!done && !pending) return;
          var fav = fullFav(g, k), et = etParts(g.start), o = (g.odds || {})[k] || {}, date = etDate(g.start);
          var segTotal = (o.total || {}).line;
          ['away', 'home'].forEach(function(side) {
            var team = g[side], opp = side === 'away' ? g.home : g.away, i = side === 'away' ? 0 : 1;
            var mi = info[g.id + '|' + team] || {}, oi = info[g.id + '|' + opp] || {};
            var fml = (g.fml || {})[side];
            var tzPrev = mi.prev && src.tz ? src.tz[mi.prev.venue] : null, tzNow = src.tz ? src.tz[g.home] : null;
            var c = { g: g, season: seasonKey, side: side, team: team, opp: opp, home: side === 'home', neutral: !!g.neutral, intl: g.intl,
              fav: fav ? fav === side : null, favMl: typeof fml === 'number' ? fml : null,
              dow: et.dow, mins: et.mins, month: +date.slice(5, 7), date: date,
              ti: src.teams[team] || null, oi: src.teams[opp] || null,
              wk: regWeek(g), prevWk: mi.prevWk, nextWk: mi.nextWk, prev: mi.prev, oppPrev: oi.prev, next: mi.next,
              rest: mi.days, oppRest: oi.days,
              restDays: mi.days == null ? null : mi.days - 1, oppRestDays: oi.days == null ? null : oi.days - 1,
              b2b: mi.days === 1, b2bFirst: mi.nextDays === 1, oppB2b: oi.days === 1,
              threeIn4: !!mi.threeIn4, trip: mi.trip || 0, tripEnded: mi.tripEnded || 0,
              tzCrossed: tzPrev != null && tzNow != null ? Math.abs(tzPrev - tzNow) : null,
              w: mi.w || 0, l: mi.l || 0, streak: mi.streak || 0, oppW: oi.w || 0, oppL: oi.l || 0,
              rank: side === 'away' ? g.ar : g.hr, oppRank: side === 'away' ? g.hr : g.ar,
              fs: fgLine(g, side), segTotal: typeof segTotal === 'number' ? segTotal : null, cuts: (src.totalCuts || {})[k] || null,
              tvn: !!g.tvn, note: g.note || '', post: !!g.post,
              goalie: mi.goalie, starter: mi.starter,
              teamConf: confOf(team), oppConf: confOf(opp), oppFcs: !src.teams[opp], oppP4: isP4(opp),
              teamPower: isPower(team), oppPower: isPower(opp), rival: isRival(g.away, g.home) };
            if (isToday) today.push({ c: c });
            if (pending) upcoming[k + '|' + g.id + '|' + team] = c;
            if (!done) return;
            var res = { margin: r.sc[i] - r.sc[1 - i], lined: !!(o.ats || o.total || o.ml || o.btts) };
            var u = r.u || {};
            if (r.su && r.su !== 'NA') {
              res.su = side === 'away' ? r.su : flip(r.su);
              if (res.su === 'P') res.su = 'T';
              res.suU = u.su ? u.su[i] : null;
              res.ml3 = res.su === 'W' ? 'W' : 'L';
              res.ml3Tie = res.su === 'T';
              res.ml3U = u.ml3 ? u.ml3[i] : null;
            }
            if (r.ats && r.ats !== 'NA') {
              res.ats = side === 'away' ? r.ats : flip(r.ats);
              res.atsU = u.ats ? u.ats[i] : fbU(res.ats === 'P' ? 'T' : res.ats);
            }
            if (r.tot && r.tot !== 'NA') {
              res.tot = r.tot;
              res.totA = u.tot ? u.tot[0] : (o.total ? fbU({ O: 'W', U: 'L' }[r.tot]) : null);
              res.totB = u.tot ? u.tot[1] : (o.total ? fbU({ O: 'L', U: 'W' }[r.tot]) : null);
            }
            if (r.btts) {
              res.btts = r.btts;
              res.bttsA = u.btts ? u.btts[0] : null;
              res.bttsB = u.btts ? u.btts[1] : null;
            }
            if (r.rfi === 'Y' || r.rfi === 'N') {   // u.rfi = [YRFI, NRFI]
              res.rfi = r.rfi;
              res.rfiA = u.rfi ? u.rfi[1] : null;
              res.rfiB = u.rfi ? u.rfi[0] : null;
            }
            out.push({ c: c, r: res });
          });
        });
      });
      if (seasonKey === 'current') todayCtx[k] = today;
      return out;
    }
    function contexts(k, mode) {
      var key = k + '|' + mode;
      if (cache[key]) return cache[key];
      var out = [];
      src.seasons.forEach(function(s) {
        if (s.key === 'prev' && mode !== 'since') return;
        if (!s.games) return;
        out = out.concat(seasonContexts(s.games, k, s.key));
      });
      return (cache[key] = out);
    }

    function agg(list, ms) {
      ms = ms || markets;
      var a = { gp: 0, lined: 0, games: 0 }, seen = {};
      ms.forEach(function(m) { a[m.id] = { a: 0, b: 0, p: 0, d: 0, n: 0, ua: 0, ub: 0, na: 0, nb: 0 }; });
      list.forEach(function(e) {
        var r = e.r;
        a.gp++; if (r.lined) a.lined++;
        if (!seen[e.c.g.id]) { seen[e.c.g.id] = 1; a.games++; }
        ms.forEach(function(m) {
          var x = a[m.id], v = r[m.id];
          if (v == null) return;
          x.n++;
          if (m.pair) {
            if (v === m.pair[0]) x.a++; else if (v === m.pair[1]) x.b++; else x.p++;
            var ua = r[m.id + 'A'], ub = r[m.id + 'B'];
            if (ua != null) { x.ua += ua; x.na++; }
            if (ub != null) { x.ub += ub; x.nb++; }
          } else {
            if (v === 'W') x.a++; else if (v === 'L') x.b++; else x.p++;
            if (r[m.id + 'Tie']) x.d++;
            var u = r[m.id + 'U'];
            if (u != null) { x.ua += u; x.na++; }
          }
        });
      });
      return a;
    }
    function table(k, view, mode) {
      var all = contexts(k, mode);
      var pool = view.mode === 'team' ? all.filter(function(e) { return e.c.team === view.slug && e.c.season === 'current'; })
        : view.conf ? all.filter(function(e) { return e.c.teamConf === view.conf; }) : all;
      // the Splits page's time filter: {from, to} dates, a league week (wk), or none
      var R = view.range;
      if (R) pool = R.none ? [] : pool.filter(function(e) {
        return R.post != null ? !!e.c.g.post === R.post : R.wk ? e.c.g.wk === R.wk : e.c.date >= R.from && e.c.date <= R.to;
      });
      return REG.groups.map(function(gr) {
        var rows = [], hidden = [];
        REG.rows.forEach(function(row) {
          if (row.group !== gr.id) return;
          if (view.mode === 'league' && row.teamOnly) return;
          if (view.mode === 'team' && row.applies && !row.applies(view.slug, C)) return;
          var list = pool.filter(function(e) {
            if (view.mode === 'league' && !row.own && !view.conf) {
              if (view.persp === 'fav' ? e.c.fav !== true : !e.c.home) return false;
            }
            return !!row.test(e.c, C);
          });
          var a = agg(list);
          // rows with fewer than 5 games stay hidden ("Not yet" on the league table)
          if (a.gp >= 5) rows.push({ row: row, agg: a });
          else if (a.gp && view.mode === 'league') hidden.push(row);
        });
        return { group: gr, rows: rows, hidden: hidden };
      }).filter(function(x) { return x.rows.length; });
    }
    // rows a team's upcoming game fits (the team page's "Tonight" spots)
    function nextFits(k, slug, gameId) {
      contexts(k, 'current');
      var c = upcoming[k + '|' + gameId + '|' + slug];
      if (!c) return [];
      return REG.rows.filter(function(row) {
        if (row.id === 'overall') return false;
        if (row.applies && !row.applies(slug, C)) return false;
        return !!row.test(c, C);
      });
    }
    // the rows a team's upcoming game fits (shown rows only: 5+ games) that
    // are real edges in one market -- the hub's Team to Watch: edge 1 = in
    // the team's favor, -1 = against it (the team page's 60% / 40% over 10+
    // games, or more than 5 units either way)
    // a row's name: a string, or a function of the segment's total cuts ("Low total (under 221.5)")
    function lab(row, k) { return typeof row.label === 'function' ? row.label(C, { cuts: (src.totalCuts || {})[k] }) : row.label; }
    function spots(k, slug, gameId, marketId) {
      var fit = {}, out = [];
      nextFits(k, slug, gameId).forEach(function(r) { fit[r.id] = 1; });
      var m = markets.filter(function(x) { return x.id === marketId; })[0] || markets[0];
      table(k, { mode: 'team', slug: slug }, 'current').forEach(function(G) {
        G.rows.forEach(function(x) {
          if (!fit[x.row.id]) return;
          var a = x.agg[m.id], d = a.a + a.b, u = m.pair ? Math.max(a.ua, a.ub) : a.ua, edge = 0;
          if ((m.pair ? a.na || a.nb : a.na) && Math.abs(u) > 5) edge = u > 0 ? 1 : -1;
          else if (d >= 10) edge = a.a / d >= 0.6 ? 1 : a.a / d <= 0.4 ? -1 : 0;
          if (edge) out.push({ label: lab(x.row, k), rec: a.a + '-' + a.b + (a.p ? '-' + a.p : ''), pct: d ? a.a / d : null, edge: edge });
        });
      });
      return out;
    }
    // the league table's standout row (the Stats Overview's Splits teaser and
    // the hub's Number): 10+ decided games, furthest from 50% in the first market
    function standout(k) {
      var m = markets[0], best = null;
      merged(table(k, { mode: 'league', persp: 'home' }, 'current')).forEach(function(G) {
        G.rows.forEach(function(x) {
          if (x.row.id === 'overall') return;
          var a = x.agg[m.id], d = a.a + a.b;
          if (d < 10) return;
          var sc = Math.abs(a.a / d - 0.5);
          if (!best || sc > best.sc) best = { sc: sc, label: lab(x.row, k), short: x.row.short, rec: a.a + '-' + a.b + (m.pair || m.id === 'ml3' ? '' : '-' + a.p),
                                              pct: Math.round(100 * a.a / d), market: m.label, pctHead: m.pctHead, own: !!x.row.own };
        });
      });
      return best;
    }
    function tags(c) {
      var skip = { overall: 1, home: 1, away: 1 }, out = [], rows = REG.rows;
      rows.forEach(function(row, i) {
        if (skip[row.id] || row.teamOnly || !row.test(c, C)) return;
        if (row.applies && !row.applies(c.team, C)) return;
        if (!row.indent) { for (var j = i + 1; j < rows.length && rows[j].indent; j++) if (rows[j].test(c, C)) return; }
        out.push(row.short);
      });
      return out;
    }

    // ---- state, URL ----
    var st = { k: null, market: null, persp: 'home', conf: '', mob: null, tonightOnly: false };
    if (src.url) {
      try {
        var q = new URLSearchParams(window.location.search);
        if (q.get('segment')) st.k = q.get('segment');
        if (q.get('market')) markets.forEach(function(m) { if (m.url === q.get('market')) st.market = m.id; });
      } catch (e) {}
    }
    function saveUrl() {
      if (!src.url) return;
      try {
        var u = new URL(window.location.href);
        if (src.segments.length > 1) u.searchParams.set('segment', st.k);
        u.searchParams.set('market', (markets.filter(function(m) { return m.id === st.market; })[0] || markets[0]).url);
        u.searchParams.delete('season');
        history.replaceState(null, '', u.toString());
      } catch (e) {}
    }

    // The Stats page's groups (Chris's spec): every registry group maps to
    // one of these, in this order; spread-size rows sit in Matchup.
    var GROUP_OF = { ha: 'Matchup', spread: 'Matchup', opp: 'Opponent', rank: 'Opponent', tip: 'Start time', drop: 'Start time',
                     ko: 'Start time', rest: 'Rest', prev: 'Previous game', goalie: 'Goalie', size: 'Total size' };
    var GROUP_ORDER = ['Matchup', 'Opponent', 'Start time', 'Rest', 'Previous game', 'Goalie', 'Total size'];
    function merged(groups) {
      var by = {}, extra = [];
      groups.forEach(function(G) {
        var name = GROUP_OF[G.group.id] || G.group.label;
        if (GROUP_ORDER.indexOf(name) === -1 && extra.indexOf(name) === -1) extra.push(name);
        var m = by[name] = by[name] || { name: name, rows: [], hidden: [], notes: [] };
        m.rows = m.rows.concat(G.rows); m.hidden = m.hidden.concat(G.hidden);
        if (G.group.note) m.notes.push(G.group.note);
      });
      return GROUP_ORDER.concat(extra).filter(function(n) { return by[n]; }).map(function(n) { return by[n]; });
    }

    function render(box, view) {
      if (!box) return;
      var k = st.k && src.segments.some(function(s) { return s.key === st.k; }) ? st.k : src.segments[0].key;
      st.k = k;
      if (!st.market || !markets.some(function(m) { return m.id === st.market; })) st.market = markets[0].id;
      var mode = 'current';
      var conf = view.mode === 'league' && REG.conferences ? st.conf : '';
      var v = view.mode === 'league' ? { mode: 'league', persp: st.persp, conf: conf, range: view.range } : view;
      var groups = merged(table(k, v, mode));
      var league = view.mode === 'league';
      // team view: the rows the team's next game fits ("Tonight")
      var FIT = {}, fits = !league && view.next ? nextFits(k, view.slug, view.next.id) : [];
      fits.forEach(function(r) { FIT[r.id] = 1; });
      var shownIds = {};
      groups.forEach(function(G) { G.rows.forEach(function(x) { shownIds[x.row.id] = 1; }); });
      if (!league && st.tonightOnly && view.next) {
        groups = groups.map(function(G) { return { name: G.name, rows: G.rows.filter(function(x) { return FIT[x.row.id]; }), hidden: [], notes: G.notes }; })
          .filter(function(G) { return G.rows.length; });
      }
      var sel = markets.filter(function(m) { return m.id === st.market; })[0];
      // the one control bar, pinned under the header: segment, market, the
      // page's time range (view.controls), then View as / conference; two
      // rows on phones
      function bar() {
        var b = '';
        if (src.segments.length > 1 && !view.noSeg) b += '<div class="seg-toggle" role="group" aria-label="Segment">' + src.segments.map(function(s) {
          return '<button class="seg-btn" data-sit-seg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>';
        if (markets.length > 1) b += '<div class="seg-toggle" role="group" aria-label="Market">' + markets.map(function(m) {
          return '<button class="seg-btn" data-sit-mk="' + m.id + '" aria-pressed="' + (m.id === st.market) + '">' + esc(m.label) + '</button>'; }).join('') + '</div>';
        var full = '';
        if (league && REG.conferences) full += '<select class="conf-select" data-sit-conf aria-label="Conference"><option value="">' + esc(REG.allLabel || 'All') + '</option>' +
          REG.conferences.map(function(c) { return '<option value="' + esc(c) + '"' + (c === conf ? ' selected' : '') + '>' + esc(((src.conf || {}).short || {})[c] || c) + '</option>'; }).join('') + '</select>';
        if (league && !conf && REG.perspectives) full += '<div class="seg-toggle sit-persp" role="group" aria-label="View as"><span class="control-label">View as</span>' +
          REG.perspectives.map(function(p) { return '<button class="seg-btn" data-sit-persp="' + p[0] + '" aria-pressed="' + (st.persp === p[0]) + '">' + p[1] + '</button>'; }).join('') + '</div>';
        return '<div class="ob-stick sit-stick"><div class="sit-bar"><div class="sit-row1">' + b + '</div><div class="sit-full">' + (view.controls || '') + full + '</div></div></div>';
      }

      function recTxt(m, x) { return x.n ? x.a + '-' + x.b + (m.pair || m.id === 'ml3' ? (x.p ? '-' + x.p : '') : '-' + x.p) : '&mdash;'; }
      // Win % leaves ties and pushes out (2-0-4 is 100%), as in template.html /
      // sport.js winPct; Tie % is out of every game played.
      function decided(m, x) { return x.a + x.b; }
      function pctOf(m, x) { var d = decided(m, x); return d ? Math.round(100 * x.a / d) : null; }
      function tieOf(x) { var d = x.a + x.b + x.p; return d ? Math.round(100 * (x.p + (x.d || 0)) / d) : null; }
      var isSu = sel.id === 'ml3';   // Tie %: the 3-way view only
      // the units shown: the market's own, or the better side of a pair
      function unitsPick(m, x) {
        if (!m.pair) return { u: x.ua, n: x.na, pre: '' };
        if (!x.na && !x.nb) return { u: 0, n: 0, pre: '' };
        var useA = x.na && (!x.nb || x.ua >= x.ub);
        return useA ? { u: x.ua, n: x.na, pre: m.pair[0] + ' ' } : { u: x.ub, n: x.nb, pre: m.pair[1] + ' ' };
      }
      // a real edge: a 60%+ (or 40% and under) win / cover rate over 10+
      // games, ties and pushes left out, or units beyond +/-5;
      // 1 = green, -1 = red, 0 = neutral gray
      function edgeOf(m, x) {
        var d = x.a + x.b, up = unitsPick(m, x);
        if (up.n && Math.abs(up.u) > 5) return up.u > 0 ? 1 : -1;
        if (d >= 10) { var p = 100 * x.a / d; return p >= 60 ? 1 : p <= 40 ? -1 : 0; }
        return 0;
      }
      function unitsOf(m, x, tone) {
        if (m.pair && REG.pairUnits === 'both' && (x.na || x.nb)) return '<span class="sit-both">' + pill(x.ua, x.na, m.pair[0] + ' ', tone) + pill(x.ub, x.nb, m.pair[1] + ' ', tone) + '</span>';
        var up = unitsPick(m, x);
        return pill(up.u, up.n, up.pre, tone);
      }
      var PER_TEAM = false;
      function perTeam(a) { if (a.gp > a.games) { PER_TEAM = true; return '<sup class="st-mark">*</sup>'; } return ''; }
      var TONIGHT_TAG = '<span class="sit-tn">Tonight</span>';
      function labelCell(row, a, tone) {
        return '<td class="sit-label' + (row.indent ? ' ind' : '') + '"><span class="sit-name">' + esc(lab(row, k)) + '</span>' + (FIT[row.id] ? ' ' + TONIGHT_TAG : '') +
          (a.gp && a.gp < (REG.smallSample || 10) ? ' <span class="sit-small">Small sample</span>' : '') + '</td>';
      }
      function cells(row, a) {
        var x0 = a[sel.id], p = pctOf(sel, x0), tone = edgeOf(sel, x0);
        var mark = a.gp && a.lined < a.gp ? '<sup class="st-mark">&dagger;</sup>' : '';
        if (a.gp && a.lined < a.gp) MARKED = true;
        var h = labelCell(row, a, tone) + '<td class="num mono">' + (a.gp || '&mdash;') + perTeam(a) + '</td>';
        h += '<td class="num mono sit-sel">' + recTxt(sel, x0) + mark + '</td>' +
          '<td class="num"><div class="pct-cell' + (tone > 0 ? ' edge-pos' : tone < 0 ? ' edge-neg' : '') + '"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div></td>' +
          (isSu ? '<td class="num mono">' + (tieOf(x0) == null ? '&mdash;' : tieOf(x0) + '%') + '</td>' : '') +
          '<td class="num">' + unitsOf(sel, x0, tone) + '</td>';
        return h;
      }
      var MARKED = false;
      var ncol = 5 + (isSu ? 1 : 0);
      // fixed column widths, so every group's card lines up
      var cols = '<colgroup><col class="sc-l"><col class="sc-gp"><col class="sc-rec"><col class="sc-pct">' + (isSu ? '<col class="sc-tie">' : '') + '<col class="sc-u"></colgroup>';
      var thead = '<tr><th class="sit-label">Split</th><th class="num">GP</th><th class="num">' + esc(sel.head) + '</th><th class="num">' + esc(sel.pctHead) +
        '</th>' + (isSu ? '<th class="num">Tie %</th>' : '') + '<th class="num">Units</th></tr>';
      function mobRows(G) {
        return G.rows.map(function(x) {
          var a = x.agg, x0 = a[sel.id], p = pctOf(sel, x0), tone = edgeOf(sel, x0);
          return '<details class="sit-mrow' + (FIT[x.row.id] ? ' sit-on' : '') + '" id="sit-m-' + esc(x.row.id) + '"><summary><span class="sit-mlabel' + (x.row.indent ? ' ind' : '') + '">' + esc(x.row.short) + (FIT[x.row.id] ? ' ' + TONIGHT_TAG : '') +
              (a.gp && a.gp < (REG.smallSample || 10) ? ' <span class="sit-small">Small</span>' : '') + '</span>' +
            '<span class="mono sit-mrec">' + recTxt(sel, x0) + '</span><span class="sit-mval">' + (sel.id === 'su' ? '<span class="mono">' + (p == null ? '&mdash;' : p + '%') + '</span>' : unitsOf(sel, x0, tone)) +
            '</span><span class="sit-chev" aria-hidden="true">&#9662;</span></summary>' +
            '<div class="sit-mbody"><p class="sit-mname">' + esc(lab(x.row, k)) + '</p>' +
              '<div class="pct-cell' + (tone > 0 ? ' edge-pos' : tone < 0 ? ' edge-neg' : '') + '"><div class="pct-bar"><span style="width:' + (p || 0) + '%"></span></div><span class="pct-num mono">' + (p == null ? '&mdash;' : p + '%') + '</span></div>' +
              '<div class="sit-m3">' + markets.map(function(m) { var xx = a[m.id]; return '<div><b>' + esc(m.label) + '</b><span class="mono">' + recTxt(m, xx) + '</span>' + unitsOf(m, xx, edgeOf(m, xx)) + '</div>'; }).join('') + '</div>' +
              '<div class="sit-mfoot">' + a.gp + (a.gp > a.games ? ' team-games' : ' game' + (a.gp === 1 ? '' : 's')) + (a.lined < a.gp ? '<sup class="st-mark">&dagger;</sup>' : '') + '</div></div></details>';
        }).join('');
      }
      var tip = esc(REG.foot || 'Records count every game; units count only games with saved closing odds, 1 unit at the closing price (spreads and totals at -110 when only the line was saved).') +
        ' Small sample: under ' + (REG.smallSample || 10) + ' games; rows under 5 games stay hidden. ' +
        '&ldquo;Per team&rdquo; rows count each team&rsquo;s game, so one game can count twice. Green and red mark real edges: 60%+ (or 40% and under) over 10+ games, or more than 5 units either way.';
      var html = '<div class="st-sec sit"><div class="st-sec-head"><h2>Situational Results <button type="button" class="info-tip" aria-label="About Situational Results" data-tip-title="Situational Results">i<span class="tip-bubble" role="tooltip">' + tip + '</span></button></h2>' +
        '</div>' + bar() + (view.line || '') +
        (st.comboMsg ? '<p class="sit-combo">Combining filters is a Premium feature: one at a time for now.</p>' : '');
      if (!league && view.next) {
        var tonightLocked = src.tonightLocked && src.tonightLocked();
        html += '<div class="sit-spots"><p><b>' + esc(view.next.label) + ':</b> ' + (fits.length ? fits.map(function(r) {
            return shownIds[r.id] ? '<a href="#sit-r-' + esc(r.id) + '" data-sit-jump="' + esc(r.id) + '">' + esc(r.short) + '</a>' : esc(r.short);
          }).join(' &middot; ') : 'no situations yet') + '</p>' +
          '<button type="button" class="seg-btn sit-tonly" data-sit-tonight aria-pressed="' + st.tonightOnly + '"' + (tonightLocked ? ' disabled title="Premium"' : '') + '>Tonight only' + (tonightLocked ? ' &#128274;' : '') + '</button></div>';
      }
      if (!groups.length) html += '<div class="sit-notyet">' + (st.tonightOnly ? 'None of tonight&rsquo;s situations has 5+ games yet.' : 'No games in these splits yet.') + '</div>';
      html += groups.map(function(G) {
        var id = 'sit-g-' + G.name.toLowerCase().replace(/[^a-z]+/g, '-');
        var tbl = '<div class="sit-desk' + (REG.mobileList ? '' : ' sit-scroll') + '"><div class="sit-wrap"><table class="sit-table">' + cols + '<thead>' + thead + '</thead><tbody>' +
          G.rows.map(function(x) { return '<tr id="sit-r-' + esc(x.row.id) + '"' + (FIT[x.row.id] ? ' class="sit-on"' : '') + '>' + cells(x.row, x.agg) + '</tr>'; }).join('') +
          (G.hidden.length ? '<tr class="sit-notyet"><td colspan="' + ncol + '">Not yet: ' + G.hidden.map(function(r) { return esc(lab(r, k)); }).join(' &middot; ') + '</td></tr>' : '') +
          '</tbody></table></div></div>';
        var mob = REG.mobileList ? '<div class="sit-mob">' + mobRows(G) +
          (G.hidden.length ? '<div class="sit-notyet">Not yet: ' + G.hidden.map(function(r) { return esc(r.short); }).join(' &middot; ') + '</div>' : '') + '</div>' : '';
        return '<section class="st-card sit-gsec" id="' + id + '"><div class="st-head"><h4>' + esc(G.name) + '</h4></div>' + tbl + mob + '</section>';
      }).join('') + (PER_TEAM ? '<p class="st-foot"><sup>*</sup> Per team: each team&rsquo;s game counts, so one game can count twice.</p>' : '') +
        (MARKED ? '<p class="st-foot"><sup>&dagger;</sup> Games without a saved line aren&rsquo;t counted in the units.</p>' : '') + '</div>';
      var locked = league && src.locked && src.locked();
      box.className = 'adv-section' + (locked ? ' locked' : '');
      box.innerHTML = html + (locked && src.lockHtml ? src.lockHtml() : '');
      st.comboMsg = false;
      // every bar changes every section, keeping the clicked section where it was
      function on(sel2, ev, fn) {
        box.querySelectorAll(sel2).forEach(function(el) {
          el['on' + ev] = function() {
            var sec = el.closest('.sit-gsec'), keep = sec ? { id: sec.id, top: sec.getBoundingClientRect().top } : null;
            var was = { persp: st.persp, conf: st.conf };
            var segChange = fn(el);
            // premium: one Splits filter at a time (time range, View as, conference)
            if (league && src.comboLocked && src.comboLocked() && (view.range ? 1 : 0) + (st.persp !== 'home' ? 1 : 0) + (st.conf ? 1 : 0) > 1) {
              st.persp = was.persp; st.conf = was.conf; st.comboMsg = true;
            }
            saveUrl();
            if (segChange && src.onSeg && src.onSeg(st.k, sec) !== false) return;
            render(box, view);
            var again = keep && document.getElementById(keep.id);
            if (again) window.scrollBy(0, again.getBoundingClientRect().top - keep.top);
          };
        });
      }
      on('[data-sit-seg]', 'click', function(b) { st.k = b.getAttribute('data-sit-seg'); return true; });
      on('[data-sit-mk]', 'click', function(b) { st.market = b.getAttribute('data-sit-mk'); });
      on('[data-sit-persp]', 'click', function(b) { st.persp = b.getAttribute('data-sit-persp'); });
      on('[data-sit-conf]', 'change', function(s) { st.conf = s.value; });
      on('[data-sit-tonight]', 'click', function() { st.tonightOnly = !st.tonightOnly; });
      if (view.after) view.after(box);
      // a spot link opens its row (on phones, the row's card) and scrolls to it
      box.querySelectorAll('[data-sit-jump]').forEach(function(a) {
        a.onclick = function(e) {
          var id = a.getAttribute('data-sit-jump'), m = document.getElementById('sit-m-' + id), d = document.getElementById('sit-r-' + id);
          var el = m && m.offsetParent ? m : d;
          if (!el) return;
          e.preventDefault();
          if (el.tagName === 'DETAILS') el.open = true;
          el.scrollIntoView({ block: 'center', behavior: 'smooth' });
        };
      });
    }
    // the How to read box's glossary: every group's rows and what each means
    // (the definitions live here, not under the rows)
    function glossary(k) {
      var notes = [], by = {}, order = [];
      REG.groups.forEach(function(G) { if (G.note) notes.push(G.note); });
      REG.rows.forEach(function(row) {
        if (!row || !row.def || row.teamOnly) return;
        var name = GROUP_OF[row.group] || ((REG.groups.filter(function(G) { return G.id === row.group; })[0] || {}).label) || '';
        if (!by[name]) { by[name] = []; order.push(name); }
        by[name].push('<dt>' + esc(lab(row, k)) + '</dt><dd>' + esc(typeof row.def === 'function' ? row.def(C, { cuts: (src.totalCuts || {})[k] }) : row.def) + '</dd>');
      });
      return '<div class="htr-gloss"><h3>Glossary</h3>' + notes.map(function(n) { return '<p>' + esc(n) + '</p>'; }).join('') +
        order.map(function(n) { return '<h4>' + esc(n) + '</h4><dl>' + by[n].join('') + '</dl>'; }).join('') + '</div>';
    }
    // ---- the team page's Situational Results (Chris's Team page spec):
    // desktop one wide table, SPLIT · GP · a column per market ("54% +1.20u
    // (13-11)"), rows under MATCHUP · OPPONENT · SCHEDULE · BOUNCE-BACK, then
    // the DAY OF WEEK strip; phones: market pills, one market at a time.
    // "All splits" / "Next game" toggle: the rows the next game fits get a dot
    // and bold text, the rest dim. view = {slug, cols: [{k, id, head, short,
    // priced}], segs ([{key, label}] or null), onSeg(k), next ({id, label,
    // dow} or null), note (the line under the title, e.g. "2026 season · final")}
    var TEAM_GROUP = { ha: 'Matchup', spread: 'Matchup', size: 'Matchup', opp: 'Opponent', rank: 'Opponent',
                       tip: 'Schedule', drop: 'Schedule', ko: 'Schedule', rest: 'Schedule', prev: 'Bounce-back' };
    var TEAM_ORDER = ['Matchup', 'Opponent', 'Schedule', 'Bounce-back'];
    var TEAM_SMALL = 8;   // fewer games than this: "small sample"
    var DOW = [[1, 'Mon'], [2, 'Tue'], [3, 'Wed'], [4, 'Thu'], [5, 'Fri'], [6, 'Sat'], [0, 'Sun']];
    var ts = { col: 0, next: false };
    function teamView(box, view) {
      if (!box) return;
      var cols = view.cols.filter(function(c) { return MARKETS[c.id]; });
      if (!cols.length) { box.innerHTML = ''; return; }
      if (ts.col >= cols.length) ts.col = 0;
      var ms = cols.map(function(c) { var o = {}; for (var x in MARKETS[c.id]) o[x] = MARKETS[c.id][x]; o.id = c.id; return o; });
      // the team's games, per segment
      var pools = {};
      cols.forEach(function(c) {
        if (!pools[c.k]) pools[c.k] = contexts(c.k, 'current').filter(function(e) { return e.c.team === view.slug && e.c.season === 'current'; });
      });
      var k0 = cols[0].k;
      var FIT = {};
      if (view.next) nextFits(k0, view.slug, view.next.id).forEach(function(r) { FIT[r.id] = 1; });
      // one aggregate per column: {colIndex: x}
      function aggRow(test) {
        var out = { gp: 0, x: [] };
        cols.forEach(function(c, i) {
          var a = agg(pools[c.k].filter(test), [ms[i]]);
          if (c.k === k0 && !out.gpSet) { out.gp = a.gp; out.gpSet = true; }
          out.x.push(a[c.id]);
        });
        return out;
      }
      function pctOf(x) { var d = x.a + x.b; return d ? Math.round(100 * x.a / d) : null; }
      function recOf(id, x) {
        if (!x.n) return '&mdash;';
        if (id === 'ml3') return x.a + '&ndash;' + (x.b - x.d) + '&ndash;' + x.d;
        if (id === 'su' || id === 'ats') return x.a + '&ndash;' + x.b + '&ndash;' + x.p;
        return x.a + '&ndash;' + x.b;
      }
      function unitsOf(c, x) {
        if (!c.priced || !x.na) return '';
        var r = Math.round(x.ua * 100) / 100;
        return ' <span class="ts-u ' + (r > 0.5 ? 'pos' : r < -0.5 ? 'neg' : 'mid') + '">' + fmtU(r) + '</span>';
      }
      function cellHtml(c, x) {
        var p = pctOf(x);
        if (!x.n) return '<span class="ts-dash">&mdash;</span>';
        return '<span class="ts-pct">' + (p == null ? '&mdash;' : p + '%') + '</span>' + unitsOf(c, x) + ' <span class="ts-rec">(' + recOf(c.id, x) + ')</span>';
      }
      // the rows, in the four groups
      var groups = {};
      REG.rows.forEach(function(row) {
        if (row.id === 'overall') return;
        var name = TEAM_GROUP[row.group];
        if (!name) return;
        if (row.applies && !row.applies(view.slug, C)) return;
        var a = aggRow(function(e) { return !!row.test(e.c, C); });
        if (a.gp < 5) return;   // rows under 5 games stay hidden
        (groups[name] = groups[name] || []).push({ row: row, a: a });
      });
      var names = TEAM_ORDER.filter(function(n) { return groups[n]; });
      var nextOn = ts.next && view.next;
      function rowCls(row) { return nextOn ? (FIT[row.id] ? ' ts-fit' : ' ts-dim') : ''; }
      function nameHtml(row, a) {
        return '<span class="ts-name">' + (nextOn && FIT[row.id] ? '<i class="ts-dot" aria-hidden="true"></i>' : '') + esc(lab(row, k0)) + '</span>' +
          (a.gp < TEAM_SMALL ? '<span class="ts-small">small sample</span>' : '');
      }
      var sel = cols[ts.col];
      function pills(cls) {
        return '<div class="seg-toggle ' + cls + '" role="group" aria-label="Market">' + cols.map(function(c, i) {
          return '<button class="seg-btn" data-ts-col="' + i + '" aria-pressed="' + (i === ts.col) + '">' + esc(c.short) + '</button>'; }).join('') + '</div>';
      }
      var h = '';
      var ctl = '';
      if (view.segs && view.segs.length > 1) ctl += '<div class="seg-toggle" role="group" aria-label="Segment">' + view.segs.map(function(s) {
        return '<button class="seg-btn" data-ts-seg="' + s.key + '" aria-pressed="' + (s.key === k0) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>';
      if (view.next) ctl += '<div class="seg-toggle" role="group" aria-label="Which splits"><button class="seg-btn" data-ts-next="0" aria-pressed="' + !nextOn + '">All splits</button>' +
        '<button class="seg-btn" data-ts-next="1" aria-pressed="' + !!nextOn + '">' + esc(view.next.label) + '</button></div>';
      if (ctl) h += '<div class="ts-ctl">' + ctl + '</div>';
      h += pills('ts-pills-phone');
      if (!names.length) h += '<p class="ts-none">No splits with 5 or more games yet.</p>';
      // desktop: one wide table
      var thead = '<tr><th class="ts-l">Split</th><th class="num">GP</th>' + cols.map(function(c) { return '<th class="num">' + esc(c.head) + '</th>'; }).join('') + '</tr>';
      var body = names.map(function(n) {
        return '<tr class="ts-grp"><th colspan="' + (cols.length + 2) + '"><span class="ts-gl">' + esc(n) + '</span></th></tr>' + groups[n].map(function(x) {
          return '<tr class="ts-row' + rowCls(x.row) + '"><td class="ts-l">' + nameHtml(x.row, x.a) + '</td><td class="num">' + x.a.gp + '</td>' +
            cols.map(function(c, i) { return '<td class="num">' + cellHtml(c, x.a.x[i]) + '</td>'; }).join('') + '</tr>';
        }).join('');
      }).join('');
      if (names.length) h += '<div class="ts-desk"><table class="ts-table"><thead>' + thead + '</thead><tbody>' + body + '</tbody></table></div>';
      // phones: the selected market only
      if (names.length) h += '<div class="ts-mob">' + names.map(function(n) {
        return '<p class="ts-gl">' + esc(n) + '</p><ul class="ts-list">' + groups[n].map(function(x) {
          return '<li class="ts-row' + rowCls(x.row) + '"><span class="ts-lcell">' + nameHtml(x.row, x.a) + '</span><span class="ts-gp">' + x.a.gp + ' GP</span>' +
            '<span class="ts-val">' + cellHtml(sel, x.a.x[ts.col]) + '</span></li>';
        }).join('') + '</ul>';
      }).join('') + '</div>';
      // DAY OF WEEK: Mon-Sun, the selected market, the next game's day highlighted
      var nd = view.next && view.next.dow != null ? view.next.dow : null;
      var strip = DOW.map(function(d) {
        var a = agg(pools[sel.k].filter(function(e) { return e.c.dow === d[0]; }), [ms[ts.col]]), x = a[sel.id], p = pctOf(x);
        return '<div class="ts-day' + (d[0] === nd ? ' ts-today' : '') + '"><span class="ts-dl">' + d[1] + '</span><span class="ts-dp">' + (p == null ? '&mdash;' : p + '%') + '</span>' +
          '<span class="ts-dr">' + (x.n ? '(' + recOf(sel.id, x) + ')' : '') + '</span></div>';
      }).join('');
      h += '<div class="ts-dow"><div class="ts-dow-head"><span class="ts-gl">Day of week</span>' + pills('ts-pills-desk') + '<span class="ts-dow-m">' + esc(sel.head) + '</span></div><div class="ts-strip">' + strip + '</div></div>';
      box.innerHTML = h;
      box.querySelectorAll('[data-ts-col]').forEach(function(b) { b.onclick = function() { ts.col = +b.getAttribute('data-ts-col'); teamView(box, view); }; });
      box.querySelectorAll('[data-ts-next]').forEach(function(b) { b.onclick = function() { ts.next = b.getAttribute('data-ts-next') === '1'; teamView(box, view); }; });
      box.querySelectorAll('[data-ts-seg]').forEach(function(b) { b.onclick = function() { if (view.onSeg) view.onSeg(b.getAttribute('data-ts-seg')); }; });
    }
    // ---- the Splits page (league): the team page's layout. Desktop: one wide
    // table, every market side by side ("% (record)", units in priced
    // columns), rows under MATCHUP · OPPONENT · START TIME · REST · PREVIOUS
    // GAME, then the DAY OF WEEK strip; phones: market pills, GP · % (record)
    // · units. Team rows count each team in the spot; matchup-wide rows
    // (division game, either team off a loss...) count the home team's side.
    // view = {range, controls, line, after(box), segs, onSeg(k)}
    var LEAGUE_GROUP = { ha: 'Matchup', spread: 'Matchup', size: 'Matchup', opp: 'Opponent', rank: 'Opponent',
                         tip: 'Start time', drop: 'Start time', ko: 'Start time', rest: 'Rest', prev: 'Previous game' };
    var LEAGUE_ORDER = ['Matchup', 'Opponent', 'Start time', 'Rest', 'Previous game'];
    // the league's side rows: Home team, Favorite, Team with more rest (their
    // mirrors, Away / Underdog / Tired, say the same thing from the other side)
    var LEAGUE_NAME = { home: 'Home team', fav: 'Favorite', rested: 'Team with more rest', radv: 'Team with more rest', restadv: 'Team with more rest' };
    function leagueSkip(id) { return { away: 1, dog: 1, tired: 1, rdis: 1, restdis: 1 }[id] || /^d\d+$/.test(id); }
    var LEAGUE_EXTRA = [
      { id: 'better', label: 'Better record team', short: 'Better record', group: 'opp', own: true, def: 'The team with the better win % going into the game.',
        test: function(c) { var a = c.w + c.l, b = c.oppW + c.oppL; return a && b && c.w / a > c.oppW / b; } }
    ];
    var lg = { col: 0 };
    function leagueView(box, view) {
      if (!box) return;
      var k = st.k && src.segments.some(function(s) { return s.key === st.k; }) ? st.k : src.segments[0].key;
      st.k = k;
      var conf = REG.conferences ? st.conf : '';
      var pool = contexts(k, 'current');
      if (conf) pool = pool.filter(function(e) { return e.c.teamConf === conf; });
      var R = view.range;
      if (R) pool = R.none ? [] : pool.filter(function(e) {
        return R.post != null ? !!e.c.g.post === R.post : R.wk ? e.c.g.wk === R.wk : e.c.date >= R.from && e.c.date <= R.to;
      });
      var ms = markets.filter(function(m) { return m.label; });
      if (lg.col >= ms.length) lg.col = 0;
      var priced = ms.map(function(m) { return pool.some(function(e) { return e.r[m.id + 'U'] != null || e.r[m.id + 'A'] != null; }); });
      function pctOf(x) { var d = x.a + x.b; return d ? Math.round(100 * x.a / d) : null; }
      function recOf(id, x) {
        if (!x.n) return '&mdash;';
        if (id === 'ml3') return x.a + '&ndash;' + (x.b - x.d) + '&ndash;' + x.d;
        if (id === 'su' || id === 'ats') return x.a + '&ndash;' + x.b + '&ndash;' + x.p;
        return x.a + '&ndash;' + x.b;
      }
      function unitsOf(i, x) {
        if (!priced[i] || !x.na) return '';
        var r = Math.round(x.ua * 100) / 100;
        return ' <span class="ts-u ' + (r > 0.5 ? 'pos' : r < -0.5 ? 'neg' : 'mid') + '">' + fmtU(r) + '</span>';
      }
      function cellHtml(i, x) {
        if (!x.n) return '<span class="ts-dash">&mdash;</span>';
        var p = pctOf(x);
        return '<span class="ts-pct">' + (p == null ? '&mdash;' : p + '%') + '</span>' + unitsOf(i, x) + ' <span class="ts-rec">(' + recOf(ms[i].id, x) + ')</span>';
      }
      var PER = false, groups = {};
      REG.rows.concat(LEAGUE_EXTRA).forEach(function(row) {
        if (row.id === 'overall' || row.teamOnly || leagueSkip(row.id)) return;
        var name = LEAGUE_GROUP[row.group];
        if (!name) return;
        var a = agg(pool.filter(function(e) { return (row.own || e.c.home) && !!row.test(e.c, C); }), ms);
        if (a.gp < 5) return;
        if (a.gp > a.games) PER = true;
        (groups[name] = groups[name] || []).push({ row: row, a: a });
      });
      var names = LEAGUE_ORDER.filter(function(n) { return groups[n]; });
      function nameHtml(row, a) {
        return '<span class="ts-name">' + esc(LEAGUE_NAME[row.id] || lab(row, k)) + (a.gp > a.games ? '<sup class="st-mark">*</sup>' : '') + '</span>' +
          (a.gp < (REG.smallSample || 10) ? '<span class="ts-small">small sample</span>' : '');
      }
      function pills(cls) {
        return '<div class="seg-toggle ' + cls + '" role="group" aria-label="Market">' + ms.map(function(m, i) {
          return '<button class="seg-btn" data-lg-col="' + i + '" aria-pressed="' + (i === lg.col) + '">' + esc(m.label) + '</button>'; }).join('') + '</div>';
      }
      var ctl = '';
      if (src.segments.length > 1) ctl += '<div class="seg-toggle" role="group" aria-label="Segment">' + src.segments.map(function(s) {
        return '<button class="seg-btn" data-lg-seg="' + s.key + '" aria-pressed="' + (s.key === k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>';
      if (REG.conferences) ctl += '<select class="conf-select" data-lg-conf aria-label="Conference"><option value="">' + esc(REG.allLabel || 'All') + '</option>' +
        REG.conferences.map(function(c) { return '<option value="' + esc(c) + '"' + (c === conf ? ' selected' : '') + '>' + esc(((src.conf || {}).short || {})[c] || c) + '</option>'; }).join('') + '</select>';
      var h = '<div class="st-sec sit"><div class="st-sec-head"><h2>Situational Results</h2></div>' +
        '<div class="ob-stick sit-stick"><div class="sit-bar"><div class="sit-row1">' + ctl + '</div><div class="sit-full">' + (view.controls || '') + '</div></div></div>' + (view.line || '');
      h += '<div class="lg-body">' + pills('ts-pills-phone');
      if (!names.length) h += '<p class="ts-none">No splits with 5 or more games yet.</p>';
      var thead = '<tr><th class="ts-l">Split</th><th class="num">GP</th>' + ms.map(function(m) { return '<th class="num">' + esc(m.label) + '</th>'; }).join('') + '</tr>';
      if (names.length) h += '<div class="ts-desk"><table class="ts-table"><thead>' + thead + '</thead><tbody>' + names.map(function(n) {
        return '<tr class="ts-grp"><th colspan="' + (ms.length + 2) + '"><span class="ts-gl">' + esc(n) + '</span></th></tr>' + groups[n].map(function(x) {
          return '<tr class="ts-row"><td class="ts-l">' + nameHtml(x.row, x.a) + '</td><td class="num">' + x.a.gp + '</td>' +
            ms.map(function(m, i) { return '<td class="num">' + cellHtml(i, x.a[m.id]) + '</td>'; }).join('') + '</tr>';
        }).join('');
      }).join('') + '</tbody></table></div>';
      var sel = ms[lg.col];
      if (names.length) h += '<div class="ts-mob">' + names.map(function(n) {
        return '<p class="ts-gl">' + esc(n) + '</p><ul class="ts-list">' + groups[n].map(function(x) {
          return '<li class="ts-row"><span class="ts-lcell">' + nameHtml(x.row, x.a) + '</span><span class="ts-gp">' + x.a.gp + ' GP</span>' +
            '<span class="ts-val">' + cellHtml(lg.col, x.a[sel.id]) + '</span></li>';
        }).join('') + '</ul>';
      }).join('') + '</div>';
      // DAY OF WEEK: Mon-Sun in the selected market (home team's side)
      var strip = DOW.map(function(d) {
        var x = agg(pool.filter(function(e) { return e.c.home && e.c.dow === d[0]; }), [sel])[sel.id], p = pctOf(x);
        return '<div class="ts-day"><span class="ts-dl">' + d[1] + '</span><span class="ts-dp">' + (p == null ? '&mdash;' : p + '%') + '</span>' +
          '<span class="ts-dr">' + (x.n ? '(' + recOf(sel.id, x) + ')' : '') + '</span></div>';
      }).join('');
      h += '<div class="ts-dow"><div class="ts-dow-head"><span class="ts-gl">Day of week</span>' + pills('ts-pills-desk') + '<span class="ts-dow-m">' + esc(sel.pctHead || '') + '</span></div><div class="ts-strip">' + strip + '</div></div></div>';
      h += '<p class="st-foot">Team rows count each team in the spot' + (PER ? ' (<sup>*</sup> one game can count twice)' : '') + '; matchup-wide rows and the day strip count the home team&rsquo;s side. Units count games with a saved price.</p></div>';
      var locked = src.locked && src.locked();
      box.className = 'adv-section' + (locked ? ' locked' : '');
      box.innerHTML = h + (locked && src.lockHtml ? src.lockHtml() : '');
      box.querySelectorAll('[data-lg-col]').forEach(function(b) { b.onclick = function() { lg.col = +b.getAttribute('data-lg-col'); leagueView(box, view); }; });
      box.querySelectorAll('[data-lg-seg]').forEach(function(b) { b.onclick = function() { st.k = b.getAttribute('data-lg-seg'); if (!(src.onSeg && src.onSeg(st.k, null) !== false)) leagueView(box, view); }; });
      var cs = box.querySelector('[data-lg-conf]');
      if (cs) cs.onchange = function() { st.conf = cs.value; saveUrl(); leagueView(box, view); };
      if (view.after) view.after(box);
    }
    return { render: render, team: teamView, league: leagueView, glossary: glossary, contexts: function(k, mode) { return contexts(k, mode || 'current'); }, tags: tags, nextFits: nextFits, spots: spots, standout: standout,
             markets: markets, reg: REG, state: st };
  }
  window.RTYBSit = { create: create, etParts: etParts };
})();
