# `make get` fetches the three rooms at the releases this set was checked with; `make test` checks the set itself.
SCRIPTORIUM = v1.1.1
SCRIPTORIUM_SHA = 0162242158b0524d56425ecbed46303d04e178fc
ANTECHAMBER = v1.2.0
ANTECHAMBER_SHA = c2c242d0393ff3874af7dbb8e0ff6607daec3b4f
VAULT_MAP   = v1.4.0
VAULT_MAP_SHA   = b14f7b1383c2add8cc66730cc9bfa23ef5a4b12d

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
