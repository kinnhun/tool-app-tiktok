import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="safari_ios")
        url = "https://api22-normal-c-alisg.tiktokv.com/aweme/v1/aweme/detail/?aweme_id=757880057313943885"
        resp = session.get(url, timeout=10)
        print("Status:", resp.status_code)
        print(resp.text[:500])
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
