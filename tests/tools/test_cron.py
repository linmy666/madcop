"""v1.6.0 — Tests for the cron scheduler."""
from __future__ import annotations

import time
import pytest
from pathlib import Path

from madcop.tools.cron import (
    CronJob,
    CronStore,
    CronScheduler,
    parse_cron,
    should_run,
    next_run_seconds,
)


# --------------------------------------------------------------------------- #
# Cron expression parser
# --------------------------------------------------------------------------- #


class TestParseCron:
    def test_star(self):
        d = parse_cron("* * * * *")
        assert all(d[k] == "*" for k in ("minute", "hour", "dom", "month", "dow"))

    def test_every_n_minutes(self):
        d = parse_cron("*/5 * * * *")
        assert d["minute"] == ("every", 5)

    def test_fixed_values(self):
        d = parse_cron("30 14 1 6 0")
        assert d["minute"] == 30
        assert d["hour"] == 14
        assert d["dom"] == 1
        assert d["month"] == 6
        assert d["dow"] == 0

    def test_invalid_field_count(self):
        with pytest.raises(ValueError):
            parse_cron("* * *")
        with pytest.raises(ValueError):
            parse_cron("* * * * * *")


# --------------------------------------------------------------------------- #
# should_run
# --------------------------------------------------------------------------- #


class TestShouldRun:
    def test_every_minute_always_runs(self):
        d = parse_cron("* * * * *")
        t = time.struct_time((2026, 6, 26, 12, 30, 0, 3, 177, 0))
        assert should_run(d, t)

    def test_every_5_minutes(self):
        d = parse_cron("*/5 * * * *")
        t_match = time.struct_time((2026, 6, 26, 12, 30, 0, 3, 177, 0))
        t_nomatch = time.struct_time((2026, 6, 26, 12, 33, 0, 3, 177, 0))
        assert should_run(d, t_match)
        assert not should_run(d, t_nomatch)

    def test_fixed_hour_and_minute(self):
        d = parse_cron("30 14 * * *")
        t_match = time.struct_time((2026, 6, 26, 14, 30, 0, 3, 177, 0))
        t_nomatch = time.struct_time((2026, 6, 26, 14, 31, 0, 3, 177, 0))
        assert should_run(d, t_match)
        assert not should_run(d, t_nomatch)

    def test_fixed_dow(self):
        # Sunday in cron = 0, Sunday in struct_time = 6
        d = parse_cron("* * * * 0")  # every Sunday
        t_sunday = time.struct_time((2026, 6, 28, 12, 0, 0, 6, 179, 0))  # Sunday
        t_monday = time.struct_time((2026, 6, 29, 12, 0, 0, 0, 180, 0))  # Monday
        assert should_run(d, t_sunday)
        assert not should_run(d, t_monday)


# --------------------------------------------------------------------------- #
# next_run_seconds
# --------------------------------------------------------------------------- #


class TestNextRunSeconds:
    def test_every_5_minutes(self):
        d = parse_cron("*/5 * * * *")
        assert next_run_seconds(d) == 300  # 5 * 60

    def test_every_minute(self):
        d = parse_cron("* * * * *")
        assert next_run_seconds(d) == 60


# --------------------------------------------------------------------------- #
# CronStore
# --------------------------------------------------------------------------- #


class TestCronStore:
    def test_add_and_get(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        job = CronJob(id="daily-report", goal="Write daily report",
                      schedule="0 9 * * *", mode="standard")
        store.add(job)
        retrieved = store.get("daily-report")
        assert retrieved is not None
        assert retrieved.goal == "Write daily report"
        assert retrieved.schedule == "0 9 * * *"
        store.close()

    def test_list_all(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="job1", goal="A", schedule="* * * * *"))
        store.add(CronJob(id="job2", goal="B", schedule="*/10 * * * *"))
        jobs = store.list_all()
        assert len(jobs) == 2
        store.close()

    def test_list_enabled(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="job1", goal="A", schedule="* * * * *", enabled=True))
        store.add(CronJob(id="job2", goal="B", schedule="* * * * *", enabled=False))
        enabled = store.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].id == "job1"
        store.close()

    def test_remove(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="temp", goal="x", schedule="* * * * *"))
        assert store.remove("temp") is True
        assert store.get("temp") is None
        assert store.remove("nonexistent") is False
        store.close()

    def test_update_after_run(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="counter", goal="x", schedule="* * * * *"))
        store.update_after_run("counter", "2026-06-26T12:00:00Z")
        job = store.get("counter")
        assert job.run_count == 1
        assert job.last_run == "2026-06-26T12:00:00Z"
        store.close()

    def test_set_enabled(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="toggle", goal="x", schedule="* * * * *", enabled=True))
        store.set_enabled("toggle", False)
        job = store.get("toggle")
        assert job.enabled is False
        store.close()

    def test_persistence_across_connections(self, tmp_path):
        db = tmp_path / "cron.db"
        store1 = CronStore(db)
        store1.add(CronJob(id="persist", goal="survive", schedule="0 0 * * *"))
        store1.close()

        store2 = CronStore(db)
        job = store2.get("persist")
        assert job is not None
        assert job.goal == "survive"
        store2.close()


# --------------------------------------------------------------------------- #
# CronScheduler (background thread)
# --------------------------------------------------------------------------- #


class TestCronScheduler:
    def test_start_and_stop(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        fired = []
        scheduler = CronScheduler(store, lambda job: fired.append(job.id), check_interval=1)
        scheduler.start()
        import time as _t
        _t.sleep(0.2)
        # Thread should be alive right after start
        scheduler.stop()
        # After stop, thread should be done
        assert scheduler._thread is None or not scheduler._thread.is_alive()
        store.close()

    def test_job_fires_on_schedule(self, tmp_path):
        """Add a * * * * * job and wait for it to fire."""
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="frequent", goal="test goal", schedule="* * * * *"))

        fired = []
        scheduler = CronScheduler(
            store,
            lambda job: fired.append(job.id),
            check_interval=1,
        )
        scheduler.start()
        # Wait up to 65 seconds for the next minute tick
        # But for tests, we'll manually trigger the check
        import time as _time
        now = _time.localtime()
        scheduler._check_and_fire(now)
        scheduler.stop()
        store.close()

        # The job should fire if it matches the current minute
        # (* * * * * always matches, so it should always fire)
        assert "frequent" in fired

    def test_disabled_job_does_not_fire(self, tmp_path):
        store = CronStore(tmp_path / "cron.db")
        store.add(CronJob(id="disabled", goal="x", schedule="* * * * *", enabled=False))
        fired = []
        scheduler = CronScheduler(store, lambda job: fired.append(job.id))
        now = time.localtime()
        scheduler._check_and_fire(now)
        scheduler.stop()
        store.close()
        assert len(fired) == 0
