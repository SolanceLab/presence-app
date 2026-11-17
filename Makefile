# `make get` fetches the three rooms at the releases this set was checked with; `make test` checks the set itself.
SCRIPTORIUM = v1.2.2
SCRIPTORIUM_SHA = 37b3db7368cd0a6cd06f68fe56cf48621a2a8f00
ANTECHAMBER = v1.3.0
ANTECHAMBER_SHA = 6dc52a6f15ed089a7d05afc5a587c34c5c040860
VAULT_MAP   = v1.4.2
VAULT_MAP_SHA   = 2167c016c911b199df95acc66faee9636eb641ea

.PHONY: get test bump bump-check bundle
get:
	@mkdir -p rooms
	@for pair in scriptorium:$(SCRIPTORIUM) antechamber:$(ANTECHAMBER) vault-map:$(VAULT_MAP); do \
	  room=$${pair%%:*}; tag=$${pair#*:}; \
	  if [ ! -d rooms/$$room ]; then \
	    git -c advice.detachedHead=false clone -q --depth 1 --branch $$tag https://github.com/SolanceLab/$$room.git rooms/$$room || exit 1; \
	  fi; \
	  have=$$(git -C rooms/$$room describe --tags --exact-match 2>/dev/null); \
	  if [ "$$have" != "$$tag" ]; then \
	    echo "rooms/$$room is at '$${have:-no tag}', not $$tag: delete rooms/$$room and run make get again"; exit 1; \
	  fi; \
	  echo "rooms/$$room at $$tag"; \
	done

test:
	python3 -m unittest discover -s tests -q
bump:
	python3 scripts/bump.py
bump-check:
	python3 scripts/bump.py --check

# `make bundle` (after `make get`) refreshes the Codex plugin from the pinned rooms: their skills, and the exact Antechamber commit.
bundle:
	python3 scripts/bundle.py
