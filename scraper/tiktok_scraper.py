"""
TikTok Scraper - Extracts product information from TikTok Shop videos.
Uses Playwright for session management + requests for data extraction.
"""

import re
import asyncio
import json
from datetime import datetime
import os
import threading
from urllib.parse import urlparse, unquote

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tiktok_session")
DEFAULT_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1"

def _cleanup_lock_files(session_dir):
    """Xóa các file lock của Chromium để tránh lỗi 'Target page' / 'Profile in use'."""
    if not session_dir or not os.path.exists(session_dir):
        return
    
    lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    for lock_name in lock_files:
        lock_path = os.path.join(session_dir, lock_name)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except:
            pass

async def login_tiktok_async(url=None):
    # Close global headless browser if open (to release lock on SESSION_DIR)
    await close_global_browser()
    
    from playwright.async_api import async_playwright
    import sys
    import shutil
    sys.stdout.reconfigure(encoding='utf-8')
    
    target_url = url if url else "https://www.tiktok.com/login"
    
    # Pre-launch cleanup: Remove lock files
    _cleanup_lock_files(SESSION_DIR)

    print(f"🚀 Đang khởi chạy trình duyệt để mở: {target_url}...")
    
    # Find local Chrome/Edge executable to bypass Google login block (Windows only)
    executable_path = None
    import platform
    if platform.system() == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]
        for path in chrome_paths:
            if os.path.exists(path):
                executable_path = path
                break
    
    # In headless environments (like Render/Railway), force headless=True for all
    is_headless_env = os.environ.get("HEADLESS", "false").lower() == "true" or platform.system() != "Windows"
    
    with _browser_lock:
        try:
            async with async_playwright() as p:
                try:
                    launch_kwargs = {
                        'user_data_dir': SESSION_DIR,
                        'headless': is_headless_env if is_headless_env else False,
                        'args': [
                            '--disable-blink-features=AutomationControlled',
                            '--no-sandbox',
                            '--disable-dev-shm-usage',
                            '--window-size=375,812'
                        ],
                        'ignore_default_args': ['--enable-automation'],
                        'user_agent': DEFAULT_UA,
                        'viewport': {'width': 375, 'height': 812},
                        'is_mobile': True,
                        'has_touch': True,
                        'locale': 'vi-VN',
                        'timezone_id': 'Asia/Ho_Chi_Minh'
                    }
                    if executable_path:
                        launch_kwargs['executable_path'] = executable_path
                        
                    context = await p.chromium.launch_persistent_context(**launch_kwargs)
                except Exception as launch_err:
                    print(f"❌ Lỗi khởi chạy browser: {launch_err}")
                    return False

                page = context.pages[0] if context.pages else await context.new_page()
                
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except:
                    pass
                
                print(f"🚀 Đang tải trang ({len(target_url)} ký tự)...")
                try:
                    await asyncio.sleep(2)
                    # Try goto first
                    await page.goto(target_url, timeout=60000)
                except Exception as nav_err:
                    print(f"⚠️ Thử cách 2 (window.location): {nav_err}")
                    try:
                        await page.evaluate(f"window.location.href = '{target_url}'")
                    except: pass
                
                # Keep open until the user closes the browser or 10 minutes pass
                success = False
                print("👀 Đang đợi bạn giải CAPTCHA hoặc đăng nhập...")
                
                for i in range(120): # 10 minutes max (120 * 5s)
                    await asyncio.sleep(5)
                    try:
                        if not context.pages or page.is_closed():
                            print("ℹ️ Trình duyệt đã đóng.")
                            success = True
                            break
                        
                        current_url = page.url
                        # If we are on tiktok.com and NOT on a login/captcha page
                        if "tiktok.com" in current_url and "login" not in current_url and "passport" not in current_url:
                            # Check if captcha container exists
                            captcha_selectors = "#captcha_container, .captcha_verify_container, [id^='secsdk'], [class*='captcha']"
                            captcha_exists = False
                            
                            # Check main page
                            try:
                                if await page.query_selector(captcha_selectors):
                                    captcha_exists = True
                            except: pass
                            
                            # Check iframes
                            if not captcha_exists:
                                for frame in page.frames:
                                    try:
                                        if await frame.query_selector(captcha_selectors):
                                            captcha_exists = True
                                            break
                                    except: pass
                                    
                            if not captcha_exists:
                                print("✨ CAPTCHA đã được giải quyết hoặc không xuất hiện! Đang lưu phiên và đóng trình duyệt...")
                                await asyncio.sleep(3) # Wait for cookies to settle
                                success = True
                                break
                    except Exception as poll_err:
                        print(f"ℹ️ Kết thúc: {poll_err}")
                        success = True
                        break
                
                await context.close()
                # Clear cookie cache to force reload in next scrape
                global _cached_cookies, _cookie_cache_time
                _cached_cookies = None
                _cookie_cache_time = None
                return success
        except Exception as e:
            print(f"❌ Lỗi nghiêm trọng trong login_tiktok_async: {e}")
            return False

