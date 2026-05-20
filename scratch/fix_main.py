import re

with open("main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace line: session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
# With: session_dir = os.path.join(os.getcwd(), f"tiktok_session_{__import__('re').sub(r'[\\\\/:*?\\\"<>|]', '_', profile_name)}")

new_content = content.replace(
    'f"tiktok_session_{profile_name}"',
    'f"tiktok_session_{__import__(\'re\').sub(r\'[\\\\\\\\/:*?\\\"<>|]\', \'_\', profile_name)}"'
)

with open("main.py", "w", encoding="utf-8") as f:
    f.write(new_content)

print("main.py patched successfully")
