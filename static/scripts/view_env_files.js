/******************************
 * UPLOADS DASHBOARD JS
 * Mirrors email dashboard logic but targets upload endpoints
 ******************************/

// Local state
// let env_id = Number("{{ env_id }}");
let localUploads = []; // list of upload objects from backend
let metrics = {
    docs: { value: 0, limit: 500 },
    emails: { value: 0, limit: 100 },
    orders: { value: 0, limit: 100 }
};

// UI refs
const queueEl = document.getElementById('queueList');
const filters = Array.from(document.querySelectorAll('.filter-btn'));
const searchInput = document.getElementById('search');
const toast = document.getElementById('toast');
const countPending = document.getElementById('countPending');
const countFailed = document.getElementById('countFailed');
const countSuccess = document.getElementById('countSuccess');
const docsProgress = document.getElementById('docsProgress');
const emailsProgress = document.getElementById('emailsProgress');
const ordersProgress = document.getElementById('ordersProgress');
const docsValue = document.getElementById('docsValue');
const emailsValue = document.getElementById('emailsValue');
const ordersValue = document.getElementById('ordersValue');
const bulkReprocessBtn = document.getElementById('bulkReprocessBtn');
const uploadFileInput = document.getElementById('uploadFileInput');
const refreshBtn = document.getElementById('refreshBtn');

// bulk reprocess btn set to disable initially
bulkReprocessBtn.setAttribute('disabled', 'disabled');

// Helper: show toast
let toastTimer = null;
function showToast(msg) {
    clearTimeout(toastTimer);
    toast.textContent = msg;
    toast.classList.add('show');
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
}

// Helper: format bytes
function format_bytes(size) {
    // return size;
    if (size < 1024) {
        return `${size.toFixed(2)} B`
    } else if (size < 1024 ** 2) {
        return `${(size / 1024).toFixed(2)} KB`
    } else if (size < 1024 ** 3) {
        return `${(size / (1024 ** 2)).toFixed(2)} MB`
    } else {
        return `${(size / (1024 ** 3)).toFixed(2)} GB`
    }
}

// Helper: HTML escape
function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, function (m) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]; });
}

// CSRF helper (Django default cookie name)
function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
}
const csrftoken = getCookie('csrftoken');

// Render metrics to UI
function renderMetrics(localMetrics) {
    if (localMetrics) metrics = localMetrics;
    const dPct = Math.round((metrics.docs.value / Math.max(1, metrics.docs.limit)) * 100);
    const ePct = Math.round((metrics.emails.value / Math.max(1, metrics.emails.limit)) * 100);
    const oPct = Math.round((metrics.orders.value / Math.max(1, metrics.orders.limit)) * 100);
    docsProgress.style.width = dPct + '%';
    emailsProgress.style.width = ePct + '%';
    ordersProgress.style.width = oPct + '%';
    docsValue.textContent = `${metrics.docs.value} / ${metrics.docs.limit}`;
    emailsValue.textContent = `${metrics.emails.value} / ${metrics.emails.limit}`;
    ordersValue.textContent = `${metrics.orders.value} / ${metrics.orders.limit}`;
}

// Skeleton helpers
function createSkeletonRowNode() {
    const s = document.createElement('div');
    s.className = 'skeleton-row';
    s.innerHTML = `
        <div class="skeleton skeleton-ava"></div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <div class="skeleton skeleton-line" style="width:70%"></div>
          <div class="skeleton skeleton-line" style="width:45%"></div>
        </div>
        <div style="display:flex;justify-content:flex-end;">
          <div class="skeleton skeleton-small"></div>
        </div>
        <div style="display:flex;justify-content:flex-end;">
          <div class="skeleton skeleton-small" style="width:60px"></div>
        </div>
      `;
    return s;
}
function renderFullListSkeleton(rows = 4) {
    queueEl.innerHTML = '';
    for (let i = 0; i < rows; i++) {
        queueEl.appendChild(createSkeletonRowNode());
    }
}

