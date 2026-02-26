/******************************
 * DASHBOARD JS - connects to Django endpoints
 ******************************/

// Local state
// let env_id = Number("{{ env_id }}");
// console.log(env_id)
let localEmails = []; // list of email objects from backend
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
// const countLimit = document.getElementById('countLimit');
const docsProgress = document.getElementById('docsProgress');
const emailsProgress = document.getElementById('emailsProgress');
const ordersProgress = document.getElementById('ordersProgress');
const docsValue = document.getElementById('docsValue');
const emailsValue = document.getElementById('emailsValue');
const ordersValue = document.getElementById('ordersValue');
const adduserBtn = document.getElementById('adduserBtn');
// const bulkReprocessBtn = document.getElementById('bulkReprocessBtn');
const scanBtn = document.getElementById('scanBtn');
const fileUpload = document.getElementById('fileUpload');
const refreshBtn = document.getElementById('refreshBtn');

// bulk reprocess btn set to disable initially
// bulkReprocessBtn.setAttribute('disabled', 'disabled');

// Add user
adduserBtn.addEventListener("click", () => {
    confirmAdd();
})

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
    // countLimit.textContent = `${metrics.active_users.value} / ${metrics.active_users.limit}`;
}

// Skeleton helpers (same as before)
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

// Create a real row node from email object
function createRowNode(email) {
    // create the actual row element (kept the same structure)
    console.log(email)
    const row = document.createElement('div');
    row.className = 'row';
    row.dataset.id = email.id;

    const colorBy = {
        true: 'linear-gradient(135deg,#10b981,#34d399)',
        false: 'linear-gradient(135deg,#ef4444,#fb7185)',
    };
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.style.background = colorBy[email.is_active] || '#94a3b8';
    avatar.textContent = (email.username || 'u')[0].toUpperCase();

    const subj = document.createElement('div');
    subj.className = 'col-subject';
    subj.innerHTML = `<div class="subject">${escapeHtml(email.username)}</div>
                        <div class="meta">${escapeHtml(email.role)} • Added on ${escapeHtml(email.date_joined)} 
                        ${ email.last_login ? ` • Last login on ${escapeHtml(email.last_login)}` : "" }
                        </div>`;

    const statusWrap = document.createElement('div');
    statusWrap.style.display = 'flex';
    statusWrap.style.justifyContent = 'flex-end';
    statusWrap.style.gap = '8px';
    const tag = document.createElement('div');
    tag.className = 'tag ' + (email.is_active ? 'success' : 'failed');
    tag.textContent = email.is_active ? 'Active' : 'Inactive';

    statusWrap.appendChild(tag);

    const actions = document.createElement('div');
    actions.className = 'col-actions';


    // const btnReproc = document.createElement('button');
    // btnReproc.className = 'icon-btn btn';
    // btnReproc.title = 'Reprocess with AI';
    // btnReproc.innerHTML = `
    //     <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
    //         <path d="M3 21v-3.75L14.81 5.44a2 2 0 0 1 2.83 0l1.92 1.92a2 2 0 0 1 0 2.83L7.75 22H3z"
    //             stroke="#0f172a" stroke-width="1.25" stroke-linecap="round"
    //             stroke-linejoin="round" />
    //     </svg>`;
    // btnReproc.addEventListener('click', (e) => {
    //     e.stopPropagation();
    //     e.preventDefault();
    //     handleReprocessClick(email.id, row, btnReproc);
    // });

    // Rename button
    const btnRename = document.createElement('button');
    btnRename.className = 'icon-btn btn';
    btnRename.title = 'Edit user';
    btnRename.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M3 21v-3.75L14.81 5.44a2 2 0 0 1 2.83 0l1.92 1.92a2 2 0 0 1 0 2.83L7.75 22H3z"
                stroke="#0f172a" stroke-width="1.5" stroke-linecap="round"
                stroke-linejoin="round" />
        </svg>`;
    btnRename.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        confirmRename(email, row, btnRename);
    });
    // End

    // if (email.status !== 'failed') {
    //     btnReproc.setAttribute('disabled', 'disabled');
    // }


    // const btnDelete = document.createElement('button');
    // btnDelete.className = 'icon-btn';
    // btnDelete.title = 'Delete user';
    // btnDelete.innerHTML = `
    //     <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
    //         <path
    //             d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"
    //             stroke="#ef4444" stroke-width="1.25" stroke-linecap="round"
    //             stroke-linejoin="round" />
    //     </svg>`;

    // // btnDelete.addEventListener('click', () => handleDeleteClick(email.id, row, btnDelete));
    // btnDelete.addEventListener('click', (e) => {
    //     e.stopPropagation();
    //     e.preventDefault();
    //     confirmDelete(e, email.id, row, btnDelete)
    // }
    // );

    // actions.appendChild(btnReproc);
    actions.appendChild(btnRename);
    // actions.appendChild(btnDelete);

    row.appendChild(avatar);
    row.appendChild(subj);
    row.appendChild(statusWrap);
    row.appendChild(actions);

    if (email.status === "successful") {
        // --- WRAP the row in an anchor tag as requested ---
        const link = document.createElement('a');
        link.className = 'row-link';
        link.href = `/environments/envmail/${email.id}/data/review`; // user requested empty href; you can change this later
        // prevent default navigation while href is empty so existing actions work as before
        // link.addEventListener('click', (e) => {
        //     // if you want the anchor to navigate later, remove this handler
        //     e.preventDefault();
        // });
        // append the row inside the anchor
        link.appendChild(row);

        return link;
    }

    return row;
}

