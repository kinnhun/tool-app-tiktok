"""
Google Sheet Manager - Handles all Google Sheets API interactions.
Uses Service Account approach for MVP.
"""

import re
import json
import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials


# Scopes needed for Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Path to service account credentials
CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials', 'service_account.json')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'sheets_config.json')


def get_client():
    """Get authenticated gspread client using service account."""
    # 1. Try environment variable (for Cloud Deployment)
    env_creds = os.getenv('SERVICE_ACCOUNT_JSON')
    if env_creds:
        try:
            creds_dict = json.loads(env_creds)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Error loading credentials from env: {e}")

    # 2. Fallback to local file (for Local Desktop)
    if not os.path.exists(CREDENTIALS_PATH):
        raise FileNotFoundError(
            "Chưa có file service_account.json trong thư mục credentials/. "
            "Vui lòng tải file credentials từ Google Cloud Console hoặc cấu hình biến môi trường SERVICE_ACCOUNT_JSON."
        )
    
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def get_service_account_email():
    """Get the service account email to display to user."""
    # Try env first
    env_creds = os.getenv('SERVICE_ACCOUNT_JSON')
    if env_creds:
        try:
            return json.loads(env_creds).get('client_email')
        except: pass

    if not os.path.exists(CREDENTIALS_PATH):
        return None
    
    with open(CREDENTIALS_PATH, 'r') as f:
        data = json.load(f)
    return data.get('client_email', None)


def extract_spreadsheet_id(url):
    """Extract spreadsheet ID from Google Sheets URL."""
    # Pattern: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/...
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None


def validate_sheet_url(url):
    """Validate Google Sheets URL format."""
    if not url:
        return False, "Link Google Sheet không được để trống."
    
    if 'docs.google.com/spreadsheets' not in url:
        return False, "Link không đúng định dạng Google Sheet."
    
    spreadsheet_id = extract_spreadsheet_id(url)
    if not spreadsheet_id:
        return False, "Không thể lấy Spreadsheet ID từ link."
    
    return True, spreadsheet_id


def check_connection(url):
    """
    Check if tool can access the Google Sheet.
    Returns dict with connection status and sheet info.
    """
    result = {
        'success': False,
        'message': '',
        'spreadsheet_id': None,
        'title': None,
        'tabs': [],
        'service_email': get_service_account_email()
    }
    
    # Validate URL
    valid, info = validate_sheet_url(url)
    if not valid:
        result['message'] = info
        return result
    
    result['spreadsheet_id'] = info
    
    try:
        client = get_client()
        spreadsheet = client.open_by_key(info)
        result['title'] = spreadsheet.title
        result['tabs'] = [ws.title for ws in spreadsheet.worksheets()]
        result['success'] = True
        result['message'] = f'Kết nối thành công! Sheet: "{spreadsheet.title}"'
    except gspread.exceptions.SpreadsheetNotFound:
        result['message'] = (
            'Không tìm thấy Google Sheet này. '
            f'Vui lòng share quyền Editor cho email: {result["service_email"]}'
        )
    except gspread.exceptions.APIError as e:
        if 'PERMISSION_DENIED' in str(e) or '403' in str(e):
            result['message'] = (
                'Tool chưa có quyền truy cập Google Sheet này. '
                f'Vui lòng bấm Share và cấp quyền Editor cho email: {result["service_email"]}'
            )
        else:
            result['message'] = f'Lỗi API: {str(e)}'
    except FileNotFoundError as e:
        result['message'] = str(e)
    except Exception as e:
        result['message'] = f'Lỗi kết nối: {str(e)}'
    
    return result


