/**
 * TikTok Shop Price Scraper - Frontend Application
 */

const API = '';
let currentConfig = {};
let allConfigs = [];
let runPollingInterval = null;
let activeRunConfigId = null;

// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadServiceEmail();
  loadConfigs();
  refreshDashboard();
  initDriveConfig();
});

// ─── Navigation ───────────────────────────────────────────────

function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const sec = document.getElementById('sec-' + name);
  if (sec) sec.classList.add('active');

  const nav = document.querySelector(`.nav-item[data-section="${name}"]`);
  if (nav) nav.classList.add('active');

  // Hide run status when switching
  document.getElementById('runStatusOverlay').style.display = 'none';

  if (name === 'dashboard') {
    refreshDashboard();
    populateQuickConfigSelect();
  }
  if (name === 'configs') renderConfigsList();
  if (name === 'settings') loadCurrentCredentials();
  if (name === 'tiktok-view') {
    populateQuickConfigSelect();
  }
}

function populateQuickConfigSelect() {
  const selects = ['quickConfigSelect', 'viewQuickConfigSelect'];

  selects.forEach(id => {
    const select = document.getElementById(id);
    if (!select) return;

    if (allConfigs.length === 0) {
      select.innerHTML = '<option value="">Chưa có cấu hình</option>';
      return;
    }

    const currentValue = select.value;
    select.innerHTML = allConfigs.map(cfg => `<option value="${cfg.id}">${cfg.name || cfg.title}</option>`).join('');

    if (currentValue && allConfigs.find(c => c.id === currentValue)) {
      select.value = currentValue;
    }
  });
}

// ─── Toast ────────────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ─── Loading ──────────────────────────────────────────────────

function showLoading(text = 'Đang xử lý...') {
  document.getElementById('loadingText').textContent = text;
  document.getElementById('loadingOverlay').style.display = 'flex';
}
function hideLoading() {
  document.getElementById('loadingOverlay').style.display = 'none';
}

// ─── Service Email ────────────────────────────────────────────

async function loadServiceEmail() {
  try {
    const res = await fetch(`${API}/api/service-email`);
    const data = await res.json();
    const el = document.getElementById('serviceEmail');
    if (data.success && data.email) {
      el.textContent = data.email;
    } else {
      el.textContent = 'Chưa cấu hình';
      el.style.color = 'var(--text-muted)';
    }
  } catch {
    document.getElementById('serviceEmail').textContent = 'Lỗi kết nối server';
  }
}

function copyEmail() {
  const email = document.getElementById('serviceEmail').textContent;
  if (email && email !== 'Chưa cấu hình' && email !== 'Lỗi kết nối server') {
    navigator.clipboard.writeText(email);
    showToast('Đã copy email!');
  }
}

// ─── Check Connection ─────────────────────────────────────────