// Render list using localEmails (filter + search)
function renderList(filter = 'all', q = '') {
    queueEl.innerHTML = '';
    console.log("USERS: ", localEmails);
    const filtered = localEmails.filter(e => {
        console.log(typeof e.is_active)
        if (filter !== 'all' && String(e.is_active) !== filter) return false;
        if (!q) return true;
        const norm = q.toLowerCase();
        return (e.username + ' ' + e.date_joined).toLowerCase().includes(norm);
    });
    if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.style.padding = '28px';
        empty.style.textAlign = 'center';
        empty.style.color = 'var(--muted)';
        empty.textContent = 'No users match this filter/search.';
        queueEl.appendChild(empty);
        updateCounts();
        return;
    }
    console.log('FILTERED: ', filtered)
    filtered.forEach(e => queueEl.appendChild(createRowNode(e)));
    updateCounts();
}

// Update counts & toggle bulk button
function updateCounts() {
    // const pending = localEmails.filter(s => s.status === 'pending').length;
    const active = localEmails.filter(s => s.is_active).length;
    const inactive = localEmails.filter(s => !s.is_active).length;
    // countPending.textContent = pending;
    countSuccess.textContent = active;
    countFailed.textContent = inactive;

    // if (inactive === 0) {
    //     bulkReprocessBtn.setAttribute('disabled', 'disabled');
    // } else {
    //     bulkReprocessBtn.removeAttribute('disabled');
    // }
}

/******************************
 * NETWORK ACTIONS (fetch to Django)
 ******************************/

// Load initial emails from /api/emails/
async function loadEmails() {
    renderFullListSkeleton(4);
    try {
        const res = await fetch(`/api/users/list/`);
        if (!res.ok) throw new Error('Failed to fetch users');
        const json = await res.json();
        // Expecting { emails: [...] }
        localEmails = Array.isArray(json.users) ? json.users : [];
        if (json.metrics) renderMetrics(json.metrics);
        renderList(activeFilter, searchInput.value.trim());
    } catch (e) {
        console.log(e)
        showToast('Failed loading users');
        queueEl.innerHTML = '<div style="padding:20px;color:var(--muted)">Failed to load users.</div>';
    }
}

// Scan inbox -> POST /api/scan-inbox/ (returns emails, metrics, summary)
// scanBtn.addEventListener('click', async () => {
//     scanBtn.setAttribute('disabled', 'disabled');
//     renderFullListSkeleton(4);
//     try {
//         const res = await fetch(`/api/scan-inbox/${env_id}/`, {
//             method: 'POST',
//             headers: { 'X-CSRFToken': csrftoken }
//         });
//         if (!res.ok) throw new Error('Scan failed');
//         const json = await res.json();
//         // expected shape: { emails: [...], metrics: {...}, summary: {...} }
//         if (Array.isArray(json.emails) && json.emails.length) {
//             // Prepend new emails into localEmails (assuming server sent the new items)
//             // Avoid duplicates by id
//             const ids = new Set(localEmails.map(e => e.id));
//             json.emails.forEach(e => { if (!ids.has(e.id)) localEmails.unshift(e); });
//         }
//         if (json.metrics) renderMetrics(json.metrics);
//         renderList(activeFilter, searchInput.value.trim());
//         showToast((json.emails?.length || 0) + ' new email(s) scanned and processed');
//     } catch (e) {
//         console.log(e)
//         showToast('Scan failed');
//         renderList(activeFilter, searchInput.value.trim());
//     } finally {
//         scanBtn.removeAttribute('disabled');
//     }
// });

