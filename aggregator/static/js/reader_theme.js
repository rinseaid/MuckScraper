// CSS theme selection stays local to this browser, separately from appearance.
(function () {
    var configElement = document.getElementById('reader-theme-config');
    if (!configElement) return;
    var config = JSON.parse(configElement.textContent);
    var stylesheet = document.getElementById('reader-theme-stylesheet');
    var key = 'muckscraper-reader-theme';
    var mobile = window.matchMedia('(max-width: 768px), (max-height: 500px)');
    function preference(value) {
        return Object.prototype.hasOwnProperty.call(config.themes, value) ? value : 'default';
    }
    var fonts = config.fonts || {};
    var fontKey = 'muckscraper-reader-font';
    function fontPreference(value) {
        return Object.prototype.hasOwnProperty.call(fonts, value) ? value : 'default';
    }
    var selectedFont = 'default';
    try { selectedFont = fontPreference(localStorage.getItem(fontKey)); } catch (_) {}
    function applyFont() {
        var root = document.documentElement;
        if (selectedFont === 'default') {
            root.removeAttribute('data-reader-font');
            root.style.removeProperty('--reader-font');
        } else {
            root.setAttribute('data-reader-font', selectedFont);
            root.style.setProperty('--reader-font', fonts[selectedFont].family);
        }
        document.querySelectorAll('[data-reader-font-choice]').forEach(function (control) {
            control.setAttribute('aria-pressed', String(control.dataset.readerFontChoice === selectedFont));
        });
        document.querySelectorAll('[data-reader-font-label]').forEach(function (label) {
            label.textContent = selectedFont === 'default' ? 'Theme default' : fonts[selectedFont].label;
        });
    }
    var selected = 'default';
    try { selected = preference(localStorage.getItem(key)); } catch (_) {}
    function apply() {
        var name = selected === 'default' ? config[mobile.matches ? 'mobile' : 'desktop'] : selected;
        var url = config.themes[name].url;
        if (url) stylesheet.setAttribute('href', url);
        else stylesheet.removeAttribute('href');
        document.documentElement.setAttribute('data-reader-theme', name);
        document.querySelectorAll('[data-reader-theme-choice]').forEach(function (control) {
            control.setAttribute('aria-pressed', String(control.dataset.readerThemeChoice === selected));
        });
        document.querySelectorAll('[data-reader-theme-preference]').forEach(function (control) {
            control.value = selected;
        });
    }
    apply();
    applyFont();
    document.addEventListener('DOMContentLoaded', function () {
        apply(); applyFont();
        document.querySelectorAll('.reader-preferences').forEach(function (dialog) {
            dialog.addEventListener('close', function () {
                var button = dialog.closest('.account-menu').querySelector('.account-button');
                if (button) button.focus();
            });
        });
    });
    document.addEventListener('click', function (event) {
        var open = event.target.closest('[data-reader-preferences-open]');
        if (open) {
            var menu = open.closest('.account-menu');
            menu.querySelector('.account-dropdown').hidden = true;
            menu.querySelector('.account-button').setAttribute('aria-expanded', 'false');
            menu.querySelector('.reader-preferences').showModal();
            return;
        }
        var close = event.target.closest('[data-reader-preferences-close]');
        if (close) { close.closest('dialog').close(); return; }
        var theme = event.target.closest('[data-reader-theme-choice]');
        if (theme) {
            selected = preference(theme.dataset.readerThemeChoice);
            try {
                if (selected === 'default') localStorage.removeItem(key);
                else localStorage.setItem(key, selected);
            } catch (_) {}
            apply();
            return;
        }
        var control = event.target.closest('[data-reader-font-choice]');
        if (!control) return;
        selectedFont = fontPreference(control.dataset.readerFontChoice);
        try {
            if (selectedFont === 'default') localStorage.removeItem(fontKey);
            else localStorage.setItem(fontKey, selectedFont);
        } catch (_) {}
        applyFont();
    });
    document.addEventListener('change', function (event) {
        if (!event.target.matches('[data-reader-theme-preference]')) return;
        selected = preference(event.target.value);
        try {
            if (selected === 'default') localStorage.removeItem(key);
            else localStorage.setItem(key, selected);
        } catch (_) {}
        apply();
    });
    mobile.addEventListener('change', apply);
    window.addEventListener('storage', function (event) {
        if (event.key === fontKey || event.key === null) {
            selectedFont = fontPreference(event.newValue);
            applyFont();
        }
        if (event.key === key || event.key === null) {
            selected = preference(event.newValue);
            apply();
        }
    });
})();
