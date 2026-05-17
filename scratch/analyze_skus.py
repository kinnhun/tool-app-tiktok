import requests
import re
import json

def format_price(val):
    if not val: return "-"
    try:
        val = int(val)
        return f"{val:,}".replace(",", ".")
    except: return val

url = 'https://www.tiktok.com/shop/vn/pdp/ban-hoc-gap-gon-%C4%91a-nang-ban-lam-viec-hoc-sinh-mat-go-mdf-tien-loi/1730664199026674480'
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)
match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', resp.text, re.DOTALL)
if match:
    data = json.loads(match.group(1))
    product_info = data['queries'][0]['state']['data']['product_info']
    skus = product_info.get('skus', [])
    print(f"Total SKUs: {len(skus)}")
    for i, sku in enumerate(skus):
        p = sku.get('price', {})
        sale = p.get('sale_price') or p.get('sale_price_decimal')
        origin = p.get('original_price') or p.get('original_price_decimal')
        print(f"SKU {i}: Sale={format_price(sale)}, Origin={format_price(origin)}")
else:
    print("No router data")
