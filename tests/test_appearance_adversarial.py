"""Exercise untrusted preferences and real shared controls without external services."""
import json
import random
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from flask import Flask, render_template_string

from aggregator.reader_themes import init_app, theme_settings

ROOT = Path(__file__).resolve().parents[1]


def test_compose_mobile_default_inherits_desktop():
    compose = (ROOT / 'docker-compose.yml').read_text()
    assert 'READER_THEME_MOBILE: "${READER_THEME_MOBILE:-}"' in compose
    settings = theme_settings({'READER_THEME_DESKTOP': 'paper', 'READER_THEMES': json.dumps({
        'paper': {'label': 'Paper', 'stylesheet': 'css/paper.css'}})})
    assert settings['mobile'] == 'paper'


@pytest.mark.parametrize('value', ['null', '[]', 'true', '42', '"x"', '{',
    '{"default":{"label":"X","stylesheet":"css/x.css"}}',
    '{"paper":null}', '{"paper":{"label":[],"stylesheet":"css/x.css"}}',
    '{"paper":{"label":"X","stylesheet":null}}'])
def test_invalid_operator_configuration_fails_closed(value):
    with pytest.raises(ValueError):
        theme_settings({'READER_THEMES': value})
    app = Flask(__name__)
    init_app(app, {'READER_THEMES': value})  # Disabled installations ignore optional config.
    assert 'READER_THEME_SETTINGS' not in app.config


def fixture_html():
    app = Flask(__name__, template_folder=str(ROOT / 'aggregator/templates'),
                static_folder=str(ROOT / 'aggregator/static'))
    init_app(app, {'READER_APPEARANCE_ENABLED': 'true', 'READER_THEMES': json.dumps({
        'paper': {'label': '</script><script>window.injected=true</script>' + 'W' * 180,
                  'stylesheet': 'css/paper.css'},
        'broken': {'label': 'Unavailable theme', 'stylesheet': 'css/broken.css'}})})
    app.jinja_env.globals.update(
        current_user=SimpleNamespace(is_authenticated=True, username='Fixture', role_label='Reader'),
        can=lambda role: False, csrf_token=lambda: 'synthetic', menu_back=lambda: '/headlines',
        url_for=lambda endpoint, **kw: '/static/' + kw['filename'] if endpoint == 'static' else '/' + endpoint)
    with app.test_request_context('/'):
        return render_template_string('''<!doctype html><html><head>
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <link rel="stylesheet" href="/static/css/theme.css">{% include '_reader_theme_head.html' %}
          </head><body>{% from 'account_menu.html' import account_menu with context %}{{ account_menu() }}
          <form method="post" action="/danger"><input id="query"><button>Submit</button></form>
          <h1>Reading the news</h1></body></html>''')


@pytest.mark.parametrize('engine', ['chromium', 'webkit'])
def test_hostile_preferences_keyboard_and_load_failures(engine):
    pw = pytest.importorskip('playwright.sync_api')
    html = fixture_html()
    with pw.sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        context = browser.new_context(viewport={'width': 320, 'height': 568})
        requests, errors = [], []
        def route(route):
            request = route.request
            requests.append((request.method, request.url))
            path = urlsplit(request.url).path
            if path == '/': route.fulfill(body=html, content_type='text/html')
            elif path == '/static/css/paper.css': route.fulfill(body='body {--fixture: paper}', content_type='text/css')
            elif path == '/static/css/broken.css': route.fulfill(status=404, body='missing')
            else:
                asset = ROOT / 'aggregator' / path.lstrip('/')
                assert asset.is_file(), request.url
                route.fulfill(path=str(asset))
        context.route('**/*', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://appearance.example/')
        assert page.evaluate('window.injected') is None
        hostile = ['__proto__', 'constructor', '<img src=x onerror=alert(1)>',
                   'javascript:alert(1)', '//attacker.example/x.css', '../x', '\x00', 'x' * 100000]
        rng = random.Random(7341)
        hostile += [''.join(chr(rng.randint(1, 0xffff)) for _ in range(32)) for _ in range(500)]
        page.evaluate('''values => {
            for (const value of values) {
                for (const key of ['muckscraper-reader-theme', 'muckscraper-reader-font']) {
                    localStorage.setItem(key, value);
                    dispatchEvent(new StorageEvent('storage', {key, newValue:value, storageArea:localStorage}));
                }
                if (document.documentElement.dataset.readerTheme !== 'classic' || document.documentElement.dataset.readerFont) throw Error('Preference escaped allowlist');
            }
        }''', hostile)
        page.reload()
        assert page.locator('html').get_attribute('data-reader-theme') == 'classic'
        page.locator('.account-button').click()
        page.locator('[data-reader-preferences-open]').click()
        page.locator('[data-reader-theme-choice=paper]').click()
        assert page.locator('dialog').evaluate('(e) => e.scrollWidth <= e.clientWidth')
        assert page.locator('dialog').evaluate('(e) => e.getBoundingClientRect().left >= 0 && e.getBoundingClientRect().right <= innerWidth')
        # Repeated keyboard activation must never submit the adjacent form or log out.
        for i in range(75):
            page.keyboard.press('Tab' if i % 2 else 'Shift+Tab')
            assert page.evaluate("document.activeElement === document.body || document.querySelector('dialog').contains(document.activeElement)")
            page.keyboard.press('Space')
            if not page.locator('dialog').evaluate('(e) => e.open'):
                page.locator('.account-button').click()
                page.locator('[data-reader-preferences-open]').click()
        page.locator('[data-reader-theme-choice=broken]').click()
        page.wait_for_function("document.documentElement.dataset.readerTheme === 'classic'")
        assert page.locator('[data-reader-theme-status]').is_visible()
        page.locator('[data-reader-theme-choice=paper]').click()
        page.wait_for_function("document.documentElement.dataset.readerTheme === 'paper'")
        assert not page.locator('[data-reader-theme-status]').is_visible()
        # Two tabs, preference changes and clearing storage stay synchronized.
        second = context.new_page()
        second.goto('https://appearance.example/')
        second.evaluate("localStorage.setItem('muckscraper-reader-font','georgia')")
        page.wait_for_function("document.documentElement.dataset.readerFont === 'georgia'")
        second.evaluate('localStorage.clear()')
        page.wait_for_function("!document.documentElement.dataset.readerFont && document.documentElement.dataset.readerTheme === 'classic'")
        page.keyboard.press('Escape')
        page.wait_for_function("document.activeElement === document.querySelector('.account-button')")
        assert not errors
        assert all(method == 'GET' and urlsplit(url).netloc == 'appearance.example' for method, url in requests)
        browser.close()
