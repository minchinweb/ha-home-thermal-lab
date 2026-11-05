"""Invoke tasks; run with ``uv run invoke --list``."""

from __future__ import annotations

from invoke import task

try:
    from minchin.releaser import make_release  # noqa: F401
except ImportError:
    print("[WARN] minchin.releaser not installed.")


@task
def update(ctx):
    """Refresh `uv.lock` with the newest allowed versions (like `apt update`)."""
    ctx.run("uv lock --upgrade", pty=False)


@task
def upgrade(ctx):
    """Install what's in `uv.lock` into `.venv` (like `apt upgrade`)."""
    ctx.run("uv sync", pty=False)


@task
def lint(ctx):
    """Check code, formatting and `pyproject.toml`; changes nothing."""
    ctx.run("uv run ruff check", pty=False)
    ctx.run("uv run ruff format --check", pty=False)
    ctx.run("uv run validate-pyproject pyproject.toml", pty=False)
    ctx.run("uv run taplo format --check pyproject.toml", pty=False)


# named `format_code` so it doesn't shadow the builtin (ruff rule `A`)
@task(name="format")
def format_code(ctx):
    """Apply safe lint fixes, import sorting and formatting (code and TOML)."""
    # unfixable problems exit non-zero; still format, `lint` reports them
    ctx.run("uv run ruff check --fix", pty=False, warn=True)
    ctx.run("uv run ruff format", pty=False)
    ctx.run("uv run taplo format pyproject.toml", pty=False)


@task
def test(ctx):
    """Run the test suite."""
    ctx.run("uv run pytest", pty=False)


@task(pre=[lint, test])
def check(ctx):
    """Everything CI runs: lint, formatting and tests."""
