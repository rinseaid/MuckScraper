"""The optional appearance hook must not alter an unconfigured installation."""
from flask import Flask
import pytest
from aggregator.reader_themes import init_app, theme_settings


def test_no_hook_or_settings_when_disabled():
    app = Flask(__name__)
    before = len(app.template_context_processors[None])
    init_app(app, {})
    assert len(app.template_context_processors[None]) == before
    assert "READER_THEME_SETTINGS" not in app.config


def test_defaults_and_local_theme_registration():
    assert theme_settings({})['desktop'] == 'classic'
    settings = theme_settings({'READER_THEMES': '{"paper":{"label":"Paper","stylesheet":"css/paper.css"}}',
                               'READER_THEME_MOBILE': 'paper'})
    assert settings['desktop'] == 'classic' and settings['mobile'] == 'paper'
    assert {font['family'].split(',')[-1].strip() for font in settings['fonts'].values()} == {'serif', 'sans-serif'}


@pytest.mark.parametrize('path', ['https://example.org/a.css', 'css/../a.css', 'css/a.css?track=1', '//example.org/a.css'])
def test_stylesheets_are_local(path):
    import json
    with pytest.raises(ValueError):
        theme_settings({'READER_THEMES': json.dumps({'paper': {'label': 'Paper', 'stylesheet': path}})})


def test_explicit_default_must_exist():
    with pytest.raises(ValueError):
        theme_settings({'READER_THEME_MOBILE': 'missing'})


def test_browser_font_preview_and_device_preferences():
    """Use the real shared account control and assets with synthetic page text."""
    from pathlib import Path
    from types import SimpleNamespace
    from jinja2 import Environment, FileSystemLoader
    pw = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[1]
    env = Environment(loader=FileSystemLoader(root / 'aggregator/templates'))
    settings = theme_settings({'READER_THEMES': '{"paper":{"label":"Paper","stylesheet":"css/paper.css"}}',
                               'READER_THEME_MOBILE': 'paper'})
    config = {**settings, 'themes': {key: {'label': item['label'], 'url': '/static/' + item['stylesheet'] if item['stylesheet'] else ''}
                                    for key, item in settings['themes'].items()}}
    env.globals.update(current_user=SimpleNamespace(is_authenticated=True, username='Example', role_label='Reader'),
                       can=lambda role: False, csrf_token=lambda: 'fixture-csrf', menu_back=lambda: '/headlines',
                       url_for=lambda endpoint, **kw: '/static/' + kw['filename'] if endpoint == 'static' else '/' + endpoint)
    html = env.from_string('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
      <link rel="stylesheet" href="/static/css/theme.css">{% include '_reader_theme_head.html' %}</head><body>
      {% from 'account_menu.html' import account_menu with context %}{{ account_menu() }}
      <h1>Example headline</h1><label for="query">Search</label><input id="query"><button id="action">Read</button>
      </body></html>''').render(reader_themes=config)
    with pw.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        errors = []
        def route(request):
            from urllib.parse import urlsplit
            path = urlsplit(request.request.url).path
            if path == '/': request.fulfill(body=html, content_type='text/html')
            elif path == '/static/css/paper.css': request.fulfill(body=':root {--fixture: paper}', content_type='text/css')
            else:
                asset = root / 'aggregator' / path.lstrip('/')
                assert asset.is_file(), path
                request.fulfill(path=str(asset))
        context.route('https://reader.example/**', route)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://reader.example/')
        assert page.locator('html').get_attribute('data-reader-theme') == 'classic'
        page.set_viewport_size({'width': 393, 'height': 852})
        page.wait_for_function("document.documentElement.dataset.readerTheme === 'paper'")
        page.locator('.account-button').click()
        page.locator('[data-reader-preferences-open]').click()
        assert page.locator('dialog').evaluate('(el) => el.open')
        for font in ['system', 'arial', 'verdana', 'georgia', 'palatino', 'times']:
            page.locator('[data-reader-font-choice=' + font + ']').click()
            assert page.locator('html').get_attribute('data-reader-font') == font
            families = page.locator('h1, #query, #action, label').evaluate_all('(els) => els.map(el => getComputedStyle(el).fontFamily)')
            assert len(set(families)) == 1
            assert page.locator('[data-reader-font-choice=' + font + ']').get_attribute('aria-pressed') == 'true'
        page.keyboard.press('Escape')
        page.wait_for_function("document.activeElement === document.querySelector('.account-button')")
        page.reload()
        assert page.locator('html').get_attribute('data-reader-font') == 'times'
        page.locator('.account-button').click()
        page.locator('[data-reader-preferences-open]').click()
        page.locator('[data-reader-theme-choice=classic]').click()
        page.locator('[data-reader-font-choice=default]').click()
        page.keyboard.press('Escape')
        page.reload()
        assert page.locator('html').get_attribute('data-reader-theme') == 'classic'
        assert page.locator('html').get_attribute('data-reader-font') is None
        assert not errors
        context.close()
        # Blocked storage must not stop transient font/theme selection.
        isolated = browser.new_context(viewport={'width': 1280, 'height': 900})
        isolated.route('https://reader.example/**', route)
        isolated.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw Error('Storage denied')}})")
        page = isolated.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('https://reader.example/')
        page.locator('.account-button').click()
        page.locator('[data-reader-preferences-open]').click()
        page.locator('[data-reader-font-choice=georgia]').click()
        assert page.locator('html').get_attribute('data-reader-font') == 'georgia'
        assert not errors
        browser.close()
