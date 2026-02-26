/* =========================
    UI State + Helpers (connected to Django)
    ========================= */

const API_BASE = '/api/audit-logs/';

let availableFilters = null; // { users: [{id,username}], actions:[], target_types:[] }

let state = {
    page: 1,
    pageSize: 50,
    filters: { users: [], actions: [], targetTypes: [] }, // users -> array of user ids (strings or numbers)
    search: ''
};

const tableWrap = document.getElementById('tableWrap');
const pager = document.getElementById('pager');
const toast = document.getElementById('toast');

// filter modal refs
const usersBackdrop = document.getElementById('usersBackdrop');
const usersList = document.getElementById('usersList');
const actionsBackdrop = document.getElementById('actionsBackdrop');
const actionsList = document.getElementById('actionsList');
const targetsBackdrop = document.getElementById('targetsBackdrop');
const targetsList = document.getElementById('targetsList');

const usersCount = document.getElementById('usersCount');
const actionsCount = document.getElementById('actionsCount');
const targetsCount = document.getElementById('targetsCount');

const searchInput = document.getElementById('searchInput');
const refreshBtn = document.getElementById('refreshBtn');

// details modal
const detailsBackdrop = document.getElementById('detailsBackdrop');
const detailsSummary = document.getElementById('detailsSummary');
const detailsMeta = document.getElementById('detailsMeta');
const rawJsonContainer = document.getElementById('rawJsonContainer');
const showRaw = document.getElementById('showRaw');

function showToast(msg) {
    toast.textContent = msg;
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateY(20px)'; }, 2600);
}

function formatDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

/* =========================
   Rendering (table, skeleton, pager)
   ========================= */

function renderSkeleton(rows = 6) {
    tableWrap.innerHTML = '';
    for (let i = 0; i < rows; i++) {
        const s = document.createElement('div');
        s.className = 'skeleton-row';
        s.innerHTML = `<div class="skeleton skeleton-line" style="width:120px"></div>
                   <div class="skeleton skeleton-line" style="width:90px"></div>
                   <div class="skeleton skeleton-line" style="width:100%"></div>
                   <div class="skeleton skeleton-line" style="width:120px"></div>
                   <div class="skeleton skeleton-line" style="width:90px"></div>`;
        tableWrap.appendChild(s);
    }
}

function renderTable(logs, total, page, pageSize) {
    tableWrap.innerHTML = '';

    const table = document.createElement('table');
    table.className = 'table';
    table.innerHTML = `
    <thead>
      <tr>
        <th style="width:220px">ACTOR</th>
        <th style="width:160px">ACTION</th>
        <th>TARGET</th>
        <th style="width:140px">TARGET TYPE</th>
        <th style="width:120px">DATE</th>
        <th style="width:120px"></th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
    const tbody = table.querySelector('tbody');

    logs.forEach(log => {
        const tr = document.createElement('tr');

        // Actor column: name + role below
        const tdActor = document.createElement('td');
        const actorWrap = document.createElement('div');
        actorWrap.className = 'actor';
        const nameEl = document.createElement('div');
        nameEl.className = 'name';
        nameEl.textContent = log.user?.username || 'System';
        const roleEl = document.createElement('div');
        roleEl.className = 'role';
        roleEl.textContent = log.user?.role ? log.user.role.replace(/_/g, ' ') : '';
        actorWrap.appendChild(nameEl);
        actorWrap.appendChild(roleEl);
        tdActor.appendChild(actorWrap);

        // Action
        const tdAction = document.createElement('td');
        tdAction.innerHTML = `<div class="action">${escapeHtml(capitalize(log.action))}</div>`;

        // Target
        const tdTarget = document.createElement('td');
        tdTarget.innerHTML = `<div>${escapeHtml(log.target)}</div>`;

        // Target type
        const tdTargetType = document.createElement('td');
        tdTargetType.innerHTML = `<div class="target-type">${escapeHtml(capitalize(log.target_type))}</div>`;

        // Date & details button
        // const tdDate = document.createElement('td');
        // tdDate.innerHTML = `<div class="meta-time">
        // ${formatDate(log.created_at)}</div>
        // <div style="margin-top:6px">
        // <button class="details-btn" data-id="${log.id}">View</button>
        // </div>`;

        const tdDate = document.createElement('td');
        tdDate.innerHTML = `<div class="meta-time">${formatDate(log.created_at)}</div>`;

        // View button
        const tdViewButton = document.createElement('td');
        tdViewButton.innerHTML = `<button class="details-btn" data-id="${log.id}">View</button>`;


        tr.appendChild(tdActor);
        tr.appendChild(tdAction);
        tr.appendChild(tdTarget);
        tr.appendChild(tdTargetType);
        tr.appendChild(tdDate);
        tr.appendChild(tdViewButton);

        tbody.appendChild(tr);

        // attach view handler
        tr.querySelector('.details-btn').addEventListener('click', () => openDetails(log));
    });

    tableWrap.appendChild(table);

    // pager
    renderPager(total, page, pageSize);
}