// Create a real row node from upload object
function createRowNode(upload) {
    // base row
    const row = document.createElement('div');
    row.className = 'row';
    row.dataset.id = upload.id;

    const colorBy = {
        successful: 'linear-gradient(135deg,#10b981,#34d399)',
        failed: 'linear-gradient(135deg,#ef4444,#fb7185)',
        pending: 'linear-gradient(135deg,#f59e0b,#f97316)'
    };
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.style.background = colorBy[upload.status] || '#94a3b8';
    avatar.textContent = (upload.name || 'U')[0].toUpperCase();

    const subj = document.createElement('div');
    subj.className = 'col-subject';
    subj.innerHTML = `<div class="subject">${escapeHtml(upload.name || 'uploaded_file')}</div>
                        <div class="meta">${escapeHtml(upload.uploader || 'Manual Upload')} • ${escapeHtml(upload.date)} • ${upload.attachments.length} attachments • ${format_bytes(upload.total_file_size) || '- KB'}</div>`;

    const statusWrap = document.createElement('div');
    statusWrap.style.display = 'flex';
    statusWrap.style.justifyContent = 'center';
    statusWrap.style.gap = '8px';
    const tag = document.createElement('div');
    tag.className = 'tag ' + (upload.status === 'failed' ? 'failed' : upload.status === 'pending' ? 'pending' : 'success');
    tag.textContent = upload.status === 'failed' ? 'Failed' : upload.status === 'pending' ? 'Pending' : 'Successful';
    statusWrap.appendChild(tag);

    if (upload.status === 'successful') {
        const tag2 = document.createElement('div');
        tag2.className = 'tag ' + (upload.is_approved ? 'success' : 'failed');
        tag2.textContent = upload.is_approved ? 'Approved' : 'Not approved';
        statusWrap.appendChild(tag2);
    }


    const actions = document.createElement('div');
    actions.className = 'col-actions';

    // Rename button
    const btnRename = document.createElement('button');
    btnRename.className = 'icon-btn btn';
    btnRename.title = 'Rename';
    btnRename.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M3 21v-3.75L14.81 5.44a2 2 0 0 1 2.83 0l1.92 1.92a2 2 0 0 1 0 2.83L7.75 22H3z"
                stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"
                stroke-linejoin="round" />
        </svg>`;
    btnRename.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        confirmRename(e, upload.id, row, btnRename, upload.name);
    });
    // End

    const btnReproc = document.createElement('button');
    btnReproc.className = 'icon-btn btn';
    btnReproc.title = 'Reprocess';
    btnReproc.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M21 12a9 9 0 1 0-3.44 6.72" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M21 12v-5" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M21 7l-4 4" stroke="#111827" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;
    btnReproc.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        handleReprocessClick(upload.id, row, btnReproc);
    });


    if (upload.status !== 'failed') {
        btnReproc.setAttribute('disabled', 'disabled');
    };

    const btnDelete = document.createElement('button');
    btnDelete.className = 'icon-btn';
    btnDelete.title = 'Delete upload';
    btnDelete.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path d="M3 6h18" stroke="#111827" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M8 6v12a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V6" stroke="#111827" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M10 11v6" stroke="#111827" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14 11v6" stroke="#111827" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;
    btnDelete.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        confirmDelete(e, upload.id, row, btnDelete);
    });

    actions.appendChild(btnRename);
    actions.appendChild(btnReproc);
    actions.appendChild(btnDelete);

    row.appendChild(avatar);
    row.appendChild(subj);
    row.appendChild(statusWrap);
    row.appendChild(actions);

    if (upload.status === "successful") {
        // Wrap the row in an anchor to review the upload; non-failed uploads are clickable (we keep consistent)
        const link = document.createElement('a');
        link.className = 'row-link';
        link.href = `/environments/envupload/${upload.id}/data/review/`;
        // clicks on action buttons use stopPropagation, so navigation won't interfere
        link.appendChild(row);

        return link;
    }

    return row;
}

// Render list using localUploads (filter + search)
function renderList(filter = 'all', q = '') {
    queueEl.innerHTML = '';
    const filtered = localUploads.filter(e => {
        if (filter !== 'all' && e.status !== filter) return false;
        if (!q) return true;
        const norm = q.toLowerCase();
        return (e.name + ' ' + (e.uploader || '') + ' ' + (e.date || '')).toLowerCase().includes(norm);
    });
    if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.style.padding = '28px';
        empty.style.textAlign = 'center';
        empty.style.color = 'var(--muted)';
        empty.textContent = 'No uploads match this filter/search.';
        queueEl.appendChild(empty);
        updateCounts();
        return;
    }
    filtered.forEach(u => queueEl.appendChild(createRowNode(u)));
    updateCounts();
}

// Update counts & toggle bulk button
function updateCounts() {
    const pending = localUploads.filter(s => s.status === 'pending').length;
    const failed = localUploads.filter(s => s.status === 'failed').length;
    const success = localUploads.filter(s => s.status === 'successful').length;
    countPending.textContent = pending;
    countFailed.textContent = failed;
    countSuccess.textContent = success;

    if (failed === 0) {
        bulkReprocessBtn.setAttribute('disabled', 'disabled');
    } else {
        bulkReprocessBtn.removeAttribute('disabled');
    }
}

/******************************
 * NETWORK ACTIONS (fetch to Django)
 ******************************/

// Load initial uploads from /api/uploads/<env_id>/
async function loadUploads() {
    renderFullListSkeleton(4);
    try {
        const res = await fetch(`/api/uploads/${env_id}/`);
        if (!res.ok) throw new Error('Failed to fetch uploads');
        const json = await res.json();
        // Expecting { uploads: [...] } (or emails in legacy)
        localUploads = Array.isArray(json.uploads) ? json.uploads : (Array.isArray(json.emails) ? json.emails : []);
        if (json.metrics) renderMetrics(json.metrics);
        console.log(json)
        renderList(activeFilter, searchInput.value.trim());
    } catch (e) {
        showToast('Failed loading uploads');
        queueEl.innerHTML = '<div style="padding:20px;color:var(--muted)">Failed to load uploads.</div>';
    }
}

// Upload files (POST multipart to /api/uploads/<env_id>/upload/)
uploadFileInput.addEventListener('change', async (ev) => {
    const files = Array.from(ev.target.files);
    if (files.length === 0) return;

    // uploadFileInput.setAttribute('disabled', 'disabled');

    // show skeletons while uploading
    renderFullListSkeleton(Math.min(4, files.length));
    const form = new FormData();
    files.forEach(f => form.append('files', f));
    try {
        const res = await fetch(`/api/uploads/${env_id}/upload/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken },
            body: form
        });
        if (!res.ok) throw new Error('Upload failed');
        const json = await res.json();
        // expected { uploads: [...], metrics: {...} } or { uploaded: [...], metrics: {...} }
        const newItems = Array.isArray(json.uploads) ? json.uploads : (Array.isArray(json.uploaded) ? json.uploaded : []);
        if (newItems.length) {
            const ids = new Set(localUploads.map(u => u.id));
            newItems.forEach(u => { if (!ids.has(u.id)) localUploads.unshift(u); });
        }
        if (json.metrics) renderMetrics(json.metrics);
        renderList(activeFilter, searchInput.value.trim());
        // showToast((newItems.length || files.length) + ' file(s) uploaded');
        // showToast((files.length) + ' file(s) uploaded');
        if (newItems.length > 0) {
            showToast((newItems.length) + ' upload(s) complete');
            // showToast((files.length) + ' file(s) uploaded');
        } else {
            showToast('Upload failed (All files not supported)')
        }
    } catch (e) {
        console.error(e);
        showToast('Upload failed');
        renderList(activeFilter, searchInput.value.trim());
    } finally {
        ev.target.value = '';
        // uploadFileInput.removeAttribute('disabled');
    }
});

