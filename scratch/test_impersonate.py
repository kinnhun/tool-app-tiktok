import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        for imp in ["safari_ios", "chrome110", "edge99"]:
            print(f"Testing {imp}...")
            session = cffi_requests.Session(impersonate=imp)
            url = "https://www.tiktok.com/@basicman869/video/757880057313943885"
            resp = session.get(url, timeout=10)
            html = resp.text
            if "UNIVERSAL_DATA" in html:
                print(f"SUCCESS with {imp}!")
                return
            else:
                print(f"Failed {imp}")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
