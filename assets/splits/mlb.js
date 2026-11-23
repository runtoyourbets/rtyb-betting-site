/*
 * MLB Situational Results registry: the team pages and the MLB Splits page.
 * Markets: First Five moneyline, run line and total, and the 1st inning's
 * NRFI. Favorite / underdog by the closing F5 moneyline, else the full-game
 * one; a pick'em is neither. Times are ET except Day / Night (the park's
 * local time: c.venueTz, standard-time offset; Arizona stays on standard
 * time all year). Total Size and "After losing the F5" use the F5 on every
 * segment (sizeTotal, bounceSeg).
 */
(function() {
  var C = { lossBy: 3, day: 17 * 60, noDst: ['ari'], altitude: ['col'] };
  // minutes after local midnight at the park (ET, shifted by the park's zone)
  function local(c) {
    if (c.venueTz == null) return null;
    var dst = c.month >= 4 && c.month <= 10 && C.noDst.indexOf(c.g.home) !== -1 ? -60 : 0;
    return (c.mins + (c.venueTz + 5) * 60 + dst + 1440) % 1440;
  }
  function third(c, n) {
    if (c.segTotal == null || !c.cuts) return false;
    return n === 0 ? c.segTotal < c.cuts[0] : n === 1 ? c.segTotal >= c.cuts[0] && c.segTotal < c.cuts[1] : c.segTotal >= c.cuts[1];
  }
  function mid(k) { return k[1] - 0.5 <= k[0] ? String(k[0]) : k[0] + ' to ' + (k[1] - 0.5); }
  // a total-size row's name with its range: "Low F5 total (under 4.5)"
  function cutLabel(name, n) {
    return function(C2, info) { var k = info.cuts; return k ? name + ' (' + ['under ' + k[0], mid(k), k[1] + '+'][n] + ')' : name; };
  }
  function cutDef(n) {
    return function(C2, info) {
      var k = info.cuts;
      if (!k) return 'Not enough posted F5 totals this season to split into thirds yet.';
      return ['F5 total under ' + k[0] + ' (bottom third this season).', 'F5 total ' + mid(k) + ' (middle third).', 'F5 total ' + k[1] + ' or higher (top third this season).'][n];
    };
  }
  var groups = [
    { id: 'ha', label: 'Home / Away / Favorite / Underdog' }, { id: 'opp', label: 'Opponent' }, { id: 'tip', label: 'Time' },
    { id: 'rest', label: 'Rest & Travel' }, { id: 'prev', label: 'Previous Game' }, { id: 'size', label: 'Total Size' },
  ];
  var rows = [
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team.', test: function(c) { return c.home; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team.', test: function(c) { return !c.home; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the closing F5 moneyline (full-game when there’s no F5 price).', test: function(c) { return c.fav === true; } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the closing F5 moneyline (full-game when there’s no F5 price).', test: function(c) { return c.fav === false; } },

    { id: 'div', label: 'Division', short: 'Div', group: 'opp', own: true, def: 'Against a division rival.', test: function(c) { return c.ti && c.oi && c.ti.division && c.ti.division === c.oi.division; } },
    { id: 'vo500', label: 'Vs. teams over .500', short: 'vs >.500', group: 'opp', own: true, def: 'The opponent was over .500 going into the game (this season).', test: function(c) { return c.oppW > c.oppL; } },
    { id: 'vu500', label: 'Vs. teams under .500', short: 'vs <.500', group: 'opp', own: true, def: 'The opponent was under .500 going into the game.', test: function(c) { return c.oppW < c.oppL; } },

    { id: 'dayg', label: 'Day game (before 5 PM local)', short: 'Day game', group: 'tip', def: 'First pitch before 5:00 PM at the park.',
      test: function(c) { var m = local(c); return m != null && m < C.day; } },
    { id: 'nightg', label: 'Night game', short: 'Night game', group: 'tip', def: 'First pitch at 5:00 PM or later at the park.',
      test: function(c) { var m = local(c); return m != null && m >= C.day; } },
    { id: 'wkday', label: 'Weekday', short: 'Weekday', group: 'tip', def: 'Monday through Friday.', test: function(c) { return c.dow >= 1 && c.dow <= 5; } },
    { id: 'wkend', label: 'Weekend', short: 'Weekend', group: 'tip', def: 'Saturday and Sunday.', test: function(c) { return c.dow === 6 || c.dow === 0; } },

    { id: 'dan', label: 'Day game after a night game', short: 'Day after night', group: 'rest', own: true,
      def: 'A game before 5 PM ET the day after a game at 5 PM ET or later.',
      test: function(c) { return c.rest === 1 && c.mins < C.day && c.prev && c.prev.mins >= C.day; } },
    { id: 'offday', label: 'After an off day', short: 'Off day', group: 'rest', own: true, def: 'One or more days off before the game.',
      test: function(c) { return c.restDays != null && c.restDays >= 1; } },
    { id: 'dh2', label: '2nd game of a doubleheader', short: 'DH game 2', group: 'rest', own: true, def: 'The second game the team played that day.',
      test: function(c) { return c.rest === 0; } },
    { id: 'tripl', label: 'Last game of a road trip', short: 'Trip finale', group: 'rest', own: true, def: 'A road game with the next game at home.',
      test: function(c) { return c.tripLast; } },
    { id: 'hometrip', label: 'First home game after a road trip', short: 'Home from trip', group: 'rest', own: true, def: 'Home after one or more straight road games.',
      test: function(c) { return c.home && c.tripEnded >= 1; } },
    { id: 'tz', label: 'Crossed 2+ time zones', short: '2+ time zones', group: 'rest', own: true, def: 'Two or more time zones from the last game’s park.',
      test: function(c) { return c.tzCrossed != null && c.tzCrossed >= 2; } },
    { id: 'coors', label: 'At altitude (Coors Field)', short: 'Coors', group: 'rest', own: true, def: 'Road games at Coors Field in Denver.',
      test: function(c) { return !c.home && C.altitude.indexOf(c.g.home) !== -1; } },

    { id: 'pw', label: 'After a win', short: 'Off W', group: 'prev', own: true, def: 'Won its previous game.', test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'pl', label: 'After a loss', short: 'Off L', group: 'prev', own: true, def: 'Lost its previous game.', test: function(c) { return c.prev && c.prev.res === 'L'; } },
    { id: 'pl3', label: 'After a loss by 3+', short: 'Off L by 3+', group: 'prev', own: true, def: 'Lost its previous game by 3 or more runs.', test: function(c) { return c.prev && c.prev.pa - c.prev.pf >= C.lossBy; } },
    { id: 'pshut', label: 'After being shut out', short: 'Off shutout', group: 'prev', own: true, def: 'Scored no runs in its previous game.', test: function(c) { return c.prev && c.prev.pf === 0; } },
    { id: 'psegf5', label: 'After losing the F5 last game', short: 'F5 bounce', group: 'prev', own: true, def: 'Trailed after five innings last game.',
      test: function(c) { return c.prev && c.prev.segRes === 'L'; } },

    { id: 'tlow', label: cutLabel('Low F5 total', 0), short: 'Low total', group: 'size', def: cutDef(0), test: function(c) { return third(c, 0); } },
    { id: 'tmid', label: cutLabel('Middle F5 total', 1), short: 'Mid total', group: 'size', def: cutDef(1), test: function(c) { return third(c, 1); } },
    { id: 'thigh', label: cutLabel('High F5 total', 2), short: 'High total', group: 'size', def: cutDef(2), test: function(c) { return third(c, 2); } },
  ];
  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.mlb = { config: C, groups: groups, rows: rows, favBy: 'seg-ml', periods: 9, smallSample: 8,
    bounceSeg: 'f5', sizeTotal: function(g) { return ((((g.odds || {}).f5 || {}).total) || {}).line; },
    perspectives: [['home', 'Home team'], ['fav', 'Favorite']],
    markets: [{ id: 'su', label: 'F5 ML' }, { id: 'ats', label: 'F5 Run Line' }, { id: 'tot', label: 'F5 O/U' }, { id: 'rfi', label: 'NRFI' }] };
})();
