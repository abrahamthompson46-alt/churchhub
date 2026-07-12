/**
 * Searchable member picker with photo / initials for treasury and welfare forms.
 */
(function () {
    var DEBOUNCE_MS = 220;
    var MIN_CHARS = 1;

    function esc(text) {
        var div = document.createElement("div");
        div.textContent = text || "";
        return div.innerHTML;
    }

    function avatarHtml(item) {
        if (item.photo_url) {
            return '<img src="' + esc(item.photo_url) + '" alt="" class="member-picker__photo">';
        }
        return '<span class="member-picker__initials">' + esc(item.initials) + "</span>";
    }

    function initPicker(root) {
        var hidden = document.getElementById(root.dataset.inputId);
        if (!hidden) return;

        var searchInput = root.querySelector("[data-picker-input]");
        var results = root.querySelector("[data-picker-results]");
        var selected = root.querySelector(".member-picker__selected");
        var nameEl = root.querySelector("[data-picker-name]");
        var subtitleEl = root.querySelector("[data-picker-subtitle]");
        var avatarEl = root.querySelector("[data-picker-avatar]");
        var clearBtn = root.querySelector("[data-picker-clear]");
        var searchWrap = root.querySelector(".member-picker__search-wrap");
        var searchUrl = root.dataset.searchUrl;
        var timer = null;

        function showSelected(item) {
            hidden.value = item.id;
            nameEl.textContent = item.name;
            subtitleEl.textContent = item.subtitle || "";
            avatarEl.innerHTML = avatarHtml(item);
            selected.classList.remove("d-none");
            searchWrap.classList.add("d-none");
            results.classList.add("d-none");
            searchInput.value = "";
        }

        function clearSelection() {
            hidden.value = "";
            selected.classList.add("d-none");
            searchWrap.classList.remove("d-none");
            searchInput.focus();
        }

        function renderResults(items) {
            if (!items.length) {
                results.innerHTML = '<div class="member-picker__empty">No members found</div>';
            } else {
                results.innerHTML = items.map(function (item) {
                    return (
                        '<button type="button" class="member-picker__option" role="option" data-id="' + esc(item.id) + '"' +
                        ' data-name="' + esc(item.name) + '" data-subtitle="' + esc(item.subtitle) + '"' +
                        ' data-photo="' + esc(item.photo_url) + '" data-initials="' + esc(item.initials) + '">' +
                        '<span class="member-picker__avatar">' + avatarHtml(item) + "</span>" +
                        '<span class="member-picker__option-text"><span class="member-picker__name">' + esc(item.name) + "</span>" +
                        (item.subtitle ? '<span class="member-picker__subtitle">' + esc(item.subtitle) + "</span>" : "") +
                        "</span></button>"
                    );
                }).join("");
            }
            results.classList.remove("d-none");
        }

        function fetchResults(query) {
            fetch(searchUrl + "?q=" + encodeURIComponent(query), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (r) { return r.json(); })
                .then(function (data) { renderResults(data.results || []); })
                .catch(function () {
                    results.innerHTML = '<div class="member-picker__empty">Search unavailable</div>';
                    results.classList.remove("d-none");
                });
        }

        if (root.dataset.initialId) {
            showSelected({
                id: root.dataset.initialId,
                name: root.dataset.initialName,
                subtitle: root.dataset.initialSubtitle || "",
                photo_url: root.dataset.initialPhoto || "",
                initials: (root.dataset.initialName || "?").split(" ").map(function (p) { return p[0]; }).join("").slice(0, 2).toUpperCase(),
            });
        } else if (hidden.value) {
            fetch(searchUrl + "?id=" + encodeURIComponent(hidden.value))
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.results && data.results[0]) showSelected(data.results[0]);
                });
        }

        searchInput.addEventListener("input", function () {
            clearTimeout(timer);
            var q = searchInput.value.trim();
            if (q.length < MIN_CHARS) {
                results.classList.add("d-none");
                return;
            }
            timer = setTimeout(function () { fetchResults(q); }, DEBOUNCE_MS);
        });

        searchInput.addEventListener("focus", function () {
            var q = searchInput.value.trim();
            if (q.length >= MIN_CHARS) fetchResults(q);
        });

        results.addEventListener("click", function (e) {
            var btn = e.target.closest(".member-picker__option");
            if (!btn) return;
            showSelected({
                id: btn.dataset.id,
                name: btn.dataset.name,
                subtitle: btn.dataset.subtitle,
                photo_url: btn.dataset.photo,
                initials: btn.dataset.initials,
            });
        });

        clearBtn.addEventListener("click", clearSelection);

        document.addEventListener("click", function (e) {
            if (!root.contains(e.target)) results.classList.add("d-none");
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-member-picker]").forEach(initPicker);
    });
})();
