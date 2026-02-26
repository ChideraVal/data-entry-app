/* ============== CONFIG ==============
   Change this if your Django save endpoint differs
   ==================================== */
const SAVE_URL = '/schemas/save/';  // change to your Django endpoint if needed

/* ============== Utilities ============== */
function uid(p = 'id') { return p + "_" + Math.random().toString(36).slice(2, 9); }
function qs(selector, el = document) { return el.querySelector(selector); }
function qsa(selector, el = document) { return Array.from(el.querySelectorAll(selector)); }

/* ============== DOM references ============== */
const rootContainer = document.getElementById('fieldsContainer');
// const jsonPreview = document.getElementById('jsonPreview');
const formjsonPreview = document.getElementById('formjsonPreview');
const treePreview = document.getElementById('treePreview');
const validationErrors = document.getElementById('validationErrors');
const saveBtn = document.getElementById('saveBtn');
// const saveStatus = document.getElementById('saveStatus');

/* ============== Field Element Factory ============== */
function createFieldElement(isNested = false) {
    const id = uid('f');
    const wrapper = document.createElement('div');
    wrapper.id = id;
    wrapper.className = isNested ? 'nested-field-card' : 'field-card';

    wrapper.innerHTML = `
    <label class="label">Field name</label>
    <input class="fname" type="text" placeholder="field_name" oninput="renderAndValidate()" />

    <label class="label">Field type</label>
    <select class="ftype" onchange="onTypeChange('${id}')">
      <option value="string">string</option>
      <option value="integer">integer</option>
      <option value="number">float</option>
      <option value="boolean">boolean</option>
      <option value="object">object</option>
      <option value="array">array</option>
    </select>

    <div style="margin-top:8px;">
      <button class="small ghost" onclick="removeElement('${id}')">Remove</button>
    </div>

    <div class="object-config" style="display:none; margin-top:10px;">
      <div class="section-label">Object fields</div>
      <div class="object-fields"></div>
      <div style="margin-top:8px;">
        <button class="small" onclick="addNestedField('${id}'); return false;">+ Add object field</button>
      </div>
    </div>

    <div class="array-config" style="display:none; margin-top:10px;">
      <label class="label">Array item type</label>
      <select class="arrayItemType" onchange="onArrayItemTypeChange('${id}')">
        <option value="string">string</option>
        <option value="integer">integer</option>
        <option value="number">float</option>
        <option value="boolean">boolean</option>
        <option value="object">object</option>
      </select>

      <div class="array-object-config" style="display:none; margin-top:8px;">
        <div class="section-label">Array item object fields</div>
        <div class="array-object-fields"></div>
        <div style="margin-top:8px;">
          <button class="small" onclick="addNestedArrayField('${id}'); return false;">+ Add array item field</button>
        </div>
      </div>
    </div>
  `;

    return wrapper;
}

/* ============== Add / Remove helpers ============== */
function addField() { rootContainer.appendChild(createFieldElement(false)); renderAndValidate(); }
function removeElement(id) { const el = document.getElementById(id); if (el) el.remove(); renderAndValidate(); }
function addNestedField(parentId) { const parent = document.getElementById(parentId); parent.querySelector('.object-fields').appendChild(createFieldElement(true)); renderAndValidate(); }
function addNestedArrayField(parentId) { const parent = document.getElementById(parentId); parent.querySelector('.array-object-fields').appendChild(createFieldElement(true)); renderAndValidate(); }

/* ============== Type change handlers ============== */
function onTypeChange(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const t = el.querySelector('.ftype').value;
    el.querySelector('.object-config').style.display = (t === 'object') ? 'block' : 'none';
    el.querySelector('.array-config').style.display = (t === 'array') ? 'block' : 'none';
    if (t === 'array') onArrayItemTypeChange(id);
    renderAndValidate();
}
function onArrayItemTypeChange(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const it = el.querySelector('.arrayItemType').value;
    el.querySelector('.array-object-config').style.display = (it === 'object') ? 'block' : 'none';
    renderAndValidate();
}

