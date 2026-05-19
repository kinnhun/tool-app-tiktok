import asyncio
from playwright.async_api import async_playwright
import json

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Inject script to intercept fetch
        await page.add_init_script("""
            const originalFetch = window.fetch;
            window.fetch = async (...args) => {
                console.log('FETCH_INTERCEPTED:', args[0]);
                return originalFetch(...args);
            };
            const originalXhrOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url) {
                console.log('XHR_INTERCEPTED:', url);
                originalXhrOpen.apply(this, arguments);
            };
        """)
        
        page.on("console", lambda msg: print(f"BROWSER: {msg.text}") if "INTERCEPTED" in msg.text else None)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        await asyncio.sleep(5)
        
        # Đóng popup
        for _ in range(3):
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            
        print("Trying to click Liked tab...")
        try:
            icon_locator = page.locator("svg path[d^='M24 12.19'] >> xpath=ancestor::*[self::p or self::div or @role='tab']").first
            await icon_locator.click(force=True)
            print("Clicked with force=True")
        except Exception as e:
            print("Failed to click:", e)
            
        await asyncio.sleep(10)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
