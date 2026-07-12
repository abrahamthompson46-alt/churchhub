/**
 * Ledger entry — cascade categories by transaction type and auto-fill accounts.
 */
(function () {
    const form = document.getElementById("ledger-entry-form");
    const typeSelect = document.getElementById("id_transaction_type");
    const categorySelect = document.getElementById("id_category");
    const narrationField = document.getElementById("id_narration");
    const memberWrap = document.getElementById("member-field-wrap");
    const preview = document.getElementById("account-preview");
    const previewDebit = document.getElementById("preview-debit");
    const previewCredit = document.getElementById("preview-credit");

    if (!form || !typeSelect || !categorySelect) return;

    const categoriesUrl = form.dataset.categoriesUrl || "/ledger/api/categories/";
    const categoryDetailTemplate = form.dataset.categoryDetailUrl || "";

    function categoryDetailUrl(id) {
        if (categoryDetailTemplate && categoryDetailTemplate.indexOf("00000000") !== -1) {
            return categoryDetailTemplate.replace("00000000-0000-0000-0000-000000000000", id);
        }
        return "/ledger/api/categories/" + id + "/";
    }

    function setOptions(categories, selectedId) {
        categorySelect.innerHTML = "";
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select category…";
        categorySelect.appendChild(placeholder);

        categories.forEach(function (cat) {
            const opt = document.createElement("option");
            opt.value = cat.id;
            opt.textContent = cat.name;
            if (selectedId && selectedId === cat.id) {
                opt.selected = true;
            }
            categorySelect.appendChild(opt);
        });
    }

    function applyCategory(cat) {
        if (!cat) {
            preview.hidden = true;
            if (memberWrap) memberWrap.style.display = "";
            return;
        }
        preview.hidden = false;
        previewDebit.textContent = cat.debit_account_name;
        previewCredit.textContent = cat.credit_account_name;
        if (memberWrap) {
            memberWrap.style.display = cat.requires_member ? "" : "none";
        }
        if (narrationField && cat.default_narration && !narrationField.value.trim()) {
            narrationField.value = cat.default_narration;
        }
    }

    function loadCategories(type, keepSelection) {
        const selected = keepSelection ? categorySelect.value : "";
        fetch(categoriesUrl + "?type=" + encodeURIComponent(type), {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                setOptions(data.categories || [], selected);
                const match = (data.categories || []).find(function (c) { return c.id === selected; });
                applyCategory(match || null);
            })
            .catch(function () {
                setOptions([]);
                applyCategory(null);
            });
    }

    function onCategoryChange() {
        const id = categorySelect.value;
        if (!id) {
            applyCategory(null);
            return;
        }
        fetch(categoryDetailUrl(id), {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (r) { return r.json(); })
            .then(applyCategory)
            .catch(function () { applyCategory(null); });
    }

    typeSelect.addEventListener("change", function () {
        loadCategories(typeSelect.value, false);
    });

    categorySelect.addEventListener("change", onCategoryChange);

    loadCategories(typeSelect.value, true);
})();
