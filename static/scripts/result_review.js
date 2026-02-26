/* ----------------------------
   File Previewer (left panel)
   All code wrapped in an IIFE to avoid globals.
   ---------------------------- */
(function () {
    // const filePicker = document.getElementById('filePicker');
    // const previewUrlsBtn = document.getElementById('previewUrlsBtn');
    const urlList = document.getElementById('urlList');
    const cards = document.getElementById('cards');
    // const clearBtn = document.getElementById('clearBtn');

    const PDF_SCALE_STEP = 1.2; // zoom multiplier
    const PDF_MIN_SCALE = 0.2;
    const PDF_MAX_SCALE = 4;
    const IMG_MIN_SCALE = 0.1;
    const IMG_MAX_SCALE = 4;
    const TEXT_MIN_SIZE = 8;
    const TEXT_MAX_SIZE = 40;

    function niceBytes(n) {
        if (n == null) return '';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let i = 0;
        while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
        return n.toFixed(n >= 100 ? 0 : 2) + ' ' + units[i];
    }

    // clearBtn.addEventListener('click', () => cards.innerHTML = '');

    // filePicker.addEventListener('change', (e) => {
    //     const files = Array.from(e.target.files || []);
    //     if (!files.length) return;
    //     files.forEach(f => createCardFromFile(f));
    //     e.target.value = '';
    // });

    // const previewURLs = async () => {
    //     const raw = (urlList.value || '').trim();
    //     if (!raw) return alert('Paste one or more file URLs (one per line, or separated by commas/semicolons).');
    //     const parts = raw.split(/\s*(?:\r?\n|,|;)\s*/).map(s => s.trim()).filter(Boolean);
    //     for (const url of parts) {
    //         await createCardFromURL(url);
    //     }
    // }

    async function previewURLs() {
        const raw = (urlList.value || '').trim();
        // if (!raw) return alert('Paste one or more file URLs (one per line, or separated by commas/semicolons).');
        if (!raw) return;;
        const parts = raw.split(/\s*(?:\r?\n|,|;)\s*/).map(s => s.trim()).filter(Boolean);
        for (const url of parts) {
            await createCardFromURL(url);
        }
    }

    // previewUrlsBtn.addEventListener('click', async () => {
    //     const raw = (urlList.value || '').trim();
    //     if (!raw) return alert('Paste one or more file URLs (one per line, or separated by commas/semicolons).');
    //     const parts = raw.split(/\s*(?:\r?\n|,|;)\s*/).map(s => s.trim()).filter(Boolean);
    //     for (const url of parts) {
    //         await createCardFromURL(url);
    //     }
    // });

    function makeCard(title) {
        const card = document.createElement('div'); card.className = 'card';
        const head = document.createElement('div'); head.className = 'card-head';
        const left = document.createElement('div'); left.className = 'card-left';
        left.innerHTML = `<div class="card-title">${escapeHtml(title)}</div><div class="card-meta"></div>`;
        // left.innerHTML = `<div class="card-meta"></div>`;
        const right = document.createElement('div'); right.className = 'card-controls';
        head.appendChild(left); head.appendChild(right);
        const previewArea = document.createElement('div'); previewArea.className = 'preview-area';
        card.appendChild(head); card.appendChild(previewArea);
        cards.prepend(card);
        return { card, head, left, right, previewArea, meta: left.querySelector('.card-meta') };
    }

    function escapeHtml(s) { return (s + '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }

    // function createCardFromFile(file) {
    //     const { right, previewArea, meta } = makeCard(file.name || 'file');
    //     meta.textContent = `${file.type || 'unknown'} • ${niceBytes(file.size)}`;
    //     const downloadA = document.createElement('a');
    //     downloadA.href = URL.createObjectURL(file);
    //     downloadA.download = file.name;
    //     downloadA.textContent = 'Download';
    //     downloadA.className = 'download';
    //     right.appendChild(downloadA);

    //     const lower = (file.name || '').toLowerCase();
    //     if ((file.type || '').startsWith('image/') || /\.(jpe?g|png|gif|webp|bmp|svg)$/i.test(lower)) {
    //         renderImageFile(file, previewArea, right, meta);
    //     } else if ((file.type || '').includes('pdf') || /\.pdf$/i.test(lower)) {
    //         renderPdfFile(file, previewArea, right, meta, file.name);
    //     } else if ((file.type || '').startsWith('text/') || /\.txt$/i.test(lower)) {
    //         renderTextFile(file, previewArea, right, meta, file.name);
    //     } else if ((file.type || '').includes('csv') || /\.csv$/i.test(lower)) {
    //         renderCsvFile(file, previewArea, right, meta, file.name);
    //     } else {
    //         previewArea.innerHTML = `<div class="muted">Unsupported file type. You can download it instead.</div>`;
    //     }
    // }

    async function createCardFromURL(url) {
        const { right, previewArea, meta } = makeCard(url);
        meta.textContent = `remote URL`;
        // const downloadA = document.createElement('a');
        // downloadA.textContent = 'Download';
        // downloadA.className = 'download';
        // downloadA.download = 'attachment';
        // downloadA.classList.add('btn-small')
        // right.appendChild(downloadA);

        previewArea.textContent = 'Fetching… (CORS must allow cross-origin requests)';
        try {
            const resp = await fetch(url, { mode: 'cors' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const contentType = (resp.headers.get('Content-Type') || '').toLowerCase();
            const ab = await resp.arrayBuffer();
            const blob = new Blob([ab], { type: (contentType || undefined) });

            const downloadA = document.createElement('a');
            downloadA.textContent = 'Download';
            downloadA.className = 'download';
            downloadA.download = 'attachment';
            downloadA.classList.add('btn-small')
            right.appendChild(downloadA);
            
            downloadA.href = URL.createObjectURL(blob);

            if (contentType.startsWith('image/') || /\.(jpe?g|png|gif|webp|bmp|svg)$/i.test(url)) {
                renderImageBlob(blob, previewArea, right, meta, url);
            } else if (contentType.includes('pdf') || /\.pdf$/i.test(url)) {
                renderPdfBlob(blob, previewArea, right, meta, url);
            } else if (contentType.includes('csv') || /\.csv$/i.test(url)) {
                const text = new TextDecoder().decode(ab);
                displayCsvTextLocal(text, previewArea, right, meta, url);
            } else if (contentType.startsWith('text/') || /\.txt$/i.test(url)) {
                const text = new TextDecoder().decode(ab);
                displayText(text, previewArea, right, meta, url);
            } else {
                previewArea.innerHTML = `<div class="muted">Unsupported or unknown file type (${escapeHtml(contentType)}). You can download it.</div>`;
            }
        } catch (err) {
            previewArea.innerHTML = `<div class="muted" style="color:var(--danger)">Failed to fetch URL: ${escapeHtml(err.message)}. CORS or network error.</div>`;
            console.warn('fetch failed', err);
        }
    }

    // IMAGE
    // function renderImageFile(file, previewArea, right, meta, name) {
    //     const url = URL.createObjectURL(file);
    //     renderImageFromUrl(url, previewArea, right, meta, name || file.name);
    // }
    function renderImageBlob(blob, previewArea, right, meta, filename) {
        const url = URL.createObjectURL(blob);
        renderImageFromUrl(url, previewArea, right, meta, filename);
    }
    function renderImageFromUrl(url, previewArea, right, meta, filename) {
        previewArea.innerHTML = '';
        const wrap = document.createElement('div'); wrap.className = 'img-wrap';
        const img = document.createElement('img'); img.src = url; img.alt = filename || 'image';
        img.style.maxWidth = '100%';
        wrap.appendChild(img);
        previewArea.appendChild(wrap);

        let scale = 1;
        let isFit = true;

        img.addEventListener('load', () => {
            if (isFit) img.style.removeProperty('width');
            else { img.style.maxWidth = 'none'; img.style.width = Math.round(img.naturalWidth * scale) + 'px'; }
            meta.textContent = `image • ${img.naturalWidth}×${img.naturalHeight} • ${isFit ? 'fit' : 'scale ' + scale.toFixed(2)}`;
        });

        const zoomInBtn = makeBtn('Zoom +', () => {
            isFit = false; scale *= PDF_SCALE_STEP; if (scale > IMG_MAX_SCALE) scale = IMG_MAX_SCALE; updateImageZoom();
        });
        const zoomOutBtn = makeBtn('Zoom −', () => {
            isFit = false; scale /= PDF_SCALE_STEP; if (scale < IMG_MIN_SCALE) scale = IMG_MIN_SCALE; updateImageZoom();
        });
        const fitBtn = makeBtn('Fit', () => {
            isFit = true; scale = 1; img.style.removeProperty('width'); img.style.maxWidth = '100%'; img.style.transform = ''; updateImageButtons(); meta.textContent = `image • ${img.naturalWidth}×${img.naturalHeight} • fit`;
        });

        right.appendChild(zoomOutBtn); right.appendChild(zoomInBtn); right.appendChild(fitBtn);

        function updateImageZoom() {
            if (img.naturalWidth) { img.style.maxWidth = 'none'; img.style.width = Math.round(img.naturalWidth * scale) + 'px'; }
            else img.style.transform = `scale(${scale})`;
            isFit = false;
            meta.textContent = `image • ${img.naturalWidth || 'unknown'}×${img.naturalHeight || 'unknown'} • scale ${scale.toFixed(2)}`;
            updateImageButtons();
        }
        function updateImageButtons() { zoomInBtn.disabled = scale >= IMG_MAX_SCALE - 1e-6; zoomOutBtn.disabled = scale <= IMG_MIN_SCALE + 1e-6; }
        updateImageButtons();
    }

    // PDF
    // function renderPdfFile(file, previewArea, right, meta, filename) {
    //     file.arrayBuffer().then(ab => renderPdfFromArrayBuffer(ab, previewArea, right, meta, filename));
    // }
    function renderPdfBlob(blob, previewArea, right, meta, filename) {
        blob.arrayBuffer().then(ab => renderPdfFromArrayBuffer(ab, previewArea, right, meta, filename));
    }

    async function renderPdfFromArrayBuffer(arrayBuffer, previewArea, right, meta, filename) {
        previewArea.innerHTML = 'Loading PDF…';
        try {
            const pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
            let currentPage = 1;
            let scale = 1.2;

            previewArea.innerHTML = '';
            const canvas = document.createElement('canvas');
            const canvasWrap = document.createElement('div'); canvasWrap.style.textAlign = 'center';
            canvasWrap.appendChild(canvas);
            previewArea.appendChild(canvasWrap);

            const info = document.createElement('div'); info.className = 'muted'; info.style.marginTop = '6px';
            previewArea.appendChild(info);

            const btnPrev = makeBtn('◀ Prev', () => { if (currentPage > 1) { currentPage--; renderPage(); } });
            const btnNext = makeBtn('Next ▶', () => { if (currentPage < pdfDoc.numPages) { currentPage++; renderPage(); } });
            const btnZoomIn = makeBtn('Zoom +', () => { scale *= PDF_SCALE_STEP; if (scale > PDF_MAX_SCALE) scale = PDF_MAX_SCALE; renderPage(); });
            const btnZoomOut = makeBtn('Zoom −', () => { scale /= PDF_SCALE_STEP; if (scale < PDF_MIN_SCALE) scale = PDF_MIN_SCALE; renderPage(); });
            const btnFit = makeBtn('Fit Width', () => {
                (async () => {
                    const page = await pdfDoc.getPage(currentPage);
                    const vp1 = page.getViewport({ scale: 1 });
                    const containerWidth = Math.max(320, previewArea.clientWidth - 20);
                    const newScale = containerWidth / vp1.width;
                    scale = Math.max(PDF_MIN_SCALE, Math.min(PDF_MAX_SCALE, newScale));
                    renderPage();
                })();
            });

            right.appendChild(btnPrev); right.appendChild(btnNext);
            right.appendChild(btnZoomOut); right.appendChild(btnZoomIn); right.appendChild(btnFit);

            async function renderPage() {
                info.textContent = `Rendering page ${currentPage} / ${pdfDoc.numPages} …`;
                try {
                    const page = await pdfDoc.getPage(currentPage);
                    const viewport = page.getViewport({ scale });
                    const context = canvas.getContext('2d');

                    canvas.width = Math.ceil(viewport.width);
                    canvas.height = Math.ceil(viewport.height);

                    context.clearRect(0, 0, canvas.width, canvas.height);
                    await page.render({ canvasContext: context, viewport }).promise;

                    canvas.style.width = canvas.width + 'px';
                    canvas.style.height = canvas.height + 'px';

                    meta.textContent = `${filename || 'PDF'} • Page ${currentPage}/${pdfDoc.numPages} • scale ${scale.toFixed(2)}`;
                    info.textContent = `Page ${currentPage} / ${pdfDoc.numPages} • scale ${scale.toFixed(2)}`;

                    btnPrev.disabled = currentPage <= 1;
                    btnNext.disabled = currentPage >= pdfDoc.numPages;
                    btnZoomIn.disabled = scale >= PDF_MAX_SCALE - 1e-6;
                    btnZoomOut.disabled = scale <= PDF_MIN_SCALE + 1e-6;
                } catch (err) {
                    previewArea.innerHTML = `<div class="muted" style="color:var(--danger)">Failed to render PDF page: ${escapeHtml(err.message)}</div>`;
                    console.error(err);
                }
            }

            await renderPage();
        } catch (err) {
            previewArea.innerHTML = `<div class="muted" style="color:var(--danger)">Failed to render PDF: ${escapeHtml(err.message)}</div>`;
            console.error(err);
        }
    }

    // Text
    // function renderTextFile(file, previewArea, right, meta, filename) {
    //     const reader = new FileReader();
    //     reader.onload = e => displayText(e.target.result, previewArea, right, meta, filename);
    //     reader.onerror = () => previewArea.innerHTML = `<div class="muted" style="color:var(--danger)">Failed to read text file.</div>`;
    //     reader.readAsText(file);
    // }

    function displayText(text, previewArea, right, meta, filename) {
        previewArea.innerHTML = '';
        const pre = document.createElement('pre'); pre.className = 'preview-pre'; pre.textContent = text; pre.style.fontSize = '13px';
        previewArea.appendChild(pre);
        let size = 13;
        const inc = makeBtn('A+', () => { size = Math.min(TEXT_MAX_SIZE, size + 2); pre.style.fontSize = size + 'px'; updateButtons(); meta.textContent = `${filename || 'text'} • font ${size}px`; });
        const dec = makeBtn('A−', () => { size = Math.max(TEXT_MIN_SIZE, size - 2); pre.style.fontSize = size + 'px'; updateButtons(); meta.textContent = `${filename || 'text'} • font ${size}px`; });
        right.appendChild(dec); right.appendChild(inc);
        function updateButtons() { inc.disabled = size >= TEXT_MAX_SIZE; dec.disabled = size <= TEXT_MIN_SIZE; }
        updateButtons();
        meta.textContent = `${filename || 'text'} • font ${size}px`;
    }

    // CSV
    // function renderCsvFile(file, previewArea, right, meta, filename) {
    //     const reader = new FileReader();
    //     reader.onload = e => displayCsvTextLocal(e.target.result, previewArea, right, meta, filename);
    //     reader.onerror = () => previewArea.innerHTML = `<div class="muted" style="color:var(--danger)">Failed to read CSV.</div>`;
    //     reader.readAsText(file);
    // }

    function displayCsvTextLocal(csvText, previewArea, right, meta, filename) {
        previewArea.innerHTML = '';
        const rows = csvText.split(/\r?\n/).filter(Boolean).map(r => parseCsvRow(r));
        if (!rows.length) { previewArea.innerHTML = '<div class="muted">Empty CSV</div>'; return; }
        const table = document.createElement('table');
        const headerRow = rows[0];
        const thead = document.createElement('thead'); const thr = document.createElement('tr');
        headerRow.forEach(h => { const th = document.createElement('th'); th.textContent = h; thr.appendChild(th); });
        thead.appendChild(thr); table.appendChild(thead);
        const tbody = document.createElement('tbody');
        for (let i = 1; i < rows.length; i++) {
            const tr = document.createElement('tr');
            rows[i].forEach(cell => { const td = document.createElement('td'); td.textContent = cell; tr.appendChild(td); });
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        previewArea.appendChild(table);

        let size = 13;
        const inc = makeBtn('A+', () => { size += 1; table.style.fontSize = size + 'px'; updateButtons(); meta.textContent = `${filename || 'csv'} • font ${size}px`; });
        const dec = makeBtn('A−', () => { size = Math.max(8, size - 1); table.style.fontSize = size + 'px'; updateButtons(); meta.textContent = `${filename || 'csv'} • font ${size}px`; });
        right.appendChild(dec); right.appendChild(inc);
        function updateButtons() { inc.disabled = size >= 30; dec.disabled = size <= 8; }
        updateButtons();
        meta.textContent = `${filename || 'csv'} • font ${size}px`;
    }

    function parseCsvRow(row) {
        const cells = []; let cur = '', inQuotes = false;
        for (let i = 0; i < row.length; i++) {
            const ch = row[i];
            if (ch === '"') {
                if (inQuotes && row[i + 1] === '"') { cur += '"'; i++; }
                else inQuotes = !inQuotes;
            } else if (ch === ',' && !inQuotes) {
                cells.push(cur); cur = '';
            } else cur += ch;
        }
        cells.push(cur);
        return cells;
    }

    function makeBtn(text, onClick) {
        const b = document.createElement('button');
        b.classList.add('btn-small');
        b.type = 'button'; b.textContent = text; b.addEventListener('click', onClick);
        return b;
    }

    window.previewURLsInPage = previewURLs;
})();

previewURLsInPage();





/* ----------------------------
   JSON Form Editor (right panel)
   Full feature set: shape JSON, nested arrays & objects, friendly labels,
   descriptive Add/Remove buttons, modal confirmation (modal DOM exists above).
   ---------------------------- */

(function () {
    // Modal references
    const confirmBackdrop = document.getElementById('confirmBackdrop');
    const confirmMessage = document.getElementById('confirmMessage');
    const confirmOk = document.getElementById('confirmOk');
    const confirmCancel = document.getElementById('confirmCancel');

    let pendingConfirm = null;
    function showDeleteConfirm(message, onConfirm) {
        pendingConfirm = { onConfirm };
        confirmMessage.textContent = message;
        confirmBackdrop.style.display = 'flex';
        confirmBackdrop.setAttribute('aria-hidden', 'false');
        confirmOk.focus();
    }
    function hideDeleteConfirm() { pendingConfirm = null; confirmBackdrop.style.display = 'none'; confirmBackdrop.setAttribute('aria-hidden', 'true'); }
    confirmOk.addEventListener('click', () => { if (pendingConfirm && typeof pendingConfirm.onConfirm === 'function') { try { pendingConfirm.onConfirm(); } catch (e) { console.error(e); } } hideDeleteConfirm(); });
    confirmCancel.addEventListener('click', () => hideDeleteConfirm());
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && confirmBackdrop.style.display === 'flex') hideDeleteConfirm(); });

    // Helper utilities
    function createElem(tag, attrs = {}, children = []) {
        const el = document.createElement(tag);
        for (const k in attrs) {
            if (k === 'class') el.className = attrs[k];
            else if (k === 'text') el.textContent = attrs[k];
            else el.setAttribute(k, attrs[k]);
        }
        for (const c of children) {
            if (typeof c === 'string') el.appendChild(document.createTextNode(c));
            else if (c) el.appendChild(c);
        }
        return el;
    }
    function detectType(v) {
        if (Array.isArray(v)) return 'array';
        if (v === null) return 'null';
        return typeof v;
    }
    function deepClone(v) { return JSON.parse(JSON.stringify(v)); }
    function singularize(name) {
        if (!name || typeof name !== 'string') return 'item';
        if (name.endsWith('ies')) return name.slice(0, -3) + 'y';
        if (name.endsWith('ses')) return name.slice(0, -2);
        if (name.endsWith('s') && name.length > 1) return name.slice(0, -1);
        return name;
    }

    // function getSampleForPath(shapeRoot, pathParts) {
    //     if (!shapeRoot) return undefined;
    //     let node = shapeRoot;
    //     for (let p of pathParts) {
    //         if (node === undefined || node === null) return undefined;
    //         if (Array.isArray(node)) node = node[0];
    //         if (node && typeof node === 'object') node = node[p];
    //         else return undefined;
    //     }
    //     return node;
    // }



    // function normalizeSchema(node) {
    //     // Convert shorthand "string" → { type: "string" }
    //     if (typeof node === 'string') {
    //         return { type: node };
    //     }

    //     if (Array.isArray(node)) {
    //         return normalizeSchema(node[0]);
    //     }

    //     if (node && typeof node === 'object') {
    //         // normalize object properties
    //         if (node.type === 'object' && node.properties) {
    //             const newProps = {};
    //             for (const k in node.properties) {
    //                 newProps[k] = normalizeSchema(node.properties[k]);
    //             }
    //             return { ...node, properties: newProps };
    //         }

    //         // normalize array items
    //         if (node.type === 'array' && node.items) {
    //             return { ...node, items: normalizeSchema(node.items) };
    //         }

    //         return node;
    //     }

    //     return node;
    // }

    function normalizeSchema(node) {
        // Normalize shorthand strings, array-samples, and nested properties/items
        if (node === null) return { type: 'null' };
        if (typeof node === 'string') {
            // "string"  -> { type: "string" }
            return { type: node };
        }
        if (Array.isArray(node)) {
            // Array literal sample => treat as array schema with items = normalized first element
            if (node.length === 0) return { type: 'array', items: {} };
            return { type: 'array', items: normalizeSchema(node[0]) };
        }
        if (typeof node !== 'object') {
            // Unknown primitive - can't normalize further
            return node;
        }

        // If the node already has explicit type / items / properties, normalize recursively
        const out = { ...node };

        // If it's an object schema or it looks like properties (shorthand top-level object),
        // ensure we return { type: 'object', properties: {...} } form.
        if (out.type === 'object' || out.properties) {
            out.type = out.type || 'object';
            const props = out.properties || {};
            const newProps = {};
            for (const k of Object.keys(props)) {
                newProps[k] = normalizeSchema(props[k]);
            }
            out.properties = newProps;
            return out;
        }

        // If it's an array schema
        if (out.type === 'array' || out.items) {
            out.type = out.type || 'array';
            out.items = normalizeSchema(out.items === undefined ? {} : out.items);
            return out;
        }

        // If it doesn't declare type/properties/items but is a plain object, treat as shorthand
        // e.g. { "fail reason": "string", "orders": { type: "array", ... } }
        if (!out.type && !out.properties && Object.keys(out).length > 0) {
            // map each key as a property
            const props = {};
            for (const k of Object.keys(out)) props[k] = normalizeSchema(out[k]);
            return { type: 'object', properties: props };
        }

        // fallback: return shallow copy
        return out;
    }


    // function getSchemaForPath(shapeRoot, pathParts) {
    //     if (!shapeRoot) return undefined;
    //     let node = shapeRoot;

    //     for (let p of pathParts) {
    //         if (node === undefined || node === null) return undefined;

    //         if (Array.isArray(node)) {
    //             node = node[0];
    //             continue;
    //         }

    //         if (typeof node === 'object') {
    //             if (node.type === 'array' && node.items !== undefined) {
    //                 node = node.items;
    //                 continue;
    //             }

    //             if (node.type === 'object' && node.properties && node.properties[p] !== undefined) {
    //                 node = node.properties[p];
    //                 continue;
    //             }

    //             if (node[p] !== undefined) {
    //                 node = node[p];
    //                 continue;
    //             }
    //         }

    //         return undefined;
    //     }

    //     return normalizeSchema(node);
    // }

    function getSchemaForPath(shapeRoot, pathParts) {
        if (!shapeRoot) return undefined;
        let node = shapeRoot;

        for (let p of pathParts) {
            if (node === undefined || node === null) return undefined;

            // If top-level has direct key (our shape JSON often does), follow it
            if (node[p] !== undefined) {
                node = node[p];
                continue;
            }

            // If node is an array literal sample, descend into first item
            if (Array.isArray(node)) {
                node = node[0];
                continue;
            }

            // If node has a 'type' field, branch accordingly
            if (typeof node === 'object') {
                // If it's an array schema, go into items
                if (node.type === 'array' && node.items !== undefined) {
                    node = node.items;
                    continue;
                }
                // If it's an object schema with properties, go into that property
                if (node.type === 'object' && node.properties && node.properties[p] !== undefined) {
                    node = node.properties[p];
                    continue;
                }
                // If it's an object schema but the property doesn't exist explicitly, stop
                if (node.type === 'object' && node.properties && node.properties[p] === undefined) {
                    return undefined;
                }
            }

            // Otherwise cannot descend
            return undefined;
        }

        // Always return a normalized schema node so callers can rely on {type, properties, items}
        return normalizeSchema(node);
    }


    // function createDefaultFromSchema(schema) {
    //     schema = normalizeSchema(schema);
    //     if (schema === undefined || schema === null) return undefined;
    //     if (Array.isArray(schema)) return createDefaultFromSchema(schema[0]);
    //     if (typeof schema !== 'object') return undefined;

    //     const t = schema.type;

    //     switch (t) {
    //         case 'number': return 0.0;
    //         case 'integer': return 0;
    //         case 'string': return '';
    //         case 'boolean': return false;
    //         case 'null': return null;
    //         case 'array':
    //             if (schema.items) {
    //                 const child = createDefaultFromSchema(schema.items);
    //                 return child === undefined ? [] : [child];
    //             }
    //             return [];
    //         case 'object': {
    //             const out = {};
    //             const props = schema.properties || {};
    //             for (const k of Object.keys(props)) out[k] = createDefaultFromSchema(props[k]);
    //             return out;
    //         }
    //         default:
    //             if (schema.properties) {
    //                 const o = {};
    //                 for (const k of Object.keys(schema.properties)) o[k] = createDefaultFromSchema(schema.properties[k]);
    //                 return o;
    //             }
    //             return undefined;
    //     }
    // }

    function createDefaultFromSchema(schema) {
        // Normalize shorthand first
        schema = normalizeSchema(schema);
        if (schema === undefined || schema === null) return undefined;

        // If schema is still not object, can't build
        if (typeof schema !== 'object') return undefined;

        const t = schema.type;

        switch (t) {
            case 'number':
            case 'float':
            case 'double':
                return 0.0;
            case 'integer': return 0;
            case 'string': return '';
            case 'boolean': return false;
            case 'null': return null;
            case 'array': {
                // Build a representative array with one default child if possible
                if (schema.items) {
                    const child = createDefaultFromSchema(schema.items);
                    return child === undefined ? [] : [child];
                }
                return [];
            }
            case 'object': {
                const out = {};
                const props = schema.properties || {};
                // IMPORTANT: we must add **all** declared properties, even if their default is undefined
                for (const k of Object.keys(props)) {
                    out[k] = createDefaultFromSchema(props[k]);
                }
                return out;
            }
            default:
                // If no explicit type but has properties, treat as object
                if (schema.properties) {
                    const o = {};
                    for (const k of Object.keys(schema.properties)) o[k] = createDefaultFromSchema(schema.properties[k]);
                    return o;
                }
                return undefined;
        }
    }


    function readShape() {
        const raw = document.getElementById('shapeInput').value.trim();
        if (!raw) return null;
        try { return JSON.parse(raw); } catch (e) { console.warn('Invalid shape JSON'); return null; }
    }

    // Primitive renderer
    function renderPrimitive(value, origType) {
        const wrapper = createElem('div', { class: 'primitive-wrapper' });
        if (origType === 'boolean') {
            const input = createElem('input', { type: 'checkbox' });
            input.checked = Boolean(value);
            input.dataset.primType = 'boolean';
            wrapper.appendChild(input);
        } else if (origType === 'number') {
            const input = createElem('input', { type: 'number', step: 'any' });
            input.value = (value === null || value === undefined) ? '' : String(value);
            input.dataset.primType = 'number';
            wrapper.appendChild(input);
        } else if (origType === 'null') {
            const sel = createElem('select', {});
            sel.dataset.primType = 'null';
            ['null', 'string', 'number', 'boolean'].forEach(opt => {
                const o = createElem('option', { value: opt, text: opt });
                if (opt === 'null') o.selected = true;
                sel.appendChild(o);
            });
            const txt = createElem('input', { type: 'text' }); txt.style.display = 'none';
            sel.addEventListener('change', () => {
                const t = sel.value; sel.dataset.primType = t;
                if (t === 'null') { txt.style.display = 'none'; txt.value = ''; } else { txt.style.display = 'inline-block'; txt.type = (t === 'number' ? 'number' : 'text'); }
            });
            wrapper.appendChild(sel); wrapper.appendChild(txt);
        } else {
            const input = createElem('input', { type: 'text' });
            input.value = (value === null || value === undefined) ? '' : String(value);
            input.dataset.primType = 'string';
            wrapper.appendChild(input);
        }

        wrapper.readValue = function () {
            const child = wrapper.querySelector('[data-prim-type]');
            if (!child) return null;
            const t = child.dataset.primType;
            if (child.tagName === 'SELECT') {
                if (t === 'null') return null;
                const adj = wrapper.querySelector('input[type="text"], input[type="number"]');
                if (!adj) return null;
                if (t === 'number') return adj.value === '' ? null : Number(adj.value);
                if (t === 'boolean') return adj.checked;
                return adj.value;
            }
            if (t === 'boolean') return child.checked;
            if (t === 'number') return child.value === '' ? null : Number(child.value);
            return child.value;
        };

        return wrapper;
    }

    // Object renderer
    function renderObject(obj, pathParts = [], shapeRoot = null) {
        const container = createElem('div', { class: 'object-block' });
        container.dataset.role = 'object';

        for (const key of Object.keys(obj)) {
            const val = obj[key];
            const type = detectType(val);
            const row = createElem('div', { class: 'prop-row' });
            const label = createElem('label', { text: key });
            const ctrl = createElem('div', { class: 'prop-controls' });

            if (type === 'object') {
                const details = createElem('details', { open: true }, [
                    createElem('summary', {}, [key + ' (object)']),
                    renderObject(val, pathParts.concat([key]), shapeRoot)
                ]);
                container.appendChild(details);
            } else if (type === 'array') {
                const arrNode = renderArray(val, pathParts.concat([key]), key, shapeRoot);
                const details = createElem('details', { open: true }, [
                    createElem('summary', {}, [key + ' (array)']),
                    arrNode
                ]);
                container.appendChild(details);
            } else {
                const prim = renderPrimitive(val, type);
                ctrl.appendChild(prim);
                row.appendChild(label); row.appendChild(ctrl); container.appendChild(row);
            }
        }

        container.readValue = function () {
            const out = {};
            for (const child of container.children) {
                if (child.tagName === 'DETAILS') {
                    const summary = child.querySelector('summary').textContent;
                    const key = summary.split(' (')[0];
                    const inner = child.querySelector('[data-role="object"], [data-role="array"], .object-block, .array-block');
                    if (!inner) { out[key] = null; continue; }
                    if (inner.dataset && inner.dataset.role === 'object') out[key] = inner.readValue();
                    else if (inner.dataset && inner.dataset.role === 'array') out[key] = inner.readValue();
                    else {
                        const prim = inner.querySelector('.primitive-wrapper');
                        out[key] = prim && prim.readValue ? prim.readValue() : null;
                    }
                } else if (child.classList && child.classList.contains('prop-row')) {
                    const key = child.querySelector('label').textContent;
                    const primWrapper = child.querySelector('.primitive-wrapper');
                    out[key] = primWrapper && primWrapper.readValue ? primWrapper.readValue() : null;
                }
            }
            return out;
        };

        return container;
    }

    // Array renderer with friendly labels + confirm modal on remove
    function renderArray(arr, pathParts = [], arrayName = 'items', shapeRoot = null) {
        const container = createElem('div', { class: 'array-block' });
        container.dataset.role = 'array';
        container.dataset.arrayName = arrayName;

        const headerRow = createElem('div', { class: 'array-header' });
        const title = createElem('div', { class: 'muted', text: `${arrayName} — ${arr.length} item${arr.length !== 1 ? 's' : ''}` });
        const countBadge = createElem('div', { class: 'badge', text: `${arr.length}` });
        headerRow.appendChild(title); headerRow.appendChild(countBadge);
        container.appendChild(headerRow);

        const list = createElem('div', { class: 'array-list' });

        // let itemSample = undefined;
        // if (arr.length > 0) itemSample = deepClone(arr[0]);
        // else {
        //     const sampleCandidate = getSampleForPath(shapeRoot, pathParts);
        //     if (Array.isArray(sampleCandidate) && sampleCandidate.length > 0) itemSample = deepClone(sampleCandidate[0]);
        // }


        // Determine itemSample (default instance) for this array.
        // Prefer data content if present; otherwise derive an instance from the schema.
        // let itemSample = undefined;
        // if (arr.length > 0) {
        //     itemSample = deepClone(arr[0]); // use real data example if available
        // } else {
        //     // Try to get the schema node for this array path
        //     const schemaNode = getSchemaForPath(shapeRoot, pathParts);
        //     if (schemaNode) {
        //         // If schemaNode is an array schema, use its items schema
        //         let itemsSchema = schemaNode;
        //         if (itemsSchema.type === 'array' && itemsSchema.items) itemsSchema = itemsSchema.items;

        //         // Build a default instance value from the items schema
        //         const sampleVal = createDefaultFromSchema(itemsSchema);
        //         if (sampleVal !== undefined) itemSample = deepClone(sampleVal);
        //     }
        //     // fallback: still undefined -> UI will allow user to choose first item type
        // }


        // Determine itemSample ONLY from schema, never from existing data
        let itemSample = undefined;

        const schemaNode = getSchemaForPath(shapeRoot, pathParts);
        if (schemaNode) {
            let itemsSchema = schemaNode;
            if (itemsSchema.type === 'array' && itemsSchema.items) {
                itemsSchema = itemsSchema.items;
            }

            const sampleVal = createDefaultFromSchema(itemsSchema);
            if (sampleVal !== undefined) {
                itemSample = deepClone(sampleVal);
            }
        }




        const itemType = itemSample === undefined ? null : detectType(itemSample);
        const singular = singularize(arrayName);

        function updateHeaderAndLabels() {
            const total = list.children.length;
            title.textContent = `${arrayName} — ${total} item${total !== 1 ? 's' : ''}`;
            countBadge.textContent = String(total);
            Array.from(list.children).forEach((it, idx) => {
                const sum = it.querySelector('summary');
                if (sum) {
                    let t = it.dataset.itemType || detectTypeFromNode(it) || 'item';
                    sum.textContent = `${singular} ${idx + 1} of ${total} (${t})`;
                }
                const removeBtn = it.querySelector('button.btn-remove');
                if (removeBtn) removeBtn.textContent = `Remove`;
            });
            const addBtns = container.querySelectorAll('button.btn-add');
            addBtns.forEach(b => { if (b.dataset && b.dataset.singular) b.textContent = `Add ${b.dataset.singular}`; });
        }

        function detectTypeFromNode(itemNode) {
            const innerObj = itemNode.querySelector('.object-block, [data-role="object"]');
            if (innerObj) return 'object';
            const innerArr = itemNode.querySelector('.array-block, [data-role="array"]');
            if (innerArr) return 'array';
            const prim = itemNode.querySelector('.primitive-wrapper [data-prim-type]');
            if (prim) return prim.dataset.primType || 'string';
            return null;
        }

        function makeItemNode(value, idx) {
            const item = createElem('div', { class: 'array-item' });
            item.dataset.index = idx;
            item.dataset.itemType = detectType(value);

            const details = createElem('details', { open: true });
            const summary = createElem('summary', {}, [`${singular} ${idx + 1} of ${Math.max(1, list.children.length)} (${item.dataset.itemType})`]);
            details.appendChild(summary);

            const body = createElem('div', {});
            const t = detectType(value);
            if (t === 'object') {
                body.appendChild(renderObject(value, pathParts.concat([String(idx)]), shapeRoot));
            } else if (t === 'array') {
                body.appendChild(renderArray(value, pathParts.concat([String(idx)]), arrayName + '-' + (idx + 1), shapeRoot));
            } else {
                const prim = renderPrimitive(value, t);
                body.appendChild(prim);
            }

            const removeBtn = createElem('button', { class: 'btn-small btn-remove', type: 'button' }, [`Remove`]);
            removeBtn.addEventListener('click', () => {
                // const label = `${singular} ${idx + 1}`;
                const label = `${singular}`;
                showDeleteConfirm(`Remove ${label}? This action cannot be undone if not saved, else just refresh the page.`, () => {
                    item.remove();
                    Array.from(list.children).forEach((ch, i) => { ch.dataset.index = i; });
                    updateHeaderAndLabels();
                    renderControls();
                });
            });

            details.appendChild(body);
            details.appendChild(removeBtn);
            item.appendChild(details);
            return item;
        }

        arr.forEach((v, i) => list.appendChild(makeItemNode(v, i)));
        container.appendChild(list);

        let controls = null;
        function renderControls() {
            if (controls && controls.parentNode) controls.remove();
            controls = createElem('div', { class: 'controls-row' });

            if (itemType === 'array') {
                const note = createElem('div', { class: 'muted', text: 'Adding items disabled for arrays-of-arrays.' });
                controls.appendChild(note);
            } else if (itemType === 'object') {
                const addBtn = createElem('button', { class: 'btn-small btn-add', type: 'button' }, [`Add ${singular}`]);
                addBtn.dataset.singular = singular;
                addBtn.addEventListener('click', () => {
                    // Build a concrete template (instance) for the new object:
                    let template = undefined;

                    // 1) Prefer the itemSample if it is already a usable instance object
                    if (itemSample && detectType(itemSample) === 'object') {
                        template = deepClone(itemSample);
                    } else {
                        // 2) Fallback: get schema for this path and create a default instance from it
                        const schemaNode = getSchemaForPath(shapeRoot, pathParts);
                        if (schemaNode) {
                            // If schemaNode is array schema, get its items schema
                            let itemsSchema = schemaNode;
                            if (itemsSchema.type === 'array' && itemsSchema.items) itemsSchema = itemsSchema.items;

                            // If itemsSchema is an object schema, create default instance
                            if (itemsSchema && itemsSchema.type === 'object') {
                                const built = createDefaultFromSchema(itemsSchema);
                                if (built !== undefined) template = deepClone(built);
                            }
                        }
                    }

                    // 3) Last fallback: empty object
                    if (!template || detectType(template) !== 'object') {
                        template = {};
                    }

                    const idx = list.children.length;
                    list.appendChild(makeItemNode(template, idx));
                    updateHeaderAndLabels(); renderControls();
                });
                controls.appendChild(addBtn);
                controls.appendChild(createElem('div', { class: 'muted', text: 'New objects match existing keys.' }));
                // } else if (itemType === 'object') {
                //     const addBtn = createElem('button', { class: 'btn-small btn-add', type: 'button' }, [`Add ${singular}`]);
                //     addBtn.dataset.singular = singular;
                //     addBtn.addEventListener('click', () => {
                //         let template = itemSample ? deepClone(itemSample) : getSampleForPath(shapeRoot, pathParts);
                //         if (!template || detectType(template) !== 'object') template = {};
                //         const idx = list.children.length;
                //         list.appendChild(makeItemNode(template, idx));
                //         updateHeaderAndLabels(); renderControls();
                //     });
                //     controls.appendChild(addBtn);
                //     controls.appendChild(createElem('div', { class: 'muted', text: 'New objects match existing keys.' }));
            } else if (itemType === 'number' || itemType === 'string' || itemType === 'boolean' || itemType === 'null') {
                const addBtn = createElem('button', { class: 'btn-small btn-add', type: 'button' }, [`Add ${singular}`]);
                addBtn.dataset.singular = singular;
                addBtn.addEventListener('click', () => {
                    let newVal = itemType === 'number' ? 0 : itemType === 'string' ? '' : itemType === 'boolean' ? false : null;
                    const idx = list.children.length; list.appendChild(makeItemNode(newVal, idx));
                    updateHeaderAndLabels(); renderControls();
                });
                controls.appendChild(addBtn);
                controls.appendChild(createElem('div', { class: 'muted', text: 'Array expects: ' + itemType }));
            } else {
                const sel = createElem('select', {});
                ['string', 'number', 'boolean', 'object', 'null'].forEach(t => sel.appendChild(createElem('option', { value: t, text: t })));
                const addBtn = createElem('button', { class: 'btn-small btn-add', type: 'button' }, [`Add ${singular}`]);
                addBtn.dataset.singular = singular;
                addBtn.addEventListener('click', () => {
                    const chosen = sel.value;
                    let val = chosen === 'string' ? '' : chosen === 'number' ? 0 : chosen === 'boolean' ? false : chosen === 'object' ? {} : null;
                    const idx = list.children.length;
                    list.appendChild(makeItemNode(val, idx));
                    itemSample = val;
                    renderControls();
                    updateHeaderAndLabels();
                });
                controls.appendChild(sel);
                controls.appendChild(addBtn);
                controls.appendChild(createElem('div', { class: 'muted', text: 'Array empty — choose item type (arrays disabled).' }));
            }

            container.appendChild(controls);
            updateHeaderAndLabels();
            return controls;
        }

        container.readValue = function () {
            const out = [];
            for (const it of list.children) {
                const innerObj = it.querySelector('.object-block, [data-role="object"]');
                const innerArr = it.querySelector('.array-block, [data-role="array"]');
                if (innerObj && innerObj.readValue) out.push(innerObj.readValue());
                else if (innerArr && innerArr.readValue) out.push(innerArr.readValue());
                else {
                    const prim = it.querySelector('.primitive-wrapper');
                    out.push(prim && prim.readValue ? prim.readValue() : null);
                }
            }
            return out;
        };

        renderControls();
        updateHeaderAndLabels();
        return container;
    }

    // Top-level form generation
    function generateFormInternal() {
        const raw = document.getElementById('jsonInput').value;
        const shapeRoot = readShape();
        let data;
        try { data = JSON.parse(raw); } catch (e) { alert('Invalid JSON: ' + e.message); return; }
        const area = document.getElementById('formArea'); area.innerHTML = '';
        if (Array.isArray(data)) {
            const topArr = renderArray(data, [], 'items', shapeRoot);
            const det = createElem('details', { open: true }, [createElem('summary', {}, ['Root Array'])]);
            det.appendChild(topArr); area.appendChild(det);
        } else if (data !== null && typeof data === 'object') {
            const topObj = renderObject(data, [], shapeRoot);
            const det = createElem('details', { open: true }, [createElem('summary', {}, ['Root Object'])]);
            det.appendChild(topObj); area.appendChild(det);
        } else {
            const prim = renderPrimitive(data, detectType(data));
            const wrap = createElem('div', {}); wrap.appendChild(createElem('label', { text: 'Root value' })); wrap.appendChild(prim);
            prim.id = 'rootPrimitive'; area.appendChild(wrap);
        }
        document.getElementById('outputJson').textContent = JSON.stringify(data, null, 2);
    }

    // Submit and rebuild JSON
    function submitFormInternal() {
        const area = document.getElementById('formArea');
        if (!area.firstChild) { alert('No form generated'); return null; }
        const top = area.firstChild;
        const inner = top.querySelector('[data-role="object"], [data-role="array"], .object-block, .array-block, .primitive-wrapper');
        let rebuilt;
        if (!inner) {
            const prim = area.querySelector('.primitive-wrapper');
            rebuilt = prim && prim.readValue ? prim.readValue() : null;
        } else {
            if (inner.dataset && inner.dataset.role === 'object') rebuilt = inner.readValue();
            else if (inner.dataset && inner.dataset.role === 'array') rebuilt = inner.readValue();
            else rebuilt = inner.readValue ? inner.readValue() : null;
        }
        document.getElementById('outputJson').textContent = JSON.stringify(rebuilt, null, 2);
        return rebuilt;
    }

    function downloadJSON() {
        const data = submitFormInternal();
        if (!data) return;
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = 'edited.json'; document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
    }

    function setButtonsDisabled(disabled) {
        saveBtn.disabled = disabled;
        saveApproveBtn.disabled = disabled;
    }

    // Helper: show toast
    const toast = document.getElementById('toast');
    let toastTimer = null;
    function showToast(msg) {
        clearTimeout(toastTimer);
        toast.textContent = msg;
        toast.classList.add('show');
        toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
    }

    // CSRF helper (Django default cookie name)
    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }
    const csrftoken = getCookie('csrftoken');

    let id = upload_id;
    let url = `/environments/envupload/${id}/data/save/`
    if (id === 0) {
        id = email_id;
        url = `/environments/envmail/${id}/data/save/`
    }
    let is_approved = "{{ result.is_approved }}";
    let approve_state = false;

    if (is_approved === "True") {
        approve_state = true;
    }


    async function saveJson(msg, approve) {
        const data = submitFormInternal();

        try {
            setButtonsDisabled(true);

            const res = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify({
                    data: data,
                    approve: approve
                })
            });

            if (!res.ok) {
                throw new Error('Failed to save');
            }

            const result = await res.json();
            is_approved = result.status;
            approve_state = false;

            // show disapprove button
            document.getElementById('saveApproveBtn').textContent = "Save and Approve";
            document.getElementById('saveApproveBtn').classList.remove("btn-remove");

            if (is_approved) {
                approve_state = true;

                // show disapprove button
                document.getElementById('saveApproveBtn').textContent = "Save and Disapprove";
                document.getElementById('saveApproveBtn').classList.add("btn-remove");
            }

            showToast(
                msg, 'success'
            );

        } catch (err) {
            console.error(err);
            showToast('Error saving Data', 'error');
        } finally {
            setButtonsDisabled(false);
        }
    }

    document.getElementById('saveBtn').addEventListener('click', async () => {
        await saveJson("Saved successfully", approve_state);
    });

    document.getElementById('saveApproveBtn').addEventListener('click', async () => {
        let msg = !approve_state === true ? "Saved and approved successfully" : "Saved and Disapproved successfully";
        await saveJson(msg, !approve_state);
    });

    document.getElementById('deleteBtn').addEventListener('click', async (e) => {
        confirmDelete();
    });

    // --------------------------
    // Delete modal flow
    // --------------------------
    function handleDeleteClick() {
        let id = upload_id;
        let url = `/environments/envupload/${id}/data/delete/`
        if (id === 0) {
            id = email_id;
            url = `/environments/envmail/${id}/data/delete/`
        }

        window.open(url, "_parent");
    }

    let pendingDelete = null;
    function confirmDelete() {
        showModal();
    }
    function showModal() {
        const mb = document.getElementById('modalBackdrop');
        const modaldeletebtn = document.getElementById('modalConfirm');
        mb.style.display = 'flex';
        modaldeletebtn.onclick = () => {
            handleDeleteClick();
            closeModal();
        }
        modaldeletebtn.focus();
    }
    function closeModal() { document.getElementById('modalBackdrop').style.display = 'none'; }

    // close modal on ESC
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });


    // function loadSample() {
    //     document.getElementById('jsonInput').value = JSON.stringify({
    //         users: [
    //             {
    //                 id: 1, name: "Alice", rating: 4.5, active: true, roles: ["admin", "editor"], scores: [10, 12.75, 9.5],
    //                 addresses: [{ city: "Lagos", zip: 100001, coordinates: { lat: 6.5244, lng: 3.3792 }, tags: ["home", "primary"] }]
    //             }
    //         ],
    //         metadata: { version: 1.1, generatedAt: "2025-01-01" }
    //     }, null, 2);
    //     document.getElementById('shapeInput').value = JSON.stringify({
    //         users: {
    //             type: "array", items: {
    //                 type: "object", properties: {
    //                     id: { type: "number" }, name: { type: "string" }, rating: { type: "number" }, active: { type: "boolean" },
    //                     roles: { type: "array", items: { type: "string" } }, scores: { type: "array", items: { type: "number" } },
    //                     addresses: {
    //                         type: "array", items: {
    //                             type: "object", properties: {
    //                                 city: { type: "string" }, zip: { type: "number" },
    //                                 coordinates: { type: "object", properties: { lat: { type: "number" }, lng: { type: "number" } } },
    //                                 tags: { type: "array", items: { type: "string" } }
    //                             }
    //                         }
    //                     }
    //                 }
    //             }
    //         },
    //         metadata: { type: "object", properties: { version: { type: "number" }, generatedAt: { type: "string" } } }
    //     }, null, 2);
    //     generateFormInternal();
    // }

    // Expose functions to global scope for buttons
    window.generateForm = generateFormInternal;
    window.submitForm = submitFormInternal;
    window.downloadJSON = downloadJSON;
    window.closeModal = closeModal;
    // window.loadSample = loadSample;

})();

generateForm();