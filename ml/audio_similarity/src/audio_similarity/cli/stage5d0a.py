"""Compatibility entry point for the active chart-based download batches.

The old genre-search catalog and original CLI remain in Git history.
No command here dispatches the historical genre-search queue.
"""
from audio_similarity.chart_download_batches import main


if __name__ == "__main__":
    main()
