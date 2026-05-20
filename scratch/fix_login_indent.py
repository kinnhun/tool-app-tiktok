import sys

with open("scraper/tiktok_scraper.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    # Fix lines 84 to 145: unindent by 4 spaces
    if 83 <= i <= 144: # i is 0-indexed, so lines 84 to 145
        if line.startswith("    "):
            new_lines.append(line[4:])
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)

with open("scraper/tiktok_scraper.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("login_tiktok_async indentation fixed")
