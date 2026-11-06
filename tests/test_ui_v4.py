"""Ensure the enterprise modular frontend ships with the API and is wired correctly."""
from pathlib import Path
from fastapi.testclient import TestClient
from meridian.api import create_app

ROOT=Path(__file__).parents[1]/'meridian'


def test_erp_nine_views_and_custom_controls():
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    for name in ('procurement','quality','reports','settings'):
        assert f'id="page-{name}"' in html
        assert f'data-page-link="{name}"' in html
    for name in ('settingsForm','widgetOptions','fieldForm','valueForm','poForm','poLines','poReceiptForm','qualityForm','commandBackdrop'):
        assert f'id="{name}"' in html
    assert '/enterprise.css' in html and '/enterprise.js' in html


def test_static_frontend_resources_are_served(tmp_path):
    with TestClient(create_app(tmp_path/'ui.db')) as client:
        html=client.get('/')
        assert html.status_code==200 and 'Enterprise Workspace v0.4' in html.text
        css=client.get('/enterprise.css')
        assert css.status_code==200 and 'text/css' in css.headers['content-type'] and 'data-theme=dark' in css.text
        js=client.get('/enterprise.js')
        assert js.status_code==200 and 'text/javascript' in js.headers['content-type'] and 'data-jump' in js.text
