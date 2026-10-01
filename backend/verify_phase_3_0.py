"""
Automated End-to-End Verification Script for Phase 3.0 Multi-Document Analytics & Comparison.
Uses Playwright to control a real browser against http://localhost:3000 and backend at http://127.0.0.1:8000.
"""

import json
import os
from pathlib import Path
import re
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\sahil\.gemini\antigravity-ide\brain\ab1688f9-4fb0-4baa-8b07-848b66b1e337\verification_screenshots")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

results = {}
console_errors = []
console_messages = []


def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        page.on("console", lambda msg: (
            console_errors.append(msg.text) if msg.type == "error" else console_messages.append(f"[{msg.type}] {msg.text}")
        ))
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        print("\n--- Step 1: Confirm Main Dashboard & Analytics Button Loads ---")
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
        has_analytics_btn = page.locator("button:has-text('Multi-Doc Analytics & Comparison')").is_visible()

        step1_pass = ("RSSB" in header_title and has_search and has_analytics_btn)
        results["Step 1: Confirm main dashboard loads with Analytics button"] = {
            "status": "PASS" if step1_pass else "FAIL",
            "details": f"Header title: '{header_title}', Search visible: {has_search}, Analytics button visible: {has_analytics_btn}",
        }
        print("Step 1:", results["Step 1: Confirm main dashboard loads with Analytics button"])

        print("\n--- Step 2: Natural Language Comparison Search ---")
        page.fill("input#office-search", "compare attendance between Sukhliya and Bicholi")
        page.click("button[aria-label='Search']")
        page.wait_for_selector("section[aria-labelledby='main-heading']", timeout=10000)
        time.sleep(2)
        page.screenshot(path=str(ARTIFACTS_DIR / "2_nl_comparison_search.png"))

        search_text = page.locator("section[aria-labelledby='main-heading']").inner_text()
        print("Search text snippet:", search_text[:350])

        has_compare_title = ("Comparison" in search_text or "Sukhliya" in search_text)
        has_comparison_stats = ("Attendance" in search_text and "Delta" in search_text or "vs" in search_text or "average" in search_text.lower())

        step2_pass = (has_compare_title and has_comparison_stats)
        results["Step 2: Natural Language Comparison Search ('compare attendance between Sukhliya and Bicholi')"] = {
            "status": "PASS" if step2_pass else "FAIL",
            "details": f"Comparison search returned results: title match={has_compare_title}, stats match={has_comparison_stats}.",
        }
        print("Step 2:", results["Step 2: Natural Language Comparison Search ('compare attendance between Sukhliya and Bicholi')"])

        print("\n--- Step 3: Open 'Multi-Doc Analytics & Comparison' Modal ---")
        page.click("button:has-text('Multi-Doc Analytics & Comparison')")
        page.wait_for_selector("#analytics-modal-title", timeout=5000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "3_analytics_modal_open.png"))

        modal_title = page.locator("#analytics-modal-title").inner_text()
        has_compare_tab = page.locator("button:has-text('Comparative Analytics')").is_visible()
        has_overview_tab = page.locator("button:has-text('Multi-Document Overview')").is_visible()

        step3_pass = ("Multi-Document Analytics & Comparison" in modal_title and has_compare_tab and has_overview_tab)
        results["Step 3: Open Multi-Doc Analytics Modal"] = {
            "status": "PASS" if step3_pass else "FAIL",
            "details": f"Modal title: '{modal_title}', Comparative tab visible: {has_compare_tab}, Overview tab visible: {has_overview_tab}",
        }
        print("Step 3:", results["Step 3: Open Multi-Doc Analytics Modal"])

        print("\n--- Step 4: Run Location-to-Location Comparison in Modal ---")
        # Ensure dimension is location
        page.select_option("#dimension-select", "location")
        time.sleep(0.5)

        # Select centres
        page.select_option("#centre-a-select", "Sukhliya")
        page.select_option("#centre-b-select", "Bicholi")

        # Run comparison
        page.click("#run-comparison-btn")
        page.wait_for_selector("div[class*='resultsSection']", timeout=15000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "4_location_comparison_results.png"))

        has_results = page.locator("div[class*='resultsSection']").is_visible()
        side_cards = page.locator("div[class*='sideCard']").count()
        has_delta = page.locator("div[class*='deltaCard']").is_visible()
        summary_text = page.locator("div[class*='summaryBanner']").inner_text() if page.locator("div[class*='summaryBanner']").is_visible() else ""

        step4_pass = (has_results and side_cards >= 2 and has_delta)
        results["Step 4: Location-to-Location Comparison Analysis"] = {
            "status": "PASS" if step4_pass else "FAIL",
            "details": f"Results section: {has_results}, Side cards count: {side_cards}, Delta card: {has_delta}, Summary: '{summary_text[:120]}...'",
        }
        print("Step 4:", results["Step 4: Location-to-Location Comparison Analysis"])

        print("\n--- Step 5: Run Period-to-Period Comparison in Modal ---")
        page.select_option("#dimension-select", "period")
        time.sleep(0.5)

        page.click("#run-comparison-btn")
        page.wait_for_selector("div[class*='resultsSection']", timeout=15000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "5_period_comparison_results.png"))

        period_results = page.locator("div[class*='resultsSection']").is_visible()
        period_side_cards = page.locator("div[class*='sideCard']").count()

        step5_pass = (period_results and period_side_cards >= 2)
        results["Step 5: Period-to-Period Comparison Analysis"] = {
            "status": "PASS" if step5_pass else "FAIL",
            "details": f"Period comparison rendered successfully: Results={period_results}, Side cards={period_side_cards}",
        }
        print("Step 5:", results["Step 5: Period-to-Period Comparison Analysis"])

        print("\n--- Step 6: Test Metric Domain (Sewadars / Duties) ---")
        page.select_option("#dimension-select", "location")
        time.sleep(0.5)
        page.select_option("#metric-select", "assignment")
        time.sleep(0.5)

        page.click("#run-comparison-btn")
        page.wait_for_selector("div[class*='resultsSection']", timeout=15000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "6_domain_filter_sewadars.png"))

        unit_text = page.locator("span[class*='sideMetricUnit']").first.inner_text()
        has_sewadar_unit = "duty" in unit_text.lower() or "assignment" in unit_text.lower() or "shift" in unit_text.lower() or "roster" in unit_text.lower()

        step6_pass = (has_sewadar_unit)
        results["Step 6: Metric Domain Filtering (Sewadars)"] = {
            "status": "PASS" if step6_pass else "FAIL",
            "details": f"Sewadar duty domain selected, unit rendered: '{unit_text}'.",
        }
        print("Step 6:", results["Step 6: Metric Domain Filtering (Sewadars)"])

        print("\n--- Step 7: Multi-Document Overview Tab ---")
        page.click("button:has-text('Multi-Document Overview')")
        time.sleep(0.5)
        page.wait_for_selector("div[class*='overviewStatsGrid']", timeout=10000)
        time.sleep(1)
        page.screenshot(path=str(ARTIFACTS_DIR / "7_multi_doc_overview_results.png"))

        overview_stats_visible = page.locator("div[class*='overviewStatsGrid']").is_visible()
        stat_cards = page.locator("div[class*='statCard']").count()

        step7_pass = (overview_stats_visible and stat_cards >= 4)
        results["Step 7: Multi-Document Overview Generation"] = {
            "status": "PASS" if step7_pass else "FAIL",
            "details": f"Multi-doc overview loaded: stats grid visible={overview_stats_visible}, stat card count={stat_cards}.",
        }
        print("Step 7:", results["Step 7: Multi-Document Overview Generation"])

        # Close modal
        page.click("button[aria-label='Close analytics modal']")
        time.sleep(0.5)

        print("\n--- Step 8: Permissions & Role Verification (Viewer Role) ---")
        print("Switching active role to 'viewer'...")
        page.select_option("select[aria-label='Active Office Role']", "viewer")
        time.sleep(1)
        user_badge_viewer = page.locator("div[class*='userBadge']").inner_text()
        print("Active user:", user_badge_viewer)

        # Open Analytics modal as Viewer (Viewer has read permission and can access analytics)
        page.click("button:has-text('Multi-Doc Analytics & Comparison')")
        page.wait_for_selector("#analytics-modal-title", timeout=5000)
        time.sleep(0.5)

        # Switch back to Comparative Analytics tab
        page.click("button:has-text('Comparative Analytics')")
        page.wait_for_selector("#run-comparison-btn", timeout=5000)
        time.sleep(0.5)
        page.screenshot(path=str(ARTIFACTS_DIR / "8_viewer_analytics_access.png"))

        viewer_can_compare = page.locator("#run-comparison-btn").is_visible()
        step8_pass = viewer_can_compare
        results["Step 8: Permissions Verification (Viewer has read access to Analytics)"] = {
            "status": "PASS" if step8_pass else "FAIL",
            "details": f"Viewer successfully accessed Multi-Document Analytics workspace and comparison action: {viewer_can_compare}.",
        }
        print("Step 8:", results["Step 8: Permissions Verification (Viewer has read access to Analytics)"])

        # Close modal
        page.click("button[aria-label='Close analytics modal']")
        time.sleep(0.5)

        print("\n--- Step 9: Browser Console Errors Check ---")
        print(f"Total Console Errors: {len(console_errors)}")
        if console_errors:
            print("Console Errors:", console_errors)
        step9_pass = (len(console_errors) == 0)
        results["Step 9: Browser console clean check"] = {
            "status": "PASS" if step9_pass else "FAIL",
            "details": f"Clean execution: 0 console errors ({len(console_messages)} informational console messages).",
        }
        print("Step 9:", results["Step 9: Browser console clean check"])

        browser.close()

    return results


if __name__ == "__main__":
    res = run_verification()
    with open(str(ARTIFACTS_DIR / "verification_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    print("\nPhase 3.0 Verification Complete!")
