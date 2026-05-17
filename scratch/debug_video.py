import asyncio
from playwright.async_api import async_playwright
import json
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use session dir if exists
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        url = 'https://www.tiktok.com/@duykhang9966/video/76152889963898211592'
        print(f"Navigating to {url}")
        await page.goto(url, wait_until='networkidle')
        await asyncio.sleep(5)
        
        content = await page.content()
        with open('debug_video_playwright.html', 'w', encoding='utf-8') as f:
            f.write(content)
            
        # Find links
        links = await page.query_selector_all('a')
        print(f"Found {len(links)} links")
        for link in links:
            href = await link.get_attribute('href')
            text = await link.inner_text()
            if href and ('pdp' in href or 'product' in href or 'shop' in href):
                print(f"PDP LINK FOUND: {href} | Text: {text}")

        # Find prices
        import re
        prices = re.findall(r'₫\s*[\d.]+', content)
        print(f"Prices found in HTML: {prices}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
