import re

with open("scraper/tiktok_scraper.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip_try = False

for i, line in enumerate(lines):
    # Found the outer try:
    if line.startswith("        try:") and lines[i+1].startswith("            try:"):
        # Skip this outer try:
        skip_try = True
        continue
    
    # If we are in the block that was indented, unindent it by 4 spaces
    # The block ends around line 1244 when we see "return result" at 12 spaces indent
    # Wait, in the original code, the return result was inside the "async with" block (12 spaces)
    if skip_try:
        if line.startswith("            return result"):
            # This was inside the async with block, unindent to 8 spaces
            new_lines.append(line[4:])
            # Now we are done with the block!
            skip_try = False
            continue
        elif line.startswith("    "):
            # Unindent 4 spaces
            if len(line) >= 4 and line[:4] == "    ":
                new_lines.append(line[4:])
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            skip_try = False
    else:
        new_lines.append(line)

with open("scraper/tiktok_scraper.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("tiktok_scraper.py unindented successfully")