async function checkConnection() {
  const url = document.getElementById('sheetUrl').value.trim();
  if (!url) {
    showToast('Vui lòng nhập link Google Sheet', 'error');
    return;
  }

  showLoading('Đang kiểm tra kết nối...');
  try {
    const res = await fetch(`${API}/api/check-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await res.json();
    hideLoading();

    const container = document.getElementById('connectionResult');
    if (data.success) {
      // Extract gid from URL
      const gidMatch = url.match(/[#&]gid=([0-9]+)/);
      const targetGid = gidMatch ? gidMatch[1] : null;
      
      container.innerHTML = `
        <div class="alert alert-success">
          <span class="icon">✅</span>
          <div>
            <strong>${data.message}</strong><br>
            <span style="font-size:12px;opacity:0.8">Các trang tìm thấy: ${data.tabs.map(t => t.title).join(', ')}</span>
          </div>
        </div>`;

      // Store connection info
      currentConfig = {
        name: document.getElementById('configName').value.trim() || data.title,
        sheet_url: url,
        spreadsheet_id: data.spreadsheet_id,
        title: data.title,
        tabs: data.tabs.map(t => t.title)
      };

      // Populate tab select
      const tabSel = document.getElementById('tabSelect');
      tabSel.innerHTML = data.tabs.map(t => `<option value="${t.title}" ${targetGid && t.gid === targetGid ? 'selected' : ''}>${t.title}</option>`).join('');

      // Auto move to step 2 after short delay
      setTimeout(() => goToStep(2), 800);
    } else {
      container.innerHTML = `
        <div class="alert alert-error">
          <span class="icon">❌</span>
          <div>${data.message}</div>
        </div>`;
    }
  } catch (e) {
    hideLoading();
    showToast('Lỗi kết nối server: ' + e.message, 'error');
  }
}

// ─── Steps Navigation ─────────────────────────────────────────

function goToStep(step) {
  document.getElementById('connectStep1').style.display = step === 1 ? 'block' : 'none';
  document.getElementById('connectStep2').style.display = step === 2 ? 'block' : 'none';
  document.getElementById('connectStep3').style.display = step === 3 ? 'block' : 'none';

  ['step1', 'step2', 'step3'].forEach((id, i) => {
    const el = document.getElementById(id);
    el.classList.remove('active', 'completed');
    if (i + 1 === step) el.classList.add('active');
    else if (i + 1 < step) el.classList.add('completed');
  });

  if (step === 2) loadTabData();
  if (step === 3) showConfigSummary();
}

// ─── Load Tab Data ────────────────────────────────────────────

async function loadTabData() {
  const tab = document.getElementById('tabSelect').value;
  if (!currentConfig.spreadsheet_id || !tab) return;

  currentConfig.tab_name = tab;

  try {
    const res = await fetch(`${API}/api/tab-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spreadsheet_id: currentConfig.spreadsheet_id, tab_name: tab })
    });
    const data = await res.json();

    if (data.success) {
      // Show sample data
      const container = document.getElementById('sampleDataContainer');
      if (data.sample && data.sample.length > 0) {
        let html = '<p style="font-size:12px;color:var(--text-muted);margin:12px 0 4px">Dữ liệu mẫu (5 dòng đầu):</p>';
        html += '<div style="overflow-x:auto"><table class="sample-table"><tr>';
        data.columns.forEach((c, i) => {
          html += `<th>${c}${data.headers[i] ? ' - ' + data.headers[i] : ''}</th>`;
        });
        html += '</tr>';
        data.sample.slice(0, 5).forEach(row => {
          html += '<tr>' + row.map(v => `<td title="${v}">${v.substring(0, 40)}</td>`).join('') + '</tr>';
        });
        html += '</table></div>';
        html += `<p style="font-size:12px;color:var(--text-muted);margin-top:8px">Tổng: ${data.total_rows} dòng (không tính header)</p>`;
        container.innerHTML = html;
      }

      // Populate column selects with defaults
      const cols = data.columns;
      const defaults = { colLink: 'B', colStatus: 'C', colName: 'D', colPrice: 'E', colOrigPrice: 'F', colSalePrice: 'G', colProductLink: 'H', colShop: 'I', colUpdated: 'J', colNote: 'K' };

      document.querySelectorAll('.col-select').forEach(sel => {
        sel.innerHTML = cols.map(c => `<option value="${c}">${c}${data.headers[cols.indexOf(c)] ? ' - ' + data.headers[cols.indexOf(c)] : ''}</option>`).join('');
        const def = defaults[sel.id];
        if (def && cols.includes(def)) sel.value = def;
      });
    }
  } catch (e) {
    showToast('Lỗi đọc tab: ' + e.message, 'error');
  }
}

// ─── Config Summary ───────────────────────────────────────────

function showConfigSummary() {
  // Read column selections
  currentConfig.link_col = document.getElementById('colLink').value;
  currentConfig.status_col = document.getElementById('colStatus').value;
  currentConfig.product_name_col = document.getElementById('colName').value;
  currentConfig.current_price_col = document.getElementById('colPrice').value;
  currentConfig.original_price_col = document.getElementById('colOrigPrice').value;
  currentConfig.sale_price_col = document.getElementById('colSalePrice').value;
  currentConfig.product_link_col = document.getElementById('colProductLink').value;
  currentConfig.shop_name_col = document.getElementById('colShop').value;
  currentConfig.updated_at_col = document.getElementById('colUpdated').value;
  currentConfig.note_col = document.getElementById('colNote').value;

  const rows = [
    ['Tên cấu hình', currentConfig.name],
    ['Google Sheet', currentConfig.title],
    ['Tab xử lý', currentConfig.tab_name],
    ['Cột Link TikTok', currentConfig.link_col],
    ['Cột Trạng thái', currentConfig.status_col],
    ['Cột Tên SP', currentConfig.product_name_col],
    ['Cột Giá hiện tại', currentConfig.current_price_col],
    ['Cột Giá gốc', currentConfig.original_price_col],
    ['Cột Giá sale', currentConfig.sale_price_col],
    ['Cột Link SP', currentConfig.product_link_col],
    ['Cột Tên shop', currentConfig.shop_name_col],
    ['Cột Cập nhật', currentConfig.updated_at_col],
    ['Cột Ghi chú', currentConfig.note_col],
  ];

  let html = '<table class="sample-table">';
  rows.forEach(([k, v]) => {
    html += `<tr><td style="font-weight:600;color:var(--text-secondary)">${k}</td><td>${v || '-'}</td></tr>`;
  });
  html += '</table>';

  document.getElementById('configSummary').innerHTML = html;
}

// ─── Save Config ──────────────────────────────────────────────

