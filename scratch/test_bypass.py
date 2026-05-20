import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper.tiktok_scraper import login_tiktok_async

async def run_test():
    url = "https://www.tiktok.com/@noithatmanhphi/video/7461821741753989384"
    print("Testing CAPTCHA bypass with CloakBrowser...")
    success = await login_tiktok_async(url)
    if success:
        print("✅ SUCCESS! Bypassed Captcha and logged in/loaded page.")
    else:
        print("❌ FAILED to bypass.")

if __name__ == "__main__":
    asyncio.run(run_test())
