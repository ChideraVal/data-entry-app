// minimal confirmation flow that supports the per-item delete-form.
// It intercepts the form submit, shows modal and only posts when confirmed.

let pendingForm = null;
let pendingEnvId = null;

function confirmDelete(event, envJSON) {
    console.log(envJSON)
    // event is the submit event, envJSON contains env id and other data if available
    event.preventDefault();
    pendingForm = event.target;
    pendingEnvId = envJSON && envJSON.id ? envJSON.id : null;


    // show a more helpful message when the schema is locked
    const usedBadge = pendingForm.closest('.card')?.querySelector('.badge.used');
    const modalMessage = document.getElementById('modalMessage');
    if (usedBadge) {
        modalMessage.textContent = 'This schema has already processed documents. Deleting it will leave depending environments without a schema. Are you sure?';
    } else {
        modalMessage.textContent = 'Are you sure you want to delete this schema? This action cannot be undone.';
    }

    showModal();
    return false;
}

function showModal() {
    const mb = document.getElementById('modalBackdrop');
    mb.style.display = 'flex';
    mb.setAttribute('aria-hidden', 'false');
    // focus confirm
    document.getElementById('modalConfirm').focus();
}
function closeModal() {
    const mb = document.getElementById('modalBackdrop');
    mb.style.display = 'none';
    mb.setAttribute('aria-hidden', 'true');
    pendingForm = null;
    pendingEnvId = null;
}
function confirmModal() {
    if (!pendingForm) { closeModal(); return; }
    // actually submit the pending form
    pendingForm.submit();
    closeModal();
}

// close modal on ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});