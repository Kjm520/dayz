DayZ console mods with Nitrado.

Currently, variables are being created and extracted, to later be substituted with values that are assigned in one config file per map (config.nasdara.yml, config.sakhal.yml). This removes the grueling process of crawling DayZ xml files looking for settings that may or may not have other dependent values that break the game. Certain changes, be it wolf count, or spawn box settings, can silently break the game. 

Example: "INFECTED_GLOBAL_D_MULTIPLIER: 2.0" - This single value applies the multiplier across all of the zombie types respective to their original proportion. 

Example (in spawn category): "MAX_DIST: "400"" - This single value applies across several spawn settings, like max distance to the nearest static object, max distance to the nearest z, max distance to the nearest player, etc.


# How to start:
Set your repo's secrets for "FTP_HOST", "FTP_PASSWORD", and "FTP_USERNAME" to the information provided from Nitrado for your server, then commit & push.



### Build

    python scripts/substitute.py   # config.<map>.yml + remote/ -> dist/
    python scripts/validate.py     # checks dist/ before it is uploaded

Config is one complete file per map. `config.<map>.yml` is named after the part of the mission folder after the dot, so `config.sakhal.yml` applies to `dayzOffline.sakhal`. Nothing is shared between maps: map size and landscape change what even the global multipliers should be, so each file carries every value its mission needs and is tuned on its own. A mission folder with no config file fails the build. A config for an official map that has no mission folder is parked: the build ignores it, and it is there to tune ahead of a switch. Any other unmatched config name is warned about as a likely typo.

The GitHub Action runs both scripts on every push to main, then FTPs `dist/` to Nitrado. A placeholder with no value, an XML/JSON file that does not parse, or a loadout naming an item class that is not in types.xml fails the build and nothing is uploaded. Variables in any config file that nothing uses are warned about (typo catcher). So are event children that can never spawn: in a `<limit>custom</limit>` event (every infected event) a child's `min` is its percent of the event's spawn budget, handed out in file order, so once the running total reaches 100 every child after it gets nothing.

In JSON files write placeholders as strings, `"{{VAR}}"`, so the source stays valid JSON. Numbers and booleans come out bare in dist/.

Multipliers: `<EventName>_D_MULTIPLIER` scales that event's nominal/min/max in events.xml. Infected ones are also multiplied by `INFECTED_GLOBAL_D_MULTIPLIER` (and their zombie_territories dmin/dmax); animal ones by `ANIMAL_GLOBAL_D_MULTIPLIER`; vehicle ones by `VEHICLE_GLOBAL_D_MULTIPLIER`. `LOOT_<CATEGORY>_MULTIPLIER` scales nominal/min for a types.xml category, `LOOT_MIN_MULTIPLIER` then scales min alone (rounding down, never below 1) to widen the gap under nominal, `LOOT_RESTOCK_MIN` floors restock, and `INFECTED_LOOT_MAX` caps what infected carry. Everything else rounds up, so nothing scales to zero.







### Chernarus (`dayzOffline.chernarusplus`) - parked

    - Not deployed. config.chernarusplus.yml holds the live maps' tuning with this map's own event names, ready for a switch.


### Livonia (`dayzOffline.enoch`) - parked

    - Not deployed. config.enoch.yml holds the live maps' tuning with this map's own event names, ready for a switch.


### Nasdara (`dayzOffline.nasdara`) - active

    - Every value is in config.nasdara.yml. Nothing is shared with other maps.
    - remote/ holds only the files that change. Everything else stays as the server shipped it.
    - Infected density 2x (zones and events). Wild dog packs 1.5x (no wolves or bears on this map). Motorbikes 0.5x (no boats).
    - Infected zones wake at 400 m instead of 300, so a town's band is on its feet before you can see into it and more of a town is live at once.
    - Loot: vanilla. The loot knobs in config.nasdara.yml sit at their neutral values. No starting bandage.
    - Economy globals: more animals, longer corpse persistence, better-condition loot, short login/logout timers.
    - Unconscious shock recovery 2x so a solo knockout is not minutes of dead time.
    - Map shows player position.
    - Spawn points: the 60 vanilla points, with group rotation turned off. Vanilla ships them as a single group with rotation on, which has nothing to rotate to.
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