async function saveConfig() {
  showLoading('Đang lưu cấu hình...');
  try {
    const res = await fetch(`${API}/api/configs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentConfig)
    });
    const data = await res.json();
    hideLoading();

    if (data.success) {
      showToast('Đã lưu cấu hình thành công!');
      currentConfig = {};
      // Reset form
      document.getElementById('configName').value = '';
      document.getElementById('sheetUrl').value = '';
      document.getElementById('connectionResult').innerHTML = '';
      goToStep(1);
      showSection('configs');
      loadConfigs();
    } else {
      showToast('Lỗi lưu: ' + (data.message || ''), 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('Lỗi: ' + e.message, 'error');
  }
}

// ─── Load Configs ─────────────────────────────────────────────

async function loadConfigs() {
  try {
    const res = await fetch(`${API}/api/configs`);
    const data = await res.json();
    if (data.success) {
      allConfigs = data.configurations;
    }
  } catch { /* silent */ }
}

// ─── Render Configs List ──────────────────────────────────────

function renderConfigsList() {
  loadConfigs().then(() => {
    const container = document.getElementById('configsList');

    if (!allConfigs.length) {
      container.innerHTML = `
        <div class="card">
          <div class="empty-state">
            <div class="icon">⚙️</div>
            <h3>Chưa có cấu hình nào</h3>
            <p>Kết nối Google Sheet để bắt đầu sử dụng</p>
            <button class="btn btn-primary" onclick="showSection('connect')">+ Kết nối Sheet</button>
          </div>
        </div>`;
      return;
    }

    let html = '';
    allConfigs.forEach(cfg => {
      const statusBadge = cfg.status === 'Đã kết nối'
        ? '<span class="badge badge-success">● Đã kết nối</span>'
        : '<span class="badge badge-error">● ' + (cfg.status || 'Lỗi') + '</span>';

      const lastRun = cfg.last_run
        ? new Date(cfg.last_run).toLocaleString('vi-VN')
        : 'Chưa chạy';

      html += `
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">
            <div>
              <div class="card-title">${cfg.name || cfg.title || 'Sheet'}</div>
              <p style="font-size:12px;color:var(--text-muted);margin-top:4px">
                Tab: ${cfg.tab_name || '-'} • Lần chạy cuối: ${lastRun}
              </p>
            </div>
            ${statusBadge}
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
            <span class="badge badge-muted">Link: Cột ${cfg.link_col}</span>
            <span class="badge badge-muted">Status: Cột ${cfg.status_col}</span>
            <span class="badge badge-muted">Giá: Cột ${cfg.current_price_col}</span>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:14px;word-break:break-all">
            ${cfg.sheet_url || ''}
          </div>
          <div class="btn-group">
            <button class="btn btn-primary btn-sm" onclick="startRun('${cfg.id}')">▶ Chạy lấy giá</button>
            <button class="btn btn-secondary btn-sm" onclick="recheckConfig('${cfg.id}')">🔄 Kiểm tra</button>
            <button class="btn btn-secondary btn-sm" onclick="viewStats('${cfg.id}')">📊 Thống kê</button>
            <button class="btn btn-danger btn-sm" onclick="deleteConfigUI('${cfg.id}')">🗑 Xóa</button>
          </div>
          <div id="stats-${cfg.id}" style="margin-top:12px"></div>
        </div>`;
    });
    container.innerHTML = html;
  });
}

// ─── Dashboard ────────────────────────────────────────────────

async function refreshDashboard() {
  await loadConfigs();

  const container = document.getElementById('configTableContainer');
  if (!allConfigs.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="icon">📄</div>
        <h3>Chưa có cấu hình nào</h3>
        <p>Bắt đầu bằng cách kết nối Google Sheet đầu tiên</p>
        <button class="btn btn-primary" onclick="showSection('connect')">Kết nối Google Sheet</button>
      </div>`;
    return;
  }

  // Show configs table
  let html = '<table class="config-table"><thead><tr>';
  html += '<th>Tên</th><th>Tab</th><th>Trạng thái</th><th>Lần chạy cuối</th><th>Hành động</th>';
  html += '</tr></thead><tbody>';

  allConfigs.forEach(cfg => {
    const badge = cfg.status === 'Đã kết nối'
      ? '<span class="badge badge-success">● Hoạt động</span>'
      : '<span class="badge badge-error">● Lỗi</span>';
    const lastRun = cfg.last_run ? new Date(cfg.last_run).toLocaleString('vi-VN') : '-';

    html += `<tr>
      <td>
        <div class="config-name">${cfg.name || cfg.title}</div>
        <div class="config-url">${cfg.sheet_url || ''}</div>
      </td>
      <td>${cfg.tab_name || '-'}</td>
      <td>${badge}</td>
      <td style="font-size:12px;color:var(--text-muted)">${lastRun}</td>
      <td>
        <div class="btn-group">
          <button class="btn btn-primary btn-sm" onclick="startRun('${cfg.id}')">▶ Chạy</button>
          <button class="btn btn-secondary btn-sm" onclick="viewStats('${cfg.id}')">📊</button>
        </div>
      </td>
    </tr>`;
  });
  html += '</tbody></table>';
  container.innerHTML = html;

  // Load aggregate stats from first config
  if (allConfigs.length > 0) {
    const cfg = allConfigs[0];
    try {
      const res = await fetch(`${API}/api/sheet-stats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          spreadsheet_id: cfg.spreadsheet_id,
          tab_name: cfg.tab_name,
          status_col: cfg.status_col
        })
      });
      const data = await res.json();
      if (data.success) {
        document.getElementById('statTotal').textContent = data.stats.total;
        document.getElementById('statPending').textContent = data.stats.pending + data.stats.retry;
        document.getElementById('statSuccess').textContent = data.stats.success;
        document.getElementById('statError').textContent = data.stats.error + data.stats.no_product;
      }
    } catch { /* silent */ }
  }

  populateQuickConfigSelect();
}

// ─── TikTok App View ──────────────────────────────────────────

async function openTiktokApp(url = null) {
  try {
    if (!url) {
      url = document.getElementById('tiktokSourceSelect').value;
    }
    showToast('Đang khởi chạy TikTok App Mode...');
    const res = await fetch(`${API}/api/open-tiktok-app`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await res.json();
    if (!data.success) showToast(data.message, 'error');
  } catch (e) {
    showToast('Lỗi khởi chạy: ' + e.message, 'error');
  }
}

function updateTiktokIframe() {
  const url = document.getElementById('tiktokSourceSelect').value;
  openTiktokApp(url);
}

async function quickAddLink() {
  const configId = document.getElementById('quickConfigSelect').value;
  const urlInput = document.getElementById('quickUrlInput');
  const url = urlInput.value.trim();
  const statusDiv = document.getElementById('quickAddStatus');
  const btn = document.getElementById('btnQuickAdd');

  if (!configId || !url) {
    showToast('Vui lòng chọn Sheet và nhập link', 'error');
    return;
  }

  // UI state
  btn.disabled = true;
  const originalBtnHtml = btn.innerHTML;
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block"></div>';
  statusDiv.innerHTML = '<span style="color:var(--text-muted)">⏳ Đang thêm và lấy thông tin... (15-30s)</span>';

  try {
    const res = await fetch(`${API}/api/quick-add-scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config_id: configId, url })
    });
    const data = await res.json();

    if (data.success) {
      statusDiv.innerHTML = `<span style="color:var(--success)">✅ ${data.message}</span>`;
      urlInput.value = '';
      showToast('Đã thêm và lấy giá thành công!');
      refreshDashboard(); // Update stats
    } else {
      statusDiv.innerHTML = `<span style="color:var(--error)">❌ ${data.message}</span>`;
      showToast(data.message, 'error');
    }
  } catch (e) {
    statusDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi kết nối server</span>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalBtnHtml;
    setTimeout(() => { if (statusDiv.innerHTML.includes('✅')) statusDiv.innerHTML = ''; }, 8000);
  }
}

