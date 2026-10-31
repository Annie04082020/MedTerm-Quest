"""Mocked CPU tests must not contend with a real user's GPU job."""
import pytest


@pytest.fixture(autouse=True)
def isolated_processing_lock(tmp_path,monkeypatch):
    from backend import local_processing
    monkeypatch.setattr(local_processing,'PROCESSING_LOCK_PATH',tmp_path/'processing.lock')
