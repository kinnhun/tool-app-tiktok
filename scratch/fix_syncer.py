import re

with open("scraper/favorites_syncer.py", "r", encoding="utf-8") as f:
    content = f.read()

new_content = content.replace(
    'f"tiktok_session_{profile_name}"',
    'f"tiktok_session_{__import__(\'re\').sub(r\'[\\\\\\\\/:*?\\\"<>|]\', \'_\', profile_name)}"'
)

with open("scraper/favorites_syncer.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("favorites_syncer.py patched successfully")
