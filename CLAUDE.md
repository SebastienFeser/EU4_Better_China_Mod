# CLAUDE.md — Chinese Culture and Religion (EU4 mod)

EU4 mod that expands Chinese culture/religion and integrates surrounding
provinces into Ming (MNG). Target game version **v1.37.5.0**.

## Base game files

Read-only base game install (already allow-listed for reads):
`C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis IV`

Useful base paths:
- `common/cultures/00_cultures.txt` — culture groups & cultures
- `history/provinces/<id> - <name>.txt` — per-province start state + dated history
- `common/religions/` — religion definitions
- `localisation/` — display names
- `map/region.txt`, `map/area.txt` — region/area groupings

When you need a base-game file the mod doesn't override yet, read it from there
and write the modified copy under the mod (same relative path / filename).

## Mod layout

```
common/cultures/00_cultures.txt   # full override of the base cultures file
history/provinces/                # ~304 province overrides (filename = "<id> - <name>.txt")
history/countries/
localisation/chinese_cultures_l_{english,french,german,spanish}.yml
descriptor.mod
.claude/skills/sinofy-culture/    # automation for culture -> Sino-X + Ming
NOMS_CHINOIS_PROPOSES.md          # working docs (proposed Chinese province names)
PROVINCES_NOM_CHINOIS_NON_MING.md
```

## Core concepts

- **Sino-X cultures = `<culture>_new`** inside the `east_asian` group of
  `00_cultures.txt` (e.g. `vietnamese_new`, `tibetan_new`, `cham_new`). The
  `_new` cultures **keep their ethnic names** (dynasty/male/female copied from
  the base culture); "sino" means political integration into the Chinese group,
  not renaming. Their `primary` tag is commented out.
  - When assigning a sino culture, only convert **non-sino** base cultures. A
    province already in a `_new` culture must keep its culture.
- **Ming integration** of a province = initial block set to `owner = MNG`,
  `controller = MNG`, an added `add_core = MNG` (existing cores kept),
  `culture = <X>_new`. Religion is kept unless explicitly asked to change it.
- **Pre-1444 rule (critical):** EU4 applies every dated history block dated
  **before the 1444.11.11 start** to the start state. After integrating a
  province to MNG, verify no pre-1444 block strips it (an `owner`/`controller`
  other than MNG, or `remove_core = MNG`); rewrite such a block to keep MNG.
  Established pattern: see `1016 - Ha Tinh.txt` (a 1413 event reinforces Ming);
  `1022 - Indrapura.txt` had a 1407 block handing it to DAI that was rewritten.

## The `sinofy-culture` skill

Automates the whole "base culture X -> Sino-X + Ming" procedure, batch-safe for
several cultures at once. Prefer it over manual edits.

```bash
python .claude/skills/sinofy-culture/sinofy.py --culture cham            # one
python .claude/skills/sinofy-culture/sinofy.py --culture cham --culture khmer  # batch
python .claude/skills/sinofy-culture/sinofy.py --culture cham --dry-run  # preview
```

**Parallelism:** province files are disjoint per culture, but `00_cultures.txt`
and the 4 loc files are shared — never run parallel writers on them. Run the
script **once with all cultures** instead (it writes each shared file once).
The script is idempotent. See the skill's `SKILL.md` for full options
(custom loc names, optional religion conversion via `--spec`).

## Encoding gotchas

- `00_cultures.txt` is **UTF-8**; some base name lists contain U+FFFD bytes
  inherited from the original Windows-1252 game files. Preserve them — don't
  "fix" them — so `<X>_new` stays byte-identical to `X`. Edit it with Python
  reading/writing UTF-8 rather than retyping name lists by hand.
- Localisation `.yml` files are **UTF-8 with BOM** (`utf-8-sig`); preserve the BOM.
- `awk` `sub()`/`gsub()` backrefs (`\1`) emit a literal SOH (0x01) byte that
  breaks EU4's parser. Use `sed -E`, Python, or manual capture instead.

## Working habits

- After editing `00_cultures.txt`, check brace balance (`{` count == `}` count).
- After integrating provinces, verify each is MNG-owned with an MNG core at the
  1444 start (the skill prints this).
- The shell is PowerShell; a Bash tool is also available (Python 3.12 present).
- **Do not commit or push unless the user asks.** Work on `master`.
