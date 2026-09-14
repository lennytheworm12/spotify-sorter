"""Recovery tests use isolated fake audio/provider evidence only."""
import shutil
import pytest
from audio_similarity.calibration import gemini_full_recovery as recovery
from audio_similarity.calibration.contracts import freeze_json,file_hash
from audio_similarity.calibration.gemini_full_inputs import RUN,read
from audio_similarity.calibration.gemini_full_runner import FullRunner
from tests.calibration.test_gemini_full import synthetic_execution
from tests.test_gemini_free_genre import FreeProvider


def setup_recovery(root, monkeypatch):
    execution, policy = synthetic_execution(root, monkeypatch)
    original = root / RUN / 'batch_0001'
    provider = FreeProvider(original); provider.point = True
    runner = FullRunner(root, original, policy, transport_factory=provider.factory)
    runner.execute_remaining()
    before = recovery.historical_files(root / RUN)
    # Exercise a nonzero schedule offset while preserving original numbering/evidence.
    target = root / recovery.RECOVERY / 'batch_0001'
    target.mkdir(parents=True)
    (target/'prepared').symlink_to(original/'prepared', target_is_directory=True)
    for name in ('prompt.txt','response_schema.json','schemas'):
        source = original / name
        if source.is_dir(): shutil.copytree(source,target/name)
        else: shutil.copyfile(source,target/name)
    manifest = read(original/'execution_manifest.json')
    manifest['schedule'] = manifest['schedule'][1:]
    freeze_json(target/'execution_manifest.json',manifest)
    batch = {'path':str(target.relative_to(root))}
    return recovery.RecoveryRunner(root,batch,policy), before


def test_offset_recovery_uses_original_neutral_audio_and_replays_without_calls(tmp_path,monkeypatch):
    runner,before=setup_recovery(tmp_path,monkeypatch)
    provider=FreeProvider(runner.run); provider.point=True
    monkeypatch.setattr(recovery,'configured_key',lambda _: 'synthetic')
    monkeypatch.setattr(recovery,'GeminiTransport',lambda *a: provider.factory())
    runner.execute_remaining()
    assert provider.generations==1
    assert runner.verified_result(1)['neutral_id']=='N002'
    assert recovery.historical_files(tmp_path/RUN)==before
    monkeypatch.setattr(recovery,'GeminiTransport',lambda *a: pytest.fail('replay made a call'))
    runner.execute_remaining()


def test_second_failure_stops_and_cannot_retry(tmp_path,monkeypatch):
    runner,before=setup_recovery(tmp_path,monkeypatch)
    monkeypatch.setattr(recovery,'configured_key',lambda _: 'synthetic')
    monkeypatch.setattr(recovery,'GeminiTransport',lambda *a: (_ for _ in ()).throw(RuntimeError('503')))
    with pytest.raises(RuntimeError,match='503'):runner.execute_remaining()
    assert (runner.directory/'STOPPED.json').exists()
    with pytest.raises(ValueError,match='already stopped'):runner.execute_remaining()
    assert recovery.historical_files(tmp_path/RUN)==before
