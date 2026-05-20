import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="safari_ios")
        url = "https://www.tiktok.com/shop/vn/pdp/set-quan-ao-nam-nu-uma-vai-cotton-thoang-mat-thoi-trang-the-thao/1731952104423983818"
        resp = session.get(url, timeout=10)
        html = resp.text
        if "captcha" in html.lower() or "security check" in html.lower():
            print("Failed PDP with safari_ios")
        else:
            print("SUCCESS PDP with safari_ios!")
            print("Length:", len(html))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
