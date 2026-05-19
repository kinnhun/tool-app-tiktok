import re
import json

try:
    with open('video_page.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    matches = re.findall(r'id=\"__UNIVERSAL_DATA_FOR_REHYDRATION__\"[^>]*>([^<]+)</script>', html)
    if matches:
        data = json.loads(matches[0])
        # Save JSON for inspection
        with open('debug_universal.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        def find_keys(obj, target_key):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == target_key:
                        print(f"FOUND KEY {k}: {str(v)[:200]}")
                    find_keys(v, target_key)
            elif isinstance(obj, list):
                for item in obj:
                    find_keys(item, target_key)
                    
        print("Searching for 'anchors'...")
        find_keys(data, 'anchors')
        
        print("\nSearching for 'seo_url'...")
        find_keys(data, 'seo_url')
        
except Exception as e:
    print("Error:", e)
