PORT   ?= 8001
PYTHON ?= python3
GAMES   = birds na-birds lizards
SITE    = dist

.PHONY: run site data deploy clean
# Build the site (from committed game data) and serve it locally.
run: site
	@( sleep 1; open http://localhost:$(PORT)/ >/dev/null 2>&1 || true ) &
	$(PYTHON) -m http.server $(PORT) --bind 127.0.0.1 --directory $(SITE)

# dist/: home page, shared assets, data, and one folder per game.
site:
	rm -rf $(SITE)
	mkdir -p $(SITE)/data
	cp -R site/css site/js site/index.html $(SITE)/
	cp data/games/*.js $(SITE)/data/
	$(PYTHON) scripts/pages.py $(SITE) $(GAMES)

# Rebuild game data from the raw downloads (see README for what goes in data/raw/).
data:
	./scripts/download.sh
	$(PYTHON) pipeline/build.py $(GAMES)

# Publish dist/ to Firebase Hosting: https://faunadle-bwb.web.app (site faunadle-bwb in
# project shopbot-gcode-hazard-tester, alongside Kinodle's filmdle-bwb).
deploy: site
	firebase deploy --only hosting:faunadle-bwb

clean:
	rm -rf $(SITE)