function renderPager(total, page, pageSize) {
    pager.innerHTML = '';
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const prev = document.createElement('button');
    prev.textContent = 'Prev';
    prev.className = 'page-btn';
    prev.disabled = page <= 1;
    prev.addEventListener('click', () => { state.page--; fetchAndRender(); });
    pager.appendChild(prev);

    // show a range of page numbers (compact)
    const start = Math.max(1, page - 3);
    const end = Math.min(pages, page + 3);
    if (start > 1) {
        addPageBtn(1);
        if (start > 2) pager.appendChild(createEllipsis());
    }
    for (let p = start; p <= end; p++) addPageBtn(p);
    if (end < pages) {
        if (end < pages - 1) pager.appendChild(createEllipsis());
        addPageBtn(pages);
    }

    const next = document.createElement('button');
    next.textContent = 'Next';
    next.className = 'page-btn';
    next.disabled = page >= pages;
    next.addEventListener('click', () => { state.page++; fetchAndRender(); });
    pager.appendChild(next);

    function addPageBtn(p) {
        const b = document.createElement('button');
        b.textContent = p;
        b.className = 'page-btn';
        if (p === page) b.style.fontWeight = '700';
        b.addEventListener('click', () => { state.page = p; fetchAndRender(); });
        pager.appendChild(b);
    }
    function createEllipsis() {
        const s = document.createElement('span'); s.textContent = '…'; s.style.padding = '0 8px'; s.style.color = 'var(--muted)'; return s;
    }
}

/* =========================
   Filters UI
   ========================= */

document.getElementById('filterUsersBtn').addEventListener('click', async () => {
    if (availableFilters) {
        populateFilterList('users', availableFilters.users, state.filters.users);
        usersBackdrop.style.display = 'flex';
        return;
    }
    usersList.innerHTML = '<div class="small">Loading…</div>';
    usersBackdrop.style.display = 'flex';
    try {
        // request page=1 so backend returns available_filters
        const res = await fetch(`${API_BASE}?page=1&page_size=1`);
        const json = await res.json();
        availableFilters = json.available_filters;
        populateFilterList('users', availableFilters.users, state.filters.users);
    } catch (e) {
        usersList.innerHTML = '<div class="small" style="color:var(--danger)">Failed to load filter values</div>';
    }
});

document.getElementById('filterActionsBtn').addEventListener('click', async () => {
    if (availableFilters) {
        populateFilterList('actions', availableFilters.actions, state.filters.actions);
        actionsBackdrop.style.display = 'flex';
        return;
    }
    actionsList.innerHTML = '<div class="small">Loading…</div>';
    actionsBackdrop.style.display = 'flex';
    try {
        const res = await fetch(`${API_BASE}?page=1&page_size=1`);
        const json = await res.json();
        availableFilters = json.available_filters;
        populateFilterList('actions', availableFilters.actions, state.filters.actions);
    } catch (e) {
        actionsList.innerHTML = '<div class="small" style="color:var(--danger)">Failed to load filter values</div>';
    }
});

document.getElementById('filterTargetsBtn').addEventListener('click', async () => {
    if (availableFilters) {
        populateFilterList('targets', availableFilters.target_types, state.filters.targetTypes);
        targetsBackdrop.style.display = 'flex';
        return;
    }
    targetsList.innerHTML = '<div class="small">Loading…</div>';
    targetsBackdrop.style.display = 'flex';
    try {
        const res = await fetch(`${API_BASE}?page=1&page_size=1`);
        const json = await res.json();
        availableFilters = json.available_filters;
        populateFilterList('targets', availableFilters.target_types, state.filters.targetTypes);
    } catch (e) {
        targetsList.innerHTML = '<div class="small" style="color:var(--danger)">Failed to load filter values</div>';
    }
});

