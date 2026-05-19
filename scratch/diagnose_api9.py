import asyncio
from playwright.async_api import async_playwright

async def test_tiktok():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Navigating to API directly...")
        api_url = "https://www.tiktok.com/api/favorite/item_list/?WebIdLastTime=1779038046&aid=1988&app_language=en&app_name=tiktok_web&browser_language=en-US&browser_name=Mozilla&browser_online=true&browser_platform=Win32&browser_version=5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F131.0.0.0%20Safari%2F537.36&channel=tiktok_web&cookie_enabled=true&count=30&coverFormat=2&cursor=0&data_collection_enabled=false&device_id=7640910209871070740&device_platform=web_pc&focus_state=true&history_len=2&is_fullscreen=false&is_page_visible=true&language=en&odinId=7640910128794862613&os=windows&priority_region=&referer=https%3A%2F%2Fwww.tiktok.com%2F%40hiki_cosmetics&region=VN&root_referer=https%3A%2F%2Fwww.tiktok.com%2F%40hiki_cosmetics&screen_height=720&screen_width=1280&secUid=MS4wLjABAAAAakfsIb3upnJhM0SfU2uWYbu3Dx2RmkR6sYBpq2P3oHQVrgJyj8H-zNpfvBVoNXBx&tz_name=Asia%2FBangkok&user_is_login=false&video_encoding=dash&webcast_language=en&msToken=&X-Bogus=DFSzsIROjQkANrJaC-yr8WmBqjqn"
        await page.goto(api_url)
        await asyncio.sleep(5)
        
        content = await page.content()
        print("API Content length:", len(content))
        print(content[:500])
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tiktok())
