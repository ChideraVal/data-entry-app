// Optional: live preview of the typed JSON (basic)
function collectFormTypedJSON() {
    const data = {};
    function linesFrom(id) { const el = document.getElementById(id); if (!el) return []; return el.value.split(/\\r?\\n/).map(s => s.trim()).filter(Boolean); }

    data.document_types = linesFrom('id_document_types_text');
    data.email_folders = linesFrom('id_email_folders_text');
    data.allowed_senders = linesFrom('id_allowed_senders_text');
    data.allowed_subject_keywords = linesFrom('id_allowed_subject_keywords_text');
    data.blocked_subject_keywords = linesFrom('id_blocked_subject_keywords_text');

    const allowed = [];
    document.querySelectorAll('input[name="allowed_file_types"]:checked').forEach(ch => allowed.push(ch.value));
    data.allowed_file_types = allowed;
    data.require_attachment = !!document.querySelector('input[name="require_attachment"]')?.checked;

    return data;
}

function updatePreview() {
    const pre = document.getElementById('typedPreview');
    pre.textContent = JSON.stringify(collectFormTypedJSON(), null, 2);
}

// wire events: update preview when textareas change and file type checkboxes change
['id_document_types_text', 'id_email_folders_text', 'id_allowed_senders_text', 'id_allowed_subject_keywords_text', 'id_blocked_subject_keywords_text'].forEach(id => {
    const e = document.getElementById(id);
    if (e) e.addEventListener('input', updatePreview);
});
document.querySelectorAll('input[name="allowed_file_types"]').forEach(ch => ch.addEventListener('change', updatePreview));
const req = document.querySelector('input[name="require_attachment"]');
if (req) req.addEventListener('change', updatePreview);

// initial preview
updatePreview();