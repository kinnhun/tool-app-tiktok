import PyInstaller.__main__
import os
import shutil
import sys

def build():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
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
        '--name=TikTokScraper_v6.34',
        '--add-data=static;static',
        '--collect-all=playwright_stealth',
        '--hidden-import=playwright',
        '--hidden-import=playwright_stealth',
        '--hidden-import=cloakbrowser',
        '--hidden-import=requests',
        '--hidden-import=flask_cors',
        '--hidden-import=gspread',
        '--hidden-import=google.oauth2.service_account',
        '--hidden-import=curl_cffi',
        '--collect-all=playwright',
        '--collect-all=curl_cffi',
        '--collect-all=cloakbrowser',
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
