DayZ console mods with Nitrado.

Currently, variables are being created and extracted, to later be substituted with values that are assigned in one config file per map (config.nasdara.yml, config.sakhal.yml). This removes the grueling process of crawling DayZ xml files looking for settings that may or may not have other dependent values that break the game. Certain changes, be it wolf count, or spawn box settings, can silently break the game. 

Example: "INFECTED_GLOBAL_D_MULTIPLIER: 2.0" - This single value applies the multiplier across all of the zombie types respective to their original proportion. 

Example (in spawn category): "MAX_DIST: "400"" - This single value applies across several spawn settings, like max distance to the nearest static object, max distance to the nearest z, max distance to the nearest player, etc.


# How to start:
Set your repo's secrets for "FTP_HOST", "FTP_PASSWORD", and "FTP_USERNAME" to the information provided from Nitrado for your server, then commit & push.

Optional: a "NITRADO_SERVICE_TOKEN" secret holding a Nitrado long-life token (Account > Developer Portal > Long-life tokens, "service" scope only) lets a push restart the server once the upload is done. Put `[restart]` in the commit message, or tick the box on a manual run. Without the tag a push only uploads, and the mission is read at the next start. The same token and FTP secrets drive the nightly survivor-board run (below), which also pushes commits to main, so main must accept pushes from the workflow token.



### Build

    python scripts/substitute.py   # config.<map>.yml + remote/ -> dist/
    python scripts/validate.py     # checks dist/ before it is uploaded

Config is one complete file per map. `config.<map>.yml` is named after the part of the mission folder after the dot, so `config.sakhal.yml` applies to `dayzOffline.sakhal`. Nothing is shared between maps: map size and landscape change what even the global multipliers should be, so each file carries every value its mission needs and is tuned on its own. A mission folder with no config file fails the build. A config for an official map that has no mission folder is parked: the build ignores it, and it is there to tune ahead of a switch. Any other unmatched config name is warned about as a likely typo.

The GitHub Action runs both scripts on every push to main, then FTPs `dist/` to Nitrado, and with `[restart]` in the commit message restarts the server after the upload has finished (restarting from the panel while the upload is still running can start the server on a half-written mission). A placeholder with no value, an XML/JSON file that does not parse, or a loadout naming an item class that is not in types.xml fails the build and nothing is uploaded. Variables in any config file that nothing uses are warned about (typo catcher). So are event children that can never spawn: in a `<limit>custom</limit>` event (every infected event) a child's `min` is its percent of the event's spawn budget, handed out in file order, so once the running total reaches 100 every child after it gets nothing.

In JSON files write placeholders as strings, `"{{VAR}}"`, so the source stays valid JSON. Numbers and booleans come out bare in dist/.

Multipliers: `<EventName>_D_MULTIPLIER` scales that event's nominal/min/max in events.xml. Infected ones are also multiplied by `INFECTED_GLOBAL_D_MULTIPLIER` (and their zombie_territories dmin/dmax); animal ones by `ANIMAL_GLOBAL_D_MULTIPLIER`; vehicle ones by `VEHICLE_GLOBAL_D_MULTIPLIER`. `LOOT_<CATEGORY>_MULTIPLIER` scales nominal/min for a types.xml category, `LOOT_MIN_MULTIPLIER` then scales min alone (rounding down, never below 1) to widen the gap under nominal, `LOOT_RESTOCK_MIN` floors restock, and `INFECTED_LOOT_MAX` caps what infected carry. Everything else rounds up, so nothing scales to zero. `<EventName>_D_ABSOLUTE` replaces the global for that event instead of stacking on it, for a placed count that must not follow a density change (the Mummy singles); setting both forms for one name fails the build.

Density has a second half: `ZOMBIE_MAX_COUNT` (globals.xml ZombieMaxCount). The engine splits it across the infected events in proportion to their zones' total dmax and prints the split in the RPT at start (`InfectedArmyION :: dmax: 320.0, 4.2 % == 41 pcs`); an event can hold no more than its share. The shares do not move with the multipliers, so raising density without raising the budget changes nothing at a base whose share is already smaller than its band.

### Survivor board

    python scripts/survivors.py                               # rebuild the board from the archive by hand
    python scripts/survivors.py --mission dayzOffline.nasdara # first run, or after a map switch

One line shown once as a player connects: the three longest-living characters, the last death, and that the board updates at restart. It runs itself. The `Survivor board` workflow (`.github/workflows/survivor-board.yml`) is the nightly restart, 04:17 server time, and refreshes the board on the way. The running instance's admin log reaches FTP only when the instance stops, so the job lists the server's logs, restarts the server, waits for the flushed log, pulls it into `nitrado-logs/adm/`, runs `scripts/survivors.py`, and if the board changed uploads `db/messages.xml` and restarts once more so the engine reads it. What it pulled and changed is committed to main by `github-actions[bot]`, so pull before you work. "Run workflow" on that workflow in the Actions tab does the same on demand; the server restarts, twice if the board changed. Any failure leaves the server running and the board stale, and the next run catches up. With Nitrado's own automated restart switched off this is the only nightly restart.

