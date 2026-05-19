import requests
import json
import re
from urllib.parse import quote

def test_api():
    url = "https://www.tiktok.com/@hiki_cosmetics"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    # 1. Lấy secUid từ HTML
    res = requests.get(url, headers=headers)
    
    secUid = None
    # Tìm trong SIGI_STATE hoặc UNIVERSAL_DATA
    match = re.search(r'"secUid":"([^"]+)"', res.text)
    if match:
        secUid = match.group(1)
    
    print(f"Found secUid: {secUid}")
    
    if secUid:
        # 2. Gọi API yêu thích
        api_url = f"https://www.tiktok.com/api/favorite/item_list/?count=30&secUid={secUid}&cursor=0"
        
        api_headers = headers.copy()
        api_headers["Referer"] = url
        
        api_res = requests.get(api_url, headers=api_headers)
        print("API Status:", api_res.status_code)
        try:
            data = api_res.json()
            if "itemList" in data:
                print(f"API Returned {len(data['itemList'])} items!")
                for item in data['itemList'][:3]:
                    print(f"- {item['id']}")
            else:
                print("No itemList. Response:", list(data.keys()))
        except Exception as e:
            print("Failed to parse JSON:", e)
            print(api_res.text[:200])

if __name__ == "__main__":
    test_api()
