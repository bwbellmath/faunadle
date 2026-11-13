# Faunadle

Daily species-guessing games scored on the tree of life. Each game has a mystery species,
and every guess gets:

- **Links**: branch points on the path between the guess and the mystery species
  (sister species = 1).
- **Diverged**: time since their last common ancestor (`45M`, `6.4M`, `320K` years).
- **Shared group**: the smallest taxon containing both (genus › family › order …).

Guesses are sorted by divergence time, then links. Same family as Kinodle (`../filmdle`):
the same table, heat bar, hints, share text and stats.

## Quick start

```sh
make            # assemble dist/ from the committed game data, serve http://localhost:8001
make data       # download raw inputs (~1.2 GB) and rebuild data/games/*.js
```

Games: `/birds/`, `/na-birds/`, `/lizards/`. Add `?practice` for random targets (nothing
saved). On localhost, `?puzzle=N` plays any puzzle number.

## How the data is built

`pipeline/build.py [game…]` builds each game from one shared backbone:

1. **Backbone tree**: the whole Open Tree of Life synthetic tree (opentree16.1, ~2.4M
   tips). A game takes one or more clades of it (`opentree.clade(ott_id)`, cached in
   `data/cache/`), keeps only its species, and removes single-child nodes
   (`gametree.from_clades`, `gametree.prune` for sub-games like NA Birds).
2. **Dates**: dated trees for the group are mapped onto the backbone. Each backbone
   node gets the median age, across the dated trees, of the MRCA of its descendants
   that the dated tree contains. Nodes no dated tree covers are interpolated
   (`gametree.date`). Adding a new group just means pointing it at a dated tree, and
   any dated tree works whatever its topology.
3. **Groups and hints**: OTT taxonomy ranks (genus … class) form a small group tree.
   "Shared group" is the LCA in it. Open Tree's own node labels are skipped because
   non-monophyletic taxa get `mrca…` labels there.
4. **Names, popularity, photos**: Wikidata, matched on the Open Tree ID (P9157):
   English names, sitelink counts (used for search ranking and the daily pool), Commons
   images and Wikipedia articles.
5. **Daily pool**: well-known species, shuffled once and frozen in `data/pools/<id>.json`,
   so rebuilding the data never changes puzzles already played. New candidates are
   appended at the end.

| Game | Species | Dates | Species list / pool |
|---|---|---|---|
| birds | 11,070 (Clements 2025) | AvesData Aves 1.7 dated MCC tree; every node dated | top 1,500 by Wikidata sitelinks |
| na-birds | 989 | same | ≥100 GBIF records in US+Canada; pool = 500 most-reported |
| lizards | 6,984 extant (Squamata minus Serpentes and Amphisbaenia) | Tonini et al. 2016, median of 100 posterior trees; 85% of tips matched | 365 best-known species with English names |

## Sources and licenses

- Open Tree of Life synthesis 16.1 and OTT 3.7.3 (https://tree.opentreeoflife.org).
- AvesData (McTavish et al. 2025, PNAS), CC BY 4.0: bird tree, dates, Clements/eBird names.
- Tonini et al. 2016 squamate tree, via VertLife (https://vertlife.org).
- GBIF.org occurrence counts (mostly eBird) for the North American species list.
- Wikidata (CC0) and Wikimedia Commons (photos are linked, not copied; per-file licenses).

Check every license before a public launch, especially VertLife's terms. The ABA
Checklist is copyrighted and must not be redistributed, which is why NA Birds uses GBIF.

## Adding a game

Write a `build_<id>()` in `pipeline/build.py`: pick clade OTT ids (and any to exclude),
a tip filter, one or more dated trees with a label → tip matcher, and hint ranks. Then
add it to `GAMES`, to the `GAMES` list in the Makefile, and to `games` in `site/js/config.js`.
