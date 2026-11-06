"""Static UI contracts for Meridian ERP v0.3 dashboard."""
from html.parser import HTMLParser
from pathlib import Path

HTML = Path(__file__).parents[1] / "meridian" / "index.html"

class Inspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.nav_links = []
        self.page_names = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if values.get("data-page-link"):
            self.nav_links.append(values["data-page-link"])
        if values.get("data-page"):
            self.page_names.append(values["data-page"])

def test_ui_has_five_distinct_navigation_views():
    inspector = Inspector()
    inspector.feed(HTML.read_text(encoding="utf-8"))
    pages = {"overview", "inventory", "boms", "production", "audit"}
    assert set(inspector.nav_links) == pages
    assert set(inspector.page_names) == pages
    assert len(inspector.ids) == len(set(inspector.ids)), "Duplicate HTML IDs"

def test_bom_editor_is_multi_component():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="addBomComponent"' in html
    assert 'id="bomComponents"' in html
    assert 'data-component-qty' in html
    assert 'function getComponents(id)' in html
    assert "const components=getComponents('bomComponents')" in html
    assert "components},`Draft BOM" in html
    assert 'A component can appear only once' in html

def test_production_and_audit_views_retain_critical_controls():
    html = HTML.read_text(encoding="utf-8")
    for element in ("receiveForm", "issueForm", "bomOrderForm", "workOrderForm",
                    "routingForm", "workOrderList", "bomList", "auditRows",
                    "ledgerRows", "exportLedger", "exportAudit", "exportStock"):
        assert f'id="{element}"' in html
    assert 'data-order-action="reserve"' in html
    assert "data-step-action" in html
    assert "function downloadCSV" in html
