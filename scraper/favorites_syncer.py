import os
import sys

# Ép buộc Playwright luôn luôn sử dụng thư mục AppData/Local làm gốc chứa Chromium (Tương thích hoàn hảo với PyInstaller)
if getattr(sys, 'frozen', False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")

import json
import asyncio
import threading
from datetime import datetime
from scraper.sheet_manager import append_link, get_client
from playwright.async_api import async_playwright

# Xác định thư mục gốc để lưu cấu hình và phiên làm việc (Tương thích hoàn hảo với PyInstaller)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.getcwd()
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNC_CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'sync_configs.json')
SESSION_BASE_DIR = BASE_DIR

# Quản lý khóa để tránh tranh chấp thư mục session giữa luồng đăng nhập và luồng đồng bộ ngầm
_session_locks = {}
_lock_lock = threading.Lock()

def get_session_lock(profile_name):
    with _lock_lock:
        if profile_name not in _session_locks:
            _session_locks[profile_name] = threading.Lock()
        return _session_locks[profile_name]

# Global state
sync_status = {
    "is_running": False,
    "last_run": None,
    "logs": []
}

# Thêm bộ lọc để tránh xung đột khi đang đăng nhập trên Web UI
active_logins = set()

def load_sync_configs():
    if not os.path.exists(SYNC_CONFIG_PATH):
        return []
    with open(SYNC_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f).get('configs', [])

