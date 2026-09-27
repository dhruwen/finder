"""Detects software-project directories so the restructure wizard never
reorganizes source code, dependency trees, or version control history.

Finder is built for tidying document archives (contracts, invoices, audits,
client deliverables) — not for rearranging a codebase's folder layout, which
restructuring would actively break: relative imports stop resolving, a git
repository's tracked paths get scrambled, `node_modules`/`.venv` trees (often
tens of thousands of files) would be pointlessly torn apart. This module is
consulted only by restructure planning; search and indexing are read-only
and unaffected, so files inside a project folder are still fully findable.
"""
from __future__ import annotations

from pathlib import Path

# Presence of any of these directly inside a folder marks that folder (and
# everything below it) as a software project — never a restructure target.
PROJECT_MARKER_NAMES: frozenset[str] = frozenset({
    ".git", ".hg", ".svn",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "node_modules",
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
    "Pipfile", "Pipfile.lock", ".venv", "venv",
    "Cargo.toml", "go.mod", "go.sum",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "Gemfile.lock", "composer.json",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "CMakeLists.txt",
    "tsconfig.json", "webpack.config.js", "vite.config.js", "next.config.js",
})
_PROJECT_MARKER_SUFFIXES: tuple[str, ...] = (
    ".xcodeproj", ".xcworkspace", ".sln", ".csproj",
)


def is_project_marker_dir(directory: Path) -> bool:
    """True if `directory` directly contains a software-project marker."""
    try:
        names = [entry.name for entry in directory.iterdir()]
    except OSError:
        return False
    if any(n in PROJECT_MARKER_NAMES for n in names):
        return True
    return any(n.endswith(_PROJECT_MARKER_SUFFIXES) for n in names)


def build_project_exclusion_set(all_dirs: set[Path], root: Path) -> set[Path]:
    """Given every directory that appears among a tree's files, return the
    subset that IS a project directory or lives inside one — memoized
    bottom-up (root's ancestors first) so each directory's marker check
    happens exactly once regardless of how many files/subfolders reuse it.
    """
    memo: dict[Path, bool] = {}
    root = root.resolve()

    def inside_project(d: Path) -> bool:
        if d in memo:
            return memo[d]
        if is_project_marker_dir(d):
            memo[d] = True
            return True
        if d == root or d.parent == d:
            memo[d] = False
            return False
        result = inside_project(d.parent)
        memo[d] = result
        return result

    return {d for d in all_dirs if inside_project(d)}
