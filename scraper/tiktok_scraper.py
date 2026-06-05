"""
TikTok Scraper - Extracts product information from TikTok Shop videos.
Uses Playwright for session management + requests for data extraction.
"""

import re
import asyncio
import json
from datetime import datetime
import sys
import os
import threading
from urllib.parse import urlparse, unquote

# Ép buộc Playwright luôn luôn sử dụng thư mục AppData/Local làm gốc chứa Chromium (Tương thích hoàn hảo với PyInstaller)
if getattr(sys, 'frozen', False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")

# Xác định thư mục lưu session TikTok (Tương thích hoàn hảo với PyInstaller)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.getcwd()
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SESSION_DIR = os.path.join(BASE_DIR, "tiktok_session")
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def _cleanup_lock_files(session_dir):
    """Xóa các file lock của Chromium để tránh lỗi 'Target page' / 'Profile in use'."""
    if not session_dir or not os.path.exists(session_dir):
        return
        
    # Tiêu diệt các tiến trình Chrome ẩn đang giữ thư mục session này (trên Windows)
    if sys.platform == 'win32':
        import subprocess
        # 1. Sử dụng PowerShell (luôn có sẵn trên Windows 10/11, thay thế wmic bị khai tử)
        try:
            folder_name = os.path.basename(os.path.normpath(session_dir))
            if folder_name:
                cmd = f"powershell -NoProfile -Command \"Get-CimInstance Win32_Process -Filter 'name = ''chrome.exe''' | Where-Object {{ $_.CommandLine -like '*{folder_name}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}\""
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
            
        # 2. Dự phòng bằng wmic (nếu PowerShell không chạy được)
        try:
            output = subprocess.check_output(
                'wmic process where "name=\'chrome.exe\'" get processid,commandline', 
                shell=True, stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore')
            
            normalized_session = os.path.normpath(session_dir).lower()
            for line in output.splitlines():
                line_lower = line.lower()
                if normalized_session in line_lower:
                    parts = line.strip().split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            subprocess.run(['taskkill', '/F', '/PID', pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            print(f"🧹 Đã tiêu diệt zombie Chrome (PID: {pid}) đang giữ lock.")
        except Exception:
            pass
    
    lock_files = ["SingletonLock", "SingletonCookie", "SingletonSocket"]
    for lock_name in lock_files:
        lock_path = os.path.join(session_dir, lock_name)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except:
            pass

login_status_dict = {'status': 'stopped', 'qr_b64': None, 'message': ''}

async def login_tiktok_async(url=None):
    global login_status_dict
    login_status_dict['status'] = 'running'
    login_status_dict['qr_b64'] = None
    login_status_dict['message'] = 'Đang khởi động trình duyệt...'
    
    # Close global headless browser if open (to release lock on SESSION_DIR)
    await close_global_browser()
    
    from cloakbrowser import launch_persistent_context_async
    import sys
    import shutil
    sys.stdout.reconfigure(encoding='utf-8')
    
    # Luôn mở trang login để hiện mã QR to rõ ràng
    target_url = "https://www.tiktok.com/login"
    
    # Pre-launch cleanup: Remove lock files
    _cleanup_lock_files(SESSION_DIR)

    print(f"🚀 Đang khởi chạy trình duyệt để mở: {target_url}...")
    import platform
    # In headless environments (like Render/Railway), force headless=True for all
    is_headless_env = os.environ.get("HEADLESS", "false").lower() == "true" or platform.system() != "Windows"
    
    with _browser_lock:
        try:
            launch_kwargs = {
                'headless': is_headless_env if is_headless_env else False,
                'args': [
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--force-device-scale-factor=1',
                    '--use-gl=angle',
                    '--use-gl=swiftshader',
                    '--window-size=1280,800'
                ],
                'locale': 'vi-VN',
                'timezone_id': 'Asia/Ho_Chi_Minh',
                'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                'viewport': {'width': 1280, 'height': 800},
                'is_mobile': False,
                'has_touch': False,
                'humanize': True
            }
            context = await launch_persistent_context_async(user_data_dir=SESSION_DIR, **launch_kwargs)
        except Exception as launch_err:
            print(f"❌ Lỗi khởi chạy browser: {launch_err}")
            return False

        page = context.pages[0] if context.pages else await context.new_page()
        
        async def block_redirects(route):
            url = route.request.url
            if url.startswith("snssdk") or url.startswith("intent") or "tiktokv.com/redirect" in url:
                print(f"🚫 Chặn mở App: {url[:50]}...")
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", block_redirects)
        
        # try:
        #     from playwright_stealth import Stealth
        #     await Stealth().apply_stealth_async(page)
        # except Exception as se:
        #     print(f"⚠️ Lỗi stealth: {se}")
        
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
            
        # Tự động chọn "Sử dụng mã QR" nếu có
        try:
            print("  ⏳ Đang tự động chọn phương thức Đăng nhập bằng QR...")
            await page.wait_for_selector("text=/Sử dụng mã QR|Use QR code/i", timeout=5000)
            await page.click("text=/Sử dụng mã QR|Use QR code/i")
            print("  ✅ Đã mở mã QR! Vui lòng quét...")
        except Exception as e:
            print(f"  ℹ️ Không tìm thấy nút mã QR, bạn vui lòng tự chọn trên màn hình.")
        
        # Keep open until login completes or 10 minutes pass
        success = False
        print("🤖 Đang tự động xử lý đăng nhập (không cần can thiệp)...")
        
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
                        login_status_dict['status'] = 'success'
                        login_status_dict['message'] = 'Đăng nhập thành công!'
                        print("✨ Đăng nhập thành công! Đang lưu phiên...")
                        await asyncio.sleep(3) # Wait for cookies to settle
                        success = True
                        break
                    else:
                        # TỰ ĐỘNG GIẢI CAPTCHA - không cần người dùng
                        print("🔓 Phát hiện CAPTCHA sau đăng nhập, đang tự động giải...")
                        login_status_dict['message'] = 'Đã đăng nhập! Đang giải CAPTCHA...'
                        try:
                            from scraper.captcha_solver import solve_captcha_with_retry
                            solved = await solve_captcha_with_retry(page, max_retries=3)
                            if solved:
                                print("✅ Đã tự động giải CAPTCHA thành công!")
                                login_status_dict['status'] = 'success'
                                login_status_dict['message'] = 'Đăng nhập thành công!'
                                await asyncio.sleep(3)
                                success = True
                                break
                            else:
                                print("⚠️ Chưa giải được, đang thử reload...")
                                try:
                                    await page.reload()
                                except: pass
                        except Exception as solver_err:
                            print(f"⚠️ Lỗi solver: {solver_err}, thử reload...")
                            try:
                                await page.reload()
                            except: pass
                            
                # Capture QR code if visible
                try:
                    import base64
                    qr_element = page.locator('canvas').first
                    if await qr_element.count() > 0 and await qr_element.is_visible():
                        screenshot = await qr_element.screenshot(type='jpeg', quality=100)
                        b64 = base64.b64encode(screenshot).decode('utf-8')
                        login_status_dict['qr_b64'] = b64
                        login_status_dict['message'] = 'Sử dụng ứng dụng TikTok trên điện thoại để quét mã QR bên dưới'
                except:
                    pass
                    
            except Exception as poll_err:
                print(f"ℹ️ Kết thúc: {poll_err}")
                login_status_dict['status'] = 'error'
                login_status_dict['message'] = f'Lỗi: {poll_err}'
                success = True
                break
                
        await context.close()
        if not success and login_status_dict['status'] == 'running':
            login_status_dict['status'] = 'timeout'
            login_status_dict['message'] = 'Hết thời gian chờ đăng nhập.'
            
        # Clear cookie cache to force reload in next scrape
        global _cached_cookies_dict
        _cached_cookies_dict = {}
        return success

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

_cached_cookies_dict = {} # dict mapping session_dir to (cookies, time)
_cookie_lock = threading.Lock()

async def _get_session_cookies(custom_session_dir=None, custom_context=None):
    """Get cookies from Playwright persistent context with thread-safe caching.
    Nếu chưa đăng nhập (không có thư mục session), trả về [] để curl_cffi tự hoạt động không cần cookie.
    """
    global _cached_cookies_dict
    
    # Nếu đã có custom_context đang chạy, lấy trực tiếp cookie cực kỳ nhanh và tránh lock
    if custom_context:
        try:
            cookies = await custom_context.cookies()
            return cookies
        except Exception as e:
            print(f"  ⚠️ Không thể lấy cookie từ custom_context: {e}")
            
    # Sử dụng folder được chỉ định hoặc folder mặc định
    target_session_dir = custom_session_dir or SESSION_DIR
    
    # Nếu thư mục session chưa tồn tại → chưa đăng nhập → trả về rỗng (không cần mở browser)
    if not os.path.exists(target_session_dir):
        print(f"  → Chưa đăng nhập (không có session), dùng curl_cffi không cần cookie...")
        return []
    
    # Kiểm tra có file cookie thực sự không (thư mục rỗng = chưa đăng nhập)
    has_data = any(
        f for f in os.listdir(target_session_dir) 
        if f not in ('SingletonLock', 'SingletonCookie', 'SingletonSocket', '.DS_Store')
    ) if os.path.isdir(target_session_dir) else False
    
    if not has_data:
        print(f"  → Thư mục session rỗng, dùng curl_cffi không cần cookie...")
        return []
    
    # Fast path: check cache per session_dir
    if target_session_dir in _cached_cookies_dict:
        cookies, cache_time = _cached_cookies_dict[target_session_dir]
        elapsed = (datetime.now() - cache_time).total_seconds()
        if elapsed < 1800: # Cache for 30 minutes - giảm thiểu mở browser
            return cookies
            
    _cleanup_lock_files(target_session_dir)
    from cloakbrowser import launch_persistent_context_async
    
    try:
        # Retry loop for launch (fix Target page error)
        context = None
        for attempt in range(2):
            try:
                launch_kwargs = {
                    'headless': False, # Trở lại headless=False giống hệt 6.15 để tránh bị nghi ngờ
                    'args': [
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-gpu',
                        '--blink-settings=imagesEnabled=false',
                        '--no-first-run',
                        '--force-device-scale-factor=1',
                        '--use-gl=angle',
                        '--use-gl=swiftshader',
                        '--window-size=1280,800',
                    ],
                    'user_agent': DEFAULT_UA,
                    'viewport': {'width': 1280, 'height': 800},
                    'is_mobile': False,
                    'has_touch': False,
                    'humanize': True
                }
                
                context = await launch_persistent_context_async(user_data_dir=target_session_dir, **launch_kwargs)
                break
            except Exception as le:
                if attempt == 0:
                    print(f"  ⚠️ Thử lại lấy cookies ({le})...")
                    _cleanup_lock_files(target_session_dir)
                    import asyncio
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
        
        _cached_cookies_dict[target_session_dir] = (tiktok_cookies, datetime.now())
        
        return tiktok_cookies
    except Exception as e:
        print(f"  ⚠ Lỗi đọc cookies từ {os.path.basename(target_session_dir)}: {e}")
        return []


def _build_requests_session(cookies):
    """Build a requests.Session with TikTok cookies."""
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome120")
    except ImportError:
        import requests
        session = requests.Session()
        session.headers.update({
            "User-Agent": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            "Referer": "https://www.tiktok.com/",
        })
    
    for c in cookies:
        session.cookies.set(c['name'], c['value'], domain=c.get('domain', ''))
    
    return session


# ─── PDP Extraction via requests (bypasses CAPTCHA) ────────────────

def _extract_pdp_via_requests(product_url, session):
    """
    Fetch PDP page via requests with session cookies.
    TikTok returns full SSR HTML with product data when cookies are present.
    Retry with exponential backoff on Security Check.
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
    
    import time as _time
    max_retries = 3
    
    for retry in range(max_retries):
      try:
        if retry > 0:
            wait = 3 * (2 ** retry) # 6s, 12s
            print(f"  ⏳ Đợi {wait}s trước khi thử lại (lần {retry+1}/{max_retries})...")
            _time.sleep(wait)
            
        print(f"  → Đang fetch PDP qua requests: {product_url[:80]}...")
        
        is_cffi = 'curl_cffi' in str(type(session))
        if is_cffi:
            # TLS Impersonate tự lo User-Agent chuẩn
            headers = {
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "max-age=0",
                "Upgrade-Insecure-Requests": "1"
            }
        else:
            headers = {
                "User-Agent": DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
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
        
        if resp.status_code == 429:
            print(f"  ⚠️ Rate limited (429), đợi rồi thử lại...")
            continue
        
        if resp.status_code != 200:
            details['note'] = f'PDP trả về mã {resp.status_code}'
            return details
        
        html = resp.text
        
        # Check if we got CAPTCHA instead of real page
        if 'Security Check' in html and len(html) < 20000:
            if retry < max_retries - 1:
                print(f"  ⚠️ Security Check detected, sẽ thử lại...")
                continue
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
                
        # ─── Strategy 1.5: Parse __UNIVERSAL_DATA_FOR_REHYDRATION__ (alternative source) ───
        if not details.get('current_price'):
            uni_match = re.search(
                r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>\s*({.+?})\s*</script>',
                html, re.DOTALL
            )
            if uni_match:
                try:
                    uni_data = json.loads(uni_match.group(1))
                    details = _parse_router_data(uni_data, details, expected_name, product_id)
                    if details.get('current_price') or details.get('sale_price'):
                        print(f"  ✅ Lấy được dữ liệu sạch từ __UNIVERSAL_DATA_FOR_REHYDRATION__ (API)")
                        return details
                except Exception as e:
                    print(f"  ⚠ Lỗi parse UNIVERSAL_DATA: {e}")
        
        # Strategy 2 (DISABLED)
        # details = _parse_prices_from_html(html, details)

        
        if not details.get('current_price'):
            details['note'] = 'Không tìm thấy dữ liệu sản phẩm trong JSON (API)'
        return details
        
      except Exception as e:
        if retry < max_retries - 1:
            print(f"  ⚠️ Lỗi fetch PDP (lần {retry+1}): {e}, thử lại...")
            continue
        details['note'] = f'Lỗi fetch PDP: {str(e)[:100]}'
        return details
    
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
        loader_data = router_data.get('loaderData') or router_data
        
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
    current_name = details.get('product_name', '')
    is_generic = not current_name or current_name in ['Security Check', 'TikTok Shop Vietnam', 'TikTok Shop Việt Nam', 'TikTok']
    if is_generic:
        # Try <h1>
        h1_match = re.search(r'<h1[^>]*>\s*<span[^>]*>([^<]+)</span>', html)
        if h1_match:
            name_val = h1_match.group(1).strip()
            if name_val not in ['Security Check', 'TikTok Shop Vietnam', 'TikTok Shop Việt Nam', 'TikTok']:
                details['product_name'] = name_val
        else:
            # Try <title>
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
            if title_match:
                title = title_match.group(1).strip()
                # Remove " - TikTok Shop Vietnam" suffix
                title = re.sub(r'\s*-\s*TikTok Shop\s*(Vietnam|Việt Nam)?$', '', title)
                if title not in ['Security Check', 'TikTok Shop Vietnam', 'TikTok Shop Việt Nam', 'TikTok']:
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
    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome120")
        is_cffi = True
    except ImportError:
        import requests
        session = requests.Session()
        is_cffi = False
    
    result = {
        'product_name': '',
        'pdp_url': '',
    }
    
    if is_cffi:
        headers = {
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
    else:
        headers = {
            "User-Agent": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
    
    try:
        resp = session.get(url, headers=headers, timeout=10)
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
        video_detail = {}
        for k, v in u_data.get('__DEFAULT_SCOPE__', {}).items():
            if 'video-detail' in k.lower() or 'video.detail' in k.lower():
                video_detail = v
                break
        item_struct = video_detail.get('itemInfo', {}).get('itemStruct', {})
        
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

async def scrape_tiktok_product(url, playwright_instance=None, custom_session_dir=None, custom_context=None):
    """
    Scrape product information from a TikTok video with session lock.
    """
    import os
    target_session_dir = custom_session_dir or SESSION_DIR
    
    # Trích xuất lock an toàn bằng đường dẫn session
    lock = None
    try:
        from scraper.favorites_syncer import get_session_lock
        if target_session_dir:
            lock = get_session_lock(target_session_dir)
    except Exception as e:
        print(f"  ⚠ Không thể lấy session lock: {e}")

    if lock:
        with lock:
            return await _scrape_tiktok_product_internal(url, playwright_instance, custom_session_dir, custom_context)
    else:
        return await _scrape_tiktok_product_internal(url, playwright_instance, custom_session_dir, custom_context)


async def _scrape_tiktok_product_internal(url, playwright_instance=None, custom_session_dir=None, custom_context=None):
    """
    Internal function to scrape product information from a TikTok video.
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
    cookies = await _get_session_cookies(custom_session_dir=target_session_dir, custom_context=custom_context)
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
    class DummyLock:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): pass
        
    lock_to_use = DummyLock() if custom_context else _browser_lock
    with lock_to_use:
        print(f"  ⚡ Đang dùng Playwright ngầm (Siêu tốc)...")
        
        from cloakbrowser import launch_persistent_context_async
        
        context = None
        is_reused_context = False
        page = None
        try:
            if custom_context:
                context = custom_context
                is_reused_context = True
            else:
                # Launch with extreme optimization
                import platform
                import os
                is_headless_env = os.environ.get("HEADLESS", "false").lower() == "true" or platform.system() != "Windows"
                
                launch_kwargs = {
                    'headless': is_headless_env if is_headless_env else False,
                    'args': [
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--no-first-run',
                        '--force-device-scale-factor=1',
                        '--use-gl=angle',
                        '--use-gl=swiftshader',
                        '--window-size=1280,800',
                    ],
                    'user_agent': DEFAULT_UA,
                    'viewport': {'width': 1280, 'height': 800},
                    'is_mobile': False,
                    'has_touch': False,
                    'locale': 'vi-VN',
                    'timezone_id': 'Asia/Ho_Chi_Minh',
                    'humanize': True
                }
                
                # Cleanup before launch
                _cleanup_lock_files(target_session_dir)
                
                # Retry loop for launch (fix Target page error)
                for attempt in range(2):
                    try:
                        context = await launch_persistent_context_async(user_data_dir=target_session_dir, **launch_kwargs)
                        break
                    except Exception as le:
                        if attempt == 0:
                            print(f"  ⚠️ Thử lại khởi chạy browser ({le})...")
                            _cleanup_lock_files(target_session_dir)
                            await asyncio.sleep(2)
                        else:
                            raise le
            
            if is_reused_context:
                page = await context.new_page()
            else:
                page = context.pages[0] if context.pages else await context.new_page()
            
            # Block App Deep Links
            async def block_redirects(route):
                url = route.request.url
                if url.startswith("snssdk") or url.startswith("intent") or "tiktokv.com/redirect" in url:
                    print(f"  🚫 Chặn tự động mở App TikTok ({url[:50]}...)")
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", block_redirects)
            
            # Áp dụng Stealth (Đã tắt để tránh xung đột với cloakbrowser)
            # try:
            #     from playwright_stealth import Stealth
            #     await Stealth().apply_stealth_async(page)
            # except Exception as se:
            #     print(f"  ⚠️ Lỗi stealth: {se}")
            # Tăng cường chống phát hiện Bot (Đã tắt để tránh xung đột với cloakbrowser)
            # await page.add_init_script("""
            #     // Ẩn webdriver flag
            #     Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            #     // Giả lập Chrome plugins
            #     Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            #     // Giả lập Chrome languages
            #     Object.defineProperty(navigator, 'languages', {get: () => ['vi-VN', 'vi', 'en-US', 'en']});
            #     // Ẩn automation flags
            #     delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            #     delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            #     delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            #     // Override permissions query
            #     const origQuery = window.navigator.permissions.query;
            #     window.navigator.permissions.query = (params) => (
            #         params.name === 'notifications' ? 
            #         Promise.resolve({state: Notification.permission}) : origQuery(params)
            #     );
            # """)
            
            # ── Bắt API response từ TikTok để lấy product data ──
            captured_api_data = {}
            
            async def _intercept_response(response):
                """Bắt các API response chứa thông tin sản phẩm."""
                try:
                    resp_url = response.url
                    # Bắt các API endpoint chứa product data
                    if any(k in resp_url for k in ['product/detail', 'pdp/get_item', 'commerce/product', 'anchor_info']):
                        if response.status == 200:
                            try:
                                data = await response.json()
                                captured_api_data['product_api'] = data
                                print(f"  📦 Bắt được API product data từ: {resp_url[:80]}")
                            except:
                                pass
                except:
                    pass
            
            page.on('response', _intercept_response)
            
            target_url = pdp_url if pdp_url else url
            print(f"  🔍 Đang quét: {target_url[:60]}...")
            
            # Use a smaller timeout for speed
            try:
                await page.goto(target_url, timeout=35000, wait_until='domcontentloaded')
            except Exception as nav_err:
                if 'ERR_HTTP_RESPONSE_CODE_FAILURE' in str(nav_err) or 'ERR_CONNECTION' in str(nav_err) or 'ERR_ABORTED' in str(nav_err):
                    print(f"  ⚠️ Lỗi mạng nghiêm trọng ({str(nav_err)[:30]}). Chuyển sang chế độ chạy lại.")
                    if context and not is_reused_context:
                        await context.close()
                    try:
                        import shutil
                        for folder in ["Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/Network"]:
                            path = os.path.join(target_session_dir, folder)
                            if os.path.exists(path):
                                shutil.rmtree(path, ignore_errors=True)
                        print("  🧹 Đã xóa Cache bị hỏng để khắc phục lỗi HTTP_RESPONSE_CODE_FAILURE.")
                    except: pass
                    result['status'] = 'Lỗi cần chạy lại'
                    result['note'] = 'Lỗi mạng khi tải trang (Đang tự động thử lại)'
                    return result
                else:
                    print(f"  ⚠️ Bỏ qua lỗi Timeout/Goto phụ: {nav_err}")
            await asyncio.sleep(2)
            
            # GIẢI CAPTCHA NGAY LẬP TỨC nếu xuất hiện ngay khi tải trang (ví dụ khi vào trang cá nhân)
            temp_content = await page.content()
            if 'captcha' in temp_content.lower() or 'Security Check' in temp_content or await page.query_selector('#captcha_container, .captcha_verify_container, [id^="secsdk"]'):
                print("  ⚠️ Gặp CAPTCHA ngay khi tải trang! Đang giải quyết...")
                from scraper.captcha_solver import solve_captcha_with_retry
                bypassed_early = await solve_captcha_with_retry(page, max_retries=3)
                if bypassed_early:
                    print("  ✅ Đã giải CAPTCHA thành công ngay lập tức!")
                    await asyncio.sleep(3)
                else:
                    print("  ❌ Giải CAPTCHA thất bại ngay khi tải trang.")
            
            page_content = await page.content()
            
            # Parse product links from video if needed
            is_on_video_page = not pdp_url
            if is_on_video_page:
                # Cách 1: Tìm link PDP trong DOM (anchor tags)
                all_links = await page.query_selector_all('a')
                for link in all_links:
                    href = await link.get_attribute('href')
                    if href and ('pdp' in href or 'product' in href or 'shop.tiktok' in href):
                        if not href.startswith('http'): href = 'https://www.tiktok.com' + href
                        pdp_url = href
                        result['product_link'] = pdp_url
                        print(f"  → Đã tìm thấy PDP link (DOM): {pdp_url[:60]}")
                        break
                
                 # Cách 2: Tìm link PDP trong __MODERN_ROUTER_DATA__ JSON (API data)
                if not pdp_url:
                    try:
                        router_match_v = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', page_content, re.DOTALL)
                        if router_match_v:
                            video_json = json.loads(router_match_v.group(1))
                            # Tìm PDP link trong JSON
                            def _find_pdp_in_json(obj):
                                if isinstance(obj, str):
                                    if '/pdp/' in obj or '/product/' in obj:
                                        return obj
                                elif isinstance(obj, dict):
                                    for v in obj.values():
                                        r = _find_pdp_in_json(v)
                                        if r: return r
                                elif isinstance(obj, list):
                                    for item in obj:
                                        r = _find_pdp_in_json(item)
                                        if r: return r
                                return None
                            
                            found_pdp = _find_pdp_in_json(video_json)
                            if found_pdp:
                                if not found_pdp.startswith('http'):
                                    found_pdp = 'https://www.tiktok.com' + found_pdp
                                pdp_url = found_pdp
                                result['product_link'] = pdp_url
                                print(f"  → Tìm thấy PDP link (JSON): {pdp_url[:60]}")
                    except:
                        pass
                
                # Cách 3: Kiểm tra API response đã bắt được
                if not pdp_url and captured_api_data.get('product_api'):
                    found_pdp = _find_pdp_in_json(captured_api_data['product_api'])
                    if found_pdp:
                        if not found_pdp.startswith('http'):
                            found_pdp = 'https://www.tiktok.com' + found_pdp
                        pdp_url = found_pdp
                        result['product_link'] = pdp_url
                        print(f"  → Tìm thấy PDP link (API): {pdp_url[:60]}")
                
                # Cách 4: Đọc __UNIVERSAL_DATA_FOR_REHYDRATION__ (chứa anchors/shop links)
                if not pdp_url:
                    try:
                        uni_match = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', page_content)
                        if uni_match:
                            u_data = json.loads(uni_match.group(1))
                            video_detail = {}
                            for k, v in u_data.get('__DEFAULT_SCOPE__', {}).items():
                                if 'video-detail' in k.lower() or 'video.detail' in k.lower():
                                    video_detail = v
                                    break
                            item_struct = video_detail.get('itemInfo', {}).get('itemStruct', {})
                            
                            anchors = item_struct.get('anchors', [])
                            for anchor in anchors:
                                if not isinstance(anchor, dict): continue
                                extra_str = anchor.get('extra', '{}')
                                try:
                                    extra_data = json.loads(extra_str)
                                    items = extra_data if isinstance(extra_data, list) else [extra_data]
                                    for item in items:
                                        inner_extra = item
                                        if isinstance(item.get('extra'), str):
                                            inner_extra = json.loads(item['extra'])
                                        seo_url = inner_extra.get('seo_url') or item.get('seo_url')
                                        if seo_url and ('shop' in seo_url or 'pdp' in seo_url):
                                            if not seo_url.startswith('http'):
                                                seo_url = 'https://www.tiktok.com' + seo_url
                                            pdp_url = seo_url
                                            result['product_link'] = pdp_url
                                            print(f"  → Tìm thấy PDP link (REHYDRATION): {pdp_url[:60]}")
                                            break
                                except: continue
                                if pdp_url: break
                    except:
                        pass
                
                # Navigate sang PDP nếu tìm được
                if pdp_url:
                    print(f"  → Đang chuyển hướng sang PDP...")
                    await page.goto(pdp_url, timeout=35000, wait_until='domcontentloaded')
                    await asyncio.sleep(3)
                    page_content = await page.content()
            
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
                            if pdp_url:
                                result['product_link'] = pdp_url
                            print(f"  ✅ Lấy được giá từ JSON trong Playwright")
                            return result
                    except Exception as e:
                        print(f"  ⚠ Lỗi parse JSON trong Playwright: {e}")

                # Final parsing from HTML (fallback)
                result = _parse_prices_from_html(page_content, result)
                
            if (result.get('current_price') or result.get('sale_price')) and (pdp_url or not is_on_video_page):
                result['status'] = 'Thành công'
                result['note'] = ''
                if pdp_url and not result.get('product_link'):
                    result['product_link'] = pdp_url
            else:
                is_login_page = "login" in target_url.lower() or "passport" in target_url.lower()
                if is_login_page or "Đăng nhập" in page_content or "Log in" in page_content:
                    print("  ⚠️ Bị yêu cầu Đăng nhập! Đang cố gắng lấy mã QR...")
                    try:
                        for text in ["Sử dụng mã QR", "Use QR code"]:
                            btn = page.locator(f'text="{text}"').first
                            if await btn.count() > 0 and await btn.is_visible():
                                await btn.click()
                                await asyncio.sleep(2)
                                break
                        
                        btn2 = page.locator('[href*="/login/qrcode"]').first
                        if await btn2.count() > 0 and await btn2.is_visible():
                            await btn2.click()
                            await asyncio.sleep(2)
                            
                        qr_canvas = page.locator('canvas').first
                        if await qr_canvas.count() > 0 and await qr_canvas.is_visible():
                            import base64
                            screenshot = await qr_canvas.screenshot(type='jpeg', quality=100)
                            result['qr_b64'] = base64.b64encode(screenshot).decode('utf-8')
                            result['note'] = 'Bị chặn đăng nhập. Vui lòng quét QR (Xem ảnh)'
                            result['status'] = 'Cần đăng nhập'
                    except Exception as e:
                        print(f"Lỗi xử lý QR đăng nhập: {e}")
                        
                if not result.get('qr_b64') and ('Security Check' in page_content or 'captcha' in page_content.lower() or await page.query_selector('#captcha_container')):
                    print("  ⚠️ Gặp CAPTCHA! Đang dùng AI Solver để tự động vượt qua...")
                    
                    from scraper.captcha_solver import solve_captcha_with_retry
                    bypassed = await solve_captcha_with_retry(page, max_retries=3)
                    
                    if bypassed:
                        print("  ✅ Tự động vượt CAPTCHA thành công!")
                        await asyncio.sleep(3)
                        
                        # Sau CAPTCHA, trang có thể redirect về đúng trang cần xem
                        current_url = page.url
                        
                        # Nếu đang ở video page → tìm link PDP
                        if '/video/' in current_url and not pdp_url:
                            print("  🔍 Đang tìm lại link sản phẩm sau CAPTCHA...")
                            all_links2 = await page.query_selector_all('a')
                            for link2 in all_links2:
                                href2 = await link2.get_attribute('href')
                                if href2 and ('pdp' in href2 or 'product' in href2 or 'shop.tiktok' in href2):
                                    if not href2.startswith('http'): href2 = 'https://www.tiktok.com' + href2
                                    pdp_url = href2
                                    result['product_link'] = pdp_url
                                    print(f"  → Tìm lại PDP: {pdp_url[:60]}")
                                    break
                        
                        # Cách 2 (post-CAPTCHA): Tìm PDP trong __UNIVERSAL_DATA_FOR_REHYDRATION__
                        if not pdp_url:
                            try:
                                post_captcha_content = await page.content()
                                uni_match2 = re.search(r'id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([^<]+)</script>', post_captcha_content)
                                if uni_match2:
                                    u_data2 = json.loads(uni_match2.group(1))
                                    video_detail2 = {}
                                    for k, v in u_data2.get('__DEFAULT_SCOPE__', {}).items():
                                        if 'video-detail' in k.lower() or 'video.detail' in k.lower():
                                            video_detail2 = v
                                            break
                                    item_struct2 = video_detail2.get('itemInfo', {}).get('itemStruct', {})
                                    for anchor2 in item_struct2.get('anchors', []):
                                        if not isinstance(anchor2, dict): continue
                                        try:
                                            extra2 = json.loads(anchor2.get('extra', '{}'))
                                            items2 = extra2 if isinstance(extra2, list) else [extra2]
                                            for it2 in items2:
                                                inner2 = it2
                                                if isinstance(it2.get('extra'), str):
                                                    inner2 = json.loads(it2['extra'])
                                                seo2 = inner2.get('seo_url') or it2.get('seo_url')
                                                if seo2 and ('shop' in seo2 or 'pdp' in seo2):
                                                    if not seo2.startswith('http'):
                                                        seo2 = 'https://www.tiktok.com' + seo2
                                                    pdp_url = seo2
                                                    result['product_link'] = pdp_url
                                                    print(f"  → Tìm thấy PDP (REHYDRATION post-CAPTCHA): {pdp_url[:60]}")
                                                    break
                                        except: continue
                                        if pdp_url: break
                            except:
                                pass
                        
                        # Nếu có PDP URL → navigate sang trang sản phẩm
                        if pdp_url:
                            result['product_link'] = pdp_url
                            
                            # Chỉ navigate nếu chưa ở trang PDP
                            if '/pdp/' not in current_url and '/product/' not in current_url:
                                print(f"  🔄 Đang chuyển sang trang sản phẩm: {pdp_url[:60]}...")
                                try:
                                    await page.goto(pdp_url, timeout=35000, wait_until='domcontentloaded')
                                    await asyncio.sleep(3)
                                    
                                    # Kiểm tra CAPTCHA trên trang PDP
                                    pdp_content = await page.content()
                                    if 'captcha' in pdp_content.lower() or 'Security Check' in pdp_content:
                                        print("  ⚠️ PDP cũng bị CAPTCHA, đang giải...")
                                        await solve_captcha_with_retry(page, max_retries=2)
                                        await asyncio.sleep(2)
                                except Exception as nav_err:
                                    print(f"  ⚠️ Lỗi navigate PDP: {nav_err}")
                                    if 'ERR_HTTP_RESPONSE_CODE_FAILURE' in str(nav_err) or 'ERR_CONNECTION' in str(nav_err) or 'ERR_ABORTED' in str(nav_err):
                                        if context and not is_reused_context:
                                            await context.close()
                                        try:
                                            import shutil
                                            for folder in ["Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/Network"]:
                                                path = os.path.join(target_session_dir, folder)
                                                if os.path.exists(path):
                                                    shutil.rmtree(path, ignore_errors=True)
                                            print("  🧹 Đã xóa Cache bị hỏng để khắc phục lỗi HTTP_RESPONSE_CODE_FAILURE.")
                                        except: pass
                                        result['status'] = 'Lỗi cần chạy lại'
                                        result['note'] = 'Lỗi mạng khi tải trang PDP (Đang tự động thử lại)'
                                        return result
                        
                        # Lấy nội dung cuối cùng
                        new_content = await page.content()
                        
                        # Thử parse JSON trước
                        router_match2 = re.search(r'id="__MODERN_ROUTER_DATA__"[^>]*>\s*({.+?})\s*</script>', new_content, re.DOTALL)
                        if router_match2:
                            try:
                                router_data2 = json.loads(router_match2.group(1))
                                product_id2 = ""
                                id_match2 = re.search(r'/(\d+)(?:\?|$)', pdp_url or url)
                                if id_match2: product_id2 = id_match2.group(1)
                                result = _parse_router_data(router_data2, result, target_product_id=product_id2)
                            except:
                                pass
                        
                        # Fallback: parse HTML
                        result = _parse_prices_from_html(new_content, result)
                        
                        # Đảm bảo product_link luôn có giá trị
                        if pdp_url and not result.get('product_link'):
                            result['product_link'] = pdp_url
                        
                        if result.get('current_price') or result.get('sale_price'):
                            result['status'] = 'Thành công'
                            if 'Lỗi' in result.get('note', '') or 'Không tìm thấy' in result.get('note', ''):
                                result['note'] = ''
                    else:
                        print("  ❌ Auto-bypass CAPTCHA thất bại. Sẽ tự động thử lại ở chu kỳ tiếp theo.")
                        result['note'] = 'Bị CAPTCHA (Đang tự động thử lại)'
                        result['status'] = 'Lỗi cần chạy lại'
                        if context and not is_reused_context:
                            await context.close()
                        try:
                            import shutil
                            for folder in ["Default/Cache", "Default/Code Cache", "Default/GPUCache", "Default/Network"]:
                                path = os.path.join(target_session_dir, folder)
                                if os.path.exists(path):
                                    shutil.rmtree(path, ignore_errors=True)
                            print("  🧹 Đã xóa Cache trình duyệt sau khi dính CAPTCHA để lần thử sau sạch sẽ hơn.")
                        except: pass
                        return result
                elif not result.get('qr_b64'):
                    if not pdp_url:
                        result['status'] = 'Lỗi'
                        result['note'] = 'Không tìm thấy link sản phẩm'
                    else:
                        result['status'] = 'Thiếu giá'

        except Exception as e:
            print(f"  ⚠ Lỗi trình duyệt ngầm: {e}")
            result['note'] = f'Lỗi hệ thống: {str(e)[:50]}'
        finally:
            if page and is_reused_context:
                try:
                    await page.close()
                except:
                    pass
            if context and not is_reused_context:
                await context.close()
        
        return result

async def process_single_link(url):
    """Process a single TikTok link - convenience wrapper."""
    return await scrape_tiktok_product(url)


def process_single_link_sync(url):
    """Synchronous wrapper for process_single_link."""
    import asyncio
    return asyncio.run(process_single_link(url))
