# Loadout JSON Schema

Reference for the structure of loadout files used by the spawn system.

---

## Top-Level Structure

```json
{
  "spawnWeight": number,          // Relative weight for random loadout selection
  "name": string,                 // Display name for this loadout
  "characterTypes": string[],     // List of valid survivor model class names

  "attachmentSlotItemSets": [ ... ],
  "discreteUnsortedItemSets": [ ... ]
}
```

---

## attachmentSlotItemSets

One entry per gear slot. Each entry picks ONE item from its `discreteItemSets` array using weighted random selection.

```json
"attachmentSlotItemSets": [
  {
    "slotName": string,           // Slot identifier (see Slot Names table below)
    "discreteItemSets": [         // ONE item from this array is chosen (weighted random)
      {
        "itemType": string,       // Class name of item ("" = no item spawned)
        "spawnWeight": number,    // Relative probability of this option being chosen
        "quickBarSlot": number,   // Hotbar binding (-1 = none, 1-9 = slot number)

        // OPTIONAL — omit if no condition/quantity control needed
        "attributes": {
          "healthMin": number,    // 0.0–1.0
          "healthMax": number,    // 0.0–1.0
          "quantityMin": number,  // float (0.0–1.0 as %) or integer for countable items
          "quantityMax": number
        },

        // OPTIONAL — children with their own explicit attributes
        // Use for gun attachments (optics, suppressors, magazines attached to a weapon)
        "complexChildrenTypes": [
          {
            "itemType": string,
            "quickBarSlot": number,
            "attributes": { ... },                          // same shape as above
            "simpleChildrenUseDefaultAttributes": boolean,  // optional
            "simpleChildrenTypes": string[]                 // optional
          }
        ],

        // OPTIONAL — children spawned using default or parent attributes (no per-item control)
        "simpleChildrenUseDefaultAttributes": boolean,
        "simpleChildrenTypes": string[]
      }
    ]
  }
]
```

### Slot Names

| `slotName`  | Purpose                          |
|-------------|----------------------------------|
| `shoulderL` | Primary weapon (left shoulder)   |
| `shoulderR` | Secondary melee/tool (right shoulder) |
| `Vest`      | Vest / chest rig                 |
| `Back`      | Backpack                         |
| `Headgear`  | Helmet / hat                     |
| `Armband`   | Armband                          |
| `Gloves`    | Gloves                           |
| `Mask`      | Face mask                        |
| `Eyewear`   | Glasses / goggles                |
| `Body`      | Jacket / top                     |
| `Legs`      | Pants                            |
| `Feet`      | Boots                            |

---

## discreteUnsortedItemSets

Fills general inventory (cargo). Same weighted-random logic as slots — ONE entry from the array is chosen. All children within the chosen entry spawn together.

```json
"discreteUnsortedItemSets": [
  {
    "name": string,               // Label (e.g. "Cargo1")
    "spawnWeight": number,

    "attributes": { ... },        // Default attributes applied to simple children in this set

    // Items with explicit per-item attributes — always included
    "complexChildrenTypes": [
      {
        "itemType": string,
        "quickBarSlot": number,
        "attributes": { ... },
        "simpleChildrenUseDefaultAttributes": boolean,  // optional
        "simpleChildrenTypes": string[]                 // optional
      }
    ],

    // Items using the set's default attributes — always included
    "simpleChildrenUseDefaultAttributes": boolean,
    "simpleChildrenTypes": string[]
  }
]
```

---

## Key Behaviors

- **Weighted random selection** — `spawnWeight` is relative. A weight of `2` is twice as likely as `1`. Applied independently per slot and per `discreteUnsortedItemSets`.

- **Empty item option** — Use `{ "itemType": "", "spawnWeight": N }` inside `discreteItemSets` to give a chance of nothing spawning in that slot (e.g. Mask, Eyewear).

- **`complexChildrenTypes`** — children with full attribute control. Always spawn (not random). Typically used for weapon attachments (optic, stock, handguard, suppressor, magazine).

- **`simpleChildrenTypes`** — children defined as plain class name strings with no per-item attributes. Always spawn alongside the parent item.
  - `simpleChildrenUseDefaultAttributes: true` — game default attributes applied.
  - `simpleChildrenUseDefaultAttributes: false` — parent item's `attributes` are inherited.

- **`quantityMin` / `quantityMax`** — for magazines/ammo, `1.0` = fully loaded. For stackable items like pills, use raw integer counts (e.g. `40` / `50`).

- **Nesting depth** — `complexChildrenTypes` can themselves contain `simpleChildrenTypes` (e.g. a `PersonalRadio` complex child with a `Battery9V` simple child). Max observed depth is 2 levels.
