#!/bin/sh
# Fetch the raw inputs for pipeline/build.py into data/raw/ (~1.2 GB unpacked).
set -eu
cd "$(dirname "$0")/../data" && mkdir -p raw && cd raw

# Open Tree of Life synthetic tree (the backbone for every game) and OTT taxonomy.
mkdir -p opentree && cd opentree
[ -d opentree16.1_tree ] || curl -fL https://files.opentreeoflife.org/synthesis/opentree16.1/opentree16.1_tree.tgz | tar xz
[ -d ott3.7.3 ] || curl -fL https://files.opentreeoflife.org/ott/ott3.7.3/ott3.7.3.tgz | tar xz
cd ..

# Birds: AvesData (McTavish et al. 2025, CC BY 4.0): dated tree + Clements/OTT crosswalk.
mkdir -p aves
AVES=https://raw.githubusercontent.com/McTavishLab/AvesData/main
[ -f aves/summary_dated_clements.nex ] || curl -fL -o aves/summary_dated_clements.nex $AVES/Tree_versions/Aves_1.7/Clements2025/summary_dated_clements.nex
[ -f aves/OTT_crosswalk_2025.csv ] || curl -fL -o aves/OTT_crosswalk_2025.csv $AVES/Taxonomy_versions/Clements2025/OTT_crosswalk_2025.csv

# North American birds: GBIF occurrence counts per species, US + Canada.
mkdir -p gbif
[ -f gbif/na_aves_counts.json ] || curl -fL -o gbif/na_aves_counts.json \
  "https://api.gbif.org/v1/occurrence/search?country=US&country=CA&taxonKey=212&facet=speciesKey&facetLimit=20000&limit=0"

# Squamates: Tonini et al. 2016 posterior (VertLife). Only the first of the ten 1000-tree
# files is needed; it is the first member of the zip, so fetch just its bytes.
mkdir -p squamata
if [ ! -f squamata/posterior_1000.trees ]; then
  curl -fL -r 0-188222211 -o squamata/part1.bin \
    https://storage.googleapis.com/data.vertlife.org/squamatetree/squam_shl_new_Posterior_9755.1000-10000.trees.zip
  python3 -I -c '
import struct, sys, zlib
f = open(sys.argv[1], "rb"); h = f.read(30); n, e = struct.unpack("<HH", h[26:30]); f.read(n + e)
d = zlib.decompressobj(-15); out = open(sys.argv[2], "wb")
for b in iter(lambda: f.read(1 << 20), b""): out.write(d.decompress(b))
out.write(d.flush())' squamata/part1.bin squamata/posterior_1000.trees
  rm squamata/part1.bin
fi
echo "raw data ready in data/raw/"
