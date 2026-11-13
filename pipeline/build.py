#!/usr/bin/env python3
"""Build the data file for one or more Faunadle games.

    python3 pipeline/build.py [birds] [na-birds] [lizards]     (default: all)

Every game is cut from the same Open Tree of Life synthetic tree (the backbone): its
clade(s) are pruned to the game's species, and divergence dates are overlaid from
dated trees for that group. Output: data/games/<id>.js (window.FAUNADLE_DATA[id]).
"""
import csv
import datetime
import json
import os
import random
import re
import sys

import gametree
import newick
import opentree
import wikidata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "games")
POOLS = os.path.join(ROOT, "data", "pools")

AVES, SQUAMATA, SERPENTES, AMPHISBAENIA = 81461, 35888, 186816, 690599

OTT_CREDIT = ("Phylogeny: Open Tree of Life synthesis %s (https://tree.opentreeoflife.org), "
              "taxonomy %s." % (opentree.SYNTH_VERSION, opentree.OTT_VERSION))
WD_CREDIT = "Names, images and links: Wikidata (CC0) and Wikimedia Commons."


# --- shared helpers -----------------------------------------------------------------

def sig(x):
    """Round an age (Myr) for the data file: 3 significant figures."""
    if x <= 0:
        return 0
    return float("%.3g" % x)


def nice_group(tax, wd, o):
    """Display name for a taxon: 'Fringillidae (finches)' when Wikidata has an English
    name that differs from the scientific one."""
    name = tax.get(o, {}).get("name") or str(o)
    w = wd.get(o) or {}
    common = (w.get("label") or "").strip()
    if common and common.lower() != name.lower():
        return "%s (%s)" % (name, common)
    return name


def frozen_pool(game_id, candidates, key):
    """Daily target order. Kept in data/pools/<id>.json so rebuilding the data never
    reshuffles puzzles already played: existing entries keep their place (if still
    present), new candidates are shuffled onto the end."""
    os.makedirs(POOLS, exist_ok=True)
    path = os.path.join(POOLS, game_id + ".json")
    by_key = {key(c): c for c in candidates}
    order = []
    if os.path.exists(path):
        with open(path) as f:
            order = [k for k in json.load(f) if k in by_key]
    new = sorted(k for k in by_key if k not in set(order))
    random.Random("faunadle:" + game_id).shuffle(new)
    order += new
    with open(path, "w") as f:
        json.dump(order, f, indent=0)
    return [by_key[k] for k in order]


# Taxonomic ranks used for "shared group" answers and the group hints.
GROUP_RANKS = {"genus", "subtribe", "tribe", "subfamily", "family", "superfamily", "parvorder",
               "infraorder", "suborder", "order", "superorder", "infraclass", "subclass", "class"}


def write_game(meta, g, tip_info, pool, tax, root_ott, hint_ranks, rename=None):
    """Serialize a game to data/games/<id>.js.

    tip_info[i] = dict(common, sci, pop, extra, alt). Taxonomic groups (genus, family,
    order... from the OTT taxonomy, up to root_ott) form a small tree of their own:
    groups[k] (display name), groupParent[k], and tipGroup[i] (the tip's lowest group).
    The smallest group shared by two species is their LCA in that tree. hint_ranks lists,
    per hint, the ranks to look for (first match in the tip's lineage)."""
    os.makedirs(OUT, exist_ok=True)
    n = g.n
    chains = []
    ids = set()
    for o in g.tips:
        ch = [a for a in opentree.lineage(tax, o)
              if tax[a]["rank"] in GROUP_RANKS or a == root_ott]
        if root_ott in ch:
            ch = ch[:ch.index(root_ott) + 1]
        chains.append(ch)
        ids.update(ch)
    wd = wikidata.lookup(ids)
    gidx, gparent, gnames = {}, [], []
    for ch in chains:  # top-down so parents get indexes first
        prev = -1
        for a in reversed(ch):
            if a not in gidx:
                gidx[a] = len(gnames)
                gparent.append(prev)
                gnames.append((rename and rename(a)) or nice_group(tax, wd, a))
            prev = gidx[a]

    def hint(ch, ranks):
        for a in ch:
            if tax[a]["rank"] in ranks:
                return gidx[a]
        return -1

    data = dict(meta)
    data.update({
        "built": datetime.date.today().isoformat(),
        "n": n,
        "common": [t["common"] or "" for t in tip_info],
        "sci": [t["sci"] for t in tip_info],
        "pop": [t["pop"] for t in tip_info],
        "parent": g.parent,
        "age": [sig(a) for a in g.age[n:]],
        "groups": gnames,
        "groupParent": gparent,
        "tipGroup": [gidx[ch[0]] if ch else -1 for ch in chains],
        "hints": [[hint(ch, r) for ch in chains] for r in hint_ranks],
        "pool": pool,
        "extra": {str(i): tip_info[i]["extra"] for i in range(n) if tip_info[i].get("extra")},
        "alt": {str(i): tip_info[i]["alt"] for i in range(n) if tip_info[i].get("alt")},
    })
    path = os.path.join(OUT, meta["id"] + ".js")
    with open(path, "w") as f:
        f.write("// Built by pipeline/build.py. Do not edit.\n")
        f.write("window.FAUNADLE_DATA = window.FAUNADLE_DATA || {};\n")
        f.write("window.FAUNADLE_DATA[%s] = " % json.dumps(meta["id"]))
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        f.write(";\n")
    print("wrote %s: %d species, %d nodes, %d groups, pool %d, %.0f KB" % (
        os.path.relpath(path, ROOT), n, len(g.parent), len(gnames), len(pool),
        os.path.getsize(path) / 1024))


