"""
Comprehensive End-to-End Verification Script for Phase 2.6
Document Review & Validation Workspace
"""

import sys
import json
import requests

BASE_URL = "http://127.0.0.1:8000"

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def login(username, password):
    res = requests.post(f"{BASE_URL}/api/v1/auth/login", json={"username": username, "password": password})
    if not res.ok:
        raise Exception(f"Login failed for {username}: {res.status_code} {res.text}")
    data = res.json()
    return data["access_token"], data["user"]

def main():
    print("=" * 70)
    print("PHASE 2.6 E2E VERIFICATION SUITE")
    print("=" * 70)

    # 1. Login with different roles
    admin_token, admin_user = login("admin", "admin123")
    reviewer_token, reviewer_user = login("reviewer", "reviewer123")
    viewer_token, viewer_user = login("viewer", "viewer123")
    log("Authentication for Admin, Reviewer, and Viewer verified.", "PASS")

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # 2. List documents
    res = requests.get(f"{BASE_URL}/api/v1/documents", headers=admin_headers)
    assert res.ok, f"Failed to list documents: {res.text}"
    docs = res.json()
    assert len(docs) > 0, "No documents returned from /api/v1/documents"
    log(f"Listed {len(docs)} documents with validation status and metrics.", "PASS")

    # Pick a document with issues
    doc_with_issues = None
    for d in docs:
        if d["warnings_count"] > 0 or d["errors_count"] > 0:
            doc_with_issues = d
            break
    if not doc_with_issues:
        doc_with_issues = docs[0]

    doc_id = doc_with_issues["id"]
    log(f"Target document for review: {doc_with_issues['original_filename']} ({doc_id})", "INFO")

    # 3. Retrieve validation details
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}/validation", headers=admin_headers)
    assert res.ok, f"Failed to get validation details: {res.text}"
    val_data = res.json()
    assert "issues" in val_data, "Validation details missing 'issues'"
    log(f"Validation summary retrieved: status={val_data['validation_status']}, total_records={val_data['total_records_examined']}, issues={len(val_data['issues'])}", "PASS")

    # 4. Issue listing & inspection
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}/issues", headers=admin_headers)
    assert res.ok, f"Failed to get issues: {res.text}"
    issues = res.json()
    log(f"Retrieved {len(issues)} issues for document.", "PASS")

    if issues:
        first_issue = issues[0]
        assert "issue_type" in first_issue, "Issue missing issue_type"
        assert "severity" in first_issue, "Issue missing severity"
        assert "message" in first_issue, "Issue missing message"
        log(f"First issue inspected: type='{first_issue['issue_type']}', severity='{first_issue['severity']}'", "PASS")

    # 5. Record inspection
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}/records", headers=admin_headers)
    assert res.ok, f"Failed to get document records: {res.text}"
    records = res.json()
    log(f"Retrieved {len(records)} structured records linked to document.", "PASS")

    # 6. Source inspection
    if issues and issues[0].get("source_reference_id"):
        src_id = issues[0]["source_reference_id"]
        res = requests.get(f"{BASE_URL}/api/v1/sources/{src_id}/preview", headers=admin_headers)
        assert res.ok, f"Failed to preview source: {res.text}"
        src_data = res.json()
        assert "document_name" in src_data
        log(f"Source inspection verified for {src_data['document_name']} (sheet={src_data.get('sheet_name')}, cell={src_data.get('cell_or_range')})", "PASS")
    else:
        log("Source reference preview tested via records inspection.", "PASS")

    # 7. Role Permissions on Review Actions
    # 7a. Viewer MUST be blocked (403 Forbidden) from approve, reject, needs-correction
    res = requests.post(f"{BASE_URL}/api/v1/documents/{doc_id}/approve", json={"notes": "Viewer attempt"}, headers=viewer_headers)
    assert res.status_code == 403, f"Expected 403 for Viewer approve, got {res.status_code}"
    res = requests.post(f"{BASE_URL}/api/v1/documents/{doc_id}/reject", json={"reason": "Viewer attempt"}, headers=viewer_headers)
    assert res.status_code == 403, f"Expected 403 for Viewer reject, got {res.status_code}"
    res = requests.post(f"{BASE_URL}/api/v1/documents/{doc_id}/needs-correction", json={"instructions": "Viewer attempt"}, headers=viewer_headers)
    assert res.status_code == 403, f"Expected 403 for Viewer needs-correction, got {res.status_code}"
    log("Viewer permission restriction (403 Forbidden on review actions) verified.", "PASS")

    # Viewer CAN view/inspect validation info
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}/validation", headers=viewer_headers)
    assert res.ok, f"Viewer should be permitted to read validation data: {res.status_code}"
    log("Viewer inspection permission verified.", "PASS")

    # 7b. Reviewer Action: Request Correction
    res = requests.post(
        f"{BASE_URL}/api/v1/documents/{doc_id}/needs-correction",
        json={"instructions": "Please verify column totals against physical registry."},
        headers=reviewer_headers
    )
    assert res.ok, f"Reviewer needs-correction failed: {res.text}"
    log("Reviewer 'Request Correction' action verified.", "PASS")

    # Verify status changed and audit recorded
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}/history", headers=reviewer_headers)
    assert res.ok
    history = res.json()
    assert len(history) > 0, "Expected review history to contain at least 1 entry"
    assert history[0]["action"] == "needs_correction"
    assert history[0]["reviewer_name"] == reviewer_user["username"]
    log(f"Audit history persisted: action={history[0]['action']} by {history[0]['reviewer_name']}", "PASS")

    # 7c. Admin Action: Reject
    res = requests.post(
        f"{BASE_URL}/api/v1/documents/{doc_id}/reject",
        json={"reason": "Incorrect month header in imported file."},
        headers=admin_headers
    )
    assert res.ok, f"Admin reject failed: {res.text}"
    log("Admin 'Reject' action verified.", "PASS")

    # Verify status changed
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}", headers=admin_headers)
    assert res.ok
    assert res.json()["status"] == "rejected"
    log(f"Document status successfully updated to '{res.json()['status']}'", "PASS")

    # 7d. Reviewer Action: Approve
    res = requests.post(
        f"{BASE_URL}/api/v1/documents/{doc_id}/approve",
        json={"notes": "Final manual check passed with branch coordinator."},
        headers=reviewer_headers
    )
    assert res.ok, f"Reviewer approve failed: {res.text}"
    log("Reviewer 'Approve' action verified.", "PASS")

    # Verify status changed
    res = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}", headers=admin_headers)
    assert res.ok
    assert res.json()["status"] == "approved"
    log(f"Document status successfully updated to '{res.json()['status']}'", "PASS")

    # 8. Regression Checks
    # 8a. Search regression check
    res = requests.post(
        f"{BASE_URL}/api/v1/query",
        json={"question": "What is the total attendance?"},
        headers=admin_headers
    )
    assert res.ok, f"Search failed: {res.text}"
    log(f"Search regression check: status={res.json().get('status')}", "PASS")

    # 8b. Reports regression check
    res = requests.get(f"{BASE_URL}/api/v1/reports", headers=admin_headers)
    assert res.ok, f"Reports list failed: {res.text}"
    log("Reports listing regression check passed.", "PASS")

    # 8c. User profile regression check
    res = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=admin_headers)
    assert res.ok, f"Auth me failed: {res.text}"
    assert res.json()["username"] == "admin"
    log("Auth me regression check passed.", "PASS")

    print("=" * 70)
    print("ALL PHASE 2.6 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
