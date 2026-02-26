(function () {
    // Configuration: endpoints (adjust if your URLs differ)
    // const ENV_ID = '{{ environment.id }}';
    const API_URL = `/environments/${ENV_ID}/data/get/`;
    const EXPORT_URL = `/environments/${ENV_ID}/data/export/`;
    const ROW_SOURCE_URL = `/environments/${ENV_ID}/row-source-options/`;

    // UI elements
    const rowSourceSelect = document.getElementById('rowSourceSelect');
    const approvalSelect = document.getElementById('approvalSelect');
    const depthInput = document.getElementById('depthInput');
    const pageSizeInput = document.getElementById('pageSizeInput');
    const tableHead = document.getElementById('tableHead');
    const tableBody = document.getElementById('tableBody');
    const infoBar = document.getElementById('infoBar');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const pagerInfo = document.getElementById('pagerInfo');
    const refreshBtn = document.getElementById('refreshBtn');
    const exportBtn = document.getElementById('exportBtn');
    const columnsBtn = document.getElementById('columnsBtn');

    const colModal = document.getElementById('colModal');
    const colList = document.getElementById('colList');
    const colApplyBtn = document.getElementById('colApplyBtn');
    const colCancelBtn = document.getElementById('colCancelBtn');

    // State
    let columns = [];        // full schema columns
    let visibleColumns = []; // currently visible columns
    let rows = [];           // current page rows
    let page = 1;
    let totalRows = 0;
    let pageCount = 1;

    // Helpers
    function qsEncode(params) {
        return Object.entries(params)
            .filter(([k, v]) => v !== undefined && v !== null && v !== '')
            .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v))
            .join('&');
    }

    async function fetchRowSourceOptions() {
        try {
            const res = await fetch(ROW_SOURCE_URL);
            const data = await res.json();

            // console.log(data)
            // options: include Document (null) + discovered paths
            rowSourceSelect.innerHTML = '';
            // const optDoc = document.createElement('option');
            // optDoc.value = '';
            // optDoc.textContent = 'Document (one row per email)';
            // rowSourceSelect.appendChild(optDoc);

            (data.sources || []).forEach(source => {
                const o = document.createElement('option');
                o.value = source.key;
                o.textContent = source.label;
                rowSourceSelect.appendChild(o);
            });
        } catch (e) {
            console.error(e);
        }
    }

    async function fetchData() {
        infoBar.textContent = 'Loading...';
        const rowSource = rowSourceSelect.value || '';
        const approval = approvalSelect.value;
        const depth = depthInput.value;
        const pageSize = pageSizeInput.value;
        console.log("PAGE SIZE: ", pageSize);

        // visible columns param for API (CSV style) - send comma-separated
        const colsParam = visibleColumns.length ? visibleColumns.join(',') : '';

        // Build url
        const params = {
            row_source: rowSource || undefined,
            approval: approval,
            depth: depth,
            page: page,
            page_size: pageSize,
            columns: colsParam || undefined
        };

        // console.log(params)

        const url = API_URL + '?' + qsEncode(params);

        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to load');
            const data = await res.json();

            // console.log('DATA:', data)

            columns = data.all_columns || [];
            visibleColumns = visibleColumns.length ? visibleColumns : columns.slice();

            // console.log('VISIBLE COLUMNS:', visibleColumns);


            rows = data.rows || [];
            totalRows = data.meta ? data.meta.total_rows : (rows.length || 0);

            renderTable();
            renderPager(data.meta || {});
            infoBar.textContent = `Showing ${rows.length} rows (page ${page}) — total ${totalRows}`;
        } catch (e) {
            console.error(e);
            infoBar.textContent = 'Error loading data';
        }
    }

    function renderTable() {
        // header
        tableHead.innerHTML = '';
        const tr = document.createElement('tr');
        visibleColumns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            tr.appendChild(th);
        });
        tableHead.appendChild(tr);

        // body
        tableBody.innerHTML = '';
        rows.forEach(row => {
            const tr = document.createElement('tr');
            visibleColumns.forEach(col => {
                // console.log('TD COL: ', col);
                const td = document.createElement('td');
                let val = row[col];
                if (val === null || val === undefined) val = '';
                else if (typeof val === 'object') val = JSON.stringify(val);

                // --- WRAP the row in an anchor tag as requested ---
                if ((col === "Email ID" || col === "Upload ID") && String(val) !== "") {
                    const link = document.createElement('a');
                    link.className = 'row-link';
                    let url = "";
                    if (col === "Email ID") {
                        url = `/environments/envmail/${String(val)}/data/review`
                    } else {
                        url = `/environments/envupload/${String(val)}/data/review`
                    }
                    link.href = url;
                    link.textContent = String(val);
                    td.appendChild(link);
                } else {
                    td.textContent = String(val);
                }
                // End

                // td.textContent = String(val);
                tr.appendChild(td);
            });
            // console.log("ROW: ", row['Email ID'])
            tableBody.appendChild(tr);
        });
    }

    function renderPager(meta) {
        let pageSize = Number(pageSizeInput.value);
        console.log("SIZE: ", pageSize);

        if (pageSize < 1) {
            pageSize = 1;
            pageSizeInput.value = 1;
        }

        const total = meta.total_rows || totalRows;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        pageCount = totalPages;
        console.log("CT: ", pageCount);
        if (page === pageCount) {
            nextBtn.setAttribute("disabled", "disabled");
        } else {
            nextBtn.removeAttribute("disabled");
        }
        pagerInfo.textContent = `Page ${page} of ${totalPages} — ${total} total rows`;
    }

    // Column modal
    function openColumnModal() {
        colList.innerHTML = '';
        // console.log(columns)
        columns.forEach(c => {
            const id = 'col_' + c.replace(/[^a-z0-9]/gi, '_');
            const div = document.createElement('div');
            div.innerHTML = `<label><input type="checkbox" id="${id}" data-col="${c}" ${visibleColumns.includes(c) ? 'checked' : ''}/> ${c}</label>`;
            colList.appendChild(div);
        });
        colModal.style.display = 'flex';
    }

    function applyColumnChanges() {
        const checks = Array.from(colList.querySelectorAll('input[type=checkbox]'));
        visibleColumns = checks.filter(ch => ch.checked).map(ch => ch.dataset.col);
        colModal.style.display = 'none';
        // reload data with new columns
        page = 1;
        fetchData();
    }

    // Export (ignores pagination)
    function exportCsv() {
        const rowSource = rowSourceSelect.value || '';
        const depth = depthInput.value;
        const colsParam = visibleColumns.length ? visibleColumns.join(',') : '';
        const params = {
            row_source: rowSource || undefined,
            depth: depth,
            columns: colsParam || undefined
        };
        const url = EXPORT_URL + '?' + qsEncode(params);
        // navigate browser to download
        window.location = url;
    }

    // Event wiring
    prevBtn.setAttribute("disabled", "disabled");
    nextBtn.setAttribute("disabled", "disabled");

    prevBtn.addEventListener('click', () => {
        if (page > 1) {
            page--;
            fetchData();
        }
        if (page === 1) {
            prevBtn.setAttribute("disabled", "disabled");
        }
    });
    nextBtn.addEventListener('click', () => {
        page++;
        fetchData();
        prevBtn.removeAttribute("disabled");
        if (page === pageCount) {
            nextBtn.setAttribute("disabled", "disabled");
        }
    });
    refreshBtn.addEventListener('click', () => { page = 1; fetchData(); });
    exportBtn.addEventListener('click', exportCsv);
    columnsBtn.addEventListener('click', openColumnModal);
    colApplyBtn.addEventListener('click', applyColumnChanges);
    colCancelBtn.addEventListener('click', () => { colModal.style.display = 'none' });

    // Change handlers
    rowSourceSelect.addEventListener('change', () => { page = 1; visibleColumns = []; fetchData(); });
    approvalSelect.addEventListener('change', () => { page = 1; fetchData(); });
    depthInput.addEventListener('change', () => { page = 1; visibleColumns = []; fetchData(); });
    pageSizeInput.addEventListener('change', () => { page = 1; fetchData(); });

    // Initial load
    (async function init() {
        await fetchRowSourceOptions();
        await fetchData();
    })();

})();
