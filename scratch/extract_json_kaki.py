import re
import json
import requests

url = 'https://www.tiktok.com/shop/vn/pdp/quan-kaki-nam-dang-ngan-tren-goi-thoi-trang-2025-mau-sac-%C4%91a-dang/1731227435493459116'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'}

try:
    r = requests.get(url, headers=headers)
    html = r.text
    
    match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', html, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        
        def find_prices(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if 'price' in k.lower() and isinstance(v, (str, int, float)):
                        print(f"FOUND {k}: {v}")
                    find_prices(v)
            elif isinstance(obj, list):
                for item in obj:
                    find_prices(item)
                    
        find_prices(data)
    else:
        print("JSON not found")
except Exception as e:
    print("Error:", e)