// Reprocess single email -> POST /api/emails/:id/reprocess/
// async function handleReprocessClick(id, rowNode, btnEl) {
//     try {
//         btnEl.setAttribute('disabled', 'disabled');
//         // replace row with skeleton
//         const placeholder = document.createElement('div');
//         placeholder.style.minHeight = rowNode.offsetHeight + 'px';
//         rowNode.parentNode.replaceChild(placeholder, rowNode);
//         const skeleton = createSkeletonRowNode();
//         placeholder.appendChild(skeleton);

//         const res = await fetch(`/api/emails/${id}/reprocess/`, {
//             method: 'POST',
//             headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
//         });
//         if (!res.ok) throw new Error('Reprocess failed');
//         const json = await res.json();
//         // expecting { processed: bool, email: {...}, metrics: {...}, summary: {...} }
//         if (json.email) {
//             // update localEmails with returned email
//             const idx = localEmails.findIndex(x => x.id === json.email.id);
//             if (idx !== -1) localEmails[idx] = json.email;
//             else localEmails.unshift(json.email); // if not present add it
//         }
//         if (json.metrics) renderMetrics(json.metrics);
//         // replace placeholder with updated row
//         renderList(activeFilter, searchInput.value.trim());
//         showToast(json.processed ? 'Reprocess successful' : 'Reprocess failed');
//     } catch (e) {
//         showToast('Reprocess failed');
//         // restore row if possible
//         renderList(activeFilter, searchInput.value.trim());
//     }
// }


// Edit single user -> POST api/users/:id/edit/
async function handleAddClick(data) {
    // btnEl.setAttribute('disabled', 'disabled');
    // const placeholder = document.createElement('div');
    // placeholder.style.minHeight = rowNode.offsetHeight + 'px';
    // rowNode.parentNode.replaceChild(placeholder, rowNode);
    // const skeleton = createSkeletonRowNode();
    // placeholder.appendChild(skeleton);

    renderFullListSkeleton(4);
    

    try {
        const res = await fetch(`/api/users/add/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            throw new Error('Failed adding user')
        }
        const json = await res.json();

        if (json.renamed) {
            const u = json.upload || json.file || json.user;
            // const idx = localEmails.findIndex(x => x.id === u.id);
            // if (idx !== -1) localEmails[idx] = u;
            // else localEmails.unshift(u);
            localEmails.unshift(u);

            renderList(activeFilter, searchInput.value.trim());
            if (json.metrics) renderMetrics(json.metrics);
            showToast('User added successfully');
        } else {
            showToast('Failed adding user');
            renderList(activeFilter, searchInput.value.trim());
        }
    } catch (e) {
        console.log(e)
        showToast('Failed adding user');
        renderList(activeFilter, searchInput.value.trim());
    }
}


// Edit single user -> POST api/users/:id/edit/
async function handleRenameClick(id, rowNode, btnEl, data) {
    btnEl.setAttribute('disabled', 'disabled');
    const placeholder = document.createElement('div');
    placeholder.style.minHeight = rowNode.offsetHeight + 'px';
    rowNode.parentNode.replaceChild(placeholder, rowNode);
    const skeleton = createSkeletonRowNode();
    placeholder.appendChild(skeleton);

    try {
        const res = await fetch(`/api/users/${id}/edit/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            throw new Error('Edit failed')
        }
        const json = await res.json();

        if (json.renamed) {
            const u = json.upload || json.file || json.user;
            const idx = localEmails.findIndex(x => x.id === u.id);
            if (idx !== -1) localEmails[idx] = u;
            else localEmails.unshift(u);

            renderList(activeFilter, searchInput.value.trim());
            if (json.metrics) renderMetrics(json.metrics);
            showToast('User edited');
        } else {
            showToast('Edit failed');
            renderList(activeFilter, searchInput.value.trim());
        }
    } catch (e) {
        console.log(e)
        showToast('Edit failed');
        renderList(activeFilter, searchInput.value.trim());
    }
}

