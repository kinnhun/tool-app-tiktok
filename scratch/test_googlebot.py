import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper.tiktok_scraper import _extract_pdp_url_from_video

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome120")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
        url = "https://www.tiktok.com/@basicman869/video/757880057313943885"
        resp = session.get(url, headers=headers, timeout=10)
        html = resp.text
        if "captcha" in html.lower() or "security check" in html.lower() or "UNIVERSAL_DATA" not in html:
            print("Failed to bypass CAPTCHA with Googlebot!")
            print(html[:500])
        else:
            print("SUCCESS! Video page loaded with Googlebot!")
            import re
            matches = re.findall(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', html)
            print("Found UNIVERSAL_DATA:", len(matches))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
