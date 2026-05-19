import asyncio
from playwright.async_api import async_playwright
import time

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        async def handle_response(response):
            if "/api/" in response.url:
                try:
                    data = await response.json()
                    if "itemList" in data:
                        print(f"API CAUGHT ({response.url}): Contains itemList with {len(data['itemList'])} items")
                        for item in data['itemList'][:3]:
                            print(f"- {item.get('id')}")
                except:
                    pass

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
