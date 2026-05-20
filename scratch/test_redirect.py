import asyncio
from cloakbrowser import launch_persistent_context_async
import os

async def test():
    session_dir = os.path.join(os.getcwd(), "test_session_redirect")
    launch_kwargs = {
        'headless': False,
        'args': ['--disable-blink-features=AutomationControlled', '--no-sandbox'],
        'user_agent': "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        'viewport': {'width': 375, 'height': 812},
        'is_mobile': True,
        'has_touch': True,
        'humanize': True
    }
    context = await launch_persistent_context_async(user_data_dir=session_dir, **launch_kwargs)
    
    async def block_redirects(route):
        url = route.request.url
        if url.startswith("snssdk") or "tiktokv.com/redirect" in url or url.startswith("intent"):
            print("Blocked redirect to:", url)
            await route.abort()
        else:
            await route.continue_()
            
    await context.route("**/*", block_redirects)
    
    page = context.pages[0] if context.pages else await context.new_page()
    url = "https://www.tiktok.com/@whitep.0410/video/7637372125182987538"
    print("Navigating to video...")
    try:
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        print("Success! Page URL:", page.url)
    except Exception as e:
        print("Goto failed:", e)
    
    await asyncio.sleep(5)
    await context.close()

if __name__ == "__main__":
    asyncio.run(test())