def get_tab_data(spreadsheet_id, tab_name):
    """Get sample data from a specific tab."""
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        
        all_values = worksheet.get_all_values()
        
        # If the sheet is empty, initialize it with default headers
        if not all_values:
            default_headers = ['STT', 'Link TikTok', 'Trạng thái', 'Tên sản phẩm', 'Giá hiện tại', 'Giá gốc', 'Giá sale', 'Link sản phẩm', 'Tên shop', 'Cập nhật lúc', 'Ghi chú']
            worksheet.update('A1:K1', [default_headers])
            all_values = [default_headers]
            
        # Get first 5 rows as sample
        sample = all_values[:5] if len(all_values) >= 5 else all_values
        
        # Get column headers (first row)
        headers = all_values[0] if all_values else []
        
        return {
            'success': True,
            'headers': headers,
            'sample': sample,
            'total_rows': len(all_values) - 1,  # Exclude header
            'columns': [chr(65 + i) for i in range(len(headers))]  # A, B, C, ...
        }
    except gspread.exceptions.WorksheetNotFound:
        return {
            'success': False,
            'message': f'Không tìm thấy tab "{tab_name}". Vui lòng kiểm tra lại tên tab.'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Lỗi đọc tab: {str(e)}'
        }


def read_tiktok_links(spreadsheet_id, tab_name, link_col, status_col, start_row=2):
    """
    Read TikTok links from Google Sheet.
    Only returns rows with status: 'Chưa xử lý', 'Lỗi cần chạy lại', 'Cần cập nhật lại' or empty.
    """
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        
        all_values = worksheet.get_all_values()
        
        processable_statuses = ['', 'Chưa xử lý', 'Lỗi cần chạy lại', 'Cần cập nhật lại']
        
        link_col_idx = ord(link_col.upper()) - 65
        status_col_idx = ord(status_col.upper()) - 65
        
        links = []
        for row_idx, row in enumerate(all_values[start_row - 1:], start=start_row):
            if link_col_idx < len(row):
                link = row[link_col_idx].strip()
                status = row[status_col_idx].strip() if status_col_idx < len(row) else ''
                
                if link and status in processable_statuses:
                    links.append({
                        'row': row_idx,
                        'link': link,
                        'status': status
                    })
        
        return {
            'success': True,
            'links': links,
            'total': len(links)
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Lỗi đọc link: {str(e)}',
            'links': [],
            'total': 0
        }


def get_sheet_stats(spreadsheet_id, tab_name, status_col, start_row=2):
    """Get statistics about the sheet processing status."""
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        
        all_values = worksheet.get_all_values()
        status_col_idx = ord(status_col.upper()) - 65
        
        stats = {
            'total': 0,
            'pending': 0,      # Chưa xử lý
            'processing': 0,   # Đang xử lý
            'success': 0,      # Thành công
            'no_product': 0,   # Không có sản phẩm
            'error': 0,        # Lỗi
            'retry': 0,        # Lỗi cần chạy lại
        }
        
        for row in all_values[start_row - 1:]:
            status = row[status_col_idx].strip() if status_col_idx < len(row) else ''
            stats['total'] += 1
            
            if status in ['', 'Chưa xử lý']:
                stats['pending'] += 1
            elif status == 'Đang xử lý':
                stats['processing'] += 1
            elif status == 'Thành công' or status == 'Đã cập nhật lại':
                stats['success'] += 1
            elif status == 'Không có sản phẩm':
                stats['no_product'] += 1
            elif status == 'Lỗi cần chạy lại':
                stats['retry'] += 1
            elif 'Lỗi' in status or 'lỗi' in status:
                stats['error'] += 1
            else:
                stats['pending'] += 1
        
        return {'success': True, 'stats': stats}
    except Exception as e:
        return {'success': False, 'message': str(e), 'stats': {}}


