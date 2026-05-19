import asyncio
import json
import re
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        url = 'https://www.tiktok.com/shop/vn/pdp/ban-hoc-gap-gon-%C4%91a-nang-ban-lam-viec-hoc-sinh-mat-go-mdf-tien-loi/1730664199026674480'
        await page.goto(url, wait_until='domcontentloaded')
        content = await page.content()
        match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', content, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            try:
                state = data['queries'][0]['state']['data']
                promo = state['promotion_model']['promotion_product_price']['min_price']
                print(json.dumps(promo, indent=2, ensure_ascii=False))
            except Exception as e:
                print(f"Error: {e}")
        else:
            print("Router data not found")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
