import json
import asyncio
import re
import requests
from scraper.tiktok_scraper import _get_session_cookies, _build_requests_session

async def main():
    cookies = await _get_session_cookies()
    session = _build_requests_session(cookies)
    url = 'https://www.tiktok.com/shop/vn/pdp/ban-hoc-gap-gon-%C4%91a-nang-ban-lam-viec-hoc-sinh-mat-go-mdf-tien-loi/1730664199026674480'
    resp = session.get(url)
    match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', resp.text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        with open('debug_pdp_table.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("✅ Dumped router data to debug_pdp_table.json")
    else:
        print("❌ Could not find router data")

if __name__ == "__main__":
    asyncio.run(main())
