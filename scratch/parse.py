import re, json

with open('page.html', encoding='utf-16') as f:
    html = f.read()

m = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', html, re.DOTALL)
if m:
    data = json.loads(m.group(1))
    
    loaderData = data.get('loaderData', {})
    
    print(f"Keys in loaderData: {list(loaderData.keys())}")
    
    for k, v in loaderData.items():
        if isinstance(v, dict):
            print(f"\n--- Key: {k} ---")
            names = re.findall(r'"name":"([^"]+)"', json.dumps(v))
            if names:
                print(f"Names found: {list(set(names))[:5]}")
