# Updates

Back to the [README](../README.md).

Third-party marketplaces do not auto-update by default. To turn it on once: `/plugin` > Marketplaces > `presence-app` > Enable auto-update. To update by hand: `claude plugin update scriptorium@presence-app` and `claude plugin update antechamber@presence-app`, then restart. The rooms in `rooms/` update when this set moves its pins: `git pull`, then delete `rooms/` and run `make get` again.

On each new session each plugin makes one request for its own public version file on GitHub, at most once a day (once an hour while the request fails), and shows one line when a newer version is out. It sends nothing about you. To switch the check off, set `PLUGIN_UPDATE_CHECK=0`.
