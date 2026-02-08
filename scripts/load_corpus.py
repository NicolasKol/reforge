import os
import requests
from pathlib import Path

API_URL = "http://localhost:8080/builder/synthetic"

def submit_program(name, source_code, category):
    payload = {
        "name": name,
        "source_code": source_code,
        "test_category": category,
        "language": "c",
        "compilers": ["gcc"],
        "optimizations": ["O0", "O1", "O2", "O3"]
    }
    response = requests.post(API_URL, json=payload)
    return response.json()

# Process directory
category = "simple_programs"
source_dir = Path("C:\\Users\\nico_\\Documents\\UNI\\Thesis\\Source\\reforge\\C-Programs\\test")

for c_file in source_dir.glob("*.c"):
    name = c_file.stem  # filename without .c
    source_code = c_file.read_text()
    
    print(f"Submitting {name}...")
    result = submit_program(name, source_code, category)
    print(f"  Job ID: {result['job_id']}")