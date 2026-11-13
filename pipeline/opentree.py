"""Open Tree of Life backbone: pull a clade out of the full synthetic tree and look up
its taxa in the OTT taxonomy.

The full tree (opentree16.1 labelled supertree, ~2.4M tips) is the shared backbone for
every game; each game is one or more clades of it, pruned to the species it uses.
"""
import json
import os
import re

import newick

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
CACHE = os.path.join(os.path.dirname(RAW), "cache")
SYNTH_VERSION = "opentree16.1"
OTT_VERSION = "ott3.7.3"
TREE = os.path.join(RAW, "opentree", SYNTH_VERSION + "_tree", "labelled_supertree",
                    "labelled_supertree_ottnames.tre")
TAXONOMY = os.path.join(RAW, "opentree", OTT_VERSION, "taxonomy.tsv")
SYNONYMS = os.path.join(RAW, "opentree", OTT_VERSION, "synonyms.tsv")

_OTT = re.compile(r"(?:^|_)ott(\d+)$")

_full_tree_text = None


def full_tree_text():
    global _full_tree_text
    if _full_tree_text is None:
        with open(TREE) as f:
            _full_tree_text = f.read()
    return _full_tree_text


def ott_id(label):
    """OTT id of a node label like 'Spinus_tristis_ott559260' (None for 'mrcaott1ott2')."""
    if not label or label.startswith("mrcaott"):
        return None
    m = _OTT.search(label)
    return int(m.group(1)) if m else None


def clade(root_ott):
    """Parsed subtree (newick.Tree) of the synthetic tree rooted at taxon `root_ott`.
    Cached as a Newick file per clade."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "clade_ott%d.tre" % root_ott)
    if not os.path.exists(path):
        text = newick.extract_clade(full_tree_text(), "_ott%d" % root_ott)
        with open(path, "w") as f:
            f.write(text + ";\n")
    with open(path) as f:
        return newick.parse(f.read())


def _rows(path, keep):
    """Stream an OTT .tsv ("\t|\t"-separated), yielding split rows where keep(row)."""
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            r = line.rstrip("\n").split("\t|\t")
            if keep(r):
                yield r


def taxa(ids, cache_name, stop=None):
    """{ott_id: {"parent", "name", "rank", "flags", "gbif"}} for `ids` and all their
    ancestors up to `stop` (resolved with repeated streaming passes over taxonomy.tsv).
    Cached."""
    path = os.path.join(CACHE, cache_name + "-taxa.json")
    if os.path.exists(path):
        with open(path) as f:
            got = {int(k): v for k, v in json.load(f).items()}
        if all(i in got for i in ids):
            return got
    got = {}
    want = set(ids)
    while want:
        want_s = {str(i) for i in want}
        for r in _rows(TAXONOMY, lambda r: r[0] in want_s):
            src = r[4]
            m = re.search(r"gbif:(\d+)", src)
            got[int(r[0])] = {
                "parent": int(r[1]) if r[1] else None,
                "name": r[2], "rank": r[3],
                "flags": [x for x in r[6].strip("\t|").split(",") if x] if len(r) > 6 else [],
                "gbif": int(m.group(1)) if m else None,
            }
        want = {v["parent"] for k, v in got.items()
                if v["parent"] and v["parent"] not in got and k != stop}
        print("  taxonomy: %d taxa, %d ancestors to resolve" % (len(got), len(want)), flush=True)
    with open(path, "w") as f:
        json.dump(got, f)
    return got


def synonyms(ids, cache_name):
    """{name: ott_id} of OTT synonyms for the given ids (for matching other trees' names)."""
    path = os.path.join(CACHE, cache_name + "-synonyms.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    want = {str(i) for i in ids}
    out = {}
    for r in _rows(SYNONYMS, lambda r: len(r) > 1 and r[1] in want):
        out.setdefault(r[0], int(r[1]))
    with open(path, "w") as f:
        json.dump(out, f)
    return out


def lineage(tax, i):
    """Ancestors of taxon i (nearest first), excluding i."""
    out = []
    p = tax.get(i, {}).get("parent")
    while p and p in tax:
        out.append(p)
        p = tax[p]["parent"]
    return out


def ancestor_of_rank(tax, i, rank):
    for a in [i] + lineage(tax, i):
        if tax.get(a, {}).get("rank") == rank:
            return a
    return None
