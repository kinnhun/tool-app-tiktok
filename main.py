"""
TikTok Shop Price Scraper - Main Flask Server
Đọc link TikTok từ Google Sheet → Lấy giá sản phẩm TikTok Shop → Ghi lại vào Google Sheet
"""

import os
import sys
import json
import asyncio
import threading
import re

# Ép buộc Playwright luôn luôn sử dụng thư mục AppData/Local làm gốc chứa Chromium (Tương thích hoàn hảo với PyInstaller)
if getattr(sys, 'frozen', False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")

from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import subprocess

# Force utf-8 encoding for stdout/stderr to avoid crash on windows with emojis
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def install_playwright():
    """Tự động cài đặt Playwright Chromium nếu chưa có bằng cách tải trực tiếp từ CDN nếu gọi lệnh thất bại."""
    try:
        print("🔍 Đang kiểm tra môi trường Playwright...")
        
        # Tính toán đường dẫn đích của Chromium
        local_app_data = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if not local_app_data:
            local_app_data = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
        
        chromium_dir = os.path.join(local_app_data, "chromium-1148")
        chrome_exe = os.path.join(chromium_dir, "chrome-win", "chrome.exe")
        
        if os.path.exists(chrome_exe):
            print("✅ Playwright Chromium đã tồn tại và sẵn sàng.")
            return

        print("⏳ Không tìm thấy Chromium. Đang thử cài đặt tự động bằng Playwright CLI...")
        # Thử cài bằng CLI trước
        try:
            if getattr(sys, 'frozen', False):
                from playwright._impl.__main__ import main as pw_main
                original_argv = sys.argv.copy()
                sys.argv = ['playwright', 'install', 'chromium']
                try:
                    pw_main()
                except SystemExit:
                    pass
                finally:
                    sys.argv = original_argv
            else:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except Exception as cli_err:
            print(f"⚠️ Cài đặt qua Playwright CLI lỗi: {cli_err}")
            
        # Kiểm tra lại xem CLI tải thành công chưa
        if os.path.exists(chrome_exe):
            print("✅ Playwright Chromium đã được cài đặt thành công qua CLI.")
            return

        # Nếu CLI thất bại (thường do VPS chặn node.exe trong temp hoặc lỗi mạng), tải trực tiếp bằng Python!
        print("⚠️ Cài đặt qua CLI thất bại (thường do VPS chặn chạy file exe từ Temp). Bắt đầu tải Chromium trực tiếp bằng Python...")
        
        # URL tải Chromium 1148 cho Win64
        url = "https://playwright.azureedge.net/builds/chromium/1148/chromium-win64.zip"
        zip_path = os.path.join(local_app_data, "chromium-win64.zip")
        
        os.makedirs(local_app_data, exist_ok=True)
        
        import urllib.request
        import zipfile
        
        print(f"📥 Đang tải Chromium từ {url}...")
        # Thực hiện tải file với User-Agent để tránh bị chặn
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            # Tải file về
            data = response.read()
            out_file.write(data)
            
        print("📦 Đang giải nén Chromium...")
        # Giải nén trực tiếp vào thư mục chromium-1148
        os.makedirs(chromium_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(chromium_dir)
            
        # Tạo các file marker để Playwright xác nhận cài đặt thành công
        with open(os.path.join(chromium_dir, "INSTALLATION_COMPLETE"), "w") as f:
            f.write("")
        with open(os.path.join(chromium_dir, "DEPENDENCIES_VALIDATED"), "w") as f:
            f.write("")
            
        # Dọn dẹp file zip sau khi tải xong
        try:
            os.remove(zip_path)
        except:
            pass
            
        if os.path.exists(chrome_exe):
            print("✅ Đã tải và cài đặt thành công Chromium thủ công bằng Python!")
        else:
            print("❌ Lỗi: Giải nén thành công nhưng không tìm thấy file chrome.exe!")
            
    except Exception as e:
        print(f"⚠️ Cài đặt Playwright thất bại: {e}")

# Chạy cài đặt khi khởi động
install_playwright()

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

from scraper.sheet_manager import (
    check_connection, get_tab_data, read_tiktok_links, get_sheet_stats,
    update_row, set_row_status, extract_spreadsheet_id, validate_sheet_url,
    get_service_account_email, load_configs, add_config, update_config,
    delete_config, get_config, append_link
)
from scraper.tiktok_scraper import scrape_tiktok_product, validate_tiktok_url

app = Flask(__name__, static_folder=get_resource_path('static'))
CORS(app)

# Import the favorites syncer to start the background scheduler
import scraper.favorites_syncer as favorites_syncer

# Global state for tracking processing jobs
processing_jobs = {}
tiktok_app_process = None

def cleanup_old_jobs():
    """Xóa bớt dữ liệu lịch sử trong RAM để tránh tốn bộ nhớ."""
    global processing_jobs
    if len(processing_jobs) > 50: # Chỉ giữ lại 50 job gần nhất
        sorted_keys = sorted(processing_jobs.keys(), key=lambda k: processing_jobs[k].get('start_time', ''), reverse=True)
        keys_to_remove = sorted_keys[50:]
        for k in keys_to_remove:
            processing_jobs.pop(k, None)
        print(f"🧹 Đã dọn dẹp {len(keys_to_remove)} jobs cũ trong RAM.")

def start_periodic_cleanup():
    """Chạy dọn dẹp định kỳ mỗi 30 phút."""
    def run_cleanup():
        import time
        while True:
            time.sleep(1800) # 30 phút
            cleanup_old_jobs()
    
    cleanup_thread = threading.Thread(target=run_cleanup, daemon=True)
    cleanup_thread.start()

start_periodic_cleanup()


# ─── Static file serving ───────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(app.static_folder, 'css'), filename)


@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(app.static_folder, 'js'), filename)


# ─── API: Service Account Info ─────────────────────────────────────

@app.route('/api/service-email', methods=['GET'])
def api_service_email():
    email = get_service_account_email()
    return jsonify({
        'success': email is not None,
        'email': email,
        'message': 'Chưa cấu hình service account.' if not email else ''
    })


@app.route('/api/update-credentials', methods=['POST'])
def api_update_credentials():
    """Update service account credentials."""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'message': 'Không có dữ liệu.'})
        
        # Simple validation: check for required keys
        required_keys = ['type', 'project_id', 'private_key', 'client_email']
        for key in required_keys:
            if key not in data:
                return jsonify({'success': False, 'message': f'Thiếu trường bắt buộc: {key}'})
        
        from scraper.sheet_manager import CREDENTIALS_PATH
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
        
        # Save to file
        with open(CREDENTIALS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        return jsonify({'success': True, 'message': 'Cập nhật tài khoản thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/get-credentials', methods=['GET'])
def api_get_credentials():
    """Get the current service account credentials."""
    try:
        from scraper.sheet_manager import CREDENTIALS_PATH
        if not os.path.exists(CREDENTIALS_PATH):
            return jsonify({'success': False, 'message': 'Chưa cấu hình tài khoản.'})
            
        with open(CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, 'credentials': data})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


# ─── API: Google Sheet Connection ──────────────────────────────────

@app.route('/api/check-connection', methods=['POST'])
def api_check_connection():
    data = request.json
    url = data.get('url', '')
    result = check_connection(url)
    return jsonify(result)


@app.route('/api/tab-data', methods=['POST'])
def api_tab_data():
    data = request.json
    spreadsheet_id = data.get('spreadsheet_id', '')
    tab_name = data.get('tab_name', '')
    result = get_tab_data(spreadsheet_id, tab_name)
    return jsonify(result)


@app.route('/api/sheet-stats', methods=['POST'])
def api_sheet_stats():
    data = request.json
    spreadsheet_id = data.get('spreadsheet_id', '')
    tab_name = data.get('tab_name', '')
    status_col = data.get('status_col', 'C')
    result = get_sheet_stats(spreadsheet_id, tab_name, status_col)
    return jsonify(result)


# ─── API: Configuration Management ────────────────────────────────

@app.route('/api/configs', methods=['GET'])
def api_list_configs():
    configs = load_configs()
    return jsonify({'success': True, 'configurations': configs})


@app.route('/api/configs', methods=['POST'])
def api_add_config():
    data = request.json
    config = add_config(data)
    return jsonify({'success': True, 'config': config})


@app.route('/api/configs/<config_id>', methods=['PUT'])
def api_update_config(config_id):
    data = request.json
    config = update_config(config_id, data)
    if config:
        return jsonify({'success': True, 'config': config})
    return jsonify({'success': False, 'message': 'Không tìm thấy cấu hình.'}), 404


@app.route('/api/configs/<config_id>', methods=['DELETE'])
def api_delete_config(config_id):
    delete_config(config_id)
    return jsonify({'success': True, 'message': 'Đã xóa cấu hình.'})


@app.route('/api/configs/<config_id>', methods=['GET'])
def api_get_config(config_id):
    config = get_config(config_id)
    if config:
        return jsonify({'success': True, 'config': config})
    return jsonify({'success': False, 'message': 'Không tìm thấy cấu hình.'}), 404


@app.route('/api/quick-add', methods=['POST'])
def api_quick_add():
    """Quickly append a link to a Google Sheet."""
    data = request.json
    config_id = data.get('config_id')
    url = data.get('url', '').strip()
    
    if not config_id:
        return jsonify({'success': False, 'message': 'Vui lòng chọn cấu hình Sheet.'})
    
    if not url:
        return jsonify({'success': False, 'message': 'Vui lòng nhập link TikTok.'})
    
    # Validate TikTok URL
    valid, msg = validate_tiktok_url(url)
    if not valid:
        return jsonify({'success': False, 'message': msg})
    
    config = get_config(config_id)
    if not config:
        return jsonify({'success': False, 'message': 'Không tìm thấy cấu hình.'})
    
    try:
        success, message = append_link(
            config.get('spreadsheet_id'),
            config.get('tab_name'),
            url,
            config.get('link_col', 'B'),
            config.get('status_col', 'C')
        )
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})


