DayZ console mods with Nitrado.

Currently, variables are being created and extracted, to later be substituted with values that are assigned in a single place (config.yml). This removes the grueling process of crawling DayZ xml files looking for settings that may or may not have other dependent values that break the game. Certain changes, be it wolf count, or spawn box settings, can silently break the game. 

Example: "INFECTED_GLOBAL_D_MULTIPLIER: 2.0" - This single value applies the multiplier across all of the zombie types respective to their original proportion. 

Example (in spawn category): "MAX_DIST: "400"" - This single value applies across several spawn settings, like max distance to the nearest static object, max distance to the nearest z, max distance to the nearest player, etc.


# How to start:
Set your repo's secrets for "FTP_HOST", "FTP_PASSWORD", and "FTP_USERNAME" to the information provided from Nitrado for your server, then commit & push.



### Build

    python scripts/substitute.py   # config layers + remote/ -> dist/
    python scripts/validate.py     # checks dist/ before it is uploaded

Config is layered. `config.yml` holds values shared by every map. `config.<map>.yml` holds one map's own values, named after the part of the mission folder after the dot, so `config.sakhal.yml` applies to `dayzOffline.sakhal`. A mission sees the shared file with its own file on top; the same key in both means the map file wins. Map-specific things (zone and event names, animals, vehicles, coordinates) belong in the map file; tuning you want everywhere belongs in the shared one.

The GitHub Action runs both scripts on every push to main, then FTPs `dist/` to Nitrado. A placeholder with no value, an XML/JSON file that does not parse, or a loadout naming an item class that is not in types.xml fails the build and nothing is uploaded. Variables in any config file that nothing uses are warned about (typo catcher).

In JSON files write placeholders as strings, `"{{VAR}}"`, so the source stays valid JSON. Numbers and booleans come out bare in dist/.

Multipliers: `<EventName>_D_MULTIPLIER` scales that event's nominal/min/max in events.xml. Infected ones are also multiplied by `INFECTED_GLOBAL_D_MULTIPLIER` (and their zombie_territories dmin/dmax); animal ones by `ANIMAL_GLOBAL_D_MULTIPLIER`; vehicle ones by `VEHICLE_GLOBAL_D_MULTIPLIER`. `LOOT_<CATEGORY>_MULTIPLIER` scales nominal/min for a types.xml category, `LOOT_MIN_MULTIPLIER` then scales min alone (rounding down, never below 1) to widen the gap under nominal, `LOOT_RESTOCK_MIN` floors restock, and `INFECTED_LOOT_MAX` caps what infected carry. Everything else rounds up, so nothing scales to zero.







### Chernarus (`dayzOffline.chernarusplus`)

    - No changes


### Livonia (`dayzOffline.enoch`)

    - No changes


### Nasdara (`dayzOffline.nasdara`) - active

    - Map-specific values are in config.nasdara.yml; shared tuning in config.yml.
    - remote/ holds only the files that change. Everything else stays as the server shipped it.
    - Infected density 2x (zones and events). Wild dog packs 1.5x (no wolves or bears on this map). Motorbikes 0.5x (no boats).
    - Survival: shared loot tuning (food 0.5x, tools 0.7x, min thresholds 0.85x, one-hour restock floor, infected carry at most 2), same loadouts, no starting bandage.
    - Economy globals and unconscious recovery: same as Sakhal.
    - Map shows player position.
    - Spawn points: the 60 vanilla points, with group rotation turned off. Vanilla ships them as a single group with rotation on, which has nothing to rotate to.
    - Ships the six animal territory files cfgenvironment.xml references but the Nitrado install lacks (sheep, goat, mouflon, fox, monitor lizard, dogs), taken from Bohemia's 1.30 mission files. Without them those animals have nowhere to spawn.
    - Mummy infected (ZmbM_Mummy, the tanky Halloween class) added to the InfectedMedic event in db/events.xml. TEST SETTINGS: weight 200 vs 100 for all other medic types, and InfectedMedic_D_MULTIPLIER 2.0 in config.nasdara.yml. Scale both back once confirmed.

### Sakhal (`dayzOffline.sakhal`) - kept for switching back

    - Map-specific values are in config.sakhal.yml; shared tuning in config.yml.
    - Spawn points are vanilla. config.sakhal.yml notes how to pin a single test spawn again.
    - Spawn geared (main_loadout.json) for testing density settings (DMR has the loudest shot).
    - Infected density 2x (zones and events), wolves 1.5x, boats 0.5x.
    - Survival: food loot 0.5x, tools 0.7x, loot min thresholds 0.85x so the map empties further before restocking, one-hour restock floor, infected carry at most 2 items, no starting bandage.
    - Economy globals: more animals, longer corpse persistence, better-condition loot, short login/logout timers.
    - Unconscious shock recovery 2x so a solo knockout is not minutes of dead time.
    - Map shows player position.