def extra_info(w):
    if not w:
        return None
    e = {"q": w["q"]}
    if w.get("article"):
        e["wp"] = w["article"]
    if w.get("image"):
        e["img"] = w["image"]
    return e


# --- birds ----------------------------------------------------------------------------

def clements():
    """Clements/eBird 2025 species rows keyed by OTT id (from the AvesData crosswalk)."""
    rows = {}
    with open(os.path.join(RAW, "aves", "OTT_crosswalk_2025.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["CATEGORY"] != "species" or not r["ott_id"] or r["ott_id"] == "NA":
                continue
            o = int(float(r["ott_id"]))
            m = re.search(r"gbif:(\d+)", r["ott_tax_sources"] or "")
            rows.setdefault(o, {
                "common": r["PRIMARY_COM_NAME"], "sci": r["sci_name_2025"] or r["SCI_NAME"],
                "order": r["ORDER"], "family": r["FAMILY"], "code": r["SPECIES_CODE"],
                "gbif": int(m.group(1)) if m else None, "taxon_order": float(r["TAXON_ORDER"]),
            })
    return rows


_birds = None


def bird_tree():
    """The full bird game tree (Open Tree Aves, Clements species), dated by AvesData."""
    global _birds
    if _birds:
        return _birds
    cl = clements()
    print("birds: Clements species with OTT ids: %d" % len(cl), flush=True)
    t = opentree.clade(AVES)
    g = gametree.from_clades([t], lambda o: o in cl)
    print("birds: %d species in the Open Tree, %d nodes" % (g.n, len(g.parent)), flush=True)
    tip_by_sci = {cl[o]["sci"].replace(" ", "_"): i for i, o in enumerate(g.tips)}
    dated = [newick.parse(nwk) for nwk, _ in newick.read_trees(
        os.path.join(RAW, "aves", "summary_dated_clements.nex"), limit=1)]
    d, interp, matched = gametree.date(g, dated, tip_by_sci.get)
    print("birds: dated %d nodes, interpolated %d; %d/%d tips in the dated tree; root %.1f Myr"
          % (d, interp, matched, g.n, max(g.age)), flush=True)
    node_otts = {o for names in g.names for o in names}
    tax = opentree.taxa(node_otts | set(g.tips), "aves", stop=AVES)
    wd = wikidata.lookup(set(g.tips) | node_otts)
    _birds = (g, cl, tax, wd)
    return _birds


def bird_tip_info(g, cl, wd, pop=None):
    out = []
    for o in g.tips:
        c = cl[o]
        w = wd.get(o) or {}
        out.append({
            "common": c["common"], "sci": c["sci"],
            "pop": pop(o) if pop else (w.get("links") or 0),
            "extra": None,
        })
    return out


def clements_names(cl, tax):
    """Display names for bird groups: Clements family names ('Turdidae (Thrushes and
    Allies)') where the OTT family matches; otherwise the default."""
    fam = {}
    for c in cl.values():
        fam.setdefault(c["family"].split(" (")[0], c["family"])
    return lambda o: fam.get(tax[o]["name"]) if tax[o]["rank"] == "family" else None


def bird_extra(cl, wd, o):
    e = extra_info(wd.get(o)) or {}
    e["ebird"] = cl[o]["code"]
    return e


BIRD_HINTS = [("order",), ("family",)]

BIRD_META = {
    "kind": "birds", "noun": "bird", "emoji": "🐦",
    "hintRanks": ["Order", "Family", "Genus"],
}


def build_birds():
    g, cl, tax, wd = bird_tree()
    info = bird_tip_info(g, cl, wd)
    # Daily pool: the best-known species (most Wikipedia language editions).
    ranked = sorted(range(g.n), key=lambda i: -info[i]["pop"])
    cand = [i for i in ranked if info[i]["pop"] >= 25][:1500]
    pool = [i for i in frozen_pool("birds", cand, key=lambda i: g.tips[i])]
    for i in pool:
        info[i]["extra"] = bird_extra(cl, wd, g.tips[i])
    meta = dict(BIRD_META, id="birds", title="Birds of the World",
                blurb="Every one of the world's ~11,000 bird species.",
                credits=[OTT_CREDIT,
                         "Bird names and dates: McTavish et al. 2025, AvesData Aves 1.7 / "
                         "Clements-eBird 2025 (CC BY 4.0).", WD_CREDIT])
    write_game(meta, g, info, pool, tax, AVES, BIRD_HINTS, clements_names(cl, tax))


def build_na_birds():
    g, cl, tax, wd = bird_tree()
    with open(os.path.join(RAW, "gbif", "na_aves_counts.json")) as f:
        counts = {int(c["name"]): c["count"] for c in json.load(f)["facets"][0]["counts"]}
    # GBIF ids: from Clements' crosswalk, else from the OTT taxonomy.
    def n_obs(o):
        gid = cl[o]["gbif"] or (tax.get(o) or {}).get("gbif")
        return counts.get(gid, 0)
    keep = [i for i, o in enumerate(g.tips) if n_obs(o) >= 100]
    h, src = gametree.prune(g, set(keep).__contains__)
    print("na-birds: %d species with >= 100 GBIF records in the US and Canada" % h.n)
    info = bird_tip_info(h, cl, wd, pop=n_obs)
    ranked = sorted(range(h.n), key=lambda i: -info[i]["pop"])
    cand = ranked[:500]  # the 500 most-reported species
    pool = frozen_pool("na-birds", cand, key=lambda i: h.tips[i])
    for i in pool:
        info[i]["extra"] = bird_extra(cl, wd, h.tips[i])
    meta = dict(BIRD_META, id="na-birds", title="North American Birds",
                blurb="Birds of the US and Canada.",
                popNote="GBIF records in the US and Canada",
                credits=[OTT_CREDIT,
                         "Bird names and dates: McTavish et al. 2025, AvesData Aves 1.7 / "
                         "Clements-eBird 2025 (CC BY 4.0).",
                         "Species list: GBIF.org occurrence records for the US and Canada "
                         "(mostly eBird), at least 100 per species.", WD_CREDIT])
    write_game(meta, h, info, pool, tax, AVES, BIRD_HINTS, clements_names(cl, tax))


# --- lizards ----------------------------------------------------------------------------

def looks_scientific(label, names):
    """Wikidata labels are often just the binomial (sometimes an older synonym)."""
    if label.replace(" ", "_") in names:
        return True
    # "Genus epithet" (or "Genus (Subgenus) epithet") where Genus is a known genus name.
    m = re.match(r"^([A-Z][a-z]+)( \([A-Z][a-z]+\))? ([a-z-]+)( [a-z-]+)?$", label)
    return bool(m) and (m.group(1) in GENERA or bool(re.search(
        r"(us|um|is|ae|i|ensis|oides|atus|ata|alis|ii|ae)$", m.group(3))))


GENERA = set()


def title_case(name):
    """'milos wall lizard' -> 'Milos Wall Lizard'; hyphenated parts after the first stay
    lower case, as in bird names ('Black-green Smooth-throated Lizard')."""
    def word(w):
        parts = w.split("-")
        return "-".join([parts[0][:1].upper() + parts[0][1:]] +
                        [p[:1].lower() + p[1:] for p in parts[1:]])
    return " ".join(word(w) for w in name.split(" "))

def build_lizards():
    t = opentree.clade(SQUAMATA)
    all_otts = {opentree.ott_id(l) for l in t.label} - {None}
    tax = opentree.taxa(all_otts, "squamata", stop=SQUAMATA)

    def is_species(o):
        r = tax.get(o)
        return bool(r) and r["rank"] == "species" and not any(
            "extinct" in f for f in r["flags"])

    g = gametree.from_clades([t], is_species, exclude=(SERPENTES, AMPHISBAENIA))
    print("lizards: %d extant species, %d nodes" % (g.n, len(g.parent)), flush=True)

    # Dated trees: Tonini et al. 2016 squamate posterior (100 of the 1000 samples).
    tip_of = {o: i for i, o in enumerate(g.tips)}
    GENERA.update(r["name"] for r in tax.values() if r["rank"] == "genus")
    names = {}
    for o in tip_of:
        names[tax[o]["name"].replace(" ", "_")] = o
    for s, o in opentree.synonyms(set(tip_of), "squamata").items():
        names.setdefault(s.replace(" ", "_"), o)
    trees = []
    for k, (nwk, _) in enumerate(newick.read_trees(
            os.path.join(RAW, "squamata", "posterior_1000.trees"))):
        if k % 10 == 0:
            trees.append(newick.parse(nwk))
    d, interp, matched = gametree.date(g, trees, lambda lab: tip_of.get(names.get(lab)))
    print("lizards: dated %d nodes, interpolated %d; %d/%d tips matched; root %.1f Myr"
          % (d, interp, matched, g.n, max(g.age)), flush=True)

    node_otts = {o for ns in g.names for o in ns}
    wd = wikidata.lookup(set(g.tips) | node_otts)
    info = []
    for o in g.tips:
        r = tax[o]
        w = wd.get(o) or {}
        common = None
        # English Wikipedia's title is usually the best-known name; then the item label,
        # then any listed common name. Scientific-looking ones are skipped.
        article = re.sub(r" \(.*\)$", "", (w.get("article") or "").replace("_", " "))
        # Wikidata lists common names in no particular order; the shortest is usually the
        # everyday one ("Green Anole" over "Red-throated Anole"). The rest become aliases.
        listed = sorted({title_case(c.strip()) for c in (w.get("common") or [])
                         if c.strip() and not looks_scientific(c.strip(), names)}, key=len)
        for c in [article, w.get("label")]:
            c = (c or "").strip()
            if c and not looks_scientific(c, names):
                common = title_case(c)
                break
        if not common and listed:
            common = listed[0]
        alt = [c for c in listed if c != common]
        info.append({
            "common": common, "sci": r["name"],
            "pop": w.get("links") or 0, "extra": None, "alt": alt,
        })
    ranked = sorted(range(g.n), key=lambda i: -info[i]["pop"])
    cand = [i for i in ranked if info[i]["common"]][:365]
    pool = frozen_pool("lizards", cand, key=lambda i: g.tips[i])
    for i in pool:
        info[i]["extra"] = extra_info(wd.get(g.tips[i]))
    meta = {"id": "lizards", "kind": "lizards", "noun": "lizard", "emoji": "🦎",
            "title": "Lizards", "blurb": "Geckos, skinks, iguanas, monitors and every other lizard.",
            "hintRanks": ["Group", "Family", "Genus"],
            "credits": [OTT_CREDIT,
                        "Dates: Tonini et al. 2016, squamate tree (VertLife, median of 100 "
                        "posterior trees).", WD_CREDIT]}
    write_game(meta, g, info, pool, tax, SQUAMATA,
               [("infraorder", "suborder", "superfamily"), ("family",)])


GAMES = {"birds": build_birds, "na-birds": build_na_birds, "lizards": build_lizards}


def main():
    want = sys.argv[1:] or list(GAMES)
    for gid in want:
        if gid not in GAMES:
            sys.exit("unknown game %r (have: %s)" % (gid, ", ".join(GAMES)))
        GAMES[gid]()


if __name__ == "__main__":
    main()