`nitrado-logs/adm/` is the whole admin-log history, and the only one: Nitrado keeps about three days. The RPT logs are too big for the repo and are attached to each run as a 90-day artifact instead. Other folders under `nitrado-logs/` are hand pulls and gitignored. `data/survivors.json` is the ledger: every character's connected time and every death, per player id. A log is ingested once and the ledger keeps what it said. A character ends at a `(DEAD)` line, or when a login lands away from the last logout position, which is how a death in a log that was never pulled shows up. Time alive is connected time, like the game's own stat. `--since` ignores logs before a wipe and `--rebuild` recomputes from the archive. The script owns `db/messages.xml` and refuses to overwrite one it did not write.

`scripts/nitrado.py` is the server-side helper both workflows share: restart and status through the Nitrado API, log pulls and single-file uploads through FTP. Credentials come from the environment only, and it never prints a whole API reply, since the gameserver details carry the FTP password.







### Chernarus (`dayzOffline.chernarusplus`) - parked

    - Not deployed. config.chernarusplus.yml holds the live maps' tuning with this map's own event names, ready for a switch.


### Livonia (`dayzOffline.enoch`) - parked

    - Not deployed. config.enoch.yml holds the live maps' tuning with this map's own event names, ready for a switch.


### Nasdara (`dayzOffline.nasdara`) - active

    - Every value is in config.nasdara.yml. Nothing is shared with other maps.
    - remote/ holds only the files that change. Everything else stays as the server shipped it.
    - Infected density 3x (zones and events). Wild dog packs 1.5x (wolves ship inactive). Motorbikes 0.5x (no boats).
    - Infected budget ZombieMaxCount 7000 (vanilla 1000). At 2x the ArmyION share was 41 for the whole map against bases wanting 48 to 72, so a base filled to 41 and kills came back only when their corpses cleaned up, as one wave (the 11-25 log). It is a cap, not a spawn count: only awake zones hold infected, so for a solo player the number just has to clear the largest cluster of any one event, with room for the previous fight's corpses.
    - Bears switched on, on Nasdara ground. The shipped mission has the AnimalBear event at nominal 0 and an env/bear_territories.xml that is Livonia's file unchanged (85 zones covering only the south-west 12.8 km of a 16.4 km map), and cfgenvironment.xml never wires them together. remote/cfgenvironment.xml adds the Bear herd the way every official map declares it, db/events.xml sets the event to Sakhal's vanilla 5 and active, config.nasdara.yml multiplies that by 8 for the verification run, and env/bear_territories.xml is our own file: zones placed on Bohemia's Nasdara wolf, mouflon and goat territories across the southern and eastern half of the map, none in the north-west quadrant where every fresh spawn is, and at least 1 km from any spawn bubble. !aux/make_bear_zones.py rebuilds it and prints the per-quadrant counts. Dial the multiplier back once a bear has been met.
    - Infected zones wake at 400 m instead of 300, so a town's band is on its feet before you can see into it and more of a town is live at once.
    - Loot: vanilla. The loot knobs in config.nasdara.yml sit at their neutral values. No starting bandage.
    - Economy globals: more animals, longer corpse persistence, better-condition loot, short login/logout timers.
    - Unconscious shock recovery 2x so a solo knockout is not minutes of dead time.
    - Map shows player position.
    - Fresh spawns: 7 of the 20 vanilla bubbles, the ones in the north-west quadrant (x below 8192), so a new character never starts in bear country. The hop and travel sections keep all 20; they only fire for a character arriving from another server of a hive. Group rotation is off: vanilla ships one group with rotation on, which has nothing to rotate to.
    - Survivor board: a connecting player gets one line with the three longest-living characters, the last death and a note that the board updates at restart. db/messages.xml is generated by scripts/survivors.py, refreshed by the nightly survivor-board workflow, and holds nothing else.
    - Ships the six animal territory files cfgenvironment.xml references but the Nitrado install lacks (sheep, goat, mouflon, fox, monitor lizard, dogs), taken from Bohemia's 1.30 mission files. Without them those animals have nowhere to spawn.
    - Mummy infected (ZmbM_Mummy, the tanky Halloween class) added as the first child of the InfectedMedic and InfectedArmy events in db/events.xml. Child `min` values are percent shares that must total 100, so the vanilla types were squeezed to make room. Mummy is 16 percent at army zones and 10 percent at hospitals, about one per small zone and three at a large base.
    - Thirty lone Mummies in the wilderness: an InfectedMummy event plus 30 one-infected zones in env/zombie_territories.xml, each at a lootable structure at least 300 m from every other infected zone and at least 900 m from the next one. With zones waking at 400 m, ten of the thirty spots have a neighbouring zone close enough to wake while you stand at the structure; the other twenty stay Mummy-only. The structure and its isolation are noted beside each zone.

### Sakhal (`dayzOffline.sakhal`) - kept for switching back

    - Every value is in config.sakhal.yml. Nothing is shared with other maps.
    - Spawn points are vanilla. config.sakhal.yml notes how to pin a single test spawn again.
    - Spawn geared (main_loadout.json) for testing density settings (DMR has the loudest shot).
    - Infected density 2x (zones and events), wolves 1.5x, boats 0.5x.
    - Loot: vanilla. The loot knobs in config.sakhal.yml sit at their neutral values. No starting bandage.
    - Economy globals: more animals, longer corpse persistence, better-condition loot, short login/logout timers.
    - Unconscious shock recovery 2x so a solo knockout is not minutes of dead time.
    - Map shows player position.

