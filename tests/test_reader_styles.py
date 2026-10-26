"""Optional styles must work with the original application, without other PRs."""
from datetime import datetime
from threading import Thread

import pytest
from flask import jsonify, request
from flask_login import login_user
from werkzeug.serving import make_server


@pytest.mark.parametrize('engine', ['chromium', 'webkit'])
def test_real_pages_theme_matrix(monkeypatch, engine):
    from aggregator import create_app, db
    from aggregator.models import User, Story, Article, Outlet
    from aggregator.blueprints import public
    pw = pytest.importorskip('playwright.sync_api')
    monkeypatch.setenv('SECRET_KEY', 'reader-styles-fixture-only-secret')
    monkeypatch.setenv('DATABASE_URL', 'sqlite://')
    monkeypatch.setenv('READER_APPEARANCE_ENABLED', 'true')
    monkeypatch.setenv('READER_THEME_DESKTOP', 'classic')
    monkeypatch.setenv('READER_THEME_MOBILE', 'classic')
    monkeypatch.setattr(public, 'check_ollama_status', lambda *a, **kw: False)
    app = create_app()
    with app.app_context():
        db.create_all()
        user = User(username='fixture', email='fixture@example.test', role='admin', is_admin=True, is_active=True)
        story = Story(title='A synthetic report with multiple perspectives', summary='Synthetic reporting for browser tests.', created_at=datetime.utcnow())
        db.session.add_all([user, story])
        for name, score in [('Example Left', 1), ('Example Center', 3), ('Example Right', 5)]:
            outlet = Outlet(name=name, bias_score=score)
            db.session.add(Article(title=story.title, source=name, url='https://example.test/' + str(score),
                                   content='<p>Synthetic report.</p>', summary='Synthetic summary.',
                                   outlet=outlet, story=story, date=datetime.utcnow(), scrape_status='success'))
        db.session.commit()
    @app.before_request
    def fixture_identity():
        if request.path in ['/ollama-status', '/meili-status']:
            return jsonify(online=False, providers=[])
        login_user(User.query.first())
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as playwright:
            browser = getattr(playwright, engine).launch()
            for width, height in [(1440, 1000), (768, 1024), (393, 852), (320, 568), (852, 393)]:
                context = browser.new_context(viewport={'width': width, 'height': height})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/headlines')
                for theme in ['classic', 'reader', 'editorial']:
                    page.evaluate('(theme) => localStorage.setItem("muckscraper-reader-theme", theme)', theme)
                    for scheme in ['light', 'dark']:
                        for path in ['/headlines', '/admin/multi-stories', '/story/1', '/article/1', '/admin/search']:
                            response = page.goto(f'http://127.0.0.1:{server.server_port}{path}')
                            assert response.status == 200
                            page.evaluate('(scheme) => document.documentElement.dataset.theme = scheme', scheme)
                            assert page.locator('html').get_attribute('data-reader-theme') == theme
                            if theme != 'classic':
                                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, theme, path)
                                toggle = page.locator('#sidebar-toggle')
                                if toggle.count():
                                    assert toggle.bounding_box()['y'] <= 24
                                    assert float(toggle.evaluate('(el) => getComputedStyle(el).fontSize').removesuffix('px')) >= 14
                                    if width > 768 and height > 500 and page.locator('.topbar-title').count():
                                        button, brand = toggle.bounding_box(), page.locator('.topbar-title').bounding_box()
                                        assert button['x'] + button['width'] <= brand['x']
                            if path in ['/story/1', '/article/1']:
                                assert page.locator('.reader-detail').count() == 1
                assert not errors
                context.close()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        with app.app_context():
            db.session.remove()
            db.drop_all()