/* ============== Build typed JSON recursively ============== */
function buildTypedFromElement(fieldEl) {
    const name = (qs('.fname', fieldEl)?.value || '').trim();
    if (!name) return null;
    const type = qs('.ftype', fieldEl).value;

    if (type === 'object') {
        const props = {};
        qsa(':scope > .object-config > .object-fields > .nested-field-card', fieldEl).forEach(nf => {
            const child = buildTypedFromElement(nf);
            if (child) props[child.name] = child.value;
        });
        return { name, value: { type: 'object', properties: props } };
    }

    if (type === 'array') {
        const itemType = qs('.arrayItemType', fieldEl).value;
        if (itemType === 'object') {
            const arrProps = {};
            qsa(':scope > .array-config > .array-object-config > .array-object-fields > .nested-field-card', fieldEl).forEach(nf => {
                const child = buildTypedFromElement(nf);
                if (child) arrProps[child.name] = child.value;
            });
            return { name, value: { type: 'array', items: { type: 'object', properties: arrProps } } };
        } else {
            return { name, value: { type: 'array', items: (itemType === 'number' ? 'float' : itemType) } };
        }
    }

    return { name, value: (type === 'number' ? 'float' : type) };
}

/* ============== Validation ============== */
function validateElement(fieldEl, path) {
    // returns array of error messages
    const errors = [];
    const name = (qs('.fname', fieldEl)?.value || '').trim();
    const displayPath = path ? `${path}` : '<root>';

    if (!name) {
        errors.push(`${displayPath}: Field name cannot be empty.`);
        fieldEl.classList.add('invalid');
        return errors;
    }

    // mark clean initially
    fieldEl.classList.remove('invalid');

    const type = qs('.ftype', fieldEl).value;

    if (type === 'object') {
        const nested = qsa(':scope > .object-config > .object-fields > .nested-field-card', fieldEl);
        if (nested.length === 0) {
            errors.push(`${displayPath}.${name}: object must contain at least one property.`);
            fieldEl.classList.add('invalid');
        } else {
            nested.forEach(nf => {
                errors.push(...validateElement(nf, `${displayPath}.${name}`));
            });
        }
    } else if (type === 'array') {
        const itemType = qs('.arrayItemType', fieldEl).value;
        if (itemType === 'object') {
            const nested = qsa(':scope > .array-config > .array-object-config > .array-object-fields > .nested-field-card', fieldEl);
            if (nested.length === 0) {
                errors.push(`${displayPath}.${name}: array items of type object must define at least one property.`);
                fieldEl.classList.add('invalid');
            } else {
                nested.forEach(nf => {
                    errors.push(...validateElement(nf, `${displayPath}.${name}[]`));
                });
            }
        }
    }

    return errors;
}

function validateEntireSchema() {
    const errors = [];
    // schema name required
    const schemaName = document.getElementById('schemaName').value.trim();
    if (!schemaName) errors.push('Schema name cannot be empty.');

    // root must have at least one field
    const topFields = qsa(':scope > .field-card', rootContainer);
    if (topFields.length === 0) {
        errors.push('Schema must have at least one top-level field.');
    }

    // validate each top field
    topFields.forEach(f => {
        errors.push(...validateElement(f, 'root'));
    });

    // remove duplicates and empty
    return errors.filter(Boolean);
}

