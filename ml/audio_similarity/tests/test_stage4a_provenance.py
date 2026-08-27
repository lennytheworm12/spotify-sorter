from pathlib import Path
import yaml
from audio_similarity.stage4_corpus import sha256_file

ROOT=Path(__file__).resolve().parents[1]
ACTUAL_CHECKPOINT="models/music_audioset_epoch_15_esc_90.14.pt"
ACTUAL_SHA="fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"

def test_stage4a_uses_reproducibly_validated_stage2b_artifact_identity():
 config=yaml.safe_load((ROOT/'configs/holistic_stage4a_fma30.yaml').read_text())
 assert config['encoder']['checkpoint']==ACTUAL_CHECKPOINT
 assert config['encoder']['checkpoint_sha256']==ACTUAL_SHA
 assert sha256_file(ROOT/ACTUAL_CHECKPOINT)==ACTUAL_SHA

def test_original_encoder_cli_proves_artifact_checkpoint_path():
 source=(ROOT/'src/audio_similarity/cli/encode_holistic.py').read_text()
 assert 'models/music_audioset_epoch_15_esc_90.14.pt' in source
 assert 'models/630k-audioset-best.pt' not in source

def test_historical_stage2b_yaml_is_unchanged_and_erratum_is_explicit():
 historical=(ROOT/'configs/holistic_stage2b_fusion.yaml').read_text()
 assert 'checkpoint: models/630k-audioset-best.pt' in historical
 erratum=(ROOT/'reports/holistic_stage2b/checkpoint_provenance_erratum.md').read_text()
 assert ACTUAL_CHECKPOINT in erratum and ACTUAL_SHA in erratum
 assert 'SINGLE_ENCODER_WINS' in erratum
