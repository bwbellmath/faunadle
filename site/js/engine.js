// Faunadle engine: tree queries, search and the daily puzzle. No DOM access.
(function () {
  'use strict';

  function Game(data) {
    this.d = data;
    this.n = data.n;
    var par = data.parent, N = par.length;
    // Depth of every node (parents may come before or after children in index order).
    var depth = new Int32Array(N).fill(-1);
    for (var i = 0; i < N; i++) {
      var chain = [], x = i;
      while (x !== -1 && depth[x] === -1) { chain.push(x); x = par[x]; }
      var dd = x === -1 ? -1 : depth[x];
      for (var k = chain.length - 1; k >= 0; k--) depth[chain[k]] = ++dd;
    }
    this.depth = depth;
    this.rootAge = Math.max.apply(null, data.age);
    // Search keys.
    this.keys = [];
    for (var t = 0; t < this.n; t++) {
      var alt = (data.alt && data.alt[t]) || [];
      this.keys.push({ c: norm(data.common[t]), s: norm(data.sci[t]), a: alt.map(norm) });
    }
    this.sciIndex = {};
    for (var s = 0; s < this.n; s++) this.sciIndex[data.sci[s]] = s;
  }

  function norm(s) {
    return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
      .replace(/[’'`.]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  }

  Game.prototype.age = function (node) { return node < this.n ? 0 : this.d.age[node - this.n]; };
  Game.prototype.lca = function (a, b) {
    var par = this.d.parent, dep = this.depth;
    while (dep[a] > dep[b]) a = par[a];
    while (dep[b] > dep[a]) b = par[b];
    while (a !== b) { a = par[a]; b = par[b]; }
    return a;
  };
  // Taxonomic groups containing species i, smallest first: [{name, k}].
  Game.prototype.lineage = function (i) {
    var out = [], gp = this.d.groupParent;
    for (var k = this.d.tipGroup[i]; k >= 0; k = gp[k]) out.push({ name: this.d.groups[k], k: k });
    return out;
  };
  // Smallest taxonomic group containing both species (null if none).
  Game.prototype.sharedGroups = function (a, b) {
    var inB = {};
    this.lineage(b).forEach(function (g) { inB[g.k] = true; });
    var la = this.lineage(a);
    for (var j = 0; j < la.length; j++) if (inB[la[j].k]) return la.slice(j);
    return [];
  };

  // Score a guess against the target.
  //   links:  branch points on the path between them in the tree (0 = the target)
  //   age:    Myr since their last common ancestor
  //   group:  the smallest named group containing both
  //   warmth: 0-100, log scale of age against the root age
  Game.prototype.evaluate = function (guess, target) {
    if (guess === target) return { idx: guess, links: 0, age: 0, group: null, warmth: 100, isTarget: true };
    var l = this.lca(guess, target);
    var links = (this.depth[guess] - this.depth[l]) + (this.depth[target] - this.depth[l]) - 1;
    var age = this.age(l);
    var shared = this.sharedGroups(guess, target);
    var warmth = 100 * (1 - Math.log1p(age) / Math.log1p(this.rootAge));
    return { idx: guess, links: links, age: age, group: shared.length ? shared[0].name : null,
      shared: shared, warmth: Math.max(0, Math.min(99.9, warmth)), isTarget: false };
  };

  Game.prototype.label = function (i) { return this.d.common[i] || this.d.sci[i]; };
  Game.prototype.genus = function (i) { return this.d.sci[i].split(' ')[0]; };
  // Hint k: the target's group at hint rank k (order, family...), then its genus.
  Game.prototype.hint = function (i, k) {
    var h = this.d.hints;
    if (k < h.length) return h[k][i] >= 0 ? this.d.groups[h[k][i]] : null;
    if (k === h.length) return this.genus(i);
    return null;
  };

  // Ranked matches for a typed query: exact, then prefix, then word-prefix, then
  // substring; ties go to the better-known species.
  Game.prototype.search = function (q, limit) {
    q = norm(q);
    if (!q) return [];
    var hits = [], pop = this.d.pop;
    for (var i = 0; i < this.n; i++) {
      var k = this.keys[i], best = 9;
      [k.c, k.s].concat(k.a).forEach(function (s, which) {
        if (!s) return;
        which = which === 1 ? 1 : which > 1 ? 2 : 0;  // common, scientific, alias
        var r = 9;
        if (s === q) r = 0;
        else if (s.indexOf(q) === 0) r = 1;
        else if ((' ' + s).indexOf(' ' + q) >= 0) r = 2;
        else if (s.indexOf(q) >= 0) r = 3;
        // Common names first: a word in a common name beats the start of a scientific one.
        if (r < 9 && which) r += r === 0 ? 0.25 * which : 1.5;
        if (r < best) best = r;
      });
      if (best < 9) hits.push([best, -pop[i], i]);
    }
    hits.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; });
    return hits.slice(0, limit || 8).map(function (h) { return h[2]; });
  };

  // --- daily puzzle ----------------------------------------------------------------
  function dayNumber(epoch, date) {
    var e = new Date(epoch + 'T00:00:00');
    var d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    return Math.round((d - e) / 86400000) + 1;
  }
  Game.prototype.puzzleTarget = function (num) {
    var pool = this.d.pool;
    return pool[((num - 1) % pool.length + pool.length) % pool.length];
  };

  // "45M", "6.4M", "393K", "4,000"
  function formatAge(myr) {
    if (myr >= 10) return Math.round(myr) + 'M';
    if (myr >= 1) return (Math.round(myr * 10) / 10) + 'M';
    var ky = myr * 1000;
    if (ky >= 10) return Math.round(ky) + 'K';
    if (ky >= 1) return (Math.round(ky * 10) / 10) + 'K';
    return Math.round(myr * 1e6).toLocaleString();
  }

  // "45 million years", "393,000 years"
  function formatAgeLong(myr) {
    if (myr >= 1) return (myr >= 10 ? Math.round(myr) : Math.round(myr * 10) / 10) + ' million years';
    var y = myr * 1e6;
    y = y >= 10000 ? Math.round(y / 1000) * 1000 : y >= 1000 ? Math.round(y / 100) * 100 : Math.round(y);
    return y.toLocaleString('en-US') + ' years';
  }

  window.Faunadle = { Game: Game, dayNumber: dayNumber, formatAge: formatAge, formatAgeLong: formatAgeLong, norm: norm };
})();
