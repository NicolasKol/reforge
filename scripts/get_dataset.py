from datasets import load_dataset
import re

ds = load_dataset("LLM4Binary/decompile-bench", split="train", streaming=True)

def is_plain_c_row(ex):
    code = ex["code"]
    file = ex.get("file","")
    # Start very strict: only .c files and no obvious C++ constructs
    if not file.endswith(".c"):
        return False
    if "::" in code or "class " in code or "std::" in code or "template" in code:
        return False
    # avoid code that likely needs project headers
    if '#include "' in code:
        return False
    # must look like a function definition
    return bool(re.search(r"\)\s*\{", code))

picked = []
for ex in ds:
    if is_plain_c_row(ex):
        picked.append(ex)
    if len(picked) >= 20:
        break

print("picked", len(picked))
print("example keys:", picked[0].keys())
print("name:", picked[0]["name"])
print("file:", picked[0]["file"])
print(picked[0]["code"][:400])