// Delete single email -> DELETE /api/emails/:id/delete/
// async function handleDeleteClick(id, rowNode, btnEl) {
//     // if (!confirm('Delete this email from queue?')) return;
//     btnEl.setAttribute('disabled', 'disabled');
//     // show skeleton placeholder
//     const placeholder = document.createElement('div');
//     placeholder.style.minHeight = rowNode.offsetHeight + 'px';
//     rowNode.parentNode.replaceChild(placeholder, rowNode);
//     const skeleton = createSkeletonRowNode();
//     placeholder.appendChild(skeleton);

//     try {
//         const res = await fetch(`/api/emails/${id}/delete/`, {
//             method: 'DELETE',
//             headers: { 'X-CSRFToken': csrftoken }
//         });
//         if (!res.ok) {
//             // try fallback POST (some servers may expect POST)
//             const fallback = await fetch(`/api/emails/${id}/delete/`, {
//                 method: 'POST',
//                 headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
//             });
//             if (!fallback.ok) throw new Error('Delete failed');
//             const fbJson = await fallback.json();
//             if (fbJson.deleted) {
//                 localEmails = localEmails.filter(x => x.id !== id);
//                 renderList(activeFilter, searchInput.value.trim());
//                 renderMetrics(fbJson.metrics);
//                 showToast('Email deleted');
//                 return;
//             } else {
//                 throw new Error('Delete failed');
//             }
//         }
//         const json = await res.json();
//         if (json.deleted) {
//             // remove locally
//             localEmails = localEmails.filter(x => x.id !== id);
//             renderList(activeFilter, searchInput.value.trim());
//             renderMetrics(json.metrics);
//             showToast('Email deleted');
//         } else {
//             showToast('Delete failed');
//             renderList(activeFilter, searchInput.value.trim());
//         }
//     } catch (e) {
//         showToast('Delete failed');
//         renderList(activeFilter, searchInput.value.trim());
//     }
// }

// Reprocess all failed -> POST /api/reprocess-failed/
// bulkReprocessBtn.addEventListener('click', async () => {
//     const failedItems = localEmails.filter(s => s.status === 'failed');
//     if (failedItems.length === 0) { showToast('No failed items to reprocess'); return; }
//     // if (!confirm(`Reprocess ${failedItems.length} failed email(s)?`)) return;

//     // replace failed rows with skeletons
//     failedItems.forEach(item => {
//         const row = queueEl.querySelector(`.row[data-id="${item.id}"]`);
//         if (row) {
//             const placeholder = document.createElement('div');
//             placeholder.style.minHeight = row.offsetHeight + 'px';
//             row.parentNode.replaceChild(placeholder, row);
//             const skeleton = createSkeletonRowNode();
//             placeholder.appendChild(skeleton);
//         }
//     });

//     bulkReprocessBtn.setAttribute('disabled', 'disabled');
//     try {
//         const res = await fetch(`/api/reprocess-failed/${env_id}/`, {
//             method: 'POST',
//             headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' }
//         });
//         if (!res.ok) throw new Error('Bulk reprocess failed');
//         const json = await res.json();
//         // expected: { results: [{ processed, email }, ...], metrics, summary }
//         console.log(json.results)
//         if (Array.isArray(json.results)) {
//             processed_count = json.results.filter(result => result.email.status === "successful").length;
//             console.log(json.results.filter(result => result.email.status === "successful"))
//             console.log(processed_count)
//             // update localEmails by replacing those email objects
//             json.results.forEach(r => {
//                 const idx = localEmails.findIndex(x => x.id === r.email.id);
//                 if (idx !== -1) localEmails[idx] = r.email;
//                 else localEmails.unshift(r.email);
//             });
//         }
//         if (json.metrics) renderMetrics(json.metrics);
//         renderList(activeFilter, searchInput.value.trim());
//         showToast(`Bulk reprocess finished for ${processed_count} email${processed_count === 1 ? "" : "s"}`);
//     } catch (e) {
//         showToast('Bulk reprocess failed');
//         renderList(activeFilter, searchInput.value.trim());
//     }
//     // } finally {
//     //     bulkReprocessBtn.removeAttribute('disabled');
//     // }
// });

