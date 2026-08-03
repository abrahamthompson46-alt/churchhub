/**
 * Record Receipt — apply category defaults (accounts, member required, description).
 * Uses embedded category payload so tellers with manage_receipts (no ledger API) still work.
 */
(function () {
    const form = document.getElementById("record-receipt-form");
    const categorySelect = document.getElementById("id_category");
    const descriptionField = document.getElementById("id_description");
    const memberWrap = document.getElementById("member-field-wrap");
    const memberLabel = memberWrap
        ? memberWrap.querySelector("label.form-label")
        : null;
    const preview = document.getElementById("account-preview");
    const previewDebit = document.getElementById("preview-debit");
    const previewCredit = document.getElementById("preview-credit");
    const dataEl = document.getElementById("receipt-category-data");

    if (!form || !categorySelect || !dataEl) return;

    let categories = {};
    try {
        categories = JSON.parse(dataEl.textContent || "{}") || {};
    } catch (e) {
        categories = {};
    }

    function setMemberRequired(required) {
        if (!memberWrap) return;
        memberWrap.style.display = required ? "" : "none";
        const picker = memberWrap.querySelector("[data-member-picker]");
        if (picker) {
            if (required) {
                picker.classList.add("member-picker--required");
                picker.setAttribute("data-required", "1");
            } else {
                picker.classList.remove("member-picker--required");
                picker.removeAttribute("data-required");
            }
        }
        if (memberLabel) {
            memberLabel.innerHTML = required
                ? 'Member<span class="text-danger ms-1">*</span>'
                : "Member (optional)";
        }
    }

    function applyCategory(cat) {
        if (!cat) {
            if (preview) preview.hidden = true;
            setMemberRequired(false);
            return;
        }
        if (preview) {
            preview.hidden = false;
            if (previewDebit) {
                previewDebit.textContent = cat.debit_account_name || "—";
                previewDebit.title = cat.debit_account_name || "";
            }
            if (previewCredit) {
                previewCredit.textContent = cat.credit_account_name || "—";
                previewCredit.title = cat.credit_account_name || "";
            }
        }
        setMemberRequired(!!cat.requires_member);
        if (
            descriptionField &&
            cat.default_narration &&
            !descriptionField.value.trim()
        ) {
            descriptionField.value = cat.default_narration;
        }
    }

    function onCategoryChange() {
        const id = categorySelect.value;
        applyCategory(id ? categories[id] || null : null);
    }

    categorySelect.addEventListener("change", onCategoryChange);
    onCategoryChange();
})();