// Reprocess single upload -> POST /api/uploads/:id/reprocess/
async function handleReprocessClick(id, rowNode, btnEl) {
    try {
        btnEl.setAttribute('disabled', 'disabled');
        const placeholder = document.createElement('div');
        placeholder.style.minHeight = rowNode.offsetHeight + 'px';
        rowNode.parentNode.replaceChild(placeholder, rowNode);
        const skeleton = createSkeletonRowNode();
        placeholder.appendChild(skeleton);

        const res = await fetch(`/api/uploads/${id}/reprocess/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
        });
        if (!res.ok) throw new Error('Reprocess failed');
        const json = await res.json();
        console.log("RP JSON: ", json);
        if (json.upload || json.email || json.file) {
            const u = json.upload || json.file || json.email;
            const idx = localUploads.findIndex(x => x.id === u.id);
            if (idx !== -1) localUploads[idx] = u;
            else localUploads.unshift(u);
        }
        if (json.metrics) renderMetrics(json.metrics);
        renderList(activeFilter, searchInput.value.trim());
        showToast(json.processed ? 'Reprocess successful' : 'Reprocess failed');
    } catch (e) {
        showToast('Reprocess failed');
        renderList(activeFilter, searchInput.value.trim());
    }
}


// Delete single upload -> DELETE /api/uploads/:id/delete/
async function handleRenameClick(id, rowNode, btnEl, new_name) {
    btnEl.setAttribute('disabled', 'disabled');
    const placeholder = document.createElement('div');
    placeholder.style.minHeight = rowNode.offsetHeight + 'px';
    rowNode.parentNode.replaceChild(placeholder, rowNode);
    const skeleton = createSkeletonRowNode();
    placeholder.appendChild(skeleton);

    try {
        const res = await fetch(`/api/uploads/${id}/rename/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: new_name
            })
        });
        if (!res.ok) {
            throw new Error('Rename failed')
        }
        const json = await res.json();

        if (json.renamed) {
            const u = json.upload || json.file || json.email;
            const idx = localUploads.findIndex(x => x.id === u.id);
            if (idx !== -1) localUploads[idx] = u;
            else localUploads.unshift(u);

            renderList(activeFilter, searchInput.value.trim());
            if (json.metrics) renderMetrics(json.metrics);
            showToast('Upload renamed');
        } else {
            showToast('Rename failed');
            renderList(activeFilter, searchInput.value.trim());
        }
    } catch (e) {
        showToast('Rename failed');
        renderList(activeFilter, searchInput.value.trim());
    }
}