function populateFilterList(kind, items, selected) {
    const container = kind === 'users' ? usersList : kind === 'actions' ? actionsList : targetsList;
    container.innerHTML = '';

    if (!items || items.length === 0) {
        container.innerHTML = '<div class="small">No options</div>';
        return;
    }

    if (kind === 'users') {
        // items are objects {id, username}
        items.forEach(it => {
            const id = `users-${it.id}`;
            const div = document.createElement('div');
            div.className = 'filter-item';
            div.innerHTML = `<label style="display:flex;gap:8px;align-items:center">
         <input type="checkbox" data-value="${escapeHtml(String(it.id))}" id="${id}"> <span>${escapeHtml(it.username)}</span>
       </label>`;
            container.appendChild(div);
            const chk = div.querySelector('input');
            if (selected && selected.map(String).includes(String(it.id))) chk.checked = true;
            div.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') chk.checked = !chk.checked;
            });
        });
        return;
    }

    // actions and target types: array of strings
    items.forEach(it => {
        const safe = String(it);
        const id = `${kind}-${safe}`;
        const div = document.createElement('div');
        div.className = 'filter-item';
        div.innerHTML = `<label style="display:flex;gap:8px;align-items:center">
      <input type="checkbox" data-value="${escapeHtml(safe)}" id="${id}"> <span>${escapeHtml(safe)}</span>
    </label>`;
        container.appendChild(div);
        const chk = div.querySelector('input');
        if (selected && selected.includes(safe)) chk.checked = true;
        div.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT') chk.checked = !chk.checked;
        });
    });
}

function closeFilter(kind) {
    if (kind === 'users') usersBackdrop.style.display = 'none';
    if (kind === 'actions') actionsBackdrop.style.display = 'none';
    if (kind === 'targets') targetsBackdrop.style.display = 'none';
}

function applyFilter(kind) {
    const container = kind === 'users' ? usersList : kind === 'actions' ? actionsList : targetsList;
    const checks = Array.from(container.querySelectorAll('input[type=checkbox]')).filter(c => c.checked).map(c => {
        return c.dataset.value;
    });

    if (kind === 'users') state.filters.users = checks;               // array of ids
    if (kind === 'actions') state.filters.actions = checks;           // array of names
    if (kind === 'targets') state.filters.targetTypes = checks;       // array of names

    usersCount.style.display = state.filters.users.length ? 'inline-block' : 'none';
    usersCount.textContent = state.filters.users.length;
    actionsCount.style.display = state.filters.actions.length ? 'inline-block' : 'none';
    actionsCount.textContent = state.filters.actions.length;
    targetsCount.style.display = state.filters.targetTypes.length ? 'inline-block' : 'none';
    targetsCount.textContent = state.filters.targetTypes.length;

    // Reset to page 1
    state.page = 1;
    showToast('Filter applied');
    fetchAndRender();

    closeFilter(kind);
}

/* =========================
   Details modal + metadata rendering
   ========================= */

function openDetails(log) {
    detailsBackdrop.style.display = 'flex';
    // summary area
    detailsSummary.innerHTML = '';
    const actorKv = createKv('Actor', (log.user?.username || 'System') + (log.user?.role ? ` — ${capitalize(log.user.role)}` : ''));
    const actionKv = createKv('Action', capitalize(log.action));
    const targetKv = createKv('Target', `${capitalize(log.target_type)} — ${log.target}`);
    const dateKv = createKv('When', formatDate(log.created_at));
    detailsSummary.appendChild(actorKv);
    detailsSummary.appendChild(actionKv);
    detailsSummary.appendChild(targetKv);
    detailsSummary.appendChild(dateKv);

    // metadata rendering (if any)
    detailsMeta.innerHTML = '';
    if (log.metadata && Object.keys(log.metadata).length) {
        renderMetadataInto(log.metadata, detailsMeta);
    } else {
        const no = document.createElement('div'); no.className = 'small'; no.textContent = 'No additional details.'; detailsMeta.appendChild(no);
    }

    // raw JSON
    rawJsonContainer.style.display = 'none';
    rawJsonContainer.innerHTML = `<div class="raw-json">${escapeHtml(JSON.stringify(log, null, 2))}</div>`;
    showRaw.checked = false;
}

showRaw.addEventListener('change', () => {
    rawJsonContainer.style.display = showRaw.checked ? 'block' : 'none';
});

/* helper to build two-column kv */
function createKv(k, v) {
    const wrap = document.createElement('div'); wrap.className = 'kv';
    const ek = document.createElement('div'); ek.className = 'k'; ek.textContent = k;
    const ev = document.createElement('div'); ev.className = 'v'; ev.textContent = v;
    wrap.appendChild(ek); wrap.appendChild(ev);
    return wrap;
}

