from __future__ import annotations

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                content_type TEXT,
                file_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                error TEXT,
                pose_path TEXT,
                summary_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(video_id) REFERENCES videos(id)
            )
            """
        )
        ensure_column(conn, "jobs", "roi_json", "TEXT")
        ensure_column(conn, "jobs", "court_points_json", "TEXT")
        ensure_column(conn, "jobs", "pose_status", "TEXT DEFAULT 'queued'")
        ensure_column(conn, "jobs", "pose_progress", "REAL DEFAULT 0")
        ensure_column(conn, "jobs", "pose_error", "TEXT")
        ensure_column(conn, "jobs", "shuttle_status", "TEXT DEFAULT 'queued'")
        ensure_column(conn, "jobs", "shuttle_progress", "REAL DEFAULT 0")
        ensure_column(conn, "jobs", "shuttle_error", "TEXT")
        ensure_column(conn, "jobs", "shuttle_path", "TEXT")
        backfill_phase_progress(conn)
        recover_interrupted_jobs(conn)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def insert_video(
    *,
    video_id: str,
    filename: str,
    original_filename: str,
    content_type: str | None,
    file_path: Path,
    size_bytes: int,
) -> dict[str, Any]:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO videos (id, filename, original_filename, content_type, file_path, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (video_id, filename, original_filename, content_type, str(file_path), size_bytes, now),
        )
        row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return row_to_dict(row) or {}


def get_video(video_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return row_to_dict(conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone())


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def insert_job(
    *,
    job_id: str,
    video_id: str,
    roi: dict[str, float] | None = None,
    court_points: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    roi_json = json.dumps(roi) if roi else None
    court_points_json = json.dumps(court_points) if court_points else None
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, video_id, status, progress, pose_status, pose_progress, shuttle_status, shuttle_progress,
                roi_json, court_points_json, created_at, updated_at
            )
            VALUES (?, ?, 'queued', 0, 'queued', 0, 'queued', 0, ?, ?, ?, ?)
            """,
            (job_id, video_id, roi_json, court_points_json, now, now),
        )
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row_to_dict(row) or {}


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = utc_now()
    if fields.get("status") in {"completed", "failed"} and "completed_at" not in fields:
        fields["completed_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        return row_to_dict(
            conn.execute(
                """
                SELECT jobs.*, videos.original_filename, videos.file_path AS video_path
                FROM jobs
                JOIN videos ON videos.id = jobs.video_id
                WHERE jobs.id = ?
                """,
                (job_id,),
            ).fetchone()
        )


def list_jobs() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT jobs.*, videos.original_filename, videos.file_path AS video_path
            FROM jobs
            JOIN videos ON videos.id = jobs.video_id
            ORDER BY jobs.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_job(job_id: str) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cursor.rowcount > 0


def delete_jobs(job_ids: list[str]) -> int:
    if not job_ids:
        return 0
    placeholders = ",".join("?" for _ in job_ids)
    with connect() as conn:
        cursor = conn.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
        return cursor.rowcount


def backfill_phase_progress(conn: sqlite3.Connection) -> None:
    now = utc_now()
    rows = conn.execute("SELECT id, status, pose_path, summary_path FROM jobs").fetchall()
    for row in rows:
        if row["status"] == "completed" and row["pose_path"] and row["summary_path"]:
            job_id = row["id"]
            output_dir = settings.outputs_dir / job_id
            shuttle_path = output_dir / "shuttle.json"
            shuttle_status = "queued"
            shuttle_progress = 0
            shuttle_error = None
            shuttle_path_value = None
            if shuttle_path.exists():
                shuttle_path_value = str(shuttle_path)
                shuttle_progress = 100
                try:
                    shuttle = json.loads(shuttle_path.read_text(encoding="utf-8"))
                    shuttle_error = shuttle.get("error")
                    shuttle_status = "failed" if shuttle_error or shuttle.get("method") == "failed" else "completed"
                except (OSError, json.JSONDecodeError):
                    shuttle_status = "failed"
                    shuttle_error = "Shuttle output could not be read."
            conn.execute(
                """
                UPDATE jobs
                SET pose_status = COALESCE(NULLIF(pose_status, 'queued'), 'completed'),
                    pose_progress = CASE WHEN pose_progress IS NULL OR pose_progress = 0 THEN 100 ELSE pose_progress END,
                    shuttle_status = CASE WHEN shuttle_path IS NULL THEN ? ELSE shuttle_status END,
                    shuttle_progress = CASE WHEN shuttle_path IS NULL THEN ? ELSE shuttle_progress END,
                    shuttle_error = CASE WHEN shuttle_path IS NULL THEN ? ELSE shuttle_error END,
                    shuttle_path = COALESCE(shuttle_path, ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (shuttle_status, shuttle_progress, shuttle_error, shuttle_path_value, now, job_id),
            )


def recover_interrupted_jobs(conn: sqlite3.Connection) -> None:
    now = utc_now()
    rows = conn.execute("SELECT id FROM jobs WHERE status IN ('queued', 'running')").fetchall()
    for row in rows:
        job_id = row["id"]
        output_dir = settings.outputs_dir / job_id
        pose_path = output_dir / "pose.json"
        summary_path = output_dir / "summary.json"
        shuttle_path = output_dir / "shuttle.json"
        if pose_path.exists() and summary_path.exists():
            shuttle_status = "queued"
            shuttle_error = None
            shuttle_progress = 0
            shuttle_path_value = None
            if shuttle_path.exists():
                shuttle_path_value = str(shuttle_path)
                shuttle_progress = 100
                try:
                    shuttle = json.loads(shuttle_path.read_text(encoding="utf-8"))
                    shuttle_error = shuttle.get("error")
                    shuttle_status = "failed" if shuttle_error or shuttle.get("method") == "failed" else "completed"
                except (OSError, json.JSONDecodeError):
                    shuttle_status = "failed"
                    shuttle_error = "Shuttle output could not be read."
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed',
                    progress = 100,
                    pose_status = 'completed',
                    pose_progress = 100,
                    pose_error = NULL,
                    shuttle_status = ?,
                    shuttle_progress = ?,
                    shuttle_error = ?,
                    pose_path = ?,
                    summary_path = ?,
                    shuttle_path = ?,
                    error = NULL,
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    shuttle_status,
                    shuttle_progress,
                    shuttle_error,
                    str(pose_path),
                    str(summary_path),
                    shuttle_path_value,
                    now,
                    now,
                    job_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    progress = 100,
                    pose_status = 'failed',
                    pose_progress = 100,
                    pose_error = ?,
                    shuttle_status = 'queued',
                    shuttle_progress = 0,
                    error = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    "Analysis was interrupted by an API restart. Please create a new analysis job.",
                    "Analysis was interrupted by an API restart. Please create a new analysis job.",
                    now,
                    now,
                    job_id,
                ),
            )
