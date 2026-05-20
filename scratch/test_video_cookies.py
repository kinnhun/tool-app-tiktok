import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from scraper.tiktok_scraper import _extract_pdp_url_from_video, _build_requests_session, _get_session_cookies

async def test():
    # Use the hiker session to get cookies
    session_dir = os.path.join(os.getcwd(), "tiktok_session_https___www.tiktok.com_@hiki_cosmetics")
    cookies = await _get_session_cookies(custom_session_dir=session_dir)
    session = _build_requests_session(cookies)
    
    url = "https://www.tiktok.com/@basicman869/video/757880057313943885"
    
    # Custom extract with session
    resp = session.get(url, timeout=10)
    html = resp.text
    if "captcha" in html.lower() or "security check" in html.lower() or "UNIVERSAL_DATA" not in html:
        print("Failed to bypass CAPTCHA with cookies!")
        print(html[:500])
    else:
        print("SUCCESS! Video page loaded with cookies!")

if __name__ == "__main__":
    asyncio.run(test())
