/**
 * ChurchHub navigation & UI polish
 */
(function () {
    const DESKTOP_BP = 992;
    const DEFAULT_FLASH_MS = 6000;

    function initHoverDropdowns() {
        document.querySelectorAll('.hover-dropdown').forEach(function (el) {
            let timeout;
            el.addEventListener('mouseenter', function () {
                if (window.innerWidth < DESKTOP_BP) return;
                clearTimeout(timeout);
                const toggle = el.querySelector('[data-bs-toggle="dropdown"]');
                if (toggle) bootstrap.Dropdown.getOrCreateInstance(toggle).show();
            });
            el.addEventListener('mouseleave', function () {
                if (window.innerWidth < DESKTOP_BP) return;
                const toggle = el.querySelector('[data-bs-toggle="dropdown"]');
                timeout = setTimeout(function () {
                    if (toggle) bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
                }, 150);
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
