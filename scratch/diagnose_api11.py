import asyncio
from playwright.async_api import async_playwright
import re
import json

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        await asyncio.sleep(3)
        
        content = await page.content()
        match = re.search(r'"secUid":"([^"]+)"', content)
        if match:
            secUid = match.group(1)
            print(f"FOUND secUid: {secUid}")
            
            api_url = f"https://www.tiktok.com/api/favorite/item_list/?count=30&secUid={secUid}&cursor=0"
            print(f"Going to API: {api_url}")
            await page.goto(api_url)
            await asyncio.sleep(2)
            
            api_content = await page.evaluate("document.body.innerText")
            try:
                data = json.loads(api_content)
                if "itemList" in data:
                    print(f"SUCCESS! Got {len(data['itemList'])} items!")
                else:
                    print("Failed to get itemList. Keys:", list(data.keys()))
            except Exception as e:
                print("Failed to parse JSON")
        else:
            print("Could not find secUid")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
