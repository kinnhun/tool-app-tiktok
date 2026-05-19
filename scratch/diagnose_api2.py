import asyncio
from playwright.async_api import async_playwright

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_response(response):
            if "/api/favorite/item_list/" in response.url or "/api/post/item_list/" in response.url:
                print(f"API CAUGHT: {response.url}")
                try:
                    data = await response.json()
                    if "itemList" in data:
                        print(f"-> Contains itemList with {len(data['itemList'])} items")
                        for item in data['itemList'][:3]:
                            print(f"- {item.get('id')} (type: {item.get('type')})")
                except Exception as e:
                    print("JSON Parse error:", e)

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        await asyncio.sleep(5)
        
        print("Closing modals with Escape...")
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        
        print("Clicking Liked tab...")
        try:
            await page.locator("[data-e2e='liked-tab']").click(timeout=10000)
            print("Clicked!")
        except Exception as e:
            print("Failed to click:", e)
        
        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
