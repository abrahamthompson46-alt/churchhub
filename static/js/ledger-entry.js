/**
 * Ledger entry — cascade categories by transaction type and auto-fill accounts.
 */
(function () {
    const form = document.getElementById("ledger-entry-form");
    const typeSelect = document.getElementById("id_transaction_type");
    const categorySelect = document.getElementById("id_category");
    const bankSelect = document.getElementById("id_bank_account");
    const bankWrap = document.getElementById("bank-field-wrap");
    const narrationField = document.getElementById("id_narration");
    const memberWrap = document.getElementById("member-field-wrap");
    const preview = document.getElementById("account-preview");
    const previewDebit = document.getElementById("preview-debit");
    const previewCredit = document.getElementById("preview-credit");

    if (!form || !typeSelect || !categorySelect) return;

    const categoriesUrl = form.dataset.categoriesUrl || "/ledger/api/categories/";
    const categoryDetailTemplate = form.dataset.categoryDetailUrl || "";

    let activeCategory = null;

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
        if (window.ChCategoryPicker) {
            window.ChCategoryPicker.refresh(categorySelect);
        }
    }

    function selectedBankName() {
        if (!bankSelect || !bankSelect.value) return "";
        const opt = bankSelect.options[bankSelect.selectedIndex];
        return opt ? opt.textContent.trim() : "";
    }

    function refreshBankPreview(cat) {
        if (!cat) return;
        if (cat.requires_bank_selection && bankWrap) {
            bankWrap.hidden = false;
        } else if (bankWrap) {
            bankWrap.hidden = true;
        }
        const bankName = selectedBankName();
        if (cat.requires_bank_selection && bankName) {
            if (cat.bank_leg === "debit") {
                previewDebit.textContent = bankName;
                previewDebit.title = bankName;
            } else if (cat.bank_leg === "credit") {
                previewCredit.textContent = bankName;
                previewCredit.title = bankName;
            }
        }
    }

    function applyCategory(cat) {
        activeCategory = cat || null;
        if (!cat) {
            preview.hidden = true;
            if (memberWrap) memberWrap.style.display = "";
            if (bankWrap) bankWrap.hidden = true;
            return;
        }
        preview.hidden = false;
        previewDebit.textContent = cat.debit_account_name || "—";
        previewCredit.textContent = cat.credit_account_name || "—";
        previewDebit.title = cat.debit_account_name || "";
        previewCredit.title = cat.credit_account_name || "";
        if (memberWrap) {
            memberWrap.style.display = cat.requires_member ? "" : "none";
        }
        if (narrationField && cat.default_narration && !narrationField.value.trim()) {
            narrationField.value = cat.default_narration;
        }
        if (bankWrap) {
            bankWrap.hidden = !cat.requires_bank_selection;
        }
        if (cat.requires_bank_selection && bankSelect && cat.default_bank_account_id) {
            const hasOption = Array.prototype.some.call(
                bankSelect.options,
                function (o) { return o.value === cat.default_bank_account_id; }
            );
            if (hasOption && !bankSelect.value) {
                bankSelect.value = cat.default_bank_account_id;
            }
        }
        refreshBankPreview(cat);
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

    if (bankSelect) {
        bankSelect.addEventListener("change", function () {
            refreshBankPreview(activeCategory);
        });
    }

    loadCategories(typeSelect.value, true);
})();