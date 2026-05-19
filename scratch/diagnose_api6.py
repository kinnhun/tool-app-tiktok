import asyncio
from playwright.async_api import async_playwright

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_response(response):
            if "collection_list" in response.url or "favorite/item_list" in response.url:
                print(f"\n=> API CAUGHT: {response.url}")
                try:
                    data = await response.json()
                    print(f"KEYS in JSON: {list(data.keys())}")
                    if "itemList" in data:
                        print(f"-> Contains itemList with {len(data['itemList'])} items")
                    elif "item_list" in data:
                        print(f"-> Contains item_list with {len(data['item_list'])} items")
                        for item in data['item_list'][:3]:
                            print(f"- {item.get('id', item.get('video', {}).get('id', 'unknown'))}")
                except Exception as e:
                    print("JSON Parse error:", e)

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        await asyncio.sleep(5)
        
        print("Trying to click Liked tab...")
        try:
            icon_locator = page.locator("svg path[d^='M24 12.19'] >> xpath=ancestor::*[self::p or self::div or @role='tab']").first
            await icon_locator.click(force=True)
            print("Clicked with force=True")
        except Exception as e:
            print("Failed to click:", e)
            
        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
