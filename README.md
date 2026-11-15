DayZ console mods with Nitrado.

Currently, variables are being created and extracted, to later be substituted with values that are assigned in a single place (config.yml). This removes the grueling process of crawling DayZ xml files looking for settings that may or may not have other dependent values that break the game. Certain changes, be it wolf count, or spawn box settings, can silently break the game. 

Example: "INFECTED_GLOBAL_D_MULTIPLIER: 2.0" - This single value applies the multiplier across all of the zombie types respective to their original proportion. 

Example (in spawn category): "MAX_DIST: "400"" - This single value applies across several spawn settings, like max distance to the nearest static object, max distance to the nearest z, max distance to the nearest player, etc.


# How to start:
Set your repo's secrets for "FTP_HOST", "FTP_PASSWORD", and "FTP_USERNAME" to the information provided from Nitrado for your server, then commit & push.



### Build

    python scripts/substitute.py   # config.yml + remote/ -> dist/
    python scripts/validate.py     # checks dist/ before it is uploaded

The GitHub Action runs both on every push to main, then FTPs `dist/` to Nitrado. A placeholder with no value in config.yml, an XML/JSON file that does not parse, or a loadout naming an item class that is not in types.xml fails the build and nothing is uploaded. Variables in config.yml that nothing uses are warned about (typo catcher).

In JSON files write placeholders as strings, `"{{VAR}}"`, so the source stays valid JSON. Numbers and booleans come out bare in dist/.

Multipliers: `<EventName>_D_MULTIPLIER` scales that event's nominal/min/max in events.xml. Infected ones are also multiplied by `INFECTED_GLOBAL_D_MULTIPLIER` (and their zombie_territories dmin/dmax); animal ones by `ANIMAL_GLOBAL_D_MULTIPLIER`; vehicle ones by `VEHICLE_GLOBAL_D_MULTIPLIER`. `LOOT_<CATEGORY>_MULTIPLIER` scales nominal/min for a types.xml category, `LOOT_MIN_MULTIPLIER` then scales min alone (rounding down, never below 1) to widen the gap under nominal, `LOOT_RESTOCK_MIN` floors restock, and `INFECTED_LOOT_MAX` caps what infected carry. Everything else rounds up, so nothing scales to zero.







### Chernarus (`dayzOffline.chernarusplus`)

    - No changes


### Livonia (`dayzOffline.enoch`)

    - No changes


### Sakhal (`dayzOffline.sakhal`)

    - Spawn points are vanilla. config.yml notes how to pin a single test spawn again.
    - Spawn geared (main_loadout.json) for testing density settings (DMR has the loudest shot).
    - Infected density 2x (zones and events), wolves 1.5x, boats 0.5x. See config.yml.
    - Survival: food loot 0.5x, tools 0.7x, loot min thresholds 0.85x so the map empties further before restocking, one-hour restock floor, infected carry at most 2 items, no starting bandage.
    - Economy globals: more animals, longer corpse persistence, better-condition loot, short login/logout timers.
    - Unconscious shock recovery 2x so a solo knockout is not minutes of dead time.
    - Map shows player position.

