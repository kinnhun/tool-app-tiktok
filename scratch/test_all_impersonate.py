import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        for imp in ["safari_ios", "chrome110", "edge99", "chrome120", "safari15_3"]:
            print(f"Testing PDP with {imp}...")
            session = cffi_requests.Session(impersonate=imp)
            url = "https://www.tiktok.com/shop/vn/pdp/set-quan-ao-nam-nu-uma-vai-cotton-thoang-mat-thoi-trang-the-thao/1731952104423983818"
            resp = session.get(url, timeout=10)
            html = resp.text
            if "captcha" in html.lower() or "security check" in html.lower() or "Verification failed" in html:
                print(f"Failed {imp}")
            else:
                print(f"SUCCESS PDP with {imp}!")
                return
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
