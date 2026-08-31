from app.models.operational_hardening import OperationalEnvironmentSnapshot, OperationalHardeningRequest, OperationalHardeningStatus
from app.services.operational_hardening import build_operational_hardening
def snap(**kw):
    v=dict(repo_exists=True,venv_python_exists=True,git_present=True,ffmpeg_present=True,gitleaks_present=True,certifier_present=True,backup_root_exists=True,resource_governor_available=True,free_space_gb=100,backup_bundle_count=10)
    v.update(kw)
    return OperationalEnvironmentSnapshot(**v)
def test_clean_environment_passes():
    r=build_operational_hardening(OperationalHardeningRequest(snapshot=snap()))
    assert r.status==OperationalHardeningStatus.HARDENING_PASS
    assert r.safe_to_run_pipeline is True
def test_workaround_is_warning_not_hidden():
    r=build_operational_hardening(OperationalHardeningRequest(snapshot=snap(git_network_workaround_required=True)))
    assert r.status==OperationalHardeningStatus.HARDENING_WARN
    assert r.warning_count==1
