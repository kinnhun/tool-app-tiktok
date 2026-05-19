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
                    target_api = response.url

        page.on("response", handle_response)
        
        print("Navigating...")
        await page.goto("https://www.tiktok.com/@hiki_cosmetics")
        
        for _ in range(10):
            if target_api: break
            await asyncio.sleep(1)
            
        if target_api:
            # Lấy URL parameter
            parsed = urllib.parse.urlparse(target_api)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            if 'X-Bogus' in params: del params['X-Bogus']
            if 'msToken' in params: del params['msToken']
            
            params['cursor'] = '0'
            new_query = urllib.parse.urlencode(params)
            new_url = f"{parsed.scheme}://{parsed.netloc}/api/favorite/item_list/?{new_query}"
            
            # Fetch from page context
            print("Fetching from page context...")
            try:
                data = await page.evaluate(f"""async () => {{
                    const res = await fetch('{new_url}');
                    return await res.json();
                }}""")
                if "itemList" in data:
                    print(f"SUCCESS! Got {len(data['itemList'])} items!")
                else:
                    print("Failed. Keys:", list(data.keys()))
            except Exception as e:
                print("Error:", e)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
