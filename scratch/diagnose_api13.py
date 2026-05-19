import asyncio
from playwright.async_api import async_playwright
import json
import urllib.parse
import re

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        target_api = None
        
        async def handle_response(response):
            nonlocal target_api
            if "/api/post/item_list/" in response.url:
                if not target_api:
                    # Đổi API path
                    api = response.url.replace("/api/post/item_list/", "/api/favorite/item_list/")
                    # Thử đổi count=16 thành count=100
                    api = re.sub(r'count=\d+', 'count=100', api)
                    target_api = api
                    print(f"FOUND API TEMPLATE: {target_api}")

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        
        for _ in range(10):
            if target_api: break
            await asyncio.sleep(1)
            
        if target_api:
            print("Going directly to Favorite API with count=100...")
            await page.goto(target_api)
            await asyncio.sleep(2)
            content = await page.evaluate("document.body.innerText")
            try:
                data = json.loads(content)
                if "itemList" in data:
                    print(f"SUCCESS! Got {len(data['itemList'])} items!")
                else:
                    print("Failed. Keys:", list(data.keys()))
            except:
                print("Not JSON")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
