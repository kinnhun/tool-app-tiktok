import os
import sys
import asyncio
from playwright.async_api import async_playwright

async def run_diagnose():
    session_dir = r"D:\tool-app-tiktok\dist\tiktok_session_trss"
    screenshot_dir = r"C:\Users\trant\.gemini\antigravity\brain\3767ef99-c215-4382-938a-af202293013b"
    os.makedirs(screenshot_dir, exist_ok=True)
    
    print(f"Starting headful diagnosis...")
    print(f"Session Dir: {session_dir}")
    
    async with async_playwright() as p:
        kwargs = {
            'user_data_dir': session_dir,
            'headless': False, # Run headful to bypass bot detection!
            'args': [
                '--disable-blink-features=AutomationControlled', 
                '--no-sandbox', 
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--window-position=-2000,-2000', # Position off-screen!
                '--window-size=1280,720'
            ],
            'viewport': {'width': 1280, 'height': 720},
            'is_mobile': False,
            'has_touch': False,
            'locale': 'vi-VN',
            'timezone_id': 'Asia/Ho_Chi_Minh',
            'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        
        context = await p.chromium.launch_persistent_context(**kwargs)
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            from playwright_stealth import stealth_async
            # Wait, since stealth_async import fails, let's use the Stealth class!
            from playwright_stealth import Stealth
            await Stealth().stealth(page)
            print("Stealth applied successfully!")
        except Exception as e:
            print(f"Stealth bypass failed: {e}")
            
        print("Navigating to https://www.tiktok.com/profile...")
        await page.goto("https://www.tiktok.com/profile", timeout=60000, wait_until="domcontentloaded")
        
        print("Waiting 10 seconds for React components...")
        await asyncio.sleep(10)
        
        current_url = page.url
        print(f"Current URL: {current_url}")
        
        # Take initial screenshot
        sc1_path = os.path.join(screenshot_dir, "diagnose_profile_headful.png")
        await page.screenshot(path=sc1_path)
        print(f"Saved initial profile screenshot to: {sc1_path}")
        
        # Click the tab
        tab_clicked = False
        tab_selectors = [
            "p[class*='PFavorite']",
            "[class*='PFavorite']",
            "[data-e2e='favorites-tab']",
            "text=Yêu thích",
            "text=Favorites"
        ]
        for selector in tab_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    tab_clicked = True
                    print(f"Success: Clicked tab via CSS selector: {selector}")
                    break
            except:
                continue
                
        if tab_clicked:
            print("Tab clicked. Waiting 5 seconds for video grid to load...")
            await asyncio.sleep(5)
            
            sc2_path = os.path.join(screenshot_dir, "diagnose_tab_clicked_headful.png")
            await page.screenshot(path=sc2_path)
            print(f"Saved post-click screenshot to: {sc2_path}")
            
            elements = await page.query_selector_all('a[href*="/video/"]')
            print(f"Found {len(elements)} video elements.")
            for idx, el in enumerate(elements[:5]):
                href = await el.get_attribute('href')
                print(f"[{idx}] href: {href}")
        else:
            print("FAILED to click Favorites tab in headful!")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(run_diagnose())
