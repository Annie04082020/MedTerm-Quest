import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_plan", Path(__file__).parents[1] / "scripts/release_plan.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
plan = module.release_plan


def test_main_build_version_matches_android_version():
    assert plan("push", "refs/heads/main", "12") == {"tag": "v0.6.12", "version": "0.6.12", "prerelease": "false"}


def test_taskdesk_style_tag_and_manual_versions():
    assert plan("push", "refs/tags/v1.2.3", "13")["version"] == "1.2.3"
    assert plan("workflow_dispatch", "refs/heads/main", "14", "v0.7.0-beta.1")["prerelease"] == "true"


@pytest.mark.parametrize("value", ["v1.0.0\nevil=1", "v1.0.0;echo unsafe", "../main", "v1", "v01.2.3"])
def test_unsafe_or_ambiguous_tags_are_rejected(value):
    with pytest.raises(ValueError):
        plan("workflow_dispatch", "refs/heads/main", "15", value)


@pytest.mark.parametrize("number", ["0", "-1", "x", "2100000000"])
def test_android_version_code_bounds(number):
    with pytest.raises(ValueError):
        plan("push", "refs/heads/main", number)
