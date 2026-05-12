"""
TikTok Scraper - Fast Version for Render (Low RAM)
Bypass Playwright and use direct requests.
"""

import re
import json
import os
import requests
from datetime import datetime

# Path to session cookies (if any)
SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_session", "cookies.json")

def _get_stored_cookies():
    """Load cookies from file if exists, otherwise return empty list."""
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return []

def _build_session():
    session = requests.Session()
    cookies = _get_stored_cookies()
    for c in cookies:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9",
        "Referer": "https://www.tiktok.com/",
    })
    return session

def _parse_pdp_html(html, url):
    details = {
        'product_name': '', 'current_price': '', 'original_price': '', 'sale_price': '',
        'product_link': url, 'shop_name': '', 'note': '', 'product_images': [],
    }
    
    # Name
    name_match = re.search(r'<h1[^>]*>.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
    if name_match: details['product_name'] = name_match.group(1).strip()
    
    # Prices - TikTok Shop VN format
    price_match = re.search(r'₫</span>.*?font-size:3[26]px[^>]*>([\d.]+)</span>', html, re.DOTALL)
    if price_match:
        details['current_price'] = f"₫{price_match.group(1)}"
        details['sale_price'] = details['current_price']
    
    orig_match = re.search(r'line-through[^>]*>[\s]*([\d.]+)₫', html)
    if orig_match: details['original_price'] = f"₫{orig_match.group(1)}"
    
    # Fallback
    if not details['current_price']:
        prices = re.findall(r'([\d]{1,3}(?:\.[\d]{3})+)\s*₫', html)
        if prices: details['current_price'] = f"₫{prices[0]}"
        
    return details

def _get_pdp_url(video_url):
    """Extract PDP URL from video page using simple requests."""
    try:
        resp = requests.get(video_url, headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)"}, timeout=10)
        # Look for the hidden JSON data
        match = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', resp.text)
        if match:
            data = json.loads(match.group(1))
            # Drill down to find the shop anchor
            item = data.get('__DEFAULT_SCOPE__', {}).get('webapp.reflow.video.detail', {}).get('itemInfo', {}).get('itemStruct', {})
            for anchor in item.get('anchors', []):
                extra = json.loads(anchor.get('extra', '{}'))
                if isinstance(extra, list): extra = extra[0]
                inner = json.loads(extra.get('extra', '{}')) if isinstance(extra.get('extra'), str) else extra
                if inner.get('seo_url'):
                    return inner['seo_url'], inner.get('title', '')
    except: pass
    return None, ''

async def scrape_tiktok_product(url):
    """Ultra-fast version: NO BROWSER, NO RAM ISSUES."""
    print(f"🚀 [Scraper] Đang xử lý: {url[:50]}...")
    
    pdp_url = url
    name_fallback = ''
    
    if '/pdp/' not in url and 'shop.tiktok' not in url:
        print("  → Phân tích link video...")
        pdp_url, name_fallback = _get_pdp_url(url)
        
    if not pdp_url:
        return {'status': 'Cần mở App', 'note': 'Không tìm thấy sản phẩm hoặc link Affiliate'}

    print(f"  → Đang lấy giá từ: {pdp_url[:50]}...")
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
    except Exception as e:
        print(f"  ❌ Lỗi: {e}")
        
    return {'status': 'Lỗi', 'note': 'Không lấy được giá (có thể bị chặn)'}

def validate_tiktok_url(url): return (True, "OK")
async def process_single_link(url): return await scrape_tiktok_product(url)
def process_single_link_sync(url): import asyncio; return asyncio.run(process_single_link(url))
