---
name: sinofy-culture
description: Integrate EU4 provinces of a given base culture into Ming (MNG) and convert them to the Sino-X (<culture>_new) east_asian culture. Use when the user asks to "intégrer/convertir une culture en sino-X", assign a culture's provinces to Ming, or create a <culture>_new culture. Supports several cultures in one safe batch.
---

# Sinofy a culture (base culture -> Sino-X + Ming integration)

Automates the established procedure for this mod: take every province of a base
culture `X`, assign it to Ming, and convert its culture to `X_new` (Sino-X) in
the `east_asian` group.

## The one rule about parallelism

Province history files are **disjoint** between cultures, but
`common/cultures/00_cultures.txt` and the 4 `localisation/chinese_cultures_l_*.yml`
files are **shared**. Two processes writing those shared files concurrently will
corrupt each other. **Never spawn parallel agents that each write the cultures or
loc files.** Instead, run the bundled script **once with all requested cultures** —
it reads/writes each shared file exactly once and handles all cultures' province
files in the same pass. That is the "parallel for many cultures, no overlap"
guarantee.

## How to run

From the mod root:

```bash
# one culture, default "Sino-<Culture>" loc names
python .claude/skills/sinofy-culture/sinofy.py --culture cham

# several cultures at once (safe batch — preferred)
python .claude/skills/sinofy-culture/sinofy.py --culture cham --culture khmer --culture malay

# preview without writing anything
python .claude/skills/sinofy-culture/sinofy.py --culture cham --dry-run

# full control (custom loc names / religion conversion) via JSON spec
python .claude/skills/sinofy-culture/sinofy.py --spec /tmp/spec.json
```

`spec.json`:
```json
[
  { "culture": "cham",
    "loc": {"english":"Sino-Cham","french":"sino-cham","german":"Sino-Cham","spanish":"sino-cham"},
    "religion": null },
  { "culture": "khmer" }
]
```

- `loc`   — optional display names per language. Missing languages default to
  `Sino-<Culture>` (en/de) and `sino-<culture>` (fr/es). French & Spanish are
  lowercase in this mod by convention.
- `religion` — optional. `null`/omitted = keep each province's religion (the
  "Culture + MNG" choice). Set a religion tag (e.g. `"confucianism"`) for the
  "Culture + MNG + religion" choice.

## What the script guarantees (the procedure, encoded)

1. **`X_new` culture** created in the `east_asian` group, **reusing X's ethnic
   names** (dynasty/male/female) — `_new` cultures keep their ethnic names; the
   "sino" is political, not a renaming. `primary` is commented out.
2. **Province discovery**: every province whose *initial* culture is `X`
   (mod override wins over base game; base files are copied into the mod).
3. **Ming integration** of each province's initial block: `owner = MNG`,
   `controller = MNG`, `culture = X_new`, plus an added `add_core = MNG`
   (existing cores, religion, and all dated events are preserved).
4. **Pre-1444 guard** (critical): any dated block dated **< 1444.11.11** that
   would strip Ming at game start (an `owner`/`controller` other than MNG, or a
   `remove_core = MNG`) is rewritten to keep MNG. EU4 applies pre-start-date
   history to the start state, so this is required for the integration to hold.
5. **Localisation** `X_new:0 "Sino-X"` added to all 4 language files (BOM kept).
6. **Verification**: brace balance of the cultures file, and per-province that
   `owner = MNG` + `add_core = MNG` survive to the 1444 start. Lines flagged
   `<-- CHECK` need a human look.

The script is **idempotent** — re-running on an already-converted culture reports
"already present / already done" and changes nothing.

## Agent workflow

1. Confirm scope with the user if unclear (culture-only vs +Ming vs +religion).
   This mod's default is **Culture + Ming integration, religion unchanged**.
2. If the user names several cultures, collect them all and run the script **once**
   with repeated `--culture` flags (or a JSON `--spec`). Do **not** fan out to
   parallel agents for the file writes.
3. Run with `--dry-run` first to preview discovered provinces, then run for real.
4. Read the report; investigate any `<-- CHECK` province manually.
5. Do not commit unless the user asks.

## Notes / gotchas

- `00_cultures.txt` is UTF-8 and some base name lists contain U+FFFD bytes
  inherited from the original Windows-1252 game files; the script preserves them
  rather than "fixing" them, keeping `X_new` identical to `X`.
- Localisation files are UTF-8 **with BOM** (`utf-8-sig`); the script preserves it.
- Province files keep their original later history (annexations, assimilations)
  on purpose — only the start state and pre-1444 blocks are forced to Ming.
- Base-game path is hard-coded in the script (`BASE_GAME`); update it there if the
  install location changes.
