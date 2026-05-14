import PyInstaller.__main__
import os
import shutil
import sys

def build():
    # 1. Clear previous builds
    # if os.path.exists('dist'):
    #     shutil.rmtree('dist')
    if os.path.exists('build'):
        shutil.rmtree('build')
    
    print("--- Bat dau qua trinh build EXE ---")

    # 2. PyInstaller arguments
    args = [
        'main.py',
        '--onefile',
        '--name=TikTokScraper_v2',
        '--add-data=static;static',
        '--hidden-import=playwright',
        '--hidden-import=flask_cors',
        '--hidden-import=gspread',
        '--hidden-import=google.oauth2.service_account',
        '--collect-all=playwright',
    ]

    try:
        PyInstaller.__main__.run(args)
        print("\n--- Build hoan tat! ---")
        print("File EXE nam trong thu muc 'dist/TikTokScraper.exe'")
        print("Luu y: Khi chay lan dau tren may khac, tool se tu dong tai trinh duyet Chromium.")
    except Exception as e:
        print(f"Loi khi build: {e}")

if __name__ == "__main__":
    build()
