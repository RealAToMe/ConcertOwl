from pathlib import Path

from scripts.migrate_from_sheets import _coerce


ROOT = Path(__file__).resolve().parents[1]


def test_migration_numeric_coercion():
    row = _coerce(
        {
            "face_price": "517",
            "observed_price": "600.5",
            "premium_ratio": "",
            "days_to_show": "9.0",
            "days_since_onsale": "",
        }
    )
    assert row["face_price"] == 517.0
    assert row["observed_price"] == 600.5
    assert row["premium_ratio"] is None
    assert row["days_to_show"] == 9
    assert row["days_since_onsale"] is None


def test_collect_workflow_uses_data_branch_not_google_secrets():
    workflow = (ROOT / ".github/workflows/collect.yml").read_text(encoding="utf-8")
    assert "CONCERTOWL_DATA_DIR" in workflow
    assert "worktree add" in workflow
    assert "GOOGLE_CREDENTIALS" not in workflow
    assert "SHEET_ID" not in workflow


def test_excel_workflow_uploads_artifact():
    workflow = (ROOT / ".github/workflows/export-report.yml").read_text(
        encoding="utf-8"
    )
    assert "concertowl.export_excel" in workflow
    assert "actions/upload-artifact" in workflow
