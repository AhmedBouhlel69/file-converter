"""The model diagnostic must not launch blocked work or strand owned workers."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bgremove import readiness


@pytest.fixture
def tool():
    path = Path(__file__).resolve().parents[2] / "tools" / "verify_background_models.py"
    spec = importlib.util.spec_from_file_location("model_verifier_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_readiness(monkeypatch, statuses):
    """Substitute artifact checks while retaining the real exit-code policy."""
    def check(profile=None, **_kwargs):
        selected = [profile] if profile else list(statuses)
        return {
            "available_memory_bytes": 4 * 1024**3,
            "profiles": [
                {
                    "profile": name,
                    "status": statuses[name],
                    "installed": True,
                    "verified": True,
                    "cpu_ready": statuses[name] == "ready",
                    "reason": "startup policy result",
                }
                for name in selected
            ],
        }

    monkeypatch.setattr(readiness, "check_models", check)


def forbid_children(monkeypatch, tool):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Readiness-only or blocked models must not launch inference")

    monkeypatch.setattr(tool.subprocess, "Popen", forbidden)


def saved_report(directory):
    paths = list(directory.glob("run-*/report.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def test_default_readiness_writes_verified_not_inferred_without_child(tool, monkeypatch, tmp_path):
    install_readiness(monkeypatch, {"fast": "ready", "balanced": "ready"})
    forbid_children(monkeypatch, tool)

    assert tool.main(["--report-dir", str(tmp_path)]) == 0

    report = saved_report(tmp_path)
    assert report["mode"] == "readiness"
    assert [item["profile"] for item in report["profiles"]] == ["fast", "balanced"]
    assert all(item["verified"] for item in report["profiles"])
    assert all(not item["inference_tested"] for item in report["profiles"])
    assert {item["verification_status"] for item in report["profiles"]} == {"ready_not_tested"}


def test_explicit_run_of_ram_blocked_profiles_never_launches(tool, monkeypatch, tmp_path):
    install_readiness(monkeypatch, {"quality": "resource_blocked", "portrait": "resource_blocked"})
    forbid_children(monkeypatch, tool)
    source = tmp_path / "input.png"
    source.write_bytes(b"not decoded because startup checks must block inference")
    reports = tmp_path / "reports"

    code = tool.main(["--run", "--input", str(source), "--report-dir", str(reports)])

    assert code == 5
    report = saved_report(reports)
    assert [entry["profile"] for entry in report["profiles"]] == ["quality", "portrait"]
    assert all(entry["verification_status"] == "blocked" for entry in report["profiles"])
    assert all(not entry["inference_tested"] for entry in report["profiles"])
    assert not any(path.name == "stdout.log" for path in reports.rglob("*"))


class OwnedProcess:
    def __init__(self, pid, *, rss=32, descendants=()):
        self.pid = pid
        self.rss = rss
        self.descendants = list(descendants)
        self.killed = False

    def children(self, recursive):
        assert recursive
        return self.descendants

    def memory_info(self):
        return SimpleNamespace(rss=self.rss)

    def kill(self):
        self.killed = True


class ChildHandle:
    def __init__(self, owner):
        self.pid = owner.pid
        self.owner = owner
        self.reaped = False

    def poll(self):
        return -9 if self.owner.killed else None

    def kill(self):
        self.owner.kill()

    def wait(self, timeout):
        assert timeout > 0
        assert self.owner.killed, "The worker must be stopped before waiting for its exit"
        self.reaped = True
        return -9


@pytest.fixture
def owned_family(tool, monkeypatch):
    descendant = OwnedProcess(701, rss=30)
    owner = OwnedProcess(700, rss=50, descendants=[descendant])
    unrelated = OwnedProcess(999, rss=10_000)
    child = ChildHandle(owner)
    waited = []

    def process(pid):
        assert pid == child.pid, "Only the Popen-owned PID may be inspected"
        return owner

    monkeypatch.setattr(tool.psutil, "Process", process)
    monkeypatch.setattr(tool.psutil, "wait_procs", lambda processes, timeout: waited.extend(processes))
    monkeypatch.setattr(tool.psutil, "virtual_memory", lambda: SimpleNamespace(available=2_000))
    return SimpleNamespace(owner=owner, descendant=descendant, unrelated=unrelated,
                           child=child, waited=waited)


def test_memory_guard_stops_and_reaps_only_its_process_family(tool, owned_family):
    family = owned_family

    result = tool.monitor_child(family.child, min_free_bytes=100, max_rss_bytes=75, timeout=60)

    assert "RSS limit" in result["guard_reason"]
    assert result["peak_process_tree_rss_bytes"] == 80
    assert family.owner.killed and family.descendant.killed and family.child.reaped
    assert not family.unrelated.killed
    assert set(family.waited) == {family.owner, family.descendant}


def test_interrupted_monitor_stops_owned_family_before_propagating(tool, monkeypatch, owned_family):
    def interrupt(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(tool.time, "sleep", interrupt)
    family = owned_family

    with pytest.raises(KeyboardInterrupt):
        tool.monitor_child(family.child, min_free_bytes=100, max_rss_bytes=1_000, timeout=60)

    assert family.owner.killed and family.descendant.killed and family.child.reaped
    assert not family.unrelated.killed
    assert set(family.waited) == {family.owner, family.descendant}


def test_interruption_during_initial_memory_sample_still_cleans_up(tool, monkeypatch, owned_family):
    def interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(tool.psutil, "virtual_memory", interrupt)
    family = owned_family

    with pytest.raises(KeyboardInterrupt):
        tool.monitor_child(family.child, min_free_bytes=100, max_rss_bytes=1_000, timeout=60)

    assert family.owner.killed and family.descendant.killed and family.child.reaped
    assert not family.unrelated.killed


def test_identity_setup_interruption_reaps_the_popen_handle(tool, monkeypatch, owned_family):
    def interrupt(_pid):
        raise KeyboardInterrupt

    monkeypatch.setattr(tool.psutil, "Process", interrupt)
    family = owned_family

    with pytest.raises(KeyboardInterrupt):
        tool.monitor_child(family.child, min_free_bytes=100, max_rss_bytes=1_000, timeout=60)

    assert family.owner.killed and family.child.reaped
    assert not family.unrelated.killed
    # No process identity was established, so cleanup must use Popen's own
    # retained handle rather than looking up arbitrary machine processes.
    assert family.waited == []
