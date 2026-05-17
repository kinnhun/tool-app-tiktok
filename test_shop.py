import re, json, sys, requests
sys.stdout.reconfigure(encoding='utf-8')

video_url = "https://www.tiktok.com/@noithatmanhphi/video/7461821741753989384"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

resp = requests.get(video_url, headers=headers, timeout=10)
html = resp.text

matches = re.findall(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', html)
if matches:
    u_data = json.loads(matches[0])
    
    # Check webapp.video-detail
    video_detail = u_data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {})
    if video_detail:
        print("=== webapp.video-detail keys ===")
        for k in video_detail.keys():
            print(f"  {k}")
        
        item_info = video_detail.get('itemInfo', {})
        item_struct = item_info.get('itemStruct', {})
        
        if item_struct:
            author = item_struct.get('author', {})
            print(f"\n=== Author ===")
            for k, v in author.items():
                if isinstance(v, str) and v and len(v) < 200:
                    print(f"  {k}: {v}")
            
            print(f"\n=== itemStruct keys ===")
            for k in item_struct.keys():
                print(f"  {k}")
        else:
            print("\nNo itemStruct found")
            print(f"itemInfo keys: {list(item_info.keys())}")
    
    # Also check other scopes
    for sk, sv in u_data.get('__DEFAULT_SCOPE__', {}).items():
        if not isinstance(sv, dict): continue
        if 'video' not in sk.lower(): continue
        if sk == 'webapp.video-detail': continue
        print(f"\n=== Scope: {sk} ===")
        print(f"  Keys: {list(sv.keys())[:10]}")

# Also: extract @username from URL
author_match = re.search(r'tiktok\.com/@([^/?]+)', video_url)
if author_match:
    print(f"\n=== Username from URL: @{author_match.group(1)} ===")
