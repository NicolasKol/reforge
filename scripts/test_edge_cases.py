"""One-off script to check data edge cases in alignment/build artifacts."""
import json
from pathlib import Path
from collections import defaultdict

root = Path(r"c:\Users\nico_\Documents\UNI\Thesis\Source\reforge\docker\local-files\artifacts\synthetic")
test_cases = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name.startswith("t"))
opt_levels = ["O0", "O1", "O2", "O3"]
variant = "debug"

# ── Q1: null best_tu_path / best_ts_func_id ──────────────────────────────────
print("=" * 80)
print("Q1: alignment_pairs.json — null best_tu_path / best_ts_func_id / best_ts_function_name")
print("=" * 80)
q1_count = 0
for tc in test_cases:
    for opt in opt_levels:
        fp = root / tc / opt / variant / "join_dwarf_ts" / "alignment_pairs.json"
        if not fp.exists():
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        for p in data.get("pairs", []):
            btp = p.get("best_tu_path")
            btf = p.get("best_ts_func_id")
            btfn = p.get("best_ts_function_name")
            if btp is None or btf is None or btfn is None:
                q1_count += 1
                print(f"  {tc}/{opt}: dwarf_id={p.get('dwarf_function_id')}, "
                      f"verdict={p.get('verdict')}, "
                      f"best_tu_path={btp!r}, best_ts_func_id={btf!r}, "
                      f"best_ts_function_name={btfn!r}")
if q1_count == 0:
    print("  (none found — all pairs have non-null best_tu_path/best_ts_func_id/best_ts_function_name)")
print(f"  TOTAL null hits: {q1_count}")

# ── Q2a: null dwarf_function_name ─────────────────────────────────────────────
print()
print("=" * 80)
print("Q2a: alignment_pairs.json — null dwarf_function_name in pairs")
print("=" * 80)
q2a_count = 0
for tc in test_cases:
    for opt in opt_levels:
        fp = root / tc / opt / variant / "join_dwarf_ts" / "alignment_pairs.json"
        if not fp.exists():
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        for p in data.get("pairs", []):
            dfn = p.get("dwarf_function_name")
            if dfn is None:
                q2a_count += 1
                print(f"  {tc}/{opt}: dwarf_id={p.get('dwarf_function_id')}, "
                      f"verdict={p.get('verdict')}, dwarf_function_name={dfn!r}")
if q2a_count == 0:
    print("  (none found)")
print(f"  TOTAL null hits: {q2a_count}")

# ── Q2b: null non_target name ─────────────────────────────────────────────────
print()
print("=" * 80)
print("Q2b: alignment_pairs.json — null non_target name")
print("=" * 80)
q2b_count = 0
for tc in test_cases:
    for opt in opt_levels:
        fp = root / tc / opt / variant / "join_dwarf_ts" / "alignment_pairs.json"
        if not fp.exists():
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        for nt in data.get("non_targets", []):
            nm = nt.get("name")
            if nm is None:
                q2b_count += 1
                print(f"  {tc}/{opt}: dwarf_id={nt.get('dwarf_function_id')}, "
                      f"dwarf_verdict={nt.get('dwarf_verdict')}, name={nm!r}")
if q2b_count == 0:
    print("  (none found)")
print(f"  TOTAL null hits: {q2b_count}")

# ── Q3: reason_counts variation across combos ─────────────────────────────────
print()
print("=" * 80)
print("Q3: reason_counts — which reasons appear in which (test_case, opt)")
print("=" * 80)
reason_map = defaultdict(set)
all_combos = set()
for tc in test_cases:
    for opt in opt_levels:
        fp = root / tc / opt / variant / "join_dwarf_ts" / "alignment_report.json"
        if not fp.exists():
            continue
        all_combos.add((tc, opt))
        data = json.loads(fp.read_text(encoding="utf-8"))
        rc = data.get("reason_counts", {})
        for reason in rc:
            reason_map[reason].add((tc, opt))

print(f"  Total (tc, opt) combos with alignment_report: {len(all_combos)}")
print(f"  All reason keys found: {sorted(reason_map.keys())}")
for reason in sorted(reason_map.keys()):
    combos = reason_map[reason]
    missing = all_combos - combos
    if missing:
        missing_list = sorted(missing)
        print(f"  reason '{reason}' missing from {len(missing)} combos:")
        for m in missing_list:
            print(f"    - {m[0]}/{m[1]}")
    else:
        print(f"  reason '{reason}' present in ALL {len(all_combos)} combos")

# ── Q4: build_receipt — artifact=null ─────────────────────────────────────────
print()
print("=" * 80)
print("Q4: build_receipt.json — builds with artifact=null")
print("=" * 80)
q4_count = 0
for tc in test_cases:
    fp = root / tc / "build_receipt.json"
    if not fp.exists():
        print(f"  {tc}: NO build_receipt.json found")
        continue
    data = json.loads(fp.read_text(encoding="utf-8"))
    for b in data.get("builds", []):
        if b.get("artifact") is None:
            q4_count += 1
            print(f"  {tc}: opt={b.get('optimization')}, variant={b.get('variant')}, "
                  f"status={b.get('status')}, artifact=None")
    # show non-success builds regardless
    for b in data.get("builds", []):
        if b.get("status") != "success":
            print(f"  {tc}: NON-SUCCESS build — opt={b.get('optimization')}, "
                  f"variant={b.get('variant')}, status={b.get('status')}, "
                  f"artifact={'present' if b.get('artifact') else 'None'}")
if q4_count == 0:
    print("  (all builds have non-null artifact)")
print(f"  TOTAL artifact=null: {q4_count}")