/* Render metadata generically:
   - arrays of primitives -> comma separated
   - nested objects -> recursive node structure (indented)
*/
function renderMetadataInto(metadata, container) {
    Object.keys(metadata).forEach(key => {
        const val = metadata[key];
        const row = document.createElement('div');
        row.className = 'meta-row';
        const k = document.createElement('div'); k.className = 'meta-key'; k.textContent = humanizeKey(key);
        const v = document.createElement('div'); v.className = 'meta-val';
        if (Array.isArray(val) && val.every(x => (typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean'))) {
            v.textContent = val.join(', ');
        } else if (Array.isArray(val)) {
            v.innerHTML = val.map(it => escapeHtml(JSON.stringify(it))).join('<br>');
        } else if (val && typeof val === 'object') {
            v.appendChild(renderNestedObject(val));
        } else {
            v.textContent = String(val);
        }
        row.appendChild(k); row.appendChild(v);
        container.appendChild(row);
    });
}

function renderNestedObject(obj) {
    const wrap = document.createElement('div');
    wrap.style.marginLeft = '6px';
    wrap.style.borderLeft = '2px dashed #eef6ff';
    wrap.style.paddingLeft = '10px';
    Object.keys(obj).forEach(k => {
        const val = obj[k];
        const row = document.createElement('div');
        row.style.marginBottom = '6px';
        const keySpan = document.createElement('strong'); keySpan.textContent = humanizeKey(k) + ': ';
        const valSpan = document.createElement('span');
        if (Array.isArray(val) && val.every(x => (typeof x === 'string' || typeof x === 'number' || typeof x === 'boolean'))) {
            valSpan.textContent = val.join(', ');
        } else if (Array.isArray(val)) {
            valSpan.textContent = val.map(it => JSON.stringify(it)).join(', ');
        } else if (val && typeof val === 'object') {
            valSpan.appendChild(renderNestedObject(val));
        } else {
            valSpan.textContent = String(val);
        }
        row.appendChild(keySpan);
        row.appendChild(valSpan);
        wrap.appendChild(row);
    });
    return wrap;
}

/* =========================
   Fetch + render flow (real API)
   ========================= */

let currentFetchToken = 0;
let loading = false;

async function fetchAndRender() {
    const token = ++currentFetchToken;
    renderSkeleton(5);
    try {
        // Build query params (users/actions/target_types are comma-joined)
        const params = new URLSearchParams({
            page: state.page,
            page_size: state.pageSize,
            search: state.search || "",
            users: state.filters.users.join(","),
            actions: state.filters.actions.join(","),
            target_types: state.filters.targetTypes.join(","),
        });
        const res = await fetch(`${API_BASE}?${params.toString()}`);
        if (!res.ok) throw new Error('Failed to fetch logs');
        const data = await res.json();

        if (token !== currentFetchToken) return; // stale

        // cache available filters (so modals open instantly later)
        if (data.available_filters) {
            availableFilters = {
                users: data.available_filters.users || [],
                actions: data.available_filters.actions || [],
                target_types: data.available_filters.target_types || []
            };
        }

        renderTable(data.results || [], data.pagination?.total_count || 0, data.pagination?.page || 1, data.pagination?.page_size || state.pageSize);
    } catch (e) {
        tableWrap.innerHTML = '<div style="padding:18px;color:var(--muted)">Failed to load logs.</div>';
    }
}

refreshBtn.addEventListener('click', () => {
    showToast('Refreshing...');
    fetchAndRender().then(() => {
        showToast('Refreshed');
    });
});

// search with debounce; reset page to 1
let searchTimer = null;
searchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        state.search = e.target.value;
        state.page = 1;         // reset page when search changes
        fetchAndRender();
    }, 350);
});

/* =========================
   Helpers + escape
   ========================= */

function escapeHtml(s) { return String(s || '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]); }
function capitalize(s) { return String(s || '').replace(/_/g, ' ').replace(/\b\w/g, m => m.toUpperCase()); }
function humanizeKey(k) { return String(k || '').replace(/_/g, ' ').replace(/\b\w/g, m => m.toUpperCase()); }

/* =========================
   Details modal helpers
   ========================= */

function closeDetails() { detailsBackdrop.style.display = 'none'; detailsMeta.innerHTML = ''; detailsSummary.innerHTML = ''; rawJsonContainer.innerHTML = ''; }

/* close filter modals on backdrop click / ESC */
document.addEventListener('click', (e) => {
    if (e.target === usersBackdrop) usersBackdrop.style.display = 'none';
    if (e.target === actionsBackdrop) actionsBackdrop.style.display = 'none';
    if (e.target === targetsBackdrop) targetsBackdrop.style.display = 'none';
    if (e.target === detailsBackdrop) closeDetails();
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { usersBackdrop.style.display = 'none'; actionsBackdrop.style.display = 'none'; targetsBackdrop.style.display = 'none'; closeDetails(); } });

/* =========================
   Init
   ========================= */

(function init() {
    fetchAndRender();
})();