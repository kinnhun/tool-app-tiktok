"""
TikTok Scraper - Extracts product information from TikTok Shop videos.
Uses Playwright for session management + requests for data extraction.
"""

import re
import asyncio
import json
from datetime import datetime
import os
from urllib.parse import urlparse, unquote

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_session")

async def login_tiktok_async():
    from playwright.async_api import async_playwright
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--window-size=380,820',
                    '--app=https://m.tiktok.com/login',
                    '--no-first-run',
                    '--no-default-browser-check'
                ],
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
                viewport={'width': 380, 'height': 820}
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://www.tiktok.com/login")
            print("Mở trang đăng nhập TikTok. Đang chờ bạn thao tác...")
            
            try:
                await page.wait_for_url(lambda u: "login" not in u and "passport" not in u, timeout=120000)
                print("Đăng nhập thành công! Lưu session hoàn tất.")
                success = True
            except Exception:
                print("Đã hết thời gian chờ 2 phút hoặc người dùng đã đóng.")
                success = False
            
            await context.close()
            return success
    except Exception as e:
        print("Lỗi mở trình duyệt login:", e)
        return False

def login_tiktok_sync():
    import asyncio
    return asyncio.run(login_tiktok_async())


def validate_tiktok_url(url):
    """Validate if URL is a valid TikTok link."""
    if not url:
        return False, "Link TikTok không được để trống."
    
    url = url.strip()
    
    # Check common TikTok URL patterns
    tiktok_patterns = [
        r'https?://(www\.)?tiktok\.com/@[\w.-]+/video/\d+',
        r'https?://(www\.)?tiktok\.com/t/[\w]+',
        r'https?://vm\.tiktok\.com/[\w]+',
        r'https?://(www\.)?tiktok\.com/@[\w.-]+/photo/\d+',
        r'https?://vt\.tiktok\.com/[\w]+',
    ]
    
    for pattern in tiktok_patterns:
        if re.match(pattern, url):
            return True, "Link hợp lệ"
    
    # Loose check - at least contains tiktok.com
    if 'tiktok.com' in url:
        return True, "Link hợp lệ (chưa xác nhận định dạng)"
    
    return False, "Link không đúng định dạng TikTok."


# ─── Cookie Management ────────────────────────────────────────────

import threading

_cached_cookies = None
_cookie_cache_time = None
_cookie_lock = threading.Lock()
_browser_lock = threading.Lock() # Lock for full browser instances to prevent RAM spike

async def _get_session_cookies():
    """Get cookies from Playwright persistent context with thread-safe caching."""
    global _cached_cookies, _cookie_cache_time
    
    # Fast path: check cache without lock first
    if _cached_cookies and _cookie_cache_time:
        elapsed = (datetime.now() - _cookie_cache_time).total_seconds()
        if elapsed < 600: # Cache for 10 minutes
            return _cached_cookies
            
    # Slow path: use lock to ensure only one thread launches browser
    with _cookie_lock:
        # Check again inside lock (double-checked locking)
        if _cached_cookies and _cookie_cache_time:
            elapsed = (datetime.now() - _cookie_cache_time).total_seconds()
            if elapsed < 600:
                return _cached_cookies
    
    from playwright.async_api import async_playwright
    
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--no-first-run',
                ]
            )
            cookies = await context.cookies()
            await context.close()
            
            tiktok_cookies = [c for c in cookies if 'tiktok' in c.get('domain', '')]
            print(f"  → Đọc {len(tiktok_cookies)} cookies từ session")
            
            _cached_cookies = tiktok_cookies
            _cookie_cache_time = datetime.now()
            return tiktok_cookies
    except Exception as e:
        print(f"  ⚠ Lỗi đọc cookies: {e}")
        return []


def _build_requests_session(cookies):
    """Build a requests.Session with TikTok cookies."""
    import requests
    
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
    
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": "https://www.tiktok.com/",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
    })
    
    return session


# ─── PDP Extraction via requests (bypasses CAPTCHA) ────────────────

