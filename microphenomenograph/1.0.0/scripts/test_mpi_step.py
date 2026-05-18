"""Phase 1 unit tests for mpi_step.py — CLI scaffolding."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

import mpi_step
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id
from _mpi_schemas import validate_units


# ---------------------------------------------------------------------------
# _mpi_atomic tests
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, '{"x": 1}')
        assert p.read_text() == '{"x": 1}'

    def test_write_is_atomic_no_tmp_leftover(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, "hello")
        assert not (tmp_path / "out.json.tmp").exists()

    def test_write_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "old")
        atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.txt"
        atomic_write(p, "deep")
        assert p.read_text() == "deep"


class TestAppendJsonl:
    def test_append_creates_and_appends(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"a": 1})
        append_jsonl(p, {"b": 2})
        lines = p.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_append_idempotent_under_re_read(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"event": "test"})
        content_a = p.read_text()
        # Re-reading the file does not change it
        assert p.read_text() == content_a


class TestLoadOrCreateRunId:
    def test_creates_uuid_if_absent(self, tmp_path):
        p = tmp_path / "run_id"
        rid = load_or_create_run_id(p)
        import uuid
        uuid.UUID(rid)  # raises if not valid UUID
        assert p.exists()

    def test_returns_existing_if_present(self, tmp_path):
        p = tmp_path / "run_id"
        p.write_text("my-fixed-id\n")
        assert load_or_create_run_id(p) == "my-fixed-id"


# ---------------------------------------------------------------------------
# _mpi_schemas tests
# ---------------------------------------------------------------------------

class TestValidateUnits:
    def test_accepts_known_stage(self):
        errors = validate_units("diachronic", "criteria_grouping", {})
        assert errors == []

    def test_rejects_unknown_stage(self):
        errors = validate_units("bad_stage", "x", {})
        assert errors
        assert any("stage" in e.field for e in errors)

    def test_rejects_non_dict(self):
        errors = validate_units("diachronic", "criteria_grouping", ["list"])
        assert errors
        assert any("payload" in e.field for e in errors)


# ---------------------------------------------------------------------------
# CLI --help tests (AC2.2)
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_top_level_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "close" in r.stdout
        assert "render" in r.stdout

    def test_close_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "close", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--actor" in r.stdout
        assert "--stage" in r.stdout
        assert "--substep" in r.stdout
        assert "--prompt-artifact" in r.stdout

    def test_init_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "init", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--run" in r.stdout
        assert "--allow-active-repo-nested" in r.stdout


# ---------------------------------------------------------------------------
# init subcommand tests (AC33.*)
# ---------------------------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def _setup_git_identity(run_dir):
    """Set git identity in run_dir so init doesn't fail on AC33.6."""
    _git(["config", "--local", "user.name", "Test User"], cwd=run_dir)
    _git(["config", "--local", "user.email", "test@example.com"], cwd=run_dir)


class TestInitDedicatedRepo:
    def test_init_in_empty_dir_succeeds(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Pre-init repo with identity so test is isolated from global config
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc == 0
        assert (run_dir / ".mpi" / "project.json").exists()

    def test_init_sets_autocrlf_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.autocrlf"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_sets_hooks_path(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.hooksPath"], cwd=run_dir)
        assert r.stdout.strip() == ".git/hooks-disabled"
        assert (run_dir / ".git" / "hooks-disabled").is_dir()

    def test_init_sets_gpgsign_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "commit.gpgsign"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_manifest_records_dedicated_mode(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "dedicated"


class TestInitActiveRepoNesting:
    def test_init_inside_nonempty_repo_fails_by_default(self, tmp_path):
        # Create a non-empty repo
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        # Try to init a run inside it
        run_dir = outer / "run"
        run_dir.mkdir()
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0

    def test_init_with_allow_flag_succeeds(self, tmp_path):
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        run_dir = outer / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir), "--allow-active-repo-nested"])
        assert rc == 0
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "nested_in_active"


class TestInitIdentityRequired:
    def test_init_fails_without_identity(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        # Ensure no global identity leaks in by patching _git_identity_set
        monkeypatch.setattr(mpi_step, "_git_identity_set", lambda cwd: False)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0


# ---------------------------------------------------------------------------
# Static source inspection tests (AC33.7)
# ---------------------------------------------------------------------------

class TestLocalOnlyDefault:
    def test_mpi_step_never_calls_git_push(self):
        """AC33.7: mpi_step.py must never call 'git push' (static source check)."""
        source = (SCRIPTS_DIR / "mpi_step.py").read_text()
        # Check that the source does not contain the string "git push"
        # (either as subprocess call or in a git command list)
        assert '"push"' not in source, \
            "mpi_step.py should never call 'git push'; found quoted 'push' string"
        assert "'push'" not in source, \
            "mpi_step.py should never call 'git push'; found quoted 'push' string"

    def test_mpi_step_never_calls_git_remote_add(self):
        """AC33.7: mpi_step.py must never call 'git remote add' (static source check)."""
        source = (SCRIPTS_DIR / "mpi_step.py").read_text()
        # Check that the source does not contain the string "remote add"
        assert '"remote", "add"' not in source and "'remote', 'add'" not in source and \
               '"add"' not in source.split("remote")[0:], \
            "mpi_step.py should never call 'git remote add'"
        # More targeted: no 'remote add' substring at all
        assert "remote add" not in source, \
            "mpi_step.py should never call 'git remote add'; found 'remote add' string"
