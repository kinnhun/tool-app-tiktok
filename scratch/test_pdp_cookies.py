import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper.tiktok_scraper import _get_session_cookies, _build_requests_session

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session_dir = os.path.join(os.getcwd(), "dist", "tiktok_session_https___www.tiktok.com_@hiki_cosmetics")
        cookies = await _get_session_cookies(custom_session_dir=session_dir)
        print("Cookies read:", len(cookies))
        
        session = cffi_requests.Session(impersonate="safari_ios")
        for c in cookies:
            session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
            
        url = "https://www.tiktok.com/shop/vn/pdp/set-quan-ao-nam-nu-uma-vai-cotton-thoang-mat-thoi-trang-the-thao/1731952104423983818"
        resp = session.get(url, timeout=10)
        html = resp.text
        if "captcha" in html.lower() or "security check" in html.lower():
            print("Failed PDP with safari_ios and cookies")
        else:
            print("SUCCESS PDP with safari_ios and cookies!")
            print("Length:", len(html))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
