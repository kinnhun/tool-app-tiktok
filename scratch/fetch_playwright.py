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
            with open('scratch/table_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("✅ Data saved to scratch/table_data.json")
        else:
            print("❌ Router data not found")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