@app.route('/api/quick-add-scrape', methods=['POST'])
def api_quick_add_scrape():
    """Quickly append a link AND scrape it immediately."""
    data = request.json
    config_id = data.get('config_id')
    url = data.get('url', '').strip()
    
    if not config_id:
        return jsonify({'success': False, 'message': 'Vui lòng chọn cấu hình Sheet.'})
    
    if not url:
        return jsonify({'success': False, 'message': 'Vui lòng nhập link TikTok.'})
    
    # Validate TikTok URL
    valid, msg = validate_tiktok_url(url)
    if not valid:
        return jsonify({'success': False, 'message': msg})
    
    config = get_config(config_id)
    if not config:
        return jsonify({'success': False, 'message': 'Không tìm thấy cấu hình.'})
    
    try:
        # 1. Append link with status "Đang xử lý"
        success, message = append_link(
            config.get('spreadsheet_id'),
            config.get('tab_name'),
            url,
            config.get('link_col', 'B'),
            config.get('status_col', 'C'),
            status="Đang xử lý"
        )
        
        if not success:
            return jsonify({'success': False, 'message': f'Lỗi thêm link: {message}'})

        # 2. Get the row index (find the link we just added to be safe)
        from scraper.sheet_manager import get_client
        client = get_client()
        spreadsheet = client.open_by_key(config.get('spreadsheet_id'))
        worksheet = spreadsheet.worksheet(config.get('tab_name'))
        
        # Optimization: Just get the last row index
        all_values = worksheet.get_all_values()
        new_row_idx = len(all_values)
        
        # 3. Scrape
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(scrape_tiktok_product(url))
        except Exception as e:
            result = {
                'status': 'Lỗi cần chạy lại',
                'note': f'Lỗi: {str(e)[:100]}',
            }
        finally:
            loop.close()

        # 4. Update the row
        column_mapping = {
            'status_col': config.get('status_col', 'C'),
            'product_name_col': config.get('product_name_col', 'D'),
            'current_price_col': config.get('current_price_col', 'E'),
            'original_price_col': config.get('original_price_col', 'F'),
            'sale_price_col': config.get('sale_price_col', 'G'),
            'product_link_col': config.get('product_link_col', 'H'),
            'shop_name_col': config.get('shop_name_col', 'I'),
            'updated_at_col': config.get('updated_at_col', 'J'),
            'note_col': config.get('note_col', 'K'),
        }
        
        update_row(config.get('spreadsheet_id'), config.get('tab_name'), new_row_idx, result, column_mapping)
        
        msg = f'Đã thêm và lấy xong: {result.get("product_name", "Sản phẩm")[:40]}'
        if result.get('current_price'):
            msg += f' - {result.get("current_price")}'
            
        return jsonify({
            'success': True, 
            'message': msg,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'})


_direct_scrape_lock = threading.Lock()
_scrape_rate_limiter = threading.Semaphore(1)  # Chỉ cho 1 luồng cào cùng lúc
_last_scrape_time = 0  # Thời điểm cào gần nhất
_MIN_SCRAPE_INTERVAL = 2.0  # Tối thiểu 2 giây giữa 2 lần cào (= tối đa ~43,200 video/ngày)

def _rate_limited_scrape(url, session_dir, loop):
    """Cào 1 link với rate limiting để tránh bị chặn IP."""
    import time
    global _last_scrape_time
    
    with _scrape_rate_limiter:
        elapsed = time.time() - _last_scrape_time
        if elapsed < _MIN_SCRAPE_INTERVAL:
            time.sleep(_MIN_SCRAPE_INTERVAL - elapsed)
        
        from scraper.tiktok_scraper import scrape_tiktok_product
        result = loop.run_until_complete(scrape_tiktok_product(url, custom_session_dir=session_dir))
        _last_scrape_time = time.time()
        return result

def trigger_scrape_directly(spreadsheet_id, tab_name, row_index, url, matching_cfg=None, profile_name=None):
    """Xử lý cào dữ liệu cho 1 link ngay lập tức."""
    import threading
    import asyncio
    import os
    
    # Xác định folder session
    session_dir = None
    if profile_name:
        session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
    
    # Nếu không có cấu hình, tìm cấu hình khớp
    if not matching_cfg:
        configs = load_configs()
        for cfg in configs:
            if cfg.get('spreadsheet_id') == spreadsheet_id and cfg.get('tab_name') == tab_name:
                matching_cfg = cfg
                break
        
        if not matching_cfg:
            for cfg in configs:
                if cfg.get('spreadsheet_id') == spreadsheet_id:
                    matching_cfg = cfg
                    break
                    
    # Cấu hình mặc định nếu vẫn không tìm thấy
    final_cfg = matching_cfg or {
        'status_col': 'C',
        'product_name_col': 'D',
        'current_price_col': 'E',
        'original_price_col': 'F',
        'sale_price_col': 'G',
        'product_link_col': 'H',
        'shop_name_col': 'I',
        'updated_at_col': 'J',
        'note_col': 'K'
    }

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from scraper.sheet_manager import update_row
            result = _rate_limited_scrape(url, session_dir, loop)
            
            column_mapping = {
                'status_col': final_cfg.get('status_col', 'C'),
                'product_name_col': final_cfg.get('product_name_col', 'D'),
                'current_price_col': final_cfg.get('current_price_col', 'E'),
                'original_price_col': final_cfg.get('original_price_col', 'F'),
                'sale_price_col': final_cfg.get('sale_price_col', 'G'),
                'product_link_col': final_cfg.get('product_link_col', 'H'),
                'shop_name_col': final_cfg.get('shop_name_col', 'I'),
                'updated_at_col': final_cfg.get('updated_at_col', 'J'),
                'note_col': final_cfg.get('note_col', 'K'),
            }
            
            update_row(spreadsheet_id, tab_name, row_index, result, column_mapping)
        except Exception as e:
            print(f"Direct scrape error: {e}")
        finally:
            loop.close()

    threading.Thread(target=_run).start()

def trigger_scrape_multiple_targets(url, targets, profile_name=None):
    """Xử lý cào dữ liệu cho 1 link và cập nhật vào nhiều Sheet/Dòng cùng lúc."""
    import threading
    import asyncio
    import os
    
    # Xác định folder session
    session_dir = None
    if profile_name:
        session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
    
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from scraper.sheet_manager import update_row
            
            # Cào dữ liệu CHỈ 1 LẦN cho mỗi link (có rate limiting)
            result = _rate_limited_scrape(url, session_dir, loop)
            
            # Cập nhật kết quả lên TẤT CẢ các sheet yêu cầu
            for target in targets:
                sheet_config = target.get('sheet_config', {})
                spreadsheet_id = sheet_config.get('spreadsheet_id')
                tab_name = sheet_config.get('tab_name')
                row_index = target.get('row_index')
                
                if not spreadsheet_id or not tab_name or not row_index:
                    continue
                    
                column_mapping = {
                    'status_col': sheet_config.get('status_col', 'C'),
                    'product_name_col': sheet_config.get('product_name_col', 'D'),
                    'current_price_col': sheet_config.get('current_price_col', 'E'),
                    'original_price_col': sheet_config.get('original_price_col', 'F'),
                    'sale_price_col': sheet_config.get('sale_price_col', 'G'),
                    'product_link_col': sheet_config.get('product_link_col', 'H'),
                    'shop_name_col': sheet_config.get('shop_name_col', 'I'),
                    'updated_at_col': sheet_config.get('updated_at_col', 'J'),
                    'note_col': sheet_config.get('note_col', 'K'),
                }
                
                try:
                    update_row(spreadsheet_id, tab_name, row_index, result, column_mapping)
                except Exception as sheet_e:
                    print(f"Error updating sheet {tab_name}: {sheet_e}")
                    
        except Exception as e:
            print(f"Direct multi-scrape error: {e}")
        finally:
            loop.close()

    threading.Thread(target=_run).start()

@app.route('/api/webhook/process-row', methods=['POST'])
def api_webhook_process_row():
    """Webhook for Google Apps Script to trigger immediate scraping of a single row."""
    data = request.json
    spreadsheet_id = data.get('spreadsheet_id')
    tab_name = data.get('tab_name')
    row_index = data.get('row_index')
    url = data.get('url', '').strip()
    
    if not all([spreadsheet_id, tab_name, row_index, url]):
        return jsonify({'success': False, 'message': 'Thiếu thông tin.'}), 400
        
    trigger_scrape_directly(spreadsheet_id, tab_name, row_index, url)
    return jsonify({'success': True, 'message': 'Đã tiếp nhận yêu cầu xử lý.'})


@app.route('/api/open-tiktok-app', methods=['POST'])
def api_open_tiktok_app():
    """Launch TikTok in a standalone mobile-sized window (App Mode) optimized."""
    import subprocess
    import platform
    import os
    
    global tiktok_app_process

    # Check if process is already running
    if tiktok_app_process and tiktok_app_process.poll() is None:
        return jsonify({'success': True, 'message': 'TikTok App đang chạy.'})

    data = request.json or {}
    # Use the provided URL or default to m.tiktok.com
    url = data.get('url', "https://m.tiktok.com/")
    
    system = platform.system()
    if system != "Windows":
        import webbrowser
        webbrowser.open(url)
        return jsonify({'success': True, 'message': 'Đã mở TikTok.'})

    # Find Chrome, Edge or Playwright Chromium
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    
    executable = None
    for path in chrome_paths:
        if os.path.exists(path):
            executable = path
            break
    
    if not executable and os.path.exists(edge_path):
        executable = edge_path
        
    # Fallback to Playwright's Chromium if system browsers not found
    if not executable:
        try:
            import playwright
            # Use a clever way to find where playwright installed chromium
            # Usually in %LOCALAPPDATA%\ms-playwright\
            base_dir = os.path.expanduser(r"~\AppData\Local\ms-playwright")
            if os.path.exists(base_dir):
                for folder in os.listdir(base_dir):
                    if folder.startswith("chromium-"):
                        p = os.path.join(base_dir, folder, "chrome-win", "chrome.exe")
                        if os.path.exists(p):
                            executable = p
                            break
        except:
            pass

    if not executable:
        import webbrowser
        webbrowser.open(url)
        return jsonify({'success': True, 'message': 'Đã mở TikTok bằng trình duyệt mặc định.'})

    # Optimization flags:
    # --disable-extensions: avoid proxy/adblocker conflicts
    # --no-first-run: faster launch
    # --window-size: mobile dimensions
    view_session_dir = os.path.join(os.getcwd(), "tiktok_view_session")
    os.makedirs(view_session_dir, exist_ok=True)

    cmd = [
        executable, 
        f"--app={url}", 
        "--window-size=380,820",
        "--remote-debugging-port=9222",
        "--user-data-dir=" + view_session_dir,
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check"
    ]

    try:
        # Use shell=False for security, and don't wait for process
        tiktok_app_process = subprocess.Popen(cmd, shell=False)
        return jsonify({'success': True, 'message': 'Đã khởi chạy TikTok App Mode (Tối ưu).'})
    except Exception as e:
        # Last resort fallback
        import webbrowser
        webbrowser.open(url)
        return jsonify({'success': True, 'message': f'Đã mở bằng trình duyệt mặc định (Lỗi App Mode: {str(e)})'})


@app.route('/api/tiktok-app/save-screenshot', methods=['POST'])
def api_save_screenshot_to_drive():
    """Upload screenshot to Drive and save link to Sheet."""
    try:
        data = request.json
        image_b64 = data.get('image')
        drive_folder_url = data.get('drive_folder_url')
        apps_script_url = data.get('apps_script_url')
        spreadsheet_id = data.get('spreadsheet_id')
        tab_name = data.get('tab_name')
        video_url = data.get('video_url', 'TikTok Video')
        product_name = data.get('product_name', '')
        price = data.get('price', '')
        shop_name = data.get('shop_name', '')
        
        if not image_b64:
            return jsonify({'success': False, 'message': 'Không có dữ liệu ảnh.'})
            
        import base64
        image_bytes = base64.b64decode(image_b64)
        
        # Helper to extract TikTok Video/Photo ID
        def extract_tiktok_id(url):
            if not url or not isinstance(url, str): return None
            # Standard video: /video/(\d+)
            # Photo: /photo/(\d+)
            # Short link: /t/(\w+) or vm.tiktok.com/... (these need resolution, but we do our best)
            match = re.search(r'/(?:video|photo)/(\d+)', url)
            if match: return match.group(1)
            return None

        target_id = extract_tiktok_id(video_url)
        
        # 1. Connect to Sheet first to find the row and STT for naming
        existing_row_index = -1
        stt = "New"
        headers = []
        all_values = []
        worksheet = None
        
        if spreadsheet_id and tab_name:
            try:
                from scraper.sheet_manager import get_client
                client = get_client()
                spreadsheet = client.open_by_key(spreadsheet_id)
                worksheet = spreadsheet.worksheet(tab_name)
                all_values = worksheet.get_all_values()
                
                if all_values:
                    headers = all_values[0]
                    # Find link column
                    link_col_idx = 1 # Default to B
                    for r_idx in range(min(5, len(all_values))):
                        for c_idx, val in enumerate(all_values[r_idx]):
                            if "tiktok.com" in val.lower():
                                link_col_idx = c_idx
                                break
                    
                    clean_target_url = video_url.split('?')[0].strip()
                    for i, row in enumerate(all_values):
                        if len(row) > link_col_idx:
                            row_url = row[link_col_idx].strip()
                            if not row_url: continue
                            if (clean_target_url != "" and clean_target_url == row_url.split('?')[0].strip()) or \
                               (target_id and extract_tiktok_id(row_url) == target_id):
                                existing_row_index = i + 1
                                stt = row[0] if len(row) > 0 else str(i)
                                break
            except Exception as e:
                print(f"Warning: Could not connect to sheet before upload: {e}")

        # 2. Generate Filename based on Convention
        import re as re_mod
        safe_name = re_mod.sub(r'[^\w\s-]', '', product_name).strip()[:30] if product_name else "Screenshot"
        timestamp = datetime.now().strftime('%H%M%S')
        filename = f"[{stt}] {safe_name} ({timestamp}).jpg"
        
        # 3. Upload to Drive
        from scraper.sheet_manager import upload_to_drive
        drive_link = upload_to_drive(image_bytes, filename, drive_folder_url, apps_script_url)
        
        # 4. Save/Update Sheet
        if worksheet:
            try:
                image_formula = f'=IMAGE("{drive_link}")'
                
                if existing_row_index > 0:
                    current_row_data = all_values[existing_row_index - 1]
                    target_col = max(len(headers), len(current_row_data)) + 1
                    
                    # Update: Filename | Drive Link | Image
                    worksheet.update_cell(existing_row_index, target_col, filename)
                    worksheet.update_cell(existing_row_index, target_col + 1, drive_link)
                    worksheet.update_cell(existing_row_index, target_col + 2, image_formula)
                    
                    return jsonify({
                        'success': True, 
                        'message': f'Đã lưu ảnh "{filename}" vào hàng {existing_row_index}!',
                        'drive_link': drive_link
                    })
                else:
                    # Append new row matching the sheet structure
                    new_row = [""] * len(headers)
                    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
                    
                    if 'STT' in headers: new_row[headers.index('STT')] = len(all_values)
                    if 'Link' in headers: new_row[headers.index('Link')] = video_url
                    elif 'Link TikTok' in headers: new_row[headers.index('Link TikTok')] = video_url
                    
                    if 'Tên SP' in headers: new_row[headers.index('Tên SP')] = product_name
                    elif 'Tên sản phẩm' in headers: new_row[headers.index('Tên sản phẩm')] = product_name
                    
                    if 'Giá' in headers: new_row[headers.index('Giá')] = price
                    if 'Shop' in headers: new_row[headers.index('Shop')] = shop_name
                    if 'Cập nhật' in headers: new_row[headers.index('Cập nhật')] = now_str
                    
                    # Add Filename, Link, Formula
                    new_row.extend([filename, drive_link, image_formula])
                    
                    worksheet.append_row(new_row, value_input_option='USER_ENTERED')
                    return jsonify({'success': True, 'message': f'Đã tạo hàng mới với ảnh "{filename}"!', 'drive_link': drive_link})
                    
            except Exception as e:
                return jsonify({
                    'success': True, 
                    'message': f'Ảnh đã lưu Drive là "{filename}", nhưng lỗi ghi Sheet: {str(e)}',
                    'drive_link': drive_link
                })
            
        return jsonify({
            'success': True, 
            'message': f'Đã tải ảnh "{filename}" lên Google Drive!',
            'drive_link': drive_link
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi lưu ảnh: {str(e)}'})

@app.route('/api/tiktok-app/action', methods=['POST'])
def api_tiktok_app_action():
    """Perform action on the running TikTok App window (screenshot, get info)."""
    action = request.json.get('action')
    
    if not action:
        return jsonify({'success': False, 'message': 'Thiếu hành động.'})

    try:
        from playwright.async_api import async_playwright
        
        async def run_action():
            async with async_playwright() as p:
                try:
                    # Connect to existing browser
                    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    context = browser.contexts[0]
                    
                    # Retry loop to find the page (it might take a moment for CDP to register it)
                    page = None
                    max_retries = 5
                    
                    # FOOLPROOF Page Selection
                    page = None
                    max_retries = 5
                    
                    for attempt in range(max_retries):
                        all_pages = []
                        for ctx in browser.contexts:
                            all_pages.extend(ctx.pages)
                        
                        # Pass 1: Find page with an ACTUAL video element that is visible
                        for pg in all_pages:
                            try:
                                url = pg.url.lower()
                                if "localhost" in url or "127.0.0.1" in url or "launcher" in url:
                                    continue
                                    
                                has_video = await pg.evaluate("""() => {
                                    const v = document.querySelector('video');
                                    return v && v.offsetWidth > 100 && v.offsetHeight > 100;
                                }""")
                                if has_video:
                                    page = pg
                                    break
                            except:
                                continue
                        if page: break
                        
                        # Pass 2: Find page with tiktok.com in URL
                        for pg in all_pages:
                            url = pg.url.lower()
                            if "tiktok.com" in url:
                                page = pg
                                break
                        if page: break
                        
                        # Wait and retry
                        await asyncio.sleep(0.8)
                    
                    if not page:
                        return jsonify({
                            'success': False, 
                            'message': f'Không tìm thấy trang TikTok. Đang thấy: {[p.url for p in all_pages]}'
                        })

                    # Ensure the page is focused and has a valid size
                    try:
                        await page.set_viewport_size({"width": 380, "height": 820})
                        await page.bring_to_front()
                        await asyncio.sleep(0.2) 
                    except:
                        pass

                    if action == 'screenshot':
                        import base64
                        
                        # Capture full viewport
                        screenshot_bytes = await page.screenshot(type='jpeg', quality=100)
                        encoded = base64.b64encode(screenshot_bytes).decode('utf-8')
                        return {'success': True, 'image': encoded}
                    
                    elif action == 'get_data':
                        url = page.url
                        title = await page.title()
                        
                        # Try to find product link
                        product_link = ''
                        links = await page.query_selector_all('a')
                        for link in links:
                            href = await link.get_attribute('href')
                            if href and ('pdp' in href or 'product' in href or 'shop.tiktok' in href):
                                if not href.startswith('http'):
                                    href = 'https://www.tiktok.com' + href
                                product_link = href
                                break
                        
                        return {
                            'success': True, 
                            'video_url': url, 
                            'title': title,
                            'product_link': product_link
                        }
                    
                    return {'success': False, 'message': 'Hành động không hợp lệ.'}
                except Exception as e:
                    return {'success': False, 'message': f'Không thể kết nối tới TikTok App: {str(e)}'}
                finally:
                    # Don't close the browser, just the CDP connection
                    pass

        result = asyncio.run(run_action())
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'})


# ─── API: TikTok Scraping ─────────────────────────────────────────

@app.route('/api/test-scrape', methods=['POST'])
def api_test_scrape():
    """Test scraping a single TikTok URL."""
    data = request.json
    url = data.get('url', '')
    
    valid, msg = validate_tiktok_url(url)
    if not valid:
        return jsonify({'success': False, 'message': msg})
    
    try:
        # Tự động lấy profile_name đầu tiên trong cấu hình để tận dụng Cookie đã đăng nhập
        # Điều này giúp Test tránh bị CAPTCHA
        session_dir = None
        try:
            from scraper.favorites_syncer import load_sync_configs
            sync_configs = load_sync_configs()
            if sync_configs and len(sync_configs) > 0:
                profile_name = sync_configs[0].get('profile_name')
                if profile_name:
                    import os
                    session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
        except Exception:
            pass
            
        result = asyncio.run(scrape_tiktok_product(url, custom_session_dir=session_dir))
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi: {str(e)}'})

@app.route('/api/login-tiktok', methods=['POST'])
def api_login_tiktok():
    """Start interactive login session."""
    try:
        data = request.json or {}
        url = data.get('url')
        
        from scraper.tiktok_scraper import login_tiktok_sync
        success = login_tiktok_sync(url=url)
        
        if success:
            return jsonify({'success': True, 'message': 'Đã cập nhật phiên làm việc.'})
        else:
            return jsonify({'success': False, 'message': 'Chưa hoàn tất thao tác hoặc hết thời gian.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi khởi chạy: {str(e)}'})

# --- API: Multi-account Favorites Sync ---
@app.route('/api/sync-configs', methods=['GET'])
def api_get_sync_configs():
    configs = favorites_syncer.load_sync_configs()
    return jsonify({'success': True, 'configs': configs})

@app.route('/api/sync-configs', methods=['POST'])
def api_save_sync_configs():
    configs = request.json.get('configs', [])
    favorites_syncer.save_sync_configs(configs)
    return jsonify({'success': True, 'message': 'Đã lưu cấu hình đồng bộ.'})

@app.route('/api/sync-status', methods=['GET'])
def api_get_sync_status():
    return jsonify({
        'success': True,
        'status': favorites_syncer.sync_status
    })

@app.route('/api/sync-force', methods=['POST'])
def api_force_sync():
    import threading
    threading.Thread(target=favorites_syncer.sync_all_accounts_job).start()
    return jsonify({'success': True, 'message': 'Đã yêu cầu đồng bộ tức thì.'})

login_sessions = {}

@app.route('/api/login-multi', methods=['POST'])
def api_login_multi():
    profile_name = request.json.get('profile_name')
    if not profile_name:
        return jsonify({'success': False, 'message': 'Thiếu tên tài khoản.'})
        
    session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
    print(f"🔑 Đang mở trình duyệt đăng nhập cho: {profile_name}")
    print(f"📂 Folder session: {session_dir}")
    
    if profile_name not in login_sessions:
        login_sessions[profile_name] = {'status': 'running', 'qr_b64': None, 'message': 'Đang khởi động trình duyệt...'}
    else:
        login_sessions[profile_name]['status'] = 'running'
        login_sessions[profile_name]['qr_b64'] = None
        login_sessions[profile_name]['message'] = 'Đang khởi động trình duyệt...'
    
    import asyncio
    from playwright.async_api import async_playwright
    
    async def login_task():
        # Thử acquire khóa, chờ tối đa 5 giây để luồng đồng bộ ngầm (nếu có) nhả ra
        from scraper.favorites_syncer import get_session_lock
        lock = get_session_lock(profile_name)
        if not lock.acquire(timeout=5):
            login_sessions[profile_name]['status'] = 'error'
            login_sessions[profile_name]['message'] = 'Thư mục session đang được luồng đồng bộ ngầm sử dụng. Vui lòng chờ vài giây rồi nhấn đăng nhập lại!'
            print(f"⚠️ Tranh chấp thư mục session cho: {profile_name} (Đang đồng bộ ngầm)")
            return
            
        try:
            async with async_playwright() as p:
                kwargs = {
                    'user_data_dir': session_dir,
                    'headless': False, # Chạy CÓ giao diện để vượt qua tường lửa/chống bot của TikTok
                    'args': [
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--window-size=1280,800', # Dùng giao diện Desktop để hiện sẵn QR
                        '--disable-extensions'
                    ],
                    'viewport': {'width': 1280, 'height': 800},
                    'locale': 'vi-VN',
                    'timezone_id': 'Asia/Ho_Chi_Minh'
                }
                
                context = await p.chromium.launch_persistent_context(**kwargs)
                page = context.pages[0] if context.pages else await context.new_page()
                
                try:
                    from playwright_stealth import Stealth
                    await Stealth().apply_stealth_async(page)
                except: pass
                
                login_sessions[profile_name]['message'] = 'Đang tải trang đăng nhập TikTok...'
                await page.goto("https://www.tiktok.com/login", timeout=60000)
                
                # Chờ load form đăng nhập
                await asyncio.sleep(5)
                
                # Thử tự động click vào nút "Sử dụng mã QR" nếu TikTok không mở sẵn
                try:
                    # Các text có thể xuất hiện
                    for text in ["Sử dụng mã QR", "Use QR code"]:
                        btn = page.locator(f'text="{text}"').first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(2)
                            break
                    
                    # Hoặc tìm theo thuộc tính
                    btn2 = page.locator('[href*="/login/qrcode"]').first
                    if await btn2.count() > 0 and await btn2.is_visible():
                        await btn2.click()
                        await asyncio.sleep(2)
                except:
                    pass
                
                # Chờ đợi mã QR (canvas) xuất hiện
                try:
                    await page.wait_for_selector('canvas', timeout=10000)
                except:
                    pass
                
                # Chờ người dùng quét mã
                for _ in range(60): # 60 * 2 = 120s
                    await asyncio.sleep(2)
                    if not context.pages or page.is_closed():
                        break
                        
                    # Cách chắc chắn nhất để biết đã đăng nhập: kiểm tra cookie sessionid
                    cookies = await context.cookies()
                    has_session = any(c['name'] == 'sessionid' for c in cookies)
                    
                    if has_session or ("tiktok.com" in page.url and "login" not in page.url):
                        login_sessions[profile_name]['status'] = 'success'
                        login_sessions[profile_name]['message'] = f'Đã đăng nhập thành công cho {profile_name}'
                        print(f"✅ Đã xác nhận đăng nhập thành công cho {profile_name}")
                        await asyncio.sleep(2)
                        break
                        
                    # Chụp ảnh QR code liên tục (vì mã QR có thể tự làm mới)
                    try:
                        import base64
                        # Chỉ chụp đúng thẻ canvas chứa mã QR
                        qr_element = page.locator('canvas').first
                        if await qr_element.count() > 0 and await qr_element.is_visible():
                            screenshot = await qr_element.screenshot(type='jpeg', quality=100)
                            b64 = base64.b64encode(screenshot).decode('utf-8')
                            login_sessions[profile_name]['qr_b64'] = b64
                            login_sessions[profile_name]['message'] = 'Sử dụng ứng dụng TikTok trên điện thoại để quét mã QR bên dưới'
                        else:
                            # Fallback chụp nguyên màn hình (không dùng locator để tránh lỗi Timeout)
                            screenshot = await page.screenshot(type='jpeg', quality=70)
                            b64 = base64.b64encode(screenshot).decode('utf-8')
                            login_sessions[profile_name]['qr_b64'] = b64
                            login_sessions[profile_name]['message'] = 'Không tìm thấy mã QR. Vui lòng xem màn hình để biết chi tiết.'
                    except Exception as e:
                        print("Lỗi chụp QR:", e)
                
                await context.close()
                
                if login_sessions[profile_name]['status'] != 'success':
                    login_sessions[profile_name]['status'] = 'timeout'
                    login_sessions[profile_name]['message'] = 'Hết thời gian chờ đăng nhập.'
                    
        except Exception as e:
            print(f"❌ Lỗi đăng nhập đa tài khoản: {e}")
            login_sessions[profile_name]['status'] = 'error'
            login_sessions[profile_name]['message'] = f'Lỗi hệ thống: {e}'
        finally:
            lock.release()

    def _run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(login_task())
        loop.close()

    import threading
    threading.Thread(target=_run_in_thread, daemon=True).start()
    
    return jsonify({'success': True, 'message': 'Đã khởi chạy luồng đăng nhập.'})

@app.route('/api/login-multi-status', methods=['GET'])
def api_login_multi_status():
    profile_name = request.args.get('profile_name')
    if not profile_name or profile_name not in login_sessions:
        return jsonify({'success': False, 'status': 'not_found'})
    
    return jsonify({
        'success': True,
        'status': login_sessions[profile_name]['status'],
        'qr_b64': login_sessions[profile_name]['qr_b64'],
        'message': login_sessions[profile_name]['message']
    })



@app.route('/api/login-reset', methods=['POST'])
def api_login_reset():
    """Xóa sạch folder session để đăng nhập lại từ đầu."""
    profile_name = request.json.get('profile_name')
    if not profile_name:
        return jsonify({'success': False, 'message': 'Thiếu tên tài khoản.'})
        
    session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
    
    try:
        import shutil
        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
            return jsonify({'success': True, 'message': f'Đã xóa dữ liệu cũ của {profile_name}. Bây giờ bạn có thể đăng nhập mới.'})
        else:
            return jsonify({'success': True, 'message': 'Không có dữ liệu cũ để xóa.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Không thể xóa: {str(e)}. Hãy chắc chắn bạn đã đóng các cửa sổ trình duyệt đang mở.'})

@app.route('/api/run/<config_id>', methods=['POST'])
def api_run_scraper(config_id):
    """Start scraping process for a configuration."""
    config = get_config(config_id)
    if not config:
        return jsonify({'success': False, 'message': 'Không tìm thấy cấu hình.'})
    
    # Check if already running
    if config_id in processing_jobs and processing_jobs[config_id].get('running'):
        return jsonify({'success': False, 'message': 'Đang xử lý, vui lòng đợi.'})
    
    # Initialize job status
    processing_jobs[config_id] = {
        'running': True,
        'total': 0,
        'processed': 0,
        'success': 0,
        'error': 0,
        'current_link': '',
        'started_at': datetime.now().isoformat(),
        'log': []
    }
    
    # Run in background thread
    thread = threading.Thread(target=_run_scraper_thread, args=(config_id, config))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Đã bắt đầu xử lý!'})


@app.route('/api/run/<config_id>/status', methods=['GET'])
def api_run_status(config_id):
    """Get status of a running scraper job."""
    if config_id in processing_jobs:
        return jsonify({'success': True, 'job': processing_jobs[config_id]})
    return jsonify({'success': False, 'message': 'Không có job nào đang chạy.'})



def _run_scraper_thread(config_id, config):
    """Background thread that runs the scraper."""
    job = processing_jobs[config_id]
    
    try:
        spreadsheet_id = config.get('spreadsheet_id', '')
        tab_name = config.get('tab_name', '')
        link_col = config.get('link_col', 'B')
        status_col = config.get('status_col', 'C')
        
        column_mapping = {
            'status_col': config.get('status_col', 'C'),
            'product_name_col': config.get('product_name_col', 'D'),
            'current_price_col': config.get('current_price_col', 'E'),
            'original_price_col': config.get('original_price_col', 'F'),
            'sale_price_col': config.get('sale_price_col', 'G'),
            'product_link_col': config.get('product_link_col', 'H'),
            'shop_name_col': config.get('shop_name_col', 'I'),
            'updated_at_col': config.get('updated_at_col', 'J'),
            'note_col': config.get('note_col', 'K'),
        }
        
        # Tìm profile_name liên kết với config này để lấy session đăng nhập đúng
        profile_name = None
        from scraper.favorites_syncer import load_sync_configs
        sync_configs = load_sync_configs()
        for sc in sync_configs:
            if sc.get('sheet_config_id') == config_id:
                profile_name = sc.get('profile_name')
                break
        
        session_dir = None
        if profile_name:
            session_dir = os.path.join(os.getcwd(), f"tiktok_session_{profile_name}")
            job['log'].append(f'🔑 Sử dụng session của nick: {profile_name}')
        
        # Read links from sheet
        links_result = read_tiktok_links(spreadsheet_id, tab_name, link_col, status_col)
        
        if not links_result['success']:
            job['running'] = False
            job['log'].append(f'❌ Lỗi đọc sheet: {links_result.get("message", "")}')
            return
        
        links = links_result['links']
        job['total'] = len(links)
        
        if not links:
            job['running'] = False
            job['log'].append('ℹ️ Không có link nào cần xử lý.')
            return
        
        job['log'].append(f'📋 Tìm thấy {len(links)} link cần xử lý.')
        
        from concurrent.futures import ThreadPoolExecutor
        
        job['log'].append(f'🚀 Bắt đầu xử lý song song (Concurrency=5)...')
        
        def process_link_task(item):
            if not job['running']:
                return
            
            row = item['row']
            url = item['link']
            
            job['current_link'] = url
            
            try:
                # Set status to "Đang xử lý"
                set_row_status(spreadsheet_id, tab_name, row, status_col, 'Đang xử lý')
                
                # Scrape the link
                try:
                    result = loop.run_until_complete(scrape_tiktok_product(url, custom_session_dir=session_dir))
                except Exception as e:
                    result = {
                        'status': 'Lỗi cần chạy lại',
                        'note': f'Lỗi: {str(e)[:100]}',
                    }
                
                # Write result back to sheet
                update_row(spreadsheet_id, tab_name, row, result, column_mapping)
                
                # Update job stats
                job['processed'] += 1
                if result.get('status') == 'Thành công':
                    job['success'] += 1
                    job['log'].append(f'  ✅ Dòng {row}: {result.get("product_name", "N/A")[:30]}')
                else:
                    job['error'] += 1
                    job['log'].append(f'  ❌ Dòng {row}: {result.get("status", "Lỗi")}')
                
                # Keep log size manageable (last 50 entries)
                if len(job['log']) > 50:
                    job['log'] = job['log'][-50:]
            finally:
                loop.close()

        # Run in parallel with a pool of workers - Reduced to 2 to save memory
        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.map(process_link_task, links)
        
        # Update config last_run
        update_config(config_id, {
            'last_run': datetime.now().isoformat(),
            'status': 'Đã kết nối'
        })
        
        job['log'].append(f'🏁 Hoàn thành! Thành công: {job["success"]}/{job["total"]}, Lỗi: {job["error"]}')
        
    except Exception as e:
        job['log'].append(f'❌ Lỗi nghiêm trọng: {str(e)}')
    finally:
        job['running'] = False
        job['current_link'] = ''


def check_dependencies():
    """Ensure Playwright browsers are installed in a non-blocking way."""
    import subprocess
    import sys
    import os
    import threading
    
    def _do_check():
        # Flag file to avoid checking every single time
        flag_file = os.path.join(os.getcwd(), ".dependencies_checked")
        if os.path.exists(flag_file):
            return

        print("🔍 Đang kiểm tra tài nguyên hệ thống (Chạy ngầm)...")
        try:
            # Check if chromium already exists to avoid redundant install check
            # Default playwright path: %LOCALAPPDATA%\ms-playwright
            appdata = os.getenv('LOCALAPPDATA', '')
            if appdata:
                pw_dir = os.path.join(appdata, 'ms-playwright')
                if os.path.exists(pw_dir) and any('chromium' in d for d in os.listdir(pw_dir)):
                    # Browser seems to exist, create flag and skip
                    with open(flag_file, "w") as f:
                        f.write("checked_fast")
                    print("✅ Tài nguyên đã sẵn sàng (Phát hiện trình duyệt có sẵn).")
                    return

            print("   (Đang kiểm tra trình duyệt Chromium, vui lòng đợi...)")
            # Run playwright install for chromium with dependencies and a longer timeout
            subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, 
                           timeout=300)
            
            with open(flag_file, "w") as f:
                f.write("checked")
            print("✅ Tài nguyên đã sẵn sàng.")
        except subprocess.TimeoutExpired:
            print("⚠️ Cảnh báo: Kiểm tra tài nguyên quá lâu (Timeout). Sẽ thử lại sau.")
        except Exception as e:
            print(f"⚠️ Cảnh báo: Không thể kiểm tra trình duyệt: {e}")
            
    # Run in a background thread so the Flask server (and the UI) starts immediately
    t = threading.Thread(target=_do_check)
    t.daemon = True
    t.start()


# ─── Main Entry Point ─────────────────────────────────────────────

if __name__ == '__main__':
    # Auto-install dependencies if needed
    check_dependencies()

    # Ensure directories exist
    os.makedirs('config', exist_ok=True)
    os.makedirs('credentials', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    # Lấy PORT từ biến môi trường (cho hosting như Render/Railway)
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