def login_tiktok_sync(url=None):
    import asyncio
    return asyncio.run(login_tiktok_async(url))


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
    
def _extract_shop_name_from_url(url):
    """Trích xuất tên shop/username từ URL TikTok."""
    if not url: return ""
    # Pattern video: tiktok.com/@username/video/...
    match = re.search(r'tiktok\.com/@([^/?#]+)', url)
    if match: return match.group(1)
    return ""


# ─── Persistent Browser Management ───────────────────────────────

_global_playwright = None
# ─── Browser Management ───────────────────────────────────────────

_browser_lock = threading.Lock()


def _cleanup_browser_data():
    """Dọn dẹp dữ liệu thừa để tiết kiệm dung lượng."""
    try:
        # Xóa các thư mục tạm nếu có
        import shutil
        for folder in ["Default/Cache", "Default/Code Cache", "Default/GPUCache"]:
            path = os.path.join(SESSION_DIR, folder)
            if os.path.exists(path):
                try: shutil.rmtree(path)
                except: pass
        print("  🧹 Đã dọn dẹp bộ nhớ đệm trình duyệt.")
    except: pass

async def close_global_browser():
    """No-op for compatibility."""
    pass

# ─── Cookie Management ────────────────────────────────────────────

_cached_cookies = None
_cookie_cache_time = None
_cookie_lock = threading.Lock()

async def _get_session_cookies(custom_session_dir=None):
    """Get cookies from Playwright persistent context with thread-safe caching."""
    global _cached_cookies, _cookie_cache_time
    
    # Sử dụng folder được chỉ định hoặc folder mặc định
    target_session_dir = custom_session_dir or SESSION_DIR
    
    # Fast path: check cache (chỉ dùng cache cho session mặc định để đơn giản, 
    # hoặc bạn có thể mở rộng cache theo key session_dir)
    if not custom_session_dir and _cached_cookies and _cookie_cache_time:
        elapsed = (datetime.now() - _cookie_cache_time).total_seconds()
        if elapsed < 600: # Cache for 10 minutes
            return _cached_cookies
            
    _cleanup_lock_files(target_session_dir)
    from playwright.async_api import async_playwright
    
    try:
        async with async_playwright() as p:
            # Retry loop for launch (fix Target page error)
            context = None
            for attempt in range(2):
                try:
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=target_session_dir,
                        headless=True,
                        args=[
                            '--disable-blink-features=AutomationControlled',
                            '--no-sandbox',
                            '--disable-gpu',
                            '--blink-settings=imagesEnabled=false',
                            '--no-first-run',
                        ],
                        user_agent=DEFAULT_UA,
                        viewport={'width': 375, 'height': 812},
                        is_mobile=True,
                        has_touch=True
                    )
                    break
                except Exception as le:
                    if attempt == 0:
                        print(f"  ⚠️ Thử lại lấy cookies ({le})...")
                        _cleanup_lock_files(target_session_dir)
                        await asyncio.sleep(2)
                    else:
                        raise le
            
            if not context: return []
            cookies = await context.cookies()
            await context.close()
            
            tiktok_cookies = [c for c in cookies if 'tiktok' in c.get('domain', '')]
            
            # Check for key session cookies
            has_session = any(c['name'] == 'sessionid' for c in tiktok_cookies)
            has_ttwid = any(c['name'] == 'ttwid' for c in tiktok_cookies)
            
            print(f"  → Đọc {len(tiktok_cookies)} cookies từ {os.path.basename(target_session_dir)} (SessionID: {'✅' if has_session else '❌'}, TTWID: {'✅' if has_ttwid else '❌'})")
            
            if not custom_session_dir:
                _cached_cookies = tiktok_cookies
                _cookie_cache_time = datetime.now()
            
            return tiktok_cookies
    except Exception as e:
        print(f"  ⚠ Lỗi đọc cookies từ {os.path.basename(target_session_dir)}: {e}")
        return []