// Delete single upload -> DELETE /api/uploads/:id/delete/
async function handleDeleteClick(id, rowNode, btnEl) {
    btnEl.setAttribute('disabled', 'disabled');
    const placeholder = document.createElement('div');
    placeholder.style.minHeight = rowNode.offsetHeight + 'px';
    rowNode.parentNode.replaceChild(placeholder, rowNode);
    const skeleton = createSkeletonRowNode();
    placeholder.appendChild(skeleton);

    try {
        const res = await fetch(`/api/uploads/${id}/delete/`, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrftoken }
        });
        if (!res.ok) {
            const fallback = await fetch(`/api/uploads/${id}/delete/`, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
            });
            if (!fallback.ok) throw new Error('Delete failed');
            const fbJson = await fallback.json();
            if (fbJson.deleted) {
                localUploads = localUploads.filter(x => x.id !== id);
                renderList(activeFilter, searchInput.value.trim());
                if (fbJson.metrics) renderMetrics(fbJson.metrics);
                showToast('Upload deleted');
                return;
            } else throw new Error('Delete failed');
        }
        const json = await res.json();
        if (json.deleted) {
            localUploads = localUploads.filter(x => x.id !== id);
            renderList(activeFilter, searchInput.value.trim());
            if (json.metrics) renderMetrics(json.metrics);
            showToast('Upload deleted');
        } else {
            showToast('Delete failed');
            renderList(activeFilter, searchInput.value.trim());
        }
    } catch (e) {
        showToast('Delete failed');
        renderList(activeFilter, searchInput.value.trim());
    }
}

