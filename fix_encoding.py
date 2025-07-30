# fix_encoding.py
input_file = "requirements.txt"
output_file = "requirements_fixed.txt"

with open(input_file, "r", encoding="cp1252") as f:
    contents = f.read()

with open(output_file, "w", encoding="utf-8") as f:
    f.write(contents)

print(f"✅ Fixed encoding written to {output_file}")
