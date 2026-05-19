import requests
import re
import json
import asyncio
from scraper.tiktok_scraper import _get_session_cookies, _build_requests_session

async def main():
    url = 'https://www.tiktok.com/shop/vn/pdp/ban-hoc-gap-gon-%C4%91a-nang-ban-lam-viec-hoc-sinh-mat-go-mdf-tien-loi/1730664199026674480'
    cookies = await _get_session_cookies()
    session = _build_requests_session(cookies)
    resp = session.get(url)
    match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', resp.text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        # Find product info in queries
        queries = data.get('queries', [])
        for q in queries:
            q_data = q.get('state', {}).get('data', {})
            if 'product_info' in q_data:
                p_info = q_data['product_info']
                print("Keys in product_info:", p_info.keys())
                if 'skus' in p_info:
                    print(f"Found {len(p_info['skus'])} SKUs in product_info")
                
                # Check for promotion_model
                if 'promotion_model' in q_data:
                    promo = q_data['promotion_model']
                    price = promo.get('promotion_product_price', {}).get('min_price', {})
                    print("Promotion Min Price Info:", json.dumps(price, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