async function viewQuickAddLink() {
  const configId = document.getElementById('viewQuickConfigSelect').value;
  const urlInput = document.getElementById('viewQuickUrlInput');
  const url = urlInput.value.trim();
  const statusDiv = document.getElementById('viewQuickAddStatus');

  if (!configId || !url) {
    showToast('Vui lòng chọn Sheet và nhập link', 'error');
    return;
  }

  statusDiv.innerHTML = '<span style="color:var(--text-muted)">⏳ Đang thêm và lấy thông tin...</span>';

  try {
    const res = await fetch(`${API}/api/quick-add-scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config_id: configId, url })
    });
    const data = await res.json();

    if (data.success) {
      statusDiv.innerHTML = `<span style="color:var(--success)">✅ Đã thêm và lấy giá!</span>`;
      urlInput.value = '';
      showToast('Đã thêm vào Sheet!');
      refreshDashboard();
    } else {
      statusDiv.innerHTML = `<span style="color:var(--error)">❌ ${data.message}</span>`;
    }
  } catch (e) {
    statusDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi kết nối</span>`;
  }
  setTimeout(() => { statusDiv.innerHTML = ''; }, 5000);
}

// ─── TikTok App Actions ───────────────────────────────────────

let currentCapturedImage = null;

let cropper = null;

async function captureAppScreenshot() {
  const container = document.getElementById('phoneScreen');
  const originalHtml = container.innerHTML;

  showLoading('Đang chụp ảnh toàn màn hình...');

  try {
    const res = await fetch(`${API}/api/tiktok-app/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'screenshot' })
    });
    const data = await res.json();
    hideLoading();

    if (data.success) {
      openCropModal(data.image);
    } else {
      showToast(data.message, 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('Lỗi kết nối: ' + e.message, 'error');
  }
}

function openCropModal(base64Image) {
  const modal = document.getElementById('cropModal');
  const image = document.getElementById('cropImage');
  image.src = `data:image/jpeg;base64,${base64Image}`;
  
  modal.style.display = 'flex';
  
  if (cropper) {
    cropper.destroy();
  }
  
  cropper = new Cropper(image, {
    viewMode: 1,
    dragMode: 'move',
    autoCropArea: 0.8,
    restore: false,
    guides: true,
    center: true,
    highlight: false,
    cropBoxMovable: true,
    cropBoxResizable: true,
    toggleDragModeOnDblclick: false,
  });
}

function closeCropModal() {
  document.getElementById('cropModal').style.display = 'none';
  if (cropper) {
    cropper.destroy();
    cropper = null;
  }
}

async function confirmCrop() {
  if (!cropper) return;
  
  const canvas = cropper.getCroppedCanvas({
    maxWidth: 1080,
    maxHeight: 1920,
    fillColor: '#fff',
    imageSmoothingEnabled: true,
    imageSmoothingQuality: 'high',
  });
  
  const croppedImageBase64 = canvas.toDataURL('image/jpeg', 0.9).split(',')[1];
  currentCapturedImage = croppedImageBase64;
  
  const btnSaveToDrive = document.getElementById('btnSaveToDrive');
  if (btnSaveToDrive) btnSaveToDrive.disabled = false;
  
  // Show preview in phone screen
  const container = document.getElementById('phoneScreen');
  container.innerHTML = `
    <div style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:#000; position:relative">
      <img src="data:image/jpeg;base64,${croppedImageBase64}" style="max-width:100%; max-height:100%; object-fit:contain">
      <div style="position:absolute; top:10px; right:10px; background:var(--accent); color:#000; padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700">PREVIEW</div>
    </div>
  `;
  
  closeCropModal();
  showToast('Đã cắt ảnh! Bạn có thể nhấn Lưu Drive & Sheet.');
}

async function saveScreenshotToDrive() {
  if (!currentCapturedImage) {
    showToast('Vui lòng chụp ảnh trước!', 'error');
    return;
  }

  const driveFolderUrl = document.getElementById('driveFolderUrl').value;
  const appsScriptUrl = document.getElementById('appsScriptUrl').value;
  const configId = document.getElementById('viewQuickConfigSelect').value;
  const statusDiv = document.getElementById('viewQuickAddStatus');

  if (!configId) {
    showToast('Vui lòng chọn cấu hình Sheet ở mục "Thao tác nhanh"', 'error');
    return;
  }

  const config = allConfigs.find(c => c.id === configId);
  if (!config) return;

  statusDiv.innerHTML = '<span style="color:var(--text-muted)">⏳ Đang tải ảnh lên Drive & Sheet...</span>';
  
  try {
    const actionRes = await fetch(`${API}/api/tiktok-app/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'get_data' })
    });
    const actionData = await actionRes.json();
    
    const res = await fetch(`${API}/api/tiktok-app/save-screenshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image: currentCapturedImage,
        drive_folder_url: driveFolderUrl,
        apps_script_url: appsScriptUrl,
        spreadsheet_id: config.spreadsheet_id,
        tab_name: config.tab_name,
        video_url: actionData.success ? actionData.video_url : 'TikTok Video',
        product_name: actionData.success ? actionData.title : '',
        price: actionData.success ? actionData.price : '',
        shop_name: actionData.success ? actionData.shop_name : ''
      })
    });
    const data = await res.json();

    if (data.success) {
      statusDiv.innerHTML = `<span style="color:var(--success)">✅ Đã lưu: <a href="${data.drive_link}" target="_blank" style="color:var(--accent)">Xem ảnh</a></span>`;
      showToast('Đã lưu ảnh lên Drive và Sheet!');
    } else {
      statusDiv.innerHTML = `<span style="color:var(--error)">❌ ${data.message}</span>`;
      showToast(data.message, 'error');
    }
  } catch (e) {
    statusDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi: ${e.message}</span>`;
  }
}

