"""
Script to generate synthetic PDF test fixtures using PyMuPDF (fitz).

Creates files under backend/tests/fixtures/:
- simple_text.pdf
- multi_page_text.pdf
- table_attendance.pdf
- ambiguous_table.pdf
- empty_minimal.pdf
"""

from pathlib import Path
import fitz  # PyMuPDF

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def create_simple_text_pdf():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size
    page.insert_text(
        fitz.Point(50, 80),
        "RSSB Office Data Platform - General Notice\n\n"
        "This is a synthetic administrative announcement for center coordinators.\n"
        "All weekly duty rosters and attendance logs must be submitted by Monday 5:00 PM.\n"
        "For transport queries, contact the transport coordinator.\n",
        fontsize=12,
    )
    doc.save(FIXTURES_DIR / "simple_text.pdf")
    doc.close()


def create_multi_page_pdf():
    doc = fitz.open()
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(fitz.Point(50, 80), "Monthly Office Report - Section 1: Overview\n\nGeneral summary of activities for the month.", fontsize=12)

    # Page 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(fitz.Point(50, 80), "Monthly Office Report - Section 2: Coordination Guidelines\n\nStandard operational procedures for satsang centers.", fontsize=12)

    # Page 3
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text(fitz.Point(50, 80), "Monthly Office Report - Section 3: Action Items\n\nSummary of follow-up tasks and deadlines.", fontsize=12)

    doc.save(FIXTURES_DIR / "multi_page_text.pdf")
    doc.close()


def _draw_grid_table(page, x0, y0, col_widths, row_height, table_data):
    """Draw a bordered table and insert text in each cell."""
    num_rows = len(table_data)
    num_cols = len(col_widths)
    total_width = sum(col_widths)
    total_height = num_rows * row_height

    # Draw outer border
    page.draw_rect(fitz.Rect(x0, y0, x0 + total_width, y0 + total_height), color=(0, 0, 0), width=1)

    # Draw horizontal row dividers
    for r in range(1, num_rows):
        y = y0 + r * row_height
        page.draw_line(fitz.Point(x0, y), fitz.Point(x0 + total_width, y), color=(0, 0, 0), width=0.5)

    # Draw vertical column dividers
    curr_x = x0
    for c in range(1, num_cols):
        curr_x += col_widths[c - 1]
        page.draw_line(fitz.Point(curr_x, y0), fitz.Point(curr_x, y0 + total_height), color=(0, 0, 0), width=0.5)

    # Insert cell text
    curr_y = y0
    for r_idx, row in enumerate(table_data):
        curr_x = x0
        for c_idx, cell_text in enumerate(row):
            w = col_widths[c_idx]
            # Center vertically in cell
            text_point = fitz.Point(curr_x + 5, curr_y + row_height - 6)
            font_size = 10 if r_idx == 0 else 9
            page.insert_text(text_point, str(cell_text), fontsize=font_size)
            curr_x += w
        curr_y += row_height


def create_table_attendance_pdf():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(50, 50), "Weekly Attendance Summary Report", fontsize=14)

    table_data = [
        ["Date", "Satsang Ghar", "Attendance Count", "Notes"],
        ["2026-09-06", "Model Town", "520", "Morning session"],
        ["2026-09-13", "Karol Bagh", "410", "Regular sangat"],
        ["2026-09-20", "Rohini Sector 7", "630", "Special gathering"],
    ]
    col_widths = [100, 150, 110, 140]
    _draw_grid_table(page, 50, 80, col_widths, 25, table_data)

    doc.save(FIXTURES_DIR / "table_attendance.pdf")
    doc.close()


def create_ambiguous_table_pdf():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text(fitz.Point(50, 50), "Unclassified Technical Metrics", fontsize=14)

    table_data = [
        ["Code ID", "Alpha Metric", "Beta Score", "Remarks"],
        ["TX-01", "88.4", "1.25", "Standard test"],
        ["TX-02", "91.2", "1.30", "Verified batch"],
    ]
    col_widths = [100, 120, 120, 150]
    _draw_grid_table(page, 50, 80, col_widths, 25, table_data)

    doc.save(FIXTURES_DIR / "ambiguous_table.pdf")
    doc.close()


def create_empty_minimal_pdf():
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # Blank page
    doc.save(FIXTURES_DIR / "empty_minimal.pdf")
    doc.close()


def create_all_pdf_fixtures():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    create_simple_text_pdf()
    create_multi_page_pdf()
    create_table_attendance_pdf()
    create_ambiguous_table_pdf()
    create_empty_minimal_pdf()
    print(f"Created all synthetic PDF fixtures in {FIXTURES_DIR}")


if __name__ == "__main__":
    create_all_pdf_fixtures()
