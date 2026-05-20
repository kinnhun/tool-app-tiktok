import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome120")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
        url = "https://www.tiktok.com/api/item/detail/?itemId=757880057313943885"
        resp = session.get(url, headers=headers, timeout=10)
        print("Status:", resp.status_code)
        print(resp.text[:500])
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
