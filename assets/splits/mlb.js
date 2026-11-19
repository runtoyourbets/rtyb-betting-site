/*
 * MLB Situational Results registry: the team pages only (teamOnly; the MLB
 * Stats page has no Splits table). Markets: First Five moneyline, run line
 * and total, and the 1st inning's NRFI. Favorite / underdog by the closing
 * F5 moneyline, else the full-game one; a pick'em is neither. Times are ET.
 */
(function() {
  var C = { lossBy: 3, day: 17 * 60 };
  var groups = [
    { id: 'ha', label: 'Home / Away / Favorite / Underdog' }, { id: 'opp', label: 'Opponent' },
    { id: 'rest', label: 'Schedule' }, { id: 'prev', label: 'Previous Game' },
  ];
  var rows = [
    { id: 'home', label: 'Home', short: 'Home', group: 'ha', own: true, def: 'Games as the home team.', test: function(c) { return c.home; } },
    { id: 'away', label: 'Away', short: 'Away', group: 'ha', own: true, def: 'Games as the road team.', test: function(c) { return !c.home; } },
    { id: 'fav', label: 'Favorite', short: 'Fav', group: 'ha', own: true, def: 'Favored by the closing F5 moneyline (full-game when there’s no F5 price).', test: function(c) { return c.fav === true; } },
    { id: 'dog', label: 'Underdog', short: 'Dog', group: 'ha', own: true, def: 'The underdog by the closing F5 moneyline (full-game when there’s no F5 price).', test: function(c) { return c.fav === false; } },

    { id: 'div', label: 'Division', short: 'Div', group: 'opp', own: true, def: 'Against a division rival.', test: function(c) { return c.ti && c.oi && c.ti.division && c.ti.division === c.oi.division; } },
    { id: 'vo500', label: 'Vs. teams over .500', short: 'vs >.500', group: 'opp', own: true, def: 'The opponent was over .500 going into the game (this season).', test: function(c) { return c.oppW > c.oppL; } },
    { id: 'vu500', label: 'Vs. teams under .500', short: 'vs <.500', group: 'opp', own: true, def: 'The opponent was under .500 going into the game.', test: function(c) { return c.oppW < c.oppL; } },

    { id: 'dan', label: 'Day game after a night game', short: 'Day after night', group: 'rest', own: true,
      def: 'A game before 5 PM ET the day after a game at 5 PM ET or later.',
      test: function(c) { return c.rest === 1 && c.mins < C.day && c.prev && c.prev.mins >= C.day; } },

    { id: 'pw', label: 'After a win', short: 'Off W', group: 'prev', own: true, def: 'Won its previous game.', test: function(c) { return c.prev && c.prev.res === 'W'; } },
    { id: 'pl', label: 'After a loss', short: 'Off L', group: 'prev', own: true, def: 'Lost its previous game.', test: function(c) { return c.prev && c.prev.res === 'L'; } },
    { id: 'pl3', label: 'After a loss by 3+', short: 'Off L by 3+', group: 'prev', own: true, def: 'Lost its previous game by 3 or more runs.', test: function(c) { return c.prev && c.prev.pa - c.prev.pf >= C.lossBy; } },
    { id: 'pshut', label: 'After being shut out', short: 'Off shutout', group: 'prev', own: true, def: 'Scored no runs in its previous game.', test: function(c) { return c.prev && c.prev.pf === 0; } },
  ];
  window.RTYB_SPLITS = window.RTYB_SPLITS || {};
  window.RTYB_SPLITS.mlb = { config: C, groups: groups, rows: rows, favBy: 'seg-ml', periods: 9, smallSample: 8, teamOnly: true,
    markets: [{ id: 'su', label: 'F5 ML' }, { id: 'ats', label: 'F5 Run Line' }, { id: 'tot', label: 'F5 O/U' }, { id: 'rfi', label: 'NRFI' }] };
})();