def save_sync_configs(configs):
    os.makedirs(os.path.dirname(SYNC_CONFIG_PATH), exist_ok=True)
    with open(SYNC_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({'configs': configs}, f, ensure_ascii=False, indent=2)

def add_sync_log(msg):
    time_str = datetime.now().strftime("%H:%M:%S")
    log_msg = f"[{time_str}] {msg}"
    sync_status["logs"].insert(0, log_msg)
    if len(sync_status["logs"]) > 100:
        sync_status["logs"].pop()
    print(log_msg)

async def extract_favorites(session_dir, seen_links=None, target_url=None):
    """Mở browser ẩn để lấy video trong tab Đã Thích (Liked)."""
    if seen_links is None:
        seen_links = []
        
    links = []
    try:
        async with async_playwright() as p:
            # Tìm executable
            executable_path = None
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
            
            kwargs = {
                'user_data_dir': session_dir,
                'headless': False, # Bắt buộc False để dùng chế độ headful
                'args': [
                    '--disable-blink-features=AutomationControlled', 
                    '--no-sandbox', 
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--window-size=1280,720'
                ],
                'viewport': {'width': 1280, 'height': 720},
                'is_mobile': False,
                'has_touch': False,
                'locale': 'vi-VN',
                'timezone_id': 'Asia/Ho_Chi_Minh',
                'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
            if executable_path:
                kwargs['executable_path'] = executable_path

            # Pre-launch cleanup
            from scraper.tiktok_scraper import _cleanup_lock_files
            _cleanup_lock_files(session_dir)

            context = None
            for attempt in range(2):
                try:
                    context = await p.chromium.launch_persistent_context(**kwargs)
                    break
                except Exception as le:
                    if attempt == 0:
                        _cleanup_lock_files(session_dir)
                        await asyncio.sleep(2)
                    else:
                        raise le
                        
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Áp dụng Stealth để chống tường lửa/chống bot của TikTok cực kỳ hiệu quả
            try:
                from playwright_stealth import Stealth
                await Stealth().apply_stealth_async(page)
            except Exception as se:
                print(f"⚠️ Không thể kích hoạt Stealth: {se}")
            
            # TỐI ƯU HÓA: Chặn tải hình ảnh và media để siêu tiết kiệm RAM và Bandwidth
            async def intercept_route(route):
                if route.request.resource_type in ["image", "media"]:
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", intercept_route)
            
            # Khai báo biến lưu video từ API
            api_links = []
            
            # Hàm lắng nghe và chặn bắt (intercept) API của TikTok (Có thể là favorite/item_list hoặc post/item_list)
            async def handle_response(response):
                try:
                    url = response.url
                    if "/api/favorite/item_list/" in url or "/api/post/item_list/" in url:
                        json_data = await response.json()
                        if "itemList" in json_data:
                            for item in json_data["itemList"]:
                                video_id = item.get("id")
                                author = item.get("author", {}).get("uniqueId")
                                if video_id and author:
                                    link = f"https://www.tiktok.com/@{author}/video/{video_id}"
                                    if link not in api_links:
                                        api_links.append(link)
                except Exception:
                    pass

            # Đăng ký listener để bắt các luồng mạng (API)
            page.on("response", lambda response: asyncio.create_task(handle_response(response)))
            
            # Tới trang profile (Sử dụng URL trực tiếp từ người dùng nếu có)
            profile_url = target_url if target_url and target_url.startswith("http") else "https://www.tiktok.com/profile"
            # TÌM API TEMPLATE (Bắt request hợp lệ đầu tiên của TikTok)
            target_api = None
            async def intercept_api(response):
                nonlocal target_api
                if "/api/post/item_list/" in response.url and not target_api:
                    target_api = response.url
            
            page.on("response", intercept_api)
            
            add_sync_log(f"Đang truy cập kênh: {profile_url}")
            await page.goto(profile_url, timeout=60000, wait_until="domcontentloaded")
            
            # BYPASS CAPTCHA LẶP LẠI ĐẾN KHI THÀNH CÔNG
            for bypass_attempt in range(5):
                await asyncio.sleep(3)
                if await page.locator("#captcha-verify-image").count() > 0 or await page.locator(".captcha_verify_container").count() > 0:
                    add_sync_log(f"⚠️ Phát hiện Captcha (Lần {bypass_attempt+1})! Đang chọc và tự động tải lại trang để vượt qua...")
                    await page.reload(wait_until="domcontentloaded")
                else:
                    break
                    
            add_sync_log(f"Đang kiểm tra tab Đã thích bằng API nội bộ...")
            
            # Đợi một chút để TikTok gửi API đầu tiên
            for _ in range(15):
                if target_api: break
                await asyncio.sleep(1)
                
            if not target_api:
                add_sync_log("❌ Không bắt được API cơ sở. Có thể do mạng chậm hoặc bị chặn hoàn toàn!")
                await context.close()
                return []
                
            add_sync_log("🎯 Đã thiết lập xong đường dẫn API bí mật. Bắt đầu tải dữ liệu...")
            
            # Tiêm mã JS để tự động cuộn (fetch) qua API mà không cần đụng vào giao diện
            import urllib.parse
            parsed = urllib.parse.urlparse(target_api)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            if 'X-Bogus' in params: del params['X-Bogus']
            if 'msToken' in params: del params['msToken']
            
            # Gỡ bỏ các tham số không cần thiết để tạo base URL
            base_query = urllib.parse.urlencode(params)
            base_api_url = f"{parsed.scheme}://{parsed.netloc}/api/favorite/item_list/?{base_query}"
            
            # Chạy vòng lặp fetch trong trình duyệt
            # Chỉ lấy 5 link đầu tiên lưu vào bộ nhớ đệm để so sánh cho lần sau
            all_extracted_links = await page.evaluate(f"""async (baseApiUrl) => {{
                let cursor = 0;
                let hasMore = true;
                let results = [];
                let seen_links = {json.dumps(seen_links) if seen_links else '[]'};
                // Chỉ so sánh với 5 link mới nhất trong bộ nhớ đệm
                let recent_cached_links = seen_links.slice(0, 5); 
                let stopFetching = false;
                
                for (let i = 0; i < 30; i++) {{ // Tối đa 30 trang
                    if (!hasMore || stopFetching) break;
                    
                    let urlObj = new URL(baseApiUrl);
                    urlObj.searchParams.set('cursor', cursor);
                    
                    try {{
                        const res = await fetch(urlObj.toString());
                        const data = await res.json();
                        
                        if (data && data.itemList) {{
                            for (const item of data.itemList) {{
                                const video_id = item.id;
                                const author = item.author ? item.author.uniqueId : null;
                                if (video_id && author) {{
                                    const link = `https://www.tiktok.com/@${{author}}/video/${{video_id}}`;
                                    
                                    // So sánh với 5 link đã lưu trong bộ nhớ đệm
                                    if (recent_cached_links.includes(link)) {{
                                        stopFetching = true;
                                        break;
                                    }}
                                    
                                    if (!results.includes(link)) {{
                                        results.push(link);
                                    }}
                                }}
                            }}
                            
                            if (stopFetching) break;
                            
                            if (data.hasMore && data.cursor) {{
                                cursor = data.cursor;
                            }} else {{
                                hasMore = false;
                            }}
                        }} else {{
                            hasMore = false;
                        }}
                    }} catch (e) {{
                        break;
                    }}
                    
                    await new Promise(r => setTimeout(r, 1000));
                }}
                return results;
            }}""", base_api_url)
            
            links = all_extracted_links or []
            
            if len(links) == 0:
                add_sync_log("⚠️ Không có video Đã Thích mới nào (hoặc danh sách bị ẩn).")
            else:
                add_sync_log(f"✅ Đã quét được {len(links)} video Đã Thích mới qua API.")
                
            await context.close()
    except Exception as e:
        add_sync_log(f"Lỗi khi trích xuất tài khoản {os.path.basename(session_dir)}: {str(e)}")
    
    # Loại bỏ link trùng, giữ nguyên thứ tự (mới nhất ở trên)
    unique_links = []
    for l in links:
        if l not in unique_links:
            unique_links.append(l)
            
    # Trả về toàn bộ (nếu cuộn tới nhớ đệm) hoặc 10 video đầu (nếu chạy lần đầu)
    if not seen_links or len(seen_links) == 0:
        return unique_links[:10]
    return unique_links

def process_account_sync_multiple(profile_name, configs, target_url):
    """Xử lý đồng bộ 1 tài khoản cho nhiều sheet."""
    # Thử acquire khóa, nếu đang bận thì bỏ qua
    lock = get_session_lock(profile_name)
    if not lock.acquire(blocking=False):
        add_sync_log(f"Tài khoản {profile_name} đang bận tiến trình khác. Tạm thời bỏ qua chu kỳ đồng bộ này.")
        return
        
    try:
        session_dir = os.path.join(SESSION_BASE_DIR, f"tiktok_session_{__import__('re').sub(r'[\\\\/:*?\"<>|]', '_', profile_name)}")
        seen_links_file = os.path.join(session_dir, "seen_links.json")
        
        # Load seen links to check for new videos
        seen_links = []
        is_first_run = not os.path.exists(seen_links_file)
        if not is_first_run:
            try:
                with open(seen_links_file, 'r', encoding='utf-8') as f:
                    seen_links = json.load(f)
            except:
                is_first_run = True
                
        # Get config details cho tất cả các sheet
        from main import get_config
        valid_sheet_configs = []
        for config in configs:
            sheet_config_id = config.get("sheet_config_id")
            if sheet_config_id:
                sheet_config = get_config(sheet_config_id)
                if sheet_config:
                    valid_sheet_configs.append(sheet_config)
                else:
                    add_sync_log(f"Không tìm thấy cấu hình Sheet ID {sheet_config_id} cho tài khoản {profile_name}")
                    
        if not valid_sheet_configs:
            add_sync_log(f"Tài khoản {profile_name} không có cấu hình Sheet nào hợp lệ.")
            return
            
        add_sync_log(f"Đang kiểm tra danh sách Đã thích của kênh {target_url}...")
        
        # Chạy async lấy link
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            recent_links = loop.run_until_complete(extract_favorites(session_dir, seen_links, target_url=target_url))
        finally:
            loop.close()
            
        if not recent_links:
            if is_first_run:
                os.makedirs(session_dir, exist_ok=True)
                with open(seen_links_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)
            add_sync_log(f"Tài khoản {profile_name}: Không tìm thấy video yêu thích nào.")
            return

        if is_first_run:
            # Lần đầu chạy đồng bộ: Lấy 10 video mới nhất đẩy lên Sheet, các video cũ hơn chỉ lưu vào cache
            try:
                os.makedirs(session_dir, exist_ok=True)
                with open(seen_links_file, 'w', encoding='utf-8') as f:
                    json.dump(recent_links, f)
                    
                new_links_to_push = recent_links[:10]
                add_sync_log(f"Tài khoản {profile_name}: Khởi tạo lần đầu, sẽ đồng bộ {len(new_links_to_push)} video mới nhất.")
            except Exception as e:
                add_sync_log(f"Lỗi khi lưu cache cho {profile_name}: {str(e)}")
                return
        else:
            # Lọc ra các video thực sự mới (chưa có trong cache)
            new_links_to_push = []
            for link in recent_links:
                if link not in seen_links:
                    new_links_to_push.append(link)

        if not new_links_to_push:
            add_sync_log(f"Tài khoản {profile_name}: Không tìm thấy video yêu thích nào mới.")
            return

        # Lưu danh sách seen_links cập nhật
        updated_seen_links = new_links_to_push + seen_links
        updated_seen_links = updated_seen_links[:200] # Giữ 200 link gần nhất
        try:
            os.makedirs(session_dir, exist_ok=True)
            with open(seen_links_file, 'w', encoding='utf-8') as f:
                json.dump(updated_seen_links, f)
        except Exception as e:
            add_sync_log(f"Lỗi khi cập nhật cache cho {profile_name}: {str(e)}")

        # Gom nhóm các link mới để cào 1 lần duy nhất cho mỗi link thay vì cào nhiều lần theo từng sheet (chống CAPTCHA)
        scrapes_needed = {} # { link_url: [ {'sheet_config': config, 'row_index': idx} ] }

        # Duyệt qua từng cấu hình Sheet để ghi
        for sheet_config in valid_sheet_configs:
            try:
                client = get_client()
                spreadsheet = client.open_by_key(sheet_config['spreadsheet_id'])
                worksheet = spreadsheet.worksheet(sheet_config['tab_name'])
                all_values = worksheet.get_all_values()
                
                # Giả sử link ở cột B (index 1)
                link_col_idx = ord(sheet_config.get('link_col', 'B').upper()) - 65
                existing_links = []
                for row in all_values:
                    if len(row) > link_col_idx:
                        l = row[link_col_idx].split('?')[0].strip()
                        if l: existing_links.append(l)
                        
                # Thêm các link chưa tồn tại
                links_to_add = []
                for link in reversed(new_links_to_push): # Thêm từ cũ đến mới
                    if link.split('?')[0].strip() not in existing_links:
                        links_to_add.append(link)
                
                if links_to_add:
                    from scraper.sheet_manager import append_links_batch
                    success, row_indices, added_count = append_links_batch(
                        sheet_config['spreadsheet_id'],
                        sheet_config['tab_name'],
                        links_to_add,
                        sheet_config.get('link_col', 'B'),
                        sheet_config.get('status_col', 'C'),
                        status="Chưa xử lý"
                    )
                    
                    if success:
                        for i, link in enumerate(links_to_add):
                            existing_links.append(link.split('?')[0].strip())
                            if link not in scrapes_needed:
                                scrapes_needed[link] = []
                            scrapes_needed[link].append({
                                'sheet_config': sheet_config,
                                'row_index': row_indices[i]
                            })
                        add_sync_log(f"Tài khoản {profile_name}: Đã thêm {added_count} video mới vào Sheet {sheet_config.get('tab_name')}.")
                
            except Exception as e:
                add_sync_log(f"Lỗi khi ghi Sheet {sheet_config.get('tab_name')} tài khoản {profile_name}: {str(e)}")
                
        # Kích hoạt quá trình cào dữ liệu: Từng link một, chỉ cào 1 lần và cập nhật vào TẤT CẢ các sheet liên quan
        for link, targets in scrapes_needed.items():
            try:
                from main import trigger_scrape_multiple_targets
                trigger_scrape_multiple_targets(link, targets, profile_name)
            except Exception as e:
                print(f"⚠️ Không thể kích hoạt cào tự động cho {link}: {e}")
    finally:
        lock.release()

def sync_all_accounts_job():
    """Hàm chạy ngầm đồng bộ tất cả cấu hình"""
    if sync_status.get("is_running"): 
        return
    
    sync_status["is_running"] = True
    
    try:
        configs = load_sync_configs()
        active_configs = [c for c in configs if c.get('active')]
        
        if not active_configs:
            return

        # Nhóm cấu hình theo tài khoản
        grouped_configs = {}
        for cfg in active_configs:
            profile_input = cfg.get("profile_name")
            if not profile_input: continue
            
            safe_profile_name = "".join(c for c in profile_input if c.isalnum() or c in ('-', '_', '@'))
            target_url = profile_input
            if "tiktok.com" in profile_input:
                parts = profile_input.split('@')
                if len(parts) > 1:
                    username = parts[1].split('?')[0].split('/')[0]
                    safe_profile_name = f"@{username}"
                    target_url = f"https://www.tiktok.com/@{username}"
                    
            if safe_profile_name not in grouped_configs:
                grouped_configs[safe_profile_name] = {
                    "target_url": target_url,
                    "configs": []
                }
            grouped_configs[safe_profile_name]["configs"].append(cfg)

        add_sync_log(f"Bắt đầu chu kỳ đồng bộ cho {len(grouped_configs)} kênh TikTok...")
        
        for profile_name, group_data in grouped_configs.items():
            # BỎ QUA nếu tài khoản này đang được người dùng thao tác đăng nhập trên Web UI
            if profile_name in active_logins:
                add_sync_log(f"Kênh {profile_name} đang bận cấu hình, bỏ qua chu kỳ này.")
                continue
                
            try:
                process_account_sync_multiple(profile_name, group_data["configs"], group_data["target_url"])
            except Exception as e:
                add_sync_log(f"Lỗi hệ thống khi đồng bộ {profile_name}: {str(e)}")
                
        sync_status["last_run"] = datetime.now().isoformat()
        add_sync_log("Hoàn tất chu kỳ đồng bộ.")
    except Exception as exc:
        add_sync_log(f"Lỗi nghiêm trọng trong chu kỳ đồng bộ: {str(exc)}")
    finally:
        sync_status["is_running"] = False

# Scheduler
def background_scheduler():
    import time
    while True:
        try:
            if load_sync_configs(): # Chỉ chạy nếu có cấu hình
                sync_all_accounts_job()
        except Exception as e:
            add_sync_log(f"Lỗi scheduler: {e}")
            
        time.sleep(120) # Ngủ 2 phút

# Bắt đầu thread
scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
scheduler_thread.start()
