"""Reserved TrackNetV3 integration boundary for shuttle trajectory detection."""


class ShuttleTracker:
    def analyze(self, video_path: str) -> None:
        raise NotImplementedError("TrackNetV3 is intentionally not implemented in the MVP.")