def _extract_pdp_via_requests(product_url, session):
    """
    Fetch PDP page via requests with session cookies.
    TikTok returns full SSR HTML with product data when cookies are present.
    This bypasses the CAPTCHA that blocks Playwright.
    """
    details = {
        'product_name': '',
        'current_price': '',
        'original_price': '',
        'sale_price': '',
        'product_link': product_url,
        'shop_name': '',
        'note': '',
        'product_images': [],
    }
    
    try:
        print(f"  → Đang fetch PDP qua requests: {product_url[:80]}...")
        resp = session.get(product_url, timeout=15)
        
        if resp.status_code != 200:
            details['note'] = f'PDP trả về mã {resp.status_code}'
            return details
        
        html = resp.text
        
        # Check if we got CAPTCHA instead of real page
        if 'Security Check' in html and len(html) < 20000:
            details['note'] = 'PDP bị CAPTCHA (cần đăng nhập lại)'
            return details
        
        # ─── Strategy 1: Parse __MODERN_ROUTER_DATA__ (best source) ───
        router_match = re.search(
            r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>',
            html, re.DOTALL
        )
        
        if router_match:
            try:
                router_data = json.loads(router_match.group(1))
                details = _parse_router_data(router_data, details)
                if details.get('current_price') or details.get('sale_price'):
                    print(f"  ✅ Lấy được giá từ __MODERN_ROUTER_DATA__")
                    return details
            except Exception as e:
                print(f"  ⚠ Lỗi parse ROUTER_DATA: {e}")
        
        # ─── Strategy 2: Parse prices from SSR HTML directly ───
        print("  → Thử parse giá từ HTML...")
        details = _parse_prices_from_html(html, details)
        
        if details.get('current_price') or details.get('sale_price'):
            print(f"  ✅ Lấy được giá từ HTML")
        else:
            print(f"  ⚠ Không tìm thấy giá trong HTML (length={len(html)})")
            details['note'] = 'Trang PDP không chứa thông tin giá'
        
        return details
        
    except Exception as e:
        details['note'] = f'Lỗi fetch PDP: {str(e)[:100]}'
        return details


def _parse_router_data(router_data, details):
    """Parse product info from __MODERN_ROUTER_DATA__ JSON."""
    try:
        loader_data = router_data.get('loaderData', {})
        
        # Find the PDP page data (key varies)
        page_data = None
        for key, value in loader_data.items():
            if 'pdp' in key and isinstance(value, dict):
                page_data = value
                break
        
        if not page_data:
            return details
        
        # Extract product info
        product_info = page_data.get('component_data', {})
        if not product_info:
            # Try nested structure
            for comp in page_data.get('page_config', {}).get('components_map', []):
                if comp.get('component_type') == 'product_info':
                    product_info = comp.get('component_data', {})
                    break
        
        product_model = product_info.get('product_info', {}).get('product_model', {})
        if not product_model:
            product_model = product_info.get('product_model', {})
        
        # Product name
        if product_model.get('name'):
            details['product_name'] = product_model['name']
        
        # Sold count for reference
        sold = product_model.get('sold_count', '')
        
        # SKUs contain price info
        skus = product_model.get('skus', [])
        if skus:
            for sku in skus:
                price_info = sku.get('price', {})
                if price_info:
                    # TikTok prices are in minor units (cents)
                    sale = price_info.get('sale_price', '')
                    original = price_info.get('original_price', '')
                    
                    if sale:
                        try:
                            sale_val = int(sale) / 100 if int(sale) > 100000 else int(sale)
                            details['sale_price'] = f"₫{sale_val:,.0f}".replace(',', '.')
                            details['current_price'] = details['sale_price']
                        except (ValueError, TypeError):
                            details['sale_price'] = str(sale)
                    
                    if original:
                        try:
                            orig_val = int(original) / 100 if int(original) > 100000 else int(original)
                            details['original_price'] = f"₫{orig_val:,.0f}".replace(',', '.')
                        except (ValueError, TypeError):
                            details['original_price'] = str(original)
                    break  # Use first SKU
        
        # Seller info
        seller_name = product_model.get('seller_name', '')
        if seller_name:
            details['shop_name'] = seller_name
            
        # Extract product images
        images = product_model.get('images', [])
        if not images:
            images = product_model.get('image_list', [])
            
        if images:
            img_links = []
            for img in images:
                # Try multiple possible keys for URL list
                urls = img.get('url_list', []) or img.get('thumb_url_list', []) or img.get('origin_url_list', [])
                if urls:
                    # Clean URL (remove query params if needed, but TikTok images usually work as is)
                    img_links.append(urls[0])
            
            if img_links:
                details['product_images'] = img_links
            
    except Exception as e:
        print(f"  ⚠ Lỗi parse router data: {e}")
    
    return details


