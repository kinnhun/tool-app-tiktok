import json
import re
import os

def parse():
    if not os.path.exists('test_html.html'):
        print("File not found")
        return
    
    with open('test_html.html', 'r', encoding='utf-8') as f:
        html = f.read()
    
    match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', html, re.DOTALL)
    if not match:
        print("No ROUTER_DATA found")
        return
    
    data = json.loads(match.group(1))
    
    # Save a slice for inspection
    with open('router_data_sample.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("ROUTER_DATA saved to router_data_sample.json")

if __name__ == "__main__":
    parse()
