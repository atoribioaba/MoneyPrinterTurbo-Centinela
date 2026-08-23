from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.centinela.control_center import (
    AUTO_PIPELINE_JOB_TYPE,
    CentinelaControlCenter,
    MediaAutomationPolicy,
    MediaRefreshDecision,
    PipelineDisposition,
)
from app.services.centinela.orchestration import JobStatus, ProjectState
from app.services.centinela.production_spine import (
    STAGE_DESCRIPTORS,
    SpineStage,
    StageArtifact,
    StageBinding,
    StageResult,
)
from app.services.centinela.project_foundation import ArtifactStore


class FakeCatalog:
    def __init__(self, items=()):
        self.items = list(items)

    def list_items(self, active_only=True):
        if not active_only:
            return list(self.items)
        return [item for item in self.items if getattr(item, "active", True)]


class FakePolicy:
    def __init__(self, refresh=False):
        self.refresh = refresh
        self.calls = 0

    def decide(self):
        self.calls += 1
        return MediaRefreshDecision(
            refresh_catalog=self.refresh,
            reason="test",
            root=r"D:\ASTRONOMÍA\Medios",
            root_exists=True,
            supported_file_count=1,
            catalog_root_item_count=1,
            active_catalog_item_count=1,
            changed_path_count=1 if self.refresh else 0,
        )


def fake_binding(stage: SpineStage, capture: dict | None = None, *, side=False):
    descriptor = STAGE_DESCRIPTORS[stage]

    def handler(context, payload):
        if capture is not None:
            capture[stage.value] = dict(payload)
        if side:
            return StageResult.needs_input(
                "human decision required",
                details={"test": True},
            )
        return StageResult.complete(
            StageArtifact(
                descriptor.required_artifact_types[0],
                payload={"stage": stage.value, "ok": True},
            ),
            message=f"{stage.value} complete",
        )

    return StageBinding(
        adapter_id=f"test_{stage.value.lower()}",
        handler=handler,
        resource_class=descriptor.minimum_resource_class,
    )


def make_service(tmp_path, *, bindings=None, policy=None):
    store = ArtifactStore(tmp_path / "centinela")
    return CentinelaControlCenter(
        store=store,
        catalog=FakeCatalog(),
        media_policy=policy or FakePolicy(False),
        stage_bindings=bindings or {},
        register_default_media=False,
        max_workers=2,
    )


def catalog_item(path: Path, *, sidecar=None):
    stat = path.stat()
    return SimpleNamespace(
        active=True,
        local_path=str(path.resolve()),
        file_size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sidecar_fingerprint=sidecar,
        provider=SimpleNamespace(value="LOCAL_MEDIA"),
        rights_status=SimpleNamespace(value="UNVERIFIED"),
        publication_eligible=False,
    )


def test_media_policy_empty_library(tmp_path):
    policy = MediaAutomationPolicy(FakeCatalog(), media_root=tmp_path)
    decision = policy.decide()
    assert decision.refresh_catalog is False
    assert decision.reason == "empty_library"
    assert decision.supported_file_count == 0


def test_media_policy_missing_root(tmp_path):
    policy = MediaAutomationPolicy(FakeCatalog(), media_root=tmp_path / "missing")
    decision = policy.decide()
    assert decision.refresh_catalog is False
    assert decision.reason == "media_root_missing"
    assert decision.root_exists is False


def test_media_policy_new_media(tmp_path):
    (tmp_path / "moon.mp4").write_bytes(b"video")
    policy = MediaAutomationPolicy(FakeCatalog(), media_root=tmp_path)
    decision = policy.decide()
    assert decision.refresh_catalog is True
    assert decision.reason == "new_media"
    assert decision.changed_path_count == 1