def update_row(spreadsheet_id, tab_name, row_number, data, column_mapping):
    """
    Update a single row in Google Sheet with scraped data.
    
    column_mapping: dict with keys like 'status_col', 'product_name_col', 'price_col', etc.
    data: dict with scraped product info
    """
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        
        updates = []
        
        # Status column
        if 'status' in data and 'status_col' in column_mapping:
            col = column_mapping['status_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['status']]]})
        
        # Product name column
        if 'product_name' in data and 'product_name_col' in column_mapping:
            col = column_mapping['product_name_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['product_name']]]})
        
        # Current price column
        if 'current_price' in data and 'current_price_col' in column_mapping:
            col = column_mapping['current_price_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['current_price']]]})
        
        # Original price column
        if 'original_price' in data and 'original_price_col' in column_mapping:
            col = column_mapping['original_price_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['original_price']]]})
        
        # Sale price column
        if 'sale_price' in data and 'sale_price_col' in column_mapping:
            col = column_mapping['sale_price_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['sale_price']]]})
        
        # Product link column
        if 'product_link' in data and 'product_link_col' in column_mapping:
            col = column_mapping['product_link_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['product_link']]]})
        
        # Shop name column
        if 'shop_name' in data and 'shop_name_col' in column_mapping:
            col = column_mapping['shop_name_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['shop_name']]]})
        
        # Updated time column
        if 'updated_at_col' in column_mapping:
            col = column_mapping['updated_at_col']
            cell = f'{col}{row_number}'
            now = datetime.now().strftime('%d/%m/%Y %H:%M')
            updates.append({'range': cell, 'values': [[now]]})
        
        # Note column
        if 'note' in data and 'note_col' in column_mapping:
            col = column_mapping['note_col']
            cell = f'{col}{row_number}'
            updates.append({'range': cell, 'values': [[data['note']]]})
        
        # Batch update
        if updates:
            # Product images (append to the end of the mapped columns)
            if 'product_images' in data and data['product_images']:
                # Find the "furthest" column used in mapping
                col_letters = [v for k, v in column_mapping.items() if k.endswith('_col')]
                if col_letters:
                    # Helper to convert column letter to index and back
                    def col_to_idx(c):
                        idx = 0
                        for char in c:
                            idx = idx * 26 + (ord(char.upper()) - 64)
                        return idx
                    
                    def idx_to_col(n):
                        res = ""
                        while n > 0:
                            n, rem = divmod(n - 1, 26)
                            res = chr(65 + rem) + res
                        return res
                    
                    max_idx = max(col_to_idx(c) for c in col_letters)
                    start_col_idx = max_idx + 1
                    
                    for i, img_url in enumerate(data['product_images']):
                        if i >= 5: break # Chỉ lấy tối đa 5 ảnh để tránh lag sheet
                        col = idx_to_col(start_col_idx + i)
                        cell = f'{col}{row_number}'
                        # Dùng HYPERLINK + IMAGE với tham số size (mode 4, width 250, height 250)
                        # Dùng dấu chấm phẩy ; cho Google Sheet tiếng Việt
                        safe_url = img_url.strip().replace('"', '""')
                        img_val = f'=HYPERLINK("{safe_url}"; IMAGE("{safe_url}"; 4; 250; 250))' if img_url else ''
                        updates.append({'range': cell, 'values': [[img_val]]})

            if updates:
                worksheet.batch_update(updates, value_input_option='USER_ENTERED')
                
                # Tự động dãn dòng và cột bằng API gốc của Google Sheets (tránh lỗi attribute)
                if 'product_images' in data and data['product_images']:
                    try:
                        sheet_id = worksheet.id
                        max_idx = max(col_to_idx(c) for c in col_letters)
                        
                        dim_requests = [
                            {
                                "updateDimensionProperties": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "dimension": "ROWS",
                                        "startIndex": row_number - 1,
                                        "endIndex": row_number
                                    },
                                    "properties": {"pixelSize": 250},
                                    "fields": "pixelSize"
                                }
                            },
                            {
                                "updateDimensionProperties": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "dimension": "COLUMNS",
                                        "startIndex": max_idx,
                                        "endIndex": max_idx + 5
                                    },
                                    "properties": {"pixelSize": 250},
                                    "fields": "pixelSize"
                                }
                            }
                        ]
                        spreadsheet.batch_update({"requests": dim_requests})
                    except Exception as e:
                        print(f"Format error: {e}")
        
        return True
    except Exception as e:
        print(f"Error updating row {row_number}: {e}")
        return False


def set_row_status(spreadsheet_id, tab_name, row_number, status_col, status):
    """Quick helper to set just the status of a row."""
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        cell = f'{status_col}{row_number}'
        worksheet.update(cell, [[status]])
        return True
    except Exception as e:
        print(f"Error setting status: {e}")
        return False


# ---- Configuration Management ----

def load_configs():
    """Load saved configurations from JSON file."""
    if not os.path.exists(CONFIG_PATH):
        return []
    
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('configurations', [])


def save_configs(configs):
    """Save configurations to JSON file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump({'configurations': configs}, f, ensure_ascii=False, indent=2)


def add_config(config):
    """Add a new sheet configuration."""
    configs = load_configs()
    
    # Generate ID
    config['id'] = datetime.now().strftime('%Y%m%d%H%M%S')
    config['created_at'] = datetime.now().isoformat()
    config['status'] = 'Đã kết nối'
    config['last_run'] = None
    
    configs.append(config)
    save_configs(configs)
    return config


def update_config(config_id, updates):
    """Update an existing configuration."""
    configs = load_configs()
    for i, cfg in enumerate(configs):
        if cfg['id'] == config_id:
            configs[i].update(updates)
            save_configs(configs)
            return configs[i]
    return None


def delete_config(config_id):
    """Delete a configuration."""
    configs = load_configs()
    configs = [c for c in configs if c['id'] != config_id]
    save_configs(configs)
    return True


def get_config(config_id):
    """Get a single configuration by ID."""
    configs = load_configs()
    for cfg in configs:
        if cfg['id'] == config_id:
            return cfg
    return None


def extract_folder_id(url):
    """Extract folder ID from Google Drive folder URL."""
    # Pattern: https://drive.google.com/drive/folders/{FOLDER_ID}
    match = re.search(r'/folders/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    return None


def upload_to_drive(file_content, filename, target_folder_url=None, apps_script_url=None):
    """Upload file to Google Drive. Supports Apps Script proxy to bypass quota."""
    import base64
    import requests

    # --- Option 1: Use Apps Script Proxy (Recommended for Personal Accounts) ---
    if apps_script_url:
        try:
            folder_id = extract_folder_id(target_folder_url)
            if not folder_id:
                raise Exception("Không tìm thấy Folder ID từ link Drive.")
                
            if '/dev' in apps_script_url:
                raise Exception("Bạn đang dùng link '/dev'. Vui lòng Deploy bản 'New Deployment' và lấy link kết thúc bằng '/exec'.")

            payload = {
                "filename": filename,
                "folderId": folder_id,
                "base64": base64.b64encode(file_content).decode('utf-8')
            }
            
            # Use specific headers to help Apps Script return raw JSON
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            
            resp = requests.post(apps_script_url, json=payload, headers=headers, allow_redirects=True)
            
            try:
                # Try to clean response if it has garbage
                text = resp.text.strip()
                if text.startswith('<!DOCTYPE'):
                    # It's HTML, search for JSON inside if it's there
                    json_match = re.search(r'({.*success.*url.*})', text)
                    if json_match:
                        result = json.loads(json_match.group(1))
                    else:
                        raise ValueError("HTML Response")
                else:
                    result = resp.json()
                
                if result.get('success'):
                    return result.get('url').replace('\\/', '/')
                else:
                    raise Exception(result.get('message', 'Lỗi Apps Script.'))
            except Exception:
                # Fallback: Try to find a drive URL pattern in the text if it's not JSON
                import re
                # Improved regex to handle escaped slashes (\/) and capture full URL
                url_match = re.search(r'https?://drive\.google\.com/[^\s"\'<>]+', resp.text.replace('\\/', '/'))
                if url_match:
                    return url_match.group(0).rstrip('.,')
                    
                # If still not found, check for login page
                if "Google Accounts" in resp.text or "login" in resp.text.lower():
                    raise Exception("Apps Script yêu cầu đăng nhập. Hãy Deploy lại bản 'New Version' và chọn 'Anyone'.")
                
                snippet = resp.text[:100] + "..." if len(resp.text) > 100 else resp.text
                raise Exception(f"Apps Script không trả về link ảnh (Mã {resp.status_code}). Phản hồi: {snippet}")
        except Exception as e:
            raise Exception(f"Lỗi qua Apps Script: {str(e)}")

    # --- Option 2: Use Service Account ---
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    import io

    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    # 1. Ensure folder exists
    folder_id = None
    
    if target_folder_url:
        folder_id = extract_folder_id(target_folder_url)
    
    if not folder_id:
        query = "name='TikTok Shop Saver' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        results = service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])

        if not items:
            file_metadata = {'name': 'TikTok Shop Saver', 'mimeType': 'application/vnd.google-apps.folder'}
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
        else:
            folder_id = items[0]['id']

    # 2. Upload file
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype='image/jpeg', resumable=True)
    file = service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id',
        supportsAllDrives=True
    ).execute()
    file_id = file.get('id')

    # 3. Make public
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'},
        supportsAllDrives=True
    ).execute()

    return f'https://drive.google.com/uc?export=view&id={file_id}'


def update_row_with_frames(spreadsheet_id, tab_name, data):
    """
    Appends a new row to the sheet with product info and frame images.
    Format: Link | Giá | Ảnh SP | Frame 1 | Frame 2 | Frame 3
    """
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)

        img = lambda url: f'=IMAGE("{url}")' if url else ''
        
        # Structure matching the extension's logic:
        # B=Link, D=Giá, E=Ảnh SP, F=Frame1, G=Frame2, H=Frame3
        # In this tool, we'll just append to the end of the sheet or specific columns if defined.
        # For simplicity, we'll follow a standard row: [Link, Price, Thumb, F1, F2, F3]
        
        row_values = [
            data.get('video_url', ''),
            data.get('price', ''),
            img(data.get('thumbnail_url', '')),
            img(data.get('frame_urls', [None])[0]),
            img(data.get('frame_urls', [None, None])[1]),
            img(data.get('frame_urls', [None, None, None])[2]),
            datetime.now().strftime('%d/%m/%Y %H:%M')
        ]
        
        worksheet.append_row(row_values, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"Error appending row with frames: {e}")
        return False

def append_link(spreadsheet_id, tab_name, link, link_col, status_col, status="Chưa xử lý"):
    """Append a new link to the sheet."""
    try:
        client = get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(tab_name)
        
        # Get all headers to find where to put the data
        all_values = worksheet.get_all_values()
        if not all_values:
            # If sheet is empty, create headers first
            headers = ['STT', 'Link TikTok', 'Trạng thái', 'Tên sản phẩm', 'Giá hiện tại', 'Giá gốc', 'Giá sale', 'Link sản phẩm', 'Tên shop', 'Cập nhật lúc', 'Ghi chú']
            worksheet.update('A1:K1', [headers])
            all_values = [headers]
            
        headers = all_values[0]
        
        # Determine how many columns to fill
        max_col_idx = 0
        link_idx = ord(link_col.upper()) - 65
        status_idx = ord(status_col.upper()) - 65
        max_col_idx = max(link_idx, status_idx)
        
        # Create a row with empty strings
        new_row = [""] * (max_col_idx + 1)
        new_row[link_idx] = link
        new_row[status_idx] = status
        
        # If there's an STT column (usually column A), fill it
        if 'STT' in headers:
            stt_idx = headers.index('STT')
            if stt_idx < len(new_row):
                new_row[stt_idx] = len(all_values)
        
        worksheet.append_row(new_row, value_input_option='USER_ENTERED')
        return True, "Đã thêm link vào Google Sheet."
    except Exception as e:
        print(f"Error appending link: {e}")
        return False, str(e)