/* ============== Render & Validate combined ============== */
function renderAndValidate() {
    // clear invalid styling first
    qsa('.invalid').forEach(el => el.classList.remove('invalid'));
    // render typed JSON
    const typed = {};
    qsa(':scope > .field-card', rootContainer).forEach(f => {
        const node = buildTypedFromElement(f);
        if (node) typed[node.name] = node.value;
    });
    // jsonPreview.textContent = JSON.stringify(typed, null, 4);
    formjsonPreview.value = JSON.stringify(typed, null, 4);

    // render tree
    treePreview.innerHTML = '';
    const ul = document.createElement('ul');
    for (const k in typed) {
        ul.appendChild(buildTree(typed[k], k));
    }
    treePreview.appendChild(ul);

    // validate
    const errs = validateEntireSchema();
    if (errs.length) {
        validationErrors.innerHTML = `<div class="errors"><b>Validation errors:</b><ul>${errs.map(e => `<li>${e}</li>`).join('')}</ul></div>`;
        saveBtn.disabled = true;
        saveBtn.classList.add('disabled');
    } else {
        validationErrors.innerHTML = '';
        saveBtn.disabled = false;
        saveBtn.classList.remove('disabled');
    }
    // clear status message when editing
    // saveStatus.style.display = 'none';
}

/* ============== Tree builder (for display) ============== */
function buildTree(node, name) {
    const li = document.createElement('li');
    if (typeof node === 'object' && !Array.isArray(node)) {
        if (node.type === 'object') {
            li.innerHTML = `<b>${name}</b> : object`;
            const ul = document.createElement('ul');
            for (const k in node.properties) ul.appendChild(buildTree(node.properties[k], k));
            li.appendChild(ul);
        } else if (node.type === 'array') {
            li.innerHTML = `<b>${name}</b> : array`;
            const ul = document.createElement('ul');
            const items = node.items;
            if (typeof items === 'object' && items.type === 'object') {
                for (const k in items.properties) ul.appendChild(buildTree(items.properties[k], k));
            } else {
                const child = document.createElement('li');
                child.textContent = `items: ${items}`;
                ul.appendChild(child);
            }
            li.appendChild(ul);
        } else {
            li.textContent = `${name} : ${node}`;
        }
    } else {
        li.textContent = `${name} : ${node}`;
    }
    return li;
}

/* ============== CSRF helper (reads cookie) ============== */
function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
}

/* ============== Save / submit ============== */
async function saveSchema() {
    const errs = validateEntireSchema();
    if (errs.length) {
        validationErrors.innerHTML = `<div class="errors"><b>Validation errors:</b><ul>${errs.map(e => `<li>${e}</li>`).join('')}</ul></div>`;
        return;
    }

    // build typed JSON
    const typed = {};
    qsa(':scope > .field-card', rootContainer).forEach(f => {
        const node = buildTypedFromElement(f);
        if (node) typed[node.name] = node.value;
    });

    const schemaName = document.getElementById('schemaName').value.trim();

    // FormData to send as form data
    const fd = new FormData();
    fd.append('schema_name', schemaName);
    fd.append('schema_json', JSON.stringify(typed));

    // show loading state
    saveBtn.disabled = true;
    // saveStatus.className = 'status';
    // saveStatus.textContent = 'Saving...';
    // saveStatus.style.display = 'block';

    try {
        const res = await fetch(SAVE_URL, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken') || ''
            },
            body: fd,
            credentials: 'include'
        });

        if (!res.ok) {
            const text = await res.text();
            // saveStatus.className = 'status error';
            // saveStatus.textContent = `Save failed: ${res.status} ${res.statusText} — ${text}`;
            saveBtn.disabled = false;
            return;
        }

        const data = await res.json().catch(() => null);

        // saveStatus.className = 'status success';
        // saveStatus.textContent = 'Saved successfully.';
        // optionally show returned ID: data.id
        saveBtn.disabled = false;
    } catch (err) {
        // saveStatus.className = 'status error';
        // saveStatus.textContent = `Save error: ${err.message}`;
        saveBtn.disabled = false;
    }
}

/* ============== Clear ============== */
function clearAll() { rootContainer.innerHTML = ''; document.getElementById('schemaName').value = ''; renderAndValidate(); }

/* init */
renderAndValidate();