def _parse_prices_from_html(html, details):
    """Parse product info directly from SSR HTML content."""
    
    # Extract product name from <h1> or <title>
    if not details.get('product_name'):
        # Try <h1>
        h1_match = re.search(r'<h1[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if h1_match:
            details['product_name'] = h1_match.group(1).strip()
        else:
            # Try <title>
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
            if title_match:
                title = title_match.group(1).strip()
                # Remove " - TikTok Shop Vietnam" suffix
                title = re.sub(r'\s*-\s*TikTok Shop\s*(Vietnam|Việt Nam)?$', '', title)
                details['product_name'] = title
    
    # ─── Extract prices ───
    # TikTok SSR HTML has prices in specific structures:
    # Sale price: <span>₫</span><span style="font-size:36px">1.015.500</span>
    # Original:   <span class="...line-through...">1.690.000₫</span>
    # Shipping:   Phí vận chuyển 47.600₫
    
    # Strategy: Find the original (line-through) price first, then the sale price
    
    # 1. Find original/strikethrough price  
    original_price = None
    orig_match = re.search(r'line-through[^>]*>[\s]*([\d.]+)₫', html)
    if orig_match:
        try:
            num = int(orig_match.group(1).replace('.', ''))
            if num >= 10000:
                original_price = f"₫{num:,}".replace(',', '.')
        except ValueError:
            pass
    
    # 2. Find sale/current price
    # Pattern: ₫</span> followed by price in next span (usually the biggest price on page)
    sale_price = None
    # Flexible match for: ₫ ... font-size:36px ... >PRICE</span>
    sale_match = re.search(
        r'₫</span>.*?font-size:3[26]px[^>]*>([\d.]+)</span>',
        html, re.DOTALL
    )
    if sale_match:
        try:
            num = int(sale_match.group(1).replace('.', ''))
            if num >= 10000:
                sale_price = f"₫{num:,}".replace(',', '.')
        except ValueError:
            pass
    
    # Fallback: look for any large price that's NOT the original price
    if not sale_price:
        price_candidates = []
        # Find all patterns like 1.234.567₫ or ₫1.234.567
        for m in re.finditer(r'(?:₫|&para;)?\s*([\d]{1,3}(?:\.[\d]{3})+)\s*(?:₫|&para;)?', html):
            price_str = m.group(1)
            try:
                num = int(price_str.replace('.', ''))
                # Product prices in VN are usually > 20,000 and not small shipping costs
                if 20000 < num < 100000000: 
                    formatted = f"₫{num:,}".replace(',', '.')
                    if formatted != original_price and formatted not in price_candidates:
                        # Context check: skip shipping
                        start = max(0, m.start() - 50)
                        context = html[start:m.start()].lower()
                        if 'vận chuyển' not in context and 'shipping' not in context:
                            price_candidates.append(formatted)
            except ValueError:
                continue
        
        if price_candidates:
            # Usually the first candidate is the main price
            sale_price = price_candidates[0]
    
    # Assign prices
    if sale_price:
        details['sale_price'] = sale_price
        details['current_price'] = sale_price
    if original_price:
        details['original_price'] = original_price
        # If we only found original but not sale, use original as current
        if not sale_price:
            details['current_price'] = original_price
    
    # Extract discount percentage
    discount_match = re.search(r'-(\d+)%', html)
    if discount_match and details.get('note') == '':
        details['note'] = f"Giảm {discount_match.group(1)}%"
    
    # Extract shop name
    if not details.get('shop_name'):
        shop_match = re.search(r'Do\s+(.+?)\s+bán', html)
        if shop_match:
            details['shop_name'] = shop_match.group(1).strip()
        else:
            # Try seller-name class
            seller_match = re.search(r'seller[_-]name[^>]*>([^<]+)<', html, re.IGNORECASE)
            if seller_match:
                details['shop_name'] = seller_match.group(1).strip()
    
    # Extract product images from HTML if not already found
    if not details.get('product_images'):
        # Look for image URLs that look like TikTok product images
        img_matches = re.findall(r'https?://[a-zA-Z0-9.-]+\.ibyteimg\.com/tos-[^"\']+\.(?:jpg|png|webp|jpeg)', html)
        if img_matches:
            # Filter unique and likely product images
            unique_imgs = list(dict.fromkeys(img_matches))
            details['product_images'] = unique_imgs[:10]
    
    return details


# ─── Video Page Analysis ──────────────────────────────────────────

def _extract_pdp_url_from_video(url):
    """
    Fetch video page via requests and extract product PDP URL 
    from __UNIVERSAL_DATA_FOR_REHYDRATION__.
    """
    import requests
    
    result = {
        'product_name': '',
        'pdp_url': '',
    }
    
    headers = {
        "User-Agent": "com.zhiliaoapp.musically/2022405010 (Linux; U; Android 10; en_US; SM-G981B; Build/QP1A.190711.020)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return result
        
        html_text = resp.text
        matches = re.findall(
            r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>',
            html_text
        )
        
        if not matches:
            return result
        
        u_data = json.loads(matches[0])
        item_struct = (u_data.get('__DEFAULT_SCOPE__', {})
                      .get('webapp.reflow.video.detail', {})
                      .get('itemInfo', {})
                      .get('itemStruct', {}))
        
        anchors = item_struct.get('anchors', [])
        
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            extra_str = anchor.get('extra', '{}')
            if not isinstance(extra_str, str) or '{' not in extra_str:
                continue
            try:
                extra_data = json.loads(extra_str)
                if isinstance(extra_data, list):
                    for item in extra_data:
                        inner_extra_str = item.get('extra')
                        if inner_extra_str and isinstance(inner_extra_str, str):
                            inner_extra = json.loads(inner_extra_str)
                            seo_url = inner_extra.get('seo_url')
                            if seo_url and 'shop' in seo_url:
                                result['pdp_url'] = seo_url
                                result['product_name'] = inner_extra.get('title', '')
                                return result
                elif isinstance(extra_data, dict):
                    seo_url = extra_data.get('seo_url')
                    if seo_url and 'shop' in seo_url:
                        result['pdp_url'] = seo_url
                        result['product_name'] = extra_data.get('title', '')
                        return result
            except Exception:
                continue
                
    except Exception as e:
        print(f"  ⚠ Lỗi phân tích video page: {e}")
    
    return result


# ─── Main Scraper ─────────────────────────────────────────────────

async def scrape_tiktok_product(url, playwright_instance=None):
    """
    Scrape product information from a TikTok video.
    
    Strategy:
    1. If URL is already a PDP link → fetch via requests with cookies
    2. If URL is a video link → extract PDP URL from video page → then fetch PDP
    3. Fall back to Playwright for edge cases
    """
    result = {
        'status': 'Lỗi',
        'product_name': '',
        'current_price': '',
        'original_price': '',
        'sale_price': '',
        'product_link': '',
        'shop_name': '',
        'note': '',
        'product_images': [],
    }
    
    # Validate URL first
    valid, msg = validate_tiktok_url(url)
    if not valid:
        result['status'] = 'Link lỗi'
        result['note'] = msg
        return result
    
    url = url.strip()
    
    # Get session cookies for requests
    cookies = await _get_session_cookies()
    session = _build_requests_session(cookies)
    
    # Determine if URL is a PDP or video link
    is_pdp = '/pdp/' in url or '/product/' in url or 'shop.tiktok' in url
    
    pdp_url = url if is_pdp else ''
    video_product_name = ''
    
    # ─── Step 1: If video link, extract PDP URL ───
    if not is_pdp:
        print(f"  → Đang phân tích video page: {url[:60]}...")
        video_data = _extract_pdp_url_from_video(url)
        
        if video_data['pdp_url']:
            pdp_url = video_data['pdp_url']
            video_product_name = video_data['product_name']
            print(f"  → Tìm thấy PDP: {pdp_url[:60]}...")
        else:
            print(f"  → Không tìm thấy link sản phẩm trong video")
    
    # ─── Step 2: Fetch PDP page via requests ───
    if pdp_url:
        result['product_link'] = pdp_url
        
        pdp_details = _extract_pdp_via_requests(pdp_url, session)
        
        # Merge results
        for key, value in pdp_details.items():
            if value:
                result[key] = value
        
        # Use video product name as fallback
        if not result['product_name'] and video_product_name:
            result['product_name'] = video_product_name
        
        # Determine status
        if result['current_price'] or result['sale_price']:
            result['status'] = 'Thành công'
        elif result['product_name']:
            result['status'] = 'Thiếu giá'
            if not result['note']:
                result['note'] = 'Lấy được tên SP nhưng không lấy được giá'
        else:
            result['status'] = 'Lỗi'
            if not result['note']:
                result['note'] = 'Không lấy được dữ liệu từ trang sản phẩm'
        
        return result
    
    # ─── Step 3: No PDP URL found → try Playwright for video page ───
    # Use lock to prevent multiple browser instances from crashing the PC
    with _browser_lock:
        print(f"  → Thử mở video bằng Playwright (Lấy browser lock)...")
        context = None
        own_playwright = False
    
    try:
        from playwright.async_api import async_playwright
        
        if playwright_instance is None:
            playwright_instance = await async_playwright().start()
            own_playwright = True
        
        context = await playwright_instance.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--no-first-run',
            ],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720}, # Smaller viewport saves memory
            locale='vi-VN',
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as nav_err:
            result['status'] = 'Lỗi truy cập'
            result['note'] = f'Không thể mở trang TikTok: {str(nav_err)[:100]}'
            return result
        
        await page.wait_for_timeout(3000)
        
        page_content = await page.content()
        
        # Check for blocks
        if 'This account is private' in page_content:
            result['status'] = 'Lỗi'
            result['note'] = 'Tài khoản TikTok ở chế độ riêng tư'
            return result
        
        if "Couldn't find this page" in page_content or 'Video is unavailable' in page_content:
            result['status'] = 'Video bị xóa'
            result['note'] = 'Video không tồn tại hoặc đã bị xóa'
            return result
        
        if 'Xem video TikTok Shop trong ứng dụng TikTok' in page_content or 'Open TikTok app' in page_content:
            result['status'] = 'Cần mở App'
            result['note'] = 'Không hiển thị sản phẩm trên web (Affiliate link cần xem trên App)'
            
            try:
                title_el = await page.query_selector('[data-e2e="browse-video-desc"]')
                if title_el:
                    text = await title_el.inner_text()
                    if text:
                        result['product_name'] = f"(Video: {text[:100]}...)"
            except Exception:
                pass
            return result
        
        # Look for product links in the video page
        product_url_found = None
        try:
            all_links = await page.query_selector_all('a')
            for link in all_links:
                href = await link.get_attribute('href')
                if href and ('pdp' in href or 'product' in href or 'shop.tiktok' in href):
                    if not href.startswith('http'):
                        href = 'https://www.tiktok.com' + href
                    product_url_found = href
                    break
        except Exception:
            pass
        
        if product_url_found:
            result['product_link'] = product_url_found
            pdp_details = _extract_pdp_via_requests(product_url_found, session)
            for key, value in pdp_details.items():
                if value:
                    result[key] = value
            
            if result['current_price'] or result['sale_price']:
                result['status'] = 'Thành công'
            else:
                result['status'] = 'Thiếu giá'
        else:
            result['status'] = 'Cần mở App'
            result['note'] = 'Không tìm thấy sản phẩm trong video'
        
        return result
        
    except Exception as e:
        result['status'] = 'Lỗi cần chạy lại'
        result['note'] = f'Lỗi scraper: {str(e)[:150]}'
        return result
    finally:
        if context:
            await context.close()
        if own_playwright and playwright_instance:
            await playwright_instance.stop()


async def process_single_link(url):
    """Process a single TikTok link - convenience wrapper."""
    return await scrape_tiktok_product(url)


def process_single_link_sync(url):
    """Synchronous wrapper for process_single_link."""
    import asyncio
    return asyncio.run(process_single_link(url))