// Reprocess all failed -> POST /api/uploads/reprocess-failed/<env_id>/
bulkReprocessBtn.addEventListener('click', async () => {
    const failedItems = localUploads.filter(s => s.status === 'failed');
    if (failedItems.length === 0) { showToast('No failed items to reprocess'); return; }
    // if (!confirm(`Reprocess ${failedItems.length} failed upload(s)?`)) return;

    failedItems.forEach(item => {
        const row = queueEl.querySelector(`.row[data-id="${item.id}"]`);
        if (row) {
            const placeholder = document.createElement('div');
            placeholder.style.minHeight = row.offsetHeight + 'px';
            row.parentNode.replaceChild(placeholder, row);
            const skeleton = createSkeletonRowNode();
            placeholder.appendChild(skeleton);
        }
    });

    bulkReprocessBtn.setAttribute('disabled', 'disabled');
    try {
        const res = await fetch(`/api/uploads/reprocess-failed/${env_id}/`, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
        });
        if (!res.ok) throw new Error('Bulk reprocess failed');
        const json = await res.json();
        if (Array.isArray(json.results)) {
            const processed_count = json.results.filter(result => result.upload && result.upload.status === "successful").length;
            console.log('JSON: ', json.results)
            console.log("PROCESSED: ", json.results.filter(result => result.upload && result.upload.status === "successful"))
            console.log('PROCESSED COUNT: ', processed_count)
            json.results.forEach(r => {
                const u = r.upload || r.email || r.file;
                const idx = localUploads.findIndex(x => x.id === u.id);
                if (idx !== -1) localUploads[idx] = u;
                else localUploads.unshift(u);
            });
            if (json.metrics) renderMetrics(json.metrics);
            renderList(activeFilter, searchInput.value.trim());
            showToast(`Bulk reprocess finished for ${processed_count} upload${processed_count === 1 ? '' : 's'}`);
        } else {
            if (json.metrics) renderMetrics(json.metrics);
            renderList(activeFilter, searchInput.value.trim());
            showToast('Bulk reprocess finished');
        }
    } catch (e) {
        showToast('Bulk reprocess failed');
        renderList(activeFilter, searchInput.value.trim());
    }
    // } finally {
    //     bulkReprocessBtn.removeAttribute('disabled');
    // }
});

// Refresh
refreshBtn.addEventListener('click', () => {
    bulkReprocessBtn.setAttribute('disabled', 'disabled');
    showToast('Refreshing...');
    loadUploads().then(() => showToast('Refreshed'));
});

// Filters
let activeFilter = 'all';
filters.forEach(btn => {
    btn.addEventListener('click', () => {
        filters.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        renderList(activeFilter, searchInput.value.trim());
    });
});

// Search
searchInput.addEventListener('input', () => {
    renderList(activeFilter, searchInput.value.trim());
});

// Init
(async function init() {
    await loadUploads();
})();

// --------------------------
// Delete modal flow
// --------------------------
// let pendingDelete = null;
function confirmDelete(event, upload_id, row, btn) {
    showModal(upload_id, row, btn);
}
function showModal(upload_id, row, btn) {
    const mb = document.getElementById('modalBackdrop');
    const modaldeletebtn = document.getElementById('modalConfirm');
    mb.style.display = 'flex';
    modaldeletebtn.onclick = () => {
        handleDeleteClick(upload_id, row, btn);
        closeModal();
    }
    modaldeletebtn.focus();
}
function closeModal() { document.getElementById('modalBackdrop').style.display = 'none'; }

// close modal on ESC
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });


// --------------------------
// Rename modal flow
// --------------------------
// let pendingDelete = null;
function confirmRename(event, upload_id, row, btn, current_name) {
    showRenameModal(upload_id, row, btn, current_name);
}

function showRenameModal(upload_id, row, btn, current_name) {
    const mb = document.getElementById('modalRename');
    const modalrenamebtn = document.getElementById('modalRenameConfirm');
    const modalinput = document.getElementById('modalRenameInput');
    modalinput.value = String(current_name);
    modalrenamebtn.setAttribute("disabled", "disabled");
    modalinput.oninput = (e) => {
        if (e.target.value === "" || e.target.value === String(current_name)) {
            modalrenamebtn.setAttribute("disabled", "disabled");
        } else {
            modalrenamebtn.removeAttribute("disabled");
        }
    }
    mb.style.display = 'flex';
    modalrenamebtn.onclick = () => {
        handleRenameClick(upload_id, row, btn, String(modalinput.value));
        closeRenameModal();
    }
    modalrenamebtn.focus();
}
function closeRenameModal() { document.getElementById('modalRename').style.display = 'none'; }

// close modal on ESC
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeRenameModal(); });
