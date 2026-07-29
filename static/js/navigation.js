/**
 * ChurchHub navigation & UI polish
 */
(function () {
    const DESKTOP_BP = 992;
    const DEFAULT_FLASH_MS = 6000;
    const DROPDOWN_HIDE_MS = 90;

    function isDesktop() {
        return window.innerWidth >= DESKTOP_BP;
    }

    function dropdownParts(el) {
        return {
            toggle: el.querySelector('[data-bs-toggle="dropdown"]'),
            menu: el.querySelector('.dropdown-menu'),
        };
    }

    function hideDropdown(toggle) {
        if (!toggle) return;
        const instance = bootstrap.Dropdown.getOrCreateInstance(toggle);
        instance.hide();
    }

    function showDropdown(toggle) {
        if (!toggle) return;
        document.querySelectorAll('.hover-dropdown [data-bs-toggle="dropdown"]').forEach(function (other) {
            if (other !== toggle) hideDropdown(other);
        });
        bootstrap.Dropdown.getOrCreateInstance(toggle).show();
    }

    function pointerInside(el, toggle, menu) {
        if (!el) return false;
        if (el.matches(':hover')) return true;
        if (menu && menu.matches(':hover')) return true;
        if (toggle && toggle.matches(':hover')) return true;
        return false;
    }

    function initHoverDropdowns() {
        document.querySelectorAll('.hover-dropdown').forEach(function (el) {
            const parts = dropdownParts(el);
            const toggle = parts.toggle;
            const menu = parts.menu;
            if (!toggle || !menu) return;

            let hideTimer = null;

            function scheduleHide() {
                clearTimeout(hideTimer);
                hideTimer = setTimeout(function () {
                    if (!isDesktop()) return;
                    if (!pointerInside(el, toggle, menu)) {
                        hideDropdown(toggle);
                    }
                }, DROPDOWN_HIDE_MS);
            }

            function cancelHide() {
                clearTimeout(hideTimer);
            }

            function onEnter() {
                if (!isDesktop()) return;
                cancelHide();
                showDropdown(toggle);
            }

            [toggle, menu, el].forEach(function (node) {
                node.addEventListener('mouseenter', onEnter);
                node.addEventListener('mouseleave', scheduleHide);
                node.addEventListener('focusin', onEnter);
                node.addEventListener('focusout', scheduleHide);
            });

            document.addEventListener('click', function (evt) {
                if (!isDesktop()) return;
                if (el.contains(evt.target)) return;
                hideDropdown(toggle);
            });
        });
    }

    function initFlashMessages() {
        document.querySelectorAll('.app-flash').forEach(function (el, index) {
            const duration = parseInt(el.getAttribute('data-flash-duration'), 10) || DEFAULT_FLASH_MS;
            const progress = el.querySelector('.app-flash__progress');
            const stagger = Math.min(index * 80, 240);

            el.style.animationDelay = stagger + 'ms';

            if (progress) {
                progress.style.animation = 'flash-progress ' + duration + 'ms linear forwards';
                progress.style.animationDelay = stagger + 'ms';
            }

            let dismissTimer = setTimeout(function () {
                const alert = bootstrap.Alert.getOrCreateInstance(el);
                if (alert) alert.close();
            }, duration + stagger);

            el.addEventListener('mouseenter', function () {
                el.classList.add('is-paused');
                clearTimeout(dismissTimer);
                if (progress) progress.style.animationPlayState = 'paused';
            });

            el.addEventListener('mouseleave', function () {
                el.classList.remove('is-paused');
                const remaining = duration * 0.4;
                if (progress) {
                    progress.style.animation = 'none';
                    void progress.offsetWidth;
                    progress.style.animation = 'flash-progress ' + remaining + 'ms linear forwards';
                }
                dismissTimer = setTimeout(function () {
                    const alert = bootstrap.Alert.getOrCreateInstance(el);
                    if (alert) alert.close();
                }, remaining);
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initHoverDropdowns();
        initFlashMessages();
    });
})();