function saveDriveConfig() {
  const url = document.getElementById('driveFolderUrl').value;
  const scriptUrl = document.getElementById('appsScriptUrl').value;
  localStorage.setItem('tiktok_drive_folder_url', url);
  localStorage.setItem('tiktok_apps_script_url', scriptUrl);
  showToast('Đã lưu cấu hình Drive!');
}

function syncAppsScriptUrl(value) {
  const fields = ['appsScriptUrl', 'settingsAppsScriptUrl'];
  fields.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  localStorage.setItem('tiktok_apps_script_url', value);
}

function initDriveConfig() {
  const saved = localStorage.getItem('tiktok_drive_folder_url');
  if (saved) document.getElementById('driveFolderUrl').value = saved;
  
  const savedScript = localStorage.getItem('tiktok_apps_script_url');
  if (savedScript) {
    const fields = ['appsScriptUrl', 'settingsAppsScriptUrl'];
    fields.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = savedScript;
    });
  }
}

async function getAppDataAndSave(type = 'video') {
  const statusDiv = document.getElementById('viewQuickAddStatus');
  const configId = document.getElementById('viewQuickConfigSelect').value;

  if (!configId) {
    showToast('Vui lòng chọn cấu hình Sheet', 'error');
    return;
  }

  statusDiv.innerHTML = '<span style="color:var(--text-muted)">⏳ Đang lấy thông tin từ App...</span>';

  try {
    const res = await fetch(`${API}/api/tiktok-app/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'get_data' })
    });
    const data = await res.json();

    if (data.success) {
      let urlToSave = type === 'product' ? data.product_link : data.video_url;

      if (type === 'product' && !urlToSave) {
        statusDiv.innerHTML = '<span style="color:var(--warning)">⚠️ Không tìm thấy link sản phẩm trên trang này.</span>';
        return;
      }

      // Fill the input and call save
      document.getElementById('viewQuickUrlInput').value = urlToSave;
      await viewQuickAddLink();
      showToast(`Đã lưu link ${type === 'product' ? 'sản phẩm' : 'video'}!`);
    } else {
      statusDiv.innerHTML = `<span style="color:var(--error)">❌ ${data.message}</span>`;
    }
  } catch (e) {
    statusDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi: ${e.message}</span>`;
  }
}

async function testScrapeFromApp() {
  showLoading('Đang lấy thông tin từ App TikTok...');
  try {
    const res = await fetch(`${API}/api/tiktok-app/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'get_data' })
    });
    const data = await res.json();

    if (data.success && data.video_url) {
      document.getElementById('testUrl').value = data.video_url;
      hideLoading();
      testScrape();
    } else {
      hideLoading();
      showToast(data.message || 'Không tìm thấy video đang mở.', 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('Lỗi: ' + e.message, 'error');
  }
}

// ─── Run Scraper ──────────────────────────────────────────────

async function startRun(configId) {
  try {
    const res = await fetch(`${API}/api/run/${configId}`, { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      showToast('Đã bắt đầu xử lý!');
      activeRunConfigId = configId;

      // Show run status
      const cfg = allConfigs.find(c => c.id === configId);
      document.getElementById('runConfigName').textContent = cfg ? cfg.name || cfg.title : '';

      // Hide current section, show run status
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      document.getElementById('runStatusOverlay').style.display = 'block';

      // Start polling
      startRunPolling(configId);
    } else {
      showToast(data.message || 'Lỗi', 'error');
    }
  } catch (e) {
    showToast('Lỗi: ' + e.message, 'error');
  }
}

function startRunPolling(configId) {
  if (runPollingInterval) clearInterval(runPollingInterval);

  runPollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API}/api/run/${configId}/status`);
      const data = await res.json();

      if (data.success && data.job) {
        const job = data.job;
        document.getElementById('runTotal').textContent = job.total;
        document.getElementById('runProcessed').textContent = job.processed;
        document.getElementById('runSuccess').textContent = job.success;
        document.getElementById('runError').textContent = job.error;

        const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;
        document.getElementById('runProgressBar').style.width = pct + '%';

        // Update log
        const logPanel = document.getElementById('runLogPanel');
        logPanel.innerHTML = job.log.map(line => {
          let cls = '';
          if (line.includes('✅')) cls = 'success';
          else if (line.includes('❌')) cls = 'error';
          else if (line.includes('ℹ️') || line.includes('📋') || line.includes('🏁')) cls = 'info';
          return `<div class="log-line ${cls}">${line}</div>`;
        }).join('');
        logPanel.scrollTop = logPanel.scrollHeight;

        if (!job.running) {
          clearInterval(runPollingInterval);
          runPollingInterval = null;
          document.getElementById('btnStopRun').style.display = 'none';
          showToast('Xử lý hoàn tất!');
        }
      }
    } catch { /* silent */ }
  }, 2000);
}

