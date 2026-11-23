/*
 * Matchups, Stats, Trends and team pages for every sport except NHL (NHL's
 * pages run their own code in template.html). Reads {slug}/data.json,
 * written by scripts/sport_build.py, and renders into #sportApp:
 *   <div id="sportApp" data-section="games|stats|trends|odds|team" data-team="slug">
 *
 * Wording rules: the straight-up market is "SU" (never "ML"); records are
 * ATS W-L-P, SU W-L-T, O-U-P. Anything that needs odds counts only games
 * with odds and says "based on N games with odds".
 */
(function() {
  'use strict';
  var app = document.getElementById('sportApp');
  if (!app) return;
  var ROOT = (document.currentScript && document.currentScript.src || '').replace(/assets\/sport\.js.*$/, '');
  var SPORT_SLUG = document.body.getAttribute('data-sport-slug');
  // the build's code version (scripts/build_site.py js_version) on every data
  // fetch, so new code never reads a data file cached from before the deploy
  var VER = ((document.currentScript && document.currentScript.src || '').match(/[?&]v=(\w+)/) || [])[1] || '';
  function dataUrl(path) { return ROOT + path + (VER ? (path.indexOf('?') === -1 ? '?' : '&') + 'v=' + VER : ''); }
  var SECTION = app.getAttribute('data-section');
  var TEAM = app.getAttribute('data-team');
  var D = null;
  // The selected segment pill (1st Quarter / 1st Half / ...). Every page
  // load starts on the sport's first segment -- its order in
  // scripts/sports.py, 1st Quarter first -- and nothing is remembered
  // between visits, so a new sport gets the right default automatically.
  // A ?seg= in the URL (a game card's trend link) picks it for this load.
  var SEG_CUR = new URLSearchParams(location.search).get('seg');

  // ---------------------------------------------------------------- utils
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function todayET() {
    var p = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    var o = {}; p.forEach(function(x) { o[x.type] = x.value; });
    return o.year + '-' + o.month + '-' + o.day;
  }
  function dateLabel(d) {
    var t = todayET();
    if (d === t) return 'Today';
    var dt = new Date(d + 'T12:00:00Z');
    var y = new Date(dt.getTime() - 864e5).toISOString().slice(0, 10);
    var n = new Date(new Date(t + 'T12:00:00Z').getTime() - 864e5).toISOString().slice(0, 10);
    if (d === n) return 'Yesterday';
    return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
  }
  function timeET(iso) {
    if (!iso) return '';
    var t = new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) + ' ET';
    // Week view lists several days, so say which one.
    if (D && D.schedule === 'week') {
      t = new Date(iso).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' }) + ' · ' + t;
    }
    return t;
  }
  function signed(n) { return n == null ? '' : (n > 0 ? '+' : '') + n; }
  function fmtUnits(u) { var r = Math.round(u * 100) / 100; return (r > 0 ? '+' : '') + r.toFixed(2) + 'u'; }
  function unitsPill(u, priced) {
    if (!priced) return '<span class="u-pill u-none">-</span>';
    var r = Math.round(u * 100) / 100;
    var cls = r >= 3 ? 'u-pos2' : r > 0.5 ? 'u-pos1' : r < -3 ? 'u-neg2' : r < -0.5 ? 'u-neg1' : 'u-mid';
    return '<span class="u-pill ' + cls + '">' + fmtUnits(r) + '</span>';
  }
  // green above +0.5u, red below -0.5u, yellow between (CLAUDE.md color rule)
  function unitCls(u) { var r = Math.round(u * 100) / 100; return r > 0.5 ? 'pos' : r < -0.5 ? 'neg' : 'mid'; }
  function pct(w, l) { return (w + l) ? Math.round(1000 * w / (w + l)) / 10 : null; }
  function pctTxt(w, l) { var p = pct(w, l); return p == null ? '-' : p.toFixed(1) + '%'; }
  // Win % leaves ties and pushes out (Favorites 2-0-4 is 100%); Tie % is out
  // of every game played. Same rule as winPct in template.html (NHL).
  function winPct(w, l, t) { var n = w + l; return n ? w / n : null; }
  function tiePct(w, l, t) { var n = w + l + (t || 0); return n ? (t || 0) / n : null; }
  function pct1(x) { return x == null ? null : Math.round(1000 * x) / 10; }
  function suPctTxt(r) { var p = pct1(winPct(r[0], r[1], r[2])); return p == null ? '-' : p.toFixed(1) + '%'; }
  function suTieTxt(r) { var p = pct1(tiePct(r[0], r[1], r[2])); return p == null ? '' : ' <small class="tie-pct">Tie ' + p.toFixed(1) + '%</small>'; }
  function rec(r) { return r ? r[0] + '-' + r[1] + '-' + r[2] : '0-0-0'; }
  // Teams outside the league (non-Division I opponents) have a name and
  // maybe a logo; college ones go by the school name (the nickname dropped)
  function team(slug) {
    if (D.teams[slug]) return D.teams[slug];
    var full = (D.otherTeams || {})[slug] || slug, college = D.sport === 'ncaab' || D.sport === 'ncaaf';
    // one code for the badge and the text next to it (sport_build: otherCodes)
    return { name: full, short: college ? full.replace(/\s+\S+$/, '') || full : full, code: (D.otherCodes || {})[slug] || '', color: null, logo: (D.otherLogos || {})[slug] || null };
  }
  function teamUrl(slug) { return D.teams[slug] ? ROOT + SPORT_SLUG + '/teams/' + (D.sport === 'nhl' ? slug.toLowerCase() : slug) + '/' : null; }
  // The team's logo (assets/logos/{sport}/, light + dark versions switched
  // by CSS with the theme), or a team-color circle when there isn't one.
  function badge(slug, size) {
    var t = team(slug);
    size = size || 26;
    if (t.svg) {   // NHL's logos: assets/logos/{CODE}_light.svg / _dark.svg
      var sv = ROOT + 'assets/logos/' + slug + '_', sst = ' style="width:' + size + 'px;height:' + size + 'px"';
      return '<span class="tlogo"' + sst + '><img class="tl-light" src="' + sv + 'light.svg" alt="" loading="lazy"><img class="tl-dark" src="' + sv + 'dark.svg" alt="" loading="lazy"></span>';
    }
    if (t.logo) {
      var base = ROOT + 'assets/logos/' + D.sport + '/' + slug;
      var st = ' style="width:' + size + 'px;height:' + size + 'px"';
      return t.logo === 'd'
        ? '<span class="tlogo"' + st + '><img class="tl-light" src="' + base + '.png" alt="" loading="lazy"><img class="tl-dark" src="' + base + '-dark.png" alt="" loading="lazy"></span>'
        : '<span class="tlogo"' + st + '><img src="' + base + '.png" alt="" loading="lazy"></span>';
    }
    var hex = (t.color || '5B6674').replace('#', '');
    var r = parseInt(hex.slice(0, 2), 16), g = parseInt(hex.slice(2, 4), 16), b = parseInt(hex.slice(4, 6), 16);
    var fg = (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#111' : '#FFF';
    var code = tcode(slug);
    return '<span class="team-badge" style="width:' + size + 'px;height:' + size + 'px;background:#' + hex + ';color:' + fg +
      ';font-size:' + Math.max(8, Math.round(size * (code.length > 3 ? 0.27 : 0.34))) + 'px">' + esc(code) + '</span>';
  }
  function teamLink(slug, text) {
    var u = teamUrl(slug);
    return u ? '<a class="gm-team" href="' + u + '">' + text + '</a>' : '<span class="gm-team">' + text + '</span>';
  }
  function shortName(slug) { var t = team(slug); return t.short || t.name; }
  function segs() { return D.segments; }
  function seg(k) { return D.segments.filter(function(s) { return s.key === k; })[0]; }
  // The Full Run (Premium; data.json fullRun): 2nd Half, NHL's 2nd / 3rd
  // Period and the Full Game. Their results and lines ride apart from the
  // first segments' (g.fr, g.fo), so the first-segment pages never see them.
  function frSeg(k) { return (D.fullRun || []).filter(function(s) { return s.key === k; })[0]; }
  function anySeg(k) { return seg(k) || frSeg(k); }
  function segRes(g, k) { return (g.res || {})[k] || (frSeg(k) ? (g.fr || {})[k] : null); }
  function segOdds(g, k) { return (g.odds || {})[k] || (frSeg(k) ? (g.fo || {})[k] : null); }
  // Starters (scripts/fetch_starters.py): MLB's starting pitcher (asp / hsp,
  // prob: the probable), NHL's starting goalie (ag / hg, status: expected /
  // confirmed on a game still to play). Other sports: none.
  function hasStarters() { return D.sportType === 'baseball' || D.sport === 'nhl'; }
  function starterOf(g, side) {
    if (!g || !hasStarters()) return null;
    return D.sportType === 'baseball' ? g[side === 'away' ? 'asp' : 'hsp'] : g[side === 'away' ? 'ag' : 'hg'];
  }
  function starterLast(p) { return p ? p.last || p.name || '' : ''; }
  // a starter's games for one team (a pitcher traded mid-season: only this team's)
  function starterGames(p, slug) {
    return teamGames(slug).filter(function(g) {
      var q = g.state === 'final' && starterOf(g, g.home === slug ? 'home' : 'away');
      return q && String(q.id) === String(p.id);
    });
  }
  // [{p, games}]: each starter of this team's side in these games (min+
  // starts), most starts first; a traded pitcher counts only this team's
  function starterRows(slug, games, min) {
    var by = {}, ids = [];
    games.forEach(function(g) {
      if (g.away !== slug && g.home !== slug) return;
      var p = starterOf(g, g.home === slug ? 'home' : 'away');
      if (!p || p.id == null) return;
      var id = String(p.id);
      if (!by[id]) { by[id] = { p: p, games: [] }; ids.push(id); }
      by[id].games.push(g);
    });
    return ids.map(function(id) { return by[id]; }).filter(function(r) { return r.games.length >= min; })
      .sort(function(a, b) { return b.games.length - a.games.length; });
  }
  // "Probable: Skubal (NRFI 71%) vs Gausman (NRFI 48%)", "Goalies: Oettinger
  // (expected · 1P 8-5-3) vs Hellebuyck (confirmed · 1P 9-4-2)": each with his
  // record with this team; rec false: names only (Matchups cards)
  function startersLine(g, rec) {
    var ps = ['away', 'home'].map(function(side) { return { side: side, p: starterOf(g, side) }; });
    if (!ps.some(function(x) { return x.p; })) return '';
    var parts = ps.map(function(x) {
      if (!x.p) return 'TBD';
      var bits = [];
      if (D.sport === 'nhl' && x.p.status) bits.push(x.p.status);
      if (rec) {
        var gs = starterGames(x.p, g[x.side]);
        if (gs.length) {
          if (D.sportType === 'baseball') bits.push('NRFI ' + tmPct(tmAgg(g[x.side], '1i', 'rfi', 'all', gs).pct));
          else bits.push('1P ' + tpRec(tmAgg(g[x.side], '1p', 'ml', 'all', gs), 'ml'));
        }
      }
      return esc(starterLast(x.p)) + (bits.length ? ' (' + bits.join(' &middot; ') + ')' : '');
    });
    var label = D.sport === 'nhl' ? 'Goalies' : g.state === 'pre' ? 'Probable' : 'Starters';
    return '<p class="tp-sps"><span class="t-label">' + label + '</span> ' + parts.join(' vs ') + '</p>';
  }
  // a segment's short name in text: "2H", "2P", "Game"
  function segTag(k) { return k === 'game' ? 'Game' : anySeg(k).tag; }
  function isRfi(k) { return D.sportType === 'baseball' && k === '1i'; }
  // Segments without 'ML' in their markets (NCAAB 1st half) show no moneyline / SU anywhere.
  function hasMl(k) { var s = seg(k); return !s || !s.markets || s.markets.indexOf('ML') !== -1; }
  function getSeg() { return seg(SEG_CUR) ? SEG_CUR : D.segments[0].key; }
  function setSeg(k) {
    SEG_CUR = k;
    var u = new URL(location.href);
    if (u.searchParams.has('seg')) { u.searchParams.set('seg', k); history.replaceState(null, '', u); }
  }
  function segToggle(id, cur, attr) {
    if (D.segments.length < 2) return '';
    return '<div class="seg-toggle" id="' + id + '">' + D.segments.map(function(s) {
      return '<button class="seg-btn" ' + (attr || 'data-seg') + '="' + s.key + '" aria-pressed="' + (s.key === cur) + '">' + esc(s.label) + '</button>';
    }).join('') + '</div>';
  }
  function emptyNote(html) { return '<div class="section-empty">' + html + '</div>'; }
  function allDates() { return Object.keys(D.games || {}).sort(); }

  // -------------------------------------------------------- matchup card
  // Chris's Matchups spec: one compact table per game for every sport, teams
  // on the rows (name per the naming rule: desktop name, phone abbreviation)
  // and the sport's markets across the top. Top-left: the start time, "LIVE
  // · clock · period" or "FINAL · segment". Each team gets its segment score
  // once the game starts; the full game sits under a divider. A finished
  // game shows its results by highlight only (resultCls): the side that won
  // a soft green fill, the side that lost dimmed, a tie or push soft yellow.
  function flipRes(r) { return { W: 'L', L: 'W' }[r] || r; }
  function nameHtml(slug) { return '<span class="tn-full">' + esc(shortName(slug)) + '</span><span class="tn-short">' + esc(tcode(slug)) + '</span>'; }
  // periods in a segment, for the score so far
  function segPeriods(k) { return { '1q': 1, '1p': 1, '1i': 1, f5: 5 }[k] || (k === '1h' ? (D.sport === 'ncaab' ? 1 : 2) : 1); }
  // [away, home] in a segment so far, or null before it starts
  function segScore(g, k) {
    var r = (g.res || {})[k];
    if (r && r.sc) return r.sc;
    if (g.state === 'pre' || !g.als || !g.hls) return null;
    var n = segPeriods(k), a = g.als.slice(0, n).filter(function(x) { return typeof x === 'number'; }), h = g.hls.slice(0, n).filter(function(x) { return typeof x === 'number'; });
    if (!a.length || !h.length) return null;
    return [a.reduce(function(s, x) { return s + x; }, 0), h.reduce(function(s, x) { return s + x; }, 0)];
  }
  // the segment whose score shows next to the names (MLB: First 5)
  function cardSeg(k) { return D.sportType === 'baseball' ? 'f5' : k; }
  // "OT", "2OT", "SO" after a final score
  function otTag(g) { return g.ot || ((g.detail || '').split('/')[1] || '').trim(); }
  // One live status everywhere (cards, Odds time rows, hub, Trends): period
  // first, then the clock: "LIVE · 3RD 11:14", "LIVE · HALFTIME", "LIVE · END 1ST"
  function liveText(g) {
    var d = String(g.detail || '').trim();
    if (/\b(AM|PM)\b|\bE[SD]?T\b/.test(d)) d = '';   // still the scheduled start, not a clock
    var p = d.split(' - '), s;
    if (p.length > 1) s = p[p.length - 1].trim() + ' ' + p[0].trim();
    else s = d.replace(/^end of /i, 'End ');
    s = s.replace(/\s+(quarter|period|inning|half)\b/ig, '').trim().toUpperCase();
    return 'LIVE' + (s ? ' \u00b7 ' + s : '');
  }
  function liveHtml(g) { return '<span class="st-live">' + esc(liveText(g)) + '</span>'; }
  function cardStatus(g, k) {
    if (g.state === 'final') return 'FINAL &middot; ' + esc(seg(cardSeg(k)).tag);
    if (g.state === 'in') return liveHtml(g);
    return g.start ? esc(timeET(g.start)) : 'TBD';
  }
  // A game with no saved line for any market of the segment shows nowhere
  // (Matchups, Odds, Trends rows, hub); MLB's card covers the 1st inning and F5
  function lined(g, k) {
    var ks = D.sportType === 'baseball' ? ['1i', 'f5'] : [k];
    return ks.some(function(x) {
      var o = (g.odds || {})[x] || {};
      return Object.keys(o).some(function(m) { var v = o[m]; return v != null && (typeof v !== 'object' || Object.keys(v).some(function(s) { return v[s] != null; })); });
    });
  }
  // the same for one segment, the Full Run's included (team Game Log)
  function segLined(g, k) {
    var o = segOdds(g, k) || {};
    return Object.keys(o).some(function(m) { var v = o[m]; return v != null && (typeof v !== 'object' || Object.keys(v).some(function(s) { return v[s] != null; })); });
  }
  // W (won) / L (lost) / P (tie or push) -> the cell's highlight
  function resultCls(r) { return r === 'W' ? ' mc-w' : r === 'L' ? ' mc-l' : r === 'P' ? ' mc-p' : ''; }
  // Total, BTTS and NRFI/YRFI cells are never win/loss colored: the outcome
  // that happened is warm (Over, BTTS Yes, YRFI: row 0) or cool (Under, No,
  // NRFI: row 1); the other row stays plain
  function ouCls(r, row) { return r === 'W' ? (row === 0 ? ' mc-warm' : ' mc-cool') : r === 'P' ? ' mc-p' : ''; }
  // the markets across the top: [market, header]
  function cardCols(k) {
    if (D.sport === 'nhl') return [['ml', 'ML'], ['total', 'O/U'], ['btts', 'BTTS'], ['ml3', '3-WAY']];
    if (D.sportType === 'baseball') return [['rfi', 'NRFI/YRFI'], ['ml', 'F5 ML'], ['ats', 'F5 RUN LINE'], ['total', 'F5 O/U']];
    return [['ats', 'SPREAD'], ['total', 'O/U']].concat(hasMl(k) ? [['ml', 'ML']] : []);
  }
  // one cell: row 0 = away (Over / Yes / YRFI), 1 = home (Under / No / NRFI),
  // 2 = the tie (NHL 3-way only)
  function cardCell(g, k, m, row) {
    var sk = m === 'rfi' ? '1i' : cardSeg(k), o = ((g.odds || {})[sk] || {}), fin = g.state === 'final';
    // a segment is graded the moment it ends (res is only saved once it's over), live games included
    var r = (g.res || {})[sk], done = r && r.sc ? r : null, home = row === 1, res = null, line = null, price = null, tip = '';
    function side(x) { if (!done) return null; if (done.na || !x || x === 'NA') return 'P'; x = home ? flipRes(x) : x; return x === 'W' || x === 'L' ? x : 'P'; }
    function yn(x, want) { if (!done) return null; if (done.na || !x || x === 'NA' || x === 'P') return 'P'; return x === want ? 'W' : 'L'; }
    if (m === 'ml') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.ml ? o.ml[home ? 'home' : 'away'] : null; res = side(done && done.su);
    } else if (m === 'ats') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      var a = o.ats && o.ats[home ? 'home' : 'away'];
      if (a) { line = signed(a.line); price = a.price; }
      res = side(done && done.ats);
    } else if (m === 'total') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      var ln = o.total ? o.total.line : D.sport === 'nhl' ? 1.5 : null;
      if (o.total) { line = ln; price = o.total[home ? 'under' : 'over']; }
      if (ln != null) tip = (home ? 'Under ' : 'Over ') + ln;
      res = yn(done && done.tot, home ? 'U' : 'O');
    } else if (m === 'btts') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.btts ? o.btts[home ? 'no' : 'yes'] : null; tip = home ? 'BTTS No' : 'BTTS Yes';
      res = yn(done && done.btts, home ? 'N' : 'Y');
    } else if (m === 'rfi') {
      if (row === 2) return '<td class="mc-cell mc-none"></td>';
      price = o.nrfi_yrfi ? o.nrfi_yrfi[home ? 'nrfi' : 'yrfi'] : null; tip = home ? 'NRFI' : 'YRFI';
      res = yn(done && done.rfi, home ? 'N' : 'Y');
    } else if (m === 'ml3') {
      var want = ['W', 'L', 'T'][row];
      price = o.ml3 ? o.ml3[['away', 'home', 'draw'][row]] : null;
      // only the outcome that hit is green; a tied period is the TIE cell
      if (done) res = done.na || !done.su || done.su === 'NA' ? 'P' : done.su === want ? 'W' : 'L';
    }
    var none = line == null && price == null, body = none ? '<span class="cell"><span class="mc-dash">-</span></span>' : oddsCell(line, price);
    // no price, nothing to highlight
    var hl = m === 'total' || m === 'btts' || m === 'rfi' ? ouCls(res, row) : resultCls(res);
    return '<td class="mc-cell' + (none ? '' : hl) + '"' + (tip ? ' data-tip="' + esc(tip) + '" data-tap title="' + esc(tip) + '"' : '') + '>' + body + '</td>';
  }
  // "FULL GAME  WSH 101 · IND 114 OT", away first, the winner bold
  function fullGameRow(g) {
    if (g.as == null || g.hs == null || (g.state !== 'final' && g.state !== 'in')) return '';
    // LIVE is said once per card, in the top status
    var fin = g.state === 'final', lbl = 'FULL GAME';
    function sc(slug, n, other) { return '<span class="mc-fs' + (fin ? (n > other ? ' mc-fs-win' : n < other ? ' mc-fs-lose' : '') : '') + '">' + esc(tcode(slug)) + ' ' + esc(n) + '</span>'; }
    var ot = fin ? otTag(g) : '';
    return '<div class="mc-full"><span class="mc-full-lbl">' + lbl + '</span><span class="mc-full-sc">' + sc(g.away, g.as, g.hs) + ' &middot; ' + sc(g.home, g.hs, g.as) +
      (ot ? ' <span class="mc-ot">' + esc(ot) + '</span>' : '') + '</span></div>';
  }
  function gameCard(g, k) {
    var cols = cardCols(k), sc = g.state !== 'pre' ? segScore(g, cardSeg(k)) : null;
    function teamRow(slug, i) {
      return '<tr><th scope="row" class="mc-team"><div class="mc-tw"><span class="mc-tn">' + teamLink(slug, badge(slug, 22) + nameHtml(slug)) + '</span>' +
        (sc ? '<b class="mc-sc">' + esc(sc[i]) + '</b>' : '') + '</div></th>' +
        cols.map(function(c) { return cardCell(g, k, c[0], i); }).join('') + '</tr>';
    }
    // NHL: a TIE row under the teams, only the 3-way column filled
    var tie = D.sport === 'nhl' ? '<tr class="mc-tie"><th scope="row" class="mc-team"><span class="mc-tie-lbl">TIE &middot; 3-WAY</span></th>' +
      cols.map(function(c) { return c[0] === 'ml3' ? cardCell(g, k, 'ml3', 2) : '<td class="mc-cell mc-none"></td>'; }).join('') + '</tr>' : '';
    return '<div class="game-card mc" data-game="' + esc(g.id) + '" style="--mc-n:' + cols.length + '">' +
      '<table class="mc-grid"><thead><tr><th scope="col" class="mc-st">' + cardStatus(g, k) + '</th>' +
      cols.map(function(c) { return '<th scope="col"><span class="mk-h">' + esc(c[1]) + '</span></th>'; }).join('') + '</tr></thead>' +
      '<tbody>' + teamRow(g.away, 0) + teamRow(g.home, 1) + tie + '</tbody></table>' + fullGameRow(g) + (SECTION === 'games' ? startersLine(g, false) : '') +
      (h2hUrl(g.away, g.home) && SECTION !== 'h2h' ? '<a class="mc-more" href="' + h2hUrl(g.away, g.home) + '">Full matchup &rarr;</a>' : '') + '</div>';
  }

  var GAME_INDEX = null, GAME_DAY = {};
  function findGame(id) {
    if (!GAME_INDEX) {
      GAME_INDEX = {};
      Object.keys(D.games).forEach(function(d) { D.games[d].forEach(function(g) { GAME_INDEX[g.id] = g; GAME_DAY[g.id] = d; }); });
    }
    return GAME_INDEX[id];
  }

  // pin an element (position: sticky) just under the site header, which is
  // sticky too; its height changes with the viewport
  function stickBelowNav(el) {
    if (!el) return;
    function place() { var hn = document.querySelector('.hn'); el.style.top = (hn ? hn.getBoundingClientRect().height : 0) + 'px'; }
    place();
    if (!stickBelowNav.wired) { stickBelowNav.wired = true; window.addEventListener('resize', function() { document.querySelectorAll('[data-stick]').forEach(function(x) { x.__place && x.__place(); }); }); }
    el.setAttribute('data-stick', '');
    el.__place = place;
  }

  // ------------------------------------------------------------ date bar
  // cal: add the calendar button (openCalendar, wired by the page)
  // words: "Today · Thu, Nov 12" (Matchups)
  // the center label is always the date itself ("Fri, Nov 13"); the small
  // Today button shows only on another date and jumps back
  function dateBar(cur, dates, cal) {
    var lbl = new Date(cur + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
    return '<div class="date-bar">' +
      '<button class="date-nav" id="datePrev" aria-label="Previous day"' + (cur <= dates[0] ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(lbl) + '</span>' +
      (cur !== todayET() ? '<button class="date-today-btn" id="dateTodayBtn" type="button">Today</button>' : '') + (cal ? CAL_BTN : '') + '</div>' +
      '<button class="date-nav" id="dateNext" aria-label="Next day"' + (cur >= dates[dates.length - 1] ? ' disabled' : '') + '>&rsaquo;</button>' +
    '</div>';
  }
  function step(dates, cur, dir) {
    if (dir > 0) { for (var i = 0; i < dates.length; i++) if (dates[i] > cur) return dates[i]; return cur; }
    for (var j = dates.length - 1; j >= 0; j--) if (dates[j] < cur) return dates[j];
    return cur;
  }
  // Today, else the next date with games, else the last one.
  function defaultDate(dates) {
    var t = todayET();
    if (dates.indexOf(t) !== -1) return t;
    var next = dates.filter(function(d) { return d > t; })[0];
    return next || dates[dates.length - 1];
  }
  function wireDateBar(dates, cur, go) {
    var p = document.getElementById('datePrev'), n = document.getElementById('dateNext'), t = document.getElementById('dateTodayBtn');
    if (p) p.onclick = function() { go(step(dates, cur, -1)); };
    if (n) n.onclick = function() { go(step(dates, cur, 1)); };
    if (t) t.onclick = function() { go(defaultDate(dates)); };
  }
  function urlDate() {
    var d = new URLSearchParams(location.search).get('date');
    return /^\d{4}-\d{2}-\d{2}$/.test(d || '') ? d : null;
  }
  function setUrlDate(d) {
    var u = new URL(location.href);
    u.searchParams.set('date', d);
    history.replaceState(null, '', u);
  }

  // ------------------------------------------------------- Results box
  // "[Weekday] [M/D] Results" (football: "Week N Results"): the finished
  // games' record, win % and units for the sport's markets in plain words,
  // in the sport's market order. Ties and pushes stay out of the win %
  // (Favorites 2-0-4 is 100%).
  function resultRows(games, k) {
    var rows = [];
    function acc(label, opts) { var x = { label: label, w: 0, l: 0, t: 0, u: 0, n: 0, ties: !!opts.ties, noTie: !!opts.noTie, always: !!opts.always }; rows.push(x); return x; }
    // only games with a saved line for the market count, so the record and units cover the same games
    function add(x, r, u) {
      if (!r || u == null) return;
      if (r === 'W') x.w++; else if (r === 'L') x.l++; else x.t++;
      if (u != null) { x.u += u; x.n++; }
    }
    function done(g, key) { var r = (g.res || {})[key]; return g.state === 'final' && r && r.sc && !r.na ? r : null; }
    function suSide(r, home) { var x = r.su; if (!x || x === 'NA') return null; x = home ? flipRes(x) : x; return x === 'W' || x === 'L' ? x : 'T'; }
    if (D.sport === 'nhl') {
      var hm = acc('Home teams', { ties: true }), fv = acc('Favorites', { ties: true }), ov = acc('O/U: Over 1.5', { noTie: true }),
          bt = acc('BTTS Yes', { noTie: true }), m3 = acc('3-way ML (home team)', { noTie: true, always: true });
      games.forEach(function(g) {
        var r = done(g, '1p'); if (!r) return;
        var u = r.u || {};
        add(hm, suSide(r, true), u.su ? u.su[1] : null);
        var f = segFavSide(g, '1p');
        if (f) add(fv, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        if (r.tot === 'O' || r.tot === 'U') add(ov, r.tot === 'O' ? 'W' : 'L', u.tot ? u.tot[0] : null);
        if (r.btts === 'Y' || r.btts === 'N') add(bt, r.btts === 'Y' ? 'W' : 'L', u.btts ? u.btts[0] : null);
        if (r.su && r.su !== 'NA') add(m3, r.su === 'L' ? 'W' : 'L', u.ml3 ? u.ml3[1] : null);
      });
    } else if (D.sportType === 'baseball') {
      var bh = acc('Home teams (F5 moneyline)', { ties: true }), bf = acc('Favorites (F5)', { ties: true }), yr = acc('YRFI', { noTie: true }), fo = acc('F5 O/U: Over', {});
      games.forEach(function(g) {
        var r = done(g, 'f5'), ri = done(g, '1i');
        if (ri && (ri.rfi === 'Y' || ri.rfi === 'N')) add(yr, ri.rfi === 'Y' ? 'W' : 'L', ri.u && ri.u.rfi ? ri.u.rfi[0] : null);
        if (!r) return;
        var u = r.u || {};
        add(bh, suSide(r, true), u.su ? u.su[1] : null);
        var f = segFavSide(g, 'f5');
        if (f) add(bf, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        if (r.tot && r.tot !== 'NA') add(fo, { O: 'W', U: 'L' }[r.tot] || 'T', u.tot ? u.tot[0] : null);
      });
    } else {
      var ml = hasMl(k);
      var sh = ml ? acc('Home teams (moneyline)', {}) : null, sf = ml ? acc('Favorites (moneyline)', {}) : null,
          sa = acc('Favorites (spread)', {}), so = acc('O/U: Over', {});
      games.forEach(function(g) {
        var r = done(g, k); if (!r) return;
        var u = r.u || {}, o = (g.odds || {})[k] || {};
        if (ml) {
          add(sh, suSide(r, true), u.su ? u.su[1] : null);
          var f = segFavSide(g, k);
          if (f) add(sf, suSide(r, f === 'home'), u.su ? u.su[f === 'away' ? 0 : 1] : null);
        }
        var line = ((o.ats || {}).away || {}).line;
        if (r.ats && r.ats !== 'NA' && typeof line === 'number' && line !== 0) {
          var fs = line < 0 ? 'away' : 'home', x = fs === 'home' ? flipRes(r.ats) : r.ats;
          add(sa, x === 'W' || x === 'L' ? x : 'T', u.ats ? u.ats[fs === 'away' ? 0 : 1] : null);
        }
        if (r.tot && r.tot !== 'NA') add(so, { O: 'W', U: 'L' }[r.tot] || 'T', u.tot ? u.tot[0] : null);
      });
    }
    rows.forEach(function(x) { var d = x.w + x.l; x.pct = d ? x.w / d : null; x.gp = x.w + x.l + x.t; });
    return rows.filter(function(x) { return x.gp || (x.always && games.some(function(g) { return g.state === 'final'; })); });
  }
  function resultsTitle(d) {
    var dt = new Date(d + 'T12:00:00Z');
    return dt.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'UTC' }) + ' ' + (dt.getUTCMonth() + 1) + '/' + dt.getUTCDate() + ' Results';
  }
  function resultsBox(games, k, title) {
    if (!games.some(function(g) { return g.state === 'final'; })) return '';
    var rows = resultRows(games, k);
    if (!rows.length) return '';
    return '<div class="daily-summary gm-results"><h3>' + esc(title) + '</h3>' +
      '<div class="ds-row ds-head"><span></span><span class="ds-right"><span class="ds-col-rec">Record</span><span class="ds-col-pct">Win %</span><span class="ds-col-units">Units</span></span></div>' +
      rows.map(function(x) {
        return '<div class="ds-row"><span class="ds-label">' + esc(x.label) + '</span><span class="ds-right">' +
          '<span class="ds-record ds-col-rec mono">' + x.w + '-' + x.l + (x.noTie ? '' : '-' + x.t) + '</span>' +
          '<span class="ds-col-pct mono">' + (x.pct == null ? '-' : Math.round(x.pct * 100) + '%') + '</span>' +
          '<span class="ds-col-units">' + (x.n ? unitsPill(x.u, true) : '<span class="u-pill u-none">-</span>') + '</span></span></div>';
      }).join('') + '</div>';
  }

  // ------------------------------------------------------- Matchups page
  // One template for every sport: the date bar (football: the week bar),
  // a pinned segment toggle (spread sports with two segments), the Results
  // box, then the cards, two to a row on desktop. Football weeks list
  // finished games last.
  function weekGames(key) {
    var out = [];
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.wk === key) out.push(g); }); });
    var rank = function(g) { return g.state === 'final' ? 1 : (g.state === 'pre' || g.state === 'in') ? 0 : 2; };
    return out.sort(function(a, b) { return (rank(a) - rank(b)) || ((a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0); });
  }
  function shortDay(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }); }
  function dayName(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }); }
  // A day (football: a week) with no games: one card with the game days on
  // either side. keys: the game days (or weeks) in order; name(key) its words.
  function noGamesCard(cur, keys, name, weekly, scheduled, past) {
    var prev = keys.filter(function(x) { return x < cur; }).pop(), next = keys.filter(function(x) { return x > cur; })[0];
    if (weekly) { var i = WEEK_ORDER.indexOf(cur); prev = keys.filter(function(x) { return WEEK_ORDER.indexOf(x) < i; }).pop(); next = keys.filter(function(x) { return WEEK_ORDER.indexOf(x) > i; })[0]; }
    // scheduled: games on the day, none with a saved line yet; past (Odds):
    // a day or week already over with no lines says none were saved
    return '<div class="st-card no-games-card"><p>' + (past ? 'No lines saved for ' : scheduled ? 'No ' + esc(D.label) + ' lines posted yet for ' : 'No ' + esc(D.label) + ' games ' + (weekly ? 'in ' : 'on ')) + esc(name(cur)) + '.</p><div class="ngc-nav">' +
      (prev ? '<button type="button" class="tr-link" data-go="' + esc(prev) + '">&larr; ' + esc(name(prev)) + '</button>' : '<span></span>') +
      (next ? '<button type="button" class="tr-link" data-go="' + esc(next) + '">Next games: ' + esc(name(next)) + ' &rarr;</button>' : '') + '</div></div>';
  }
  var WEEK_ORDER = [];
  function wireNoGames(go) { app.querySelectorAll('.no-games-card [data-go]').forEach(function(b) { b.onclick = function() { go(b.getAttribute('data-go')); }; }); }
  function weekRange(w) { return w.start === w.end ? shortDay(w.start) : shortDay(w.start) + '-' + shortDay(w.end); }
  // This week = the first week that still has a game to play; else the last.
  function currentWeek(weeks) {
    for (var i = 0; i < weeks.length; i++) {
      if (weekGames(weeks[i].key).some(function(g) { return g.state === 'pre' || g.state === 'in'; })) return weeks[i].key;
    }
    return weeks[weeks.length - 1].key;
  }
  function gmSegBar(k) {
    return !periodFamily() && D.segments.length > 1 ? '<div class="gm-stick" id="gmStick"><div class="sport-seg-row">' + segToggle('pageSeg', k) + '</div></div>' : '';
  }
  function renderGames() {
    var weeks = D.schedule === 'week' ? D.weeks || [] : null;
    var dates = allDates();
    if (weeks ? !weeks.length : !dates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' matchups loaded yet.'); return; }
    var keys = weeks ? weeks.map(function(w) { return w.key; }) : null;
    var thisWeek = weeks ? currentWeek(weeks) : null, cur;
    if (weeks) { var want = new URLSearchParams(location.search).get('week'); cur = keys.indexOf(want) !== -1 ? want : thisWeek; }
    else cur = urlDate() || defaultDate(dates);
    function go(x) {
      if (weeks) { if (keys.indexOf(x) === -1) { var w = weekFor(weeks, x); if (!w) return; x = w.key; } cur = x; var u = new URL(location.href); u.searchParams.set('week', x); u.searchParams.delete('date'); history.replaceState(null, '', u); }
      else { cur = x; setUrlDate(x); }
      draw();
    }
    function draw() {
      var k = getSeg(), games, title, none;
      if (weeks) {
        var w = weeks[keys.indexOf(cur)];
        games = weekGames(cur); title = w.label + ' Results'; none = 'this week';
      } else {
        games = (D.games[cur] || []).slice().sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0; });
        title = resultsTitle(cur); none = 'on ' + dateLabel(cur);
      }
      games = games.filter(function(g) { return lined(g, k); });
      var html = (weeks ? weekBar(weeks, cur, thisWeek) : dateBar(cur, dates, true)) + gmSegBar(k) + resultsBox(games, k, title);
      if (!games.length) {
        if (weeks) WEEK_ORDER = keys;
        html += weeks ? noGamesCard(cur, keys.filter(function(x) { return weekGames(x).length; }), function(x) { return weeks[keys.indexOf(x)].label; }, true, weekGames(cur).length > 0)
          : noGamesCard(cur, dates.filter(function(d) { return D.games[d].length; }), dayName, false, (D.games[cur] || []).length > 0);
      }
      html += '<div class="games-list mc-list">' + games.map(function(g) { return gameCard(g, k); }).join('') + '</div>';
      app.innerHTML = html;
      wireTips(app);
      wireNoGames(go);
      stickBelowNav(document.getElementById('gmStick'));
      if (weeks) {
        var i = keys.indexOf(cur), p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
        if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
        if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
        if (t) t.onclick = function() { go(thisWeek); };
      } else wireDateBar(dates, cur, go);
      var cal = document.getElementById('dateCal');
      if (cal) cal.onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: weeks, onPick: go }); };
      var ps = document.getElementById('pageSeg');
      if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    }
    draw();
  }

  // ------------------------------------------------- per-game aggregation
  // Records from the graded games themselves (res + per-side units on each
  // game), so any side, market or date range can be counted in the browser.
  // res is from the away side: su / ats W-L-T(P); tot O-U-P; rfi Y / N.
  // u[market] = [away units, home units] ([over, under] for totals).
  // Games with any graded period (a live game counts once its 1st quarter /
  // half / inning is final, the same as the build's season stats).
  function finalGames(from, to) {
    var out = [];
    allDates().forEach(function(d) {
      if ((from && d < from) || (to && d > to)) return;
      D.games[d].forEach(function(g) { if (g.res) out.push(g); });
    });
    return out;
  }
  // ------------------------------------------- Teams list + team pages
  // One layout for every sport (Chris's Teams spec). The market pills come
  // from the sport's family config (D.markets: [segment, market, label,
  // kind], scripts/sports.py). A team's result in a market, from res (away
  // side): ml W/L/T, ats W/L/P, total O/U/P, btts Y/N, rfi Y/N, with units
  // u[market] = [away, home] ([over, under] / [yes, no]). NHL and MLB count
  // a tied segment as a tie; the spread family calls it a push.
  function tieSport() { return periodFamily(); }
  function tmMarkets(k) {
    return (D.markets || []).filter(function(m) { return !k || m[0] === k; }).map(function(m) {
      return { k: m[0], m: m[1], label: m[1] === 'total' && D.sport === 'nhl' ? 'Over 1.5' : m[2] };
    });
  }
  // a Full Run segment's markets: NHL's periods their result (W-L-T) and
  // goals per game; the full game ML / puck line / total (MLB ML / run line /
  // total); the spread family's 2nd half and game Spread / Total / ML
  var FR_MIN = 5;
  var FR_LOCK = '<svg class="fr-lock" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-label="Premium"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>';
  function frMarkets(k) {
    if (k === '2p' || k === '3p') return [{ k: k, m: 'per' }, { k: k, m: 'gpg' }];
    var ms = periodFamily() ? ['ml', 'ats', 'total'] : ['ats', 'total', 'ml'];
    return ms.map(function(m) { return { k: k, m: m }; });
  }
  // the hit / miss / tie letters for runs, records and the game log
  var TM_INFO = {
    ml: { pct: 'Win %', hit: 'W', miss: 'L' }, ml3: { pct: 'Win %', hit: 'W', miss: 'L', tie: 'T' },
    ats: { pct: 'Cover %', hit: 'W', miss: 'L', tie: 'P' }, total: { pct: 'Over %', hit: 'O', miss: 'U', tie: 'P' },
    btts: { pct: 'Yes %', hit: 'Y', miss: 'N' }, rfi: { pct: 'NRFI %', hit: 'N', miss: 'Y' },
    // the Full Run's results-only rows: per = won the NHL period (W-L-T, ties
    // count, as the 3-way), su = won the 2nd half (until its lines are in)
    per: { pct: 'Win %', hit: 'W', miss: 'L', tie: 'T' }, su: { pct: 'Win %', hit: 'W', miss: 'L', tie: 'T' }
  };
  function tmTieLetter(m) { return m === 'ml' ? (tieSport() ? 'T' : 'P') : (TM_INFO[m].tie || 'P'); }
  function tmLetter(r, m) { return r === 'W' ? TM_INFO[m].hit : r === 'L' ? TM_INFO[m].miss : tmTieLetter(m); }
  function tmNoPush(m) { return m === 'btts' || m === 'rfi' || (m === 'total' && D.sport === 'nhl'); }
  function fbUnits(r) { return r === 'W' ? 0.9091 : r === 'L' ? -1 : 0; }   // -110 when only the line was saved
  // One team's result in one market: {r: 'W' (the hit side) | 'L' | 'T' (tie / push), u: units or null}
  function tmBet(g, k, m, slug) {
    var r = segRes(g, k);
    if (!r || !r.sc || r.na) return null;
    var home = g.home === slug, i = home ? 1 : 0, u = r.u || {}, o = segOdds(g, k) || {};
    function side(x) { if (!x || x === 'NA') return null; x = home ? flipRes(x) : x; return x === 'P' ? 'T' : x; }
    if (m === 'per' || m === 'su') { var w = side(r.su); return w ? { r: w, u: null } : null; }   // results only: every game
    // the Full Run's records count only the games with a line for the market
    if (m === 'ml' && frSeg(k) && !u.su) return null;
    if (m === 'ml' || m === 'ml3') {
      var x = side(r.su);
      if (!x) return null;
      return { r: x, u: m === 'ml3' ? (u.ml3 ? u.ml3[i] : null) : (u.su ? u.su[i] : null) };   // 3-way: a tie loses the bet
    }
    if (m === 'ats') { var a = side(r.ats); return a ? { r: a, u: u.ats ? u.ats[i] : o.ats ? fbUnits(a) : null } : null; }
    if (m === 'total') {
      if (!r.tot || r.tot === 'NA') return null;
      var t = { O: 'W', U: 'L', P: 'T' }[r.tot];
      return { r: t, u: u.tot ? u.tot[0] : o.total ? fbUnits(t) : null };
    }
    if (m === 'btts') return r.btts === 'Y' || r.btts === 'N' ? { r: r.btts === 'Y' ? 'W' : 'L', u: u.btts ? u.btts[0] : null } : null;
    if (m === 'rfi') return r.rfi === 'Y' || r.rfi === 'N' ? { r: r.rfi === 'N' ? 'W' : 'L', u: u.rfi ? u.rfi[1] : null } : null;
    return null;
  }
  // games: one team's games, oldest first; side: all / home / away
  function tmAgg(slug, k, m, side, games) {
    var a = { w: 0, l: 0, t: 0, gp: 0, units: 0, priced: 0, seq: [] };
    games.forEach(function(g) {
      if ((side === 'home' && g.home !== slug) || (side === 'away' && g.away !== slug)) return;
      var b = tmBet(g, k, m, slug);
      if (!b) return;
      a.gp++; a.seq.push(b.r);
      if (b.r === 'W') a.w++; else if (b.r === 'L') a.l++; else a.t++;
      if (b.u != null) { a.units += b.u; a.priced++; }
    });
    // ties and pushes stay out of the win % (a 3-way bet loses on a tie)
    var d = m === 'ml3' || m === 'per' ? a.w + a.l + a.t : a.w + a.l;
    a.pct = d ? a.w / d : null;
    a.tiePct = m === 'ml3' && a.gp ? a.t / a.gp : null;
    var n = 0, last = a.seq[a.seq.length - 1];
    for (var j = a.seq.length - 1; j >= 0 && a.seq[j] === last; j--) n++;
    a.run = n ? { r: last, n: n } : null;
    return a;
  }
  function tmPct(x) { return x == null ? '-' : Math.round(x * 100) + '%'; }
  // only the number is colored: --good above +0.5u, red below -0.5u, yellow between
  function tmUnits(a) {
    if (!a.priced) return '<span class="tm-u">-</span>';
    var r = Math.round(a.units * 100) / 100;
    return '<span class="tm-u ' + unitCls(r) + '">' + fmtUnits(r) + '</span>';
  }
  function teamGames(slug) {
    var out = [];
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.away === slug || g.home === slug) out.push(g); }); });
    return out.sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : (a.start || '') > (b.start || '') ? 1 : 0; });
  }
  function gameDay(g) { findGame(g.id); return GAME_DAY[g.id]; }
  // "Playing today": today's date only, weekly sports too (not the week)
  function tmSlate() { return D.games[todayET()] || []; }
  // pills: the spread family picks a segment first; NHL / MLB list every market
  function tmPills(k) { return !periodFamily() && D.segments.length > 1 ? tmMarkets(k) : tmMarkets(); }
  function tmPick(st, pills) {
    var p = pills.filter(function(x) { return x.k === st.k && x.m === st.m; })[0] || pills.filter(function(x) { return x.k === st.k; })[0] || pills[0];
    st.k = p.k; st.m = p.m;
    return p;
  }
  function tmControls(st, pills, id) {
    var segRow = !periodFamily() && D.segments.length > 1 ? '<div class="seg-toggle" data-tm-segs>' + D.segments.map(function(s) {
      return '<button class="seg-btn" data-tm-seg="' + s.key + '" aria-pressed="' + (s.key === st.k) + '">' + esc(s.label) + '</button>'; }).join('') + '</div>' : '';
    return segRow + '<div class="seg-toggle" id="' + id + '">' + pills.map(function(p) {
      return '<button class="seg-btn" data-tm-pill="' + p.k + '|' + p.m + '" aria-pressed="' + (p.k === st.k && p.m === st.m) + '">' + esc(p.label) + '</button>'; }).join('') + '</div>';
  }
  function wireTmControls(root, st, draw) {
    root.querySelectorAll('[data-tm-seg]').forEach(function(b) { b.onclick = function() { st.k = b.getAttribute('data-tm-seg'); setSeg(st.k); draw(); }; });
    root.querySelectorAll('[data-tm-pill]').forEach(function(b) { b.onclick = function() { var x = b.getAttribute('data-tm-pill').split('|'); st.k = x[0]; st.m = x[1]; draw(); }; });
  }
  // ----------------------------------------------------------- Teams list
  // Chris's Teams index spec (Nov 19): one market at a time; desktop a
  // table (Team · % (record) · Last 10 · Streak · Units) with the Leaders
  // column; phones two-line rows. Every team sorts normally, with no
  // small-sample label; game times only with Today on. College:
  // search, 50 rows at a time (sorting and filters run on every team first).
  var tl = { k: null, m: null, side: 'all', q: '', sortKey: 'units', sortDir: -1, today: false, grp: '', shown: 50 };
  var TL_PAGE = 50;      // college: rows shown at a time
  var TL_LEAD_MIN = 10;  // games a team needs for a Leaders card
  // The group dropdown: college groups (Power 4 / Group of 5 /
  // Independents; Power conferences / Mid-majors) then each conference;
  // pro sports each conference, then each division. [{v, label, test}]
  var POWER4 = /^(Southeastern|Big Ten|Big 12|Atlantic Coast) Conference$/;
  var POWER_HOOPS = /^(Southeastern|Big Ten|Big 12|Atlantic Coast|Big East) Conference$/;
  function tlCollege() { return D.sport === 'ncaab' || D.sport === 'ncaaf'; }
  function tlGroups() {
    function vals(f) { var o = {}; Object.keys(D.teams).forEach(function(s) { var v = D.teams[s][f]; if (v) o[v] = 1; }); return Object.keys(o).sort(); }
    function conf(s) { return D.teams[s].conference || ''; }
    var out = [{ v: '', label: tlCollege() ? 'All conferences' : 'All teams', test: function() { return true; } }];
    if (D.sport === 'ncaaf') {
      out.push({ v: 'p4', label: 'Power 4', test: function(s) { return POWER4.test(conf(s)); } },
               { v: 'g5', label: 'Group of 5', test: function(s) { return !POWER4.test(conf(s)) && !/Independent/.test(conf(s)); } },
               { v: 'ind', label: 'Independents', test: function(s) { return /Independent/.test(conf(s)); } });
    } else if (D.sport === 'ncaab') {
      out.push({ v: 'power', label: 'Power conferences', test: function(s) { return POWER_HOOPS.test(conf(s)); } },
               { v: 'mid', label: 'Mid-majors', test: function(s) { return !POWER_HOOPS.test(conf(s)); } });
    }
    vals('conference').filter(function(c) { return D.sport !== 'ncaaf' || !/Independent/.test(c); }).forEach(function(c) {
      var label = tlCollege() ? c.replace(/ Conference$/, '') : { East: 'Eastern Conference', West: 'Western Conference' }[c] || c;
      out.push({ v: 'c:' + c, label: label, test: function(s) { return conf(s) === c; } });
    });
    vals('division').forEach(function(d) {
      out.push({ v: 'd:' + d, label: d + (/\s/.test(d) ? '' : ' Division'), test: function(s) { return D.teams[s].division === d; } });
    });
    return out;
  }
  // the name: desktop the full name (college: the school), phones the short name
  function tlName(s) { return tlCollege() ? shortName(s) : D.teams[s].name; }
  // the record column: "1P ML % (W-L-T)", "1H SPREAD % (W-L-P)", "O/U 1.5 % (O-U)", "BTTS % (Y-N)"
  function tlHead(p) {
    var n = D.sport === 'nhl' ? { ml: '1P ML', total: 'O/U 1.5', btts: 'BTTS', ml3: '3-Way' }[p.m] : tpName(p);
    return n + ' % (' + tpSides(p.m) + ')';
  }
  function tlRecTxt(a, m) { return a.gp ? tmPct(a.pct) + ' (' + tpRec(a, m) + ')' : '-'; }
  // the last 10: [w, l, t] and its win rate for sorting
  function tlL10(seq) {
    var x = seq.slice(-10), w = 0, l = 0, t = 0;
    x.forEach(function(r) { if (r === 'W') w++; else if (r === 'L') l++; else t++; });
    return { w: w, l: l, t: t, n: x.length, v: w + l ? w / (w + l) : null };
  }
  function tlL10Txt(x, m) { return x.n ? x.w + '-' + x.l + (tmNoPush(m) ? '' : '-' + x.t) : '-'; }
  function tlStreak(run, m) {
    if (!run) return '-';
    return '<span class="tl-streak ' + (run.r === 'W' ? 'good' : run.r === 'L' ? 'bad' : 'flat') + '">' + tmLetter(run.r, m) + run.n + '</span>';
  }
  function tlNote(m) {
    return { ml: tieSport() ? 'Moneyline: win % leaves ties out (a tie is in the record, not the %)' : 'Moneyline: win % leaves pushes out (a tied segment is in the record, not the %)',
             ml3: '3-Way: win % counts ties (a tied segment loses the bet)',
             ats: (D.sportType === 'baseball' ? 'Run line' : 'Spread') + ': cover % leaves pushes out (they count in the record)' }[m] ||
      (tmNoPush(m) ? 'This market can’t push' : 'Total: Over % leaves pushes out (they count in the record)');
  }
  // "@ TB · 7:30 PM" / "vs WPG · 7:00 PM" (Today on only)
  function tlGameTxt(pl) {
    var t = pl.g.start ? new Date(pl.g.start).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }) : '';
    return (pl.at ? '@ ' : 'vs ') + tcode(pl.opp) + (t ? ' · ' + t : '');
  }
  // LEADERS (desktop): a card per market, Hottest / Coldest Last 10, Longest Active Streaks
  function tlLeaders(byTeam, k) {
    var cards = periodFamily() ? tmMarkets() : tmMarkets(k);
    if (D.sportType === 'baseball') {
      var order = { ml: 0, ats: 1, rfi: 2, total: 3 };
      cards = cards.slice().sort(function(a, b) { return order[a.m] - order[b.m]; });
    }
    var slugs = Object.keys(D.teams), AGG = {};
    function agg(s, p) { var id = s + '|' + p.k + '|' + p.m; return AGG[id] || (AGG[id] = tmAgg(s, p.k, p.m, 'all', byTeam[s])); }
    function row(i, s, val) {
      return '<li><a class="tll-row" href="' + teamUrl(s) + '"><span class="tll-rank">' + (i + 1) + '</span>' + badge(s, 20) +
        '<span class="tll-name">' + esc(shortName(s)) + '</span><span class="tll-val">' + val + '</span></a></li>';
    }
    function card(title, rows) {
      if (!rows.length) return '';
      return '<div class="st-card tll-card"><div class="st-head"><h4>' + esc(title) + '</h4></div><ol class="tll-list">' + rows.join('') + '</ol></div>';
    }
    var out = cards.map(function(p) {
      var list = slugs.map(function(s) { return { s: s, a: agg(s, p) }; }).filter(function(x) { return x.a.gp >= TL_LEAD_MIN; });
      var side = p.m === 'ml' || p.m === 'ml3' || p.m === 'ats';
      // by units where most teams have prices (MLB / WNBA saved a handful: by win %)
      var byU = side && list.filter(function(x) { return x.a.priced; }).length * 2 > list.length;
      var title = D.sportType === 'baseball' ? { ml: 'F5 ML', ats: 'F5 Run Line', rfi: 'NRFI', total: 'F5 Over' }[p.m]
        : D.sport === 'nhl' ? { ml: '1P Moneyline', total: '1P Over 1.5', btts: 'BTTS No', ml3: '3-Way' }[p.m]
        : seg(p.k).tag + ' ' + { ml: 'Moneyline', ats: spreadWord(), total: 'Over' }[p.m];
      function rate(a) { return p.m === 'btts' ? (a.w + a.l ? a.l / (a.w + a.l) : null) : a.pct; }   // BTTS No
      list = list.filter(function(x) { return byU ? x.a.priced : rate(x.a) != null; });
      list.sort(function(x, y) { return byU ? y.a.units - x.a.units : rate(y.a) - rate(x.a) || y.a.gp - x.a.gp; });
      return card(title, list.slice(0, 3).map(function(x, i) {
        return row(i, x.s, byU ? tmUnits(x.a) : tmPct(rate(x.a)) + ' <span class="tll-sub">(' + (p.m === 'btts' ? x.a.l + '-' + x.a.w : tpRec(x.a, p.m)) + ')</span>');
      }));
    }).join('');
    // Hottest / Coldest Last 10, in the first market
    var p0 = cards[0];
    var l10 = slugs.map(function(s) { var a = agg(s, p0); return { s: s, x: tlL10(a.seq), gp: a.gp }; })
      .filter(function(x) { return x.gp >= TL_LEAD_MIN && x.x.v != null; });
    var hot = l10.slice().sort(function(a, b) { return (b.x.w - b.x.l) - (a.x.w - a.x.l); }).slice(0, 3);
    var cold = l10.slice().sort(function(a, b) { return (a.x.w - a.x.l) - (b.x.w - b.x.l); }).slice(0, 3);
    var l10Name = D.sport === 'nhl' ? '1P ML' : tpName(p0);
    out += card('Hottest Last 10 · ' + l10Name, hot.map(function(x, i) { return row(i, x.s, tlL10Txt(x.x, p0.m)); }));
    out += card('Coldest Last 10 · ' + l10Name, cold.map(function(x, i) { return row(i, x.s, tlL10Txt(x.x, p0.m)); }));
    // Longest Active Streaks, any market (a tie or push ends a run, it doesn't make one)
    var runs = [];
    slugs.forEach(function(s) {
      var best = null;
      tmMarkets().forEach(function(p) {
        var a = agg(s, p);
        if (a.gp < TL_LEAD_MIN || !a.run || a.run.r === 'T') return;
        if (!best || a.run.n > best.run.n) best = { s: s, run: a.run, p: p };
      });
      if (best) runs.push(best);
    });
    runs.sort(function(a, b) { return b.run.n - a.run.n; });
    out += card('Longest Active Streaks', runs.slice(0, 3).map(function(x, i) {
      return row(i, x.s, tlStreak(x.run, x.p.m) + ' <span class="tll-sub">' + esc(D.sport === 'nhl' ? { ml: '1P ML', total: 'O/U 1.5', btts: 'BTTS', ml3: '3-Way' }[x.p.m] : tpName(x.p)) + '</span>');
    }));
    if (!out) out = '<p class="tl-small">A team needs ' + TL_LEAD_MIN + ' games to make a Leaders card.</p>';
    return '<aside class="tll"><h2 class="tll-h">' + esc(D.label) + ' Leaders</h2>' + out +
      '<a class="fr-more tll-all" href="' + statsUrl() + '#leaders">All leaders &rarr;</a></aside>';
  }
  function renderTeamsIndex() {
    if (!D.season) return;   // keep the plain list
    var byTeam = {};
    Object.keys(D.teams).forEach(function(s) { byTeam[s] = teamGames(s); });
    var playing = {};
    tmSlate().forEach(function(g) {
      if (g.state === 'postponed' || g.state === 'canceled') return;
      playing[g.away] = { g: g, opp: g.home, at: true };
      playing[g.home] = { g: g, opp: g.away, at: false };
    });
    var anyPlaying = Object.keys(playing).some(function(s) { return D.teams[s]; });
    var groups = tlGroups(), college = tlCollege(), nTeams = Object.keys(D.teams).length;
    if (!groups.some(function(x) { return x.v === tl.grp; })) tl.grp = '';
    if (!tl.k) tl.k = getSeg();
    var leadK = null, leadHtml = '';
    function draw() {
      var pills = tmPills(tl.k), p = tmPick(tl, pills), k = p.k, m = p.m;
      var grp = groups.filter(function(x) { return x.v === tl.grp; })[0];
      // filters and sorting run on every team; only the display is cut to TL_PAGE (college)
      var list = Object.keys(D.teams).filter(function(s) {
        var t = D.teams[s];
        if (tl.today && !playing[s]) return false;
        if (!grp.test(s)) return false;
        return !tl.q || (t.name + ' ' + (t.code || '') + ' ' + (t.short || '')).toLowerCase().indexOf(tl.q) !== -1;
      }).map(function(s) {
        var a = tmAgg(s, k, m, tl.side, byTeam[s]);
        a.slug = s; a.name = tlName(s); a.l10 = tlL10(a.seq);
        a.u = a.priced ? a.units : null; a.l10v = a.l10.v; a.runV = a.run ? (a.run.r === 'W' ? a.run.n : a.run.r === 'L' ? -a.run.n : 0) : null;
        return a;
      });
      var key = { units: 'u', streak: 'runV', l10: 'l10v', pct: 'pct' }[tl.sortKey] || tl.sortKey, dir = tl.sortDir;
      list.sort(function(a, b) {
        if (key === 'name') return a.name.localeCompare(b.name) * dir;
        var va = a[key], vb = b[key];
        if (va === vb || (va == null && vb == null)) return b.gp - a.gp || a.name.localeCompare(b.name);
        if (va == null) return 1;
        if (vb == null) return -1;
        return (va - vb) * dir;
      });
      var shown = college ? list.slice(0, tl.shown) : list;
      function today(r) { var pl = tl.today && playing[r.slug]; return pl ? '<span class="tl-game">' + esc(tlGameTxt(pl)) + '</span>' : ''; }
      function rowHtml(r) {
        return '<tr class="tl-row" data-href="' + teamUrl(r.slug) + '"><td class="team-cell"><span class="tl-team">' + badge(r.slug, 24) +
          '<span class="tl-nm"><a class="tl-name" href="' + teamUrl(r.slug) + '">' + esc(r.name) + '</a>' + today(r) + '</span></span></td>' +
          '<td class="num">' + tlRecTxt(r, m) + '</td><td class="num">' + tlL10Txt(r.l10, m) + '</td>' +
          '<td class="num">' + tlStreak(r.run, m) + '</td><td class="num">' + tmUnits(r) + '</td></tr>';
      }
      function mobHtml(r) {
        return '<li><a class="tlm-row" href="' + teamUrl(r.slug) + '">' + badge(r.slug, 28) + '<span class="tlm-l"><span class="tlm-name">' + esc(shortName(r.slug)) + '</span>' +
          today(r) +
          '<span class="tlm-sub">' + (r.l10.n ? 'L10 ' + tlL10Txt(r.l10, m) + (r.run ? ' &middot; ' : '') : '') + (r.run ? tlStreak(r.run, m) : '') + '</span></span>' +
          '<span class="tlm-r"><span class="tlm-rec">' + tlRecTxt(r, m) + '</span>' + tmUnits(r) + '</span></a></li>';
      }
      var empty = tl.q ? 'No teams match &ldquo;' + esc(tl.q) + '&rdquo;.' : tl.today ? 'No teams playing today.' : 'No teams in ' + esc(grp.label) + '.';
      function th(key2, label) {
        var on = tl.sortKey === key2;
        return '<th class="' + (key2 === 'name' ? '' : 'num') + '" data-sort="' + key2 + '" aria-sort="' + (on ? (tl.sortDir < 0 ? 'descending' : 'ascending') : 'none') + '">' + label + '<span class="arrow">' + (on ? (tl.sortDir < 0 ? '▼' : '▲') : '') + '</span></th>';
      }
      function sidePill(v, label) { return '<button class="seg-btn" data-tl-side="' + v + '" aria-pressed="' + (tl.side === v) + '">' + label + '</button>'; }
      var more = college && list.length > shown.length ? '<div class="tl-more"><button class="seg-btn" id="tlMore" type="button">Show ' + Math.min(TL_PAGE, list.length - shown.length) + ' more</button>' +
        '<span class="tl-count">' + shown.length + ' of ' + list.length + '</span></div>' : college && list.length ? '<div class="tl-more"><span class="tl-count">' + list.length + ' of ' + list.length + '</span></div>' : '';
      if (leadK !== k) { leadK = k; leadHtml = tlLeaders(byTeam, k); }
      app.innerHTML = '<div id="teamView"><div class="controls tm-controls">' + tmControls(tl, pills, 'tlPills') +
        '<div class="seg-toggle">' + sidePill('all', 'All') + sidePill('home', 'Home') + sidePill('away', 'Away') +
        (anyPlaying ? '<button class="seg-btn" id="tlToday" aria-pressed="' + tl.today + '">Today</button>' : '') + '</div>' +
        (groups.length > 1 ? '<select class="tm-filter" id="tlGroup" aria-label="Filter teams">' + groups.map(function(x) {
          return '<option value="' + esc(x.v) + '"' + (x.v === tl.grp ? ' selected' : '') + '>' + esc(x.label) + '</option>'; }).join('') + '</select>' : '') +
        (college ? '<input class="search-box" id="tlSearch" type="search" placeholder="Search ' + nTeams + ' teams" aria-label="Search teams" value="' + esc(tl.q) + '">' : '') + '</div>' +
        '<div class="tl-layout"><div class="tl-main">' +
        '<div class="st-card tl-card tl-desk"><table id="leagueTable" class="tl-table"><thead><tr>' +
        th('name', 'Team') + th('pct', esc(tlHead(p))) + th('l10', 'Last 10') + th('streak', 'Streak') + th('units', 'Units') +
        '</tr></thead><tbody>' + (shown.length ? shown.map(rowHtml).join('') : '<tr><td colspan="5"><div class="empty-state">' + empty + '</div></td></tr>') + '</tbody></table></div>' +
        '<div class="tl-mob"><div class="tl-mob-sort">' + esc(tlHead(p)) + '</div>' +
        (shown.length ? '<ul class="tlm-list">' + shown.map(mobHtml).join('') + '</ul>' : '<div class="empty-state">' + empty + '</div>') + '</div>' + more +
        '<p class="tl-note">' + esc(seg(k).label) + ' &middot; ' + esc(D.seasonLabel || '') + ' season &middot; ' + esc(tlNote(m)) +
        ' &middot; Units: 1 unit a game at the closing price, only where prices were saved.</p></div>' +
        leadHtml + '</div></div>';
      wireTmControls(app, tl, function() { tl.shown = TL_PAGE; draw(); });
      app.querySelectorAll('[data-tl-side]').forEach(function(b) { b.onclick = function() { tl.side = b.getAttribute('data-tl-side'); tl.shown = TL_PAGE; draw(); }; });
      var gs = document.getElementById('tlGroup');
      if (gs) gs.onchange = function() { tl.grp = gs.value; tl.shown = TL_PAGE; draw(); };
      var tb = document.getElementById('tlToday');
      if (tb) tb.onclick = function() { tl.today = !tl.today; tl.shown = TL_PAGE; draw(); };
      var mb = document.getElementById('tlMore');
      if (mb) mb.onclick = function() { tl.shown += TL_PAGE; draw(); };
      app.querySelectorAll('th[data-sort]').forEach(function(h) {
        h.onclick = function() {
          var key2 = h.getAttribute('data-sort');
          if (tl.sortKey === key2) tl.sortDir *= -1; else { tl.sortKey = key2; tl.sortDir = key2 === 'name' ? 1 : -1; }
          tl.shown = TL_PAGE;
          draw();
        };
      });
      app.querySelectorAll('tr[data-href]').forEach(function(tr) {
        tr.onclick = function(e) { if (!e.target.closest('a')) window.location.href = tr.getAttribute('data-href'); };
      });
      var q = document.getElementById('tlSearch');
      if (q) q.oninput = function() {
        tl.q = q.value.trim().toLowerCase(); tl.shown = TL_PAGE; var pos = q.selectionStart; draw();
        var q2 = document.getElementById('tlSearch'); q2.focus(); q2.setSelectionRange(pos, pos);
      };
    }
    draw();
  }

  // ------------------------------------------------------------ team page
  // Chris's Team page spec (Nov 19), every sport, its own segment and
  // markets: Header (static) · Next game · Last game · Season markets ·
  // Current streaks · Game log · Home / Away · Situational results · Line
  // history · Results history. The build marks the sport's season state on
  // #sportApp (scripts/seasons.py): data-season "off" = between seasons
  // (Next game becomes "[YEAR] SEASON · FINAL", Current streaks the season's
  // longest, every stats section says "[YEAR] season · final"); "early" =
  // the first 21 days (each section gets This season / Last season).
  function tmSection(title, body, id, note) {
    return '<section class="tm-sec"' + (id ? ' id="' + id + '"' : '') + '><div class="tph"><h2 class="team-section-title">' + title + '</h2>' +
      (note || '') + tpSeasonToggle() + '</div>' + body + '</section>';
  }
  function scoreWord() { return D.sport === 'nhl' ? 'goals' : D.sport === 'mlb' ? 'runs' : 'points'; }
  function num1(x) { var r = Math.round(x * 10) / 10; return String(r); }
  function signedLine(x) { var r = Math.round(x * 10) / 10; return (r > 0 ? '+' : '') + r; }
  function priceTxt(p) { return typeof p === 'number' ? (p > 0 ? '+' : '') + Math.round(p) : '-'; }
  function shortDate(g) { return g.start ? new Date(g.start).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' }) : ''; }
  function numDate(g) { return g.start ? new Date(g.start).toLocaleDateString('en-US', { month: 'numeric', day: 'numeric', timeZone: 'America/New_York' }) : ''; }
  function wdDate(g) { return g.start ? new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' }) : ''; }
  function tmScore(g, k, slug) {
    var r = segRes(g, k);
    if (!r || !r.sc) return null;
    return g.home === slug ? r.sc[1] + '-' + r.sc[0] : r.sc[0] + '-' + r.sc[1];
  }
  // the segment the team's headline numbers use: MLB's First Five, else the first
  function tpSeg() { return D.sportType === 'baseball' ? 'f5' : D.segments[0].key; }
  // "1P ML", "1P Over 1.5", "F5 Run Line", "NRFI", "1Q Spread"
  function tpName(p) {
    if (D.sportType === 'baseball' && p.k !== 'game') return { rfi: 'NRFI', ml: 'F5 ML', ats: 'F5 Run Line', total: 'F5 Total' }[p.m];
    return segTag(p.k) + ' ' + { ml: 'ML', ml3: '3-Way', ats: spreadWord(), total: D.sport === 'nhl' && p.k === '1p' ? 'Over 1.5' : 'Total', btts: 'BTTS', per: 'Result', su: 'Result' }[p.m];
  }
  // the sides a record lists, first side = the %: "W-L-T", "O-U", "Y-N", "N-Y"
  function tpSides(m) { return { ml: tieSport() ? 'W-L-T' : 'W-L-P', ml3: 'W-L-T', ats: 'W-L-P', total: 'O-U', btts: 'Y-N', rfi: 'N-Y', per: 'W-L-T', su: 'W-L-T' }[m]; }
  // Home / Away and Situational headers: "1P ML (W-L-T)", "O/U 1.5 (O-U)", "BTTS (Y-N)", "1Q TOTAL (O-U)"
  function tpHead(p) {
    var n = D.sport === 'nhl' ? { ml: '1P ML', total: 'O/U 1.5', btts: 'BTTS', ml3: '3-Way' }[p.m] : tpName(p);
    return n + ' (' + tpSides(p.m) + ')';
  }
  function tpRec(a, m) { return !a.gp ? '-' : a.w + '-' + a.l + (m === 'ml' || m === 'ml3' || m === 'ats' || m === 'per' || m === 'su' ? '-' + a.t : ''); }
  // what each market's % means (2-way ML leaves ties out; 3-way counts them)
  function tpNote(m) {
    return { ml: tieSport() ? 'ML: win % leaves ties out' : 'ML: win % leaves pushes out',
             ml3: '3-Way: win % counts ties (a tied segment loses the bet)', ats: (D.sportType === 'baseball' ? 'Run line' : D.sport === 'nhl' ? 'Puck line' : 'Spread') + ': pushes count in the record, not the %',
             total: D.sport === 'nhl' ? 'Over 1.5 can’t push' : 'Total: pushes leave the record and the %',
             btts: 'BTTS can’t push', rfi: 'NRFI can’t push', per: '2P / 3P: win % counts ties' }[m];
  }
  // every market, oldest-first games per team (the league's top 5 per market)
  var TP_TOP = {};
  function tpTop5(p) {
    var key = p.k + '|' + p.m;
    if (TP_TOP[key]) return TP_TOP[key];
    var by = {};
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { if (g.state === 'final' && g.res) { (by[g.away] = by[g.away] || []).push(g); (by[g.home] = by[g.home] || []).push(g); } }); });
    var rows = Object.keys(by).filter(function(s) { return D.teams[s]; }).map(function(s) { return { s: s, a: tmAgg(s, p.k, p.m, 'all', by[s]) }; })
      .filter(function(x) { return x.a.pct != null && x.a.gp >= 5; });
    rows.sort(function(a, b) { return b.a.pct - a.a.pct; });
    var top = {};
    // a top 5 needs a league to rank: 10+ teams with 5+ games in the market
    if (rows.length >= 10) rows.slice(0, 5).forEach(function(x) { top[x.s] = 1; });
    return (TP_TOP[key] = top);
  }
  // one market's result for the team, as the Matchups cell shows it: the
  // outcome in the cell; w = the team's side happened (green), p = tie or
  // push (gold), n = their side didn't (gray). Game markets (O/U, BTTS,
  // NRFI) show what happened, in green.
  function tpResult(g, k, m, slug) {
    var b = tmBet(g, k, m, slug);
    if (!b) return null;
    var home = g.home === slug, me = tcode(slug), opp = tcode(home ? g.away : g.home), o = segOdds(g, k) || {};
    var cls = b.r === 'T' ? 'p' : b.r === 'W' ? 'w' : 'n', txt, short = null;
    if (m === 'ml' || m === 'ml3' || m === 'per' || m === 'su') txt = b.r === 'T' ? 'Tie' : b.r === 'W' ? me : opp;
    else if (m === 'ats') { var ln = ((o.ats || {})[home ? 'home' : 'away'] || {}).line; txt = me + (typeof ln === 'number' ? ' ' + signedLine(ln) : ''); short = typeof ln === 'number' ? signedLine(ln) : me; }
    // game markets: never win / loss; warm = Over, BTTS Yes, YRFI; cool = Under, No, NRFI
    else if (m === 'total') { txt = b.r === 'T' ? 'Push' : b.r === 'W' ? 'Over' : 'Under'; cls = b.r === 'T' ? 'p' : b.r === 'W' ? 'warm' : 'cool'; }
    else if (m === 'btts') { txt = b.r === 'W' ? 'Yes' : 'No'; cls = b.r === 'W' ? 'warm' : 'cool'; }
    else { txt = b.r === 'W' ? 'NRFI' : 'YRFI'; cls = b.r === 'W' ? 'cool' : 'warm'; }
    return { cls: cls, txt: txt, short: short };
  }
  function tpResCell(g, p, slug, label) {
    var x = tpResult(g, p.k, p.m, slug);
    return '<div class="tp-res">' + (label ? '<span class="tp-gl">' + esc(tpName(p)) + '</span>' : '') +
      '<span class="cell tp-rc' + (x ? ' tp-rc-' + x.cls : '') + '">' + (x ? '<span class="ob-ln">' + (x.short && !label ? '<span class="tn-full">' + esc(x.txt) + '</span><span class="tn-short">' + esc(x.short) + '</span>' : esc(x.txt)) + '</span>' : '<span class="mc-dash">-</span>') + '</span></div>';
  }
  // "Next game: @ TB, Thu" (the Situational toggle)
  function tpNextLabel(g, slug) {
    return 'Next game: ' + (g.home === slug ? 'vs ' : '@ ') + tcode(g.home === slug ? g.away : g.home) + ', ' +
      new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' });
  }
  // the season state from the build, and the early season's Last season data
  var TP = { state: app.getAttribute('data-season') || '', year: app.getAttribute('data-season-year') || '', opening: app.getAttribute('data-opening') || '',
             champ: app.getAttribute('data-champ') || '',
             which: 'this', cur: null, prev: null, prevTried: false, log: 5, sitK: null, haCol: 0 };
  function tpSeasonToggle() {
    if (TP.state !== 'early') return '';
    return '<div class="seg-toggle tp-season" role="group" aria-label="Season"><button class="seg-btn" data-tp-season="this" aria-pressed="' + (TP.which === 'this') + '">This season</button>' +
      '<button class="seg-btn" data-tp-season="last" aria-pressed="' + (TP.which === 'last') + '">Last season</button></div>';
  }
  function tpFinalNote() { return TP.state === 'off' ? '<p class="tp-final">' + esc(TP.year || D.seasonLabel || '') + ' season &middot; final</p>' : ''; }

  function renderTeam() {
    var slug = TEAM;
    if (!TP.cur) TP.cur = D.games;
    var games = teamGames(slug);
    if (!games.length && TP.which === 'this') return;   // keep the server-rendered empty sections
    var finals = games.filter(function(g) { return g.state === 'final'; });
    var graded = finals.filter(function(g) { return g.res; });
    var off = TP.state === 'off';
    var next = off || TP.which === 'last' ? null : games.filter(function(g) { return g.state === 'pre' || g.state === 'in'; })[0];
    var last = finals[finals.length - 1];
    var all = tmMarkets();
    var sname = function(s) { return esc(shortName(s)); };

    // NEXT GAME: title bar, both teams, venue + TV, the best price per market
    function nextHtml() {
      if (off) return '';   // between seasons: the one season card (marketsHtml)
      if (!next) return tmSection('Next Game', emptyNote('No upcoming game scheduled.'));
      var g = next, day = gameDay(g);
      var when = day === todayET() ? 'Today' : wdDate(g);
      var where = [g.ven, (g.tv || []).join(', ')].filter(Boolean).map(esc).join(' &middot; ');
      var teams = '<div class="tp-teams">' + [g.away, g.home].map(function(s, i) {
        return (i ? '<span class="tp-at">@</span>' : '') + '<span class="tp-team">' + badge(s, 32) + teamLink(s, '<span class="tn-full">' + sname(s) + '</span><span class="tn-short">' + esc(tcode(s)) + '</span>') + '</span>';
      }).join('') + '</div>';
      var href = ROOT + SPORT_SLUG + '/odds/' + (D.schedule === 'week' && g.wk ? '?week=' + encodeURIComponent(g.wk) : '?date=' + day) + '#og-' + g.away + '-' + g.home;
      return tmSection('Next Game', '<div class="st-card tp-card"><div class="st-head"><h4>Next game &middot; ' + esc(when) + ' ' +
        esc(new Date(g.start).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })) + ' ET</h4></div>' +
        '<div class="tp-ng">' + teams + (where ? '<p class="tp-where">' + where + '</p>' : '') + startersLine(g, true) + '</div>' +
        '<div id="tpOdds">' + oddsBlocks(g, null, null) + '</div>' +
        '<div class="fr-links">' + (h2hUrl(g.away, g.home) ? '<a class="fr-more" href="' + h2hUrl(g.away, g.home) + '">Full matchup &rarr;</a>' : '') +
        '<a class="fr-more" href="' + href + '">All odds for this game &rarr;</a></div></div>');
    }
    // the team's side in a market: its own (ML, spread, 3-way), else the
    // side its season leans to (Over / Under, BTTS Yes / No, NRFI / YRFI).
    // The segment is at the row's left, so labels leave it out.
    function oddsSide(p) {
      var home = next.home === slug, side = home ? 'home' : 'away', mine = ' · ' + tcode(slug);
      if (p.m === 'ml' || p.m === 'ats' || p.m === 'ml3') return { key: side, label: { ml: 'ML', ml3: '3-Way', ats: D.sportType === 'baseball' ? 'Run Line' : D.sport === 'nhl' ? 'Puck Line' : 'Spread' }[p.m] + mine };
      var first = p.k === 'game' ? gameOverLean() : (function(a) { return a.pct == null || a.pct >= 0.5; })(tmAgg(slug, p.k, p.m, 'all', graded));
      if (p.m === 'total') return { key: first ? 'over' : 'under', label: (first ? 'Over' : 'Under') + (D.sport === 'nhl' && p.k !== 'game' ? ' 1.5' : '') };
      if (p.m === 'btts') return { key: first ? 'yes' : 'no', label: 'BTTS ' + (first ? 'Yes' : 'No') };
      return { key: first ? 'nrfi' : 'yrfi', label: first ? 'NRFI' : 'YRFI' };
    }
    // the full game's total: the side the team's finals went to against the
    // closing full-game total (ESPN), else its first segment's lean
    function gameOverLean() {
      var o = 0, u = 0;
      finals.forEach(function(g) { if (typeof g.ft === 'number' && g.as != null && g.hs != null) { if (g.as + g.hs > g.ft) o++; else if (g.as + g.hs < g.ft) u++; } });
      if (o + u) return o >= u;
      var t = all.filter(function(p) { return p.m === 'total'; })[0], a = t ? tmAgg(slug, t.k, 'total', 'all', graded) : {};
      return a.pct == null || a.pct >= 0.5;
    }
    // the full-game line: the backfill's "game" segment once it's on the
    // game, else ESPN's closing line (fs = the home spread, ft, fml)
    function gameLine(g) {
      var o = (g.odds || {}).game;
      if (o) return o;
      o = {};
      if (g.fml && g.fml.away != null) o.ml = { away: g.fml.away, home: g.fml.home };
      if (typeof g.fs === 'number') o.ats = { away: { line: -g.fs, price: null }, home: { line: g.fs, price: null } };
      if (typeof g.ft === 'number') o.total = { line: g.ft, over: null, under: null };
      return Object.keys(o).length ? o : null;
    }
    // one market's block: its label, the book with the best price and the price.
    // The Game row of a game not started reads the Odds page's `full` block
    // (the full game's books and best price, live from both feeds)
    function oddsBlock(p, g, og, sources, gameOdds) {
      var s = oddsSide(p), mk = p.m === 'rfi' ? 'nrfi_yrfi' : p.m;
      og = p.k === 'game' ? (og && og.full) || null : og;
      var best = og ? ((og.best || {})[p.k] || {})[mk] : null;
      var mine = p.k === 'game' ? (gameOdds || {})[p.m] : ((g.odds || {})[p.k] || {})[mk];
      var o = best || mine, top = null, sub = null, line = null;
      if (o) {
        if (p.m === 'ats') { var a = o[s.key] || {}; if (typeof a.line === 'number') { top = signedLine(a.line); sub = a.price != null ? priceTxt(a.price) : null; line = a.line; } }
        else if (p.m === 'total') { if (o[s.key] != null || (p.k === 'game' && o.line != null)) { top = (s.key === 'over' ? 'o' : 'u') + (o.line != null ? num1(o.line) : ''); sub = o[s.key] != null ? priceTxt(o[s.key]) : null; line = o.line; } }
        else if (o[s.key] != null) top = priceTxt(o[s.key]);
      }
      var book = '';
      if (best && og && sources && top) {
        var price = p.m === 'ats' ? (o[s.key] || {}).price : o[s.key], rows = (((og.books || {})[p.k] || {})[mk]) || {}, id = null;
        // sportsbooks, then exchanges, then the Consensus price (a market only it prices)
        ['book', 'exch', 'consensus'].forEach(function(pass) {
          Object.keys(rows).forEach(function(b) {
            if (id || (sources[b] || {}).nb || (b === 'consensus') !== (pass === 'consensus')) return;
            if (pass !== 'consensus' && !!(sources[b] || {}).x !== (pass === 'exch')) return;
            var r = rows[b], v = r && r[s.key], vp = v && typeof v === 'object' ? v.price : v;
            if (vp !== price) return;
            if (p.m === 'ats' && v.line !== line) return;
            if (p.m === 'total' && r.line !== line) return;
            id = b;
          });
        });
        var src = id ? sources[id] || {} : null;
        if (src) book = src.logo ? '<img class="sl-book" src="' + ROOT + esc(src.logo) + '" alt="' + esc(src.name || id) + '" title="' + esc(src.name || id) + '" loading="lazy">' : '<span class="sl-bname">' + esc(src.name || id) + '</span>';
      }
      // ESPN's full-game line is DraftKings' close
      if (p.k === 'game' && top && !best && !(g.odds || {}).game && sources && sources['1']) {
        var dk = sources['1'];
        book = dk.logo ? '<img class="sl-book" src="' + ROOT + esc(dk.logo) + '" alt="' + esc(dk.name) + '" title="' + esc(dk.name) + '" loading="lazy">' : '<span class="sl-bname">' + esc(dk.name) + '</span>';
      }
      var cell = top ? '<span class="cell tp-best"><span class="ob-ln">' + esc(top) + '</span>' + (sub ? '<span class="ob-pr">' + esc(sub) + '</span>' : '') + '</span>'
        : '<span class="cell"><span class="mc-dash">-</span></span>';
      return { top: !!top, html: '<div class="tp-ob"><span class="tp-gl">' + esc(s.label) + '</span><span class="tp-ob-row"><span class="tp-book">' + book + '</span>' + cell + '</span></div>' };
    }
    // a row per segment (its label at the left, its markets as columns),
    // then the full game; every row has the same columns so they line up.
    // A market with no line is left out, and a row with none at all
    function oddsBlocks(g, og, sources) {
      var rows = D.segments.filter(function(sg) { return tmMarkets(sg.key).length; }).map(function(sg) {
        return { label: sg.key === '1i' ? '1st Inning' : sg.key === 'f5' ? 'F5' : sg.tag, ps: tmMarkets(sg.key) };
      });
      var shown = function(bs) { return bs.filter(function(b) { return b.top; }).map(function(b) { return b.html; }); };
      var segHtml = rows.map(function(r) {
        return { label: r.label, blocks: shown(r.ps.map(function(p) { return oddsBlock(p, g, og, sources); })) };
      }).filter(function(r) { return r.blocks.length; });
      var gl = gameLine(g) || (og && og.full ? {} : null);
      if (gl) {
        // the full game's markets: NHL and MLB moneyline, puck / run line, total;
        // the spread sports in their segments' order
        var order = D.sport === 'nhl' || D.sportType === 'baseball' ? ['ml', 'ats', 'total'] : rows[0].ps.map(function(p) { return p.m; }).filter(function(m) { return m === 'ml' || m === 'ats' || m === 'total'; });
        var gb = shown(order.map(function(m) { return oddsBlock({ k: 'game', m: m }, g, og, sources, gl); }));
        if (gb.length) segHtml.push({ label: 'Game', blocks: gb });
      }
      if (!segHtml.length) return '<p class="tp-none">Lines not posted yet.</p>';
      var n = Math.max.apply(null, segHtml.map(function(r) { return r.blocks.length; }));
      return '<div class="tp-odds' + (n > 3 ? ' tp-n4' : '') + '" style="--n:' + n + '">' + segHtml.map(function(r) {
        while (r.blocks.length < n) r.blocks.push('<div class="tp-ob tp-ob-empty" aria-hidden="true"></div>');
        return '<div class="tp-orow"><span class="tp-oseg">' + esc(r.label) + '</span><div class="tp-ocols">' + r.blocks.join('') + '</div></div>';
      }).join('') + '</div>';
    }
    function loadOdds() {
      if (!next) return;
      var day = gameDay(next);
      Promise.all([fetch(dataUrl(SPORT_SLUG + '/odds.json')).then(function(r) { return r.ok ? r.json() : {}; }),
                   fetch(dataUrl(SPORT_SLUG + '/odds/' + day + '.json')).then(function(r) { return r.ok ? r.json() : { games: [] }; })]).then(function(x) {
        var og = (x[1].games || []).filter(function(o) { return o.away === next.away && o.home === next.home; })[0], box = document.getElementById('tpOdds');
        if (box) box.innerHTML = oddsBlocks(next, og || null, x[0].sources || {});   // the sources name the Game row's book too
      }).catch(function() {});
    }
    // between seasons: one section, "[YEAR] SEASON MARKETS · FINAL"; its title
    // bar has the champion's trophy on the left (the title winner only) and
    // "NEXT SEASON STARTS · MAR 24 · 125 DAYS" (or "· DATE TBA") on the right
    function finalHtml() {
      var right = 'Next season starts &middot; ';
      if (TP.opening) {
        var d = new Date(TP.opening + 'T12:00:00Z'), n = Math.max(0, Math.round((d - new Date(todayET() + 'T12:00:00Z')) / 864e5));
        right += d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) + ' &middot; ' + n + ' day' + (n === 1 ? '' : 's');
      } else right += 'date TBA';
      var champ = TP.champ ? '<span aria-hidden="true">\uD83C\uDFC6</span> ' + esc(TP.champ) : '';
      return tmSection(esc(TP.year || D.seasonLabel || '') + ' Season Markets &middot; Final', '<div class="st-card tp-card"><div class="st-head tp-split"><h4>' + champ +
        '</h4><span class="tp-hr">' + right + '</span></div>' + marketCards() + '</div>', 'tpMarkets');
    }
    // LAST GAME: the header row (both logos, names on desktop / codes on
    // phones, the final score: "76ers 121 @ Magic 116 · Final"), then
    // desktop: a row per segment, the segment and its score at the left
    // ("1P 0-0", "1Q BOS 30-24"), then every market with every side, the
    // closing price under the line; phones: only the side that settled each
    // bet, its market label above it (NHL a 2 x 2 grid; the rest a column
    // per segment).
    function lastHtml() {
      if (!last) return tmSection('Last Game', emptyNote('No games played yet.'));
      var g = last, fin = g.as != null && g.hs != null;
      var title = 'Last game &middot; ' + esc(wdDate(g));
      if (g.post && g.note) title = esc(String(g.note).replace(/\s*-\s*/, ' ')) + ' &middot; ' + esc(shortDate(g));
      var ot = g.ot ? ' ' + esc(g.ot) : '';
      var teams = '<div class="tp-teams tp-lg-teams">' + [g.away, g.home].map(function(s, i) {
        return (i ? '<span class="tp-at">@</span>' : '') + '<span class="tp-team">' + badge(s, 32) + teamLink(s, '<span class="tn-full">' + sname(s) + '</span><span class="tn-short">' + esc(tcode(s)) + '</span>') +
          (fin ? ' <span class="tp-lg-pts">' + (i ? g.hs : g.as) + '</span>' : '') + '</span>';
      }).join('') + (fin ? '<span class="tp-at">&middot; Final' + ot + '</span>' : '') + '</div>';
      var segs = D.segments.filter(function(sg) { return tmMarkets(sg.key).length; });
      // the segment and its score, the leader first ("LAL 34-29"); a tie "Tied 28-28"
      function segHead(sg) {
        var r = (g.res || {})[sg.key], lbl = sg.key === '1i' ? '1st Inning' : sg.tag;
        if (!r || !r.sc) return { k: lbl, sc: '-' };
        var a = r.sc[0], h = r.sc[1];
        return { k: lbl, sc: a === h ? 'Tied ' + a + '-' + h : tcode(a > h ? g.away : g.home) + ' ' + Math.max(a, h) + '-' + Math.min(a, h) };
      }
      // phones: the segment's whole name ("1st Quarter", "First Five"), never cut
      function segName(sg) { return sg.key === 'f5' ? 'First Five' : sg.label; }
      var desk = segs.map(function(sg) {
        var h = segHead(sg);
        return '<div class="tp-lg-row"><div class="tp-lg-seg"><span class="tp-gl">' + esc(h.k) + '</span><span class="tp-lg-sc">' + esc(h.sc) + '</span></div>' +
          '<div class="tp-lg-mks">' + tmMarkets(sg.key).map(function(p) {
            var sides = lastSides(g, p);
            return '<div class="tp-lg-mk"><span class="tp-gl">' + esc(lastLabel(p)) + '</span><div class="tp-lg-sides tp-lg-n' + sides.length + '">' +
              sides.map(lastSideCell).join('') + '</div></div>';
          }).join('') + '</div></div>';
      }).join('');
      // phones: the settled side of each bet
      function settled(p) {
        var x = settledSide(lastSides(g, p));
        return '<div class="tp-res"><span class="tp-gl">' + esc(lastLabel(p)) + '</span>' + (x ? lastSideCell(x) : '<span class="cell"><span class="mc-dash">-</span></span>') + '</div>';
      }
      var phone;
      if (D.sport === 'nhl') {
        var h0 = segHead(segs[0]);
        phone = '<div class="tp-lgp-col"><div class="tp-lg-seg"><span class="tp-gl">' + esc(segName(segs[0])) + '</span><span class="tp-lg-sc">' + esc(h0.sc) + '</span></div>' +
          '<div class="tp-lgp-grid">' + tmMarkets(segs[0].key).map(settled).join('') + '</div></div>';
      } else {
        phone = segs.map(function(sg) {
          var h = segHead(sg);
          return '<div class="tp-lgp-col"><div class="tp-lg-seg"><span class="tp-gl">' + esc(segName(sg)) + '</span><span class="tp-lg-sc">' + esc(h.sc) + '</span></div>' +
            tmMarkets(sg.key).map(settled).join('') + '</div>';
        }).join('');
      }
      return tmSection('Last Game', '<div class="st-card tp-card"><div class="st-head"><h4>' + title + '</h4></div>' + teams +
        '<div class="tp-lgd">' + desk + '</div><div class="tp-lgp tp-lgp-' + (D.sport === 'nhl' ? 1 : segs.length) + '">' + phone + '</div></div>');
    }
    // the market's label, as the Next Game card names it: "1P ML", "1P O/U 1.5",
    // "1P BTTS", "1P 3-Way"; spread sports "Spread", "Total", "ML" (the
    // segment is at the row's left); MLB "NRFI / YRFI", "F5 ML", "F5 Run Line", "F5 Total"
    function lastLabel(p) {
      if (D.sportType === 'baseball') return { rfi: 'NRFI / YRFI', ml: 'F5 ML', ats: 'F5 Run Line', total: 'F5 Total' }[p.m];
      if (D.sport === 'nhl') return seg(p.k).tag + ' ' + { ml: 'ML', ml3: '3-Way', total: 'O/U 1.5', btts: 'BTTS' }[p.m];
      return { ml: 'ML', ats: spreadWord(), total: 'Total', btts: 'BTTS' }[p.m];
    }
    // every side of a market in the last game: the line, its closing price
    // ("-" when none was saved) and how it settled: w won, n lost (dimmed),
    // p push; Total / BTTS / NRFI-YRFI warm or cool for the side that happened
    function lastSides(g, p, bare) {
      var r = segRes(g, p.k) || {}, o = segOdds(g, p.k) || {}, home = g.home === slug;
      if (!r.sc || r.na) r = {};   // not graded: the lines only
      var us = home ? 'home' : 'away', them = home ? 'away' : 'home';
      function sideRes(x, side) {   // a result read from the away side, for `side`
        if (!x || x === 'NA') return null;
        if (x === 'P' || x === 'T') return 'p';
        return (side === 'away') === (x === 'W') ? 'w' : 'n';
      }
      if (p.m === 'ml') {
        return [us, them].map(function(sd) { return { ln: tcode(g[sd]), pr: (o.ml || {})[sd], cls: sideRes(r.su, sd), mine: sd === us }; });
      }
      if (p.m === 'ats') {
        return [us, them].map(function(sd) {
          var a = (o.ats || {})[sd] || {};
          return { ln: tcode(g[sd]) + (typeof a.line === 'number' ? ' ' + signedLine(a.line) : ''), pr: a.price, cls: sideRes(r.ats, sd), mine: sd === us };
        });
      }
      if (p.m === 'ml3') {
        var su = r.su && r.su !== 'NA' ? r.su : null;
        return [[us, tcode(g[us])], ['draw', 'Tie'], [them, tcode(g[them])]].map(function(x) {
          var won = !su ? null : su === 'T' ? x[0] === 'draw' : x[0] !== 'draw' && (x[0] === 'away') === (su === 'W');
          return { ln: x[1], pr: (o.ml3 || {})[x[0]], cls: won == null ? null : won ? 'w' : 'n', mine: x[0] === us };
        });
      }
      if (p.m === 'total') {
        var t = o.total || {}, ln = bare ? '' : typeof t.line === 'number' ? ' ' + num1(t.line) : D.sport === 'nhl' ? ' 1.5' : '';
        return [['over', 'O', 'O', 'warm'], ['under', 'U', 'U', 'cool']].map(function(x) {
          var c = !r.tot || r.tot === 'NA' ? null : r.tot === 'P' ? 'p' : r.tot === x[2] ? x[3] : 'n';
          return { ln: x[1] + ln, pr: t[x[0]], cls: c };
        });
      }
      if (p.m === 'btts') {
        return [['yes', 'Yes', 'Y', 'warm'], ['no', 'No', 'N', 'cool']].map(function(x) {
          return { ln: x[1], pr: (o.btts || {})[x[0]], cls: r.btts === 'Y' || r.btts === 'N' ? (r.btts === x[2] ? x[3] : 'n') : null };
        });
      }
      return [['nrfi', 'NRFI', 'N', 'cool'], ['yrfi', 'YRFI', 'Y', 'warm']].map(function(x) {
        return { ln: x[1], pr: (o.nrfi_yrfi || {})[x[0]], cls: r.rfi === 'Y' || r.rfi === 'N' ? (r.rfi === x[2] ? x[3] : 'n') : null };
      });
    }
    // the side that settled a bet: the winner (or what happened); a push, our side
    function settledSide(sides) {
      var won = sides.filter(function(x) { return x.cls === 'w' || x.cls === 'warm' || x.cls === 'cool'; })[0];
      var push = sides.filter(function(x) { return x.cls === 'p'; });
      return won || push.filter(function(x) { return x.mine; })[0] || push[0] || null;
    }
    function lastSideCell(x) {
      return '<span class="cell tp-rc' + (x.cls ? ' tp-rc-' + x.cls : '') + '"><span class="ob-ln">' + esc(x.ln) + '</span><span class="ob-pr">' +
        (typeof x.pr === 'number' ? esc(priceTxt(x.pr)) : '-') + '</span></span>';
    }
    // SEASON MARKETS: a row per segment, its label at the left (as the Next
    // Game card), one card per market (green border: top 5 in the league);
    // phones: each row stacks as its own group. Under the first segments,
    // the Full Run's rows in the Premium style (frMarkets).
    function marketCards() {
      var notes = [], fr = frRows();
      var rows = D.segments.filter(function(sg) { return tmMarkets(sg.key).length; }).map(function(sg) {
        return { label: sg.key === '1i' ? '1st Inning' : sg.key === 'f5' ? 'F5' : sg.tag, ps: tmMarkets(sg.key) };
      }).concat(fr);
      var n = Math.max.apply(null, rows.map(function(r) { return r.ps.length; }));
      var html = rows.map(function(r) {
        var cards = r.ps.map(function(p) {
          if (p.m === 'gpg') return gpgCard(p);
          var a = tmAgg(slug, p.k, p.m, 'all', graded), top = a.gp && p.m !== 'per' && p.m !== 'su' && tpTop5(p)[slug];
          var nt = tpNote(p.m);
          if (nt && notes.indexOf(nt) === -1) notes.push(nt);
          return '<div class="tp-mk' + (top ? ' tp-top' : '') + '"><span class="tp-gl">' + esc(tpMkName(p)) + '</span><span class="tp-big">' + tmPct(a.pct) + '</span>' +
            '<span class="tp-rec">' + tpRec(a, p.m) + '</span>' + (p.m === 'ml' || p.m === 'ml3' || p.m === 'ats' || a.priced ? tmUnits(a) : '') + '</div>';
        });
        while (cards.length < n) cards.push('<div class="tp-mk-empty" aria-hidden="true"></div>');
        return '<div class="tp-mrow' + (r.fr ? ' fr-row' : '') + '"><span class="tp-oseg">' + esc(r.label) + (r.fr ? '<span class="fr-tag">Premium</span>' : '') + '</span>' +
          '<div class="tp-mks">' + cards.join('') + (r.note ? '<p class="fr-note">' + esc(r.note) + '</p>' : '') + '</div></div>';
      });
      // PREMIUM.fullRun on: free visitors see the first Full Run row, the rest blurred
      html = lockFrom(html, rows.length - fr.length + 1, 'fullRun');
      return '<div class="tp-mrows' + (n > 3 ? ' tp-n4' : '') + '" style="--n:' + n + '">' + html + '</div><p class="tp-foot">' + esc(notes.join(' · ')) + '. Green border: top 5 in ' + esc(leagueIn()) + '.</p>';
    }
    // the Full Run rows: 2nd Half (NHL 2nd and 3rd Period), then the Full
    // Game. A 2nd Half with fewer than FR_MIN graded games for a market
    // shows only won / lost the 2H until the lines backfill fills it.
    function frRows() {
      return (D.fullRun || []).map(function(sg) {
        var ps = frMarkets(sg.key), note = null;
        if (sg.key === '2h' && ps.some(function(p) { return tmAgg(slug, p.k, p.m, 'all', graded).gp < FR_MIN; })) {
          ps = [{ k: '2h', m: 'su' }];
          note = 'Lines from Nov 22';
        }
        return { label: sg.tag, ps: ps, fr: 1, note: note };
      });
    }
    // NHL periods: goals per game, the team's then the opponent's
    function gpgCard(p) {
      var f = 0, a = 0, n = 0;
      graded.forEach(function(g) {
        var r = segRes(g, p.k);
        if (!r || !r.sc) return;
        var home = g.home === slug;
        f += r.sc[home ? 1 : 0]; a += r.sc[home ? 0 : 1]; n++;
      });
      return '<div class="tp-mk"><span class="tp-gl">Goals per game</span><span class="tp-big">' + (n ? (f / n).toFixed(1) : '-') + '</span>' +
        '<span class="tp-rec">' + (n ? 'Allowed ' + (a / n).toFixed(1) : '-') + '</span></div>';
    }
    // a market's name inside its segment's row: "ML", "Over 1.5", "Run Line",
    // "NRFI"; the total box is the Over rate, so it says Over
    function tpMkName(p) {
      if (p.m === 'per' || p.m === 'su') return 'Won the ' + segTag(p.k);
      if (D.sportType === 'baseball') return { rfi: 'NRFI', ml: 'ML', ats: 'Run Line', total: 'Over' }[p.m];
      return { ml: 'ML', ml3: '3-Way', ats: spreadWord(), total: D.sport === 'nhl' && p.k === '1p' ? 'Over 1.5' : 'Over', btts: 'BTTS' }[p.m];
    }
    function marketsHtml() { return off ? finalHtml() : tmSection('Season Markets', marketCards(), 'tpMarkets', tpFinalNote()); }
    // BY STARTING PITCHER / GOALIE: a row per starter with 3+ starts for this
    // team, most starts first; "Next game" on tonight's starter
    var SP_MIN = 3;
    function startersHtml() {
      if (!hasStarters()) return '';
      var rows = starterRows(slug, graded, SP_MIN);
      var mlb = D.sportType === 'baseball', title = mlb ? 'By Starting Pitcher' : 'By Starting Goalie';
      if (!rows.length) return tmSection(title, '<p class="tp-none">No ' + (mlb ? 'pitcher' : 'goalie') + ' with ' + SP_MIN + '+ starts yet.</p>', 'tpStarters', tpFinalNote());
      var np = next ? starterOf(next, next.home === slug ? 'home' : 'away') : null;
      function cell(a, m, units) {
        if (!a.gp) return '-';
        return '<span class="h2h-pct">' + tmPct(a.pct) + '</span> <span class="tp-hr2">(' + tpRec(a, m) + ')</span>' + (units ? ' ' + tmUnits(a) : '');
      }
      function ou(a) { return a.gp ? a.w + '-' + a.l : '-'; }
      var cols = mlb ? [['NRFI %', function(gs) { return cell(tmAgg(slug, '1i', 'rfi', 'all', gs), 'rfi'); }],
                        ['F5 ML %', function(gs) { return cell(tmAgg(slug, 'f5', 'ml', 'all', gs), 'ml', true); }],
                        ['F5 Run Line %', function(gs) { return cell(tmAgg(slug, 'f5', 'ats', 'all', gs), 'ats', true); }],
                        ['F5 O/U (O-U)', function(gs) { return ou(tmAgg(slug, 'f5', 'total', 'all', gs)); }]]
        : [['1P ML % (W-L-T)', function(gs) { return cell(tmAgg(slug, '1p', 'ml', 'all', gs), 'ml'); }],
           ['O/U 1.5 (O-U)', function(gs) { return ou(tmAgg(slug, '1p', 'total', 'all', gs)); }],
           ['BTTS (Y-N)', function(gs) { return ou(tmAgg(slug, '1p', 'btts', 'all', gs)); }],
           ['1P goals allowed', function(gs) {
             var n = 0, ga = 0;
             gs.forEach(function(g) { var r = segRes(g, '1p'); if (r && r.sc) { ga += r.sc[g.home === slug ? 0 : 1]; n++; } });
             return n ? (ga / n).toFixed(2) : '-';
           }]];
      var head = '<tr><th>' + (mlb ? 'Pitcher' : 'Goalie') + '</th><th class="num">Starts</th>' + cols.map(function(c) { return '<th class="num">' + esc(c[0]) + '</th>'; }).join('') + '</tr>';
      var body = rows.map(function(r) {
        var tag = np && String(np.id) === String(r.p.id) ? ' <span class="sit-tn">Next game</span>' : '';
        return '<tr><th scope="row" class="tp-pl"><span class="tn-full">' + esc(r.p.name || starterLast(r.p)) + '</span><span class="tn-short">' + esc(starterLast(r.p)) + '</span>' + tag + '</th>' +
          '<td class="num">' + r.games.length + '</td>' + cols.map(function(c) { return '<td class="num">' + c[1](r.games) + '</td>'; }).join('') + '</tr>';
      }).join('');
      return tmSection(title, '<div class="st-card tp-card h2h-x"><table class="tp-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>', 'tpStarters', tpFinalNote());
    }
    // CURRENT STREAKS: chips, 3+ only; between seasons, the season's longest per market
    function streakText(m, kind, k) {
      var tag = D.sportType === 'baseball' ? (m === 'rfi' ? '' : 'F5 ') : seg(k).tag + ' ';
      if (m === 'ml') return tag + (kind === 'W' ? 'wins' : 'losses');
      if (m === 'ats') return tag + (kind === 'W' ? 'covers' : 'non-covers');
      if (m === 'total') return tag + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '');
      if (m === 'btts') return 'BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
      return kind === 'Y' ? 'YRFI' : 'NRFI';
    }
    function chip(n, m, kind, k, dates) {
      return '<div class="tp-chip"><span class="tp-cn ' + heatCls(n) + '">' + n + '</span><span class="tp-ct">' + n + ' straight ' + esc(streakText(m, kind, k)) +
        (dates ? '<small>' + dates + '</small>' : '') + '</span></div>';
    }
    function eachSeq(fn) {
      D.segments.forEach(function(s) {
        var seqs = teamSeqs('9999-12-31', s.key), done = {};
        tmMarkets(s.key).forEach(function(p) {
          var m = p.m === 'ml3' ? 'ml' : p.m;
          if (done[m] || !HIT[m]) return;
          done[m] = 1;
          fn(((seqs[slug] || {})[m]) || [], m, s.key);
        });
      });
    }
    function streaksHtml() {
      var rows = [];
      if (off) {
        // the longest run of either side in each market, with its dates
        var seen = {};
        all.forEach(function(p) {
          var m = p.m === 'ml3' ? 'ml' : p.m;
          if (seen[p.k + m]) return;
          seen[p.k + m] = 1;
          var best = null, cur = null;
          graded.forEach(function(g) {
            var b = tmBet(g, p.k, m, slug);
            if (!b) return;
            if (b.r === 'T') { cur = null; return; }
            cur = cur && cur.r === b.r ? { r: b.r, n: cur.n + 1, a: cur.a, b: g } : { r: b.r, n: 1, a: g, b: g };
            if (!best || cur.n > best.n) best = cur;
          });
          if (!best || best.n < 2) return;
          var kind = best.r === 'W' ? HIT[m] : MISS[m];
          if (m === 'rfi') kind = best.r === 'W' ? 'N' : 'Y';   // tmBet: W = NRFI
          rows.push({ n: best.n, html: chip(best.n, m, kind, p.k, esc(shortDate(best.a)) + ' - ' + esc(shortDate(best.b))) });
        });
        rows.sort(function(a, b) { return b.n - a.n; });
        return tmSection('Longest Streaks of ' + esc(TP.year || D.seasonLabel || ''), rows.length ? '<div class="tp-chips">' + rows.map(function(r) { return r.html; }).join('') + '</div>' :
          '<p class="tp-none">No streaks of 2 or more.</p>');
      }
      eachSeq(function(seq, m, k) {
        var st = streakOf(seq);
        if (st && st.n >= 3) rows.push({ n: st.n, html: chip(st.n, m, st.kind, k) });
      });
      rows.sort(function(a, b) { return b.n - a.n; });
      return tmSection('Current Streaks', rows.length ? '<div class="tp-chips">' + rows.map(function(r) { return r.html; }).join('') + '</div>' :
        '<p class="tp-none">No active streaks of 3 or more.</p>');
    }
    // GAME LOG: Date · Opponent · segment score · a result cell per market ·
    // Final; a pill per segment, the Full Run's last (gold dot; a lock while
    // PREMIUM.fullRun keeps them from free visitors)
    function logHtml() {
      var segs = D.segments.filter(function(s) { return tmMarkets(s.key).length; }).concat(D.fullRun || []);
      var k = tm.logK && anySeg(tm.logK) ? tm.logK : segs[0].key;
      var ms = frSeg(k) ? (k === '2p' || k === '3p' ? [{ k: k, m: 'per' }] : frMarkets(k)) : tmMarkets(k), sk = k;
      var locked = !!frSeg(k) && premiumLocked('fullRun');
      // only games with a saved line for the segment (CLAUDE.md); the NHL
      // periods have no lines, and the 2nd Half keeps every game while its
      // row still shows only won / lost the 2H (frRows)
      var all = k === '2p' || k === '3p' || k === '2h' && frMarkets('2h').some(function(p) { return tmAgg(slug, p.k, p.m, 'all', graded).gp < FR_MIN; });
      var list = finals.filter(function(g) { return all || segLined(g, k); }).reverse(), shown = list.slice(0, TP.log);
      var rows = shown.map(function(g) {
        var home = g.home === slug, opp = home ? g.away : g.home;
        var fin = g.as != null && g.hs != null ? (home ? g.hs + '-' + g.as : g.as + '-' + g.hs) + (g.ot ? ' ' + esc(g.ot) : '') : '-';
        var oppHtml = '<span class="tp-vs">' + (home ? 'vs' : '@') + '</span>' + badge(opp, 20) + '<span class="tp-oc">' + esc(tcode(opp)) + '</span>';
        var pair = h2hUrl(slug, opp);
        return '<tr><td class="tp-d"><span class="tn-full">' + esc(shortDate(g)) + '</span><span class="tn-short">' + esc(numDate(g)) + '</span></td><td class="tp-o">' + (teamUrl(opp) ? '<a href="' + teamUrl(opp) + '">' + oppHtml + '</a>' : oppHtml) +
          (pair ? '<a class="tp-h2h" href="' + pair + '" title="Head to head"><span class="tn-full">Head to head</span><span class="tn-short">H2H</span></a>' : '') + '</td>' +
          '<td class="num tp-sc">' + (tmScore(g, sk, slug) || '-') + '</td>' + ms.map(function(p) { return '<td class="tp-lc">' + logCell(g, p) + '</td>'; }).join('') +
          '<td class="num tp-fin">' + fin + '</td></tr>';
      }).join('');
      var more = list.length > shown.length ? '<button class="seg-btn tp-more" id="tpLogMore" type="button">' + (TP.log === 5 ? 'Show 10 more' : 'Load more') + '</button>' : '';
      var segBtns = segs.length > 1 ? '<div class="seg-toggle" id="tmLogSeg">' + segs.map(function(s) { return segPill(s, s.key === k, !!frSeg(s.key), 'data-log-seg', s.key === 'f5' ? 'First 5' : s.label); }).join('') + '</div>' : '';
      var head = '<tr><th>Date</th><th>Opp</th><th class="num tp-sc">' + esc(sk === '1i' ? '1st' : segTag(sk)) + '</th>' + ms.map(function(p) {
        var short = { ml: 'ML', ml3: '3W', ats: D.sportType === 'baseball' ? 'RL' : D.sport === 'nhl' ? 'PL' : 'Spread', total: D.sport === 'nhl' && p.k === '1p' ? 'O/U' : 'Total', btts: 'BTTS', rfi: 'NRFI', per: 'Result' }[p.m];
        var full = D.sport === 'nhl' && p.k === '1p' ? seg(p.k).tag + ' ' + { ml: 'ML', ml3: '3-Way', total: 'O/U 1.5', btts: 'BTTS' }[p.m] : tpName(p);
        return '<th class="tp-lc"><span class="tn-full">' + esc(full) + '</span><span class="tn-short">' + esc(short) + '</span></th>'; }).join('') +
        '<th class="num tp-fin">Final</th></tr>';
      var table = lockFrom(['<div class="st-card tp-card tp-log"><table class="tp-table"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div>'], locked ? 0 : 1, 'fullRun');
      return tmSection('Game Log', segBtns + (list.length ? table + (locked ? '' : more)
        : emptyNote(finals.length ? 'No games with a ' + segTag(k) + ' line yet.' : 'No games played yet.')), 'tmLog', tpFinalNote());
    }
    // a game log cell: ML, 3-way and spread / run line show the page team's
    // own side and price, graded from its side; Total, BTTS and NRFI the side
    // that happened. No saved price: "-" in a plain cell, never a result color
    function logCell(g, p) {
      if (p.m === 'per') return tpResCell(g, p, slug, false);
      var sides = lastSides(g, p, D.sport === 'nhl');
      var x = p.m === 'ml' || p.m === 'ml3' || p.m === 'ats' ? sides.filter(function(y) { return y.mine; })[0] : settledSide(sides);
      return '<div class="tp-res">' + (x && x.cls && typeof x.pr === 'number' ? lastSideCell(x) : '<span class="cell tp-rc"><span class="mc-dash">-</span></span>') + '</div>';
    }
    // HOME / AWAY: desktop every market side by side; phones one market (pills)
    function homeAwayHtml() {
      var cols = all;
      if (TP.haCol >= cols.length) TP.haCol = 0;
      function cellOf(p, side) {
        var a = tmAgg(slug, p.k, p.m, side, graded);
        if (!a.gp) return '-';
        // 60%+ / 40% and under with 5+ graded games: side markets green / red,
        // Total, BTTS and NRFI amber / purple (only the %)
        var c = '';
        var pc = a.pct == null ? 50 : Math.round(a.pct * 100);   // the shown number
        if (a.gp >= 5 && (pc >= 60 || pc <= 40)) {
          var hi = pc >= 60, side = p.m === 'ml' || p.m === 'ml3' || p.m === 'ats';
          c = ' tp-hp-' + (side ? (hi ? 'up' : 'down') : (hi ? 'warm' : 'cool'));
        }
        return '<span class="tp-hp' + c + '">' + tmPct(a.pct) + '</span> <span class="tp-hr2">(' + tpRec(a, p.m) + ')</span>';
      }
      var pills = '<div class="seg-toggle tp-pills-phone" role="group" aria-label="Market">' + cols.map(function(p, i) {
        return '<button class="seg-btn" data-ha-col="' + i + '" aria-pressed="' + (i === TP.haCol) + '">' + esc(tpName(p)) + '</button>'; }).join('') + '</div>';
      var body = [['home', 'Home'], ['away', 'Away']].map(function(sd) {
        return '<tr><th>' + sd[1] + '</th>' + cols.map(function(p, i) { return '<td class="num' + (i === TP.haCol ? ' tp-on' : '') + '">' + cellOf(p, sd[0]) + '</td>'; }).join('') + '</tr>';
      }).join('');
      return tmSection('Home / Away', pills + '<div class="st-card tp-card tp-ha"><table class="tp-table"><thead><tr><th></th>' +
        cols.map(function(p, i) { return '<th class="num' + (i === TP.haCol ? ' tp-on' : '') + '">' + esc(tpHead(p)) + '</th>'; }).join('') + '</tr></thead><tbody>' + body + '</tbody></table></div>',
        'tpHA', tpFinalNote());
    }
    // SITUATIONAL RESULTS (assets/situational.js team view)
    var SID = { ml: 'su', ml3: 'ml3', ats: 'ats', total: 'tot', btts: 'btts', rfi: 'rfi' };
    function sitHtml() {
      if (!splitReg()) return tmSection('Situational Results', emptyNote('Situational Results aren’t set up for ' + esc(D.label) + ' yet.'));
      return tmSection('Situational Results', '<div id="teamSit" class="tp-sit"></div>', 'tpSit', tpFinalNote());
    }
    function drawSit() {
      var e = sitEngine(), box = document.getElementById('teamSit');
      if (!e || !box) return;
      var k = TP.sitK && seg(TP.sitK) ? TP.sitK : D.segments[0].key;
      var cols = (periodFamily() ? all : tmMarkets(k)).map(function(p) {
        return { k: p.k, id: SID[p.m], head: tpHead(p), short: tpName(p), priced: p.m === 'ml' || p.m === 'ml3' || p.m === 'ats' };
      });
      var nx = next ? { id: next.id, label: tpNextLabel(next, slug), dow: window.RTYBSit.etParts(next.start).dow } : null;
      var tm = team(slug);
      e.team(box, { slug: slug, cols: cols, segs: periodFamily() ? null : D.segments, next: nx, name: { d: shortName(slug), m: tm.code || shortName(slug) },
        onSeg: function(x) { TP.sitK = x; drawSit(); } });
    }
    // LINE HISTORY + RESULTS HISTORY: tiles (label strip, one big value, one muted line)
    function tile(label, big, sub) {
      return '<div class="tp-tile"><span class="tp-tl">' + esc(label) + '</span><span class="tp-tv">' + big + '</span><span class="tp-ts">' + (sub || '&nbsp;') + '</span></div>';
    }
    function avg(xs) { return xs.reduce(function(a, b) { return a + b; }, 0) / xs.length; }
    // prices average through their implied probability (-150 and +130 don't average to -10)
    function avgPrice(xs) {
      var p = avg(xs.map(function(x) { return x < 0 ? -x / (-x + 100) : 100 / (x + 100); }));
      return p >= 0.5 ? -100 * p / (1 - p) : 100 * (1 - p) / p;
    }
    function linesHtml() {
      var k = tpSeg(), tag = D.sportType === 'baseball' ? 'F5' : seg(k).tag;
      function side(g) { return g.home === slug ? 'home' : 'away'; }
      function o(g) { return (g.odds || {})[k] || {}; }
      var useMl = hasMl(k);
      // 1: the segment's moneyline (spread sports without one: the spread)
      function mlv(g) { return useMl ? (o(g).ml || {})[side(g)] : ((o(g).ats || {})[side(g)] || {}).line; }
      function fmt1(v) { return useMl ? priceTxt(v) : signedLine(v); }
      function avgOf(where, f, isPrice) {
        var xs = finals.filter(function(g) { return (g.home === slug) === (where === 'home'); }).map(f).filter(function(v) { return typeof v === 'number'; });
        return xs.length ? (isPrice ? avgPrice(xs) : avg(xs)) : null;
      }
      var mh = avgOf('home', mlv, useMl), ma = avgOf('away', mlv, useMl);
      var t1 = tile('Avg ' + tag + (useMl ? ' ML' : ' spread'), mh == null ? '-' : fmt1(mh), ma == null ? 'Road: -' : 'Road: ' + fmt1(ma));
      // 2: the O/U price (NHL's Over 1.5) or the total line
      var nhl = D.sport === 'nhl';
      function tv(g) { var t = o(g).total || {}; return nhl ? t.over : t.line; }
      var th = avgOf('home', tv, nhl), ta = avgOf('away', tv, nhl);
      var t2 = tile(nhl ? 'Avg O/U price' : 'Avg ' + tag + ' total', th == null ? '-' : nhl ? priceTxt(th) : num1(th), ta == null ? 'Road: -' : 'Road: ' + (nhl ? priceTxt(ta) : num1(ta)));
      // 3: the range, with the opponents
      var xs = finals.filter(function(g) { return typeof mlv(g) === 'number'; });
      var t3;
      if (xs.length >= 2) {
        var lo = xs.reduce(function(a, g) { return mlv(g) < mlv(a) ? g : a; }), hi = xs.reduce(function(a, g) { return mlv(g) > mlv(a) ? g : a; });
        function vs(g) { return (g.home === slug ? 'vs ' : '@ ') + tcode(g.home === slug ? g.away : g.home); }
        t3 = tile(tag + (useMl ? ' ML' : ' spread') + ' range', fmt1(mlv(lo)) + ' to ' + fmt1(mlv(hi)), esc(vs(lo)) + ' &middot; ' + esc(vs(hi)));
      } else t3 = tile(tag + (useMl ? ' ML' : ' spread') + ' range', '-', 'Not enough lines yet');
      // 4: lines vs results: the average actual vs the average total
      var tg = finals.filter(function(g) { var r = (g.res || {})[k]; return r && r.sc && (nhl || (o(g).total && typeof o(g).total.line === 'number')); });
      var t4;
      if (tg.length) {
        var al = nhl ? 1.5 : avg(tg.map(function(g) { return o(g).total.line; })), aa = avg(tg.map(function(g) { return g.res[k].sc[0] + g.res[k].sc[1]; }));
        t4 = tile('Lines vs results', num1(aa) + ' vs ' + num1(al), 'Actual vs total, ' + esc(tag) + ' ' + scoreWord());
      } else t4 = tile('Lines vs results', '-', 'No totals saved yet');
      return '<section class="tm-sec tp-hist"><div class="tph"><h2 class="team-section-title">Line History</h2>' + tpSeasonToggle() + '</div><div class="tp-tiles">' + t1 + t2 + t3 + t4 + '</div></section>';
    }
    function resultsHtml() {
      var k = tpSeg(), tag = D.sportType === 'baseball' ? 'F5' : seg(k).tag;
      var rows = finals.filter(function(g) { return ((g.res || {})[k] || {}).sc; }).map(function(g) {
        var sc = g.res[k].sc, mine = g.home === slug ? sc[1] : sc[0], theirs = g.home === slug ? sc[0] : sc[1];
        return { g: g, mine: mine, theirs: theirs, mg: mine - theirs, r: mine > theirs ? 'W' : mine < theirs ? 'L' : 'T' };
      });
      function vs(g) { return (g.home === slug ? 'vs ' : '@ ') + tcode(g.home === slug ? g.away : g.home); }
      var best = null, cur = null;
      rows.forEach(function(x) {
        if (x.r === 'W') { cur = cur ? { n: cur.n + 1, a: cur.a, b: x.g } : { n: 1, a: x.g, b: x.g }; if (!best || cur.n > best.n) best = cur; }
        else cur = null;
      });
      var wins = rows.filter(function(x) { return x.r === 'W'; }), losses = rows.filter(function(x) { return x.r === 'L'; });
      var bw = wins.length ? wins.reduce(function(a, x) { return x.mg > a.mg ? x : a; }) : null;
      var aw = wins.length ? avg(wins.map(function(x) { return x.mg; })) : null, al = losses.length ? avg(losses.map(function(x) { return -x.mg; })) : null;
      var t1 = tile('Longest ' + tag + ' win run', best ? String(best.n) : '0', best ? esc(shortDate(best.a)) + (best.n > 1 ? ' - ' + esc(shortDate(best.b)) : '') : 'No ' + esc(tag) + ' wins yet');
      var t2 = tile('Best ' + tag + ' win', bw ? bw.mine + '-' + bw.theirs : '-', bw ? esc(vs(bw.g)) + ' &middot; ' + esc(shortDate(bw.g)) : 'No ' + esc(tag) + ' wins yet');
      var t3 = tile('Avg margin', aw != null ? '+' + num1(aw) : '-', 'Losses: ' + (al != null ? '-' + num1(al) : '-'));
      var t4 = tile('Avg ' + tag + ' ' + scoreWord(), rows.length ? num1(avg(rows.map(function(x) { return x.mine; }))) : '-',
        'Against: ' + (rows.length ? num1(avg(rows.map(function(x) { return x.theirs; }))) : '-'));
      return '<section class="tm-sec tp-hist"><div class="tph"><h2 class="team-section-title">Results History</h2>' + tpSeasonToggle() + '</div><div class="tp-tiles">' + t1 + t2 + t3 + t4 + '</div></section>';
    }

    function drawLog() {
      var box = document.getElementById('tmLogBox');
      box.innerHTML = logHtml();
      var mb = document.getElementById('tpLogMore');
      if (mb) mb.onclick = function() { TP.log += 10; drawLog(); };
      box.querySelectorAll('[data-log-seg]').forEach(function(b) { b.onclick = function() { tm.logK = b.getAttribute('data-log-seg'); drawLog(); }; });
      wireSeason(box);
    }
    function drawHA() {
      var box = document.getElementById('tpHABox');
      box.innerHTML = homeAwayHtml();
      box.querySelectorAll('[data-ha-col]').forEach(function(b) { b.onclick = function() { TP.haCol = +b.getAttribute('data-ha-col'); drawHA(); }; });
      wireSeason(box);
    }
    function wireSeason(root) {
      root.querySelectorAll('[data-tp-season]').forEach(function(b) { b.onclick = function() { tpUse(b.getAttribute('data-tp-season')); }; });
    }
    app.innerHTML = nextHtml() + lastHtml() + marketsHtml() + startersHtml() + streaksHtml() + '<div id="tmLogBox"></div><div id="tpHABox"></div>' + sitHtml() +
      '<div class="tp-hists">' + linesHtml() + resultsHtml() + '</div>';
    drawLog();
    drawHA();
    drawSit();
    wireSeason(app);
    loadOdds();
  }
  // early season: every section switches between this season and last
  // (history.json, the same shape); last season has no Next game
  function tpUse(which) {
    if (which === TP.which) return;
    function go(games) {
      TP.which = which;
      D.games = games;
      TEAM_SEQ = {}; TP_TOP = {}; SIT = null; TP.log = 5;
      renderTeam();
    }
    if (which === 'this') { go(TP.cur); return; }
    if (TP.prev) { go(TP.prev); return; }
    fetch(dataUrl(SPORT_SLUG + '/history.json')).then(function(r) { return r.ok ? r.json() : {}; }).then(function(h) {
      if (h && h.games && !Array.isArray(h.games) && Object.keys(h.games).length) { TP.prev = h.games; go(TP.prev); }
      else document.querySelectorAll('.tp-season').forEach(function(t) { t.insertAdjacentHTML('afterend', '<p class="tp-none">Not tracked last season.</p>'); t.remove(); });
    }).catch(function() {});
  }
  var tm = { logK: null };

  // Stats for any set of graded games, in the same shape as the build's
  function favSide(o) {
    var ml = (o || {}).ml || {}, a = ml.away, h = ml.home;
    function imp(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
    if (typeof a === 'number' && typeof h === 'number' && imp(a) !== imp(h)) return imp(a) > imp(h) ? 'away' : 'home';
    var line = (((o || {}).ats || {}).away || {}).line;
    if (typeof line === 'number' && line !== 0) return line < 0 ? 'away' : 'home';
    return null;
  }
  // ---- Stats page time filter ----
  // Season / This week / Last week (Overview and Splits). Daily sports' weeks
  // run Monday-Sunday, like NHL's; weekly sports (NFL, NCAAF) use the
  // league's own weeks, plus a Week dropdown for any week so far.
  var tf = { mode: 'all', wk: '' };
  function addDaysStr(d, n) { return new Date(new Date(d + 'T12:00:00Z').getTime() + n * 864e5).toISOString().slice(0, 10); }
  function mondayOf(d) { var day = new Date(d + 'T12:00:00Z').getUTCDay(); return addDaysStr(d, -((day + 6) % 7)); }
  function weeklySport() { return D.schedule === 'week' && (D.weeks || []).length; }
  function startedWeeks() {
    var t = todayET();
    var w = (D.weeks || []).filter(function(x) { return x.start <= t; });
    return w.length ? w : (D.weeks || []).slice(0, 1);
  }
  // Season is the regular season; Postseason (ESPN season type 3, NCAAF's
  // bowls included; NHL: an 03 game id) shows once there are postseason games
  function hasPost() { return finalGames().some(function(g) { return g.post; }); }
  // the selected range: null (everything), {post: true | false} (Season /
  // Postseason), {from, to, label}, or {none: true}
  function tfDates() {
    if (tf.mode === 'all') return hasPost() ? { post: false } : null;
    if (tf.mode === 'post') return { post: true };
    if (weeklySport()) {
      var ws = startedWeeks(), w = null;
      if (tf.mode === 'week') w = ws[ws.length - 1];
      else if (tf.mode === 'lastweek') w = ws[ws.length - 2];
      else if (tf.mode === 'wk') w = (D.weeks || []).filter(function(x) { return x.key === tf.wk; })[0];
      return w ? { from: w.start, to: w.end, wk: w.key, label: esc(w.label) + ' (' + shortDay(w.start) + ' - ' + shortDay(w.end) + ')' } : { none: true };
    }
    var mon = addDaysStr(mondayOf(todayET()), tf.mode === 'week' ? 0 : -7), sun = addDaysStr(mon, 6);
    return { from: mon, to: sun, label: '(' + shortDay(mon) + ' - ' + shortDay(sun) + ')' };
  }
  // {games, line}: the graded games in the selected range, and the range
  function tfRange() {
    var r = tfDates();
    if (!r) return { games: finalGames(), line: '' };
    if (r.none) return { games: [], line: '<div class="sc-week">No week to show yet</div>' };
    if (r.post != null) return { games: finalGames().filter(function(g) { return !!g.post === r.post; }), line: '' };
    var games = r.wk ? finalGames().filter(function(g) { return g.wk === r.wk; }) : finalGames(r.from, r.to);
    return { games: games, line: '<div class="sc-week">' + r.label + '</div>' };
  }
  function tfControls() {
    function btn(mode, label) { return '<button class="seg-btn" data-tf="' + mode + '" aria-pressed="' + (tf.mode === mode) + '">' + label + '</button>'; }
    var weekly = weeklySport();
    return '<div class="seg-toggle seg-sm" role="group" aria-label="Time range">' + btn('all', 'Season') + btn('week', 'This week') + btn('lastweek', 'Last week') +
      (hasPost() ? btn('post', 'Postseason') : '') + '</div>' +
      (weekly ? '<select class="conf-select tf-week" id="tfWeek" aria-label="Pick a week"><option value="">Week&hellip;</option>' +
        startedWeeks().map(function(w) { return '<option value="' + esc(w.key) + '"' + (tf.mode === 'wk' && tf.wk === w.key ? ' selected' : '') + '>' + esc(w.label) + '</option>'; }).join('') +
        '</select>' : '');
  }
  // before(): return false to keep the old range (Splits: a premium-locked filter combination)
  function wireTf(draw, before) {
    function set(mode, wk) { var was = { mode: tf.mode, wk: tf.wk }; tf.mode = mode; tf.wk = wk; if (before && before() === false) { tf.mode = was.mode; tf.wk = was.wk; } draw(); }
    app.querySelectorAll('[data-tf]').forEach(function(b) { b.onclick = function() { set(b.getAttribute('data-tf'), ''); }; });
    var sel = document.getElementById('tfWeek');
    if (sel) sel.onchange = function() { if (sel.value) set('wk', sel.value); else set('all', ''); };
  }

  // ---- Scoring (Stats Overview; NHL has Goal Stats instead) ----
  // Three cards on the time filter's graded games with a score for the
  // segment the page toggle picks: the averages (and how often the segment
  // ends tied; MLB adds the NRFI rate), Most Common Scores (exact score,
  // higher first) and Scoring Distribution (combined score in buckets,
  // sortable by count or range; ?sort=common|range keeps the view linkable).
  var FB_BUCKETS = {
    '1q': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, null]],
    '1h': [[0, 0], [1, 3], [4, 7], [8, 10], [11, 14], [15, 17], [18, 21], [22, 24], [25, 28], [29, 31], [32, 35], [36, null]],
  };
  var MLB_BUCKETS = {
    '1i': [[0, 0], [1, 1], [2, 2], [3, null]],
    'f5': [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6], [7, 7], [8, 9], [10, null]],
  };
  var fbState = null;
  function isFootball() { return D.sport === 'nfl' || D.sport === 'ncaaf'; }
  function fbInit() {
    if (fbState) return;
    var q = {};
    try { new URLSearchParams(window.location.search).forEach(function(v, key) { q[key] = v; }); } catch (e) {}
    fbState = { sort: q.sort === 'range' ? 'range' : 'common', open: false };
  }
  function fbSaveUrl() {
    try {
      var u = new URL(window.location.href);
      u.searchParams.set('sort', fbState.sort);
      history.replaceState(null, '', u.toString());
    } catch (e) {}
  }
  function fbPct(n, of) {
    if (!of) return '0%';
    var p = 100 * n / of;
    return (p > 0 && p < 1 ? p.toFixed(1) : String(Math.round(p))) + '%';
  }
  // one bar row: label, bar (width vs the largest row), "count · %" inside
  // the bar when it fits, else just past its end; no bar for 0 games
  function fbRow(label, n, of, max, key) {
    var w = n && max ? Math.min(100, Math.max(1, Math.round(100 * n / max))) : 0;
    var val = '<b>' + n + '</b> <span class="hd-sub">&middot; ' + fbPct(n, of) + '</span>';
    var inside = w >= 38;
    return '<div class="hd-row"' + (key != null ? ' data-fb-key="' + esc(key) + '"' : '') + '><span class="hd-lbl mono">' + esc(label) + '</span>' +
      '<div class="hd-track">' + (w ? '<div class="hd-bar" style="width:' + w + '%">' + (inside ? '<span class="hd-val in">' + val + '</span>' : '') + '</div>' : '') +
      (inside ? '' : '<span class="hd-val out">' + val + '</span>') + '</div></div>';
  }
  // the distribution's buckets: football and baseball fixed, basketball
  // from the sample (5-point steps for a quarter, 10 for a half; the
  // thinnest 3% at each end pooled into "or fewer" / "+" buckets)
  function scoreBuckets(k, totals) {
    if (isFootball()) return FB_BUCKETS[k] || FB_BUCKETS['1q'];
    if (D.sportType === 'baseball') return MLB_BUCKETS[k] || MLB_BUCKETS.f5;
    if (!totals.length) return [];
    var step = k === '1q' ? 5 : 10, srt = totals.slice().sort(function(a, b) { return a - b; });
    var lo = Math.floor(srt[Math.floor(srt.length * 0.03)] / step) * step, hi = Math.floor(srt[Math.ceil(srt.length * 0.97) - 1] / step) * step;
    var out = [[null, lo - 1]];
    for (var x = lo; x <= hi; x += step) out.push([x, x + step - 1]);
    out.push([hi + step, null]);
    return out.filter(function(b) { return totals.some(function(t) { return (b[0] == null || t >= b[0]) && (b[1] == null || t <= b[1]); }); });
  }
  function bucketLabel(b) { return b[0] == null ? '≤' + b[1] : b[1] == null ? b[0] + '+' : b[0] === b[1] ? String(b[0]) : b[0] + '-' + b[1]; }
  function scoringHtml(games, k) {
    var sample = [], missing = 0, rfiN = 0, rfiY = 0;
    games.forEach(function(g) {
      var r = (g.res || {})[k];
      if (r && r.sc && !r.na) { sample.push(r.sc); if (r.rfi === 'Y' || r.rfi === 'N') { rfiN++; if (r.rfi === 'N') rfiY++; } }
      else if (g.state === 'final') missing++;
    });
    var n = sample.length, s = anySeg(k), unit = scoreUnit();
    var totals = sample.map(function(sc) { return sc[0] + sc[1]; });
    var tied = sample.filter(function(sc) { return sc[0] === sc[1]; }).length;
    var avg = n ? totals.reduce(function(a, b) { return a + b; }, 0) / n : null;
    // card 1: averages
    var segName = isRfi(k) ? '1st-inning' : s.tag;
    var stats = [['Avg ' + segName + ' ' + unit, avg == null ? '-' : avg.toFixed(D.sportType === 'baseball' ? 2 : 1)],
                 ['Avg per team', avg == null ? '-' : (avg / 2).toFixed(D.sportType === 'baseball' ? 2 : 1)]];
    if (isRfi(k)) stats.push(['NRFI rate', rfiN ? fbPct(rfiY, rfiN) : '-']);
    var card0 = stats.map(function(x) { return '<div class="st-row st-stat"><span class="st-lbl">' + x[0] + '</span><span class="st-num mono">' + x[1] + '</span></div>'; }).join('') +
      (n && !isRfi(k) ? '<p class="st-line">' + fbPct(tied, n) + ' of ' + esc(segWords(k)) + ' end tied.</p>' : '');
    // card 2: exact scores, order-agnostic
    var scores = {};
    sample.forEach(function(sc) {
      var hi = Math.max(sc[0], sc[1]), lo = Math.min(sc[0], sc[1]), key = hi + '-' + lo;
      (scores[key] = scores[key] || { label: key, n: 0, tot: hi + lo, hi: hi }).n++;
    });
    var ranked = Object.keys(scores).map(function(x) { return scores[x]; }).sort(function(a, b) {
      return b.n - a.n || a.tot - b.tot || a.hi - b.hi;
    });
    var top = fbState.open ? ranked : ranked.slice(0, 5), rest = ranked.slice(5);
    var other = rest.reduce(function(t, x) { return t + x.n; }, 0);
    // bars scale to the most common score; "Other" (many scores pooled) caps at full width
    var max1 = Math.max.apply(null, top.map(function(x) { return x.n; }).concat([0]));
    var card1 = top.map(function(x) { return fbRow(x.label, x.n, n, max1); }).join('') +
      (!fbState.open && rest.length ? fbRow('Other', other, n, max1) : '') +
      (rest.length ? '<button type="button" class="fb-more" id="fbMore">' + (fbState.open ? 'Show less &#9652;' : 'Show all (' + rest.length + ' more) &#9662;') + '</button>' : '');
    // card 3: combined score in buckets
    var rows = scoreBuckets(k, totals).map(function(b, i) {
      var c = totals.filter(function(t) { return (b[0] == null || t >= b[0]) && (b[1] == null || t <= b[1]); }).length;
      return { i: i, label: bucketLabel(b), n: c };
    });
    if (fbState.sort === 'common') rows.sort(function(a, b) { return b.n - a.n || a.i - b.i; });
    var max2 = Math.max.apply(null, rows.map(function(r) { return r.n; }).concat([0]));
    var card2 = rows.map(function(r) { return fbRow(r.label, r.n, n, max2, r.label); }).join('');
    var sub = n + ' game' + (n === 1 ? '' : 's') + (missing ? ' &middot; ' + missing + ' missing ' + esc(segWord(k)) + ' scores' : '');
    function sortLink(v, label) {
      return '<button type="button" class="fb-sort' + (fbState.sort === v ? ' on' : '') + '" data-fb-sort="' + v + '" aria-pressed="' + (fbState.sort === v) + '">' + label + '</button>';
    }
    var none = emptyNote('No games with ' + esc(s.label) + ' scores in this range.');
    return '<div class="st-grid">' +
      stCard(s.tag === 'NRFI' ? '1st Inning' : s.tag + ' Scoring', sub, n ? card0 : none) +
      stCard('Most Common Scores', sub, '<div class="hdist">' + (n ? card1 : none) + '</div>') +
      stCard('Scoring Distribution', sub, '<div class="fb-sorts">Sort: ' + sortLink('common', 'Common') + ' <span aria-hidden="true">|</span> ' + sortLink('range', 'Range') + '</div>' +
        '<div class="hdist" id="fbDist">' + (n ? card2 : none) + '</div>') +
      '</div>';
  }
  function renderScoring(games, k) {
    var box = document.getElementById('statsScoringBody');
    if (!box) return;
    fbInit();
    // FLIP: remember where each bucket row was, re-render, then slide rows
    // from their old spots to the new ones (~200ms), unless reduced motion
    var before = {};
    box.querySelectorAll('#fbDist [data-fb-key]').forEach(function(el) { before[el.getAttribute('data-fb-key')] = el.getBoundingClientRect().top; });
    box.innerHTML = scoringHtml(games, k);
    var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!still) {
      box.querySelectorAll('#fbDist [data-fb-key]').forEach(function(el) {
        var was = before[el.getAttribute('data-fb-key')];
        if (was == null) return;
        var dy = was - el.getBoundingClientRect().top;
        if (!dy) return;
        el.style.transform = 'translateY(' + dy + 'px)';
        el.style.transition = 'none';
        requestAnimationFrame(function() {
          el.style.transition = 'transform 200ms ease';
          el.style.transform = '';
        });
      });
    }
    box.querySelectorAll('[data-fb-sort]').forEach(function(b) {
      b.onclick = function() { fbState.sort = b.getAttribute('data-fb-sort'); fbSaveUrl(); renderScoring(games, k); };
    });
    var more = document.getElementById('fbMore');
    if (more) more.onclick = function() { fbState.open = !fbState.open; renderScoring(games, k); };
  }

  // ------------------------------------------------------------ Stats pages
  // Three pages for every sport (Chris's spec, the sport-families rule in
  // CLAUDE.md): Overview (/stats/: Season Results, Money Board and
  // Scoring), Splits (/stats/splits/: Situational
  // Results) and Edges (/stats/edges/: what happens after the opening
  // segment, Best Closers and Biggest Faders). Everything is counted here
  // from the graded games: res[k] (from the away side) and u[market] units
  // on each game, the same as the Teams pages.
  //
  // PREMIUM: one flag per section. Off = everyone sees it all. On = free
  // visitors (IS_PREMIUM false, or ?free=1) see each card's first 2 rows
  // and the rest blurred behind "Unlock with Premium". splitCombine: more
  // than one Splits filter at once; edgesPage: the whole Edges page;
  // fullRun: the Full Run (team pages: the first Full Run row of Season
  // Markets, the rest blurred, and a lock on the Game Log's Full Run pills;
  // Stats: the Full Run segment pills).
  var PREMIUM = { board: false, edge1q: false, edge1h: false, edge1p: false, edgef5: false, edge1i: false, tonightOnly: false, splitCombine: false, edgesPage: false, fullRun: false };
  function periodFamily() { return D.sport === 'nhl' || D.sport === 'mlb'; }
  function spreadWord() { return D.sportType === 'baseball' ? 'Run Line' : D.sport === 'nhl' ? 'Puck Line' : 'Spread'; }   // MLB's spreads are run lines, NHL's (the full game) the puck line
  function totalWord(k) { return D.sport === 'nhl' && k === '1p' ? 'O/U 1.5' : 'O/U'; }
  function scoreUnit() { return D.sport === 'nhl' ? 'goals' : D.sportType === 'baseball' ? 'runs' : 'points'; }
  function pctOf(n, of) { return of ? Math.round(100 * n / of) : null; }
  function pctCell(n, of) { var p = pctOf(n, of); return p == null ? '-' : p + '%'; }
  function mlFavSide(ml) {
    ml = ml || {};
    if (typeof ml.away !== 'number' || typeof ml.home !== 'number') return null;
    function imp(p) { return p < 0 ? -p / (-p + 100) : 100 / (p + 100); }
    return imp(ml.away) === imp(ml.home) ? null : imp(ml.away) > imp(ml.home) ? 'away' : 'home';
  }
  // the segment's favorite: its own moneyline, else its spread line, else the full game
  function segFavSide(g, k) { return favSide((g.odds || {})[k]) || mlFavSide(g.fml) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null); }
  // the full-game favorite: closing moneyline, else the spread
  function gameFav(g) { return mlFavSide(g.fml) || (g.fs ? (g.fs < 0 ? 'home' : 'away') : null); }
  function graded(games, k) {
    return games.filter(function(g) { var r = (g.res || {})[k]; return r && r.sc && !r.na; });
  }
  function premiumLocked(flag) { return !!PREMIUM[flag] && !IS_PREMIUM; }
  // rows[first..] blurred behind "Unlock with Premium" while `flag` locks them (the Full Run: from its second row)
  function lockFrom(rows, first, flag) { return !premiumLocked(flag) || rows.length <= first ? rows.join('') : rows.slice(0, first).join('') + '<div class="pm-blur" aria-hidden="true">' + rows.slice(first).join('') + '</div><a class="pm-unlock" href="' + ROOT + '#premium">Unlock with Premium</a>'; }
  // a segment pill; the Full Run's carry the gold dot, and a lock while PREMIUM.fullRun keeps them from free visitors
  function segPill(s, on, fr, attr, label) { return '<button class="seg-btn' + (fr ? ' fr-pill' : '') + '" ' + attr + '="' + s.key + '" aria-pressed="' + on + '">' + (fr && premiumLocked('fullRun') ? FR_LOCK : '') + esc(label || s.label) + '</button>'; }
  function lockRows(rows, flag) {
    if (!premiumLocked(flag) || rows.length <= 2) return rows.join('');
    return rows.slice(0, 2).join('') + '<div class="pm-blur" aria-hidden="true">' + rows.slice(2).join('') + '</div>' +
      '<a class="pm-unlock" href="' + ROOT + '#premium">Unlock with Premium</a>';
  }
  // every "i" opens the one box (template.html #tipBox); tipBody: its title,
  // a short definition and, on trends only, the comparison line
  // (only Live definitions reach the page: none, and the box shows the title
  // and the comparison line). No link out of the box (Nov 20).
  function infoTip(html, left, label, term) {
    return '<button type="button" class="info-tip"' + ' aria-label="About ' + esc(label || 'this section') + '"' + (term ? ' data-term="' + esc(term) + '"' : '') + '>i<span class="tip-bubble" role="tooltip">' + html + '</span></button>';
  }
  function tipBody(title, def, cmp) {
    return '<span class="tip-t">' + esc(title) + '</span>' + (def ? '<span class="tip-d">' + esc(def) + '</span>' : '') + (cmp ? '<span class="tip-c">' + esc(cmp) + '</span>' : '');
  }
  // a market's glossary entry (content/definitions.json term:{anchor})
  function termOf(m) {
    if (m === 'ats' || m === 'spread') return D.sport === 'mlb' ? 'run-line' : 'spread';
    return { ml: 'moneyline', su: 'moneyline', ml3: '3-way-moneyline', total: 'total', tot: 'total', btts: 'btts', rfi: 'nrfi' }[m] || null;
  }
  function statsUrl(page) { return ROOT + SPORT_SLUG + '/stats/' + (page ? page + '/' : ''); }
  // the one card style (Part 4): caps title, at most one muted subtitle,
  // chips in a fixed row under the header, rows on the shared grid
  function stCard(title, sub, body, chips, cls) {
    return '<div class="st-card' + (cls ? ' ' + cls : '') + '"><div class="st-head"><h4>' + title + '</h4>' + (sub ? '<div class="st-sub">' + sub + '</div>' : '') + '</div>' +
      (chips ? '<div class="st-chips">' + chips + '</div>' : '') + body + '</div>';
  }
  function stSection(id, title, controls, body) {
    return '<section class="st-sec" id="' + id + '"><div class="st-sec-head"><h2>' + title + '</h2>' + (controls ? '<div class="st-ctl">' + controls + '</div>' : '') + '</div>' + body + '</section>';
  }
  function stUnits(r) { return r.pr ? '<span class="st-u ' + unitCls(r.u) + '">' + fmtUnits(r.u) + '</span>' : '<span class="st-u st-none">-</span>'; }
  function stPct(w, l) { return w + l ? Math.round(100 * w / (w + l)) + '%' : '-'; }
  // one row: label | record | % | units, the columns lined up across cards
  function stRow(label, recTxt, pctTxt, unitsTxt, cls) {
    return '<div class="st-row' + (cls ? ' ' + cls : '') + '"><span class="st-lbl">' + label + '</span><span class="st-rec mono">' + recTxt + '</span>' +
      '<span class="st-pct mono">' + pctTxt + '</span>' + (unitsTxt == null ? '<span class="st-u"></span>' : unitsTxt) + '</div>';
  }
  function stHead(a, b, c) { return '<div class="st-row st-colhead"><span class="st-lbl"></span><span class="st-rec">' + a + '</span><span class="st-pct">' + b + '</span><span class="st-u">' + c + '</span></div>'; }

  // ---- Season Results ----
  // card = {id, title, gp, rows [{id, label, r {w, l, t, u, pr}, fmt 'T'|'P'|''}], tie (ML: tied games), stat}
  function sRec() { return { w: 0, l: 0, t: 0, u: 0, pr: 0 }; }
  function sAdd(r, res, u) {
    if (res === 'W') r.w++; else if (res === 'L') r.l++; else r.t++;
    if (u != null) { r.u += u; r.pr++; }
  }
  function newCard(id, title, rows, fmt) {
    var c = { id: id, title: title, gp: 0, rows: [], by: {} };
    rows.forEach(function(x) { var row = { id: x[0], label: x[1], r: sRec(), fmt: fmt }; c.rows.push(row); c.by[x[0]] = row; });
    return c;
  }
  function seasonCards(games, k) {
    var list = graded(games, k), t = segTag(k), nhl = D.sport === 'nhl' && k !== 'game';   // NHL's full game: the spread family's cards (puck line)
    var pre = isRfi(k) ? '' : t + ' ';
    if (isRfi(k)) {
      var rf = newCard('rfi', 'NRFI/YRFI', [['YRFI', 'YRFI'], ['NRFI', 'NRFI']], '');
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).rfi;
        if (r.rfi !== 'Y' && r.rfi !== 'N') return;
        rf.gp++;
        sAdd(rf.by.YRFI.r, r.rfi === 'Y' ? 'W' : 'L', u ? u[0] : null);
        sAdd(rf.by.NRFI.r, r.rfi === 'N' ? 'W' : 'L', u ? u[1] : null);
      });
      return [rf];
    }
    var ml = newCard('ml', pre + 'Moneyline', [['home', 'Home'], ['away', 'Away']], 'T');
    var mlfd = newCard('mlfd', pre + 'Favorites / Underdogs', [['fav', 'Favorite'], ['dog', 'Underdog']], 'T');
    var sp = newCard('ats', pre + spreadWord(), [['home', 'Home'], ['away', 'Away']], 'P');
    var tot = newCard('tot', pre + totalWord(k), [['over', 'Over'], ['under', 'Under']], nhl ? '' : 'P');
    var bt = newCard('btts', pre + 'BTTS', [['yes', 'Yes'], ['no', 'No']], '');
    var m3 = newCard('ml3', pre + '3-way ML', [['home', 'Home'], ['away', 'Away'], ['tie', 'Tie']], '');
    var fd = newCard('fd', pre + 'Favorites / Underdogs', [['mlfav', 'ML Fav'], ['mldog', 'ML Dog'], ['spfav', spreadWord() + ' Fav'], ['spdog', spreadWord() + ' Dog']], '');
    fd.rows[0].fmt = fd.rows[1].fmt = 'T'; fd.rows[2].fmt = fd.rows[3].fmt = 'P';
    var ha = newCard('ha', pre + 'Home / Away', [['hfav', 'Home Fav'], ['hdog', 'Home Dog'], ['rfav', 'Road Fav'], ['rdog', 'Road Dog']], 'P');
    // NHL: Home / Away by the segment's moneyline (no 1P spread)
    var haMl = newCard('ha', pre + 'Home / Away', [['hfav', 'Home Fav'], ['hdog', 'Home Dog'], ['rfav', 'Road Fav'], ['rdog', 'Road Dog']], 'T');
    // a tied segment: its own row on the Moneyline card; NHL's tie lives on
    // the 3-way ML card instead (the ML record stays W-L-T)
    if (!nhl) ml.tie = 0;
    var fdSeen = {};
    list.forEach(function(g) {
      var r = g.res[k], u = r.u || {}, o = (g.odds || {})[k] || {};
      if (hasMl(k) && r.su && r.su !== 'NA') {
        var aRes = r.su === 'P' ? 'T' : r.su, hRes = flipRes(aRes), us = u.su;
        ml.gp++; if (aRes === 'T' && !nhl) ml.tie++;
        sAdd(ml.by.home.r, hRes, us ? us[1] : null); sAdd(ml.by.away.r, aRes, us ? us[0] : null);
        var f = segFavSide(g, k);
        if (f) {
          var fi = f === 'away' ? 0 : 1, fRes = f === 'away' ? aRes : hRes;
          mlfd.gp++;
          sAdd(mlfd.by.fav.r, fRes, us ? us[fi] : null); sAdd(mlfd.by.dog.r, flipRes(fRes), us ? us[1 - fi] : null);
          sAdd(fd.by.mlfav.r, fRes, us ? us[fi] : null); sAdd(fd.by.mldog.r, flipRes(fRes), us ? us[1 - fi] : null);
          fdSeen[g.id] = 1;
          haMl.gp++;
          sAdd(haMl.by[f === 'home' ? 'hfav' : 'hdog'].r, hRes, us ? us[1] : null);
          sAdd(haMl.by[f === 'away' ? 'rfav' : 'rdog'].r, aRes, us ? us[0] : null);
        }
        if (u.ml3) {
          m3.gp++;
          sAdd(m3.by.home.r, hRes === 'W' ? 'W' : 'L', u.ml3[1]); sAdd(m3.by.away.r, aRes === 'W' ? 'W' : 'L', u.ml3[0]);
          sAdd(m3.by.tie.r, aRes === 'T' ? 'W' : 'L', u.ml3[2]);
        }
      }
      if (r.ats && r.ats !== 'NA') {
        var aA = r.ats === 'T' ? 'P' : r.ats, hA = flipRes(aA), ua = u.ats;
        sp.gp++; sAdd(sp.by.home.r, hA, ua ? ua[1] : null); sAdd(sp.by.away.r, aA, ua ? ua[0] : null);
        var line = ((o.ats || {}).away || {}).line;
        if (typeof line === 'number' && line !== 0) {
          var sf = line < 0 ? 'away' : 'home', si = sf === 'away' ? 0 : 1, fA = sf === 'away' ? aA : hA;
          fdSeen[g.id] = 1;
          sAdd(fd.by.spfav.r, fA, ua ? ua[si] : null); sAdd(fd.by.spdog.r, flipRes(fA), ua ? ua[1 - si] : null);
          ha.gp++;
          sAdd(ha.by[sf === 'home' ? 'hfav' : 'hdog'].r, hA, ua ? ua[1] : null);
          sAdd(ha.by[sf === 'away' ? 'rfav' : 'rdog'].r, aA, ua ? ua[0] : null);
        }
      }
      if (r.tot && r.tot !== 'NA') {
        tot.gp++;
        var oRes = r.tot === 'O' ? 'W' : r.tot === 'U' ? 'L' : 'P';
        sAdd(tot.by.over.r, oRes, u.tot ? u.tot[0] : null); sAdd(tot.by.under.r, flipRes(oRes), u.tot ? u.tot[1] : null);
      }
      if (r.btts === 'Y' || r.btts === 'N') {
        bt.gp++;
        sAdd(bt.by.yes.r, r.btts === 'Y' ? 'W' : 'L', u.btts ? u.btts[0] : null); sAdd(bt.by.no.r, r.btts === 'N' ? 'W' : 'L', u.btts ? u.btts[1] : null);
      }
    });
    fd.gp = Object.keys(fdSeen).length;
    // NHL: Moneyline, O/U 1.5, BTTS, 3-way ML, Scoring, then Moneyline by
    // favorite and Home / Away. Spread family (and MLB's F5): Moneyline,
    // Spread, O/U, Favorites/Underdogs, Home/Away.
    var cards = nhl ? [ml, tot, bt, m3, scoringCard(list, k), mlfd, haMl] : [ml, sp, tot, fd, ha];
    return cards.filter(function(c) { return c.stat || c.gp; });
  }
  // NHL's Scoring card: the average 1st-period goals, 0-0 and tied rates
  function scoringCard(list, k) {
    var s = anySeg(k), n = list.length, pts = 0, zero = 0, tied = 0;
    list.forEach(function(g) { var sc = g.res[k].sc, t = sc[0] + sc[1]; pts += t; if (!t) zero++; if (sc[0] === sc[1]) tied++; });
    return { id: 'scoring', title: s.tag + ' Scoring', gp: n, stat: [
      ['Avg ' + s.tag + ' goals', n ? (pts / n).toFixed(2) : '-'],
      ['0-0', n ? zero + ' <small>(' + pctCell(zero, n) + ')</small>' : '-'],
      [k === '1p' ? 'Tied after one' : 'Tied ' + s.tag, n ? tied + ' <small>(' + pctCell(tied, n) + ')</small>' : '-']] };
  }
  function recOf(r, fmt) { return r.w + '-' + r.l + (fmt ? '-' + r.t : ''); }
  function cardHtml(c, total) {
    var body;
    if (c.stat) body = c.stat.map(function(x) { return '<div class="st-row st-stat"><span class="st-lbl">' + x[0] + '</span><span class="st-num mono">' + x[1] + '</span></div>'; }).join('');
    else {
      var mark = c.gp < total ? '<sup class="st-mark" title="Games without a saved line aren&rsquo;t counted">*</sup>' : '';
      var fmts = c.rows.map(function(x) { return x.fmt; }).filter(Boolean);
      body = stHead(fmts.length ? (fmts.indexOf('T') !== -1 && fmts.indexOf('P') !== -1 ? 'Record' : 'W-L-' + fmts[0]) : 'W-L', '%', 'Units') +
        c.rows.map(function(x) { return stRow(x.label, recOf(x.r, x.fmt) + mark, stPct(x.r.w, x.r.l), stUnits(x.r)); }).join('');
      // ML only: a tied segment is a tie (0u); its own row, % of every game
      if (c.tie != null) body += stRow('Tie', String(c.tie), pctCell(c.tie, c.gp), null, 'st-tie');
    }
    return stCard(c.title, '', body);
  }
  function seasonMarked(cards, total) { return cards.some(function(c) { return !c.stat && c.gp < total; }); }

  // ---- NHL Goal Stats: 1st-period goals (from the old NHL page) ----
  function goalStats(games) {
    var list = graded(games, '1p').filter(function(g) { return g.state === 'final'; }), n = list.length;
    function tp(g) { return g.res['1p'].sc[0] + g.res['1p'].sc[1]; }
    function cnt(arr, fn) { return arr.filter(fn).length; }
    function bars(rows, of) {
      return rows.map(function(r) {
        return '<div class="st-row st-stat"><span class="st-lbl">' + r[0] + '</span><span class="st-num mono">' + r[1] + ' <small>(' + pctCell(r[1], of) + ')</small></span></div>' +
          '<div class="adv-bar"><span style="width:' + (pctOf(r[1], of) || 0) + '%"></span></div>';
      }).join('');
    }
    // the game after a team was shut out (full game)
    var byTeam = {}, offShut = [], shutGames = {};
    allDates().forEach(function(d) { D.games[d].forEach(function(g) { ['away', 'home'].forEach(function(s) { (byTeam[g[s]] = byTeam[g[s]] || []).push({ g: g, s: s }); }); }); });
    Object.keys(byTeam).forEach(function(t) {
      var arr = byTeam[t];
      for (var i = 1; i < arr.length; i++) {
        var p = arr[i - 1], e = arr[i];
        if (p.g.state !== 'final' || (p.s === 'away' ? p.g.as : p.g.hs) !== 0) continue;
        var r = (e.g.res || {})['1p'];
        if (!r || !r.sc || e.g.state !== 'final') continue;
        offShut.push(e.s === 'away' ? r.sc[0] : r.sc[1]);
        shutGames[e.g.id] = e.g;
      }
    });
    var sg = Object.keys(shutGames).map(function(id) { return shutGames[id]; }), m = offShut.length;
    var cards = [
      ['Overs Ladder', 'Games over each 1st-period total', n, bars([['Over 0.5', cnt(list, function(g) { return tp(g) > 0; })], ['Over 1.5', cnt(list, function(g) { return tp(g) > 1; })], ['Over 2.5', cnt(list, function(g) { return tp(g) > 2; })]], n)],
      ['1P Goal Split', 'Total goals in the 1st period', n, bars([['0 goals', cnt(list, function(g) { return tp(g) === 0; })], ['1 goal', cnt(list, function(g) { return tp(g) === 1; })], ['2 goals', cnt(list, function(g) { return tp(g) === 2; })], ['3+ goals', cnt(list, function(g) { return tp(g) >= 3; })]], n)],
      ['Off a Shutout: Goals Scored', 'Team&rsquo;s own 1P goals the game after being shut out', m, bars([['0 goals', offShut.filter(function(x) { return x === 0; }).length], ['1 goal', offShut.filter(function(x) { return x === 1; }).length], ['2+ goals', offShut.filter(function(x) { return x >= 2; }).length]], m)],
      ['Off a Shutout: 1P Goals', 'Both teams, the game after a shutout loss', sg.length, bars([['Over 0.5', cnt(sg, function(g) { return tp(g) > 0; })], ['Over 1.5', cnt(sg, function(g) { return tp(g) > 1; })], ['Over 2.5', cnt(sg, function(g) { return tp(g) > 2; })]], sg.length)]
    ];
    return '<div class="st-grid">' + cards.map(function(c) { return stCard(c[0], c[1] + ' &middot; ' + c[2] + ' games', c[3]); }).join('') + '</div>';
  }

  // ---- Money Board: the segment's moneyline by side and price; spread
  // sports add a Moneyline / Spread switch (cover rates by line size) ----
  var boardState = { view: 'pct', market: 'ml' };
  function newRec() { return { w: 0, l: 0, t: 0, u: 0, pr: 0 }; }
  function addRec(a, res, u) {
    if (res === 'W') a.w++; else if (res === 'L') a.l++; else a.t++;
    if (u != null) { a.u += u; a.pr++; }
  }
  function boardRow(label, a, twoWay) {
    return stRow(label, a.w + '-' + a.l + (twoWay ? '' : '-' + a.t), boardState.view === 'pct' ? stPct(a.w, a.l) : '', boardState.view === 'pct' ? null : stUnits(a));
  }
  function boardCard(title, sub, rows, note, fmt) {
    return stCard(title, sub, stHead(fmt, boardState.view === 'pct' ? 'Win %' : '', boardState.view === 'pct' ? '' : 'Units') +
      lockRows(rows, 'board') + (note ? '<div class="st-note">' + note + '</div>' : ''));
  }
  // MLB's 1st inning: NRFI / YRFI by which side was favored, and the NRFI by its closing price
  function rfiBoard(list) {
    var sides = [['NRFI as favorite', 'n', 1], ['NRFI as underdog', 'n', 0], ['YRFI as favorite', 'y', 1], ['YRFI as underdog', 'y', 0]];
    var by = sides.map(newRec), priced = 0;
    var tiers = [['-150 or shorter', function(p) { return p <= -150; }], ['-149 to -101', function(p) { return p > -150 && p <= -101; }],
                 ['+100 to +149', function(p) { return (p >= 100 && p <= 149) || p === -100; }], ['+150 or longer', function(p) { return p >= 150; }]];
    var tr = tiers.map(newRec);
    list.forEach(function(g) {
      var r = g.res['1i'], u = (r.u || {}).rfi, o = ((g.odds || {})['1i'] || {}).nrfi_yrfi || {};
      var f = mlFavSide({ away: o.yrfi, home: o.nrfi });   // 'home' = the NRFI was favored
      if ((r.rfi !== 'Y' && r.rfi !== 'N') || !u || !f) return;
      priced++;
      var nRes = r.rfi === 'N' ? 'W' : 'L', nFav = f === 'home';
      sides.forEach(function(x, i) {
        if ((x[2] === 1) !== (x[1] === 'n' ? nFav : !nFav)) return;
        addRec(by[i], x[1] === 'n' ? nRes : flipRes(nRes), x[1] === 'n' ? u[1] : u[0]);
      });
      for (var i = 0; i < tiers.length; i++) if (tiers[i][1](o.nrfi)) { addRec(tr[i], nRes, u[1]); break; }
    });
    var cards = [boardCard('NRFI / YRFI', 'by the favored side', sides.map(function(x, i) { return boardRow(x[0], by[i], true); }), priced + ' games with a closing NRFI / YRFI price', 'W-L'),
                 boardCard('Odds Tiers', 'NRFI by closing price', tiers.map(function(t, i) { return boardRow(t[0], tr[i], true); }), 'NRFI can&rsquo;t push', 'W-L')];
    var pills = '<div class="seg-toggle" role="group" aria-label="Show"><button class="seg-btn" data-board-view="pct" aria-pressed="' + (boardState.view === 'pct') + '">Win %</button>' +
      '<button class="seg-btn" data-board-view="units" aria-pressed="' + (boardState.view === 'units') + '">Profit</button></div>';
    return stSection('statsBoard', 'Money Board', pills, '<p class="st-sec-sub">NRFI / YRFI at closing prices</p><div class="st-grid st-grid-2">' + cards.join('') + '</div>');
  }
  function moneyBoard(games, k) {
    var list = graded(games, k), s = anySeg(k);
    if (isRfi(k)) return rfiBoard(list);
    var canMl = hasMl(k) && !isRfi(k), canAts = !periodFamily() || D.sportType === 'baseball' || k === 'game';
    canAts = canAts && list.some(function(g) { var r = g.res[k]; return r.ats && r.ats !== 'NA'; });
    if (!canMl && !canAts) return '';
    var mk = boardState.market === 'ats' && canAts ? 'ats' : canMl ? 'ml' : 'ats';
    var cards = [];
    if (mk === 'ml') {
      var groups = { 'Home Fav': newRec(), 'Home Dog': newRec(), 'Road Fav': newRec(), 'Road Dog': newRec() };
      var tiers = [['-150 or shorter', function(p) { return p <= -150; }], ['-149 to -101', function(p) { return p > -150 && p <= -101; }],
                   ['+100 to +149', function(p) { return (p >= 100 && p <= 149) || p === -100; }], ['+150 or longer', function(p) { return p >= 150; }]];
      var tr = tiers.map(newRec), priced = 0;
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).su, ml = ((g.odds || {})[k] || {}).ml || {};
        if (!r.su || r.su === 'NA' || !u) return;
        var f = mlFavSide(ml);
        if (!f) return;
        priced++;
        var aRes = r.su === 'P' ? 'T' : r.su, hRes = flipRes(aRes);
        addRec(groups[f === 'home' ? 'Home Fav' : 'Home Dog'], hRes, u[1]);
        addRec(groups[f === 'away' ? 'Road Fav' : 'Road Dog'], aRes, u[0]);
        [['away', aRes, u[0]], ['home', hRes, u[1]]].forEach(function(x) {
          for (var i = 0; i < tiers.length; i++) if (tiers[i][1](ml[x[0]])) { addRec(tr[i], x[1], x[2]); break; }
        });
      });
      cards.push(boardCard('Home / Road Fav &amp; Dog', s.tag + ' moneyline by side', Object.keys(groups).map(function(g) { return boardRow(g, groups[g]); }), priced + ' games with a closing ' + s.tag + ' moneyline', 'W-L-T'));
      cards.push(boardCard('Odds Tiers', s.tag + ' moneyline by closing price', tiers.map(function(t, i) { return boardRow(t[0], tr[i]); }), 'Ties are 0u, left out of win %', 'W-L-T'));
    } else {
      var B = [['0.5-2.5', 0.5, 2.5], ['3-4.5', 3, 4.5], ['5+', 5, 999]];
      var fav = B.map(newRec), dog = B.map(newRec);
      list.forEach(function(g) {
        var r = g.res[k], u = (r.u || {}).ats, ats = ((g.odds || {})[k] || {}).ats || {};
        var line = (ats.away || {}).line;
        if (!r.ats || r.ats === 'NA' || typeof line !== 'number' || line === 0) return;
        var f = line < 0 ? 'away' : 'home', size = Math.abs(line);
        var aRes = r.ats === 'P' ? 'T' : r.ats, fr = f === 'away' ? aRes : flipRes(aRes), fi = f === 'away' ? 0 : 1;
        for (var i = 0; i < B.length; i++) if (size >= B[i][1] && size <= B[i][2]) {
          addRec(fav[i], fr, u ? u[fi] : fbu(fr));
          addRec(dog[i], flipRes(fr), u ? u[1 - fi] : fbu(flipRes(fr)));
          break;
        }
      });
      cards.push(boardCard('Favorites by line', s.tag + ' ' + spreadWord() + ' cover rate', B.map(function(b, i) { return boardRow('Favored by ' + b[0], fav[i]); }), 'Pushes left out of cover %', 'W-L-P'));
      cards.push(boardCard('Underdogs by line', s.tag + ' Spread cover rate', B.map(function(b, i) { return boardRow('Getting ' + b[0], dog[i]); }), 'Units at the closing price (-110 when only the line was saved)', 'W-L-P'));
    }
    var pills = (canMl && canAts ? '<div class="seg-toggle" role="group" aria-label="Market"><button class="seg-btn" data-board-mk="ml" aria-pressed="' + (mk === 'ml') + '">Moneyline</button>' +
        '<button class="seg-btn" data-board-mk="ats" aria-pressed="' + (mk === 'ats') + '">' + spreadWord() + '</button></div>' : '') +
      '<div class="seg-toggle" role="group" aria-label="Show"><button class="seg-btn" data-board-view="pct" aria-pressed="' + (boardState.view === 'pct') + '">Win %</button>' +
      '<button class="seg-btn" data-board-view="units" aria-pressed="' + (boardState.view === 'units') + '">Profit</button></div>';
    return stSection('statsBoard', 'Money Board', pills, '<p class="st-sec-sub">' + esc(s.tag) + ' ' + (mk === 'ml' ? 'Moneyline' : spreadWord()) + ' at closing prices</p>' +
      '<div class="st-grid st-grid-2">' + cards.join('') + '</div>');
  }

  // ---- Edges: what happens after the opening segment ----
  // Lead-size buckets per sport and segment (Chris's QA spec): [small max,
  // medium max]; bigger = big. MLB's 1st inning: 1 / 2 / 3+.
  var LEAD_CUTS = {
    nhl: { '1p': [1, 2] },
    nba: { '1q': [4, 9], '1h': [6, 12] }, wnba: { '1q': [4, 9], '1h': [6, 12] }, ncaab: { '1h': [6, 14] },
    nfl: { '1q': [3, 7], '1h': [7, 14] }, ncaaf: { '1q': [7, 14], '1h': [7, 16] },
    mlb: { '1i': [1, 2], 'f5': [1, 3] }
  };
  var EDGE_NAME = { '1p': ['Intermission Edge', 'After the 1st period'], '1q': ['Quarter Edge', 'After the 1st quarter'], '1h': ['Halftime Edge', 'At halftime'],
                    'f5': ['F5 Edge', 'After 5 innings'], '1i': ['1st Inning Edge', 'After the 1st inning'] };
  // Best Closers / Biggest Faders need this many games (college plays fewer, against more teams)
  var CLOSER_MIN = { ncaab: 8, ncaaf: 6 };
  // the build sets each bucket to about a third of the games (scripts/lead_cuts.py: D.leadCuts)
  function leadCuts(k) { return (D.leadCuts || {})[k] || (LEAD_CUTS[D.sport] || {})[k]; }
  function edgeSegs() { return D.segments.filter(function(s) { return leadCuts(s.key); }); }
  function fbu(res) { return res === 'W' ? 0.9091 : res === 'L' ? -1 : 0; }   // spreads and totals at -110
  // "in the NBA", "in MLB", "in college basketball"
  function leagueIn() { return { ncaab: 'college basketball', ncaaf: 'college football', mlb: 'MLB' }[D.sport] || 'the ' + D.label; }
  function segAdj(k) { return k === 'f5' ? 'F5' : seg(k).label.replace(/^1st /, '1st-').toLowerCase(); }
  function brk(k) { return EDGE_NAME[k][1].toLowerCase(); }
  // the break-even American price for a rate: -(p/(1-p))*100 at 50%+, else
  // +((1-p)/p)*100, to the nearest 5; none at 0% or 100%
  function worthAt(p) {
    if (!(p > 0 && p < 1)) return '-';
    var v = Math.round((p >= 0.5 ? -(p / (1 - p)) * 100 : ((1 - p) / p) * 100) / 5) * 5;
    if (Math.abs(v) > 2000) return '-';   // past -2000 / +2000: no price worth quoting
    return (v > 0 ? '+' : '-') + Math.abs(v);
  }
  // {n, cards [{id, title, sub, rows [{label, n, hit}]}], rows (all of them), later {team: rest-of-game {w, l, t, m}}}
  function edgeRows(games, k) {
    var cuts = leadCuts(k);
    var basketball = ['nba', 'wnba', 'ncaab'].indexOf(D.sport) !== -1, football = isFootball(), hockey = D.sport === 'nhl';
    var unit = hockey ? 'goal' : D.sportType === 'baseball' ? 'run' : 'point';
    function lbl(a, b) { return b === 999 ? a + '+' : a === b ? String(a) : a + '-' + b; }
    var sizes = [[1, cuts[0]], [cuts[0] + 1, cuts[1]], [cuts[1] + 1, 999]];
    var R = {};
    function row(id, label) { return (R[id] = R[id] || { id: id, label: label, n: 0, hit: 0 }); }
    function add(id, label, hit) { var x = row(id, label); x.n++; if (hit) x.hit++; }
    sizes.forEach(function(sz, i) { row('lead' + i, 'Up ' + lbl(sz[0], sz[1]) + ' ' + unit + (sz[0] === 1 && sz[1] === 1 ? '' : 's')); });
    var close = football ? 7 : 5, bigLine = basketball ? 10 : football ? 7 : null;
    var list = graded(games, k).filter(function(g) { return g.state === 'final' && g.as != null && g.hs != null; });
    var later = {};   // team -> rest-of-game record and margin, for the closers lists
    list.forEach(function(g) {
      var r = g.res[k], a = r.sc[0], h = r.sc[1], fa = g.as, fh = g.hs, lead = Math.abs(a - h);
      var leader = a > h ? 'away' : a < h ? 'home' : null, trail = leader === 'away' ? 'home' : 'away';
      var winner = fa > fh ? 'away' : fa < fh ? 'home' : null, fav = gameFav(g);
      var margin = function(side) { return side === 'away' ? fa - fh : fh - fa; };
      var spread = function(side) { return g.fs == null ? null : side === 'home' ? g.fs : -g.fs; };
      if (leader) {
        for (var i = 0; i < sizes.length; i++) if (lead >= sizes[i][0] && lead <= sizes[i][1]) add('lead' + i, null, winner === leader);
        var sp = spread(leader);
        if (sp != null && margin(leader) + sp !== 0) add('cover', 'Leader covers the full-game spread', margin(leader) + sp > 0);
        if (fav && leader !== fav) {
          add('favback', 'Favorite comes back to win', winner === fav);
          var fsp = spread(fav);
          if (fsp != null && margin(fav) + fsp !== 0) add('favcover', 'Favorite still covers the spread', margin(fav) + fsp > 0);
          add('dogwin', 'Underdog holds on to win', winner === leader);
        }
      } else {
        add('tiehome', 'Home team wins', winner === 'home');
        if (fav) add('tiefav', 'Favorite wins', winner === fav);
      }
      // close games at the half (college basketball and football)
      if (k === '1h' && (D.sport === 'ncaab' || football) && lead <= close) {
        add('chome', 'Home team wins', winner === 'home');
        if (fav) {
          add('cfav', 'Favorite wins', winner === fav);
          var csp = spread(fav);
          if (csp != null && margin(fav) + csp !== 0) add('cfavcov', 'Favorite covers the spread', margin(fav) + csp > 0);
        }
        if (bigLine && g.fs != null && Math.abs(g.fs) >= bigLine) {
          var bf = g.fs < 0 ? 'home' : 'away', bm = margin(bf) + spread(bf);
          if (bm !== 0) add('bigfav', 'Big favorite (' + bigLine + '+) covers', bm > 0);
        }
      }
      // does the pace carry: the segment's O/U, then the game's
      if (g.ft != null && fa + fh !== g.ft) {
        var gOver = fa + fh > g.ft;
        if (isRfi(k) && r.rfi) {
          if (r.rfi === 'Y') add('oo', 'Run in the 1st: game goes Over', gOver); else add('uu', 'No run in the 1st: game goes Under', !gOver);
        } else if (r.tot && r.tot !== 'NA' && r.tot !== 'P') {
          if (r.tot === 'O') add('oo', seg(k).tag + ' Over: game goes Over', gOver); else add('uu', seg(k).tag + ' Under: game goes Under', !gOver);
        }
      }
      var tl = (((g.odds || {})[k] || {}).total || {}).line;
      if (k === '1h' && g.ft != null && typeof tl === 'number') {
        var hot = basketball ? (D.sport === 'ncaab' ? 6 : 8) : 7, h1 = a + h, h2 = fa + fh - h1, h2line = g.ft - tl;
        if (h1 >= tl + hot && h2 !== h2line) add('hi', 'Hot 1st half (' + hot + '+ over): 2nd half Under', h2 < h2line);
        if (h1 <= tl - hot && h2 !== h2line) add('lo', 'Cold 1st half (' + hot + '+ under): 2nd half Over', h2 > h2line);
      }
      if (football && k === '1q' && a === 0 && h === 0 && g.ft != null && fa + fh !== g.ft) add('fbq', 'Scoreless 1st quarter: game Under', fa + fh < g.ft);
      var two = g.als && g.hls && g.als.length > 1 && g.hls.length > 1;
      if (hockey && two) {
        var p2 = g.als[1] + g.hls[1];
        if (a + h >= 3) add('hi', '3+ goals in the 1st: 2nd period Under 1.5', p2 < 2);
        if (a + h === 0) add('lo', '0-0 after one: 2nd period Over 1.5', p2 > 1);
      }
      // bounce-back: the segment's loser wins the next stretch
      if (leader) {
        var aN = null, hN = null, next = '';
        if ((k === '1q' || k === '1p') && two) { aN = g.als[1]; hN = g.hls[1]; next = k === '1q' ? '2nd quarter' : '2nd period'; }
        else if (k === '1h' || k === 'f5' || k === '1i') { aN = fa - a; hN = fh - h; next = k === '1h' ? '2nd half' : edgeRest(k); }
        if (aN != null) add('bounce', segAdj(k).replace(/^./, function(c) { return c.toUpperCase(); }) + ' loser wins the ' + next, trail === 'away' ? aN > hN : hN > aN);
      }
      // rest of the game, for the closers lists
      [['away', fa - a, fh - h], ['home', fh - h, fa - a]].forEach(function(x) {
        var t = later[g[x[0]]] = later[g[x[0]]] || { w: 0, l: 0, t: 0, m: 0 };
        if (x[1] > x[2]) t.w++; else if (x[1] < x[2]) t.l++; else t.t++;
        t.m += x[1] - x[2];
      });
    });
    var tied = k === '1h' ? 'Tied at the break' : k === 'f5' ? 'Tied after five' : 'Tied after one';
    var C = [
      { id: 'hold', title: 'Does the ' + segAdj(k) + ' leader hold on?', sub: 'How often the team ahead ' + brk(k) + ' wins the game.', ids: ['lead0', 'lead1', 'lead2', 'cover'] },
      { id: 'trouble', title: 'Favorite in trouble', sub: 'The pregame favorite is behind ' + brk(k) + '.', ids: ['favback', 'favcover', 'dogwin'] },
      { id: 'tied', title: tied, sub: 'Level ' + brk(k) + ': who wins the game?', ids: ['tiehome', 'tiefav'] },
      { id: 'close', title: 'Close games at the half', sub: 'Within ' + close + ' points at halftime.', ids: ['chome', 'cfav', 'cfavcov', 'bigfav'] },
      { id: 'pace', title: 'Does the pace carry?', sub: 'A fast or slow ' + segAdj(k) + ' start, then the rest of the game.', ids: ['oo', 'uu', 'hi', 'lo', 'fbq'] },
      { id: 'bounce', title: 'Bounce-back', sub: 'The team that lost the ' + segAdj(k).replace(/-/g, ' ') + ' wins the next stretch.', ids: ['bounce'] }
    ];
    var cards = C.map(function(c) { return { id: c.id, title: c.title, sub: c.sub, rows: c.ids.filter(function(id) { return R[id] && R[id].n; }).map(function(id) { return R[id]; }) }; })
      .filter(function(c) { return c.rows.length; });
    return { n: list.length, cards: cards, rows: [].concat.apply([], cards.map(function(c) { return c.rows; })), later: later };
  }
  // every finished game's edges per segment, counted once a page load
  var EDGE_CACHE = {};
  function edgeData(k) { return EDGE_CACHE[k] || (EDGE_CACHE[k] = edgeRows(finalGames(), k)); }
  function edgeRest(k) { return k === '1p' ? 'periods 2-3 (and OT)' : k === '1q' ? 'quarters 2-4' : k === 'f5' ? 'innings 6-9' : k === '1i' ? 'innings 2-9' : 'the 2nd half'; }
  // Best Closers / Biggest Faders: each team's record over the rest of the
  // game (after the segment); a minimum of games (college: CLOSER_MIN), win
  // % leaves ties out, ties broken by the average margin
  function closerBoards(k, E, only) {
    E = E || edgeData(k);
    var min = CLOSER_MIN[D.sport] || 3;
    var teams = Object.keys(E.later).filter(function(t) { return D.teams[t] && (!only || only(t)); }).map(function(t) {
      var x = E.later[t], d = x.w + x.l, gp = x.w + x.l + x.t; return { t: t, x: x, p: d ? x.w / d : 0, q: d ? x.l / d : 0, d: d, avg: gp ? x.m / gp : 0 };
    }).filter(function(e) { return e.x.w + e.x.l + e.x.t >= min && e.d; });
    return {
      best: teams.slice().sort(function(a, b) { return b.p - a.p || b.avg - a.avg || (a.t < b.t ? -1 : 1); }),
      worst: teams.slice().sort(function(a, b) { return b.q - a.q || a.avg - b.avg || (a.t < b.t ? -1 : 1); })
    };
  }
  // the games on tonight's slate (football: this week's)
  function slateGames() {
    if (D.schedule === 'week') return (D.weeks || []).length ? weekGames(currentWeek(D.weeks)) : [];
    return (D.games || {})[todayET()] || [];
  }
  function playsNow(slug) { return slateGames().filter(function(g) { return g.away === slug || g.home === slug; })[0] || null; }
  var NOW_WORD = function() { return D.schedule === 'week' ? 'Plays this week' : 'Plays tonight'; };
  function teamCell(slug) { return teamLink(slug, badge(slug, 22) + '<span class="st-abbr">' + esc(tcode(slug)) + '</span>'); }
  function closerRow(e, key) {
    return stRow(teamCell(e.t), e.x.w + '-' + e.x.l + '-' + e.x.t, Math.round(100 * e[key]) + '%',
      '<span class="st-u">' + (playsNow(e.t) ? '<span class="ed-now">' + NOW_WORD() + '</span>' : '') + '</span>', 'st-team');
  }
  // a situation card: rows under 10 games hidden (with a note)
  function edgeCard(c, flag) {
    var shown = c.rows.filter(function(x) { return x.n >= 10; }), hid = c.rows.length - shown.length;
    if (!shown.length) return '';   // nothing to show: no card
    var rows = shown.map(function(x) {
      var p = x.hit / x.n;
      return stRow(x.label, String(x.n), Math.round(100 * p) + '%', '<span class="st-u">' + worthAt(p) + '</span>');
    });
    return stCard(c.title, c.sub, (rows.length ? stHead('Games', 'How often', 'Worth it at') + lockRows(rows, flag) : '') +
      (hid ? '<p class="st-note">' + (rows.length ? hid + ' more row' + (hid === 1 ? '' : 's') + ' under 10 games, hidden for now.' : 'Under 10 games so far, hidden for now.') + '</p>' : ''), '', 'ed-card');
  }
  // Watch tonight (football: this week): the top-5 closers and faders on the slate
  function watchCard(B, flag) {
    var rows = [];
    [['best', 'Closer', 'p'], ['worst', 'Fader', 'q']].forEach(function(x) {
      B[x[0]].slice(0, 5).forEach(function(e, i) {
        var g = playsNow(e.t);
        if (!g) return;
        var opp = g.away === e.t ? g.home : g.away;
        rows.push(stRow(teamCell(e.t), x[1] + ' #' + (i + 1), Math.round(100 * e[x[2]]) + '%',
          '<span class="st-u">' + (g.away === e.t ? '@ ' : 'vs ') + esc(tcode(opp)) + '</span>', 'st-team'));
      });
    });
    if (!rows.length) return '';   // no closer or fader on the slate: no card
    var wk = D.schedule === 'week';
    var title = wk ? 'Watch this week' : 'Watch tonight &middot; ' + new Date(todayET() + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
    return stCard(title, 'Top-5 closers and faders ' + (wk ? 'playing this week' : 'on tonight&rsquo;s slate') + '.',
      stHead('Rank', 'Rate', 'Game') + lockRows(rows, flag), '', 'st-wide');
  }
  // the hub's Number: how a row reads as a sentence ("71% of teams up 5-9 points after the 1st quarter win the game")
  function edgeSay(x, k) {
    var b = brk(k), m = /^lead/.test(x.id) ? 'of teams ' + x.label.toLowerCase() + ' ' + b + ' win the game' : {
      favback: 'of favorites trailing ' + b + ' come back to win', dogwin: 'of underdogs leading ' + b + ' hold on to win',
      tiehome: 'of games tied ' + b + ' are won by the home team', tiefav: 'of games tied ' + b + ' are won by the favorite'
    }[x.id];
    return m || b + ': ' + x.label.replace(/^./, function(c) { return c.toLowerCase(); });
  }

  // the page's segment toggle, pinned under the header like Matchups / Odds;
  // the Full Run's pills last, in the Premium style
  function statsSegBar(k) {
    var segs = D.segments.concat(D.fullRun || []);
    return segs.length > 1 ? '<div class="ob-stick st-stick" id="stStick"><div class="sport-seg-row odds-controls"><div class="seg-toggle" id="statsSeg">' +
      segs.map(function(s) { return segPill(s, s.key === k, !!frSeg(s.key), 'data-seg'); }).join('') + '</div></div></div>' : '';
  }
  function statsK() { return frSeg(SEG_CUR) ? SEG_CUR : getSeg(); }
  // a Full Run segment's games in the first segments' shape (res[k],
  // odds[k]), so the Overview's cards count them the same way. lined: only
  // the games with a line, the ML only where it was priced (records count
  // only games with a line for the market); NHL's 2nd / 3rd period have no
  // lines, so every game
  function frView(games, k, lined) {
    return games.map(function(g) {
      var r = (g.fr || {})[k], res = {}, odds = {};
      if (!r) return null;
      if (lined && k !== '2p' && k !== '3p') {
        if (!(r.u || {}).su) { r = Object.assign({}, r); delete r.su; }
        if (!r.su && !r.ats && !r.tot) return null;
      }
      res[k] = r; odds[k] = (g.fo || {})[k];
      return Object.assign({}, g, { res: res, odds: odds });
    }).filter(Boolean);
  }
  function wireStatsSeg(draw) {
    var segEl = document.getElementById('statsSeg');
    if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
    stickBelowNav(document.getElementById('stStick'));
  }
  function noStats() { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet - stats appear once games are played.'); }
  function keepPlace(anchor) {
    var keep = anchor ? { id: anchor.id, top: anchor.getBoundingClientRect().top } : null;
    return function() { if (keep) { var el = document.getElementById(keep.id); if (el) window.scrollBy(0, el.getBoundingClientRect().top - keep.top); } };
  }
  function splitsStandout(k) { var e = leagueSit(); return e && e.standout ? e.standout(k) : null; }
  // /stats/: Season Results, Money Board, Scoring
  function renderStats() {
    if (!D.season || !allDates().length) { noStats(); return; }
    function draw(anchor) {
      var back = keepPlace(anchor);
      var k = statsK(), fr = !!frSeg(k), range = tfRange(), games = fr ? frView(range.games, k, true) : range.games, N = graded(games, k).length;
      var cards = seasonCards(games, k);
      var season = stSection('statsSeason', 'Season Results <small class="st-count">' + N + ' game' + (N === 1 ? '' : 's') + '</small>', tfControls(), range.line +
        (N ? '<div class="st-grid">' + cards.map(function(c) { return cardHtml(c, N); }).join('') + '</div>' +
          (seasonMarked(cards, N) ? '<p class="st-foot"><sup>*</sup> Games without a saved line aren&rsquo;t counted.</p>' : '')
          : emptyNote('No graded games in this range yet.')));
      var scoring = stSection('statsScoring', 'Scoring', '', D.sport === 'nhl' && !fr ? goalStats(finalGames()) : '<div id="statsScoringBody"></div>');
      var board = k === '2p' || k === '3p' ? '' : moneyBoard(fr ? frView(finalGames(), k, true) : finalGames(), k);
      // PREMIUM.fullRun on: a Full Run pill's sections blurred for free visitors
      app.innerHTML = statsSegBar(k) + lockFrom([season + statsLeaders(k) + board + scoring], fr ? 0 : 1, 'fullRun');
      var lm = document.getElementById('leadMkt');
      if (lm) lm.onclick = function(e) { var b = e.target.closest('[data-lead]'); if (b) { LEAD_MK = b.getAttribute('data-lead'); draw(document.getElementById('leaders')); } };
      wireStatsSeg(function() { draw(document.getElementById('statsSeason')); });
      wireTf(function() { draw(document.getElementById('statsSeason')); });
      app.querySelectorAll('[data-board-view]').forEach(function(b) { b.onclick = function() { boardState.view = b.getAttribute('data-board-view'); draw(document.getElementById('statsBoard')); }; });
      app.querySelectorAll('[data-board-mk]').forEach(function(b) { b.onclick = function() { boardState.market = b.getAttribute('data-board-mk'); draw(document.getElementById('statsBoard')); }; });
      if (D.sport !== 'nhl' || fr) renderScoring(fr ? frView(range.games, k, false) : range.games, k);
      wireTips(app);
      back();
    }
    draw();
    // the Teams index's "All leaders" link
    if (location.hash === '#leaders') { var lh = document.getElementById('leaders'); if (lh) lh.scrollIntoView({ block: 'start' }); }
  }

  // Stats Overview "Leaders": market pills, then Top 5 / Bottom 5 (10+
  // games), the Teams index Leaders' rows: rank · logo · team · % (record) ·
  // units. Ranked by units where most teams have prices, else by the %.
  var LEAD_MK = null, LEAD_MIN = 10;
  function statsLeaders(k) {
    var ps = frSeg(k) ? frMarkets(k).filter(function(p) { return p.m !== 'gpg'; }).map(function(p) {
      return { k: p.k, m: p.m, label: p.m === 'per' ? 'Result' : p.m === 'ml' ? 'Moneyline' : p.m === 'ats' ? spreadWord() : 'Total' };
    }) : periodFamily() ? tmMarkets() : tmMarkets(k);
    if (!ps.length) return '';
    var p = ps.filter(function(x) { return x.k + '|' + x.m === LEAD_MK; })[0] || ps[0];
    LEAD_MK = p.k + '|' + p.m;
    var list = Object.keys(D.teams).map(function(s) { return { s: s, a: tmAgg(s, p.k, p.m, 'all', teamGames(s)) }; })
      .filter(function(x) { return x.a.gp >= LEAD_MIN && x.a.pct != null; });
    var byU = list.filter(function(x) { return x.a.priced; }).length * 2 > list.length;
    if (byU) list = list.filter(function(x) { return x.a.priced; });
    list.sort(function(x, y) { return byU ? y.a.units - x.a.units : y.a.pct - x.a.pct || y.a.gp - x.a.gp; });
    function row(x, i) {
      return '<li><a class="tll-row sl-row" href="' + teamUrl(x.s) + '"><span class="tll-rank">' + (i + 1) + '</span>' + badge(x.s, 20) +
        '<span class="tll-name">' + nameHtml(x.s) + '</span><span class="tll-val">' + tmPct(x.a.pct) + ' <span class="tll-sub">(' + tpRec(x.a, p.m) + ')</span></span>' +
        '<span class="tll-val">' + tmUnits(x.a) + '</span></a></li>';
    }
    function card(title, rows) {
      return '<div class="st-card tll-card"><div class="st-head"><h4>' + esc(title) + '</h4></div><ol class="tll-list">' + rows.join('') + '</ol></div>';
    }
    var pills = '<div class="seg-toggle" id="leadMkt">' + ps.map(function(x) {
      return '<button class="seg-btn" data-lead="' + x.k + '|' + x.m + '" aria-pressed="' + (x === p) + '">' + esc((periodFamily() && ps.some(function(y) { return y.k !== x.k; }) && x.label.indexOf(segTag(x.k)) !== 0 ? segTag(x.k) + ' ' : '') + x.label) + '</button>';
    }).join('') + '</div>';
    var n = Math.min(5, Math.floor(list.length / 2)), what = TM_INFO[p.m].pct;
    var body = list.length < 2 ? emptyNote('Leaders show once teams have played ' + LEAD_MIN + ' games.')
      : '<div class="ldr-grid">' + card('Top 5 · ' + what, list.slice(0, n).map(row)) +
        card('Bottom 5 · ' + what, list.slice(-n).reverse().map(row)) + '</div>' +
        '<p class="st-foot">' + (byU ? 'Ranked by units' : 'Ranked by ' + what.toLowerCase() + ' (too few saved prices to rank by units)') + '. ' + LEAD_MIN + '+ games.</p>';
    return stSection('leaders', 'Leaders', pills, body);
  }

  // /stats/splits/: Situational Results, league-wide
  function renderSplits() {
    if (!D.season || !allDates().length) { noStats(); return; }
    var eng = leagueSit();
    if (!eng) { app.innerHTML = emptyNote('Situational Results aren&rsquo;t set up for ' + esc(D.label) + ' yet.'); return; }
    // premium: one filter at a time (the time range here; conference in situational.js)
    function comboOk() { return !(premiumLocked('splitCombine') && tf.mode !== 'all' && eng.state.conf); }
    function draw(anchor) {
      var back = keepPlace(anchor);
      var k = getSeg(), r = tfDates();
      eng.state.k = k;
      app.innerHTML = '<div id="statsSit"></div>';
      // one sticky bar: segment, time range, conference (situational.js leagueView)
      eng.league(document.getElementById('statsSit'), { range: r, controls: tfControls(), line: r && r.label ? '<div class="sc-week">' + r.label + '</div>' : '',
        after: function(box) { wireTf(function() { draw(document.getElementById('statsSit')); }, comboOk); stickBelowNav(box.querySelector('.sit-stick')); } });
      sitGlossary(k);
      back();
    }
    SIT_ON_SEG = function(k, anchor) { setSeg(k); draw(anchor); };
    draw();
  }

  // /stats/edges/: one segment at a time under one sticky bar (segment,
  // time range, conference for college): Watch tonight, the situation
  // cards two to a row, then Best closers and Biggest faders
  var edgeConf = '';
  function edgeConfs() {
    if (D.sport !== 'ncaab' && D.sport !== 'ncaaf') return [];
    var s = {};
    Object.keys(D.teams).forEach(function(t) { var c = D.teams[t].conference; if (c) s[c] = 1; });
    return Object.keys(s).sort();
  }
  function renderEdges() {
    if (!D.season || !allDates().length) { noStats(); return; }
    var es = edgeSegs();
    if (!es.length) { app.innerHTML = emptyNote('Edges aren&rsquo;t set up for ' + esc(D.label) + ' yet.'); return; }
    function draw(anchor) {
      var back = keepPlace(anchor);
      var k = es.some(function(s) { return s.key === getSeg(); }) ? getSeg() : es[0].key, flag = 'edge' + k;
      var confs = edgeConfs(), inConf = edgeConf ? function(t) { return (D.teams[t] || {}).conference === edgeConf; } : null;
      var range = tfRange(), games = range.games;
      if (inConf) games = games.filter(function(g) { return inConf(g.away) || inConf(g.home); });
      var E = edgeRows(games, k), B = closerBoards(k, E, inConf), min = CLOSER_MIN[D.sport] || 3;
      var bar = '<div class="ob-stick sit-stick" id="edStick"><div class="sit-bar"><div class="sit-row1">' + (es.length > 1 ? segToggle('edSeg', k) : '') + '</div>' +
        '<div class="sit-full">' + tfControls() + (confs.length ? '<select class="conf-select" id="edConf" aria-label="Conference"><option value="">All conferences</option>' +
          confs.map(function(c) { return '<option value="' + esc(c) + '"' + (c === edgeConf ? ' selected' : '') + '>' + esc(c) + '</option>'; }).join('') + '</select>' : '') + '</div></div></div>';
      var body = '<p class="st-sec-sub">' + EDGE_NAME[k][1] + ' &middot; ' + E.n + ' finished game' + (E.n === 1 ? '' : 's') + '</p>' + range.line;
      if (!E.n) body += emptyNote('No finished games with the ' + esc(seg(k).label) + ' graded in this range yet.');
      else {
        body += watchCard(B, flag) +
          '<div class="st-grid st-grid-2 ed-grid">' + E.cards.map(function(c) { return edgeCard(c, flag); }).join('') + '</div>' +
          '<div class="st-grid st-grid-2 ed-grid">' +
            (B.best.length ? stCard('Best closers', 'Win ' + edgeRest(k) + ' most often (' + min + '+ games).', stHead('W-L-T', 'Win %', '') + lockRows(B.best.slice(0, 5).map(function(e) { return closerRow(e, 'p'); }), flag)) : '') +
            (B.worst.length ? stCard('Biggest faders', 'Lose ' + edgeRest(k) + ' most often (' + min + '+ games).', stHead('W-L-T', 'Loss %', '') + lockRows(B.worst.slice(0, 5).map(function(e) { return closerRow(e, 'q'); }), flag)) : '') +
          '</div>';
      }
      if (premiumLocked('edgesPage')) body = '<div class="pm-blur" aria-hidden="true">' + body + '</div><a class="pm-unlock" href="' + ROOT + '#premium">Unlock with Premium</a>';
      app.innerHTML = bar + '<section class="st-sec" id="edBody">' + body + '</section>';
      var segEl = document.getElementById('edSeg');
      if (segEl) segEl.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); draw(); } };
      var cs = document.getElementById('edConf');
      if (cs) cs.onchange = function() { edgeConf = cs.value; draw(); };
      wireTf(function() { draw(); });
      stickBelowNav(document.getElementById('edStick'));
      wireTips(app);
      back();
    }
    draw();
  }

  // --------------------------------------------------------- Trends page
  // League Trends (cards from {slug}/trends.json, scripts/trends.py: frozen
  // per slate once its first game starts), then Matchup Trends and Streak
  // Trends, worked out here from each team's games before the slate. Copy
  // and tooltips come from content/definitions.json (TR.tips).
  var TR = null;
  // Each section's own filters (League, Streak and Matchup Trends): the
  // segment (sports with more than one), the market, the side. Defaults:
  // the first segment, All markets, All sides.
  var TRF = {};
  function trSegs() { return D.segments.filter(function(s) { return TR.markets.some(function(x) { return x[0] === s.key; }); }); }
  function trState(sec) {
    var st = TRF[sec] || (TRF[sec] = { seg: trSegs()[0].key, mkt: 'all', side: 'all' });
    if (!trSegs().some(function(s) { return s.key === st.seg; })) st.seg = trSegs()[0].key;
    if (st.mkt !== 'all' && !TR.markets.some(function(x) { return x[0] === st.seg && x[1] === st.mkt; })) st.mkt = 'all';
    return st;
  }
  // "1Q · 1H"; MLB "1st Inning · F5"
  function trSegLabel(s) { return D.sportType === 'baseball' ? (s.key === 'f5' ? 'F5' : '1st Inning') : s.tag; }
  // the site's market names: Spread · O/U · Moneyline; NHL Moneyline · O/U 1.5 · BTTS · 3-Way; MLB NRFI/YRFI · F5 ML · F5 Run Line · F5 Total
  function trMktLabel(x) {
    if (D.sportType === 'baseball') return { rfi: 'NRFI/YRFI', ml: 'F5 ML', ats: 'F5 Run Line', total: 'F5 Total' }[x[1]] || x[2];
    return { ats: spreadWord(), total: D.sport === 'nhl' ? 'O/U 1.5' : 'O/U', ml: 'Moneyline', btts: 'BTTS', ml3: '3-Way' }[x[1]] || x[2];
  }
  // the three rows under a section's heading (phones: each scrolls sideways)
  function trFilters(sec) {
    var st = trState(sec), segs = trSegs();
    function row(f, opts, cur, label) {
      return '<div class="seg-toggle tr-frow" role="group" aria-label="' + label + '">' + opts.map(function(o) {
        return '<button class="seg-btn" data-trf="' + f + '" data-v="' + o[0] + '" aria-pressed="' + (o[0] === cur) + '">' + esc(o[1]) + '</button>';
      }).join('') + '</div>';
    }
    return '<div class="tr-filters">' +
      (segs.length > 1 ? row('seg', segs.map(function(s) { return [s.key, trSegLabel(s)]; }), st.seg, 'Segment') : '') +
      row('mkt', [['all', 'All']].concat(TR.markets.filter(function(x) { return x[0] === st.seg; }).map(function(x) { return [x[1], trMktLabel(x)]; })), st.mkt, 'Market') +
      row('side', [['all', 'All'], ['home', 'Home'], ['away', 'Away']], st.side, 'Side') + '</div>';
  }
  function tcode(slug) { var t = team(slug); return t.code || String(t.short || slug).slice(0, 4).toUpperCase(); }
  function segWord(k) { return anySeg(k).label.toLowerCase(); }
  function segWords(k) { var w = segWord(k); return /innings$/.test(w) ? w : /half$/.test(w) ? w.replace(/half$/, 'halves') : w + 's'; }
  function flipR(x) { return x === 'W' ? 'L' : x === 'L' ? 'W' : x; }
  // One side's result in a segment: W / L / P (a tie or push), or null.
  // ml3: a tied segment loses a team bet.
  function sideRes(g, k, m, side) {
    var r = (g.res || {})[k];
    if (!r || !r.sc || r.na) return null;
    var x = r[m === 'ats' ? 'ats' : 'su'];
    if (!x || x === 'NA') return null;
    if (side === 'home') x = flipR(x);
    if (m === 'ml3') return x === 'W' ? 'W' : 'L';
    return x === 'T' ? 'P' : x;
  }
  // A game bet's result: over / under, yes / no (BTTS, a 1st-inning run), tie.
  function gameRes(g, k, m, bet) {
    var r = (g.res || {})[k];
    if (!r || !r.sc || r.na) return null;
    if (m === 'ml3') return r.su === 'T' ? 'W' : r.su ? 'L' : null;
    var x = r[{ total: 'tot', btts: 'btts', rfi: 'rfi' }[m]];
    if (!x || x === 'NA') return null;
    if (m === 'total') return x === 'P' ? 'P' : (x === 'O') === (bet === 'over') ? 'W' : 'L';
    return (x === 'Y') === (bet === 'yes') ? 'W' : 'L';
  }
  function started(g) { return g.state === 'in' || g.state === 'final' || (g.start && Date.now() >= Date.parse(g.start)); }
  function betRes(g, c, x) { return x.side ? sideRes(g, c.seg, c.mk, x.side) : gameRes(g, c.seg, c.mk, x.bet); }
  // A row's status, neutral: the start time, LIVE or FINAL
  function rowStatus(g) { return g.state === 'final' ? 'FINAL' : started(g) ? 'LIVE' : trTime(g.start); }
  function pct0(x) { return Math.round(x * 100) + '%'; }
  // Start time; football rows say the day ("Sun 1:00 PM")
  function trTime(iso) {
    if (!iso || D.schedule !== 'week') return timeET(iso);
    return new Date(iso).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' }).replace(',', '');
  }
  function codeLink(slug) { return teamLink(slug, esc(tcode(slug))); }
  // a trend row's "Last time" line: a click or tap opens it (one at a time)
  if (!window.__lastRows) {
    window.__lastRows = true;
    var lastRow = function(r) {
      var open = r.getAttribute('aria-expanded') !== 'true';
      document.querySelectorAll('.tr-has-last[aria-expanded="true"]').forEach(function(x) { x.setAttribute('aria-expanded', 'false'); });
      r.setAttribute('aria-expanded', String(open));
    };
    document.addEventListener('click', function(e) {
      var r = e.target.closest ? e.target.closest('.tr-has-last') : null;
      if (r && !e.target.closest('a, button')) lastRow(r);
    });
    document.addEventListener('keydown', function(e) {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.classList && e.target.classList.contains('tr-has-last')) { e.preventDefault(); lastRow(e.target); }
    });
  }
  var TR_ROWS = 5;   // game rows per card before "Show all N games"
  // games not started (soonest first), then live, then finished
  function rowOrder(g) { return g.state === 'final' ? 2 : started(g) ? 1 : 0; }

  // One league card. The "i": the title, what it means and how it compares
  // to the league (nothing else). The "Last time" line under the rows shows
  // only when the trend's show_last switch is on (off by default).
  function showLast(c) { return c.last && ((TR.tips || {}).show_last || []).indexOf(c.angle) !== -1 ? c.last : ''; }
  function trendCard(c) {
    var last = showLast(c);
    var list = c.games.map(function(x) { return { x: x, g: findGame(x.id) }; })
      .filter(function(o) { return o.g && lined(o.g, c.seg); })
      .sort(function(a, b) { return (rowOrder(a.g) - rowOrder(b.g)) || ((a.g.start || '') < (b.g.start || '') ? -1 : 1); });
    var rows = list.map(function(o, i) {
      var g = o.g, x = o.x;
      // the logo loads right away (a lazy one could stay blank as rows move)
      var bet = x.side ? 'Bet ' + badge(g[x.side], 16).replace(/ loading="lazy"/g, '') + ' ' + codeLink(g[x.side]) : esc(x.label);
      // the trend's "Last time" line under the row: hover or click (desktop), tap (phones, ▾)
      return '<div class="tr-row' + (last ? ' tr-has-last' : '') + '"' + (i >= TR_ROWS ? ' hidden data-extra' : '') + (last ? ' tabindex="0" aria-expanded="false"' : '') + '><span class="tr-time">' + esc(rowStatus(g)) + '</span>' +
        '<span class="tr-match">' + codeLink(g.away) + ' @ ' + codeLink(g.home) + '</span>' +
        '<span class="tr-bet">' + bet + '</span>' + (last ? '<i class="tr-caret" aria-hidden="true">&#9662;</i></div><p class="tr-last">' + esc(last) + '</p>' : '</div>');
    }).join('');
    var more = list.length > TR_ROWS ? '<button type="button" class="tr-more tr-all">Show all ' + list.length + ' games</button>' : '';
    var rec = c.mk === 'ml3' && c.avg != null
      ? 'Hit ' + c.w + ' of ' + (c.w + c.l) + ' at avg ' + priceTxt(c.avg) + ' · <span class="' + unitCls(c.units) + '">' + fmtUnits(c.units) + '</span>'
      : pct0(c.rate) + ' (' + c.w + '-' + c.l + ') · <span class="' + unitCls(c.units) + '">' + fmtUnits(c.units) + '</span>';
    var avg = c.mk === 'ml3' && c.avg != null ? '' : '<p class="ht-avg">League average ' + pct0(c.base) + '</p>';
    return '<div class="tr-card"><div class="tr-top"><span class="lt-tag">' + esc(c.tag) + '</span></div>' +
      '<h3 class="tr-title">' + esc(c.title) + '</h3><div class="tr-rec" title="' + esc((TR.tips.record_line || {}).tooltip || '') + '">' + rec + '</div>' + avg +
      '<div class="tr-rows">' + rows + '</div>' + more + '</div>';
  }
  // The "All" view: 3-way ML cards never in the first 8, at most one, never a Tie card
  var ALL_NO_ML3 = 8;
  function allCards(cards) {
    var rest = cards.filter(function(c) { return c.mk !== 'ml3'; });
    var one = cards.filter(function(c) { return c.mk === 'ml3' && c.dir; })[0];   // the best side card ("Tie:" cards have no dir)
    if (one && rest.length >= ALL_NO_ML3) {
      var rank = cards.slice(0, cards.indexOf(one)).filter(function(c) { return c.mk !== 'ml3'; }).length;
      rest.splice(Math.max(ALL_NO_ML3, rank), 0, one);
    }
    return rest;
  }
  // the team page's last-8 dots (Trends pages have none)
  function dots(seq, kind) {
    return '<span class="tr-dots" aria-hidden="true">' + seq.slice(-8).map(function(v) {
      return '<i class="' + (v === kind ? 'on' : v === 'T' || v === 'P' ? 'mid' : '') + '"></i>';
    }).join('') + '</span>';
  }

  // ---- each team's season in one segment, for Matchup and Streak Trends
  // seq per market: [{r, g}] oldest first. ml: W / L / T; ats: W / L / P;
  // total: O / U / P; btts, rfi: Y / N.
  var TEAM_SEQ = {};
  function teamSeqs(before, k) {
    var key = before + '|' + k;
    if (TEAM_SEQ[key]) return TEAM_SEQ[key];
    var out = {};
    allDates().forEach(function(d) {
      if (d >= before) return;
      D.games[d].forEach(function(g) {
        var r = (g.res || {})[k];
        if (g.state !== 'final' || !r || !r.sc || r.na) return;
        ['away', 'home'].forEach(function(side) {
          function mk() { return { ml: [], ats: [], total: [], btts: [], rfi: [], mlD1: [] }; }
          var s = g[side], o = out[s] || (out[s] = mk());
          o.v = o.v || { home: mk(), away: mk() };   // Streak Trends' Home / Away: the team's runs at that venue
          [o, o.v[side]].forEach(function(o) {
            if (r.su && r.su !== 'NA') o.ml.push(side === 'away' ? r.su : flipR(r.su));
            // college Streak Trends: the moneyline against Division I (FBS) teams only
            if (r.su && r.su !== 'NA' && D.teams[g[side === 'away' ? 'home' : 'away']]) o.mlD1.push(side === 'away' ? r.su : flipR(r.su));
            if (r.ats && r.ats !== 'NA') o.ats.push(side === 'away' ? r.ats : flipR(r.ats));
            if (r.tot && r.tot !== 'NA') o.total.push(r.tot);
            if (r.btts === 'Y' || r.btts === 'N') o.btts.push(r.btts);
            if (r.rfi === 'Y' || r.rfi === 'N') o.rfi.push(r.rfi);
          });
        });
      });
    });
    return (TEAM_SEQ[key] = out);
  }
  function streakOf(seq) {
    var n = 0, last = seq[seq.length - 1];
    if (!last || last === 'T' || last === 'P') return null;
    for (var i = seq.length - 1; i >= 0 && seq[i] === last; i--) n++;
    return { kind: last, n: n };
  }
  var HIT = { ml: 'W', ats: 'W', total: 'O', btts: 'Y', rfi: 'Y' }, MISS = { ml: 'L', ats: 'L', total: 'U', btts: 'N', rfi: 'N' };
  // The team's lean in one market: {kind, x, y, rate} or null. ml counts
  // ties as games played; ats / total leave pushes out.
  var LEAN_MIN = 5;   // a lean ("usually"): 60%+ of a team's games, this many played
  function leanOf(m, seq) {
    var a = 0, b = 0, t = 0;
    seq.forEach(function(x) { if (x === HIT[m]) a++; else if (x === MISS[m]) b++; else t++; });
    var y = m === 'ml' ? a + b + t : a + b;
    if (y < LEAN_MIN) return null;
    var kind = a >= b ? HIT[m] : MISS[m], x = Math.max(a, b);
    return x / y >= 0.6 ? { kind: kind, x: x, y: y, rate: x / y } : null;
  }
  function countOf(m, seq, kind) {
    var x = 0, y = 0;
    seq.forEach(function(v) { if (v === kind) x++; if (m === 'ml' || v === HIT[m] || v === MISS[m]) y++; });
    return { x: x, y: y };
  }
  function lineWords(m, kind, k) {
    var s = segWord(k);
    if (m === 'ml') return 'has ' + (kind === 'W' ? 'won' : 'lost') + ' the ' + s;
    if (m === 'ats') return kind === 'W' ? 'has covered the ' + s + ' spread' : 'has failed to cover the ' + s + ' spread';
    if (m === 'total') return 'has gone ' + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : ' the ' + s + ' total');
    if (m === 'btts') return 'has gone BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
    return 'has gone ' + (kind === 'Y' ? 'YRFI' : 'NRFI');
  }
  function streakWords(slug, m, s, k) {
    var nm = shortName(slug), sw = segWords(k), n = s.n + ' straight';
    if (m === 'ml') return nm + ' have ' + (s.kind === 'W' ? 'won' : 'lost') + ' the ' + segWord(k) + ' ' + n;
    if (m === 'ats') return nm + ' have ' + (s.kind === 'W' ? 'covered' : 'failed to cover') + ' the ' + segWord(k) + ' spread ' + n;
    var w = m === 'total' ? (s.kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '') : m === 'btts' ? 'BTTS ' + (s.kind === 'Y' ? 'Yes' : 'No') : (s.kind === 'Y' ? 'YRFI' : 'NRFI');
    return nm + ' ' + sw + ' have gone ' + w + ' ' + n;
  }
  // The markets a pill covers (ml3 reads the moneyline's results)
  function teamMarkets(k, mkt) {
    var ms = TR.markets.filter(function(x) { return x[0] === k; }).map(function(x) { return x[1] === 'ml3' ? 'ml' : x[1]; });
    if (mkt && mkt !== 'all') ms = [mkt === 'ml3' ? 'ml' : mkt];
    return ms.filter(function(m, i) { return ms.indexOf(m) === i && HIT[m]; });
  }
  // Matchup Trends (option A): per market, each team's 60%+ lean (10+
  // games), strongest first, with its current streak of 3+
  var MT_MAX = 4;
  function mktHead(k, m) {
    var t = seg(k).tag;
    if (m === 'total') return t + ' O/U' + (D.sport === 'nhl' ? ' 1.5' : '');
    return t + ' ' + ({ ml: 'ML', ats: spreadWord(), btts: 'BTTS', rfi: 'NRFI' }[m] || m);
  }
  function sideWord(m, kind, k) {
    var t = seg(k).tag;
    if (m === 'ml') return (kind === 'W' ? 'Won ' : 'Lost ') + t;
    if (m === 'ats') return (kind === 'W' ? 'Covered ' : 'Didn’t cover ') + t;
    if (m === 'total') return kind === 'O' ? 'Over' : 'Under';
    if (m === 'btts') return kind === 'Y' ? 'Yes' : 'No';
    return kind === 'Y' ? 'YRFI' : 'NRFI';
  }
  // streak heat (CLAUDE.md --heat-1..4): 3-4, 5-6, 7-8, 9+, the same in every market
  function heatCls(n) { return 'heat heat-' + (n >= 9 ? 4 : n >= 7 ? 3 : n >= 5 ? 2 : 1); }
  function streakChip(m, st) {
    if (!st || st.n < 3) return '';
    return '<span class="mt-streak ' + heatCls(st.n) + '">' + st.n + ' straight</span>';
  }
  function mtLabelId(m, x) {
    if (!x || !x.away || !x.home) return null;
    if (m === 'total' || m === 'btts') return x.away !== x.home ? 'tug_of_war' : x.away === HIT[m] ? 'fireworks' : 'lockdown';
    if (m === 'ml') return x.away !== x.home ? 'mismatch' : x.away === 'W' ? 'heavyweights' : null;
    return null;
  }
  function mtChip(id, m, k) {
    var l = id && (TR.tips.matchup_labels || {})[id];
    return l ? labelChip(l.label, labelText(l, (TR.segments || {})[k] || 'opening segment', m === 'btts')) : '';
  }
  // a matchup label's definition: {segment}s reads "1st periods" (the first
  // five stays "first five"); BTTS labels have their own wording
  function labelText(l, seg, btts) {
    var t = (btts && l.tooltip_btts) || l.tooltip || '';
    return t.replace(/\{segment\}s/g, seg === 'first five' ? seg : seg + 's').replace(/\{segment\}/g, seg);
  }
  // a finished game's result for one team's lean: Hit / Miss / Push, or null
  function leanResult(g, k, m, side, kind) {
    var r = (g.res || {})[k];
    if (g.state !== 'final' || !r || !r.sc || r.na) return null;
    var v = m === 'ml' ? (r.su && r.su !== 'NA' ? (side === 'away' ? r.su : flipR(r.su)) : null)
      : m === 'ats' ? (r.ats && r.ats !== 'NA' ? (side === 'away' ? r.ats : flipR(r.ats)) : null)
      : m === 'total' ? (r.tot !== 'NA' ? r.tot : null) : m === 'btts' ? r.btts : r.rfi;
    if (!v) return null;
    return v === kind ? 'hit' : v === 'T' || v === 'P' ? 'push' : 'miss';
  }
  var RES_WORD = { hit: 'Hit', miss: 'Miss', push: 'Push' };
  // null when nothing qualifies (the game doesn't appear), else {html,
  // labels: [{id, m}], rate: the average of its lines' rates, start}.
  // One line per lean: NY · 1H Under (i) · 79% (11-3), then on past dates
  // the result (Hit / Miss / Push); today and later, the streak of 3+.
  // st: the section's filters (the market; the side: that team's lines
  // only, the label chips still from both teams).
  function matchupBlock(g, k, before, past, st) {
    var seqs = teamSeqs(before, k), groups = '', labels = [], rates = [];
    teamMarkets(k, st.mkt).forEach(function(m) {
      var lines = [], leans = {};
      ['away', 'home'].forEach(function(side) {
        var slug = g[side], seq = ((seqs[slug] || {})[m]) || [], ln = leanOf(m, seq);
        if (!ln) return;
        leans[side] = ln.kind;
        if (st.side !== 'all' && side !== st.side) return;
        var res = past ? leanResult(g, k, m, side, ln.kind) : null;
        var end = past ? (res ? '<span class="mt-res mt-r-' + res + '">' + RES_WORD[res] + '</span>' : '') : streakChip(m, streakOf(seq));
        lines.push({ rate: ln.rate, html: '<div class="mt-line">' + teamLink(slug, badge(slug, 18) + '<b>' + esc(tcode(slug)) + '</b>') +
          '<span class="mt-side">' + esc(stkWord(m, ln.kind, k)) + '</span>' +
          '<span class="mt-pct">' + pct0(ln.rate) + ' <span class="mt-rec">(' + ln.x + '-' + (ln.y - ln.x) + ')</span></span>' +
          '<span class="mt-st">' + end + '</span></div>' });
      });
      if (!lines.length) return;
      lines.sort(function(a, b) { return b.rate - a.rate; });
      var id = mtLabelId(m, leans);
      if (id && (TR.tips.matchup_labels || {})[id]) labels.push({ id: id, m: m });
      lines.slice(0, MT_MAX).forEach(function(x) { rates.push(x.rate); });
      groups += '<div class="mt-group"><div class="mt-ghead"><span class="t-label">' + esc(mktHead(k, m)) + '</span>' + mtChip(id, m, k) + '</div>' +
        lines.slice(0, MT_MAX).map(function(x) { return x.html; }).join('') + '</div>';
    });
    if (!groups) return null;
    function nm(slug) { return badge(slug, 22) + '<span class="nm-full">' + esc(shortName(slug)) + '</span><span class="nm-abbr">' + esc(tcode(slug)) + '</span>'; }
    return { labels: labels, rate: rates.reduce(function(a, b) { return a + b; }, 0) / rates.length, start: g.start || '',
      html: '<div class="st-card mt-game" id="mt-' + esc(g.id) + '"><div class="mt-head"><span class="tr-time">' + esc(past ? 'FINAL' : trTime(g.start)) + '</span>' +
        teamLink(g.away, nm(g.away)) + '<span class="mt-at">@</span>' + teamLink(g.home, nm(g.home)) + '</div>' + groups + '</div>' };
  }
  // Matchup Trends grouped by label: Fireworks · Lockdown · Mismatch ·
  // Heavyweights · Tug of war (a game with two goes in its first), then
  // "Other matchups"; each group strongest first (its lines' average rate),
  // then start time, MT_GAMES at a time. The filters apply first.
  var MT_ORDER = ['fireworks', 'lockdown', 'mismatch', 'heavyweights', 'tug_of_war'];
  function mtSection(o) {
    var st = trState('mt'), k = st.seg, groups = {};
    var games = o.games.filter(function(g) { return lined(g, k); });
    games.forEach(function(g) {
      var b = matchupBlock(g, k, o.before, o.past, st);
      if (!b) return;
      var first = MT_ORDER.filter(function(id) { return b.labels.some(function(l) { return l.id === id; }); })[0];
      var key = first || 'other';
      (groups[key] = groups[key] || { m: first ? b.labels.filter(function(l) { return l.id === first; })[0].m : null, list: [] }).list.push(b);
    });
    var body = MT_ORDER.concat(['other']).filter(function(id) { return groups[id]; }).map(function(id) {
      var x = groups[id], n = x.list.length;
      x.list.sort(function(a, b) { return (b.rate - a.rate) || (a.start < b.start ? -1 : a.start > b.start ? 1 : 0); });
      var count = '<span class="mt-gcount">&middot; ' + n + ' game' + (n === 1 ? '' : 's') + '</span>';
      var head = (id === 'other' ? '<span class="t-label">Other matchups</span>' : mtChip(id, x.m, k)) + count;
      return '<div class="mt-grp"><div class="mt-ghd">' + head + '</div><div class="mt-grid">' + x.list.map(function(b, i) {
        return i >= MT_GAMES ? b.html.replace('<div class="st-card mt-game"', '<div hidden class="st-card mt-game"') : b.html;
      }).join('') + '</div>' + (n > MT_GAMES ? '<button type="button" class="tr-more" data-mt-more>Show more games</button>' : '') + '</div>';
    }).join('');
    return '<section class="trends-page-section" id="matchup-trends"><div class="tph"><div><h2>Matchup Trends</h2></div></div>' + trFilters('mt') +
      (!games.length ? '<div class="no-games-note">No games ' + esc(o.none) + '.</div>'
        : body || '<div class="no-games-note">No matchup trends for these filters.</div>') + '</section>';
  }
  // the label chip with its own "i" next to it
  function labelChip(text, def) {
    return '<span class="lbl-chip"><span class="mt-label">' + esc(text) + '</span>' + infoTip(tipBody(text, def), false, text) + '</span>';
  }

  // Streak Trends: follows the segment and market pills. One group per
  // market (top STK_TOP, longest first, then "+N more teams on N+ streaks"),
  // only teams playing on the slate (football: the week); a group with none
  // says so. Rows: the heat chip (the run's length) · logo · code · streak,
  // then the opponent + time under the code, every device. All / Home / Away:
  // Home is each team's run in its home games, for teams at home on the
  // slate (Away the same on the road). "All active streaks" opens every
  // team's run in place. Runs: 3+ in every sport; college moneyline runs
  // count Division I (FBS) games only.
  var STK_TOP = 5;
  function stkMin() { return 3; }
  function stkCollege() { return D.sport === 'ncaab' || D.sport === 'ncaaf'; }
  var STK_ORDER = { nhl: ['ml', 'total', 'btts', 'ml3'], mlb: ['rfi', 'ml', 'ats', 'total'] };
  function stkMarkets(k, mkt) {
    var order = STK_ORDER[D.sport] || ['ats', 'ml', 'total'];
    var ms = TR.markets.filter(function(x) { return x[0] === k && (HIT[x[1]] || x[1] === 'ml3'); });
    if (mkt !== 'all') ms = ms.filter(function(x) { return x[1] === mkt; });
    return ms.sort(function(a, b) { return order.indexOf(a[1]) - order.indexOf(b[1]); });
  }
  function stkWord(m, kind, k) {
    var t = seg(k).tag;
    if (m === 'ml' || m === 'ml3') return kind === 'W' ? 'Won ' + t : kind === 'T' ? 'Tied ' + t : 'Lost ' + t;
    if (m === 'ats') return kind === 'W' ? 'Covered ' + t : 'No cover ' + t;
    if (m === 'total') return t + ' ' + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '');
    if (m === 'btts') return t + ' BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
    return kind === 'Y' ? 'YRFI' : 'NRFI';
  }
  // 3-way: the moneyline's results with ties as their own run
  function stkOf(m, seq) {
    if (m !== 'ml3') return streakOf(seq);
    var n = 0, last = seq[seq.length - 1];
    if (!last) return null;
    for (var i = seq.length - 1; i >= 0 && seq[i] === last; i--) n++;
    return { kind: last, n: n };
  }
  function streakSection(games, before, none, all) {
    var st = trState('stk'), k = st.seg;
    var seqs = teamSeqs(before, k), playing = {}, weekly = D.schedule === 'week';
    // a team's next game on the slate (football: the week)
    games.slice().sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : 1; }).forEach(function(g) {
      playing[g.away] = playing[g.away] || g; playing[g.home] = playing[g.home] || g;
    });
    var min = stkMin(), ven = st.side;
    var groups = stkMarkets(k, st.mkt).map(function(x) {
      var m = x[1], list = [];
      Object.keys(all ? seqs : playing).forEach(function(slug) {
        var key = m === 'ml3' ? 'ml' : m === 'ml' && stkCollege() ? 'mlD1' : m, g = playing[slug];
        // Home / Away: teams at that venue on the slate (every team's run there when "All active streaks" is open)
        if (ven !== 'all' && g && g[ven] !== slug) return;
        if (ven !== 'all' && !g && !all) return;
        var src = ven === 'all' ? seqs[slug] : ((seqs[slug] || {}).v || {})[ven];
        var seq = ((src || {})[key]) || [], st = stkOf(m, seq);
        if (!st || st.n < min) return;
        list.push({ slug: slug, m: m, s: st, g: g });
      });
      list.sort(function(a, b) { return b.s.n - a.s.n || (((a.g || {}).start || '') < ((b.g || {}).start || '') ? -1 : 1); });
      var more = all ? 0 : Math.max(0, list.length - STK_TOP);
      return { m: m, full: list, label: x[2].replace('Total', 'O/U'), list: all ? list : list.slice(0, STK_TOP), more: more };
    });
    // 3-way: shown only when its list differs from the moneyline's (same teams, same counts = hidden)
    function stkSig(x) { return x.full.map(function(e) { return e.slug + ':' + e.s.n; }).sort().join(','); }
    var stkMl = groups.filter(function(x) { return x.m === 'ml'; })[0];
    if (stkMl) groups = groups.filter(function(x) { return x.m !== 'ml3' || stkSig(x) !== stkSig(stkMl); });
    if (all) groups = groups.filter(function(x) { return x.list.length; });
    var where = ven === 'home' ? ' at home' : ven === 'away' ? ' on the road' : '';
    function row(x) {
      var g = x.g, opp = g ? (g.home === x.slug ? 'vs ' : '@ ') + tcode(g.home === x.slug ? g.away : g.home) : '';
      var when = g ? (g.state === 'final' ? 'FINAL' : weekly ? trTime(g.start) : rowStatus(g)) : '';
      return '<div class="stk-row"><span class="sk-len ' + heatCls(x.s.n) + '">' + x.s.n + '</span>' +
        '<span class="stk-l1">' + teamLink(x.slug, badge(x.slug, 20) + '<span>' + esc(tcode(x.slug)) + '</span>') +
        '<span class="stk-run">' + esc(stkWord(x.m, x.s.kind, k) + where) + '</span></span>' +
        '<span class="stk-l2">' + esc([opp, when].filter(Boolean).join(' · ')) + '</span></div>';
    }
    var when = weekly ? 'this week' : 'today';
    var body = !all && !Object.keys(playing).length ? '<div class="no-games-note">No games ' + esc(none) + '.</div>'
      : groups.length ? groups.map(function(x) {
        return '<div class="st-card stk-group"><div class="st-head"><h4>' + esc(x.label) + '</h4></div>' +
          (x.list.length ? x.list.map(row).join('') : '<p class="stk-none">No active streaks of ' + min + ' or more ' + when + '.</p>') +
          (x.more ? '<button type="button" class="tr-link stk-more" data-all-streaks>+' + x.more + ' more team' + (x.more === 1 ? '' : 's') + ' on ' + min + '+ streaks &rarr;</button>' : '') + '</div>';
      }).join('') : '<div class="no-games-note">No team is on a run of ' + min + ' or more.</div>';
    return '<section class="trends-page-section" id="streak-trends"><div class="tph"><div><h2>Streak Trends</h2>' +
      '<p class="tp-sub">' + esc(((TR.tips.streaks || {}).section || '').replace(/run of \d+ or more/, 'run of ' + stkMin() + ' or more')) + '</p></div></div>' + trFilters('stk') +
      '<div class="stk-grid' + (st.mkt !== 'all' ? ' stk-one' : '') + '">' + body + '</div>' +
      (all ? '' : '<button type="button" class="tr-link" data-all-streaks>All active streaks &rarr;</button>') + '</section>';
  }

  // League Trends: the slate's cards in the section's segment and market.
  // Home / Away: the trends about that side (the rows that bet the home /
  // the away team); trends not about a side (totals, BTTS, NRFI) show under
  // All only.
  function ltSection(o) {
    var st = trState('lt'), k = st.seg, slate = (TR.slates || {})[o.key] || { cards: [] };
    var cards = slate.cards.filter(function(c) { return c.seg === k && (st.mkt === 'all' || c.mk === st.mkt); });
    if (st.side !== 'all') cards = cards.map(function(c) {
      return Object.assign({}, c, { games: (c.games || []).filter(function(x) { return x.side === st.side; }) });
    }).filter(function(c) { return c.games.length; });
    if (st.mkt === 'all') cards = allCards(cards);
    var html = '<section class="trends-page-section" id="league-trends"><div class="tph"><div><h2>League Trends</h2></div></div>' + trFilters('lt');
    if (!o.games.length) html += '<div class="no-games-note">No ' + esc(D.label) + ' games ' + esc(o.none) + '.</div>';
    else if (!cards.length) html += noTrendsCard(o, k);
    else {
      // strongest first: 6 on desktop, 3 on phones, then "Show all N trends"
      // opens the rest in place. Past TR_OPEN they unlock with the Running
      // Tab (the signup box is at the bottom of the page: front.running_tab).
      html += '<div class="tr-cards">' + cards.slice(0, TR_OPEN).map(function(c, i) {
        return i >= TR_PHONE ? trendCard(c).replace('<div class="tr-card"', '<div class="tr-card tr-ph-more"') : trendCard(c);
      }).join('') + '</div>';
      if (cards.length > TR_OPEN) html += '<div class="tr-rest" hidden>' + lockedTrends(cards.slice(TR_OPEN)) + '</div>';
      if (cards.length > TR_PHONE) html += '<button type="button" class="tr-more tr-show-all' + (cards.length <= TR_OPEN ? ' tr-ph-only' : '') + '">Show all ' + cards.length + ' trends</button>';
    }
    return html + '</section>';
  }
  // One slate: a date, or (football) a week; each section has its own filters
  function trendsSlate(o) {
    return '<p class="tr-date">' + esc(o.title) + '</p>' + o.bar +
      '<div id="ltBox">' + ltSection(o) + '</div>' +
      '<div id="stkBox">' + streakSection(o.games, o.before, o.none) + '</div>' +
      '<div id="mtBox">' + mtSection(o) + '</div>';
  }
  var TR_OPEN = 6, TR_PHONE = 3, MT_GAMES = 5;
  // No card qualifies: early in the season it says when they start; last
  // season's strongest trends (trends.json lastSeason) open in place
  function noTrendsCard(o, k) {
    var most = 0, seqs = teamSeqs(o.before, k);
    Object.keys(seqs).forEach(function(t) { most = Math.max(most, seqs[t].ml.length); });
    var msg = most < 10 ? 'League trends start once teams have played 10 games.' : 'No trends meet our bar ' + o.none + '.' + (o.today ? ' Check back tomorrow.' : '');
    var prior = TR.lastSeason;
    return '<div class="st-card tr-none"><p>' + esc(msg) + '</p>' +
      (prior && prior.cards.length ? '<button type="button" class="tr-link" data-last-season>See last season&rsquo;s trends &rarr;</button>' : '') + '</div>' +
      '<div class="tr-cards" id="trLastSeason" hidden></div>';
  }
  function lastSeasonCard(c) {
    var u = c.units == null ? '' : ' · <span class="' + unitCls(c.units) + '">' + fmtUnits(c.units) + '</span>';
    return '<div class="tr-card"><div class="tr-top"><span class="lt-tag">' + esc(c.tag) + '</span><span class="lt-season">' + esc(TR.lastSeason.label) + ' season</span></div>' +
      '<h3 class="tr-title">' + esc(c.title) + '</h3><div class="tr-rec">' + pct0(c.rate) + ' (' + c.w + '-' + c.l + ')' + u + '</div>' +
      '<p class="ht-avg">League average ' + pct0(c.base) + '</p></div>';
  }
  function lockedTrends(rest) {
    var n = rest.length;
    return '<div class="ht-locked"><div class="ht-blur"' + (document.documentElement.classList.contains('rt-subbed') ? '' : ' aria-hidden="true"') + '><div class="tr-cards">' +
      rest.map(function(c) { return trendCard(c, false); }).join('') + '</div></div>' +
      '<div class="ht-overlay"><div class="ht-lock-card"><div class="ht-lock-title">' + n + ' more trend' + (n === 1 ? '' : 's') + '</div>' +
      '<p>Free with the Running Tab, our newsletter. Sign up once and they unlock on this device.</p>' +
      '<a class="btn-primary" href="#signup-tab">Get the Tab</a></div></div></div>';
  }
  function wireSlate(draw, o) {
    // a section's filter redraws that section only
    function filters(box, sec, redraw) {
      box.querySelectorAll('[data-trf]').forEach(function(b) {
        b.onclick = function() { trState(sec)[b.getAttribute('data-trf')] = b.getAttribute('data-v'); redraw(); };
      });
    }
    function ltWire() {
      var box = document.getElementById('ltBox');
      if (!box) return;
      filters(box, 'lt', function() { box.innerHTML = ltSection(o); ltWire(); });
      var all = box.querySelector('.tr-show-all');
      if (all) all.onclick = function() {
        var sec = document.getElementById('league-trends'), rest = sec.querySelector('.tr-rest');
        sec.classList.add('tr-open');
        if (rest) rest.hidden = false;
        all.remove();
      };
      var ls = box.querySelector('[data-last-season]');
      if (ls) ls.onclick = function() {
        var st = trState('lt'), lb = document.getElementById('trLastSeason');
        lb.innerHTML = TR.lastSeason.cards.filter(function(c) { return c.seg === st.seg && (st.mkt === 'all' || c.mk === st.mkt); }).map(lastSeasonCard).join('') ||
          '<div class="no-games-note">No ' + esc(TR.lastSeason.label) + ' trends for this market.</div>';
        lb.hidden = false;
        ls.remove();
      };
      box.querySelectorAll('.tr-all').forEach(function(b) {
        b.onclick = function() { b.parentNode.querySelectorAll('.tr-row[data-extra]').forEach(function(r) { r.hidden = false; }); b.remove(); };
      });
    }
    var stkAll = false;
    function stkWire() {
      var box = document.getElementById('stkBox');
      if (!box) return;
      box.querySelectorAll('[data-all-streaks]').forEach(function(as) {
        as.onclick = function() { stkAll = true; box.innerHTML = streakSection(o.games, o.before, o.none, true); stkWire(); box.scrollIntoView({ block: 'start' }); };
      });
      filters(box, 'stk', function() { box.innerHTML = streakSection(o.games, o.before, o.none, stkAll); stkWire(); });
    }
    function mtWire() {
      var box = document.getElementById('mtBox');
      if (!box) return;
      filters(box, 'mt', function() { box.innerHTML = mtSection(o); mtWire(); });
      // "Show more games": per group, MT_GAMES at a time
      box.querySelectorAll('[data-mt-more]').forEach(function(mm) {
        mm.onclick = function() {
          var rest = mm.parentNode.querySelectorAll('.mt-game[hidden]');
          [].slice.call(rest, 0, MT_GAMES).forEach(function(x) { x.hidden = false; });
          if (rest.length <= MT_GAMES) mm.remove();
        };
      });
    }
    ltWire();
    stkWire();
    mtWire();
  }
  function dayCounts() { var o = {}; allDates().forEach(function(d) { o[d] = D.games[d].length; }); return o; }
  function longDay(d) { return new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric', timeZone: 'UTC' }); }

  function renderTrends() {
    fetch(dataUrl(SPORT_SLUG + '/trends.json')).then(function(r) { return r.json(); }).then(function(tr) {
      TR = tr;
      if (D.schedule === 'week') renderTrendsByWeek(); else renderTrendsByDay();
      // the hub's "See the full matchup" link: #mt-<game id>; the hubs' "All streaks" link: #streak-trends
      var hit = /^#(mt-|streak-trends$)/.test(location.hash) && document.getElementById(location.hash.slice(1));
      if (hit) { hit.hidden = false; if (/^#mt-/.test(location.hash)) hit.classList.add('mt-hit'); hit.scrollIntoView({ block: 'start' }); }
    }).catch(function(e) {
      app.innerHTML = emptyNote('Couldn&rsquo;t load the trends. Try reloading.');
      if (window.console) console.error(e);
    });
  }
  function renderTrendsByDay() {
    var dates = allDates();
    if (!dates.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet - trends appear once games are played.'); return; }
    var cur = urlDate() || defaultDate(dates);
    function go(d) { cur = d; setUrlDate(d); draw(); }
    function draw() {
      var t = todayET(), today = cur === t;
      var o = {
        key: cur, games: D.games[cur] || [], before: cur, today: today, past: cur < t, title: longDay(cur), bar: dateBar(cur, dates, true),
        recLabel: today ? 'Today’s' : shortDay(cur), none: today ? 'today' : 'on ' + shortDay(cur),
      };
      app.innerHTML = trendsSlate(o);
      wireDateBar(dates, cur, go);
      document.getElementById('dateCal').onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: null, onPick: go }); };
      wireSlate(draw, o);
    }
    draw();
  }
  // Football: one slate per week, like its Matchups page
  function renderTrendsByWeek() {
    var weeks = D.weeks || [];
    if (!weeks.length) { app.innerHTML = emptyNote('No ' + esc(D.label) + ' games loaded yet - trends appear once games are played.'); return; }
    var keys = weeks.map(function(w) { return w.key; });
    var want = new URLSearchParams(location.search).get('week');
    var thisWeek = currentWeek(weeks);
    var cur = keys.indexOf(want) !== -1 ? want : thisWeek;
    function go(k) {
      cur = k;
      var u = new URL(location.href); u.searchParams.set('week', k); u.searchParams.delete('date');
      history.replaceState(null, '', u);
      draw();
    }
    function draw() {
      var i = keys.indexOf(cur), w = weeks[i], now = cur === thisWeek;
      var o = {
        key: cur, games: weekGames(cur), before: w.start, today: now, past: i < keys.indexOf(thisWeek), title: w.label + ' · ' + weekRange(w), bar: weekBar(weeks, cur, thisWeek),
        recLabel: now ? 'This Week’s' : w.label, none: now ? 'this week' : 'in ' + w.label
      };
      app.innerHTML = trendsSlate(o);
      var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), t = document.getElementById('weekNowBtn');
      if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
      if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
      if (t) t.onclick = function() { go(thisWeek); };
      document.getElementById('dateCal').onclick = function() { openCalendar({ days: dayCounts(), cur: cur, weeks: weeks, onPick: go }); };
      wireSlate(draw, o);
    }
    draw();
  }

  // ------------------------------------------------ Situational Results
  // The shared split table (assets/situational.js) with this sport's
  // registry (assets/splits/{sport}.js). "Since last season" loads
  // {slug}/history.json only when picked. Premium: the same lock as NHL's
  // premium sections (everyone is Premium for now; ?free=1 previews it).
  var IS_PREMIUM = !/[?&]free=1\b/.test(window.location.search);
  var LOCK_HTML = '<div class="adv-lock"><div class="adv-lock-card">' +
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>' +
    '<div class="adv-lock-title">Unlock Situational Results</div><div class="adv-lock-desc">Home / road, favorite / underdog, rest, schedule and previous-game splits for every market.</div>' +
    '<a class="adv-lock-btn" href="' + ROOT + '#premium">Go Premium</a></div></div>';
  var SIT = null;
  function splitReg() { return (window.RTYB_SPLITS || {})[D.sport] || null; }
  // Stats page: this season only (no season picker); rows that are real
  // edges and fit a game today link to the Trends page; a segment change in
  // any of its bars redraws the whole page (SIT_ON_SEG, set by renderStats).
  var SIT_ON_SEG = null;
  function sitEngine() {
    if (SIT || !splitReg() || !window.RTYBSit) return SIT;
    var seasons = [{ key: 'current', label: D.seasonLabel, games: D.games }];
    SIT = window.RTYBSit.create({ sport: D.sport, segments: D.segments, teams: D.teams, seasons: seasons, conf: D.conf, rivals: D.rivals,
      totalCuts: D.totalCuts, tz: D.tz || null, url: SECTION === 'splits', today: todayET(), comboLocked: function() { return premiumLocked('splitCombine'); },
      onSeg: function(k, anchor) { if (SIT_ON_SEG) SIT_ON_SEG(k, anchor); else return false; },
      ties: periodFamily(), tonightLocked: function() { return premiumLocked('tonightOnly'); },
      locked: function() { return !IS_PREMIUM; }, lockHtml: function() { return LOCK_HTML; } });
    return SIT;
  }
  // the league tables (Stats Splits, the Number): not for a team-pages-only registry (MLB)
  function leagueSit() { var e = sitEngine(); return e && !e.reg.teamOnly ? e : null; }
  // view = {mode: 'league'} or {mode: 'team', slug}
  function renderSit(boxId, view) {
    var e = sitEngine();
    if (e) e.render(document.getElementById(boxId), view);
  }
  // the split definitions, as a glossary in the page's How to read box
  // the Live definitions (assets/definitions.json, from the admin's Definitions tab)
  var DEFS_P = null;
  function defs() { return DEFS_P || (DEFS_P = fetch(dataUrl('assets/definitions.json')).then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; })); }
  function sitGlossary(k) {
    defs().then(function(d) { sitGlossaryNow(k, d); });
  }
  function sitGlossaryNow(k, d) {
    var e = sitEngine(), box = document.querySelector('.how-to-read');
    if (!e || !box || !e.glossary) return;
    var old = box.querySelector('.htr-gloss');
    if (old) old.remove();
    var seo = box.querySelector('.htr-seo');
    var div = document.createElement('div');
    div.innerHTML = e.glossary(k, d);
    box.insertBefore(div.firstChild, seo || null);
  }
  // ------------------------------------------------------- calendar modal
  // A month calendar in a modal (a full-width sheet from the bottom on
  // phones), shared by the Odds and Trends pages. Days with games get a dot.
  // opts: {days: {date: n games}, cur: date, weeks: [{key, label, start, end}]
  // or null (weekly sports pick a week: a day picks the week it falls in, or
  // the next one), onPick(date or week key)}.
  function weekFor(weeks, d) {
    for (var i = 0; i < weeks.length; i++) if (d <= weeks[i].end) return weeks[i];
    return null;
  }
  function openCalendar(opts) {
    var weeks = opts.weeks || null, days = opts.days || {};
    var curWeek = weeks ? weeks.filter(function(w) { return w.key === opts.cur; })[0] : null;
    var focus = (curWeek ? curWeek.start : opts.cur || todayET()).slice(0, 7);
    var keys = Object.keys(days).sort();
    var first = (keys[0] || focus).slice(0, 7), last = (keys[keys.length - 1] || focus).slice(0, 7);
    var wrap = document.createElement('div');
    wrap.className = 'cal-modal';
    wrap.setAttribute('role', 'dialog');
    wrap.setAttribute('aria-modal', 'true');
    wrap.setAttribute('aria-label', weeks ? 'Pick a week' : 'Pick a date');
    var opener = document.activeElement;
    function close() { document.removeEventListener('keydown', onKey); wrap.remove(); if (opener && opener.focus) opener.focus(); }
    function onKey(e) { if (e.key === 'Escape') close(); }
    function monthAdd(ym, n) { var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + n; y += Math.floor(m / 12); m = ((m % 12) + 12) % 12; return y + '-' + (m < 9 ? '0' : '') + (m + 1); }
    function draw() {
      var y = +focus.slice(0, 4), mo = +focus.slice(5, 7);
      var lead = new Date(Date.UTC(y, mo - 1, 1)).getUTCDay(), n = new Date(Date.UTC(y, mo, 0)).getUTCDate();
      var title = new Date(Date.UTC(y, mo - 1, 15)).toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
      var cells = '';
      for (var i = 0; i < lead; i++) cells += '<span class="cal-pad"></span>';
      for (var dd = 1; dd <= n; dd++) {
        var d = focus + '-' + (dd < 10 ? '0' : '') + dd, w = weeks ? weekFor(weeks, d) : null;
        var on = weeks ? (curWeek && w && w.key === curWeek.key && d >= w.start && d <= w.end) : d === opts.cur;
        var cls = 'cal-day' + (days[d] ? ' has' : '') + (on ? ' on' : '') + (d === todayET() ? ' today' : '');
        cells += '<button type="button" class="' + cls + '" data-d="' + d + '"' + (w ? ' data-w="' + esc(w.key) + '"' : '') +
          (weeks && !w ? ' disabled' : '') + ' aria-label="' + esc(dateLabel(d)) + (days[d] ? ', ' + days[d] + ' game' + (days[d] === 1 ? '' : 's') : '') + '">' + dd + '</button>';
      }
      wrap.innerHTML = '<div class="cal-back" data-close></div><div class="cal-sheet">' +
        '<div class="cal-head"><button type="button" class="date-nav" data-mon="-1" aria-label="Previous month"' + (focus <= first ? ' disabled' : '') + '>&lsaquo;</button>' +
        '<b>' + esc(title) + '</b><button type="button" class="date-nav" data-mon="1" aria-label="Next month"' + (focus >= last ? ' disabled' : '') + '>&rsaquo;</button>' +
        '<button type="button" class="cal-x" data-close aria-label="Close">&times;</button></div>' +
        '<div class="cal-grid">' + ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(function(x) { return '<span class="cal-dow">' + x + '</span>'; }).join('') + cells + '</div>' +
        '<p class="cal-key"><i></i>' + (weeks ? 'Game days. Pick any day to jump to its week.' : 'Days with games') + '</p></div>';
      var on = wrap.querySelector('.cal-day.on') || wrap.querySelector('.cal-day.has') || wrap.querySelector('.cal-day');
      if (on) on.focus();
    }
    wrap.addEventListener('click', function(e) {
      if (e.target.closest('[data-close]')) { close(); return; }
      var m = e.target.closest('[data-mon]');
      if (m && !m.disabled) { focus = monthAdd(focus, +m.getAttribute('data-mon')); draw(); return; }
      var b = e.target.closest('.cal-day');
      if (b && !b.disabled) { close(); opts.onPick(weeks ? b.getAttribute('data-w') : b.getAttribute('data-d')); }
    });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(wrap);
    draw();
  }
  var CAL_BTN = '<button type="button" class="date-cal" id="dateCal" aria-label="Open calendar">' +
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg></button>';
  // The week bar (NFL / NCAAF): ‹ Week 11 › with the dates under it
  function weekBar(weeks, cur, thisWeek) {
    var i = weeks.map(function(w) { return w.key; }).indexOf(cur), w = weeks[i];
    return '<div class="date-bar">' +
      '<button class="date-nav" id="weekPrev" aria-label="Previous week"' + (i <= 0 ? ' disabled' : '') + '>&lsaquo;</button>' +
      '<div class="date-label-wrap"><span class="date-label">' + esc(w.label) + ' <span class="week-range">' + esc(weekRange(w)) + '</span></span>' +
      (cur !== thisWeek ? '<button class="date-today-btn" id="weekNowBtn" type="button">This week</button>' : '') + CAL_BTN + '</div>' +
      '<button class="date-nav" id="weekNext" aria-label="Next week"' + (i >= weeks.length - 1 ? ' disabled' : '') + '>&rsaquo;</button></div>';
  }

  // ------------------------------------------------------------ Odds page
  // Every source's price for every game on the selected date (or week), from
  // {slug}/odds.json (the index) and {slug}/odds/{date}.json (one file per
  // date; sport_build.write_odds_page). One table: Team and Open pinned on
  // the left, then a column per source (major sportsbooks, other sportsbooks,
  // then exchanges and prediction markets). Games that haven't started link
  // each price to its source (Gambly links with the partner code); started
  // and finished games show each source's closing line; Open is always the
  // opening line (a game with only The Odds API's closing lines: Close, the
  // closing line it's graded with). The best price per side gets a green outline (the key at
  // the bottom says so). The controls and the header row stay pinned.
  // ?mkt= opens a market (The Big Numbers' rows link to theirs, #og-away-home: the game)
  var MKT_CUR = new URLSearchParams(location.search).get('mkt');
  var OG_HASH = /^#og-/.test(location.hash) ? location.hash.slice(1) : null;
  // the market pills: totals read "O/U" (NHL "O/U 1.5", MLB "F5 O/U")
  function pillLabel(x) { return x[1] === 'total' ? x[2].replace('Total', 'O/U') : x[2]; }
  // "· FINAL" or "· LIVE · 3RD 11:14" after a game's start time (Odds and Matchups)
  function oddsStatus(g) {
    if (g.state === 'final') return ' &middot; FINAL';
    // a game whose status never came back (off-season, postponed) isn't live
    var stale = g.start && Date.now() - Date.parse(g.start) > 8 * 3600e3;
    if ((g.state === 'live' || g.state === 'in') && !stale) return ' &middot; ' + liveHtml(g);
    return '';
  }
  // one side's result on a finished game (the Odds page's past dates): W / L
  // / P, from the game's res (away side: su, ats; tot O/U; btts and rfi Y/N)
  function oddsSideRes(g, k, m, s) {
    var r = (g.res || {})[k];   // graded once the segment ends, live or final
    if (!r || !r.sc) return null;
    if (r.na) return 'P';
    function yn(x, yes, flip) { var v = !x || x === 'NA' || x === 'P' ? 'P' : x === yes ? 'W' : 'L'; return flip ? flipRes(v) : v; }
    if (m === 'ml' || m === 'ats') {
      var x = r[m === 'ml' ? 'su' : 'ats'];
      if (!x || x === 'NA') return 'P';
      x = s === 'home' ? flipRes(x) : x;
      return x === 'W' || x === 'L' ? x : 'P';
    }
    if (m === 'ml3') return !r.su || r.su === 'NA' ? 'P' : r.su === { away: 'W', home: 'L', draw: 'T' }[s] ? 'W' : 'L';
    if (m === 'total') return yn(r.tot, 'O', s === 'under');
    if (m === 'btts') return yn(r.btts, 'Y', s === 'no');
    if (m === 'rfi') return yn(r.rfi, 'Y', s === 'nrfi');
    return null;
  }
  // One cell style for Odds and Matchups: the line on top (large, bold), the
  // price under it (small, muted); a moneyline cell shows the price in the
  // line style.
  // one cell (template.html .cell): the line on top, the price under it
  function oddsCell(line, price) {
    if (line == null) return price == null ? '' : '<span class="cell"><span class="ob-ln">' + esc(signed(price)) + '</span></span>';
    return '<span class="cell"><span class="ob-ln">' + esc(line) + '</span>' + (price != null ? '<span class="ob-pr">' + esc(signed(price)) + '</span>' : '') + '</span>';
  }
  // the name behind a logo or cell (data-tip): hover shows the title; a long
  // press (logos) or a tap (cells without a link) shows it on phones
  function wireTips(root) {
    if (root.__tips) return;
    root.__tips = true;
    var tip = null, timer = null;
    function hide() { if (tip) { tip.remove(); tip = null; } }
    function show(el) {
      hide();
      tip = document.createElement('div');
      tip.className = 'rt-tip';
      tip.textContent = el.getAttribute('data-tip');
      document.body.appendChild(tip);
      var r = el.getBoundingClientRect();
      tip.style.left = Math.max(8, Math.min(window.innerWidth - tip.offsetWidth - 8, r.left + r.width / 2 - tip.offsetWidth / 2)) + 'px';
      tip.style.top = (window.scrollY + r.top - tip.offsetHeight - 6) + 'px';
      setTimeout(hide, 1800);
    }
    root.addEventListener('touchstart', function(e) {
      var el = e.target.closest('[data-tip]');
      clearTimeout(timer);
      if (el) timer = setTimeout(function() { show(el); }, 450);
    }, { passive: true });
    root.addEventListener('touchend', function() { clearTimeout(timer); }, { passive: true });
    root.addEventListener('touchmove', function() { clearTimeout(timer); }, { passive: true });
    root.addEventListener('click', function(e) {
      var el = e.target.closest('[data-tip]');
      if (el && el.hasAttribute('data-tap') && !e.target.closest('a')) show(el);
    });
    root.addEventListener('contextmenu', function(e) { if (e.target.closest('img[data-tip]')) e.preventDefault(); });
    window.addEventListener('scroll', hide, { passive: true });
  }
  var MKT_WORD = { ml: 'moneyline', ml3: '3-way moneyline', ats: 'spread', total: 'total', btts: 'BTTS', rfi: 'NRFI / YRFI' };
  var YN_SIDES = { total: ['over', 'under'], btts: ['yes', 'no'], rfi: ['yrfi', 'nrfi'] };
  // one: {box, day, away, home} draws one game's table into box (the head to
  // head page): no date bar, the segment and market tabs only
  function renderOdds(one) {
    var box = one ? one.box : app;
    fetch(dataUrl(SPORT_SLUG + '/odds.json')).then(function(r) { return r.ok ? r.json() : null; }).then(function(O) {
      // NHL's data.json has its own shape: its odds.json carries what this page needs
      if (O && O.segments && !(D && D.segments)) D = { sport: O.sport, label: O.label, sportType: O.sportType, segments: O.segments, teams: O.teams || {}, otherTeams: {} };
      if (!D) return;
      var dates = O ? Object.keys(O.days || {}).sort() : [];
      if (!dates.length) { box.innerHTML = emptyNote('No ' + esc(D.label) + ' games on the schedule yet.'); return; }
      var weeks = !one && O.calendar === 'weekly' && (O.weeks || []).length ? O.weeks : null;
      var sources = O.sources || {}, order = O.order || [];
      var cache = {};
      function load(ds) {
        return Promise.all(ds.map(function(d) {
          if (cache[d]) return cache[d];
          cache[d] = fetch(dataUrl(SPORT_SLUG + '/odds/' + d + '.json')).then(function(r) { return r.ok ? r.json() : { games: [] }; });
          return cache[d];
        }));
      }
      // the selected date, or week
      var cur, thisWeek = null;
      if (weeks) {
        var t = todayET(), keys = weeks.map(function(w) { return w.key; });
        thisWeek = (weekFor(weeks, t) || weeks[weeks.length - 1]).key;
        var wantW = new URLSearchParams(location.search).get('week');
        cur = keys.indexOf(wantW) !== -1 ? wantW : thisWeek;
      } else {
        var want = one ? one.day : urlDate();
        cur = want || defaultDate(dates);
      }
      function slate() {
        if (!weeks) return O.days[cur] ? [cur] : [];
        var w = weeks.filter(function(x) { return x.key === cur; })[0];
        return dates.filter(function(d) { return d >= w.start && d <= w.end; });
      }
      function go(x) {
        cur = x;
        if (weeks) { var u = new URL(location.href); u.searchParams.set('week', x); u.searchParams.delete('date'); history.replaceState(null, '', u); }
        else setUrlDate(x);
        show();
      }
      function markets(k) { return (O.markets || []).filter(function(x) { return x[0] === k; }); }
      function code(x) { return team(x).code || shortName(x); }
      // the rows for one market: [side key, label (null = the team on that row)]
      function sides(m, kind) {
        if (kind === 'ml3') return [['away', null], ['draw', 'Tie'], ['home', null]];
        if (kind === 'yn') return [[(YN_SIDES[m] || ['over', 'under'])[0], null, 'away'], [(YN_SIDES[m] || ['over', 'under'])[1], null, 'home']];
        return [['away', null], ['home', null]];
      }
      // {line, price, link} for one source and side
      function val(row, m, s) {
        if (!row || !row[s]) return null;
        if (m === 'total') return { line: row.line, price: row[s].price, link: row[s].link };
        return { line: row[s].line != null ? signed(row[s].line) : null, price: row[s].price, link: row[s].link };
      }
      // the best (or Open) price for a side, from g.best / g.open
      function top(src, m, s) {
        if (!src) return null;
        if (m === 'total') return src[s] != null ? { line: src.line, price: src[s] } : null;
        if (m === 'ats') return src[s] ? { line: signed(src[s].line), price: src[s].price } : null;
        return src[s] != null ? { line: null, price: src[s] } : null;
      }
      function same(a, b) { return !!a && !!b && a.price === b.price && String(a.line) === String(b.line); }
      // nb: the Books tab took it out of the best price, so it's never outlined
      function counts(b, m) { var s = sources[b] || {}; return !s.nb && (m === 'ml3' || m === 'btts' || !s.x); }
      function cellTxt(v) { return oddsCell(v.line, v.price); }
      function name(b) { return (sources[b] || {}).name || 'Source ' + b; }
      // a book's logo (its name on hover, or on a long press on phones)
      function head(b) {
        var s = sources[b] || {};
        return s.logo ? '<img class="ob-logo" src="' + ROOT + s.logo + '" alt="' + esc(name(b)) + '" title="' + esc(name(b)) + '" data-tip="' + esc(name(b)) + '" loading="lazy">' : '<span class="ob-bname" title="' + esc(name(b)) + '" data-tip="' + esc(name(b)) + '">' + esc(name(b)) + '</span>';
      }
      // the team (and, once the game starts, its score in the segment)
      function teamCell(g, sd, k) {
        if (sd[1]) return '<span class="ob-team"><span class="ob-tie">' + esc(sd[1]) + '</span></span>';
        var side = sd[2] || sd[0], slug = g[side], sc = g.state !== 'pre' && g.score && g.score[k];
        return '<span class="ob-team">' + teamLink(slug, badge(slug, 20) + '<span class="tn-full">' + esc(shortName(slug)) + '</span><span class="tn-short">' + esc(code(slug)) + '</span>') +
          (sc ? '<span class="ob-sc mono">' + esc(sc[side === 'away' ? 0 : 1]) + '</span>' : '') + '</span>';
      }
      // Team, Open and one column per source
      function colgroup(cols) { return '<colgroup><col class="ob-w-team"><col class="ob-w-open">' + cols.map(function() { return '<col class="ob-w-src">'; }).join('') + '</colgroup>'; }
      function columns(games, k, m) {
        var ids = {};
        games.forEach(function(g) { Object.keys((((g.books || {})[k] || {})[m]) || {}).forEach(function(b) { ids[b] = 1; }); });
        return order.filter(function(b) { return ids[b]; });
      }
      function table(games, k, m, kind, cols, lined) {
        var body = games.map(function(g) {
          var books = ((g.books || {})[k] || {})[m] || {};
          // a game with only closing lines (The Odds API backfill): the column shows the close
          var best = ((g.best || {})[k] || {})[m], open = g.close ? best : ((g.open || {})[k] || {})[m];
          var past = g.state !== 'pre';
          var rows = sides(m, kind).map(function(sd) {
            var s = sd[0], b = top(best, m, s), o = top(open, m, s);
            // a finished game: the side that won green, the loser dimmed, a tie or push yellow
            var rc = resultCls(oddsSideRes(g, k, m, s));
            return '<tr><th scope="row" class="ob-c-team">' + teamCell(g, sd, k) + '</th>' +
              '<td class="ob-c-open' + (o ? rc : '') + '">' + (o ? cellTxt(o) : '') + '</td>' +
              cols.map(function(id) {
                var v = val(books[id], m, s);
                if (!v) return '<td class="ob-na"></td>';
                var cls = 'ob-cell' + rc + (counts(id, m) && same(v, b) ? ' ob-best' : '');
                return '<td class="' + cls + '">' + (v.link && !past ? '<a href="' + esc(v.link) + '" target="_blank" rel="sponsored noopener" title="' + esc(name(id)) + '">' + cellTxt(v) + '</a>' : cellTxt(v)) + '</td>';
              }).join('') + '</tr>';
          }).join('');
          // timeET already names the day in week view
          var day = weeks && g.start && !(D && D.schedule === 'week') ? new Date(g.start).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'America/New_York' }) + ' ' : '';
          // every game's time row carries Open and the book logos, over their columns
          var pair = one ? null : h2hUrl(g.away, g.home);
          return '<tbody class="ob-game" id="og-' + esc(g.away) + '-' + esc(g.home) + '"><tr class="ob-ghead"><th scope="col" class="ob-c-team"><span class="ob-time">' + esc(day) + (g.start ? esc(timeET(g.start)) : 'TBD') + oddsStatus(g) + '</span>' +
            (pair ? '<a class="ob-h2h" href="' + pair + '">Matchup &rarr;</a>' : '') + '</th>' +
            '<th scope="col" class="ob-c-open">' + (g.close ? 'Close' : 'Open') + '</th>' + cols.map(function(b) { return '<th scope="col" class="ob-src">' + head(b) + '</th>'; }).join('') + '</tr>' + rows + '</tbody>';
        }).join('');
        return '<div class="ob-scroll" id="obBody"><table class="ob-grid" style="--n:' + cols.length + '">' + colgroup(cols) + body + '</table></div>';
      }
      function draw(docs) {
        var k = getSeg(), ms = markets(k);
        var games = [];
        docs.forEach(function(doc) { (doc.games || []).forEach(function(g) { games.push(g); }); });
        // a game with no line in any of the segment's markets doesn't show
        games = games.filter(function(g) { var s = (g.books || {})[k] || {}; return Object.keys(s).some(function(m) { return s[m] && Object.keys(s[m]).length; }); });
        if (one) games = games.filter(function(g) { return g.away === one.away && g.home === one.home; });
        // football weeks: finished games drop to the bottom, in start order
        if (weeks) games = games.filter(function(g) { return g.state !== 'final'; }).concat(games.filter(function(g) { return g.state === 'final'; }));
        if (!ms.some(function(x) { return x[1] === MKT_CUR; })) {
          // start on the first market with lines on this slate
          var withLines = ms.filter(function(x) { return games.some(function(g) { var b = ((g.books || {})[k] || {})[x[1]]; return b && Object.keys(b).length; }); });
          MKT_CUR = ((withLines[0] || ms[0]) || [])[1] || null;
        }
        var mk = ms.filter(function(x) { return x[1] === MKT_CUR; })[0];
        var m = mk ? mk[1] : null;
        var lined = mk && games.some(function(g) { var b = ((g.books || {})[k] || {})[m]; return b && Object.keys(b).length; });
        var cols = games.length ? columns(games, k, m) : [];
        var html = one ? '' : weeks ? weekBar(weeks, cur, thisWeek) : dateBar(cur, dates, true);
        html += '<div class="ob-stick" id="obStick"><div class="sport-seg-row odds-controls">' + (D.segments.length > 1 ? segToggle('pageSeg', k) : '') +
          '<div class="seg-toggle" id="oddsMkt">' + ms.map(function(x) {
            return '<button class="seg-btn" data-mkt="' + x[1] + '" aria-pressed="' + (x[1] === MKT_CUR) + '">' + esc(pillLabel(x)) + '</button>';
          }).join('') + '</div></div></div>';
        var first = slate()[0];
        if (!games.length && one) html += '<p class="tp-none">No ' + esc(seg(k).label) + ' lines for this game.</p>';
        else if (!games.length) {
          var days = dates.filter(function(d) { return O.days[d]; }), sched = slate().some(function(d) { return O.days[d]; });
          if (weeks) {
            WEEK_ORDER = weeks.map(function(w) { return w.key; });
            var cw = weeks.filter(function(w) { return w.key === cur; })[0];
            html += noGamesCard(cur, weeks.filter(function(w) { return days.some(function(d) { return d >= w.start && d <= w.end; }); }).map(function(w) { return w.key; }),
              function(x) { return weeks.filter(function(w) { return w.key === x; })[0].label; }, true, sched, !!cw && cw.end < todayET());
          } else html += noGamesCard(cur, days, dayName, false, sched, cur < todayET());
        }
        else {
          if (!lined) html += '<div class="no-games-note">' + (first && first < todayET() ? 'Lines not available.' : 'No ' + esc(seg(k).label) + ' ' + (mk ? MKT_WORD[m] || esc(mk[2]) : 'lines') + ' posted yet.') + '</div>';
          html += table(games, k, m, mk ? mk[3] : 'side', cols, lined);
        }
        if (m === 'btts') html += '<p class="odds-note">Both teams to score in the 1st period. BTTS isn&rsquo;t on our odds feed, so our team enters ' + (cols[0] && cols[0] !== 'consensus' ? esc(name(cols[0])) + '&rsquo;s price' : 'a consensus price across the books') + '.</p>';
        box.innerHTML = html;
        if (one) {
          wireTips(box);
          var ops = box.querySelector('#pageSeg');
          if (ops) ops.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); show(); } };
          box.querySelector('#oddsMkt').onclick = function(e) { var b = e.target.closest('[data-mkt]'); if (b) { MKT_CUR = b.getAttribute('data-mkt'); show(); } };
          return;
        }
        wireNoGames(go);
        stickBelowNav(document.getElementById('obStick'));
        wireTips(app);
        var hit = OG_HASH && document.getElementById(OG_HASH);
        // (instant: the page can redraw while a smooth scroll runs; the next second's redraws land there too)
        if (hit) { hit.scrollIntoView({ block: 'center', behavior: 'instant' }); setTimeout(function() { OG_HASH = null; }, 1500); }
        if (weeks) {
          var keys = weeks.map(function(w) { return w.key; }), i = keys.indexOf(cur);
          var p = document.getElementById('weekPrev'), n = document.getElementById('weekNext'), now = document.getElementById('weekNowBtn');
          if (p) p.onclick = function() { if (i > 0) go(keys[i - 1]); };
          if (n) n.onclick = function() { if (i < keys.length - 1) go(keys[i + 1]); };
          if (now) now.onclick = function() { go(thisWeek); };
        } else wireDateBar(dates, cur, go);
        document.getElementById('dateCal').onclick = function() { openCalendar({ days: O.days, cur: cur, weeks: weeks, onPick: go }); };
        var ps = document.getElementById('pageSeg');
        if (ps) ps.onclick = function(e) { var b = e.target.closest('[data-seg]'); if (b) { setSeg(b.getAttribute('data-seg')); show(); } };
        document.getElementById('oddsMkt').onclick = function(e) { var b = e.target.closest('[data-mkt]'); if (b) { MKT_CUR = b.getAttribute('data-mkt'); show(); } };
      }
      function show() { load(slate()).then(draw); }
      show();
    }).catch(function(e) {
      box.innerHTML = emptyNote('Couldn&rsquo;t load the odds. Try reloading.');
      if (window.console) console.error(e);
    });
  }

  // ------------------------------------------------- head to head page
  // /{sport}/matchups/{a}-vs-{b}/ (scripts/h2h.py writes the page, its
  // breadcrumb and H1, and last season's meetings as #h2hPrev). Top to
  // bottom: the header (the next meeting, else the last), best lines now
  // (after the game: the closing lines and the result), the angle, side by
  // side in tonight's roles, head to head, streaks and Last 5, scoring,
  // situational spots, the Odds page's table for the game, the Preview link.
  // Phones: a tab row under the header (Overview · Odds · H2H · Trends).
  function h2hUrl(a, b) {
    var ta = D.teams[a], tb = D.teams[b];
    if (!ta || !tb || !ta.mu || !tb.mu || a === b) return null;
    var x = [ta.mu, tb.mu].sort();
    return ROOT + SPORT_SLUG + '/matchups/' + x[0] + '-vs-' + x[1] + '/';
  }
  var H2 = { k: null, prev: [], label: '', og: null, sources: {}, data: null };
  function h2K() { return H2.k && seg(H2.k) ? H2.k : D.segments[0].key; }
  // the segment's side market: the spread (NHL the ML, MLB's 1st inning NRFI)
  function h2Main(k) {
    var ms = tmMarkets(k).map(function(p) { return p.m; });
    return ms.indexOf('ats') !== -1 ? 'ats' : ms.indexOf('ml') !== -1 ? 'ml' : ms[0];
  }
  function h2Finals(slug) { return teamGames(slug).filter(function(g) { return g.state === 'final'; }); }
  function h2Day(g) { return gameDay(g) || (g.start ? new Date(g.start).toLocaleDateString('en-CA', { timeZone: 'America/New_York' }) : ''); }
  // "Sat, Mar 21, 2026": the head to head log always has the year; the
  // header only for last season's game
  function h2LongDate(g, year) {
    if (!g.start) return '';
    var o = { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' };
    if (year || !findGame(g.id)) o.year = 'numeric';
    return new Date(g.start).toLocaleDateString('en-US', o);
  }
  function h2Rec(a, m) { return !a.gp ? '-' : a.w + '-' + a.l + (a.t ? '-' + a.t : ''); }
  function h2Cell(ln, pr, cls) {
    return '<span class="cell tp-rc' + (cls ? ' tp-rc-' + cls : '') + '"><span class="ob-ln">' + esc(ln) + '</span>' + (pr != null ? '<span class="ob-pr">' + esc(pr) + '</span>' : '') + '</span>';
  }
  var H2_DASH = '<span class="cell tp-rc"><span class="mc-dash">-</span></span>';
  // full-game W-L (OT and shootouts included, as books grade it)
  function h2Record(slug) {
    var w = 0, l = 0, t = 0;
    h2Finals(slug).forEach(function(g) {
      if (g.as == null || g.hs == null) return;
      var mine = g.home === slug ? g.hs : g.as, th = g.home === slug ? g.as : g.hs;
      if (mine > th) w++; else if (mine < th) l++; else t++;
    });
    return w + '-' + l + (t ? '-' + t : '');
  }
  // "Back-to-back · Game 3 of a road trip"
  function h2Rest(G, slug) {
    if (!findGame(G.id)) return '';
    var list = teamGames(slug), i = list.map(function(g) { return g.id; }).indexOf(G.id), out = [];
    if (i < 1) return '';
    var n = Math.round((Date.parse(h2Day(G) + 'T12:00:00Z') - Date.parse(h2Day(list[i - 1]) + 'T12:00:00Z')) / 864e5);
    out.push(n === 0 ? 'Doubleheader' : n === 1 ? 'Back-to-back' : (n - 1) + (n === 2 ? ' day off' : ' days off'));
    if (!G.neutral) {
      var home = G.home === slug, run = 1;
      for (var j = i - 1; j >= 0 && !list[j].neutral && (list[j].home === slug) === home; j--) run++;
      out.push(run > 1 ? 'Game ' + run + ' of a ' + (home ? 'home stand' : 'road trip') : home ? 'Back home' : 'Starts a road trip');
    }
    return out.join(' &middot; ');
  }
  function h2Header(G, which) {
    var fin = G.state === 'final' && G.as != null && G.hs != null;
    var when = which === 'next' ? (h2Day(G) === todayET() ? 'Today' : h2LongDate(G)) + (G.start ? ' ' + timeET(G.start).replace(/^.* · /, '') : '') : h2LongDate(G) + ' &middot; Final' + (G.ot ? ' ' + esc(G.ot) : '');
    var col = function(slug, i) {
      var recs = D.segments.filter(function(s) { return tmMarkets(s.key).length; }).map(function(s) {
        var m = h2Main(s.key);
        return esc(tpName({ k: s.key, m: m })) + ' ' + h2Rec(tmAgg(slug, s.key, m, 'all', h2Finals(slug)), m);
      });
      if (D.sportType === 'baseball') recs = recs.slice(-1);   // F5 run line
      var rest = which === 'next' ? h2Rest(G, slug) : '';
      return '<div class="h2h-team">' + badge(slug, 48) + '<div class="h2h-tw"><span class="h2h-tn">' + teamLink(slug, nameHtml(slug)) +
        (fin ? ' <span class="tp-lg-pts">' + (i ? G.hs : G.as) + '</span>' : '') + '</span>' +
        '<span class="h2h-rec">' + h2Record(slug) + ' &middot; ' + recs.join(' &middot; ') + '</span>' +
        (rest ? '<span class="h2h-rest">' + rest + '</span>' : '') + '</div></div>';
    };
    var where = [G.ven, (G.tv || []).join(', ')].filter(Boolean).map(esc).join(' &middot; ');
    return '<div class="st-card h2h-head"><div class="st-head"><h4>' + (which === 'next' ? (G.state === 'in' ? 'Live' : 'Next meeting') : 'Last meeting') + ' &middot; ' + when + '</h4></div>' +
      '<div class="h2h-teams">' + col(G.away, 0) + '<span class="tp-at">@</span>' + col(G.home, 1) + '</div>' +
      (where ? '<p class="tp-where">' + where + '</p>' : '') + startersLine(G, true) + '</div>' +
      '<nav class="h2h-tabs" aria-label="Sections"><a href="#h2Over">Overview</a><a href="#h2Odds">Odds</a><a href="#h2Meet">H2H</a><a href="#h2Trends">Trends</a></nav>';
  }
  // the best price per segment, market and side, its book and the open
  function h2BestBlocks(G) {
    var og = H2.og, sources = H2.sources;
    if (!og) return '<p class="tp-none">Lines not posted yet.</p>';
    function book(k, mk, s, v, m) {
      var rows = (((og.books || {})[k] || {})[mk]) || {}, id = null;
      ['book', 'exch', 'consensus'].forEach(function(pass) {
        Object.keys(rows).forEach(function(b) {
          if (id || (sources[b] || {}).nb || (b === 'consensus') !== (pass === 'consensus')) return;
          if (pass !== 'consensus' && !!(sources[b] || {}).x !== (pass === 'exch')) return;
          var r = rows[b], x = r && r[s], xp = x && typeof x === 'object' ? x.price : x;
          if (xp !== v.price) return;
          if (m === 'ats' && x.line !== v.line) return;
          if (m === 'total' && r.line !== v.line) return;
          id = b;
        });
      });
      var src = id ? sources[id] || {} : null;
      if (!src) return '';
      return src.logo ? '<img class="sl-book" src="' + ROOT + esc(src.logo) + '" alt="' + esc(src.name || id) + '" title="' + esc(src.name || id) + '" loading="lazy">' : '<span class="sl-bname">' + esc(src.name || id) + '</span>';
    }
    function val(o, m, s) {
      if (!o) return null;
      if (m === 'ats') return o[s] && typeof o[s].line === 'number' ? { line: o[s].line, price: o[s].price, ln: signedLine(o[s].line) } : null;
      if (m === 'total') return o[s] != null ? { line: o.line, price: o[s], ln: (s === 'over' ? 'o' : 'u') + num1(o.line) } : null;
      return o[s] != null ? { line: null, price: o[s], ln: priceTxt(o[s]) } : null;
    }
    function sideLabel(m, s) {
      if (s === 'away' || s === 'home') return tcode(G[s]);
      return { draw: 'Tie', over: 'Over', under: 'Under', yes: 'Yes', no: 'No', nrfi: 'NRFI', yrfi: 'YRFI' }[s];
    }
    var rows = D.segments.filter(function(s) { return tmMarkets(s.key).length; }).map(function(sg) {
      var k = sg.key;
      var blocks = tmMarkets(k).map(function(p) {
        var m = p.m, mk = m === 'rfi' ? 'nrfi_yrfi' : m;
        var best = ((og.best || {})[k] || {})[mk], open = og.close ? null : ((og.open || {})[k] || {})[mk];
        var sides = m === 'ml3' ? ['away', 'draw', 'home'] : m === 'total' ? ['over', 'under'] : m === 'btts' ? ['yes', 'no'] : m === 'rfi' ? ['nrfi', 'yrfi'] : ['away', 'home'];
        var html = sides.map(function(s) {
          var v = val(best, m, s), o = val(open, m, s);
          if (!v) return '';
          return '<div class="h2h-side"><span class="h2h-sl">' + esc(sideLabel(m, s)) + '</span><span class="tp-book">' + book(k, mk, s, v, m) + '</span>' +
            '<span class="cell tp-best"><span class="ob-ln">' + esc(v.ln) + '</span>' + (m === 'ats' || m === 'total' ? '<span class="ob-pr">' + esc(priceTxt(v.price)) + '</span>' : '') + '</span>' +
            '<span class="h2h-open">' + (o ? 'Open ' + esc(o.ln) + (m === 'ats' || m === 'total' ? ' ' + esc(priceTxt(o.price)) : '') : og.close ? 'Close' : '') + '</span></div>';
        }).join('');
        return html ? '<div class="h2h-mk"><span class="tp-gl">' + esc(tpName(p)) + '</span>' + html + '</div>' : '';
      }).filter(Boolean);
      return blocks.length ? '<div class="tp-orow"><span class="tp-oseg">' + esc(k === '1i' ? '1st Inning' : sg.tag) + '</span><div class="h2h-mks">' + blocks.join('') + '</div></div>' : '';
    }).filter(Boolean);
    return rows.length ? '<div class="tp-odds">' + rows.join('') + '</div>' : '<p class="tp-none">Lines not posted yet.</p>';
  }
  function h2Lines(G) {
    if (G.state === 'pre') return '<div class="st-card tp-card" id="h2Best">' + h2BestBlocks(G) + '</div>';
    // live or final: the Matchups card (the closing lines, the result by highlight)
    var ks = D.sportType === 'baseball' ? ['f5'] : D.segments.map(function(s) { return s.key; });
    return '<div class="h2h-cards">' + ks.map(function(k) {
      return (ks.length > 1 ? '<p class="tp-gl">' + esc(seg(k).label) + '</p>' : '') + gameCard(G, k);
    }).join('') + '</div>';
  }
  // the angle: the game's trends by bet, the most agreeing first; the
  // RTYB badge when 2+ agree (scripts/h2h.py, the Matchups trends' rules)
  function h2Angle(G) {
    var bets = ((H2.data || {}).angle || {})[String(G.id)];
    if (!bets || !bets.length) return '<p class="tp-none">No trends for this game yet.</p>';
    return '<div class="st-card h2h-angle">' + bets.map(function(b) {
      return '<div class="h2h-bet"><div class="h2h-bh"><span class="t-label">' + esc(b.bet) + '</span>' +
        (b.n >= 2 ? '<span class="h2h-badge">RTYB</span><span class="tr-agree">' + b.n + ' trends agree</span>' : '') + '</div>' +
        '<ul class="h2h-tl">' + b.trends.map(function(t) { return '<li><span>' + esc(t.t) + '</span><span class="h2h-tr">' + esc(t.r) + '</span></li>'; }).join('') + '</ul></div>';
    }).join('') + '</div>';
  }
  // side by side: the away team on the road, the home team at home, in the
  // segment's markets; its fav / dog role; the last 10; units
  function h2Side(G, k) {
    var fav = segFavSide(G, k), main = h2Main(k);
    function role(side) { return (fav ? (fav === side ? (side === 'home' ? 'Home fav' : 'Road fav') : (side === 'home' ? 'Home dog' : 'Road dog')) : (side === 'home' ? 'Home' : 'Road')); }
    function cell(a, m) {
      if (!a.gp) return '-';
      return '<span class="h2h-pct">' + tmPct(a.pct) + '</span> <span class="tp-hr2">(' + h2Rec(a, m) + ')</span>' + (a.priced ? ' ' + tmUnits(a) : '');
    }
    var sides = ['away', 'home'];
    var rows = tmMarkets(k).map(function(p) {
      return '<tr><th scope="row">' + esc(tpName(p)) + '</th>' + sides.map(function(sd) {
        return '<td class="num">' + cell(tmAgg(G[sd], k, p.m, sd, h2Finals(G[sd])), p.m) + '</td>'; }).join('') + '</tr>';
    });
    if (fav) {
      rows.push('<tr><th scope="row">' + esc(tpName({ k: k, m: main })) + ' as ' + '<span class="tn-full">tonight&rsquo;s role</span><span class="tn-short">role</span></th>' + sides.map(function(sd) {
        var slug = G[sd], games = h2Finals(slug).filter(function(g) { return g[sd] === slug && (segFavSide(g, k) === sd) === (fav === sd); });
        return '<td class="num">' + cell(tmAgg(slug, k, main, sd, games), main) + '</td>';
      }).join('') + '</tr>');
    }
    rows.push('<tr><th scope="row">' + esc(tpName({ k: k, m: main })) + ', last 10</th>' + sides.map(function(sd) {
      var slug = G[sd], games = h2Finals(slug).filter(function(g) { return tmBet(g, k, main, slug); }).slice(-10);
      return '<td class="num">' + cell(tmAgg(slug, k, main, 'all', games), main) + '</td>';
    }).join('') + '</tr>');
    var head = '<tr><th></th>' + sides.map(function(sd) {
      return '<th class="num"><span class="h2h-th">' + badge(G[sd], 20) + esc(tcode(G[sd])) + '</span><span class="h2h-role">' + role(sd) + '</span></th>';
    }).join('') + '</tr>';
    return '<div class="st-card tp-card h2h-sbs h2h-x"><table class="tp-table"><thead>' + head + '</thead><tbody>' + rows.join('') + '</tbody></table></div>' +
      '<p class="tp-foot">Records in tonight&rsquo;s spots: ' + esc(tcode(G.away)) + ' on the road, ' + esc(tcode(G.home)) + ' at home' + (fav ? ', the role from the ' + esc(segTag(k)) + ' line' : '') + '.</p>';
  }
  // one graded cell of a meeting: the side that settled the bet ("-" when no line)
  function h2MeetCell(g, k, m) {
    var r = segRes(g, k) || {}, o = segOdds(g, k) || {};
    if (!r.sc || r.na) return H2_DASH;
    if (m === 'ats') {
      if (!r.ats || r.ats === 'NA' || !o.ats) return H2_DASH;
      var s = r.ats === 'L' ? 'home' : 'away', a = o.ats[s] || {};
      return typeof a.line === 'number' ? h2Cell(tcode(g[s]) + ' ' + signedLine(a.line), a.price != null ? priceTxt(a.price) : null, r.ats === 'P' ? 'p' : 'w') : H2_DASH;
    }
    if (m === 'ml' || m === 'ml3') {
      var ml = m === 'ml3' ? o.ml3 : o.ml;
      if (!ml || !r.su || r.su === 'NA') return H2_DASH;
      if (r.su === 'T') return m === 'ml3' ? h2Cell('Tie', priceTxt(ml.draw), 'w') : h2Cell('Tie', null, 'p');
      var w = r.su === 'W' ? 'away' : 'home';
      return h2Cell(tcode(g[w]), priceTxt(ml[w]), 'w');
    }
    if (m === 'total') {
      var t = o.total;
      if (!t || !r.tot || r.tot === 'NA') return H2_DASH;
      var ln = typeof t.line === 'number' ? ' ' + num1(t.line) : '';
      return r.tot === 'P' ? h2Cell('Push' + ln, null, 'p') : h2Cell((r.tot === 'O' ? 'O' : 'U') + ln, priceTxt(t[r.tot === 'O' ? 'over' : 'under']), r.tot === 'O' ? 'warm' : 'cool');
    }
    if (m === 'btts') return o.btts && (r.btts === 'Y' || r.btts === 'N') ? h2Cell(r.btts === 'Y' ? 'Yes' : 'No', priceTxt(o.btts[r.btts === 'Y' ? 'yes' : 'no']), r.btts === 'Y' ? 'warm' : 'cool') : H2_DASH;
    if (m === 'rfi') return o.nrfi_yrfi && (r.rfi === 'Y' || r.rfi === 'N') ? h2Cell(r.rfi === 'Y' ? 'YRFI' : 'NRFI', priceTxt(o.nrfi_yrfi[r.rfi === 'Y' ? 'yrfi' : 'nrfi']), r.rfi === 'Y' ? 'warm' : 'cool') : H2_DASH;
    return H2_DASH;
  }
  // head to head: every meeting this season and last, newest first; the
  // summary from the header's away team ("BOS 1Q ATS 2-2 · 1Q Over 2-2 ·
  // BOS won the 1Q 4 of 4"). Records count only the games with a line.
  function h2Meet(G, k, meets) {
    var list = meets.filter(function(g) { return g.state === 'final' && lined(g, k) && (segRes(g, k) || {}).sc; });
    if (!list.length) return '<p class="tp-none">No meetings with ' + esc(segTag(k)) + ' lines since ' + esc(H2.label || 'last season') + '.</p>';
    var X = G.away, tag = k === '1i' ? '1st inning' : segTag(k), ms = tmMarkets(k);
    var withLine = function(m) { var mk = m === 'rfi' ? 'nrfi_yrfi' : m; return list.filter(function(g) { return (segOdds(g, k) || {})[mk]; }); };
    var sum = [];
    ms.forEach(function(p) {
      var gs = withLine(p.m), n = 0, x = 0, y = 0;
      if (!gs.length) return;
      if (p.m === 'ats') { var a = tmAgg(X, k, 'ats', 'all', gs); if (a.gp) sum.push(esc(tcode(X)) + ' ' + esc(tag) + ' ATS ' + h2Rec(a, 'ats')); }
      else if (p.m === 'total') { gs.forEach(function(g) { var r = segRes(g, k); if (r.tot === 'O') x++; else if (r.tot === 'U') y++; }); if (x + y) sum.push(esc(tag) + ' Over ' + x + '-' + y); }
      else if (p.m === 'btts') { gs.forEach(function(g) { var r = segRes(g, k); if (r.btts === 'Y') x++; else if (r.btts === 'N') y++; }); if (x + y) sum.push(esc(tag) + ' BTTS Yes ' + x + '-' + y); }
      else if (p.m === 'rfi') { gs.forEach(function(g) { var r = segRes(g, k); if (r.rfi === 'N') x++; else if (r.rfi === 'Y') y++; }); if (x + y) sum.push('NRFI ' + x + '-' + y); }
      else if (p.m === 'ml') { gs.forEach(function(g) { var b = tmBet(g, k, 'ml', X); if (b) { n++; if (b.r === 'W') x++; } }); if (n) sum.push(esc(tcode(X)) + ' won the ' + esc(tag) + ' ' + x + ' of ' + n); }
    });
    var head = '<tr><th>Date</th><th>Game</th><th class="num">' + esc(k === '1i' ? '1st' : segTag(k)) + '</th>' + ms.map(function(p) {
      return '<th class="tp-lc"><span class="tn-full">' + esc(tpName(p)) + '</span><span class="tn-short">' + esc({ ml: 'ML', ml3: '3W', ats: D.sportType === 'baseball' ? 'RL' : D.sport === 'nhl' ? 'PL' : 'Spread', total: 'Total', btts: 'BTTS', rfi: 'NRFI' }[p.m]) + '</span></th>';
    }).join('') + '<th class="num tp-fin">Final</th></tr>';
    var rows = list.slice().reverse().map(function(g) {
      var sc = segRes(g, k).sc, a = sc[0], h = sc[1];
      var segSc = a === h ? 'Tied ' + a + '-' + h : tcode(a > h ? g.away : g.home) + ' ' + Math.max(a, h) + '-' + Math.min(a, h);
      var fin = g.as != null && g.hs != null ? (g.as === g.hs ? 'Tied ' : tcode(g.as > g.hs ? g.away : g.home) + ' ') + Math.max(g.as, g.hs) + '-' + Math.min(g.as, g.hs) + (g.ot ? ' ' + esc(g.ot) : '') : '-';
      return '<tr><td class="tp-d">' + esc(h2LongDate(g, true)) + '</td><td>' + esc(tcode(g.away)) + ' @ ' + esc(tcode(g.home)) + '</td><td class="num">' + esc(segSc) + '</td>' +
        ms.map(function(p) { return '<td class="tp-lc"><div class="tp-res">' + h2MeetCell(g, k, p.m) + '</div></td>'; }).join('') + '<td class="num tp-fin">' + fin + '</td></tr>';
    }).join('');
    return (sum.length ? '<p class="tp-line">' + sum.join(' &middot; ') + '</p>' : '') +
      '<div class="st-card tp-card tp-log h2h-x"><table class="tp-table"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div>';
  }
  function h2StreakText(m, kind, k) {
    var tag = D.sportType === 'baseball' ? (m === 'rfi' ? '' : 'F5 ') : seg(k).tag + ' ';
    if (m === 'ml') return tag + (kind === 'W' ? 'wins' : 'losses');
    if (m === 'ats') return tag + (kind === 'W' ? 'covers' : 'non-covers');
    if (m === 'total') return tag + (kind === 'O' ? 'Over' : 'Under') + (D.sport === 'nhl' ? ' 1.5' : '');
    if (m === 'btts') return 'BTTS ' + (kind === 'Y' ? 'Yes' : 'No');
    return kind === 'Y' ? 'YRFI' : 'NRFI';
  }
  // current streaks (heat chips, 3+) and the last 5 in the segment's side market
  function h2Form(G, k) {
    var main = h2Main(k);
    return '<div class="h2h-2col">' + [G.away, G.home].map(function(slug) {
      var chips = [];
      D.segments.forEach(function(s) {
        var seqs = teamSeqs('9999-12-31', s.key), done = {};
        tmMarkets(s.key).forEach(function(p) {
          var m = p.m === 'ml3' ? 'ml' : p.m, st = !done[m] && HIT[m] ? streakOf(((seqs[slug] || {})[m]) || []) : null;
          done[m] = 1;
          if (st && st.n >= 3) chips.push({ n: st.n, html: '<div class="tp-chip"><span class="tp-cn ' + heatCls(st.n) + '">' + st.n + '</span><span class="tp-ct">' + st.n + ' straight ' + esc(h2StreakText(m, st.kind, s.key)) + '</span></div>' });
        });
      });
      chips.sort(function(a, b) { return b.n - a.n; });
      var last = h2Finals(slug).map(function(g) { return tmBet(g, k, main, slug); }).filter(Boolean).slice(-5);
      var cells = last.map(function(b) { return h2Cell(tmLetter(b.r, main), null, b.r === 'W' ? 'w' : b.r === 'L' ? 'n' : 'p'); }).join('');
      return '<div class="st-card tp-card"><div class="st-head"><h4>' + badge(slug, 20) + ' ' + esc(shortName(slug)) + '</h4></div>' +
        (chips.length ? '<div class="tp-chips">' + chips.map(function(c) { return c.html; }).join('') + '</div>' : '<p class="tp-none">No active streaks of 3 or more.</p>') +
        '<p class="tp-gl h2h-l5h">Last 5 &middot; ' + esc(tpName({ k: k, m: main })) + '</p>' +
        (cells ? '<div class="h2h-l5">' + cells + '</div>' : '<p class="tp-none">No graded games yet.</p>') + '</div>';
    }).join('') + '</div>';
  }
  // scoring in tonight's roles, and what the two averages add to vs the total
  function h2Scoring(G, k) {
    function avgs(slug, side) {
      var f = 0, a = 0, n = 0, i = side === 'home' ? 1 : 0;
      h2Finals(slug).forEach(function(g) { var r = segRes(g, k); if (g[side] !== slug || !r || !r.sc) return; f += r.sc[i]; a += r.sc[1 - i]; n++; });
      return n ? { f: f / n, a: a / n, n: n } : null;
    }
    var x = avgs(G.away, 'away'), y = avgs(G.home, 'home'), tag = k === '1i' ? '1st inning' : segTag(k);
    var row = function(slug, v, where) {
      return '<tr><th scope="row">' + badge(slug, 20) + ' ' + esc(tcode(slug)) + ' <span class="tp-hr2">' + where + '</span></th><td class="num">' + (v ? num1(v.f) : '-') + '</td><td class="num">' + (v ? num1(v.a) : '-') + '</td><td class="num">' + (v ? v.n : 0) + '</td></tr>';
    };
    var t = ((segOdds(G, k) || {}).total || {}).line;
    if (t == null && H2.og) t = ((((H2.og.best || {})[k] || {}).total) || {}).line;
    if (t == null && D.sport === 'nhl') t = 1.5;
    var line = x && y ? '<p class="tp-line">Their ' + esc(tag) + ' averages add to ' + num1(x.f + y.f) + (typeof t === 'number' ? ' vs the ' + num1(t) + ' total' : '') + '.</p>' : '';
    return line + '<div class="st-card tp-card h2h-x"><table class="tp-table"><thead><tr><th></th><th class="num">' + esc(tag) + ' ' + esc(scoreWord()) + ' for</th><th class="num">Allowed</th><th class="num">Games</th></tr></thead><tbody>' +
      row(G.away, x, 'on the road') + row(G.home, y, 'at home') + '</tbody></table></div>';
  }
  // the 3-5 strongest Situational splits tonight's game fits, both teams
  var H2_SPOTS_PER = 2;
  function h2Spots(G, k) {
    var e = sitEngine();
    if (!e || G.state !== 'pre' || !findGame(G.id)) return '';
    var out = [];
    [G.away, G.home].forEach(function(slug) {
      (e.markets || []).forEach(function(mk) {
        (e.spots(k, slug, G.id, mk.id) || []).forEach(function(x) { if (x.pct != null) out.push({ slug: slug, mk: mk, x: x }); });
      });
    });
    // the strongest spots, at most 2 per team and 2 per market (so both teams show)
    out.sort(function(a, b) { return Math.abs(b.x.pct - 0.5) - Math.abs(a.x.pct - 0.5); });
    var per = {};
    out = out.filter(function(o) {
      var t = 't:' + o.slug, m = 'm:' + o.mk.id;
      if ((per[t] || 0) >= H2_SPOTS_PER || (per[m] || 0) >= H2_SPOTS_PER) return false;
      per[t] = (per[t] || 0) + 1; per[m] = (per[m] || 0) + 1;
      return true;
    });
    if (!out.length) return '<p class="tp-none">No situational edges for tonight&rsquo;s spot.</p>';
    return '<div class="st-card tp-card h2h-x"><table class="tp-table"><thead><tr><th>Team</th><th>Spot</th><th>Market</th><th class="num">Rate</th></tr></thead><tbody>' + out.map(function(o) {
      return '<tr><td>' + badge(o.slug, 20) + ' ' + esc(tcode(o.slug)) + '</td><td>' + esc(o.x.label) + '</td><td>' + esc(segTag(k) + ' ' + o.mk.label) + ' <span class="tp-hr2">' + esc(o.mk.pctHead) + '</span></td>' +
        '<td class="num">' + tmPct(o.x.pct) + ' <span class="tp-hr2">(' + esc(o.x.rec) + ')</span></td></tr>';
    }).join('') + '</tbody></table></div>';
  }
  function h2Preview(G) {
    var days = (H2.data || {}).previewDays || [], d = h2Day(G);
    var hit = days.indexOf(d) !== -1 ? d : null;
    if (!hit && D.schedule === 'week' && G.wk) hit = days.filter(function(x) { return x <= d && (D.weeks || []).some(function(w) { return w.key === G.wk && x >= w.start; }); }).pop() || null;
    return hit ? '<div class="fr-links"><a class="fr-more" href="' + ROOT + SPORT_SLUG + '/preview/' + hit + '/">Read the ' + esc(D.label) + ' Preview &rarr;</a></div>' : '';
  }
  function renderH2H() {
    var A = app.getAttribute('data-a'), B = app.getAttribute('data-b');
    try { var p = JSON.parse((document.getElementById('h2hPrev') || {}).textContent || '{}'); H2.label = p.label || ''; H2.prev = p.games || []; } catch (e) { H2.prev = []; }
    var cur = teamGames(A).filter(function(g) { return g.away === B || g.home === B; });
    var meets = H2.prev.slice().sort(function(a, b) { return (a.start || '') < (b.start || '') ? -1 : 1; }).concat(cur);
    var next = cur.filter(function(g) { return g.state === 'pre' || g.state === 'in'; })[0];
    var done = meets.filter(function(g) { return g.state === 'final'; });
    var G = next || done[done.length - 1];
    if (!G) return;   // never met: the page's own text stays
    var which = next ? 'next' : 'last';
    var segBar = function(id) { return segToggle(id, h2K(), 'data-h2-seg'); };
    function drawSeg() {
      var k = h2K();
      document.getElementById('h2SideBox').innerHTML = h2Side(G, k);
      document.getElementById('h2MeetBox').innerHTML = h2Meet(G, k, meets);
      document.getElementById('h2FormBox').innerHTML = h2Form(G, k);
      document.getElementById('h2ScoreBox').innerHTML = h2Scoring(G, k);
      var sp = document.getElementById('h2SpotBox');
      if (sp) sp.innerHTML = h2Spots(G, k);
      app.querySelectorAll('[data-h2-seg]').forEach(function(b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-h2-seg') === k)); });
    }
    var spots = splitReg() && G.state === 'pre' && findGame(G.id);
    app.innerHTML = h2Header(G, which) +
      '<div id="h2Over">' + tmSection(G.state === 'pre' ? 'Best lines now' : 'Closing lines and result', '<div id="h2LinesBox">' + h2Lines(G) + '</div>') +
      (G.state === 'pre' ? tmSection('The angle', '<div id="h2AngleBox"><p class="tp-none">Loading&hellip;</p></div>') : '') +
      '<div hidden data-h2h-soon="full-run"></div><div hidden data-h2h-soon="due-factor"></div>' +
      tmSection('Side by side', '<div id="h2SideBox"></div>', null, segBar('h2Seg1')) + '</div>' +
      '<div id="h2Meet">' + tmSection('Head to head', '<div id="h2MeetBox"></div>', null, segBar('h2Seg2')) + '</div>' +
      '<div id="h2Trends">' + tmSection('Streaks and last 5', '<div id="h2FormBox"></div>', null, segBar('h2Seg3')) +
      tmSection('Scoring by segment', '<div id="h2ScoreBox"></div>', null, segBar('h2Seg4')) +
      (spots ? tmSection('Situational spots', '<div id="h2SpotBox"></div>', null, segBar('h2Seg5')) : '') + '</div>' +
      '<div hidden data-h2h-soon="injuries"></div><div hidden data-h2h-soon="starters"></div>' +
      '<div id="h2Odds">' + tmSection('Odds', '<div id="h2OddsBox"><p class="tp-none">Loading&hellip;</p></div>') + '</div>' +
      '<div id="h2PrevBox"></div>';
    app.addEventListener('click', function(e) {
      var b = e.target.closest('[data-h2-seg]');
      if (b) { H2.k = b.getAttribute('data-h2-seg'); drawSeg(); }
    });
    drawSeg();
    wireTips(app);
    var day = h2Day(G);
    Promise.all([fetch(dataUrl(SPORT_SLUG + '/odds.json')).then(function(r) { return r.ok ? r.json() : {}; }).catch(function() { return {}; }),
                 fetch(dataUrl(SPORT_SLUG + '/odds/' + day + '.json')).then(function(r) { return r.ok ? r.json() : { games: [] }; }).catch(function() { return { games: [] }; }),
                 fetch(dataUrl(SPORT_SLUG + '/h2h.json')).then(function(r) { return r.ok ? r.json() : {}; }).catch(function() { return {}; })]).then(function(x) {
      H2.sources = x[0].sources || {};
      H2.og = (x[1].games || []).filter(function(o) { return o.away === G.away && o.home === G.home; })[0] || null;
      H2.data = x[2] || {};
      if (G.state === 'pre') document.getElementById('h2LinesBox').innerHTML = h2Lines(G);
      var ab = document.getElementById('h2AngleBox');
      if (ab) ab.innerHTML = h2Angle(G);
      document.getElementById('h2PrevBox').innerHTML = h2Preview(G);
      drawSeg();   // the scoring line's total, from the best line
      if (H2.og) renderOdds({ box: document.getElementById('h2OddsBox'), day: day, away: G.away, home: G.home });
      else document.getElementById('h2OddsBox').innerHTML = '<p class="tp-none">Lines not posted yet.</p>';
    });
  }

  // ---------------------------------------------------------------- boot
  // NHL's data.json is its own shape; its Matchups, Stats, Trends and Teams pages read the shared shape (nhl/sport.json)
  var DATA_FILE = SPORT_SLUG === 'nhl' && ['games', 'stats', 'splits', 'edges', 'trends', 'teams', 'team', 'h2h'].indexOf(SECTION) !== -1 ? 'sport.json' : 'data.json';
  // the hub (/{sport}/) is all static HTML (scripts/front.py sections)
  if (SECTION !== 'hub') fetch(dataUrl(SPORT_SLUG + '/' + DATA_FILE)).then(function(r) { return r.json(); }).then(function(data) {
    D = data;
    if (SECTION === 'odds') { renderOdds(); return; }   // works from odds.json alone for NHL
    if (!D.segments || !D.segments.length) return;
    if (SECTION === 'games') renderGames();
    else if (SECTION === 'stats') renderStats();
    else if (SECTION === 'splits') renderSplits();
    else if (SECTION === 'edges') renderEdges();
    else if (SECTION === 'trends') renderTrends();
    else if (SECTION === 'team') renderTeam();
    else if (SECTION === 'teams') renderTeamsIndex();
    else if (SECTION === 'h2h') renderH2H();
    else if (SECTION === 'odds') renderOdds();
  }).catch(function(e) {
    if (SECTION !== 'team' && SECTION !== 'teams') app.innerHTML = emptyNote('Couldn&rsquo;t load ' + esc(SPORT_SLUG) + ' data. Try reloading.');
    if (window.console) console.error(e);
  });
})();
