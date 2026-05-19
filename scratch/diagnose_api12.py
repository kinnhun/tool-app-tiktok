import asyncio
from playwright.async_api import async_playwright
import json
import urllib.parse

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
                    target_api = response.url.replace("/api/post/item_list/", "/api/favorite/item_list/")
                    print(f"FOUND API TEMPLATE: {target_api}")

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        
        # Chờ cho đến khi bắt được API
        for _ in range(10):
            if target_api: break
            await asyncio.sleep(1)
            
        if target_api:
            print("Going directly to Favorite API...")
            await page.goto(target_api)
            await asyncio.sleep(2)
            content = await page.evaluate("document.body.innerText")
            try:
                data = json.loads(content)
                if "itemList" in data:
                    print(f"SUCCESS! Got {len(data['itemList'])} items!")
                    for item in data['itemList'][:3]:
                        print(f"- {item.get('id')}")
                else:
                    print("Failed. Keys:", list(data.keys()))
            except:
                print("Not JSON")
        else:
            print("Did not catch post_item_list")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
