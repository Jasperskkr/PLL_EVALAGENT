"""Source ZIP metadata must not require Git or weaken source/protocol locks."""
from types import SimpleNamespace
import pytest
import tools.run_stage41 as historical


@pytest.mark.parametrize('missing_executable',[False,True])
def test_exported_source_explicit_no_git_identity(monkeypatch,missing_executable):
    def unavailable(*args,**kwargs):
        if missing_executable:raise FileNotFoundError('git')
        return SimpleNamespace(returncode=128,stdout='')
    monkeypatch.setattr(historical.subprocess,'run',unavailable)
    assert historical.checkout_identity()=={'HEAD':None,'checkout_kind':'SOURCE_ARCHIVE_NO_GIT'}


def test_git_identity_kept_when_available(monkeypatch):
    monkeypatch.setattr(historical.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='abc123\n'))
    assert historical.checkout_identity()=={'HEAD':'abc123','checkout_kind':'GIT_CHECKOUT'}
