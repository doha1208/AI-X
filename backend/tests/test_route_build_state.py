from app.services.route_build_state import builder_lock, update_builder_state, read_builder_state


def test_only_one_builder_can_hold_the_directory(tmp_path):
    with builder_lock(tmp_path) as first:
        assert first
        with builder_lock(tmp_path) as second:
            assert not second
    with builder_lock(tmp_path) as restarted:
        assert restarted


def test_state_updates_keep_diagnostics_and_do_not_expose_paths(tmp_path):
    update_builder_state(tmp_path, status="preparing", environment_ready=False)
    update_builder_state(tmp_path, last_checked_at="2026-11-04T00:00:00+00:00")
    state = read_builder_state(tmp_path)
    assert state["status"] == "preparing"
    assert state["environment_ready"] is False
    assert state["last_checked_at"] == "2026-11-04T00:00:00+00:00"
