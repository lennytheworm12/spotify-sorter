import pytest
from audio_similarity.stage5e3_artifacts import freeze_json,hashes,verify_hashes
from audio_similarity.stage5e3_prepare import verify_prepared,prepare
from audio_similarity.stage5e3_closeout import require_frozen_review


def test_immutable_prepare_and_integrity(tmp_path):
    root=tmp_path;run=root/'run';source=root/'source';source.write_bytes(b'original')
    freeze_json(run/'input_reference.json',{'historical':{'source':hashes([source],root)['source']},'source_hashes':{},'implementation':{}})
    freeze_json(run/'preparation_manifest.json',hashes([run/'input_reference.json'],run))
    freeze_json(run/'preparation_status.json',{'status':'PREPARED'})
    before={p:p.stat().st_mtime_ns for p in run.iterdir()}
    assert prepare(root,run)=={'status':'PREPARED'}
    assert before=={p:p.stat().st_mtime_ns for p in run.iterdir()}
    with pytest.raises(ValueError,match='AWAITING_HUMAN_REVIEW'):require_frozen_review(root,run)
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='integrity'):verify_prepared(root,run)
    assert not (run/'closeout.json').exists()


def test_manifest_detects_modified_config(tmp_path):
    run=tmp_path/'run';freeze_json(run/'config.json',{'x':1})
    freeze_json(run/'input_reference.json',{'historical':{},'source_hashes':{},'implementation':{}})
    freeze_json(run/'preparation_manifest.json',hashes(run.glob('*.json'),run))
    (run/'config.json').write_text('{}')
    with pytest.raises(ValueError,match='config.json'):verify_prepared(tmp_path,run)
