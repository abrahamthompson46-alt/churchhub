/**
 * ChurchHub app UI — sticky sections, tab scroll, table polish
 */
(function () {
    "use strict";

    function initStickyModuleTabs() {
        document.querySelectorAll(".module-tabs--sticky").forEach(function (el) {
            var nav = document.querySelector(".ch-navbar");
            if (nav) {
                var height = nav.getBoundingClientRect().height;
                el.style.top = height + "px";
            }
        });
    }

    function initActiveModuleTabScroll() {
        document.querySelectorAll(".module-tabs-scroll").forEach(function (scroll) {
            var active = scroll.querySelector(".module-tab.is-active");
            if (!active) return;
            var left = active.offsetLeft - scroll.offsetWidth / 2 + active.offsetWidth / 2;
            scroll.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
        });
    }

    function initFilterBarSticky() {
        document.querySelectorAll(".filter-bar--sticky").forEach(function (el) {
            var nav = document.querySelector(".ch-navbar");
            var tabs = document.querySelector(".module-tabs--sticky");
            var top = nav ? nav.getBoundingClientRect().height : 0;
            if (tabs) top += tabs.getBoundingClientRect().height;
            el.style.top = top + "px";
        });
    }

    function initTableRowFocus() {
        document.querySelectorAll(".data-card table tbody tr").forEach(function (row) {
            if (row.querySelector("a.table-link")) {
                row.classList.add("table-row--interactive");
            }
        });
    }

    function initNavCollapseClose() {
        var collapse = document.getElementById("mainNav");
        if (!collapse) return;
        collapse.querySelectorAll("a.nav-link, a.nav-mega-link").forEach(function (link) {
            link.addEventListener("click", function () {
                if (window.innerWidth < 992 && collapse.classList.contains("show")) {
                    bootstrap.Collapse.getOrCreateInstance(collapse).hide();
                }
            });
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        initStickyModuleTabs();
        initActiveModuleTabScroll();
        initFilterBarSticky();
        initTableRowFocus();
        initNavCollapseClose();
        window.addEventListener("resize", function () {
            initStickyModuleTabs();
            initFilterBarSticky();
        });
    });
})();
