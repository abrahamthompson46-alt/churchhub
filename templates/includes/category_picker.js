/**
 * Type-to-filter category combobox. Native <select> stays the submitted value.
 */
(function () {
    "use strict";

    if (window.ChCategoryPicker && window.ChCategoryPicker._bound) {
        window.ChCategoryPicker.initAll();
        return;
    }

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

    function selectedLabel(select) {
        var opt = select.options[select.selectedIndex];
        return opt && opt.value ? opt.textContent : "";
    }

    function ensureChrome(select) {
        var root = select.closest("[data-category-picker]");
        if (root) {
            return root;
        }
        root = document.createElement("div");
        root.className = "category-picker";
        root.setAttribute("data-category-picker", "");
        select.parentNode.insertBefore(root, select);
        root.appendChild(select);

        var input = document.createElement("input");
        input.type = "search";
        input.className = "form-control category-picker__input";
        input.setAttribute("autocomplete", "off");
        input.setAttribute("spellcheck", "false");
        input.setAttribute("aria-label", "Search categories");
        input.setAttribute("placeholder", "Type to search categories…");
        input.setAttribute("data-cp-input", "");
        input.id = (select.id || "id_category") + "_search";

        var results = document.createElement("div");
        results.className = "category-picker__results d-none";
        results.setAttribute("data-cp-results", "");
        results.setAttribute("role", "listbox");

        root.appendChild(input);
        root.appendChild(results);
        return root;
    }

    function renderResults(state, query) {
        var q = (query || "").trim().toLowerCase();
        var items = optionItems(state.select).filter(function (opt) {
            if (!q) return true;
            return opt.textContent.toLowerCase().indexOf(q) !== -1;
        });
        state.activeIndex = items.length ? 0 : -1;

        if (!items.length) {
            state.results.innerHTML = '<div class="category-picker__empty">No categories found</div>';
        } else {
            state.results.innerHTML = items
                .map(function (opt, idx) {
                    return (
                        '<button type="button" class="category-picker__option' +
                        (idx === 0 ? " is-active" : "") +
                        '" role="option" data-value="' +
                        esc(opt.value) +
                        '">' +
                        esc(opt.textContent) +
                        "</button>"
                    );
                })
                .join("");
        }
        state.results.classList.remove("d-none");
        state.open = true;
    }

    function setActive(state, index) {
        var options = state.results.querySelectorAll(".category-picker__option");
        if (!options.length) return;
        if (index < 0) index = options.length - 1;
        if (index >= options.length) index = 0;
        state.activeIndex = index;
        Array.prototype.forEach.call(options, function (el, i) {
            el.classList.toggle("is-active", i === index);
        });
        options[index].scrollIntoView({ block: "nearest" });
    }

    function closeResults(state) {
        state.results.classList.add("d-none");
        state.open = false;
        state.activeIndex = -1;
    }

    function choose(state, value) {
        state.select.value = value || "";
        state.select.dispatchEvent(new Event("change", { bubbles: true }));
        state.input.value = selectedLabel(state.select);
        closeResults(state);
    }

    function syncFromSelect(state) {
        var label = selectedLabel(state.select);
        if (!state.input.matches(":focus")) {
            state.input.value = label;
        }
    }

    function bindPicker(state) {
        state.input.addEventListener("input", function () {
            renderResults(state, state.input.value);
        });

        state.input.addEventListener("focus", function () {
            if (state.input.value && selectedLabel(state.select) === state.input.value) {
                state.input.select();
            }
            renderResults(state, state.input.value === selectedLabel(state.select) ? "" : state.input.value);
        });

        state.input.addEventListener("keydown", function (e) {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                if (!state.open) {
                    renderResults(state, state.input.value);
                } else {
                    setActive(state, state.activeIndex + 1);
                }
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (state.open) setActive(state, state.activeIndex - 1);
            } else if (e.key === "Enter") {
                if (!state.open) return;
                e.preventDefault();
                var active = state.results.querySelector(".category-picker__option.is-active");
                if (active) choose(state, active.getAttribute("data-value"));
            } else if (e.key === "Escape") {
                closeResults(state);
                state.input.value = selectedLabel(state.select);
            }
        });

        state.results.addEventListener("mousedown", function (e) {
            e.preventDefault();
            var btn = e.target.closest(".category-picker__option");
            if (!btn) return;
            choose(state, btn.getAttribute("data-value"));
        });

        state.input.addEventListener("blur", function () {
            window.setTimeout(function () {
                closeResults(state);
                var typed = (state.input.value || "").trim().toLowerCase();
                if (!typed) {
                    choose(state, "");
                    return;
                }
                var match = optionItems(state.select).find(function (opt) {
                    return opt.textContent.toLowerCase() === typed;
                });
                if (match) {
                    choose(state, match.value);
                } else {
                    state.input.value = selectedLabel(state.select);
                }
            }, 120);
        });

        state.select.addEventListener("change", function () {
            syncFromSelect(state);
        });
    }

    function enhanceSelect(select) {
        if (!select) return;
        var root = ensureChrome(select);
        if (root.dataset.categoryPickerReady === "1") {
            var existing = select._categoryPickerState;
            if (existing) syncFromSelect(existing);
            return;
        }
        var input = root.querySelector("[data-cp-input]");
        var results = root.querySelector("[data-cp-results]");
        if (!input || !results) return;

        root.dataset.categoryPickerReady = "1";
        root.classList.add("is-enhanced");
        select.classList.add("category-picker__native");
        select.setAttribute("tabindex", "-1");
        select.setAttribute("aria-hidden", "true");
        select.style.cssText =
            "position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;border:0;padding:0;margin:-1px;overflow:hidden;";

        var state = {
            select: select,
            root: root,
            input: input,
            results: results,
            open: false,
            activeIndex: -1,
        };
        select._categoryPickerState = state;
        bindPicker(state);
        syncFromSelect(state);
    }

    function initAll(root) {
        (root || document).querySelectorAll("select.js-category-picker").forEach(enhanceSelect);
    }

    function refresh(select) {
        if (!select) return;
        enhanceSelect(select);
        var state = select._categoryPickerState;
        if (!state) return;
        syncFromSelect(state);
        closeResults(state);
    }

    window.ChCategoryPicker = {
        initAll: initAll,
        refresh: refresh,
        _bound: true,
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll();
        });
    } else {
        initAll();
    }
})();
