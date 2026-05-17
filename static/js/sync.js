// Logic for Auto Sync Favorites

let syncConfigs = [];

async function loadSyncConfigs() {
    try {
        const res = await fetch('/api/sync-configs');
        const data = await res.json();
        if (data.success) {
            syncConfigs = data.configs || [];
            renderSyncConfigs();
        }
    } catch (e) {
        console.error(e);
    }
}

function renderSyncConfigs() {
    const list = document.getElementById('syncMappingsList');
    if (!list) return;
    
    if (syncConfigs.length === 0) {
        list.innerHTML = `<div class="empty-state" style="padding: 20px;"><p>Chưa có tài khoản nào được cấu hình đồng bộ.</p></div>`;
        return;
    }
    
    let html = '';
    syncConfigs.forEach((cfg, idx) => {
        html += `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border: 1px solid var(--border-color); border-radius: 6px; margin-bottom: 8px;">
            <div>
                <strong>${cfg.profile_name}</strong> 
                <span class="badge ${cfg.active ? 'badge-success' : ''}">${cfg.active ? 'Đang chạy' : 'Tạm dừng'}</span>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                    Sheet Config ID: ${cfg.sheet_config_id}
                </div>
            </div>
            <div>
                <button class="btn btn-secondary btn-sm" onclick="toggleSyncConfig(${idx})">${cfg.active ? 'Tạm dừng' : 'Bật'}</button>
                <button class="btn btn-danger btn-sm" onclick="deleteSyncConfig(${idx})">Xóa</button>
            </div>
        </div>`;
    });
    list.innerHTML = html;
}

async function loginMultiAccount() {
    const profileName = document.getElementById('syncProfileName').value.trim();
    if (!profileName) {
        alert("Vui lòng nhập tên tài khoản trước khi đăng nhập!");
        return;
    }
    
    document.getElementById('syncAddResult').innerHTML = "Đang khởi động trình duyệt... Vui lòng đợi.";
    
    try {
        const res = await fetch('/api/login-multi', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile_name: profileName })
        });
        const data = await res.json();
        document.getElementById('syncAddResult').innerHTML = data.message;
    } catch (e) {
        document.getElementById('syncAddResult').innerHTML = "Lỗi kết nối server.";
    }
}

async function resetMultiAccount() {
    const profileName = document.getElementById('syncProfileName').value.trim();
    if (!profileName) {
        alert("Vui lòng nhập tên tài khoản muốn xóa dữ liệu!");
        return;
    }
    
    if(!confirm(`Bạn có chắc muốn xóa sạch dữ liệu đăng nhập cũ của nick '${profileName}'?`)) return;

    try {
        const res = await fetch('/api/login-reset', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile_name: profileName })
        });
        const data = await res.json();
        alert(data.message);
    } catch (e) {
        alert("Lỗi kết nối server.");
    }
}

async function connectAndSync() {
    const profileName = document.getElementById('syncProfileName').value.trim();
    const sheetConfigId = document.getElementById('syncConfigSelect').value;
    const resultDiv = document.getElementById('syncAddResult');
    
    if (!profileName || !sheetConfigId) {
        alert("Vui lòng nhập tên tài khoản và chọn cấu hình Sheet!");
        return;
    }
    
    try {
        resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Bước 1: Đang làm sạch dữ liệu cũ...</span>`;
        
        // 1. Tự động Reset để tránh nhầm nick
        await fetch('/api/login-reset', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile_name: profileName })
        });

        resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Bước 2: Đang mở trình duyệt đăng nhập... (Vui lòng đăng nhập trong cửa sổ mới)</span>`;
        
        // 2. Mở trình duyệt đăng nhập
        const res = await fetch('/api/login-multi', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile_name: profileName })
        });
        const data = await res.json();
        
        if (data.success) {
            resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Bước 3: Đăng nhập thành công! Đang lưu cấu hình...</span>`;
            
            // 3. Tự động lưu liên kết
            const existing = syncConfigs.find(c => c.profile_name === profileName);
            if (existing) {
                existing.sheet_config_id = sheetConfigId;
                existing.active = true;
            } else {
                syncConfigs.push({
                    profile_name: profileName,
                    sheet_config_id: sheetConfigId,
                    active: true
                });
            }
            
            await saveSyncConfigs();
            resultDiv.innerHTML = `<span style="color:var(--success)">✅ Hoàn tất! Tài khoản ${profileName} đã được kích hoạt đồng bộ.</span>`;
            loadSyncConfigs();
        } else {
            resultDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi: ${data.message}</span>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi kết nối server.</span>`;
    }
}

async function saveSyncConfigs() {
    try {
        await fetch('/api/sync-configs', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ configs: syncConfigs })
        });
        loadSyncConfigs();
    } catch (e) {
        console.error(e);
    }
}

async function toggleSyncConfig(idx) {
    if (syncConfigs[idx]) {
        syncConfigs[idx].active = !syncConfigs[idx].active;
        await saveSyncConfigs();
    }
}

async function deleteSyncConfig(idx) {
    if (confirm("Bạn có chắc muốn xóa liên kết này?")) {
        syncConfigs.splice(idx, 1);
        await saveSyncConfigs();
    }
}

async function forceSyncNow() {
    try {
        const res = await fetch('/api/sync-force', {method: 'POST'});
        const data = await res.json();
        alert(data.message);
        loadSyncStatus();
    } catch (e) {
        console.error(e);
    }
}

async function loadSyncStatus() {
    try {
        const res = await fetch('/api/sync-status');
        const data = await res.json();
        if (data.success && data.status) {
            const logPanel = document.getElementById('syncLogPanel');
            if (logPanel) {
                logPanel.innerHTML = data.status.logs.map(log => `<div>${log}</div>`).join('');
            }
        }
    } catch (e) {
        console.error(e);
    }
}

// Hook into existing app.js functions if possible, or setup interval
document.addEventListener('DOMContentLoaded', () => {
    loadSyncConfigs();
    loadAvailableSheetConfigs();
    
    // Auto refresh logs if section is active
    setInterval(() => {
        const sec = document.getElementById('sec-auto-sync');
        if (sec && sec.classList.contains('active')) {
            loadSyncStatus();
        }
    }, 5000);
});

async function loadAvailableSheetConfigs() {
    try {
        const res = await fetch('/api/configs');
        const data = await res.json();
        const select = document.getElementById('syncConfigSelect');
        if (select && data.success && data.configurations) {
            let html = '<option value="">-- Chọn Sheet và Trang (Tab) --</option>';
            data.configurations.forEach(c => {
                const sheetName = c.name || "Chưa đặt tên";
                const tabName = c.tab_name || "N/A";
                html += `<option value="${c.id}">${sheetName} (Trang: ${tabName})</option>`;
            });
            select.innerHTML = html;
        }
    } catch (e) {
        console.error("Lỗi tải danh sách cấu hình", e);
    }
}
