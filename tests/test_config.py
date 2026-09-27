from app.core.config import Settings


def test_settings_defaults():
    s = Settings()
    assert s.default_file_action == "ask"
    assert s.use_ai_suggestions is True
    assert s.show_mismatch_warnings is True
    assert s.ask_before_rebuild is True


def test_settings_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.app_data_dir", lambda: tmp_path)

    s = Settings()
    s.default_file_action = "open_file"
    s.use_ai_suggestions = False
    s.roots = ["/some/folder"]
    s.save()

    loaded = Settings.load()
    assert loaded.default_file_action == "open_file"
    assert loaded.use_ai_suggestions is False
    assert loaded.roots == ["/some/folder"]


def test_settings_load_ignores_unknown_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.app_data_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text(
        '{"default_file_action": "open_location", "some_future_field": 123}',
        encoding="utf-8",
    )
    loaded = Settings.load()
    assert loaded.default_file_action == "open_location"
    assert not hasattr(loaded, "some_future_field")