// Upload files (local behaviour: POST to an endpoint if you have one; here we simply add pending)
// fileUpload.addEventListener('change', async (ev) => {
//     const files = Array.from(ev.target.files);
//     if (files.length === 0) return;
//     // Option: if you have an endpoint to upload, call it here. For now we just add to UI as pending and show toast.
//     files.forEach((f, i) => {
//         const id = Math.max(0, ...localEmails.map(s => s.id)) + i + 1;
//         localEmails.unshift({
//             id,
//             subject: `[Uploaded] ${f.name}`,
//             from: "manual.upload",
//             date: new Date().toISOString().slice(0, 16).replace('T', ' '),
//             status: 'pending',
//             sizeKb: Math.round(f.size / 1024)
//         });
//     });
//     renderList(activeFilter, searchInput.value.trim());
//     showToast(files.length + ' file(s) uploaded (mock)');
//     ev.target.value = '';
// });

// Refresh button: re-render UI (or optionally re-fetch)
refreshBtn.addEventListener('click', () => {
    // Optionally re-fetch from server: loadEmails();
    // loadEmails()
    // renderList(activeFilter, searchInput.value.trim());
    // bulkReprocessBtn.setAttribute('disabled', 'disabled');
    showToast('Refreshing...');
    loadEmails().then(() => {
        showToast('Refreshed');
    })
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


// Init: load initial emails, then optionally request metrics via scan endpoint to populate metrics
(async function init() {
    await loadEmails();
    // Optionally, request a lightweight metrics update by calling scan with n=0 (if your scan endpoint supports it)
    // Here we'll call scan with GET and ?n=0 if you want server metrics without adding new emails.
    // try {
    //     const res = await fetch('/api/scan-inbox/?n=0', { method: 'GET' });
    //     if (res.ok) {
    //         const json = await res.json();
    //         if (json.metrics) renderMetrics(json.metrics);
    //         if (json.summary) {
    //             // optionally sync counts from server summary (but keep localEmails authoritative)
    //             document.getElementById('countPending').textContent = json.summary.pending ?? document.getElementById('countPending').textContent;
    //             document.getElementById('countFailed').textContent = json.summary.failed ?? document.getElementById('countFailed').textContent;
    //             document.getElementById('countSuccess').textContent = json.summary.success ?? document.getElementById('countSuccess').textContent;
    //         }
    //     } else {
    //         // ignore silently
    //     }
    // } catch (e) {
    //     // ignore
    // }
})();

// minimal confirmation flow that supports the per-item delete-form.
// It intercepts the form submit, shows modal and only posts when confirmed.

// let pendingForm = null;
// let pendingEnvId = null;

// function confirmDelete(event, email_id, row, btnDelete) {
//     console.log(email_id)
//     showModal(email_id, row, btnDelete);
//     return false;
// }

// function showModal(email_id, row, btnDelete) {
//     const mb = document.getElementById('modalBackdrop');
//     const modaldeletebtn = document.getElementById('modalConfirm');
//     console.log(modaldeletebtn)
//     mb.style.display = 'flex';
//     modaldeletebtn.onclick = () => {
//         confirmModal(email_id, row, btnDelete);
//     }
//     // focus confirm
//     modaldeletebtn.focus();
// }

// function closeModal() {
//     const mb = document.getElementById('modalBackdrop');
//     mb.style.display = 'none';
// }

// function confirmModal(email_id, row, btnDelete) {
//     handleDeleteClick(email_id, row, btnDelete);
//     closeModal();
// }

// // close modal on ESC
// document.addEventListener('keydown', (e) => {
//     if (e.key === 'Escape') closeModal();
// });



// --------------------------
// Edit modal flow
// --------------------------
// let pendingDelete = null;
function confirmRename(email, row, btn) {
    showRenameModal(email, row, btn);
}

function showRenameModal(email, row, btn) {
    const mb = document.getElementById('modalRename');
    const modalrenamebtn = document.getElementById('modalRenameConfirm');
    const usernameinput = document.getElementById('usernameInput');
    const isactiveinput = document.getElementById('isactiveInput');
    const roleinput = document.getElementById('roleInput');

    usernameinput.value = String(email.username);
    isactiveinput.checked = email.is_active;
    roleinput.value = String(email.role);
    // usernameinput.oninput = (e) => {
    //     if (e.target.value === "") {
    //         modalrenamebtn.setAttribute("disabled", "disabled");
    //     } else {
    //         modalrenamebtn.removeAttribute("disabled");
    //     }
    // }
    mb.style.display = 'flex';
    modalrenamebtn.onclick = () => {
        handleRenameClick(email.id, row, btn, {
            // username: String(usernameinput.value),
            is_active: isactiveinput.checked,
            role: String(roleinput.value),

        });
        closeRenameModal();
    }
    modalrenamebtn.focus();
}
function closeRenameModal() { document.getElementById('modalRename').style.display = 'none'; }

// close modal on ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeRenameModal();
});



