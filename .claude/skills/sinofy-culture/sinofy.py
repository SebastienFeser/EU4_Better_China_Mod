#!/usr/bin/env python3
"""
sinofy.py - Integrate one or more EU4 base cultures into Ming (MNG) and convert
them to their "Sino-X" (<culture>_new) east_asian counterpart.

This is the automated, batch-safe version of the manual procedure. It processes
ALL requested cultures in a SINGLE process so every shared file
(00_cultures.txt + the 4 localisation files) is read-modified-written exactly
once -> no concurrency/overlap corruption. Province history files are disjoint
between cultures, so they are simply handled in the same pass.

Usage:
    python sinofy.py --spec spec.json
    python sinofy.py --culture cham
    python sinofy.py --culture cham --culture malay --dry-run

spec.json (preferred for several cultures, lets you set loc names / religion):
[
  {
    "culture": "cham",
    "loc": {"english":"Sino-Cham","french":"sino-cham",
            "german":"Sino-Cham","spanish":"sino-cham"},
    "religion": null
  },
  { "culture": "malay" }
]

Per-culture fields:
  culture   (required) base culture tag, e.g. "cham"
  loc       (optional) display names per language; missing langs default to
            "Sino-<Culture>" (english/german) / "sino-<culture>" (french/spanish)
  religion  (optional) if set, the INITIAL religion of each province is changed
            to this value (the "Culture + MNG + religion" option). Default: keep.

What it does per culture (idempotent / safe to re-run):
  1. Creates <culture>_new inside the east_asian group of 00_cultures.txt,
     reusing the base culture's dynasty/male/female names (the established
     pattern: _new cultures keep their ethnic names), with #primary commented.
  2. Finds every province whose INITIAL culture == <culture> (mod overrides win
     over base game files).
  3. Writes a mod override (or edits the existing mod file) setting the initial
     block to owner=MNG, controller=MNG, culture=<culture>_new, and appends
     add_core=MNG (existing cores + religion + dated events kept).
  4. Pre-1444 guard: any dated block dated < 1444.11.11 that would strip MNG
     (owner != MNG, or remove_core = MNG) is rewritten to keep MNG.
  5. Adds localisation <culture>_new:0 "Sino-X" in english/french/german/spanish
     (BOM preserved), if absent.
  6. Verifies brace balance + that every touched province is MNG-owned with an
     MNG core at the 1444 start, and prints a report.
"""

import argparse, io, json, os, re, sys

# --- paths ---------------------------------------------------------------
# this file lives in <mod>/.claude/skills/sinofy-culture/ -> up 3 to mod root
MOD_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BASE_GAME = r"C:/Program Files (x86)/Steam/steamapps/common/Europa Universalis IV"

CULTURES_REL = "common/cultures/00_cultures.txt"
PROV_REL     = "history/provinces"
LOC_REL      = "localisation"
LANGS        = ["english", "french", "german", "spanish"]
START        = (1444, 11, 11)

def p_mod(*a):  return os.path.join(MOD_ROOT, *a)
def p_base(*a): return os.path.join(BASE_GAME, *a)

def read(path, enc="utf-8"):
    with io.open(path, "r", encoding=enc) as f:
        return f.read()

def write(path, text, enc="utf-8"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding=enc, newline="") as f:
        f.write(text)

def safe(s):  # printable on cp1252 consoles
    return s.encode("ascii", "backslashreplace").decode("ascii")

# --- cultures file -------------------------------------------------------
def find_block(text, name):
    """Return (start_idx, end_idx_inclusive, indent) of a `name = { ... }` block."""
    m = re.search(r'(?m)^([ \t]*)' + re.escape(name) + r'\s*=\s*\{', text)
    if not m:
        return None
    indent = m.group(1)
    i = text.index('{', m.start()); depth = 0; j = i
    while j < len(text):
        if text[j] == '{': depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                break
        j += 1
    return (m.start(), j + 1, indent)

def make_new_culture(cultures_text, culture):
    """Return the <culture>_new block string indented to match east_asian, or
    None if the base culture block can't be found."""
    blk = find_block(cultures_text, culture)
    if not blk:
        return None
    s, e, old_indent = blk
    block = cultures_text[s:e]
    # target indent = that of an existing east_asian culture (korean_new)
    kn = re.search(r'(?m)^([ \t]*)korean_new\s*=\s*\{', cultures_text)
    target = kn.group(1) if kn else "\t"
    # shift indentation old_indent -> target on every line
    out = []
    for line in block.split('\n'):
        if line.startswith(old_indent):
            out.append(target + line[len(old_indent):])
        else:
            out.append(line)
    block = '\n'.join(out)
    block = block.replace(target + culture + " = {",
                          target + culture + "_new = {", 1)
    # comment out a primary tag if present (the base culture keeps the tag)
    block = re.sub(r'(?m)^(\s*)primary(\s*=)', r'\1#primary\2', block, count=1)
    return block