def test_media_policy_ignores_unsupported_files(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    decision = MediaAutomationPolicy(FakeCatalog(), media_root=tmp_path).decide()
    assert decision.refresh_catalog is False
    assert decision.supported_file_count == 0


def test_media_policy_skips_symlink_files(tmp_path):
    target = tmp_path / "target.mp4"
    target.write_bytes(b"video")
    link = tmp_path / "link.mp4"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink not available")
    decision = MediaAutomationPolicy(
        FakeCatalog([catalog_item(target)]),
        media_root=tmp_path,
    ).decide()
    assert decision.refresh_catalog is False
    assert decision.supported_file_count == 1


def test_media_policy_up_to_date(tmp_path):
    path = tmp_path / "moon.mp4"
    path.write_bytes(b"video")
    decision = MediaAutomationPolicy(
        FakeCatalog([catalog_item(path)]),
        media_root=tmp_path,
    ).decide()
    assert decision.refresh_catalog is False
    assert decision.reason == "up_to_date"


def test_media_policy_detects_changed_media(tmp_path):
    path = tmp_path / "moon.mp4"
    path.write_bytes(b"video")
    item = catalog_item(path)
    path.write_bytes(b"changed-video")
    decision = MediaAutomationPolicy(FakeCatalog([item]), media_root=tmp_path).decide()
    assert decision.refresh_catalog is True
    assert decision.reason == "media_changed"


def test_media_policy_detects_removed_media(tmp_path):
    path = tmp_path / "moon.mp4"
    path.write_bytes(b"video")
    item = catalog_item(path)
    path.unlink()
    decision = MediaAutomationPolicy(FakeCatalog([item]), media_root=tmp_path).decide()
    assert decision.refresh_catalog is True
    assert decision.reason == "removed_media"


def test_media_policy_detects_sidecar_change(tmp_path):
    path = tmp_path / "moon.mp4"
    path.write_bytes(b"video")
    item = catalog_item(path, sidecar=None)
    (tmp_path / "moon.astromedia.json").write_text("{}", encoding="utf-8")
    decision = MediaAutomationPolicy(FakeCatalog([item]), media_root=tmp_path).decide()
    assert decision.refresh_catalog is True
    assert decision.reason == "sidecar_changed"


def test_media_policy_detects_new_file_in_nested_directory(tmp_path):
    nested = tmp_path / "moon" / "night"
    nested.mkdir(parents=True)
    (nested / "clip.mov").write_bytes(b"video")
    decision = MediaAutomationPolicy(FakeCatalog(), media_root=tmp_path).decide()
    assert decision.refresh_catalog is True
    assert decision.supported_file_count == 1


def test_control_center_requires_two_workers(tmp_path):
    store = ArtifactStore(tmp_path / "centinela")
    with pytest.raises(ValueError, match="max_workers"):
        CentinelaControlCenter(
            store=store,
            catalog=FakeCatalog(),
            media_policy=FakePolicy(),
            register_default_media=False,
            max_workers=1,
        )


def test_create_project_is_draft_and_autopublish_false(tmp_path):
    service = make_service(tmp_path)
    try:
        project, started = service.create_project("Luna y Júpiter", auto_start=False)
        assert started is None
        assert project.state == ProjectState.DRAFT
        assert project.auto_publication is False
        manifest = service.store.load_project(project.project_id)
        assert manifest.metadata["auto_publication"] is False
    finally:
        service.shutdown()


def test_create_project_rejects_blank_title(tmp_path):
    service = make_service(tmp_path)
    try:
        with pytest.raises(ValueError, match="obligatorio"):
            service.create_project("   ", auto_start=False)
    finally:
        service.shutdown()


def test_auto_pipeline_stops_at_missing_research_without_mutating_state(tmp_path):
    service = make_service(tmp_path)
    try:
        project, start = service.create_project("Júpiter", auto_start=True)
        record = service.jobs.wait(start.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
        assert record.result["disposition"] == PipelineDisposition.CAPABILITY_PENDING.value
        assert record.result["stage"] == SpineStage.RESEARCH.value
        assert service.project(project.project_id).state == ProjectState.DRAFT
    finally:
        service.shutdown()


def test_auto_pipeline_job_type_is_product_level(tmp_path):
    service = make_service(tmp_path)
    try:
        project, start = service.create_project("Saturno", auto_start=True)
        record = service.jobs.wait(start.job_id, timeout=10)
        assert record.job_type == AUTO_PIPELINE_JOB_TYPE
        assert not record.job_type.startswith("centinela.spine.")
        assert project.project_id == record.project_id
    finally:
        service.shutdown()


def test_auto_pipeline_runs_connected_stages_until_audio_pending(tmp_path):
    bindings = {
        stage: fake_binding(stage)
        for stage in (
            SpineStage.RESEARCH,
            SpineStage.SCRIPT,
            SpineStage.SCENES,
            SpineStage.MEDIA,
        )
    }
    service = make_service(tmp_path, bindings=bindings)
    try:
        project, start = service.create_project("Eclipse", auto_start=True)
        record = service.jobs.wait(start.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
        assert record.result["disposition"] == PipelineDisposition.CAPABILITY_PENDING.value
        assert record.result["stage"] == SpineStage.AUDIO.value
        assert record.result["completed_stages"] == [
            "RESEARCH",
            "SCRIPT",
            "SCENES",
            "MEDIA",
        ]
        assert service.project(project.project_id).state == ProjectState.MEDIA_READY
    finally:
        service.shutdown()


def test_media_stage_receives_automatic_refresh_decision(tmp_path):
    captured = {}
    bindings = {
        stage: fake_binding(stage, captured)
        for stage in (
            SpineStage.RESEARCH,
            SpineStage.SCRIPT,
            SpineStage.SCENES,
            SpineStage.MEDIA,
        )
    }
    policy = FakePolicy(True)
    service = make_service(tmp_path, bindings=bindings, policy=policy)
    try:
        _, start = service.create_project("Luna", auto_start=True)
        record = service.jobs.wait(start.job_id, timeout=10)
        assert record.status == JobStatus.SUCCEEDED
        media_request = captured["MEDIA"]["resolver"]
        assert media_request["refresh_catalog"] is True
        assert media_request["semantic_evidence"] is False
        assert media_request["analyze_selected_focal"] is True
        assert media_request["publication_eligible_only"] is False
        assert policy.calls == 1
    finally:
        service.shutdown()


def test_media_policy_not_called_before_media_stage(tmp_path):
    policy = FakePolicy(True)
    service = make_service(
        tmp_path,
        bindings={SpineStage.RESEARCH: fake_binding(SpineStage.RESEARCH)},
        policy=policy,
    )
    try:
        _, start = service.create_project("Marte", auto_start=True)
        service.jobs.wait(start.job_id, timeout=10)
        assert policy.calls == 0
    finally:
        service.shutdown()


def test_unresolved_connected_stage_stops_in_needs_input(tmp_path):
    bindings = {
        SpineStage.RESEARCH: fake_binding(SpineStage.RESEARCH),
        SpineStage.SCRIPT: fake_binding(SpineStage.SCRIPT, side=True),
    }
    service = make_service(tmp_path, bindings=bindings)
    try:
        project, start = service.create_project("Cometa", auto_start=True)
        record = service.jobs.wait(start.job_id, timeout=10)
        assert record.result["disposition"] == PipelineDisposition.NEEDS_INPUT.value
        assert service.project(project.project_id).state == ProjectState.NEEDS_INPUT
    finally:
        service.shutdown()


def test_project_view_counts_artifacts_without_exposing_paths(tmp_path):
    service = make_service(tmp_path)
    try:
        project, _ = service.create_project("Nebulosa", auto_start=False)
        service.store.put_json(
            project.project_id,
            "fact_lock",
            {"ok": True},
            producer="test",
        )
        view = service.project(project.project_id)
        assert view.artifact_count == 1
        assert view.artifact_type_counts == {"fact_lock": 1}
        assert not hasattr(view, "artifact_paths")
    finally:
        service.shutdown()


def test_capabilities_report_media_only_when_only_media_registered(tmp_path):
    service = make_service(tmp_path)
    try:
        caps = service.capabilities()
        assert len(caps) == 8
        assert not any(item.connected for item in caps)
    finally:
        service.shutdown()


def test_capabilities_report_injected_binding(tmp_path):
    service = make_service(
        tmp_path,
        bindings={SpineStage.RESEARCH: fake_binding(SpineStage.RESEARCH)},
    )
    try:
        by_stage = {item.stage: item for item in service.capabilities()}
        assert by_stage[SpineStage.RESEARCH].connected is True
        assert by_stage[SpineStage.SCRIPT].connected is False
    finally:
        service.shutdown()


def test_library_view_is_read_only_summary(tmp_path):
    path = tmp_path / "moon.mp4"
    path.write_bytes(b"video")
    item = catalog_item(path)
    item.provider = SimpleNamespace(value="OWN_MEDIA")
    item.rights_status = SimpleNamespace(value="CONFIRMED_OWNED")
    item.publication_eligible = True
    store = ArtifactStore(tmp_path / "storage")
    catalog = FakeCatalog([item])
    service = CentinelaControlCenter(
        store=store,
        catalog=catalog,
        media_policy=MediaAutomationPolicy(catalog, media_root=tmp_path),
        register_default_media=False,
        max_workers=2,
    )
    try:
        view = service.library()
        assert view.active_items == 1
        assert view.publication_eligible_items == 1
        assert view.provider_counts == {"OWN_MEDIA": 1}
        assert view.rights_counts == {"CONFIRMED_OWNED": 1}
        assert view.refresh.refresh_catalog is False
    finally:
        service.shutdown()


def test_storage_integrity_is_exposed_read_only(tmp_path):
    service = make_service(tmp_path)
    try:
        assert service.storage_integrity() == "ok"
    finally:
        service.shutdown()


def test_start_pipeline_is_idempotent_for_active_job(tmp_path):
    service = make_service(tmp_path)
    try:
        project, _ = service.create_project("Aurora", auto_start=False)
        original = service._pipeline_handler

        def slow_handler(context, payload):
            time_module = __import__("time")
            time_module.sleep(0.4)
            return original(context, payload)

        service.jobs.register_handler(AUTO_PIPELINE_JOB_TYPE, slow_handler)
        first = service.start_pipeline(project.project_id)
        second = service.start_pipeline(project.project_id)
        assert second.existing is True
        assert second.job_id == first.job_id
        service.jobs.wait(first.job_id, timeout=10)
    finally:
        service.shutdown()


def test_recover_runtime_returns_structured_result(tmp_path):
    service = make_service(tmp_path)
    try:
        result = service.recover_runtime()
        assert set(result) == {
            "transitions",
            "interrupted_job_ids",
            "resumed_queued_job_ids",
        }
    finally:
        service.shutdown()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_product_entrypoint_uses_grouped_navigation():
    text = (_repo_root() / "webui" / "Centinela.py").read_text(encoding="utf-8")
    compile(text, "webui/Centinela.py", "exec")
    for label in (
        "PRODUCCIÓN",
        "ASTRONOMÍA",
        "MEDIOS",
        "RESULTADOS",
        "SISTEMA",
        "AVANZADO · INGENIERÍA",
    ):
        assert label in text
    assert "st.navigation(" in text


def test_product_entrypoint_preserves_legacy_engineering_pages():
    text = (_repo_root() / "webui" / "Centinela.py").read_text(encoding="utf-8")
    assert '"Main.py"' in text
    assert '(WEBUI_ROOT / "pages").glob("*.py")' in text


def test_product_pages_have_no_manual_astromedia_actions():
    text = (_repo_root() / "webui" / "product" / "pages.py").read_text(encoding="utf-8")
    compile(text, "webui/product/pages.py", "exec")
    assert 'st.button("Indexar"' not in text
    assert 'st.button("Buscar"' not in text
    assert "form_submit_button(\n            \"Generar borrador\"" in text


def test_product_pages_do_not_render_raw_tracebacks():
    text = (_repo_root() / "webui" / "product" / "pages.py").read_text(encoding="utf-8")
    assert "st.exception(" not in text
    assert "traceback.format" not in text


def test_windows_launcher_uses_product_entrypoint():
    text = (_repo_root() / "webui.bat").read_text(encoding="utf-8")
    assert "run .\\webui\\Centinela.py" in text
    assert "run .\\webui\\Main.py" not in text


def test_posix_launcher_uses_product_entrypoint():
    text = (_repo_root() / "webui.sh").read_text(encoding="utf-8")
    assert 'run "$CURRENT_DIR/webui/Centinela.py"' in text
    assert 'run "$CURRENT_DIR/webui/Main.py"' not in text


def test_windows_start_stop_scripts_recognize_new_and_legacy_entrypoints():
    root = _repo_root()
    start = (root / "Iniciar-Centinela-MPT.ps1").read_text(encoding="utf-8")
    stop = (root / "Detener-Centinela-MPT.ps1").read_text(encoding="utf-8")
    marker = "(?:Centinela|Main)\\.py"
    assert marker in start
    assert marker in stop


def test_legacy_main_and_astromedia_page_are_preserved():
    root = _repo_root()
    assert (root / "webui" / "Main.py").is_file()
    assert (root / "webui" / "pages" / "04_AstroMedia.py").is_file()
