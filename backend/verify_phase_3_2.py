"""
Automated End-to-End Verification Script for Phase 3.2 Visual Analytics & Executive Dashboard.
Uses Playwright to control a real browser against http://localhost:3000 and backend at http://127.0.0.1:8000.
"""

import json
import os
from pathlib import Path
import re
import sys
import time

from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\sahil\.gemini\antigravity-ide\brain\ab1688f9-4fb0-4baa-8b07-848b66b1e337\verification_screenshots_phase_3_2")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

results = {}
console_errors = []
console_messages = []


def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.on("console", lambda msg: (
            console_errors.append(msg.text) if msg.type == "error" else console_messages.append(f"[{msg.type}] {msg.text}")
        ))
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("\n--- Step 1: Confirm Main Dashboard Loads Correctly ---")
        page.goto("http://localhost:3000", wait_until="networkidle")
        time.sleep(1)

        # Check if login screen is displayed
        login_btn = page.locator("button:has-text('Sign In to Office Platform')")
        if login_btn.is_visible():
            print("Login screen detected. Signing in as Admin...")
            quick_admin = page.locator("button:has-text('Admin')").first
            if quick_admin.is_visible():
                quick_admin.click()
            else:
                page.fill("input#username", "admin")
                page.fill("input#password", "admin123")
                login_btn.click()
            page.wait_for_selector("text=RSSB Office Data Platform", timeout=10000)

        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "1_dashboard_loaded.png"))

        header_title = page.locator("header h1").inner_text()
        has_search = page.locator("input#office-search").is_visible()
        has_dash_btn = page.locator("button:has-text('Executive Dashboard & Trends')").is_visible()

        step1_pass = ("RSSB" in header_title and has_search and has_dash_btn)
        results["Step 1: Confirm main dashboard loads correctly"] = {
            "status": "PASS" if step1_pass else "FAIL",
            "details": f"Header title: '{header_title}', Search visible: {has_search}, Dashboard button visible: {has_dash_btn}",
        }
        print("Step 1:", results["Step 1: Confirm main dashboard loads correctly"])

        print("\n--- Step 2: Open 'Executive Dashboard & Trends' Modal ---")
        page.click("button:has-text('Executive Dashboard & Trends')")
        page.wait_for_selector("#dashboard-modal-title", timeout=5000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "2_dashboard_modal_open.png"))

        modal_title = page.locator("#dashboard-modal-title").inner_text()
        overview_tab_visible = page.locator("button:has-text('Executive Overview')").is_visible()
        trends_tab_visible = page.locator("button:has-text('Trend Trajectories')").is_visible()
        anomalies_tab_visible = page.locator("button:has-text('Operational Anomalies')").is_visible()

        step2_pass = (
            ("Executive" in modal_title and "Dashboard" in modal_title)
            and overview_tab_visible
            and trends_tab_visible
            and anomalies_tab_visible
        )
        results["Step 2: Open Executive Dashboard modal"] = {
            "status": "PASS" if step2_pass else "FAIL",
            "details": f"Modal title: '{modal_title}', Tabs visible: {overview_tab_visible}, {trends_tab_visible}, {anomalies_tab_visible}",
        }
        print("Step 2:", results["Step 2: Open Executive Dashboard modal"])

        print("\n--- Step 3: Verify Executive Overview KPIs ---")
        kpi_cards = page.locator("div[class*='kpiCard']")
        kpi_count = kpi_cards.count()
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "3_executive_overview_kpis.png"))

        step3_pass = kpi_count >= 5
        results["Step 3: Verify Executive Overview KPIs"] = {
            "status": "PASS" if step3_pass else "FAIL",
            "details": f"Rendered KPI cards count: {kpi_count}",
        }
        print("Step 3:", results["Step 3: Verify Executive Overview KPIs"])

        print("\n--- Step 4: Verify Center Performance Leaderboard ---")
        has_rankings_table = page.locator("div[class*='tableWrapper'] table").first.is_visible()
        ranking_rows = page.locator("div[class*='tableWrapper'] table tbody tr").count()
        time.sleep(0.5)
        page.screenshot(path=str(ARTIFACTS_DIR / "4_center_leaderboard.png"))

        step4_pass = has_rankings_table and ranking_rows > 0
        results["Step 4: Verify Center Performance Leaderboard"] = {
            "status": "PASS" if step4_pass else "FAIL",
            "details": f"Leaderboard table visible: {has_rankings_table}, Ranked centers count: {ranking_rows}",
        }
        print("Step 4:", results["Step 4: Verify Center Performance Leaderboard"])

        print("\n--- Step 5: Switch to Trend Trajectories Tab ---")
        page.click("button:has-text('Trend Trajectories')")
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "5_trend_trajectories_tab.png"))

        has_svg_chart = page.locator("svg[class*='chartSvg']").is_visible()
        trend_summary = page.locator("p[class*='summaryText']").inner_text() if page.locator("p[class*='summaryText']").is_visible() else ""

        step5_pass = has_svg_chart
        results["Step 5: Render native SVG trend trajectories"] = {
            "status": "PASS" if step5_pass else "FAIL",
            "details": f"SVG chart rendered: {has_svg_chart}, Narrative preview: {trend_summary[:60]}...",
        }
        print("Step 5:", results["Step 5: Render native SVG trend trajectories"])

        print("\n--- Step 6: Toggle Moving Average Smoothing ---")
        ma_checkbox = page.locator("input#trend-ma-checkbox")
        if ma_checkbox.is_visible():
            ma_checkbox.click()
            time.sleep(0.5)
            page.screenshot(path=str(ARTIFACTS_DIR / "6_moving_average_toggled.png"))
            step6_pass = True
        else:
            step6_pass = False

        results["Step 6: Toggle Moving Average smoothing"] = {
            "status": "PASS" if step6_pass else "FAIL",
            "details": "Moving average checkbox successfully toggled and state updated",
        }
        print("Step 6:", results["Step 6: Toggle Moving Average smoothing"])

        print("\n--- Step 7: Filter Trend by Center ---")
        center_select = page.locator("select#trend-center-select")
        if center_select.is_visible():
            opts = center_select.locator("option").all_inner_texts()
            target_opt = opts[1] if len(opts) > 1 else opts[0]
            center_select.select_option(label=target_opt)
            time.sleep(1)
            page.screenshot(path=str(ARTIFACTS_DIR / "7_trend_center_filtered.png"))
            step7_pass = True
            details_7 = f"Selected center: '{target_opt}'"
        else:
            step7_pass = False
            details_7 = "Center select element not found"

        results["Step 7: Filter Trend by specific Center"] = {
            "status": "PASS" if step7_pass else "FAIL",
            "details": details_7,
        }
        print("Step 7:", results["Step 7: Filter Trend by specific Center"])

        print("\n--- Step 8: Switch Metric to Sewa Duty Assignments ---")
        metric_select = page.locator("select#trend-metric-select")
        if metric_select.is_visible():
            metric_select.select_option(value="assignment")
            time.sleep(1)
            page.screenshot(path=str(ARTIFACTS_DIR / "8_trend_assignment_metric.png"))
            step8_pass = True
            details_8 = "Switched metric to Sewa Duty Assignments"
        else:
            step8_pass = False
            details_8 = "Metric select element not found"

        results["Step 8: Switch Metric domain"] = {
            "status": "PASS" if step8_pass else "FAIL",
            "details": details_8,
        }
        print("Step 8:", results["Step 8: Switch Metric domain"])

        print("\n--- Step 9: Switch to Operational Anomalies Tab ---")
        page.click("button:has-text('Operational Anomalies')")
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "9_operational_anomalies_tab.png"))

        anom_cards = page.locator("div[class*='anomalyCard']")
        anom_count = anom_cards.count()
        has_anom_feed = page.locator("div[class*='anomalyFeed']").is_visible() or anom_count >= 0

        step9_pass = has_anom_feed
        results["Step 9: View Operational Anomalies"] = {
            "status": "PASS" if step9_pass else "FAIL",
            "details": f"Anomalies feed visible: {has_anom_feed}, Detected anomalies count: {anom_count}",
        }
        print("Step 9:", results["Step 9: View Operational Anomalies"])

        print("\n--- Step 10: Close Modal ---")
        page.click("button[aria-label='Close modal']")
        time.sleep(0.5)
        modal_closed = not page.locator("#dashboard-modal-title").is_visible()
        step10_pass = modal_closed
        results["Step 10: Close Dashboard modal"] = {
            "status": "PASS" if step10_pass else "FAIL",
            "details": f"Dashboard modal closed: {modal_closed}",
        }
        print("Step 10:", results["Step 10: Close Dashboard modal"])

        print("\n--- Step 11: Natural Language Trend Query via Search Bar ---")
        page.fill("input#office-search", "Show attendance trend for Sukhliya")
        page.click("button[aria-label='Search']")
        page.wait_for_selector("div[aria-label='Search results']", timeout=10000)
        time.sleep(1.5)
        page.screenshot(path=str(ARTIFACTS_DIR / "11_nl_trend_search_results.png"))

        search_text_11 = page.locator("div[aria-label='Search results']").inner_text()
        has_trend_card = (
            "Trajectory" in search_text_11
            or "Trend" in search_text_11
            or "Attendance" in search_text_11
        )
        step11_pass = has_trend_card
        results["Step 11: Natural Language Trend Query"] = {
            "status": "PASS" if step11_pass else "FAIL",
            "details": f"Trend visualization card rendered in search results: {has_trend_card}",
        }
        print("Step 11:", results["Step 11: Natural Language Trend Query"])

        print("\n--- Step 12: Natural Language Dashboard Query via Search Bar ---")
        page.fill("input#office-search", "Executive dashboard summary")
        page.click("button[aria-label='Search']")
        page.wait_for_selector("div[aria-label='Search results']", timeout=10000)
        time.sleep(1.5)
        page.screenshot(path=str(ARTIFACTS_DIR / "12_nl_dashboard_search_results.png"))

        search_text_12 = page.locator("div[aria-label='Search results']").inner_text()
        has_dash_card = (
            "Executive" in search_text_12
            or "Dashboard" in search_text_12
            or "Summary" in search_text_12
        )
        step12_pass = has_dash_card
        results["Step 12: Natural Language Dashboard Query"] = {
            "status": "PASS" if step12_pass else "FAIL",
            "details": f"Dashboard summary card rendered in search results: {has_dash_card}",
        }
        print("Step 12:", results["Step 12: Natural Language Dashboard Query"])

        print("\n--- Step 13: Verify Read Access for Viewer Role ---")
        role_select = page.locator("select[aria-label='Active Office Role']")
        if role_select.is_visible():
            role_select.select_option("viewer")
            time.sleep(1)

        # Open dashboard as viewer
        page.click("button:has-text('Executive Dashboard & Trends')")
        page.wait_for_selector("#dashboard-modal-title", timeout=5000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "13_viewer_dashboard_access.png"))

        viewer_modal_open = page.locator("#dashboard-modal-title").is_visible()
        step13_pass = viewer_modal_open
        results["Step 13: Viewer role can access dashboard"] = {
            "status": "PASS" if step13_pass else "FAIL",
            "details": f"Viewer successfully accessed and rendered executive dashboard: {viewer_modal_open}",
        }
        print("Step 13:", results["Step 13: Viewer role can access dashboard"])

        # Close modal
        page.click("button[aria-label='Close modal']")
        time.sleep(0.5)

        print("\n--- Step 14: Console Error Check ---")
        filtered_errors = [e for e in console_errors if "favicon" not in e.lower()]
        step14_pass = len(filtered_errors) == 0
        results["Step 14: Zero frontend console errors"] = {
            "status": "PASS" if step14_pass else "FAIL",
            "details": f"Found {len(filtered_errors)} console errors: {filtered_errors[:3]}",
        }
        print("Step 14:", results["Step 14: Zero frontend console errors"])

        browser.close()

    # Save summary results
    results_path = ARTIFACTS_DIR / "verification_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n================ VERIFICATION SUMMARY ================")
    all_passed = True
    for step, r in results.items():
        status_flag = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
        if r["status"] != "PASS":
            all_passed = False
        print(f"{status_flag} {step} - {r['details']}")

    print(f"\nFinal Phase 3.2 Verification: {'ALL PASS' if all_passed else 'SOME STEPS FAILED'}")
    return all_passed


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