def insert_cultures(cultures_text, cultures, report):
    """Insert every missing <culture>_new before korean_new. One write."""
    for c in cultures:
        if re.search(r'(?m)^\s*' + re.escape(c) + r'_new\s*=\s*\{', cultures_text):
            report.append(f"culture {c}_new: already present (skipped)")
            continue
        block = make_new_culture(cultures_text, c)
        if block is None:
            report.append(f"culture {c}: BASE CULTURE NOT FOUND in {CULTURES_REL} (skipped)")
            continue
        anchor = re.search(r'(?m)^[ \t]*korean_new\s*=\s*\{', cultures_text)
        idx = cultures_text.rfind('\n', 0, anchor.start())  # start of korean_new line
        cultures_text = cultures_text[:idx] + '\n' + block + cultures_text[idx:]
        report.append(f"culture {c}_new: inserted into east_asian group")
    return cultures_text

# --- localisation --------------------------------------------------------
def default_loc(culture):
    title = culture.replace('_', ' ').title().replace(' ', '-')
    low   = culture.replace('_', '-').lower()
    return {"english": f"Sino-{title}", "german": f"Sino-{title}",
            "french": f"sino-{low}",   "spanish": f"sino-{low}"}

def apply_loc(cultures, report):
    for lang in LANGS:
        path = p_mod(LOC_REL, f"chinese_cultures_l_{lang}.yml")
        if not os.path.exists(path):
            report.append(f"loc {lang}: file missing ({path}) - skipped")
            continue
        text = read(path, "utf-8-sig")
        changed = False
        for c in cultures:
            key = f"{c}_new:"
            if key in text:
                continue
            text = text if text.endswith("\n") else text + "\n"
            text += f' {c}_new:0 "{LOC_NAMES[c][lang]}"\n'
            changed = True
        if changed:
            write(path, text, "utf-8-sig")
            report.append(f"loc {lang}: updated")

# --- province files ------------------------------------------------------
DATE_RE = re.compile(r'(?m)^(\d{1,4})\.(\d{1,2})\.(\d{1,2})\s*=\s*\{')

def block_bounds(text, brace_start):
    depth = 0; j = brace_start
    while j < len(text):
        if text[j] == '{': depth += 1
        elif text[j] == '}':
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return len(text) - 1

def fix_pre1444(text):
    """Rewrite any dated block before the 1444 start that would strip MNG."""
    edits = []  # (start, end, newtext)
    for m in DATE_RE.finditer(text):
        d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d >= START:
            continue
        bs = text.index('{', m.start())
        be = block_bounds(text, bs)
        blk = text[bs:be + 1]
        new = blk
        new = re.sub(r'owner\s*=\s*\w+',      'owner = MNG',      new)
        new = re.sub(r'controller\s*=\s*\w+', 'controller = MNG', new)
        # drop any line removing the MNG core
        new = re.sub(r'(?m)^[ \t]*remove_core\s*=\s*MNG[ \t]*\r?\n?', '', new)
        if new != blk:
            edits.append((bs, be + 1, new))
    for s, e, nt in reversed(edits):
        text = text[:s] + nt + text[e:]
    return text, len(edits)

def transform_province(text, src, target, religion):
    nl = '\r\n' if '\r\n' in text else '\n'
    text = re.sub(r'(?m)^owner\s*=\s*\w+',      'owner = MNG',      text, count=1)
    text = re.sub(r'(?m)^controller\s*=\s*\w+', 'controller = MNG', text, count=1)
    text = re.sub(r'(?m)^culture\s*=\s*' + re.escape(src) + r'\b',
                  f'culture = {target}_new', text, count=1)
    if religion:
        text = re.sub(r'(?m)^religion\s*=\s*\w+', f'religion = {religion}', text, count=1)
    if not re.search(r'(?m)^add_core\s*=\s*MNG\b', text):
        m = re.search(r'(?m)^add_core\s*=\s*\w+[ \t]*', text)
        if m:
            text = text[:m.end()] + nl + 'add_core = MNG' + text[m.end():]
        else:  # no core at all: add one right after the controller line
            m = re.search(r'(?m)^controller\s*=\s*MNG[ \t]*', text)
            text = text[:m.end()] + nl + 'add_core = MNG' + text[m.end():]
    text, _ = fix_pre1444(text)
    return text

def find_provinces(src, target):
    """Return {province_filename: source_path}.

    A province belongs to this entry if its INITIAL culture line is <src> (the
    base culture) or <target>_new (the converted result, so re-runs still detect
    already-converted ones). For a normal entry src == target; for a mapping
    entry (e.g. karen -> shan) src != target.
    Source path is the MOD override when it exists (to preserve mod-specific
    dated events), otherwise the base-game file."""
    pat = re.compile(r'(?m)^culture\s*=\s*(?:' + re.escape(src) + r'|'
                     + re.escape(target) + r'_new)\b')
    base_root, mod_root = p_base(PROV_REL), p_mod(PROV_REL)

    # Build the set of province filenames; the MOD override is authoritative for a
    # province's *effective* culture when it exists, otherwise the base file is.
    names = set()
    for root in (base_root, mod_root):
        if os.path.isdir(root):
            names.update(fn for fn in os.listdir(root) if fn.lower().endswith(".txt"))

    found = {}
    for fn in names:
        mod_path  = os.path.join(mod_root, fn)
        eff_path  = mod_path if os.path.exists(mod_path) else os.path.join(base_root, fn)
        try:
            if pat.search(read(eff_path)):   # effective culture is src or target_new
                found[fn] = eff_path
        except Exception:
            pass
    return found

