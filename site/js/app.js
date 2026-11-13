// Faunadle game page.
(function () {
  'use strict';
  var F = window.Faunadle;
  var config = window.FAUNADLE_CONFIG;
  var gameId = window.FAUNADLE_GAME;
  var data = (window.FAUNADLE_DATA || {})[gameId];
  var $ = function (id) { return document.getElementById(id); };
  if (!data) { $('message').textContent = 'Could not load this game’s data.'; return; }

  var game = new F.Game(data);
  var params = new URLSearchParams(location.search);
  var practice = params.has('practice');
  var today = F.dayNumber(config.epoch, new Date());
  var puzzle = today;
  var isLocal = /^(localhost|127\.|$)/.test(location.hostname);
  if (params.has('puzzle')) {
    var p = parseInt(params.get('puzzle'), 10);
    if (p >= 1 && (p <= today || isLocal)) puzzle = p;
  }
  var target = practice ? randomTarget() : game.puzzleTarget(puzzle);
  var MAX_HINTS = config.maxHints;

  var state = { guesses: [], explore: [], solved: false, gaveUp: false, hints: 0 };
  var latest = null, openIdx = null, suggest = [], active = 0;

  function randomTarget() { return data.pool[Math.floor(Math.random() * data.pool.length)]; }

  // --- storage (best effort) -----------------------------------------------------
  var prefix = 'faunadle:' + gameId + ':';
  function store(k, v) { try { localStorage.setItem(prefix + k, JSON.stringify(v)); } catch (e) {} }
  function fetchKey(k) { try { return JSON.parse(localStorage.getItem(prefix + k) || 'null'); } catch (e) { return null; } }
  function save() {
    if (practice) return;
    store('p' + puzzle, {
      g: state.guesses.map(function (g) { return data.sci[g.idx]; }),
      x: state.explore.map(function (g) { return data.sci[g.idx]; }),
      solved: state.solved, gaveUp: state.gaveUp, hints: state.hints,
    });
  }
  function restore() {
    if (practice) return;
    var s = fetchKey('p' + puzzle);
    if (!s) return;
    var n = 0;
    (s.g || []).forEach(function (sci) {
      var i = game.sciIndex[sci];
      if (i != null) state.guesses.push(score(i, ++n));
    });
    (s.x || []).forEach(function (sci) {
      var i = game.sciIndex[sci];
      if (i != null) { var r = score(i, 0); r.explore = true; state.explore.push(r); }
    });
    state.solved = !!s.solved; state.gaveUp = !!s.gaveUp; state.hints = s.hints || 0;
  }
  function recordStats() {
    if (practice || puzzle !== today) return;
    var st = fetchKey('stats') || { played: 0, won: 0, streak: 0, best: 0, last: null, dist: {} };
    if (st.last === puzzle) return;
    st.played++;
    if (state.solved) {
      st.won++;
      st.streak = st.last === puzzle - 1 ? st.streak + 1 : 1;
      st.best = Math.max(st.best, st.streak);
      var b = bucket(state.guesses.length);
      st.dist[b] = (st.dist[b] || 0) + 1;
    } else st.streak = 0;
    st.last = puzzle;
    store('stats', st);
  }
  function bucket(n) { return n <= 5 ? '1–5' : n <= 10 ? '6–10' : n <= 20 ? '11–20' : n <= 40 ? '21–40' : '41+'; }

  // --- helpers -------------------------------------------------------------------
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function over() { return state.solved || state.gaveUp; }
  function score(i, n) { var r = game.evaluate(i, target); r.n = n; return r; }
  function setMessage(t, err) { var m = $('message'); m.textContent = t || ''; m.className = 'message' + (err ? ' error' : ''); }

  var TIERS = [
    { min: 75, cls: 't0', label: '🔥 hot', sq: '🟥' },
    { min: 55, cls: 't1', label: 'warm', sq: '🟧' },
    { min: 35, cls: 't2', label: 'tepid', sq: '🟨' },
    { min: 15, cls: 't3', label: 'cool', sq: '🟦' },
    { min: -1, cls: 't4', label: '🧊 cold', sq: '🟪' },
  ];
  function tier(g) {
    if (g.isTarget) return { cls: 'twin', label: data.emoji + ' correct!', sq: data.emoji };
    for (var k = 0; k < TIERS.length; k++) if (g.warmth >= TIERS[k].min) return TIERS[k];
  }
  // Closest first: most recent common ancestor, then fewest links.
  function compare(a, b) {
    if (a.isTarget !== b.isTarget) return a.isTarget ? -1 : 1;
    return a.age - b.age || a.links - b.links || a.n - b.n;
  }

  // --- rendering -----------------------------------------------------------------
  function nameHtml(i, caret) {
    var c = data.common[i];
    return c ? esc(c) + (caret || '') + '<span class="sci">' + esc(data.sci[i]) + '</span>'
      : '<i>' + esc(data.sci[i]) + '</i>' + (caret || '');
  }
  function rowHtml(g) {
    var t = tier(g), open = openIdx === g.idx;
    return '<tr data-idx="' + g.idx + '" class="clickable heat-' + t.cls + (g.isTarget ? ' target' : '') + '">' +
      '<td class="num">' + (g.explore ? '' : g.n) + '</td>' +
      '<td class="name">' + nameHtml(g.idx, ' <span class="caret" aria-hidden="true">' + (open ? '▾' : '▸') + '</span>') + '</td>' +
      '<td class="grp">' + (g.isTarget ? '' : esc(g.group || '')) + '</td>' +
      '<td class="num"><span class="links ' + t.cls + '">' + (g.isTarget ? data.emoji : g.links) + '</span></td>' +
      '<td class="num age">' + (g.isTarget ? '' : F.formatAge(g.age)) + '</td>' +
      '<td><span class="temp ' + t.cls + '"><span class="bar"><span style="width:' + (g.isTarget ? 100 : g.warmth.toFixed(0)) +
      '%"></span></span><span class="label">' + t.label + '</span></span></td></tr>';
  }
  function detailHtml(g) {
    var i = g.idx, bits = [];
    if (g.isTarget) {
      bits.push('This is the mystery ' + esc(data.noun) + '.');
    } else {
      bits.push('Last common ancestor with the mystery ' + esc(data.noun) + ': <b>' + F.formatAgeLong(g.age) +
        ' ago</b>, ' + g.links + ' branch point' + (g.links === 1 ? '' : 's') + ' apart on the tree.');
      if (g.shared.length) bits.push('Both are in: ' + g.shared.map(function (l) { return esc(l.name); }).join(' › '));
    }
    var mine = game.lineage(i), cut = g.isTarget ? mine.length : mine.length - g.shared.length;
    if (cut > 0) bits.push(esc(game.label(i)) + ': ' + mine.slice(0, cut).map(function (l) { return esc(l.name); }).join(' › '));
    bits.push('<a href="' + wikiUrl(i) + '" target="_blank" rel="noopener">Wikipedia ↗</a>');
    return '<tr class="detail"><td></td><td colspan="5">' + bits.map(function (b) { return '<div>' + b + '</div>'; }).join('') + '</td></tr>';
  }
  function wikiUrl(i) {
    var e = data.extra[i];
    if (e && e.wp) return 'https://en.wikipedia.org/wiki/' + encodeURIComponent(e.wp.replace(/ /g, '_'));
    return 'https://en.wikipedia.org/wiki/Special:Search?search=' + encodeURIComponent(data.sci[i]);
  }

  function render() {
    var all = state.guesses.concat(state.explore);
    $('guesses').hidden = all.length === 0;
    var last = all.filter(function (g) { return g.idx === latest; })[0];
    $('latest').innerHTML = last && all.length > 1 ? rowHtml(last) : '';
    $('sorted').innerHTML = state.guesses.slice().sort(compare).map(rowHtml).join('');
    $('explore').innerHTML = state.explore.length ? '<tr class="explore-head"><td colspan="6">After the game <span>(not counted)</span></td></tr>' +
      state.explore.slice().sort(compare).map(rowHtml).join('') : '';
    if (openIdx != null) {
      var row = $('guesses').querySelector('#sorted tr[data-idx="' + openIdx + '"], #explore tr[data-idx="' + openIdx + '"]');
      var g = all.filter(function (x) { return x.idx === openIdx; })[0];
      if (row && g) row.insertAdjacentHTML('afterend', detailHtml(g));
    }
    var done = over();
    $('guess-input').disabled = false; $('guess-btn').disabled = false;
    $('guess-input').placeholder = done ? 'Look up any ' + data.noun : 'Name a ' + data.noun + ' (common or scientific name)';
    $('guess-btn').textContent = done ? 'Look up' : 'Guess';
    $('giveup-btn').hidden = done || !state.guesses.length;
    $('hint-btn').hidden = done || state.hints >= MAX_HINTS;
    $('hint-btn').textContent = 'Hint (' + (MAX_HINTS - state.hints) + ' left)';
    $('reveal-btn').hidden = !done;
    $('practice-btn').hidden = !practice;
    $('puzzle-meta').textContent = (practice ? 'Practice' : 'Puzzle #' + puzzle) +
      (state.guesses.length ? ' · ' + state.guesses.length + ' guess' + (state.guesses.length === 1 ? '' : 'es') : '');
    renderHints();
  }

  function hintText(k) {
    var labels = data.hintRanks || ['Group', 'Family', 'Genus'];
    var nh = data.hints.length;
    if (k <= nh) {
      var h = game.hint(target, k);
      return (labels[k] || 'Genus') + ': ' + (h ? (k === nh ? '<i>' + esc(h) + '</i>' : esc(h)) : 'unknown');
    }
    var c = data.common[target];
    return c ? 'Common name starts with “' + esc(c[0]) + '” (' + c.split(' ').length + ' word' + (c.split(' ').length === 1 ? '' : 's') + ')'
      : 'Species: <i>' + esc(data.sci[target].replace(/ (\S)\S*$/, ' $1…')) + '</i>';
  }
  function renderHints() {
    var n = over() ? 0 : state.hints;
    $('hints').hidden = n === 0;
    var out = [];
    for (var k = 0; k < n; k++) out.push('<li>' + hintText(k) + '</li>');
    $('hints').innerHTML = out.join('');
  }

  // --- guessing --------------------------------------------------------------------
  function guess(i) {
    hideSuggest();
    $('guess-input').value = '';
    var all = state.guesses.concat(state.explore);
    if (all.some(function (g) { return g.idx === i; })) {
      latest = i; render(); setMessage('Already there: ' + game.label(i) + '.');
      return;
    }
    if (over()) {
      var r = score(i, 0); r.explore = true; state.explore.push(r);
      latest = i; save(); render(); setMessage('Looked up ' + game.label(i) + ' (not counted).');
      return;
    }
    var g = score(i, state.guesses.length + 1);
    state.guesses.push(g);
    latest = i;
    if (g.isTarget) {
      state.solved = true; recordStats(); save(); render();
      setMessage('You got it in ' + state.guesses.length + '!');
      showResult();
    } else {
      save(); render();
      setMessage(game.label(i) + ': ' + g.links + ' link' + (g.links === 1 ? '' : 's') + ', split ' +
        F.formatAgeLong(g.age) + ' ago' + (g.group ? ' (both in ' + g.group + ')' : '') + '.');
    }
  }

  function updateSuggest() {
    var q = $('guess-input').value;
    suggest = q.trim().length >= 2 ? game.search(q, 8) : [];
    active = 0;
    var box = $('suggest');
    if (!suggest.length) { hideSuggest(); return; }
    box.innerHTML = suggest.map(function (i, k) {
      return '<li role="option" data-idx="' + i + '" class="' + (k === active ? 'active' : '') + '">' +
        nameHtml(i) + '</li>';
    }).join('');
    box.hidden = false;
  }
  function hideSuggest() { $('suggest').hidden = true; suggest = []; }
  function highlight() {
    Array.prototype.forEach.call($('suggest').children, function (li, k) { li.className = k === active ? 'active' : ''; });
  }

  $('guess-input').addEventListener('input', updateSuggest);
  $('guess-input').addEventListener('keydown', function (e) {
    if ($('suggest').hidden) return;
    if (e.key === 'ArrowDown') { active = Math.min(active + 1, suggest.length - 1); highlight(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); highlight(); e.preventDefault(); }
    else if (e.key === 'Escape') hideSuggest();
  });
  $('suggest').addEventListener('mousedown', function (e) {
    var li = e.target.closest('li');
    if (li) { e.preventDefault(); guess(+li.dataset.idx); }
  });
  $('guess-form').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = $('guess-input').value;
    if (!q.trim()) return;
    var hits = suggest.length ? suggest : game.search(q, 8);
    if (!hits.length) { setMessage('No ' + data.noun + ' matches “' + q + '”.', true); return; }
    guess(hits[Math.min(active, hits.length - 1)]);
  });
  $('guesses').addEventListener('click', function (e) {
    var tr = e.target.closest('tr[data-idx]');
    if (!tr || e.target.closest('a')) return;
    var i = +tr.dataset.idx;
    openIdx = openIdx === i ? null : i;
    render();
  });
  $('hint-btn').addEventListener('click', function () {
    if (state.hints >= MAX_HINTS) return;
    if (!confirm('Reveal a hint? Hints are shown in your shared result.')) return;
    state.hints++; save(); render();
  });
  $('giveup-btn').addEventListener('click', function () {
    if (!confirm('Give up and see the answer?')) return;
    state.gaveUp = true; recordStats(); save(); render(); showResult();
  });
  $('reveal-btn').addEventListener('click', showResult);
  $('practice-btn').addEventListener('click', function () {
    target = randomTarget();
    state = { guesses: [], explore: [], solved: false, gaveUp: false, hints: 0 };
    latest = openIdx = null; setMessage('New mystery ' + data.noun + '. Good luck!'); render();
  });

  // --- result dialog ---------------------------------------------------------------
  function shareText() {
    var sorted = state.guesses.slice().sort(function (a, b) { return a.n - b.n; });
    var squares = sorted.map(function (g) { return tier(g).sq; });
    var line = squares.length > 30 ? squares.slice(0, 14).join('') + '…' + squares.slice(-15).join('') : squares.join('');
    var best = state.guesses.filter(function (g) { return !g.isTarget; }).sort(compare)[0];
    return 'Faunadle ' + data.emoji + ' ' + data.title + ' #' + puzzle + '\n' +
      (state.solved ? 'Solved in ' + state.guesses.length : 'Gave up after ' + state.guesses.length) +
      (state.hints ? ' · ' + state.hints + ' hint' + (state.hints === 1 ? '' : 's') : '') +
      (!state.solved && best ? ' · closest ' + F.formatAge(best.age) + ' yrs' : '') + '\n' +
      line + (config.siteUrl ? '\n' + config.siteUrl + '/' + gameId + '/' : '');
  }
  function statsHtml() {
    var st = fetchKey('stats');
    if (!st || practice) return '';
    var tiles = [['Played', st.played], ['Win %', st.played ? Math.round(100 * st.won / st.played) : 0],
      ['Streak', st.streak], ['Best', st.best]];
    var max = 1;
    Object.keys(st.dist).forEach(function (k) { max = Math.max(max, st.dist[k]); });
    var mine = state.solved ? bucket(state.guesses.length) : null;
    return '<div class="stats"><h3>Your ' + esc(data.title) + ' stats</h3><div class="stat-tiles">' +
      tiles.map(function (t) { return '<div class="tile"><b>' + t[1] + '</b><span>' + t[0] + '</span></div>'; }).join('') +
      '</div><div class="dist"><span class="dist-title">Guesses to solve</span>' +
      ['1–5', '6–10', '11–20', '21–40', '41+'].map(function (b) {
        var v = st.dist[b] || 0;
        return '<div class="dist-row"><span class="dist-label">' + b + '</span><span class="dist-bar' + (b === mine ? ' mine' : '') +
          '" style="width:' + Math.max(8, 100 * v / max) + '%">' + v + '</span></div>';
      }).join('') + '</div></div>';
  }
  function showResult() {
    var e = data.extra[target] || {};
    var img = e.img ? '<img class="photo" alt="" loading="lazy" src="https://commons.wikimedia.org/wiki/Special:FilePath/' +
      encodeURIComponent(e.img) + '?width=480">' +
      '<p class="attribution">Photo: <a href="https://commons.wikimedia.org/wiki/File:' + encodeURIComponent(e.img) +
      '" target="_blank" rel="noopener">Wikimedia Commons</a> (see page for author and license)</p>' : '';
    var lin = game.lineage(target).slice(0, 4).map(function (l) { return esc(l.name); }).join(' › ');
    var links = ['<a href="' + wikiUrl(target) + '" target="_blank" rel="noopener">Wikipedia</a>'];
    if (e.ebird) links.push('<a href="https://ebird.org/species/' + encodeURIComponent(e.ebird) +
      '" target="_blank" rel="noopener">eBird</a>');
    if (e.q) links.push('<a href="https://www.wikidata.org/wiki/' + e.q + '" target="_blank" rel="noopener">Wikidata</a>');
    $('result-body').innerHTML =
      '<h2>' + (state.solved ? 'You found it!' : 'The mystery ' + esc(data.noun) + ' was') + '</h2>' +
      '<p class="animal">' + esc(game.label(target)) + '</p>' +
      (data.common[target] ? '<p class="sci-line"><i>' + esc(data.sci[target]) + '</i></p>' : '') +
      (lin ? '<p class="crew">' + lin + '</p>' : '') + img +
      '<p class="offers">' + links.join(' ') + '</p>' +
      (practice ? '' : '<div class="share-row"><button id="share-btn" type="button">Share result</button>' +
        '<span id="share-note" class="attribution"></span></div>') + statsHtml();
    var sb = $('share-btn');
    if (sb) sb.addEventListener('click', function () {
      var text = shareText();
      var done = function () { $('share-note').textContent = 'Copied to clipboard.'; };
      if (navigator.share && /Mobi|Android/i.test(navigator.userAgent)) navigator.share({ text: text }).catch(function () {});
      else if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { prompt('Copy your result:', text); });
      else prompt('Copy your result:', text);
    });
    $('result-dialog').showModal();
  }

  // --- start -----------------------------------------------------------------------
  document.title = 'Faunadle · ' + data.title;
  $('title').textContent = data.title;
  $('game-emoji').textContent = data.emoji;
  $('species-count').textContent = data.n.toLocaleString();
  $('noun').textContent = data.noun;
  $('credits-note').innerHTML = data.credits.map(esc).join('<br>') + '<br>Data built ' + esc(data.built) + '.';
  restore();
  setMessage(over() ? (state.solved ? 'Solved! Keep exploring: look-ups now don’t count.' : 'You gave up. Keep exploring if you like.')
    : 'Guess any ' + data.noun + '. Closer relatives score lower.');
  render();
  $('guess-input').focus();
})();
