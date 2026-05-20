import sys
import os
import asyncio
import json
import re
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

async def test():
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="safari_ios")
        url = "https://www.tiktok.com/@whitep.0410/video/7637372125182987538"
        resp = session.get(url, timeout=10)
        html = resp.text
        matches = re.findall(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', html)
        if matches:
            u_data = json.loads(matches[0])
            with open("scratch/universal_data.json", "w", encoding="utf-8") as f:
                json.dump(u_data, f, ensure_ascii=False, indent=2)
            print("Saved to universal_data.json")
        else:
            print("No UNIVERSAL_DATA found")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