# --- verification --------------------------------------------------------
def verify_province(path):
    t = read(path)
    owner_ok = bool(re.search(r'(?m)^owner\s*=\s*MNG', t))
    core_ok  = bool(re.search(r'(?m)^add_core\s*=\s*MNG', t))
    # simulate pre-1444 owner overrides
    eff_owner = "MNG" if owner_ok else "?"
    for m in DATE_RE.finditer(t):
        d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d < START:
            bs = t.index('{', m.start()); be = block_bounds(t, bs)
            mo = re.search(r'owner\s*=\s*(\w+)', t[bs:be + 1])
            if mo:
                eff_owner = mo.group(1)
    return owner_ok, core_ok, eff_owner

# --- main ----------------------------------------------------------------
LOC_NAMES = {}  # culture -> {lang: name}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", help="JSON spec file (list of culture objects)")
    ap.add_argument("--culture", action="append", default=[],
                    help="culture tag (repeatable); uses default Sino-X loc names")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    specs = []
    if args.spec:
        specs = json.loads(read(args.spec))
    for c in args.culture:
        specs.append({"culture": c})
    if not specs:
        ap.error("provide --spec or at least one --culture")

    # normalise entries: src culture, target (_new owner), religion, loc
    entries = []
    for s in specs:
        src = s["culture"]
        target = s.get("target", src)          # mapping: e.g. karen -> shan
        religion = s.get("religion")
        loc = default_loc(target)
        loc.update(s.get("loc", {}) or {})
        LOC_NAMES[target] = loc
        entries.append({"src": src, "target": target, "religion": religion})

    # cultures whose <name>_new must be created/localised (skip mapping entries)
    creates = [e["target"] for e in entries if e["src"] == e["target"]]
    creates = list(dict.fromkeys(creates))      # de-dup, keep order

    report = []
    print(f"MOD_ROOT  = {MOD_ROOT}")
    print(f"BASE_GAME = {BASE_GAME}")
    print(f"Entries   = {[(e['src'], e['target']) for e in entries]}")
    print(f"Dry run   = {args.dry_run}\n")

    # 1+2) cultures file (single read/write across all cultures)
    cpath = p_mod(CULTURES_REL)
    ctext = read(cpath)
    new_ctext = insert_cultures(ctext, creates, report)
    if not args.dry_run and new_ctext != ctext:
        write(cpath, new_ctext)
    bal = new_ctext.count('{') == new_ctext.count('}')
    report.append(f"cultures file braces balanced: {bal} "
                  f"({new_ctext.count('{')}/{new_ctext.count('}')})")

    # 3) localisation (single read/write per lang across all cultures)
    if not args.dry_run:
        apply_loc(creates, report)
    else:
        report.append("loc: skipped (dry-run)")

    # 4+5) province files (disjoint per entry)
    prov_report = []
    for e in entries:
        src, target = e["src"], e["target"]
        label = src if src == target else f"{src}->{target}"
        provs = find_provinces(src, target)
        for fn, srcpath in sorted(provs.items()):
            t = read(srcpath)
            if re.search(r'(?m)^culture\s*=\s*' + re.escape(target) + r'_new\b', t) \
               and re.search(r'(?m)^owner\s*=\s*MNG', t):
                prov_report.append((label, target, fn, "already done"))
                continue
            nt = transform_province(t, src, target, e["religion"])
            outpath = p_mod(PROV_REL, fn)
            if not args.dry_run:
                write(outpath, nt)
            o, k, eff = verify_province(outpath) if not args.dry_run \
                else (True, True, "MNG(dry)")
            prov_report.append((label, target, fn,
                                f"owner_MNG={o} core_MNG={k} start_owner={eff}"))

    print("=== SHARED FILES ===")
    for r in report:
        print("  " + safe(r))
    print("\n=== PROVINCES ===")
    cur = None
    for label, target, fn, st in prov_report:
        if label != cur:
            print(f"  [{label}] -> {target}_new")
            cur = label
        flag = "" if ("owner_MNG=True" in st or "already" in st or "dry" in st) else "  <-- CHECK"
        print(f"    {safe(fn):32s} {st}{flag}")
    if not prov_report:
        print("  (no provinces found)")
    print("\nDone." + ("  (DRY RUN - nothing written)" if args.dry_run else ""))

if __name__ == "__main__":
    main()
