"""The Dataform repo root file `definitions/workflow_settings.yaml` is not
committed — it is regenerated from `env/config/setting.yaml` by
`scripts/sync_dataform_config.py` (Makefile: `make sync-dataform-config`)
before any Dataform compile. CI runs the generator in both ci.yml and
deploy-dataform.yml.

This test verifies that the generator's `render()` output reflects the
current `setting.yaml` for every required Dataform key. If it fails, the
generator or setting.yaml is out of sync — not the workflow_settings.yaml
file (which is gitignored).
"""

from __future__ import annotations

from pathlib import Path

from scripts.config.sync_dataform import REQUIRED_KEYS, render

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTING_YAML = REPO_ROOT / "env" / "config" / "setting.yaml"


def _flat_yaml(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


def test_generator_includes_every_required_dataform_key() -> None:
    rendered = _flat_yaml(render())
    expected_keys = {
        "defaultProject",
        "defaultLocation",
        "defaultDataset",
        "defaultAssertionDataset",
        "dataformCoreVersion",
    }
    missing = expected_keys - rendered.keys()
    assert not missing, f"render() omitted Dataform keys: {missing}"


def test_generator_values_match_setting_yaml() -> None:
    setting = _flat_yaml(SETTING_YAML.read_text(encoding="utf-8"))
    rendered = _flat_yaml(render())

    expected = {
        "defaultProject": setting["project_id"],
        "defaultLocation": setting["region"],
        "defaultDataset": setting["dataform_default_dataset"],
        "defaultAssertionDataset": setting["dataform_default_assertion_dataset"],
        "dataformCoreVersion": setting["dataform_core_version"],
    }
    drift = {k: (rendered.get(k), v) for k, v in expected.items() if rendered.get(k) != v}
    assert not drift, (
        f"sync_dataform_config.render() drifted from setting.yaml: {drift}\n"
        "Fix scripts/sync_dataform_config.py or env/config/setting.yaml."
    )


def test_setting_yaml_has_all_required_keys() -> None:
    """Guard against silently dropping a Dataform-relevant key from setting.yaml."""
    setting = _flat_yaml(SETTING_YAML.read_text(encoding="utf-8"))
    required = {k.lower() for k in REQUIRED_KEYS}
    missing = required - setting.keys()
    assert not missing, f"env/config/setting.yaml is missing keys: {missing}"
