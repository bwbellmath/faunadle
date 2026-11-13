// Faunadle configuration.
window.FAUNADLE_CONFIG = Object.assign({
  // Day #1 of every game's puzzle sequence. Changing it shifts all future puzzles.
  epoch: '2026-11-13',
  // Public address used in shared results (switch to https://faunadle.com once it's set up).
  siteUrl: 'https://faunadle-bwb.web.app',
  contact: '',
  maxHints: 4,

  // Home page. `id` must match a built data file (data/<id>.js) to be playable.
  games: [
    { id: 'birds', emoji: '🐦', title: 'Birds of the World', blurb: 'All ~11,000 bird species.' },
    { id: 'na-birds', emoji: '🦅', title: 'North American Birds', blurb: 'Birds of the US and Canada.' },
    { id: 'lizards', emoji: '🦎', title: 'Lizards', blurb: 'Geckos, skinks, iguanas, chameleons, monitors…' },
    { id: 'animals', emoji: '🌍', title: 'All Animals', soon: true },
    { id: 'mammals', emoji: '🦊', title: 'Mammals', soon: true },
    { id: 'reptiles', emoji: '🐊', title: 'Reptiles', soon: true },
    { id: 'fish', emoji: '🐟', title: 'Fish', soon: true },
    { id: 'insects', emoji: '🦋', title: 'Insects', soon: true },
  ],
}, window.FAUNADLE_CONFIG || {});
