/**
 * Searchable wrapper for category <select> fields (ledger + teller receipts).
 * Keeps the native select as the form source of truth.
 */
(function () {
    "use strict";

    function esc(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function optionItems(select) {
        return Array.prototype.filter.call(select.options, function (opt) {
            return opt.value;
        });
    }

    function buildPicker(select) {
        if (select.dataset.categoryPickerReady === "1") {
            return select.closest(".category-picker");
        }
        select.dataset.categoryPickerReady = "1";
        select.classList.add("category-picker__native");

        var wrap = document.createElement("div");
        wrap.className = "category-picker";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);

        var selected = document.createElement("div");
        selected.className = "category-picker__selected d-none";
        selected.innerHTML =
            '<span class="category-picker__label" data-cp-label></span>' +
            '<button type="button" class="btn btn-sm btn-link text-muted category-picker__clear" data-cp-clear aria-label="Clear category">&times;</button>';

        var searchWrap = document.createElement("div");
        searchWrap.className = "category-picker__search-wrap";
        searchWrap.innerHTML =
            '<input type="text" class="form-control category-picker__input" autocomplete="off" data-cp-input aria-label="Search categories" placeholder="Search category…">' +
            '<div class="category-picker__results d-none" data-cp-results role="listbox"></div>';

        wrap.insertBefore(selected, select);
        wrap.insertBefore(searchWrap, select);

        var state = {
            select: select,
            wrap: wrap,
            selected: selected,
            labelEl: selected.querySelector("[data-cp-label]"),
            clearBtn: selected.querySelector("[data-cp-clear]"),
            searchWrap: searchWrap,
            input: searchWrap.querySelector("[data-cp-input]"),
            results: searchWrap.querySelector("[data-cp-results]"),
        };
        select._categoryPickerState = state;
        bindPicker(state);
        syncFromSelect(state);
        return wrap;
    }

    function renderResults(state, query) {
        var q = (query || "").trim().toLowerCase();
        var items = optionItems(state.select).filter(function (opt) {
            if (!q) return true;
            return opt.textContent.toLowerCase().indexOf(q) !== -1;
        });

        if (!items.length) {
            state.results.innerHTML = '<div class="category-picker__empty">No categories found</div>';
        } else {
            state.results.innerHTML = items
                .map(function (opt) {
                    return (
                        '<button type="button" class="category-picker__option" role="option" data-value="' +
                        esc(opt.value) +
                        '">' +
                        esc(opt.textContent) +
                        "</button>"
                    );
                })
                .join("");
        }
        state.results.classList.remove("d-none");
    }

    function showSelected(state, label) {
        state.labelEl.textContent = label;
        state.selected.classList.remove("d-none");
        state.searchWrap.classList.add("d-none");
        state.results.classList.add("d-none");
        state.input.value = "";
    }

    function showSearch(state) {
        state.selected.classList.add("d-none");
        state.searchWrap.classList.remove("d-none");
        state.input.focus();
    }

    function syncFromSelect(state) {
        var opt = state.select.options[state.select.selectedIndex];
        if (opt && opt.value) {
            showSelected(state, opt.textContent);
        } else {
            state.selected.classList.add("d-none");
            state.searchWrap.classList.remove("d-none");
        }
    }

    function bindPicker(state) {
        state.input.addEventListener("input", function () {
            renderResults(state, state.input.value);
        });

        state.input.addEventListener("focus", function () {
            renderResults(state, state.input.value);
        });

        state.results.addEventListener("click", function (e) {
            var btn = e.target.closest(".category-picker__option");
            if (!btn) return;
            state.select.value = btn.dataset.value;
            state.select.dispatchEvent(new Event("change", { bubbles: true }));
            syncFromSelect(state);
        });

        state.clearBtn.addEventListener("click", function () {
            state.select.value = "";
            state.select.dispatchEvent(new Event("change", { bubbles: true }));
            showSearch(state);
        });

        state.select.addEventListener("change", function () {
            syncFromSelect(state);
        });

        document.addEventListener("click", function (e) {
            if (!state.wrap.contains(e.target)) {
                state.results.classList.add("d-none");
            }
        });
    }

    function refresh(select) {
        if (!select) return;
        var state = select._categoryPickerState;
        if (!state) {
            buildPicker(select);
            return;
        }
        syncFromSelect(state);
        state.results.classList.add("d-none");
    }

    function initAll(root) {
        (root || document).querySelectorAll("select.js-category-picker").forEach(buildPicker);
    }

    window.ChCategoryPicker = {
        initAll: initAll,
        refresh: refresh,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll();
        });
    } else {
        initAll();
    }
})();
