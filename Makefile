# `make get` fetches the three rooms at the releases this set was checked with; `make test` checks the set itself.
SCRIPTORIUM = v1.0.0
ANTECHAMBER = v1.0.0
VAULT_MAP   = v1.3.0

.PHONY: get test
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
