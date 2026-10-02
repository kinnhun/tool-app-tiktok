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
            <div style="display: flex; gap: 4px;">
                <button class="btn btn-primary btn-sm" onclick="loginSyncAccount('${cfg.profile_name}')">🔑 Đăng nhập</button>
                <button class="btn btn-secondary btn-sm" onclick="toggleSyncConfig(${idx})">${cfg.active ? 'Tạm dừng' : 'Bật'}</button>
                <button class="btn btn-danger btn-sm" onclick="deleteSyncConfig(${idx})">Xóa</button>
            </div>
        </div>`;
    });
    list.innerHTML = html;
}

async function loginSyncAccount(profileName) {
    const resultDiv = document.getElementById('syncAddResult');
    if (!resultDiv) return;
    
    resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Đang mở trình duyệt đăng nhập...</span>`;
    
    try {
        const res = await fetch('/api/login-multi', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ profile_name: profileName })
        });
        const data = await res.json();
        
        if (data.success) {
            pollLoginStatus(profileName, null, resultDiv);
        } else {
            resultDiv.innerHTML = `<span style="color:var(--error)">❌ ${data.message}</span>`;
        }
    } catch (e) {
        resultDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi kết nối server</span>`;
    }
}

let loginPollInterval = null;

async function pollLoginStatus(profileName, sheetConfigId, resultDiv) {
    if (loginPollInterval) clearInterval(loginPollInterval);
    
    loginPollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/login-multi-status?profile_name=${encodeURIComponent(profileName)}`);
            const data = await res.json();
            
            if (data.success) {
                let html = `<span style="color:var(--accent)">⏳ ${data.message}</span>`;
                
                if (data.qr_b64) {
                    html += `<div style="text-align: center;"><img src="data:image/jpeg;base64,${data.qr_b64}" style="width: 250px; height: 250px; object-fit: contain; border-radius: 8px; margin-top: 10px; border: 2px solid var(--border-color); background: white; padding: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);"></div>`;
                }
                
                resultDiv.innerHTML = html;
                
                if (data.status === 'success') {
                    clearInterval(loginPollInterval);
                    resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Bước 3: Đăng nhập thành công! Đang lưu cấu hình...</span>`;
                    
                    if (sheetConfigId) {
                        const existing = syncConfigs.find(c => c.profile_name === profileName && c.sheet_config_id === sheetConfigId);
                        if (existing) {
                            existing.active = true;
                        } else {
                            syncConfigs.push({
                                profile_name: profileName,
                                sheet_config_id: sheetConfigId,
                                active: true
                            });
                        }
                        
                        await saveSyncConfigs();
                        resultDiv.innerHTML = `<span style="color:var(--success)">✅ Hoàn tất! Đang tiến hành lấy dữ liệu Yêu thích... Bạn có thể xem Log bên dưới.</span>`;
                        loadSyncConfigs();
                        
                        // Kích hoạt đồng bộ ngay lập tức
                        forceSyncNow();
                    }
                } else if (data.status === 'timeout' || data.status === 'error' || data.status === 'not_found') {
                    clearInterval(loginPollInterval);
                    resultDiv.innerHTML = `<span style="color:var(--error)">❌ Quá trình đăng nhập kết thúc (${data.status}). Vui lòng thử lại.</span>`;
                }
            }
        } catch (e) {
            console.error(e);
        }
    }, 2000);
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
        alert("Vui lòng nhập Link Kênh và chọn cấu hình Sheet!");
        return;
    }
    
    if (!profileName.includes("tiktok.com")) {
        alert("Link kênh không hợp lệ! Vui lòng nhập link chuẩn (VD: https://www.tiktok.com/@username)");
        return;
    }
    
    try {
        resultDiv.innerHTML = `<span style="color:var(--accent)">⏳ Đang thiết lập cấu hình...</span>`;
        
        const existing = syncConfigs.find(c => c.profile_name === profileName && c.sheet_config_id === sheetConfigId);
        if (existing) {
            existing.active = true;
        } else {
            syncConfigs.push({
                profile_name: profileName,
                sheet_config_id: sheetConfigId,
                active: true
            });
        }
        
        await saveSyncConfigs();
        resultDiv.innerHTML = `<span style="color:var(--success)">✅ Hoàn tất! Hệ thống sẽ quét video Đã thích (Liked) tự động mỗi 2 phút.</span>`;
        loadSyncConfigs();
        
        // Kích hoạt đồng bộ ngay lập tức
        forceSyncNow();
        
    } catch (e) {
        resultDiv.innerHTML = `<span style="color:var(--error)">❌ Lỗi: ${e.message}</span>`;
        console.error(e);
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

let currentSyncEnabled = true;
let currentSyncInterval = 600;

async function loadQueueStatus() {
    try {
        const res = await fetch('/api/queue-status');
        const data = await res.json();
        if (!data.success) return;
        
        currentSyncEnabled = data.sync_enabled !== false;
        currentSyncInterval = data.sync_interval_seconds || 600;
        
        // Cập nhật nút bật/tắt quét ngầm
        const btnToggle = document.getElementById('btnToggleAutoSync');
        if (btnToggle) {
            if (currentSyncEnabled) {
                btnToggle.className = 'btn btn-secondary btn-sm';
                btnToggle.innerText = '⏸ Tạm dừng quét ngầm';
            } else {
                btnToggle.className = 'btn btn-success btn-sm';
                btnToggle.innerText = '▶️ Bật quét ngầm';
            }
        }
        
        const selInterval = document.getElementById('syncIntervalSelect');
        if (selInterval && selInterval.value != currentSyncInterval) {
            selInterval.value = currentSyncInterval;
        }
        
        // Cập nhật huy hiệu trạng thái
        const qSize = data.queue_size || 0;
        const isBusy = data.is_busy;
        const activeJobs = data.active_jobs || [];
        
        let statusText = '🟢 Rảnh rỗi';
        let badgeClass = 'badge badge-success';
        let detailText = `Hàng đợi: ${qSize} task chờ | Quét ngầm: ${currentSyncEnabled ? 'Đang bật (' + Math.round(currentSyncInterval/60) + ' phút/lần)' : 'Đã tắt'}`;
        
        if (isBusy || activeJobs.length > 0) {
            statusText = '🟡 Đang xử lý';
            badgeClass = 'badge badge-warning';
            if (activeJobs.length > 0) {
                const j = activeJobs[0];
                detailText = `Đang cào sản phẩm: ${j.processed}/${j.total} link | ${qSize} task trong hàng đợi`;
            } else {
                detailText = `Hệ thống đang bận | ${qSize} task trong hàng đợi`;
            }
        }
        
        // Huy hiệu ở tab Auto-Sync
        const queueBadge = document.getElementById('queueBadge');
        if (queueBadge) {
            queueBadge.className = badgeClass;
            queueBadge.innerText = statusText;
        }
        const queueDetail = document.getElementById('queueDetailText');
        if (queueDetail) {
            queueDetail.innerText = detailText;
        }
        
        // Thanh hàng đợi ở Dashboard
        const dashBadge = document.getElementById('dashQueueStatusBadge');
        if (dashBadge) {
            dashBadge.className = badgeClass;
            dashBadge.innerText = statusText;
        }
        const dashInfo = document.getElementById('dashQueueInfo');
        if (dashInfo) {
            dashInfo.innerText = `(${qSize} tác vụ trong hàng đợi)`;
        }
        const dashSyncText = document.getElementById('dashSyncText');
        if (dashSyncText) {
            dashSyncText.innerText = currentSyncEnabled ? `Đang bật (${Math.round(currentSyncInterval/60)} phút)` : 'Đã tắt';
            dashSyncText.style.color = currentSyncEnabled ? 'var(--success)' : 'var(--error)';
        }
    } catch (e) {
        // silent
    }
}

async function toggleAutoSync() {
    try {
        const res = await fetch('/api/sync-control', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ enabled: !currentSyncEnabled })
        });
        const data = await res.json();
        if (data.success) {
            loadQueueStatus();
        }
    } catch (e) {
        console.error(e);
    }
}

async function changeSyncInterval(val) {
    try {
        const res = await fetch('/api/sync-control', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ interval_seconds: parseInt(val) })
        });
        const data = await res.json();
        if (data.success) {
            loadQueueStatus();
        }
    } catch (e) {
        console.error(e);
    }
}

// Hook into existing app.js functions if possible, or setup interval
document.addEventListener('DOMContentLoaded', () => {
    loadSyncConfigs();
    loadAvailableSheetConfigs();
    loadQueueStatus();
    
    // Theo dõi hàng đợi định kỳ mỗi 3 giây
    setInterval(loadQueueStatus, 3000);
    
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

