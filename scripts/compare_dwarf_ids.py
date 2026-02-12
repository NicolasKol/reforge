"""Compare dwarf_function_id values across O0 and O1 for all synthetic test cases."""
import json
import os

base = r"c:\Users\nico_\Documents\UNI\Thesis\Source\reforge\docker\local-files\artifacts\synthetic"
tests = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])


def extract(data):
    """Build name -> [list of dwarf_function_id] from pairs + non_targets."""
    result = {}
    for p in data.get("pairs", []):
        name = p.get("dwarf_function_name", "?")
        fid = p.get("dwarf_function_id", "?")
        result.setdefault(name, []).append(fid)
    for p in data.get("non_targets", []):
        name = p.get("name", "?")
        fid = p.get("dwarf_function_id", "?")
        result.setdefault(name, []).append(fid)
    return result


total_same = 0
total_diff = 0

for test in tests:
    o0_path = os.path.join(base, test, "O0", "debug", "join_dwarf_ts", "alignment_pairs.json")
    o1_path = os.path.join(base, test, "O1", "debug", "join_dwarf_ts", "alignment_pairs.json")
    if not (os.path.exists(o0_path) and os.path.exists(o1_path)):
        print(f"\n=== {test}: MISSING one or both files ===")
        continue

    with open(o0_path) as f:
        o0 = json.load(f)
    with open(o1_path) as f:
        o1 = json.load(f)

    map0 = extract(o0)
    map1 = extract(o1)

    all_names = sorted(set(map0.keys()) | set(map1.keys()), key=lambda x: (x is None, x or ""))

    print(f"\n{'='*120}")
    print(f"  TEST CASE: {test}")
    print(f"{'='*120}")
    hdr = f"  {'Function Name':<30} {'O0 dwarf_function_id':<30} {'O1 dwarf_function_id':<30} {'Same?'}"
    print(hdr)
    print(f"  {'-'*30} {'-'*30} {'-'*30} {'-'*5}")

    for name in all_names:
        display_name = name if name is not None else "(None)"
        ids0 = map0.get(name, ["(absent)"])
        ids1 = map1.get(name, ["(absent)"])
        max_len = max(len(ids0), len(ids1))
        for i in range(max_len):
            id0 = ids0[i] if i < len(ids0) else "(absent)"
            id1 = ids1[i] if i < len(ids1) else "(absent)"
            id0 = id0 if id0 is not None else "(None)"
            id1 = id1 if id1 is not None else "(None)"
            same = "YES" if id0 == id1 else "NO"
            if id0 == id1:
                total_same += 1
            else:
                total_diff += 1
            label = display_name if i == 0 else f"  {display_name} [dup {i}]"
            print(f"  {label:<30} {id0:<30} {id1:<30} {same}")

print(f"\n{'='*120}")
print(f"  SUMMARY")
print(f"{'='*120}")
print(f"  Total comparisons: {total_same + total_diff}")
print(f"  Same ID across O0/O1:  {total_same}")
print(f"  Different ID:          {total_diff}")
print(f"  Pct same: {100*total_same/(total_same+total_diff):.1f}%")
