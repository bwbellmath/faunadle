"""Common names, popularity (sitelink counts), images and Wikipedia articles from Wikidata
(CC0), matched on the Open Tree of Life ID property (P9157). Cached across games."""
import json
import os
import time
import urllib.parse
import urllib.request

import opentree

ENDPOINT = "https://query.wikidata.org/sparql"
UA = "faunadle-build/0.1 (daily taxonomy game; data build script)"
CACHE = os.path.join(opentree.CACHE, "wikidata.json")
BATCH = 300

QUERY = """
SELECT ?ott ?item ?label ?common ?links ?image ?article WHERE {
  VALUES ?ott { %s }
  ?item wdt:P9157 ?ott ; wikibase:sitelinks ?links .
  OPTIONAL { ?item rdfs:label ?label FILTER(lang(?label) = "en") }
  OPTIONAL { ?item wdt:P1843 ?common FILTER(lang(?common) = "en") }
  OPTIONAL { ?item wdt:P18 ?image }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }
}"""


def _load():
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            return json.load(f)
    return {}


def _query(ids):
    q = QUERY % " ".join('"%d"' % i for i in ids)
    body = urllib.parse.urlencode({"query": q}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Accept": "application/sparql-results+json", "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["results"]["bindings"]
        except Exception as e:  # rate limits / timeouts: back off and retry
            wait = 5 * (attempt + 1)
            print("  wikidata: %s; retrying in %ds" % (e, wait), flush=True)
            time.sleep(wait)
    raise RuntimeError("Wikidata query kept failing")


def lookup(ott_ids):
    """{ott_id: {"q", "label", "common": [..], "links", "image", "article"}} (missing ids
    have no Wikidata item with that OTT id)."""
    cache = _load()
    todo = sorted({int(i) for i in ott_ids if str(i) not in cache})
    for k in range(0, len(todo), BATCH):
        chunk = todo[k:k + BATCH]
        rows = _query(chunk)
        got = {}
        for b in rows:
            o = b["ott"]["value"]
            links = int(b["links"]["value"])
            e = got.get(o)
            # Several items can share an OTT id; keep the best-linked one.
            if e is None or links > e["links"]:
                e = got[o] = {"q": b["item"]["value"].rsplit("/", 1)[-1], "links": links,
                              "label": None, "common": [], "image": None, "article": None}
            if e["q"] != b["item"]["value"].rsplit("/", 1)[-1]:
                continue
            if "label" in b:
                e["label"] = b["label"]["value"]
            if "common" in b and b["common"]["value"] not in e["common"]:
                e["common"].append(b["common"]["value"])
            if "image" in b and not e["image"]:
                e["image"] = urllib.parse.unquote(b["image"]["value"].rsplit("/", 1)[-1])
            if "article" in b:
                e["article"] = urllib.parse.unquote(b["article"]["value"].rsplit("/", 1)[-1])
        for i in chunk:
            cache[str(i)] = got.get(str(i))
        print("  wikidata: %d/%d" % (min(k + BATCH, len(todo)), len(todo)), flush=True)
        with open(CACHE, "w") as f:
            json.dump(cache, f)
        time.sleep(1)
    return {int(i): cache.get(str(int(i))) for i in ott_ids}
