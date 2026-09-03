"""Stage 5B.1J metadata layered over the generic human-review store."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage5b1a_models import Stage5B1AValidationError
from .stage5b1b_challenge import ChallengeManifest
from .stage5b1b_challenge_review_store import Stage5B1BChallengeReviewStore
from .stage5b1i_live_fallback import (
    EXACT_RECORDING,
    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
)
from .stage5b1j_representation_rediscovery import (
    REPRESENTATION_EQUIVALENT_MASTER_FALLBACK,
)


_MATCH_MODES = {
    EXACT_RECORDING,
    REPRESENTATION_EQUIVALENT_STUDIO_FALLBACK,
    REPRESENTATION_EQUIVALENT_MASTER_FALLBACK,
}


class Stage5B1JReviewStore(Stage5B1BChallengeReviewStore):
    def __init__(
        self,
        manifest: ChallengeManifest,
        queue_path: str | Path,
        review_path: str | Path,
    ) -> None:
        queue = json.loads(Path(queue_path).read_text(encoding="utf-8"))
        self._fallback_by_id: dict[str, dict[str, Any]] = {}
        for case in queue.get("cases", []):
            fallback = case.get("fallback")
            stable_id = case.get("stable_track_id")
            if (
                not isinstance(stable_id, str)
                or not isinstance(fallback, dict)
                or fallback.get("match_mode") not in _MATCH_MODES
                or not isinstance(fallback.get("reason"), str)
            ):
                raise Stage5B1AValidationError(
                    "invalid Stage 5B.1J fallback review metadata"
                )
            self._fallback_by_id[stable_id] = fallback
        super().__init__(
            manifest,
            queue_path,
            review_path,
            session_mode="stage5b1j_representation_fallback_review",
            export_filename="stage5b1j-representation-fallback-human-review.csv",
            shuffle_salt="stage5b1j-representation-fallback-review-v1",
        )

    def session(self) -> dict[str, Any]:
        value = super().session()
        for case in value["cases"]:
            case["fallback"] = self._fallback_by_id[case["stable_track_id"]]
        return value
