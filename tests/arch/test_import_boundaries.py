"""Architectural boundary checks — enforced at CI time via AST.

The canonical ruleset and the AST scanner live in
``scripts/checks/layers.py``; this test module just wraps every entry of
``RULES`` in its own pytest case so a failure points cleanly at the
offending file. To add a rule, edit ``scripts/checks/layers.py::RULES``
(do NOT duplicate the dict here).

Composition-root wiring in ``*/adapters.py`` and ``*/main.py`` is exempt.
The check is intentionally shallow: each file is inspected at every
``Import`` / ``ImportFrom`` node — top-level AND inside functions — so
lazy imports cannot smuggle a forbidden dependency back in. Transitive
imports via adapters are allowed (that is the whole point of
Port/Adapter).
"""

from __future__ import annotations

import pytest

from scripts.checks.layers import REPO_ROOT, RULES, find_violations


@pytest.mark.parametrize("rel_path", sorted(RULES))
def test_no_forbidden_imports(rel_path: str) -> None:
    assert (REPO_ROOT / rel_path).exists(), f"source file missing: {rel_path}"

    violations = find_violations(rel_path)
    assert not violations, (
        f"{rel_path} imports forbidden modules: "
        f"{[(v.imported, v.banned_prefix) for v in violations]}. "
        "Move external-SDK / concrete-adapter usage into the adapters/composition root."
    )
