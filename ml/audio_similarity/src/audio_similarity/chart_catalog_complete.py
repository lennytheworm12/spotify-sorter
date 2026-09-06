"""Finish the collected chart metadata queue, then freeze append-only batches.

No YouTube discovery, media acquisition, or model inference occurs here.
Provider errors propagate immediately; rerunning reuses successful checkpoints.
"""
import argparse
from pathlib import Path
from types import SimpleNamespace

from .chart_catalog import execute, metadata_lock, song_candidates
from .chart_batch_expansion import expand
from .stage5d0a_worker import read_json
from .stage5b1b_artifacts import atomic_json


def complete(root):
    runtime = root / '.research_audio/chart_catalog_v1'
    runtime.mkdir(parents=True, exist_ok=True)
    with metadata_lock(runtime):
        charts = read_json(root / 'reports/stage5d_chart_catalog_v1/chart_appearances.json')
        candidates = len(song_candidates(charts['entries']))
        # Finite upper bound even if a future bug stops advancing the queue.
        for _ in range((candidates + 499) // 500 + 1):
            snapshot = execute(SimpleNamespace(root=root, command='match', max_requests=500), runtime)
            metrics = read_json(snapshot)['metrics']
            pending = metrics['matching_outcomes'].get('PENDING', 0)
            atomic_json(runtime/'expansion_progress.json', {
                'pending':pending, 'matched_recordings':metrics['recordings_matched'],
                'snapshot':str(snapshot.relative_to(root)), 'downloads_started':False})
            if pending == 0:
                result = expand(root, snapshot)
                result.update(metadata_queue_exhausted=True, chart_coverage_complete=False,
                              matching_outcomes=metrics['matching_outcomes'],
                              source_gaps=metrics['coverage_gaps'])
                atomic_json(runtime/'expansion_result.json',result)
                return result
        raise RuntimeError('bounded matching passes exhausted; inspect progress before retry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    import json
    print(json.dumps(complete(Path(__file__).resolve().parents[2]), indent=2))


if __name__ == '__main__':
    main()
