"""Inst-Sim-ABX external calibration runner (Stage 1A validation).

    python -m audio_similarity.cli.eval_abx

Cuts the referenced 5-second segments from local Slakh test-set mixtures,
encodes them through every benchmark encoder, and measures agreement with
the 281-subject human majority votes. Published baselines for comparison:
MuQ-MuLan ~72.4%, CLAP ~72%.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np


ANSWERS_REL = "csvs/inst_sim_abx_answers.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/inst_sim_abx")
    parser.add_argument("--audio-dir", default="data/slakh_test_mix")
    parser.add_argument("--cache-dir", default="data/abx_feature_cache")
    parser.add_argument("--output", default="reports/holistic_stage1a/abx_calibration.json")
    parser.add_argument(
        "--encoders", default="muq_mulan_large,mert_5120,mert_generic,laion_clap"
    )
    args = parser.parse_args()

    from audio_similarity.abx_calibration import (
        load_config_index,
        load_triplets,
        abx_agreement,
    )
    from audio_similarity.audio import preprocess_file
    from audio_similarity.holistic_encoders import (
        LaionClapEncoder,
        MuQMulanEncoder,
        mert_5120_encoder,
        mert_generic_encoder,
    )

    config_index = load_config_index(Path(args.data_dir))
    triplets = load_triplets(
        Path(args.data_dir) / ANSWERS_REL, config_index,
        instrument_filter=("mix",),
    )

    # unique segments: (ID, index_s, index_e)
    seg_index: dict[tuple[int, int, int], np.ndarray] = {}
    needed_ids = sorted(set(triplets["ref_ID"]) | set(triplets["a_ID"]) | set(triplets["b_ID"]))

    print(f"triplets: {len(triplets)} | unique slakh tracks: {len(needed_ids)}")

    # decode each needed track once, cache all requested slices
    decoded: dict[int, np.ndarray] = {}
    for n, tid in enumerate(needed_ids, 1):
        name = f"Track{tid:05d}_mix.flac"
        path = Path(args.audio_dir) / name
        if not path.exists():
            print(f"missing {name}")
            continue
        wav = preprocess_file(path).numpy().astype(np.float64)  # 24 kHz mono canonical
        decoded[tid] = wav
        if n % 20 == 0:
            print(f"decoded {n}/{len(needed_ids)}")

    def slice_waveform(tid: int, bounds: tuple[int, int], sr_orig: int = 44100):
        key = (int(tid), int(bounds[0]), int(bounds[1]))
        if key in seg_index:
            return seg_index[key]
        full = decoded.get(int(tid))
        if full is None:
            return None
        start_24k = int(bounds[0] * 24000 / sr_orig)
        end_24k = min(int(bounds[1] * 24000 / sr_orig), len(full))
        seg = full[start_24k:end_24k]
        if len(seg) < 24000:
            seg = np.pad(seg, (0, 24000 - len(seg)))
        seg = seg.astype(np.float64)
        seg_index[key] = seg
        return seg

    # materialize every unique referenced segment once
    unique_segments: set[tuple[int, int, int]] = set()
    sr_orig = int(triplets.iloc[0]["ref_sr"]) if len(triplets) else 44100
    for _, row in triplets.iterrows():
        unique_segments.add((int(row["ref_ID"]), int(row["ref_bounds"][0]), int(row["ref_bounds"][1])))
        unique_segments.add((int(row["a_ID"]), int(row["a_bounds"][0]), int(row["a_bounds"][1])))
        unique_segments.add((int(row["b_ID"]), int(row["b_bounds"][0]), int(row["b_bounds"][1])))
    for key in sorted(unique_segments):
        slice_waveform(key[0], (key[1], key[2]), sr_orig)
    print(f"unique segments materialized: {len(seg_index)}/{len(unique_segments)}")

    encoders = {
        "muq_mulan_large": lambda: MuQMulanEncoder(),
        "mert_5120": mert_5120_encoder,
        "mert_generic": mert_generic_encoder,
        "laion_clap": lambda: LaionClapEncoder(
            checkpoint_path=str(Path("models/music_audioset_epoch_15_esc_90.14.pt"))
            if Path("models/music_audioset_epoch_15_esc_90.14.pt").exists()
            else None
        ),
    }
    wanted = [e.strip() for e in args.encoders.split(",")]

    # precompute embeddings per encoder over all unique segments
    embeddings_by_encoder: dict[str, dict] = {}
    for name in wanted:
        maker = encoders[name]
        enc = maker()
        store: dict[tuple[int, int, int], np.ndarray] = {}
        t0 = time.perf_counter()
        count = 0
        for key, wav in seg_index.items():
            result = enc.encode_segment(wav, 24000)
            store[key] = result.embedding
            count += 1
        embeddings_by_encoder[name] = store
        dt = time.perf_counter() - t0
        print(f"{name}: encoded {count} segments in {dt:.1f}s")

    def make_lookup(store):
        def lookup(track_id: int, bounds):
            return store.get((int(track_id), int(bounds[0]), int(bounds[1])))
        return lookup

    def cosine(a, b):
        return float(np.dot(a, b))

    report: dict = {"experiment": "inst_sim_abx_calibration", "results": {}}
    published = {"muq_mulan_large": 72.4, "mert_5120": None, "mert_generic": None, "laion_clap": 71.9}

    for name in wanted:
        store = embeddings_by_encoder[name]
        res_high = abx_agreement(triplets, make_lookup(store), cosine,
                                 high_agreement_threshold=0.80)
        res_all = abx_agreement(triplets, make_lookup(store), cosine,
                                high_agreement_threshold=None)
        pub = published.get(name)
        report["results"][name] = {
            "high_agreement_80": res_high,
            "all_mix_triplets": res_all,
            "published_baseline_pct": pub,
        }
        print(f"{name}: high-agreement agreement = "
              f"{100*res_high['agreement_rate']:.1f}% (n={res_high['n_triplets_scored']})"
              + (f" | published baseline {pub}%" if pub else ""))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        json.dump(report, fh, indent=1)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