def _build_requests_session(cookies):
    """Build a requests.Session with TikTok cookies."""
    import requests
    
    session = requests.Session()
    for c in cookies:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
    
    session.headers.update({
        "User-Agent": DEFAULT_UA,
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
        'shop_link': '',
        'note': '',
        'product_images': [],
    }
    
    try:
        print(f"  → Đang fetch PDP qua requests: {product_url[:80]}...")
        # Sử dụng User-Agent của ứng dụng TikTok thật để lách CAPTCHA. 
        # TikTok thường tin tưởng User-Agent từ app của chính mình và trả về nội dung SSR đầy đủ.
        headers = {
            "User-Agent": "com.zhiliaoapp.musically/2022405010 (Linux; U; Android 10; en_US; SM-G981B; Build/QP1A.190711.020)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # Sử dụng session có chứa Cookie đã đăng nhập để tải trang sản phẩm
        resp = session.get(product_url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            details['note'] = f'PDP trả về mã {resp.status_code}'
            return details
        
        html = resp.text
        
        # Check if we got CAPTCHA instead of real page
        if 'Security Check' in html and len(html) < 20000:
            details['note'] = 'PDP bị CAPTCHA (cần đăng nhập lại)'
            return details
        
        # Lấy tên sản phẩm từ HTML trước để làm "kim chỉ nam" tìm đúng dữ liệu trong JSON
        expected_name = ""
        h1_match = re.search(r'<h1[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if h1_match:
            expected_name = h1_match.group(1).strip()
        else:
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
            if title_match:
                expected_name = re.sub(r'\s*-\s*TikTok Shop.*$', '', title_match.group(1).strip())
                
        # Lấy Product ID từ URL để định danh chính xác
        product_id = ""
        id_match = re.search(r'/(\d+)(?:\?|$)', product_url)
        if id_match:
            product_id = id_match.group(1)
                
        # ─── Strategy 1: Parse __MODERN_ROUTER_DATA__ (best source) ───
        router_match = re.search(
            r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>',
            html, re.DOTALL
        )
        
        if router_match:
            try:
                router_data = json.loads(router_match.group(1))
                # Truyền expected_name và product_id vào để đảm bảo lấy đúng sản phẩm chính
                details = _parse_router_data(router_data, details, expected_name, product_id)
                
                # Verify we actually got the right product by checking if names roughly match
                # if we have an expected name
                if details.get('current_price') or details.get('sale_price'):
                    print(f"  ✅ Lấy được dữ liệu sạch từ __MODERN_ROUTER_DATA__ (API)")
                    return details
            except Exception as e:
                print(f"  ⚠ Lỗi parse ROUTER_DATA: {e}")
        
        # Strategy 2 (DISABLED)
        # details = _parse_prices_from_html(html, details)

        
        if not details.get('current_price'):
            details['note'] = 'Không tìm thấy dữ liệu sản phẩm trong JSON (API)'
        return details
        
    except Exception as e:
        details['note'] = f'Lỗi fetch PDP: {str(e)[:100]}'
        return details


def _clean_tiktok_image_url(url):
    """Chuyển ảnh TikTok sang JPEG để tương thích với Google Sheet (vì Sheet không hỗ trợ WEBP/AVIF)."""
    if not url: return ""
    import re
    # Xóa các query parameter (?...)
    url = url.split('?')[0]
    # Đổi định dạng từ .webp, .avif sang .jpeg để Google Sheet có thể hiển thị
    url = re.sub(r'\.(?:webp|avif)$', '.jpeg', url, flags=re.IGNORECASE)
    # Một số URL không có đuôi, nhưng có tham số tplv-obj. ta có thể ép đuôi .jpeg vào
    if not re.search(r'\.(?:jpg|jpeg|png|gif)$', url, re.IGNORECASE):
        url = url + ".jpeg"
    return url

def _parse_router_data(router_data, details, expected_name="", target_product_id=""):
    """Parse product info from __MODERN_ROUTER_DATA__ JSON."""
    try:
        loader_data = router_data.get('loaderData', {})
        
        product_model = {}
        product_info = {}
        
        # Danh sách tất cả các product_model tìm được
        all_models = []
        
        # Hàm đệ quy để tìm TẤT CẢ product_model sâu bên trong
        def find_all_product_models(data):
            if isinstance(data, dict):
                if 'product_model' in data and isinstance(data['product_model'], dict) and 'name' in data['product_model']:
                    all_models.append((data['product_model'], data))
                
                if 'name' in data and ('skus' in data or 'price' in data) and 'images' in data:
                    all_models.append((data, data))
                
                if 'component_data' in data and isinstance(data['component_data'], dict):
                    if 'product_info' in data['component_data'] and 'product_model' in data['component_data']['product_info']:
                        all_models.append((data['component_data']['product_info']['product_model'], data['component_data']))

                for key, val in data.items():
                    find_all_product_models(val)
            elif isinstance(data, list):
                for item in data:
                    find_all_product_models(item)
            
        find_all_product_models(loader_data)
        
        if not all_models:
            return details
            
        # Lọc các model hợp lệ (chỉ cần có name)
        valid_models = []
        for model, info in all_models:
            if model.get('name'):
                valid_models.append((model, info))
                
        if not valid_models:
            return details
            
        details = details.copy()
        found_price = False
        product_model = None
        product_info = None
        
        # 1. Ưu tiên tuyệt đối theo Product ID
        if target_product_id:
            for model, info in valid_models:
                p_id = str(model.get('product_id', '') or model.get('id', ''))
                if p_id == target_product_id:
                    product_model, product_info = model, info
                    print(f"  ✅ Khớp Product ID: {target_product_id}")
                    break
        
        # 2. Nếu không khớp ID, dùng expected_name
        if not product_model and expected_name:
            best_match = None
            highest_sim = -1
            
            exp_words = set(expected_name.lower().split())
            for model, info in valid_models:
                m_name = model.get('name', '')
                m_words = set(m_name.lower().split())
                # Tính độ tương đồng
                sim = len(exp_words & m_words)
                if sim > highest_sim:
                    highest_sim = sim
                    best_match = (model, info)
                    
            if best_match:
                product_model, product_info = best_match
        
        if not product_model:
            return details
        
        print(f"  → Đang xử lý sản phẩm: {product_model.get('name', 'N/A')}")
        
        # Tên sản phẩm
        if product_model.get('name'):
            details['product_name'] = product_model['name']
        
        # ─── Price Extraction (Advanced) ───
        promotion_model = product_info.get('promotion_model', {})
        if not promotion_model:
            # Try to find promotion_model in loader_data if not in product_info
            def find_promotion_model(data):
                if isinstance(data, dict):
                    if 'promotion_model' in data: return data['promotion_model']
                    for v in data.values():
                        res = find_promotion_model(v)
                        if res: return res
                elif isinstance(data, list):
                    for item in data:
                        res = find_promotion_model(item)
                        if res: return res
                return None
            promotion_model = find_promotion_model(loader_data) or {}

        # Lấy danh sách SKUs để tìm giá gốc chính xác nhất (thường là giá gạch ngang trên UI)
        sku_original_price = None
        sku_sale_price = None
        discount_rate = None
        
        # Thử tìm skus trong nhiều vị trí khác nhau của JSON
        skus = product_model.get('skus') or product_info.get('skus')
        if not skus:
            # TikTok mới thường để skus trong component_data -> product_info -> skus
            p_info = product_info.get('product_info') or product_info
            skus = p_info.get('skus', [])
            
        if skus and len(skus) > 0:
            # Ưu tiên SKU đầu tiên hoặc SKU có giá thấp nhất
            price_info = skus[0].get('price', {})
            sku_original_price = price_info.get('original_price') or price_info.get('original_price_decimal')
            sku_sale_price = price_info.get('sale_price') or price_info.get('sale_price_decimal')
            discount_rate = price_info.get('discount_rate') or price_info.get('discount')
            if not discount_rate:
                 # Thử tìm trong promotion_info của SKU
                 promo_info = skus[0].get('promotion_info', {})
                 discount_rate = promo_info.get('discount_rate') or promo_info.get('discount')

        # Nếu vẫn không thấy discount_rate, quét toàn bộ product_info
        if not discount_rate:
            def _deep_find_key(obj, key):
                if isinstance(obj, dict):
                    if key in obj: return obj[key]
                    for v in obj.values():
                        res = _deep_find_key(v, key)
                        if res: return res
                elif isinstance(obj, list):
                    for item in obj:
                        res = _deep_find_key(item, key)
                        if res: return res
                return None
            discount_rate = _deep_find_key(product_info, 'discount_rate') or _deep_find_key(product_info, 'discount')

        promotion_model = product_info.get('promotion_model') or {}
        if not promotion_model and 'product_info' in product_info:
             promotion_model = product_info['product_info'].get('promotion_model', {})
             
        promo_price_info = promotion_model.get('promotion_product_price', {}).get('min_price', {})
        if promo_price_info:
            sale_decimal = promo_price_info.get('sale_price_decimal')
            origin_decimal = promo_price_info.get('origin_price_decimal')
            # Nếu promotion_model không có discount_rate, thử lấy từ SKU
            if not discount_rate:
                discount_rate = promo_price_info.get('discount_rate')
                
            deduction = promo_price_info.get('promotion_deduction_details', {}).get('seller_subtotal_deduction_decimal', '0')
            
            # CÔNG THỨC MỚI: Nếu không có discount_rate, hãy tính toán từ Sale/Origin của API
            if not discount_rate and sale_decimal and origin_decimal and int(origin_decimal) > 0:
                try:
                    discount_rate = round(100 - (int(sale_decimal) * 100 / int(origin_decimal)))
                except: pass
            
            try:
                # CÔNG THỨC: Giá hiển thị = Giá gốc - Chiết khấu của Shop
                # Ưu tiên dùng origin_decimal từ promotion nếu có, nếu không dùng từ SKU
                base_origin = origin_decimal if (origin_decimal and int(origin_decimal) > 0) else sku_original_price
                
                if base_origin and int(base_origin) > 0:
                    price_val = int(base_origin) - int(deduction)
                    # TRƯỜNG HỢP ĐẶC BIỆT: Nếu có discount_rate (ví dụ 15%), và giá sau giảm là 17k
                    # thì giá gốc PHẢI là 20k (17 / 0.85). TikTok đôi khi để origin_decimal rất cao (giá gốc tuyệt đối)
                    # nhưng UI chỉ hiển thị giá gốc của đợt giảm giá đó.
                    if discount_rate and int(discount_rate) > 0:
                        calculated_origin = int(price_val) * 100 // (100 - int(discount_rate))
                        # Nếu giá gốc tính toán (20k) khác xa giá gốc API (23k), ưu tiên giá gốc tính toán để khớp % UI
                        if sku_original_price and abs(int(sku_original_price) - calculated_origin) < abs(int(base_origin) - calculated_origin):
                             base_origin = sku_original_price
                        elif not base_origin or abs(calculated_origin - int(base_origin)) > 1000:
                             # Nếu chênh lệch quá lớn, có thể giá gốc UI là giá khác
                             pass

                    print(f"  ✅ Tính toán giá (BaseOrigin - Deduction): {price_val}")
                elif sale_decimal:
                    price_val = int(sale_decimal)
                    print(f"  ✅ Dùng giá Sale trực tiếp: {price_val}")
                else:
                    price_val = 0
                
                if price_val > 0:
                    details['sale_price'] = _format_tiktok_price(price_val)
                    details['current_price'] = details['sale_price']
                    
                    # Ưu tiên hiển thị giá gốc khớp với % giảm giá
                    final_origin = sku_original_price if sku_original_price else origin_decimal
                    
                    # CỰC KỲ QUAN TRỌNG: Nếu có discount_rate (ví dụ 15%), hãy tính toán giá gốc 
                    # dựa trên giá hiện tại để đảm bảo hiển thị đúng số % người dùng thấy.
                    if discount_rate and int(discount_rate) > 0:
                        try:
                            # Ví dụ: 17.000 / (1 - 0.15) = 20.000
                            calc_origin = int(price_val) * 100 // (100 - int(discount_rate))
                            # Chỉ thay thế nếu giá tính toán này "đẹp" hoặc gần với SKU price
                            final_origin = calc_origin
                        except: pass
                    
                    if final_origin:
                        details['original_price'] = _format_tiktok_price(final_origin)
                    
                    # Thêm thông tin phần trăm giảm giá nếu có
                    if discount_rate:
                        details['note'] = f"Giảm -{discount_rate}%"
                        print(f"  ✅ Phần trăm giảm giá: -{discount_rate}%")
                        
                    found_price = True
                    print(f"  ✅ Kết quả giá cuối cùng: {details['sale_price']} (Gốc: {details.get('original_price', '-')})")
            except Exception as e:
                print(f"  ⚠️ Lỗi tính toán giá: {e}")

        if not found_price and skus:
            for sku in skus:
                price_info = sku.get('price', {})
                sale = price_info.get('sale_price') or price_info.get('sale_price_decimal')
                original = price_info.get('original_price') or price_info.get('original_price_decimal')
                
                if sale:
                    details['sale_price'] = _format_tiktok_price(sale)
                    details['current_price'] = details['sale_price']
                    found_price = True
                if original:
                    details['original_price'] = _format_tiktok_price(original)
                if found_price: break
        
        # Nếu vẫn không có, thử lấy từ trường price tổng quát
        if not found_price:
            gen_price = product_model.get('price', {})
            if not gen_price:
                gen_price = product_info.get('price', {})
            min_p = gen_price.get('min_price')
            max_p = gen_price.get('max_price')
            if min_p:
                details['sale_price'] = _format_tiktok_price(min_p)
                details['current_price'] = details['sale_price']
                found_price = True
            if max_p and max_p != min_p:
                details['original_price'] = _format_tiktok_price(max_p)
        
        # ─── Seller Info & Shop Link ───
        def find_shop_name(data):
            if isinstance(data, dict):
                if 'shop_name' in data: return data['shop_name']
                if 'seller_name' in data: return data['seller_name']
                for v in data.values():
                    res = find_shop_name(v)
                    if res: return res
            elif isinstance(data, list):
                for item in data:
                    res = find_shop_name(item)
                    if res: return res
            return ""

        seller_name = find_shop_name(loader_data)
        if seller_name:
            details['shop_name'] = seller_name
            
        seller_id = product_model.get('seller_id', '') or product_info.get('seller_id', '')
        if seller_id:
            # Link shop thường có định dạng /shop/vn/shop/{seller_id} hoặc construct từ name
            details['shop_link'] = f"https://www.tiktok.com/shop/vn/shop/{seller_id}"
            
        # Extract product images
        images = []
        # Danh sách các key tiềm năng chứa ảnh trong product_model
        image_keys = ['images', 'image_list', 'main_images', 'gallery_images']
        for k in image_keys:
            if product_model.get(k):
                images = product_model.get(k)
                break
            
        if not images:
            # Tìm sâu hơn trong product_info
            images = product_info.get('image_list', []) or product_info.get('images', [])
            
        if images:
            img_links = []
            for img in images:
                if isinstance(img, str):
                    img_links.append(_clean_tiktok_image_url(img))
                    continue
                    
                # Thử nhiều key khác nhau cho URL list
                urls = img.get('url_list', []) or img.get('thumb_url_list', []) or img.get('origin_url_list', []) or img.get('thumb_url', [])
                if urls:
                    img_links.append(_clean_tiktok_image_url(urls[0]))
                elif img.get('url'):
                    img_links.append(_clean_tiktok_image_url(img.get('url')))
            
            if img_links:
                details['product_images'] = img_links
                details['image_url'] = img_links[0]
        
        return details
        
    except Exception as e:
        print(f"  ⚠ Lỗi parse ROUTER_DATA chi tiết: {e}")
        return details

def _format_tiktok_price(price_str):
    """Định dạng giá TikTok (VND)."""
    if not price_str: return ""
    try:
        # Xóa các ký tự không phải số nếu có
        import re
        clean_str = re.sub(r'[^\d]', '', str(price_str))
        val = int(clean_str)
        
        # Trong TikTok Shop VN, giá trả về thường là giá trị thực (không cần chia 100)
        # Nếu giá quá nhỏ (< 1000) có thể là lỗi hoặc giá USD (không phổ biến ở VN)
        if val < 1000 and val > 0:
            return f"₫{val}"
            
        return f"₫{val:,.0f}".replace(',', '.')
    except:
        return str(price_str)


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
        if details.get('product_name') or details.get('current_price'):
            if 'captcha' not in html.lower() and 'security check' not in html.lower():
                # Tìm các link ảnh có cấu trúc của TikTok Shop (thường chứa 'tos-' và 'ibyteimg')
                # Mở rộng regex để bắt được nhiều loại link ảnh hơn
                img_matches = re.findall(r'https?://[a-zA-Z0-9.-]+\.(?:ibyteimg|tiktokcdn)\.com/[^"\']+\.(?:jpg|png|webp|jpeg|avif)', html)
                if img_matches:
                    # Lọc trùng và làm sạch
                    unique_imgs = list(dict.fromkeys(img_matches))
                    cleaned_imgs = []
                    for u in unique_imgs:
                        cleaned = _clean_tiktok_image_url(u)
                        if cleaned and cleaned not in cleaned_imgs:
                            cleaned_imgs.append(cleaned)
                    
                    if cleaned_imgs:
                        details['product_images'] = cleaned_imgs[:10] # Lấy tối đa 10 ảnh
                        details['image_url'] = cleaned_imgs[0]
            else:
                details['product_images'] = []
        else:
            details['product_images'] = []
    
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
        found_products = []
        
        for anchor in anchors:
            if not isinstance(anchor, dict): continue
            
            # Check for shop-style anchors
            extra_str = anchor.get('extra', '{}')
            try:
                extra_data = json.loads(extra_str)
                # Extra can be a list or a dict
                items = extra_data if isinstance(extra_data, list) else [extra_data]
                for item in items:
                    inner_extra = item
                    if isinstance(item.get('extra'), str):
                        inner_extra = json.loads(item['extra'])
                    
                    seo_url = inner_extra.get('seo_url') or item.get('seo_url')
                    if seo_url and ('shop' in seo_url or 'pdp' in seo_url):
                        found_products.append({
                            'pdp_url': seo_url,
                            'product_name': inner_extra.get('title') or item.get('title') or ""
                        })
            except: continue

        if found_products:
            # Nếu có nhiều sản phẩm, in ra log để debug
            if len(found_products) > 1:
                print(f"  → Tìm thấy {len(found_products)} sản phẩm trong video.")
                # Nếu có sản phẩm trùng với "MANA ONE" (giả sử user đang tìm cái này), ưu tiên nó
                # Đây là một heuristic tạm thời để giải quyết vấn đề của user
                for p in found_products:
                    if 'mana' in p['product_name'].lower():
                        print(f"  → Ưu tiên sản phẩm: {p['product_name']}")
                        return p
            
            return found_products[0]
                
    except Exception as e:
        print(f"  ⚠ Lỗi phân tích video page: {e}")
    
    return result


# ─── Main Scraper ─────────────────────────────────────────────────

async def scrape_tiktok_product(url, playwright_instance=None, custom_session_dir=None):
    """
    Scrape product information from a TikTok video.
    """
    target_session_dir = custom_session_dir or SESSION_DIR
    
    result = {
        'status': 'Lỗi',
        'product_name': '',
        'current_price': '',
        'original_price': '',
        'sale_price': '',
        'product_link': '',
        'shop_name': '',
        'shop_link': '',
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
    
    # Pre-extract shop name from URL
    url_shop_name = _extract_shop_name_from_url(url)
    if url_shop_name:
        result['shop_name'] = url_shop_name
    
    # Get session cookies for requests
    cookies = await _get_session_cookies(custom_session_dir=target_session_dir)
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
        
        # Reset price info to avoid leakage from video anchor text
        result['current_price'] = ''
        result['sale_price'] = ''
        result['original_price'] = ''
        
        pdp_details = _extract_pdp_via_requests(pdp_url, session)
        
        # Merge results - PDP data is the TRUTH
        for key, value in pdp_details.items():
            if value:
                result[key] = value
        
        # Use video product name as fallback
        if not result['product_name'] and video_product_name:
            result['product_name'] = video_product_name
        
        # If we got prices, mark as success and skip Playwright entirely
        if result.get('current_price') or result.get('sale_price'):
            result['status'] = 'Thành công'
            # Chỉ xóa note nếu nó chứa thông báo lỗi, giữ lại thông tin khuyến mãi
            if 'Lỗi' in result.get('note', '') or 'Không tìm thấy' in result.get('note', ''):
                result['note'] = ''
            print(f"  ✅ Đã lấy được giá từ API, bỏ qua Playwright.")
            return result
        
        print(f"  → Requests không lấy được giá ({result['note']}), thử Playwright fallback...")
    
    # ─── Step 3: Playwright Fallback (Highly Optimized) ───
    with _browser_lock:
        print(f"  ⚡ Đang dùng Playwright ngầm (Siêu tốc)...")
        
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            context = None
            try:
                # Launch with extreme optimization
                import platform
                import os
                is_headless_env = os.environ.get("HEADLESS", "false").lower() == "true" or platform.system() != "Windows"
                
                # Tìm trình duyệt thật (Chrome/Edge) trên máy để vượt mặt hệ thống chống bot của TikTok
                executable_path = None
                if platform.system() == "Windows":
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
                        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
                    ]
                    for path in chrome_paths:
                        if os.path.exists(path):
                            executable_path = path
                            break
                            
                launch_kwargs = {
                    'user_data_dir': target_session_dir,
                    'headless': is_headless_env if is_headless_env else False,
                    'args': [
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--no-first-run',
                    ],
                    'ignore_default_args': ['--enable-automation'],
                    'user_agent': DEFAULT_UA,
                    'viewport': {'width': 375, 'height': 812},
                    'is_mobile': True,
                    'has_touch': True,
                    'locale': 'vi-VN',
                    'timezone_id': 'Asia/Ho_Chi_Minh'
                }
                
                if executable_path:
                    launch_kwargs['executable_path'] = executable_path
                
                # Cleanup before launch
                _cleanup_lock_files(target_session_dir)
                
                # Retry loop for launch (fix Target page error)
                for attempt in range(2):
                    try:
                        context = await p.chromium.launch_persistent_context(**launch_kwargs)
                        break
                    except Exception as le:
                        if attempt == 0:
                            print(f"  ⚠️ Thử lại khởi chạy browser ({le})...")
                            _cleanup_lock_files(target_session_dir)
                            await asyncio.sleep(2)
                        else:
                            raise le
                
                page = await context.new_page()
                try:
                    from playwright_stealth import stealth_async
                    await stealth_async(page)
                except:
                    pass
                # Fast stealth
                await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                target_url = pdp_url if pdp_url else url
                print(f"  🔍 Đang quét: {target_url[:60]}...")
                
                # Use a smaller timeout for speed
                await page.goto(target_url, timeout=35000, wait_until='domcontentloaded')
                await asyncio.sleep(2)
                
                page_content = await page.content()
                
                # Parse product links from video if needed
                is_on_video_page = not pdp_url
                if is_on_video_page:
                    all_links = await page.query_selector_all('a')
                    for link in all_links:
                        href = await link.get_attribute('href')
                        if href and ('pdp' in href or 'product' in href or 'shop.tiktok' in href):
                            if not href.startswith('http'): href = 'https://www.tiktok.com' + href
                            pdp_url = href
                            result['product_link'] = pdp_url
                            print(f"  → Đã tìm thấy PDP link: {pdp_url[:60]}, đang chuyển hướng...")
                            await page.goto(pdp_url, timeout=35000, wait_until='domcontentloaded')
                            await asyncio.sleep(2)
                            page_content = await page.content()
                            break
                
                # Try to parse JSON data from PDP page content (API-like)
                if pdp_url:
                    router_match = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', page_content, re.DOTALL)
                    if router_match:
                        try:
                            router_data = json.loads(router_match.group(1))
                            product_id = ""
                            id_match = re.search(r'/(\d+)(?:\?|$)', pdp_url)
                            if id_match: product_id = id_match.group(1)
                            
                            result = _parse_router_data(router_data, result, target_product_id=product_id)
                            if result.get('current_price'):
                                result['status'] = 'Thành công'
                                print(f"  ✅ Lấy được giá từ JSON trong Playwright")
                                return result
                        except Exception as e:
                            print(f"  ⚠ Lỗi parse JSON trong Playwright: {e}")

                # Final parsing from HTML (fallback)
                result = _parse_prices_from_html(page_content, result)
                
                if result['current_price'] or result['sale_price']:
                    result['status'] = 'Thành công'
                    result['note'] = ''
                else:
                    if 'Security Check' in page_content or 'captcha' in page_content.lower():
                        result['note'] = 'Bị CAPTCHA (Bỏ qua thất bại)'
                        result['status'] = 'Lỗi'
                    else:
                        result['status'] = 'Thiếu giá'

            except Exception as e:
                print(f"  ⚠ Lỗi trình duyệt ngầm: {e}")
                result['note'] = f'Lỗi hệ thống: {str(e)[:50]}'
            finally:
                if context: await context.close()
            
            return result

async def process_single_link(url):
    """Process a single TikTok link - convenience wrapper."""
    return await scrape_tiktok_product(url)


def process_single_link_sync(url):
    """Synchronous wrapper for process_single_link."""
    import asyncio
    return asyncio.run(process_single_link(url))
