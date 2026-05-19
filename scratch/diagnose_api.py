import asyncio
import sys
from playwright.async_api import async_playwright

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_response(response):
            if "/api/" in response.url:
                print(f"API: {response.url}")
                try:
                    data = await response.json()
                    if "itemList" in data:
                        print(f"-> Contains itemList with {len(data['itemList'])} items")
                except:
                    pass

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        await asyncio.sleep(5)
        print("Clicking Liked tab...")
        try:
            await page.locator("[data-e2e='liked-tab']").click(timeout=10000, force=True)
            print("Clicked!")
        except Exception as e:
            print("Failed to click:", e)
        
        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