async function stopRun() {
  if (!activeRunConfigId) return;
  try {
    await fetch(`${API}/api/run/${activeRunConfigId}/stop`, { method: 'POST' });
    showToast('Đã gửi lệnh dừng');
  } catch { /* silent */ }
}

function closeRunStatus() {
  document.getElementById('runStatusOverlay').style.display = 'none';
  if (runPollingInterval) {
    clearInterval(runPollingInterval);
    runPollingInterval = null;
  }
  showSection('dashboard');
}

// ─── View Stats ───────────────────────────────────────────────

async function viewStats(configId) {
  const cfg = allConfigs.find(c => c.id === configId);
  if (!cfg) return;

  const container = document.getElementById('stats-' + configId);
  container.innerHTML = '<div class="spinner" style="margin:8px auto"></div>';

  try {
    const res = await fetch(`${API}/api/sheet-stats`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        spreadsheet_id: cfg.spreadsheet_id,
        tab_name: cfg.tab_name,
        status_col: cfg.status_col
      })
    });
    const data = await res.json();

    if (data.success) {
      const s = data.stats;
      container.innerHTML = `
        <div class="stats-grid" style="margin-bottom:0">
          <div class="stat-card accent"><div class="stat-value">${s.total}</div><div class="stat-label">Tổng</div></div>
          <div class="stat-card info"><div class="stat-value">${s.pending}</div><div class="stat-label">Chưa xử lý</div></div>
          <div class="stat-card" style="--accent:#00e096"><div class="stat-value" style="color:var(--accent)">${s.success}</div><div class="stat-label">Thành công</div></div>
          <div class="stat-card danger"><div class="stat-value">${s.error}</div><div class="stat-label">Lỗi</div></div>
          <div class="stat-card warning"><div class="stat-value">${s.no_product}</div><div class="stat-label">Không SP</div></div>
          <div class="stat-card purple"><div class="stat-value">${s.retry}</div><div class="stat-label">Cần chạy lại</div></div>
        </div>`;
    } else {
      container.innerHTML = `<div class="alert alert-error"><span class="icon">❌</span>${data.message}</div>`;
    }
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error"><span class="icon">❌</span>Lỗi: ${e.message}</div>`;
  }
}

