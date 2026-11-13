#!/usr/bin/env python3
"""Write dist/<game>/index.html for each game from site/game.html, with the game's own
title and link-preview tags (so a shared /lizards/ link unfurls as "Faunadle · Lizards")."""
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = "https://faunadle-bwb.web.app"


def meta(game):
    with open(os.path.join(ROOT, "data", "games", game + ".js"), encoding="utf-8") as f:
        line = f.read().splitlines()[-1]
    return json.loads(line[line.index("] = ") + 4:].rstrip(";"))


def main(dist, games):
    with open(os.path.join(ROOT, "site", "game.html"), encoding="utf-8") as f:
        tpl = f.read()
    for g in games:
        d = meta(g)
        title = "Faunadle · " + d["title"]
        desc = ("A daily %s-guessing game scored on the tree of life: %s species, each guess "
                "scored by branch points and millions of years to the mystery %s."
                % (d["noun"], "{:,}".format(d["n"]), d["noun"]))
        tags = ('<title>%s</title>\n  <meta name="description" content="%s">\n'
                '  <meta property="og:title" content="%s">\n'
                '  <meta property="og:description" content="%s">\n'
                '  <meta property="og:url" content="%s/%s/">\n'
                '  <meta property="og:type" content="website">\n'
                '  <meta name="twitter:card" content="summary">'
                % (html.escape(title), html.escape(desc), html.escape(title), html.escape(desc),
                   SITE_URL, g))
        page = tpl.replace("__GAME__", g)
        start, end = page.index("<title>"), page.index('<link rel="stylesheet"')
        page = page[:start] + tags + "\n  " + page[end:]
        os.makedirs(os.path.join(dist, g), exist_ok=True)
        with open(os.path.join(dist, g, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
