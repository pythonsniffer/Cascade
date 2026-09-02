"""End-to-end UI test (run manually — needs a running backend + frontend).

    .venv/bin/uvicorn backend.main:app --port 8000 &
    cd frontend && npm run dev &          # or `npm run preview` for the built bundle
    .venv/bin/python tests/e2e_ui.py

Kept out of the pytest suite deliberately: it needs two live servers and a browser,
where tests/ runs offline in seconds.

End-to-end UI test: navigation, station interaction, live WS, alerts, charts,
config editing, error states, responsive behaviour."""
import json, os, sys, tempfile, urllib.request
from playwright.sync_api import sync_playwright

# Playwright finds its own browser unless one is pinned here
CHROME = os.environ.get("CASCADE_E2E_CHROME") or None
SHOTS = os.environ.get("CASCADE_E2E_SHOTS", tempfile.mkdtemp(prefix="cascade-e2e-"))
UI = os.environ.get("CASCADE_E2E_UI", "http://localhost:5173")
API = os.environ.get("CASCADE_E2E_API", "http://127.0.0.1:8000")

results, errors = [], []
def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{extra}]" if extra else ""))

def post(path):
    urllib.request.urlopen(urllib.request.Request(API + path, method="POST"), timeout=20).read()

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, executable_path=CHROME)
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))
    page.on("console", lambda m: errors.append(f"[console.error] {m.text}")
            if m.type == "error" else None)

    print("\n== navigation ==")
    page.goto(UI); page.wait_for_load_state("networkidle"); page.wait_for_timeout(1500)
    for label, expect_text in [("Quality", "Detector model card"), ("Profit & loss", "Net projected"),
                               ("History", "Show last"), ("Settings", "Line controls"),
                               ("What's real", "What is real")]:
        page.get_by_role("link", name=label).click()
        page.wait_for_timeout(900)
        check(f"nav → {label}", expect_text.lower() in page.inner_text("body").lower())
    page.get_by_role("link", name="Live twin").click(); page.wait_for_timeout(900)

    print("\n== deep links serve the app, not the API ==")
    # Regression guard: /pnl, /history and /config are BOTH frontend routes and REST
    # endpoints. A weak "the page has text" assertion missed this once, because
    # Chromium renders raw JSON in a viewer that looks like a rendered page.
    for route in ("/pnl", "/history", "/config"):
        r = urllib.request.urlopen(UI + route, timeout=20)
        ctype = r.headers.get("content-type", "")
        body = r.read(400).decode("utf-8", "replace")
        check(f"{route} serves HTML, not JSON",
              "text/html" in ctype and body.lstrip().lower().startswith("<!doctype html"),
              ctype)

    print("\n== live floor + station interaction ==")
    markers = page.locator('svg [role="button"][aria-label^="Station S"]')
    check("35 station markers from /line", markers.count() == 35, f"got {markers.count()}")
    markers.nth(7).click(); page.wait_for_timeout(700)
    card = page.get_by_role("dialog", name="Station S7 detail")
    check("station click opens detail card", card.is_visible())
    check("card shows blockage/starvation", "blockage" in card.inner_text().lower())
    page.screenshot(path=f"{SHOTS}/station-card.png")
    card.get_by_role("button", name="Close station detail").click(); page.wait_for_timeout(500)
    check("card dismisses via ×", page.get_by_role("dialog").count() == 0)

    print("\n== status strip filters ==")
    strip = page.get_by_label("Station status")
    total = strip.get_by_role("tab").first.inner_text()
    strip.get_by_role("tab", name="Bottleneck").click(); page.wait_for_timeout(500)
    cards = strip.locator("button[aria-pressed]")
    check("bottleneck filter narrows the strip", cards.count() <= 2, f"{cards.count()} cards")
    strip.get_by_role("tab", name="All").click(); page.wait_for_timeout(400)
    check("all filter restores 35", strip.locator("button[aria-pressed]").count() == 35)

    print("\n== live websocket updates ==")
    before = page.locator("h2").first.inner_text()
    pill_before = page.locator('[role="status"]').first.inner_text()
    check("live pill reports a connection", "Connected" in pill_before or "Live" in pill_before,
          pill_before)
    net_before = page.inner_text("body")
    post("/control/tick"); page.wait_for_timeout(2000)
    net_after = page.inner_text("body")
    check("UI updates from a WS tick without reload", net_before != net_after)

    print("\n== play / pause ==")
    page.get_by_role("button", name="Play").first.click(); page.wait_for_timeout(1200)
    check("play switches the pill to Live",
          "Live" in page.locator('[role="status"]').first.inner_text(),
          page.locator('[role="status"]').first.inner_text())
    page.wait_for_timeout(3000)
    page.get_by_role("button", name="Pause").first.click(); page.wait_for_timeout(1000)
    check("pause returns to paused",
          "paused" in page.locator('[role="status"]').first.inner_text().lower())

    print("\n== P&L ==")
    page.get_by_role("link", name="Profit & loss").click(); page.wait_for_timeout(1500)
    body = page.inner_text("body")
    check("mandatory disclaimer present", "not measured savings" in body.lower())
    check("breakdown shown, not a bare number", "Value from bottleneck" in body)
    check("sources legend present", "your assumption" in body.lower())
    field = page.get_by_role("spinbutton", name="Downtime cost per min")
    old = field.input_value()
    headline = page.locator("p.font-display").first.inner_text()
    field.fill(str(float(old) * 3)); field.press("Enter"); page.wait_for_timeout(2500)
    new_headline = page.locator("p.font-display").first.inner_text()
    check("editing an assumption re-projects instantly", headline != new_headline,
          f"{headline} → {new_headline}")
    page.screenshot(path=f"{SHOTS}/pnl.png")
    page.get_by_role("button", name="Reset to defaults").click(); page.wait_for_timeout(2000)
    check("reset restores the default assumption",
          page.get_by_role("spinbutton", name="Downtime cost per min").input_value() == old,
          page.get_by_role("spinbutton", name="Downtime cost per min").input_value())
    check("audit note shown after edit", "Last changed" in page.inner_text("body"))

    print("\n== charts ==")
    page.get_by_role("link", name="History").click(); page.wait_for_timeout(2000)
    svgs = page.locator(".recharts-surface")
    check("history renders recharts surfaces", svgs.count() >= 3, f"{svgs.count()} charts")
    page.screenshot(path=f"{SHOTS}/history.png")

    print("\n== quality honesty ==")
    page.get_by_role("link", name="Quality").click(); page.wait_for_timeout(1500)
    q = page.inner_text("body")
    det = json.loads(urllib.request.urlopen(API + "/health", timeout=20)
                     .read())["models"]["defect"]
    if det["state"] == "no_detector":
        # metrics must be withheld: this instance cannot stand behind them
        check("detector-off state is explicit", "not loaded" in q.lower())
        check("detector metrics withheld when unloaded", "0.901" not in q)
    else:
        # detector present: its own checkpoint numbers may be shown, and if it has
        # no frames the page must say so rather than implying it is inspecting.
        check("loaded detector shows its recorded metrics", "mAP50" in q)
        check("idle detector says why it is quiet",
              det["state"] == "ready" or "no camera frames" in q.lower(), det["state"])
    page.screenshot(path=f"{SHOTS}/quality.png")

    print("\n== about page is API-driven ==")
    page.get_by_role("link", name="What's real").click(); page.wait_for_timeout(1200)
    a = page.inner_text("body")
    check("about shows measured bottleneck RMSE", "2.689" in a, )
    check("about shows chain recovery", "3 of 3" in a or "3/3" in a or "Recovered 3" in a)
    check("about explains the fixed 35 stations", "35 stations" in a)
    page.screenshot(path=f"{SHOTS}/about.png")

    print("\n== settings ==")
    page.get_by_role("link", name="Settings").click(); page.wait_for_timeout(1500)
    cam = page.get_by_role("spinbutton", name="Station for cam_paint_2")
    prev = cam.input_value()
    cam.fill("19"); cam.press("Enter"); page.wait_for_timeout(1800)
    check("camera map edit persists",
          page.get_by_role("spinbutton", name="Station for cam_paint_2").input_value() == "19")
    check("edit is audited", "mappings" in page.inner_text("body"))
    cam.fill(prev); cam.press("Enter"); page.wait_for_timeout(1500)
    page.screenshot(path=f"{SHOTS}/config.png")

    print("\n== error state ==")
    bad = ctx.new_page()
    bad.route("**/api/**", lambda r: r.abort())
    bad.goto(UI); bad.wait_for_timeout(2500)
    check("backend-down shows a recovery message", "Can't reach the twin" in bad.inner_text("body"))
    bad.screenshot(path=f"{SHOTS}/error-state.png")
    bad.close()

    print("\n== responsive ==")
    for w, h, name in [(1280, 800, "laptop"), (900, 1200, "tablet"), (420, 900, "phone")]:
        pg = b.new_context(viewport={"width": w, "height": h}).new_page()
        pg.goto(UI); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1500)
        scroll_w = pg.evaluate("document.documentElement.scrollWidth")
        check(f"{name} {w}px has no horizontal page scroll", scroll_w <= w + 2,
              f"scrollWidth={scroll_w}")
        pg.screenshot(path=f"{SHOTS}/responsive-{name}.png")
        pg.close()

    b.close()

print("\n--- runtime errors ---")
uniq = list(dict.fromkeys(errors))
print("\n".join(e[:220] for e in uniq) if uniq else "none")
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n==== {passed}/{len(results)} checks passed ====")
sys.exit(0 if passed == len(results) else 1)