// ─── Recheck Config ───────────────────────────────────────────

async function recheckConfig(configId) {
  const cfg = allConfigs.find(c => c.id === configId);
  if (!cfg) return;

  showLoading('Đang kiểm tra kết nối...');
  try {
    const res = await fetch(`${API}/api/check-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: cfg.sheet_url })
    });
    const data = await res.json();
    hideLoading();

    if (data.success) {
      await fetch(`${API}/api/configs/${configId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Đã kết nối' })
      });
      showToast('Kết nối thành công!');
    } else {
      await fetch(`${API}/api/configs/${configId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: data.message.substring(0, 50) })
      });
      showToast(data.message, 'error');
    }
    renderConfigsList();
  } catch (e) {
    hideLoading();
    showToast('Lỗi: ' + e.message, 'error');
  }
}

async function deleteConfigUI(configId) {
  if (!confirm('Bạn có chắc muốn xóa cấu hình này?')) return;

  try {
    await fetch(`${API}/api/configs/${configId}`, { method: 'DELETE' });
    showToast('Đã xóa cấu hình');
    await loadConfigs();
    renderConfigsList();
  } catch (e) {
    showToast('Lỗi: ' + e.message, 'error');
  }
}

// ─── Test Scrape ──────────────────────────────────────────────

async function testScrape() {
  const url = document.getElementById('testUrl').value.trim();
  if (!url) {
    showToast('Vui lòng nhập link TikTok', 'error');
    return;
  }

  const btn = document.getElementById('btnTestScrape');
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block"></div> Đang lấy giá...';

  const container = document.getElementById('testResult');
  container.innerHTML = '<div class="alert alert-info"><span class="icon">⏳</span>Đang mở video TikTok và tìm sản phẩm... (có thể mất 15-30 giây)</div>';

  try {
    const res = await fetch(`${API}/api/test-scrape`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await res.json();

    if (data.success && data.result) {
      const r = data.result;
      const isOk = r.status === 'Thành công';
      const isCaptcha = r.note && (r.note.includes('CAPTCHA') || r.note.includes('đăng nhập lại'));

      let html = `<div class="alert ${isOk ? 'alert-success' : isCaptcha ? 'alert-danger' : 'alert-warning'}">
        <span class="icon">${isOk ? '✅' : isCaptcha ? '🛡️' : '⚠️'}</span>
        <div style="display:flex; justify-content:space-between; align-items:center; width:100%">
          <div>
            <strong>Trạng thái: ${r.status}</strong>
            ${isCaptcha ? '<div style="font-size:12px;margin-top:4px">Phát hiện CAPTCHA! Hãy bấm nút bên phải để giải.</div>' : ''}
          </div>
          <div style="display:flex; gap:8px">
            ${isCaptcha ? `<button class="btn btn-primary btn-sm" onclick="loginTikTok('${r.product_link || url}')">🧩 Giải CAPTCHA</button>` : ''}
            <button class="btn btn-secondary btn-sm" onclick="openTiktokApp('${url}')">📱 Xem trong App Mode</button>
          </div>
        </div>
      </div>`;

      if (r.image_url) {
        html += `<div style="margin-bottom:15px; text-align:center">
          <img src="${r.image_url}" style="max-width:100%; max-height:200px; border-radius:8px; border:1px solid rgba(255,255,255,0.1)">
        </div>`;
      }

      html += '<table class="sample-table">';
      const fields = [
        ['Tên sản phẩm', r.product_name],
        ['Giá hiện tại', r.current_price],
        ['Giá gốc', r.original_price],
        ['Giá sale', r.sale_price],
        ['Link sản phẩm', r.product_link ? `<a href="${r.product_link}" target="_blank" style="color:var(--accent)">${r.product_link.substring(0, 60)}...</a>` : '-'],
        ['Tên shop', r.shop_name],
        ['Ghi chú', r.note]
      ];
      
      if (r.product_images && r.product_images.length > 0) {
        let imgsHtml = '<div style="display:flex; gap:5px; overflow-x:auto; padding:5px 0">';
        r.product_images.forEach(img => {
            imgsHtml += `<img src="${img}" style="width:50px; height:50px; object-fit:cover; border-radius:4px">`;
        });
        imgsHtml += '</div>';
        fields.push(['Danh sách ảnh', imgsHtml]);
      }
      fields.forEach(([k, v]) => {
        html += `<tr><td style="font-weight:600;color:var(--text-secondary);width:140px">${k}</td><td>${v || '-'}</td></tr>`;
      });
      html += '</table>';

      container.innerHTML = html;

      // Tự động mở trình duyệt để giải CAPTCHA (giới hạn 1 lần mỗi 60s để tránh vòng lặp)
      const now = Date.now();
      if (isCaptcha && (!window._lastAutoLogin || (now - window._lastAutoLogin > 60000))) {
        window._lastAutoLogin = now;
        showToast('Phát hiện CAPTCHA! Đang tự động mở trình duyệt...', 'warning');
        setTimeout(() => loginTikTok(r.product_link || url), 1500);
      }
    } else {
      container.innerHTML = `<div class="alert alert-error"><span class="icon">❌</span>${data.message || 'Không lấy được dữ liệu'}</div>`;
    }
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error"><span class="icon">❌</span>Lỗi: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🚀 Test lấy giá';
  }
}

// ─── Login TikTok ───────────────────────────────────────────────

async function loginTikTok(url = null) {
  const btn = document.getElementById('btnLoginTiktok');
  const originalHtml = btn.innerHTML;
  
  btn.disabled = true;
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block"></div> Đang mở trình duyệt...';

  showToast(url ? 'Đang mở trang bị lỗi CAPTCHA...' : 'Đang khởi động trình duyệt đăng nhập...');

  try {
    const res = await fetch(`${API}/api/login-tiktok`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, 'success');
      if (url) testScrape(); // Re-run test scrape if it was a specific link
    } else {
      showToast(data.message || 'Không thể đăng nhập', 'warning');
    }
  } catch (e) {
    showToast('Lỗi kết nối: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

// ─── Settings ──────────────────────────────────────────────────

async function loadCurrentCredentials() {
  const textarea = document.getElementById('credentialsJson');
  textarea.value = 'Đang tải...';

  try {
    const res = await fetch(`${API}/api/get-credentials`);
    const data = await res.json();

    if (data.success) {
      textarea.value = JSON.stringify(data.credentials, null, 2);
    } else {
      textarea.value = '';
      showToast(data.message || 'Chưa cấu hình tài khoản.', 'info');
    }
  } catch (e) {
    textarea.value = 'Lỗi tải dữ liệu.';
    showToast('Lỗi: ' + e.message, 'error');
  }
}

async function updateCredentials() {
  const textarea = document.getElementById('credentialsJson');
  const jsonStr = textarea.value.trim();

  if (!jsonStr) {
    showToast('Vui lòng nhập nội dung JSON.', 'error');
    return;
  }

  let credentials;
  try {
    credentials = JSON.parse(jsonStr);
  } catch (e) {
    showToast('JSON không hợp lệ: ' + e.message, 'error');
    return;
  }

  showLoading('Đang cập nhật tài khoản...');
  try {
    const res = await fetch(`${API}/api/update-credentials`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(credentials)
    });
    const data = await res.json();
    hideLoading();

    if (data.success) {
      showToast('Đã cập nhật tài khoản thành công!');
      loadServiceEmail(); // Refresh email in sidebar
    } else {
      showToast('Lỗi: ' + data.message, 'error');
    }
  } catch (e) {
    hideLoading();
    showToast('Lỗi: ' + e.message, 'error');
  }
}

