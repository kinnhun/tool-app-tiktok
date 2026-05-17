import os
import json
import asyncio
import threading
from datetime import datetime
from scraper.sheet_manager import append_link, get_client
from playwright.async_api import async_playwright

SYNC_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'sync_configs.json')
SESSION_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)))

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

async def extract_favorites(session_dir):
    """Mở browser ẩn để lấy video trong tab Yêu thích."""
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
                'headless': True,
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
            
            # TỐI ƯU HÓA: Chặn tải hình ảnh, video, nhạc, font để siêu tiết kiệm RAM và Bandwidth
            async def intercept_route(route):
                if route.request.resource_type in ["image", "media", "font"]:
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", intercept_route)
            
            # Tới trang profile cá nhân (chỉ chờ DOM load xong, không chờ load toàn bộ trang)
            await page.goto("https://www.tiktok.com/profile", timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2) # Giảm thời gian chờ vì không tải media nên trang load cực nhanh
            
            # Click tab Đã Lưu / Yêu thích (Favorites)
            try:
                # Dùng CSS selector mạnh mẽ hơn: tìm thẻ có chứa biểu tượng bookmark/Yêu thích
                # Thường TikTok web dùng data-e2e="favorites-tab"
                await page.click("[data-e2e='favorites-tab']", timeout=5000)
            except:
                try:
                    await page.click("text=Yêu thích", timeout=3000)
                except:
                    try:
                        await page.click("text=Favorites", timeout=3000)
                    except:
                        add_sync_log(f"Không tìm thấy tab Yêu thích. Đang thử đọc URL...")
            
            await asyncio.sleep(2)
            
            # Lấy các thẻ a chứa link video
            elements = await page.query_selector_all('a[href*="/video/"]')
            for el in elements:
                href = await el.get_attribute('href')
                if href and '/video/' in href:
                    # Ensure absolute url
                    if not href.startswith('http'):
                        href = 'https://www.tiktok.com' + href
                    links.append(href.split('?')[0]) # Lấy link chuẩn
            
            await context.close()
    except Exception as e:
        add_sync_log(f"Lỗi khi trích xuất tài khoản {os.path.basename(session_dir)}: {str(e)}")
    
    # Loại bỏ link trùng, giữ thứ tự
    unique_links = []
    for l in links:
        if l not in unique_links:
            unique_links.append(l)
    return unique_links[:10] # Chỉ lấy 10 video gần nhất để xử lý nhanh

def process_account_sync(config):
    """Xử lý đồng bộ 1 tài khoản."""
    profile_name = config.get("profile_name")
    sheet_config_id = config.get("sheet_config_id")
    
    if not profile_name or not sheet_config_id:
        return
        
    session_dir = os.path.join(SESSION_BASE_DIR, f"tiktok_session_{profile_name}")
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
            
    # Get config details
    from main import get_config
    sheet_config = get_config(sheet_config_id)
    if not sheet_config:
        add_sync_log(f"Không tìm thấy cấu hình Sheet cho tài khoản {profile_name}")
        return
        
    add_sync_log(f"Đang kiểm tra Favorites của tài khoản {profile_name}...")
    
    # Chạy async lấy link
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        recent_links = loop.run_until_complete(extract_favorites(session_dir))
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

    # Đọc link hiện có từ Sheet để chống trùng
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
        added_count = 0
        for link in reversed(new_links_to_push): # Thêm từ cũ đến mới
            if link not in existing_links:
                # Append to sheet
                success, msg = append_link(
                    sheet_config['spreadsheet_id'],
                    sheet_config['tab_name'],
                    link,
                    sheet_config.get('link_col', 'B'),
                    sheet_config.get('status_col', 'C'),
                    status="Chưa xử lý"
                )
                if success:
                    added_count += 1
                    existing_links.append(link) # Cập nhật danh sách local
                    
                    # TỰ ĐỘNG KÍCH HOẠT CÀO DỮ LIỆU NGAY LẬP TỨC
                    try:
                        from main import trigger_scrape_directly
                        # Gọi hàm cào trong một thread riêng để không làm chậm quá trình đồng bộ
                        threading.Thread(target=trigger_scrape_directly, args=(
                            sheet_config['spreadsheet_id'],
                            sheet_config['tab_name'],
                            len(all_values) + added_count, # Row index mới
                            link,
                            sheet_config, # Cấu hình sheet
                            profile_name # Tên nick để lấy session
                        )).start()
                    except Exception as e:
                        print(f"⚠️ Không thể kích hoạt cào tự động: {e}")
                    
        add_sync_log(f"Tài khoản {profile_name}: Đã thêm {added_count} video mới vào Sheet.")
        
    except Exception as e:
        add_sync_log(f"Lỗi khi ghi Sheet tài khoản {profile_name}: {str(e)}")

def sync_all_accounts_job():
    """Hàm chạy ngầm đồng bộ tất cả cấu hình"""
    if sync_status["is_running"]: return
    
    sync_status["is_running"] = True
    configs = load_sync_configs()
    active_configs = [c for c in configs if c.get('active')]
    
    if not active_configs:
        sync_status["is_running"] = False
        return

    add_sync_log(f"Bắt đầu chu kỳ đồng bộ {len(active_configs)} tài khoản...")
    
    for cfg in active_configs:
        profile_name = cfg.get("profile_name")
        
        # BỎ QUA nếu tài khoản này đang được người dùng thao tác đăng nhập trên Web UI
        if profile_name in active_logins:
            add_sync_log(f"Tài khoản {profile_name} đang được đăng nhập, bỏ qua chu kỳ này.")
            continue
            
        try:
            process_account_sync(cfg)
        except Exception as e:
            add_sync_log(f"Lỗi hệ thống khi đồng bộ {profile_name}: {str(e)}")
            
    sync_status["last_run"] = datetime.now().isoformat()
    sync_status["is_running"] = False
    add_sync_log("Hoàn tất chu kỳ đồng bộ.")
    
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
