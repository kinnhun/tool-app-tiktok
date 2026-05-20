import sys
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi import requests
import json
import re

def test_direct_scrape():
    url = "https://www.tiktok.com/@noithatmanhphi/video/7461821741753989384"
    print("Testing direct scrape with curl_cffi...")
    
    session = requests.Session(impersonate="chrome120")
    
    # 1. Get homepage to get cookies (ttwid)
    print("1. Fetching homepage for cookies...")
    session.get("https://www.tiktok.com/", timeout=10)
    print("Cookies obtained:", session.cookies.get_dict())
    
    # 2. Fetch video page
    print("2. Fetching video page...")
    resp = session.get(url, timeout=10)
    
    html = resp.text
    matches = re.findall(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', html)
    if matches:
        u_data = json.loads(matches[0])
        video_detail = u_data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {})
        if video_detail and video_detail.get('itemInfo'):
            print("✅ SUCCESS! Extracted video detail.")
            return True
        else:
            print("❌ Extracted data but no video detail found (might be blocked).")
            print(html[:500])
    else:
        print("❌ No UNIVERSAL_DATA found.")
        if "captcha" in html.lower():
            print("Got CAPTCHA page!")
        else:
            print(html[:500])

if __name__ == "__main__":
    test_direct_scrape()
