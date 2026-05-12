"""
TikTok Scraper - Ultra Fast V2 for Render
More resilient product extraction without browser.
"""

import re
import json
import os
import requests
from datetime import datetime

SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_session", "cookies.json")

def _get_stored_cookies():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f: return json.load(f)
        except: pass
    return []

def _build_session():
    session = requests.Session()
    # Desktop headers are sometimes more stable for price scraping
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.tiktok.com/",
        "Cache-Control": "no-cache",
    })
    return session

def _parse_pdp_html(html, url):
    details = {
        'product_name': '', 'current_price': '', 'original_price': '', 'sale_price': '',
        'product_link': url, 'shop_name': '', 'note': '', 'product_images': [],
    }
    
    # Clean HTML from escapes
    html = html.replace('\\"', '"').replace('\\/', '/')
    
    # Name
    name_match = re.search(r'"title":"([^"]+)"', html)
    if name_match: details['product_name'] = name_match.group(1)
    
    if not details['product_name']:
        name_match = re.search(r'<title>(.*?)</title>', html)
        if name_match: details['product_name'] = name_match.group(1).replace(" - TikTok Shop", "")

    # Prices
    # Search for price patterns like "₫123.456" or "123.456₫"
    price_patterns = [
        r'₫\s*([\d.]+)',
        r'([\d.]+)\s*₫',
        r'"sale_price":"([\d.]+)"',
        r'"price":\s*(\d+)'
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, html)
        if match:
            val = match.group(1)
            if val.isdigit() and int(val) > 1000:
                details['current_price'] = f"₫{int(val):,}".replace(",", ".")
                break
            elif "." in val:
                details['current_price'] = f"₫{val}"
                break
                
    details['sale_price'] = details['current_price']
    return details

def _get_pdp_url(video_url):
    """Scan video page for ANY product links."""
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"}
    try:
        resp = requests.get(video_url, headers=headers, timeout=10, allow_redirects=True)
        html = resp.text
        
        # Strategy 1: Look for explicit /pdp/ or /product/ links
        pdp_match = re.search(r'(https?://[a-zA-Z0-9.-]*tiktok\.com/[^"\'\s]*/(?:pdp|product)/[\d]+)', html)
        if pdp_match:
            return pdp_match.group(1), ""
            
        # Strategy 2: Scan JSON data
        json_matches = re.findall(r'id="__[A-Z_]+__"[^>]*>([^<]+)</script>', html)
        for json_str in json_matches:
            # Look for seo_url directly in string to avoid complex parsing
            seo_match = re.search(r'"seo_url":"(https?://[^"]+)"', json_str)
            if seo_match:
                url = seo_match.group(1).replace("\\u002F", "/")
                title_match = re.search(r'"title":"([^"]+)"', json_str)
                return url, title_match.group(1) if title_match else ""
                
    except Exception as e:
        print(f"  ⚠ Lỗi lấy PDP URL: {e}")
    return None, ''

async def scrape_tiktok_product(url):
    print(f"🚀 [Webhook] Xử lý: {url[:50]}...")
    
    pdp_url = url
    name_fallback = ''
    
    if '/pdp/' not in url and 'shop.tiktok' not in url:
        pdp_url, name_fallback = _get_pdp_url(url)
        
    if not pdp_url:
        print("  ❌ Không tìm thấy link sản phẩm")
        return {'status': 'Cần mở App', 'note': 'Video này không chứa link sản phẩm web-view'}

    print(f"  → Truy cập trang sản phẩm: {pdp_url[:50]}...")
    session = _build_session()
    try:
        resp = session.get(pdp_url, timeout=15)
        if resp.status_code == 200:
            result = _parse_pdp_html(resp.text, pdp_url)
            if not result['product_name']: result['product_name'] = name_fallback
            
            if result['current_price']:
                result['status'] = 'Thành công'
                print(f"  ✅ Lấy được giá: {result['current_price']}")
                return result
            else:
                print("  ⚠ Không tìm thấy giá trong HTML")
    except Exception as e:
        print(f"  ❌ Lỗi truy cập: {e}")
        
    return {'status': 'Lỗi', 'note': 'Không lấy được giá (TikTok chặn hoặc hết hạn session)'}

def validate_tiktok_url(url): return (True, "OK")
async def process_single_link(url): return await scrape_tiktok_product(url)
def process_single_link_sync(url): import asyncio; return asyncio.run(process_single_link(url))
