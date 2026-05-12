"""
TikTok Scraper - Final Resilient Version
Using deep JSON inspection found by subagent.
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
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": "https://www.tiktok.com/",
    })
    return session

def _parse_pdp_html(html, url):
    details = {'product_name': '', 'current_price': '', 'original_price': '', 'sale_price': '', 'product_link': url, 'shop_name': '', 'note': '', 'product_images': []}
    
    # Extract price using multiple patterns
    # Pattern 1: Standard VN format (₫123.456)
    price_match = re.search(r'₫\s*([\d.]+)', html)
    if price_match:
        details['current_price'] = f"₫{price_match.group(1)}"
    
    # Pattern 2: JSON price
    if not details['current_price']:
        price_json = re.search(r'"price":\s*"?(\d+)"?', html)
        if price_json:
            p = int(price_json.group(1))
            if p > 1000: details['current_price'] = f"₫{p:,}".replace(",", ".")

    # Name
    name_match = re.search(r'"title":"([^"]+)"', html)
    if name_match: details['product_name'] = name_match.group(1).encode().decode('unicode_escape', 'ignore')
    
    if not details['product_name']:
        title_match = re.search(r'<title>(.*?)</title>', html)
        if title_match: details['product_name'] = title_match.group(1).replace(" - TikTok Shop", "")

    details['sale_price'] = details['current_price']
    return details

def _get_pdp_url(video_url):
    """Deep scan for product anchors (Type 33)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"}
    try:
        resp = requests.get(video_url, headers=headers, timeout=10)
        html = resp.text
        
        # Look for the massive data object
        data_match = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', html)
        if data_match:
            try:
                data = json.loads(data_match.group(1))
                # New path found by subagent
                item_info = data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {}).get('itemInfo', {})
                if not item_info:
                    # Fallback path
                    for key in data.get('__DEFAULT_SCOPE__', {}).keys():
                        if 'video.detail' in key:
                            item_info = data['__DEFAULT_SCOPE__'][key].get('itemInfo', {})
                            break
                
                anchors = item_info.get('itemStruct', {}).get('anchors', [])
                for anchor in anchors:
                    if anchor.get('type') == 33 or 'product' in str(anchor).lower():
                        extra_str = anchor.get('extra', '{}')
                        extra = json.loads(extra_str) if isinstance(extra_str, str) else extra
                        
                        # Support list or dict in extra
                        items = extra if isinstance(extra, list) else [extra]
                        for it in items:
                            # Final product link
                            p_url = it.get('seo_url')
                            if p_url:
                                return p_url, it.get('title', '')
            except: pass

        # Emergency Fallback: Regex for any PDP link in the whole page
        fallback_match = re.search(r'(https?://[a-zA-Z0-9.-]*tiktok\.com/[^"\'\s]*/(?:pdp|product)/[\d]+)', html)
        if fallback_match:
            return fallback_match.group(1), ""
            
    except: pass
    return None, ''

async def scrape_tiktok_product(url):
    print(f"🚀 [Scraper] Bắt đầu: {url[:50]}...")
    pdp_url, name_fallback = _get_pdp_url(url)
    
    if not pdp_url:
        print("  ❌ Không tìm thấy giỏ hàng trong video này.")
        return {'status': 'Cần mở App', 'note': 'Không tìm thấy giỏ hàng (Có thể là video thường hoặc link bị ẩn)'}

    print(f"  → Đã tìm thấy link sản phẩm ẩn. Đang lấy giá...")
    session = _build_session()
    try:
        resp = session.get(pdp_url, timeout=15)
        if resp.status_code == 200:
            result = _parse_pdp_html(resp.text, pdp_url)
            if not result['product_name']: result['product_name'] = name_fallback
            if result['current_price']:
                result['status'] = 'Thành công'
                print(f"  ✅ Thành công: {result['current_price']}")
                return result
    except Exception as e:
        print(f"  ❌ Lỗi: {e}")
        
    return {'status': 'Lỗi', 'note': 'TikTok chặn truy cập trực tiếp'}

def validate_tiktok_url(url): return (True, "OK")
async def process_single_link(url): return await scrape_tiktok_product(url)
def process_single_link_sync(url): import asyncio; return asyncio.run(process_single_link(url))
