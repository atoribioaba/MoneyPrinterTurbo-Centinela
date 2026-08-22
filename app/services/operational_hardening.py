from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from typing import Any
from app.models.operational_hardening import *
def _hash(v:Any)->str: return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest().upper()
def build_operational_hardening(request:OperationalHardeningRequest)->OperationalHardeningPlan:
    s=request.snapshot; f=[]
    def add(fid,severity,detail): f.append(OperationalFinding(finding_id=fid,severity=severity,detail=detail))
    required={"repo":s.repo_exists,"venv_python":s.venv_python_exists,"git":s.git_present,"ffmpeg":s.ffmpeg_present,"gitleaks":s.gitleaks_present,"certifier":s.certifier_present,"backup_root":s.backup_root_exists,"resource_governor":s.resource_governor_available}
    for name,ok in required.items():
        if not ok: add(f"missing_{name}",FindingSeverity.BLOCK,f"required capability missing: {name}")
    if s.free_space_gb < 5: add("disk_critical",FindingSeverity.BLOCK,f"free_space_gb={s.free_space_gb:.2f}")
    elif s.free_space_gb < 20: add("disk_low",FindingSeverity.WARN,f"free_space_gb={s.free_space_gb:.2f}")
    if s.backup_bundle_count==0: add("no_checkpoint_bundles",FindingSeverity.WARN,"no checkpoint bundles detected")
    if s.git_network_workaround_required: add("git_network_workaround",FindingSeverity.WARN,"normal Windows resolver/Schannel path is not trusted; forced GitHub IP + OpenSSL workaround required")
    if s.plaintext_secret_config_count>0: add("plaintext_secret_config",FindingSeverity.WARN,f"secret-bearing config keys with non-empty values={s.plaintext_secret_config_count}; values are not emitted")
    blocks=sum(x.severity==FindingSeverity.BLOCK for x in f); warns=sum(x.severity==FindingSeverity.WARN for x in f)
    status=OperationalHardeningStatus.HARDENING_BLOCKED if blocks else (OperationalHardeningStatus.HARDENING_WARN if warns else OperationalHardeningStatus.HARDENING_PASS)
    stable={"version":OPERATIONAL_HARDENING_VERSION,"snapshot":s.model_dump(mode="json"),"findings":[x.model_dump(mode="json") for x in f],"status":status.value}
    return OperationalHardeningPlan(status=status,safe_to_run_pipeline=blocks==0,finding_count=len(f),block_count=blocks,warning_count=warns,findings=f,snapshot=s,operational_hardening_hash=_hash(stable),generated_at_utc=datetime.now(timezone.utc))
