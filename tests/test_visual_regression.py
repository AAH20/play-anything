"""Static smoke checks for dashboard view navigation.

These checks catch missing view markup and route wiring without a browser. They
do not capture screenshots or compare pixels against a visual baseline.
"""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest


DASHBOARD = Path(__file__).resolve().parents[1] / "play_anything" / "dashboard.html"
GRAPH_VIEWER = DASHBOARD.with_name("graph-viewer.js")
GRAPH_PAGE = DASHBOARD.with_name("graph-page.js")
CREATOR_UI = DASHBOARD.with_name("creator.js")
CREATOR_HTML = DASHBOARD.with_name("creator.html")
REQUIRED_VIEWS = {
    "map",
    "skills",
    "battle",
    "voice",
    "benchmarks",
    "studio",
    "personalization",
    "enterprise",
}


class DashboardMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.buttons = {}
        self.nav_labels = []
        self.nav_classes = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
            if element_id.startswith("tab-btn-"):
                self.buttons[element_id.removeprefix("tab-btn-")] = attributes.get("onclick", "")
        if tag == "nav":
            self.nav_labels.append(attributes.get("aria-label", ""))
            self.nav_classes.append(attributes.get("class", ""))


class DashboardNavigationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DASHBOARD.read_text(encoding="utf-8")
        cls.graph_viewer = GRAPH_VIEWER.read_text(encoding="utf-8")
        cls.graph_page = GRAPH_PAGE.read_text(encoding="utf-8")
        cls.creator_ui = CREATOR_UI.read_text(encoding="utf-8")
        cls.creator_html = CREATOR_HTML.read_text(encoding="utf-8")
        cls.markup = DashboardMarkup()
        cls.markup.feed(cls.html)

    def test_eight_requested_views_have_matching_buttons_and_panels(self):
        buttons = set(self.markup.buttons)
        panels = {
            element_id.removeprefix("view-")
            for element_id in self.markup.ids
            if element_id.startswith("view-")
        }
        self.assertTrue(REQUIRED_VIEWS <= buttons, f"missing tab buttons: {REQUIRED_VIEWS - buttons}")
        self.assertTrue(REQUIRED_VIEWS <= panels, f"missing view panels: {REQUIRED_VIEWS - panels}")

    def test_each_requested_button_targets_its_matching_view(self):
        for view in sorted(REQUIRED_VIEWS):
            with self.subTest(view=view):
                self.assertIn(f"switchTab('{view}')", self.markup.buttons[view])
                self.assertIn(f"view-{view}", self.markup.ids)

    def test_requested_views_are_in_the_runtime_tab_allowlist(self):
        match = re.search(r"const tabs = \[(.*?)\];", self.html, re.DOTALL)
        self.assertIsNotNone(match, "switchTab runtime tab list is missing")
        runtime_tabs = set(re.findall(r"'([a-z]+)'", match.group(1)))
        self.assertTrue(REQUIRED_VIEWS <= runtime_tabs, f"missing runtime routes: {REQUIRED_VIEWS - runtime_tabs}")

    def test_requested_views_are_accepted_on_initial_hash_load(self):
        match = re.search(r"DOMContentLoaded[\s\S]*?\['graph',[\s\S]*?\]\.includes\(hash\)", self.html)
        self.assertIsNotNone(match, "initial hash route allowlist is missing")
        accepted_hashes = set(re.findall(r"'([a-z]+)'", match.group(0)))
        self.assertTrue(REQUIRED_VIEWS <= accepted_hashes, f"missing initial hash routes: {REQUIRED_VIEWS - accepted_hashes}")

    def test_navigation_wraps_and_has_an_accessible_name(self):
        self.assertIn("Dashboard views", self.markup.nav_labels)
        self.assertTrue(any("flex-wrap" in classes.split() for classes in self.markup.nav_classes))

    def test_optional_cdn_does_not_block_offline_dashboard_structure(self):
        self.assertRegex(self.html, r'<script async src="https://www\.gstatic\.com/antigravity/web/dev/tailwindcss\.min\.js"></script>')
        style = re.search(r"<style>([\s\S]*?)</style>", self.html)
        self.assertIsNotNone(style)
        for fallback in (".hidden { display: none !important; }", "main { display: flex;",
                         "#view-map:not(.hidden)", "nav[aria-label=\"Dashboard views\"]"):
            with self.subTest(fallback=fallback):
                self.assertIn(fallback, style.group(1))

    def test_selected_view_is_exposed_to_assistive_technology(self):
        match = re.search(r'<button[^>]*id="tab-btn-map"[^>]*>', self.html)
        self.assertIsNotNone(match)
        self.assertIn('aria-current="page"', match.group(0))
        self.assertIn("b.setAttribute('aria-current', 'page')", self.html)
        self.assertIn("b.removeAttribute('aria-current')", self.html)

    def test_map_animation_pauses_when_hidden_or_reduced_motion_is_requested(self):
        self.assertIn("document.addEventListener('visibilitychange'", self.html)
        self.assertIn("window.matchMedia('(prefers-reduced-motion: reduce)')", self.html)
        self.assertIn("cancelAnimationFrame(canvasFrame)", self.html)
        switch = re.search(r"function switchTab\(tabId\) \{[\s\S]*?\n    \}", self.html)
        self.assertIsNotNone(switch)
        self.assertIn("stopCanvasAnimation()", switch.group(0))

    def test_reduced_motion_still_gets_a_resized_static_map_frame(self):
        resize = re.search(r"function resizeCanvas\(\) \{[\s\S]*?\n    \}", self.html)
        self.assertIsNotNone(resize)
        self.assertIn("renderCanvas()", resize.group(0))
        self.assertIn("new ResizeObserver(resizeCanvas)", self.html)
        self.assertIn("function canvasViewport()", self.html)
        self.assertIn("const mouseX = (e.clientX - rect.left - offsetX) / scale;", self.html)
        style = re.search(r"<style>([\s\S]*?)</style>", self.html).group(1)
        self.assertIn("body { height: 100vh; min-height: 100vh;", style)
        self.assertIn("main { display: flex; flex: 1 1 0;", style)
        self.assertIn("#biome-canvas { position: absolute; inset: 0;", style)
        self.assertIn("header > div:nth-child(2) { grid-template-columns: minmax(0, 1fr); }", style)
        self.assertIn("header > div:nth-child(2) > div:last-child { grid-column: 1 / -1; }", style)
        self.assertIn("body { height: auto; min-height: 100vh; overflow-x: hidden; overflow-y: auto; }", style)
        self.assertIn("grid-template-rows: auto auto; height: auto;", style)
        self.assertIn("#view-map > div:first-child { display: flex; flex-direction: column; min-height: 360px; height: auto;", style)
        self.assertIn("#biome-canvas-frame { position: relative; inset: auto; flex: 0 0 360px; width: 100%; height: 360px;", style)
        self.assertIn(".map-overlay { position: static !important; inset: auto !important;", style)
        self.assertIn("header > div:first-child p > span:last-child { flex-basis: 100%; }", style)
        self.assertIn("header p { margin: .25rem 0 0; color: #94a3b8; font-size: .78rem; column-gap: .3rem; row-gap: .15rem; }", style)
        self.assertIn("#biome-legend > div:last-child { column-gap: .75rem; row-gap: .25rem; }", style)
        self.assertRegex(self.html, r'<div id="biome-canvas-frame">\s*<canvas id="biome-canvas"')

    def test_mobile_map_overlays_flow_after_the_fixed_canvas_frame(self):
        style = re.search(r"<style>([\s\S]*?)</style>", self.html).group(1)
        self.assertIn("new ResizeObserver(resizeCanvas).observe(canvas.parentElement)", self.html)
        self.assertIn("#biome-canvas-frame { position: absolute; inset: 0;", style)
        self.assertIn(".map-overlay-legend", self.html)
        self.assertIn('class="map-overlay map-overlay-hint', self.html)
        self.assertIn('class="map-overlay map-overlay-controls', self.html)
        self.assertIn(".map-overlay-legend > div:last-child { flex-wrap: wrap; }", style)

    def test_graph_discloses_provenance_and_analysis_limits(self):
        self.assertIn("class=\"graph-analysis help\" role=\"status\" aria-live=\"polite\"", self.graph_viewer)
        for field in ("status", "source_kind", "file_count", "analyzed_files", "unparsed_files",
                      "parse_errors", "unreadable_files", "too_large_files", "file_limit_reached",
                      "source_bytes_read", "source_budget_bytes", "source_budget_exceeded_files",
                      "source_budget_exhausted",
                      "graph_file_count", "graph_unparsed_files", "graph_parse_errors",
                      "graph_unreadable_files", "graph_too_large_files",
                      "graph_file_limit_reached", "graph_symbol_limit_reached"):
            with self.subTest(field=field):
                self.assertIn(f"analysis.{field}", self.graph_viewer)
        self.assertIn("Source-analysis completeness is unavailable in this graph snapshot.", self.graph_viewer)

    def test_keyboard_graph_node_keeps_focus_and_announces_selection(self):
        self.assertIn("const focusedNode=svg.contains(document.activeElement)?document.activeElement.dataset.node:null;", self.graph_viewer)
        self.assertIn("aria-pressed=\"${this.selected===n.id}\"", self.graph_viewer)
        self.assertIn("node.dataset.node===focusedNode)?.focus()", self.graph_viewer)

    def test_graph_filters_keep_effect_when_neighborhood_is_focused(self):
        focus = self.graph_viewer.index("if(this.focused&&this.selected)")
        filtered = self.graph_viewer.index("nodes=nodes.filter(n=>(n.name+' '+n.path).toLowerCase().includes(query))")
        self.assertLess(filtered, focus, "focused neighborhood must be intersected with current search results")
        self.assertIn("nodes=nodes.filter(n=>neighbors.has(n.id))", self.graph_viewer)

    def test_graph_controls_have_component_local_names_and_live_result_state(self):
        for control_class in ("graph-level", "graph-search", "graph-relation", "graph-inferred"):
            with self.subTest(control=control_class):
                self.assertRegex(self.graph_viewer, rf'<label(?: class="graph-check")?>[^<]*<(?:select|input) class="{control_class}"')
                self.assertNotRegex(self.graph_viewer, rf'(?:id|for)="{control_class}"')
        self.assertIn('class="graph-caption" role="status" aria-live="polite" aria-atomic="true"', self.graph_viewer)
        self.assertIn('class="graph-empty" aria-hidden="true" hidden', self.graph_viewer)
        self.assertIn("No source nodes were found.", self.graph_viewer)
        self.assertIn("No nodes match the current filters.", self.graph_viewer)

    def test_dashboard_solver_header_does_not_claim_a_live_fixed_timing(self):
        self.assertNotIn("10 NP-Hard Solvers Active (582 µs)", self.html)
        self.assertIn("Solver examples · timings are illustrative", self.html)

    def test_creator_labels_synthetic_demo_separately_from_scanned_repository(self):
        self.assertIn("source_kind:'synthetic_demo'", self.creator_ui)
        self.assertIn("Illustrative synthetic demo; no repository files were analyzed.", self.creator_ui)
        self.assertIn("analysisDescription(report)", self.creator_ui)
        self.assertIn("Illustrative files", self.creator_ui)
        self.assertIn("analysis?.source_kind==='synthetic_demo'", self.creator_ui)
        self.assertIn("analysis.message", self.creator_ui)
        self.assertIn("state.report?.analysis?.source_kind==='bundled_sample'", self.creator_ui)
        self.assertIn("report.url==='local:play-anything'", self.creator_ui)
        self.assertIn("The bundled Play-Anything repository was scanned; no user repository was provided.", self.creator_ui)
        for field in ("source_bytes_read", "source_budget_bytes", "source_budget_exceeded_files", "source_budget_exhausted"):
            with self.subTest(budget_field=field):
                self.assertIn(f"analysis.{field}", self.creator_ui)
        summary_region = re.search(r'<p id="repo-limit"[^>]*>', self.creator_html)
        self.assertIsNotNone(summary_region)
        self.assertIn('role="status"', summary_region.group(0))
        self.assertIn('aria-live="polite"', summary_region.group(0))

    def test_creator_graph_import_is_a_bounded_preview_separate_from_analysis(self):
        self.assertIn('for="graph-preview-file"', self.creator_html)
        self.assertIn('id="graph-preview-file" type="file" accept="application/json,.json"', self.creator_html)
        self.assertIn('id="graph-preview-status" class="help" role="status" aria-live="polite"', self.creator_html)
        self.assertIn('id="imported-graph-preview" hidden', self.creator_html)
        self.assertIn('id="imported-graph-viewer"', self.creator_html)
        self.assertIn('File/import graph preview; analyze the repository above to complete understanding.', self.creator_html)
        preview = re.search(r"\$\('graph-preview-file'\)\.onchange=[\s\S]*?\n  \};", self.creator_ui)
        self.assertIsNotNone(preview)
        self.assertIn('file.size>15000000', preview.group(0))
        self.assertIn("$('imported-graph-viewer').graph=graph", preview.group(0))
        for mutation in ("state.report=", "state.completed=", "state.server=", "save();", "event("):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, preview.group(0))
        self.assertIn('The existing preview, repository analysis, and tutorial status are unchanged.', preview.group(0))
        self.assertIn('graphPreviewGate.invalidate()', self.creator_ui)
        self.assertIn('if(!graphPreviewGate.isCurrent(request))return', preview.group(0))

    def test_graph_page_explicit_snapshot_import_supersedes_startup_load(self):
        self.assertIn("const loadGate=globalThis.playAnythingCreateRequestGate()", self.graph_page)
        self.assertIn("const revision=loadGate.begin(),file=event.target.files[0]", self.graph_page)
        self.assertIn("if(!loadGate.isCurrent(revision))return;show(JSON.parse(text))", self.graph_page)

    def test_main_landmark_closes_before_the_dashboard_script(self):
        self.assertLess(self.html.index("</main>"), self.html.index("<script>", self.html.index("</main>")))


if __name__ == "__main__":
    unittest.main()
