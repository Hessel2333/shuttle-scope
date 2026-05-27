# Shuttle Scope Architecture

Shuttle Scope is a local-only badminton video analysis MVP.

- `apps/web`: Next.js workstation UI.
- `apps/api`: FastAPI service, SQLite job store, OpenCV video sampling, YOLO Pose inference.
- `data/uploads`: Uploaded videos.
- `data/outputs`: Per-job `pose.json` and `summary.json`.
- `data/db`: SQLite database.

The current version keeps first-version compatibility by exposing one primary player at the frame root, but each frame also stores all detected persons under `persons`. Primary player selection prefers tracks inside the user-provided calibrated court polygon or ROI, then falls back to box size, lower-frame position, and confidence. Keypoints are filtered by confidence and expanded bbox bounds, then lightly smoothed across frames.

When users provide four court corners, the backend computes an OpenCV homography from image coordinates to a standard 6.1m x 13.4m badminton court. Player foot points are mapped to `court_point`, and summary zone ratios plus movement distance use court-plane coordinates instead of raw pixels.

TrackNetV3, court calibration, stronger multi-player tracking, and action classification are intentionally reserved behind separate module boundaries.
