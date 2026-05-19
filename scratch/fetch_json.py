import requests
import re
import json

url = 'https://www.tiktok.com/shop/vn/pdp/ban-hoc-gap-gon-%C4%91a-nang-ban-lam-viec-hoc-sinh-mat-go-mdf-tien-loi/1730664199026674480'
headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1'
}
resp = requests.get(url, headers=headers)
match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', resp.text, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    # Search for price data
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print("Could not find router data")
