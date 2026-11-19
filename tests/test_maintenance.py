import json
from datetime import datetime, timedelta, timezone

import st_maintenance as m

def test_parse_interval_defaults_when_block_missing():
    assert m.parse_maintenance_block(None) == (7, None)
    assert m.parse_maintenance_block({}) == (7, None)

def test_parse_interval_accepts_valid():
    assert m.parse_maintenance_block({"interval_days": 3}) == (3, None)

def test_parse_interval_rejects_invalid_values():
    for bad in (0, -1, 2.5, "7", True, [], None):
        days, warning = m.parse_maintenance_block({"interval_days": bad})
        assert days == 7 and warning and "interval_days" in warning

def test_parse_interval_rejects_non_object_block():
    days, warning = m.parse_maintenance_block([])
    assert days == 7 and warning

def test_read_state_missing_file(tmp_path):
    assert m.read_state(tmp_path / "yok.json") == (None, None)

def test_read_state_roundtrip(tmp_path):
    iso = "2026-11-11T12:00:00+00:00"
    p = tmp_path / "maintenance.json"
    p.write_text(json.dumps({"last_reminded": iso}))
    assert m.read_state(p) == (iso, None)

def test_read_state_corrupt_variants(tmp_path):
    p = tmp_path / "maintenance.json"
    for text in ("{ not json", "[]", '{"other": 1}',
                 '{"last_reminded": 5}', '{"last_reminded": "dün"}'):
        p.write_text(text)
        last, warning = m.read_state(p)
        assert last is None and warning

def test_compute_days_since_whole_days():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-11T12:00:00+00:00", now) == 7
    assert m.compute_days_since("2026-11-11T12:30:00+00:00", now) == 6  # 6 gün 23.5 saat

def test_compute_days_since_naive_treated_as_utc():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-11T12:00:00", now) == 7

def test_compute_days_since_future_clamps_zero():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.compute_days_since("2026-11-25T12:00:00+00:00", now) == 0

def test_is_due_never_reminded():
    assert m.is_due(None, 7, datetime.now(timezone.utc)) is True

def test_is_due_boundary():
    now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
    assert m.is_due("2026-11-11T12:00:00+00:00", 7, now) is True   # tam 7 gün
    assert m.is_due("2026-11-11T12:00:01+00:00", 7, now) is False  # 7 günden az

def test_fill_percent_missing_dir(tmp_path):
    assert m.memory_fill_percent(tmp_path / "yok") is None

def test_fill_percent_empty_dir(tmp_path):
    (tmp_path / "memories").mkdir()
    assert m.memory_fill_percent(tmp_path / "memories") == 0

def test_fill_percent_single_file(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "MEMORY.md").write_text("a" * 2112)  # 2112 / 2200 = %96
    assert m.memory_fill_percent(d) == 96

def test_fill_percent_user_file_alone(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "USER.md").write_text("a" * 275)     # 275 / 1375 = %20; MEMORY.md yok
    assert m.memory_fill_percent(d) == 20

def test_fill_percent_caps_at_100(tmp_path):
    d = tmp_path / "memories"; d.mkdir()
    (d / "MEMORY.md").write_text("a" * 10000)
    assert m.memory_fill_percent(d) == 100

def test_build_reminder_full():
    assert m.build_reminder(3, 87) == (
        "🧹 Hafıza bakımı bekliyor (son bakım 3 gün önce; hafıza %87 dolu) — "
        "'bakım yapalım' dersen memory-maintenance skill'iyle başlarım."
    )

def test_build_reminder_without_fill():
    assert m.build_reminder(3, None) == (
        "🧹 Hafıza bakımı bekliyor (son bakım 3 gün önce) — "
        "'bakım yapalım' dersen memory-maintenance skill'iyle başlarım."
    )

def test_build_reminder_first_run():
    text = m.build_reminder(None, 87)
    assert "henüz bakım kaydı yok" in text and "son bakım" not in text

def test_reminder_line_fits_budget():
    text = m.build_reminder(99999, 100)
    assert len(text) <= 200 and "\n" not in text

def test_update_last_reminded_creates_and_updates(tmp_path):
    p = tmp_path / "nested" / "maintenance.json"
    m.update_last_reminded(p, "2026-11-18T00:00:00+00:00")
    assert json.loads(p.read_text()) == {"last_reminded": "2026-11-18T00:00:00+00:00"}
    m.update_last_reminded(p, "2026-11-19T00:00:00+00:00")
    assert json.loads(p.read_text()) == {"last_reminded": "2026-11-19T00:00:00+00:00"}
