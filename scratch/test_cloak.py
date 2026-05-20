import asyncio
from cloakbrowser import launch_async

async def main():
    print("Launching CloakBrowser...")
    browser = await launch_async(headless=True)
    page = await browser.new_page()
    await page.goto("https://bot.sannysoft.com/")
    print(await page.title())
    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