// --------------------------
// Add modal flow
// --------------------------
// let pendingDelete = null;
function confirmAdd() {
    showAddModal();
}

function showAddModal() {
    const mb = document.getElementById('modalAdd');
    const modaladdbtn = document.getElementById('modalAddConfirm');
    const usernameinput = document.getElementById('usernameInput-a');
    const passwordinput = document.getElementById('passwordInput-a');
    const confirmpasswordinput = document.getElementById('passwordconfirmInput-a');
    const isactiveinput = document.getElementById('isactiveInput-a');
    const roleinput = document.getElementById('roleInput-a');

    // usernameinput.value = String(email.username);
    // isactiveinput.checked = email.is_active;
    // roleinput.value = String(email.role);

    modaladdbtn.setAttribute("disabled", "disabled");

    usernameinput.oninput = (e) => {
        if (e.target.value === "" || passwordinput.value === "" || confirmpasswordinput.value === "" || passwordinput.value.length < 8 || passwordinput.value !== confirmpasswordinput.value) {
            modaladdbtn.setAttribute("disabled", "disabled");
        } else {
            modaladdbtn.removeAttribute("disabled");
        }
    }

    passwordinput.oninput = (e) => {
        if (e.target.value === "" || usernameinput.value === "" || confirmpasswordinput.value === "" || passwordinput.value.length < 8 || passwordinput.value !== confirmpasswordinput.value) {
            modaladdbtn.setAttribute("disabled", "disabled");
        } else {
            modaladdbtn.removeAttribute("disabled");
        }
    }

    confirmpasswordinput.oninput = (e) => {
        if (e.target.value === "" || usernameinput.value === "" || passwordinput.value === "" || passwordinput.value.length < 8 || passwordinput.value !== confirmpasswordinput.value) {
            modaladdbtn.setAttribute("disabled", "disabled");
        } else {
            modaladdbtn.removeAttribute("disabled");
        }
    }

    mb.style.display = 'flex';
    modaladdbtn.onclick = () => {
        handleAddClick({
            username: String(usernameinput.value),
            password: String(passwordinput.value),
            is_active: isactiveinput.checked,
            role: String(roleinput.value),

        });
        closeAddModal();
    }
    modaladdbtn.focus();
}

function closeAddModal() {
    document.getElementById('usernameInput-a').value = "";
    document.getElementById('passwordInput-a').value = "";
    document.getElementById('passwordInput-a').type = 'password';
    document.getElementById('passwordconfirmInput-a').type = 'password';
    document.getElementById('passwordconfirmInput-a').value = "";
    document.getElementById('isactiveInput-a').checked = true;
    document.getElementById('togglePassword').checked = false;
    document.getElementById('roleInput-a').value = "member";
    document.getElementById('modalAdd').style.display = 'none';
}

// close modal on ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAddModal();
});


const togglePassword = document.getElementById('togglePassword');
const passwordField = document.getElementById('passwordInput-a');
const confirmPasswordField = document.getElementById('passwordconfirmInput-a');

togglePassword.addEventListener('change', function () {
    const type = this.checked ? 'text' : 'password';
    passwordField.type = type;
    confirmPasswordField.type = type;
});