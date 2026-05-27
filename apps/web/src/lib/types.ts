export type Health = {
  status: string;
  device: string;
  cuda_available: boolean;
  model_name: string;
  yolo_imgsz: number;
  yolo_conf: number;
  yolo_iou: number;
  yolo_max_det: number;
  yolo_court_crop_second_pass: boolean;
  yolo_court_crop_imgsz: number;
  yolo_court_crop_conf: number;
  shuttle_detection_enabled: boolean;
  tracknet_enabled: boolean;
  tracknet_ready: boolean;
  tracknet_busy: boolean;
  tracknet_repo_dir: string;
  tracknet_tracknet_file: string;
  tracknet_inpaintnet_file: string;
  tracknet_batch_size: number;
  tracknet_proxy_max_width: number;
  tracknet_max_sample_num: number;
  tracknet_timeout_sec: number;
  sample_fps: number;
  mock_enabled: boolean;
  data_dir: string;
};

export type AnalysisSettings = {
  sample_fps: number;
  yolo_imgsz: number;
  yolo_conf: number;
  yolo_iou: number;
  yolo_max_det: number;
  yolo_court_crop_second_pass: boolean;
  yolo_court_crop_imgsz: number;
  yolo_court_crop_conf: number;
  enable_shuttle_detection: boolean;
  enable_tracknet: boolean;
  tracknet_large_video: boolean;
  tracknet_batch_size: number;
  tracknet_proxy_max_width: number;
  tracknet_max_sample_num: number;
  tracknet_timeout_sec: number;
};

export type VideoRecord = {
  id: string;
  filename: string;
  original_filename: string;
  content_type?: string | null;
  file_path: string;
  size_bytes: number;
  created_at: string;
};

export type JobRecord = {
  id: string;
  video_id: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  error?: string | null;
  pose_status?: string | null;
  pose_progress?: number | null;
  pose_error?: string | null;
  shuttle_status?: string | null;
  shuttle_progress?: number | null;
  shuttle_error?: string | null;
  pose_path?: string | null;
  summary_path?: string | null;
  shuttle_path?: string | null;
  roi_json?: string | null;
  court_points_json?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  original_filename?: string | null;
  video_path?: string | null;
};

export type Roi = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type CourtPoint = {
  x: number;
  y: number;
};

export type PosePerson = {
  track_id: number | null;
  selected?: boolean;
  bbox: [number, number, number, number];
  keypoints: [number, number, number][];
  raw_keypoint_count?: number;
  valid_keypoint_count?: number;
  person_confidence: number;
  center: [number, number];
  foot_midpoint: [number, number];
  court_point?: [number, number] | null;
  in_court?: boolean;
};

export type PoseFrame = {
  frame_index: number;
  timestamp: number;
  bbox: [number, number, number, number] | null;
  keypoints: [number, number, number][];
  person_confidence: number;
  center: [number, number] | null;
  foot_midpoint: [number, number] | null;
  court_point?: [number, number] | null;
  in_court?: boolean;
  persons?: PosePerson[];
};

export type PoseOutput = {
  video_id: string;
  fps_sampled: number;
  source_width: number;
  source_height: number;
  roi?: Roi | null;
  court?: {
    points: CourtPoint[];
    court_width_m: number;
    court_length_m: number;
    homography: number[][];
  } | null;
  primary_track_id?: number | null;
  keypoint_filter?: {
    min_confidence: number;
    bbox_padding_ratio: number;
    temporal_smoothing: boolean;
  };
  frames: PoseFrame[];
};

export type SummaryOutput = {
  job_id: string;
  video_id: string;
  duration_sec: number;
  fps_sampled: number;
  sampled_frames: number;
  detected_frames: number;
  avg_confidence: number;
  estimated_movement_px: number;
  avg_speed_px_s: number;
  movement_unit?: string;
  avg_speed_unit?: string;
  zone_ratio: {
    front: number;
    mid: number;
    back: number;
    left: number;
    center: number;
    right: number;
  };
  analysis: {
    mode: string;
    device: string;
    model_name: string;
    fallback_error?: string | null;
    track_count?: number;
    max_persons_per_frame?: number;
    court_calibrated?: boolean;
  };
  report: {
    overall: string;
    movement: string;
    positioning: string;
    video_quality: string;
    next_steps: string[];
  };
};

export type ShuttleCandidate = {
  position: [number, number];
  confidence: number;
  bbox: [number, number, number, number];
};

export type ShuttleFrame = {
  frame_index: number;
  timestamp: number;
  position: [number, number] | null;
  raw_position?: [number, number] | null;
  filtered_position?: [number, number] | null;
  rejected_reason?: string | null;
  court_point?: [number, number] | null;
  confidence: number;
  candidates?: ShuttleCandidate[];
};

export type ShuttleOutput = {
  video_id: string;
  fps_sampled: number;
  duration_sec?: number;
  source_width?: number;
  source_height?: number;
  method: string;
  detected_frames: number;
  error?: string;
  frames: ShuttleFrame[];
};
