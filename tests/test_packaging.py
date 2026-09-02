"""Guards against shipping a repo that cannot be cloned and run.

An unanchored `config/` line in .gitignore once matched backend/config/ as well as
the repo-root runtime directory, silently excluding the whole config package. Every
fresh clone then died with `ModuleNotFoundError: No module named 'backend.config'`
while the working copy kept running fine. These tests make that class of mistake fail
here instead of on someone else's machine.
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _tracked() -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return set(out.stdout.split())


def test_every_backend_source_file_is_tracked():
    """Anything the app imports at runtime must survive a clone."""
    tracked = _tracked()
    missing = [
        str(p.relative_to(ROOT))
        for p in sorted(ROOT.joinpath("backend").rglob("*"))
        if p.is_file()
        and p.suffix in {".py", ".json", ".txt"}
        and "__pycache__" not in p.parts
        and str(p.relative_to(ROOT)) not in tracked
    ]
    assert not missing, (
        "these backend files are not tracked by git, so a fresh clone would not have "
        f"them: {missing}. Check .gitignore for an unanchored directory pattern.")


def test_every_python_package_under_backend_has_an_init():
    pkgs = [p for p in ROOT.joinpath("backend").rglob("*")
            if p.is_dir() and "__pycache__" not in p.parts
            and any(c.suffix == ".py" for c in p.iterdir() if c.is_file())]
    missing = [str(p.relative_to(ROOT)) for p in pkgs if not (p / "__init__.py").exists()]
    assert not missing, f"missing __init__.py, so these will not import: {missing}"


def test_runtime_dirs_are_ignored_but_only_at_the_repo_root():
    """/config/ and /data/ are generated at runtime and must stay out of the repo —
    but anchored, so they cannot swallow a same-named package deeper in the tree."""
    lines = [ln.strip() for ln in (ROOT / ".gitignore").read_text().splitlines()]
    for name in ("config", "data"):
        assert f"/{name}/" in lines, f"expected an anchored '/{name}/' rule"
        assert f"{name}/" not in lines, (
            f"unanchored '{name}/' matches that directory at ANY depth, including "
            f"backend/{name}/. Anchor it as '/{name}/'.")


def test_artifacts_needed_at_startup_are_tracked():
    tracked = _tracked()
    required = ["graph.pt", "normalization.json", "chains.json",
                "bstan_seed0.pt", "bstan_seed1.pt", "bstan_seed2.pt"]
    missing = [f for f in required if f"artifacts/{f}" not in tracked]
    assert not missing, f"artifacts a clone needs to boot are not tracked: {missing}"
