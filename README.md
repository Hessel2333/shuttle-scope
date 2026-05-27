# Shuttle Scope

Windows 本地羽毛球视频 AI 分析 MVP。浏览器访问本地 Next.js 工作台，FastAPI 后端在本机 CPU/GPU 上分析视频，不上传云端。

## Requirements

- Windows + PowerShell
- Python 3.11
- Node.js 22 / npm 10
- NVIDIA GPU 可选；无 CUDA 时自动 fallback 到 CPU
- FFmpeg 可选；当前实现默认使用 OpenCV 读取视频

## Quick Start

```powershell
Copy-Item .env.example .env
.\scripts\dev-api.ps1
```

另开一个 PowerShell：

```powershell
.\scripts\dev-web.ps1
```

打开 http://localhost:3000。

## CUDA / YOLO Notes

后端默认使用 `MODEL_NAME=yolo11n-pose.pt`。Ultralytics 会在首次运行时自动下载权重。`torch.cuda.is_available()` 为 true 时使用 `cuda:0`，否则使用 CPU。

远端小人容易漏检，默认推理参数偏向“多人/小人召回”：`YOLO_IMGSZ=960`、`YOLO_CONF=0.12`、`YOLO_MAX_DET=30`。如果已经标定场地，后端会额外启用场地裁剪二次检测：`YOLO_COURT_CROP_SECOND_PASS=true`、`YOLO_COURT_CROP_IMGSZ=1280`、`YOLO_COURT_CROP_CONF=0.06`，把目标场地裁出来放大再跑一遍 YOLO Pose，以提高对面小人的召回。如果速度太慢，可关闭二次检测或把 `YOLO_COURT_CROP_IMGSZ` 调低；如果误检太多，可把 `YOLO_CONF` 或 `YOLO_COURT_CROP_CONF` 提高。

如果 pip 默认安装的 PyTorch 不是 CUDA 版本，可在 `apps/api\.venv` 激活后按你的 CUDA/驱动环境安装官方 CUDA wheel，例如：

```powershell
pip install --force-reinstall torch==2.11.0+cu128 torchvision==0.26.0+cu128 --index-url https://download.pytorch.org/whl/cu128
```

也可以直接运行脚本：

```powershell
.\scripts\install-cuda-torch.ps1
```

如果普通依赖下载慢，可以把 PyPI 源换成国内镜像；PyTorch CUDA wheel 仍建议使用官方 CUDA wheel 源，或传入你自己的 Torch wheel 镜像：

```powershell
.\scripts\install-cuda-torch.ps1 -PyPiIndex https://pypi.tuna.tsinghua.edu.cn/simple
```

本机当前没有 `ffmpeg` 命令也可以运行。若后续需要更强的视频格式兼容性，可安装 FFmpeg 并加入 PATH。

## TrackNetV3 Shuttle Tracking

羽毛球轨迹优先使用 TrackNetV3。TrackNetV3 官方仓库说明其模型由轨迹预测和轨迹修复两部分组成，测试集 F1 高于 TrackNetV2，并提供 `predict.py` 从视频输出 `Frame, Visibility, X, Y` 轨迹 CSV。项目已接入可选 TrackNetV3 runner：权重就绪时优先使用 TrackNetV3；否则自动回退到 OpenCV 候选检测。

首次安装：

```powershell
.\scripts\setup-tracknet.ps1
```

脚本会克隆 `https://github.com/qaz812345/TrackNetV3.git`，下载官方 checkpoint zip，并把权重放到：

- `data/models/tracknetv3/ckpts/TrackNet_best.pt`
- `data/models/tracknetv3/ckpts/InpaintNet_best.pt`

相关 `.env`：

```env
ENABLE_TRACKNET=true
TRACKNET_REPO_DIR=../../third_party/TrackNetV3
TRACKNET_TRACKNET_FILE=../../data/models/tracknetv3/ckpts/TrackNet_best.pt
TRACKNET_INPAINTNET_FILE=../../data/models/tracknetv3/ckpts/InpaintNet_best.pt
TRACKNET_BATCH_SIZE=2
TRACKNET_EVAL_MODE=nonoverlap
TRACKNET_MAX_SAMPLE_NUM=600
TRACKNET_USE_INPAINT=false
TRACKNET_PROXY_MAX_WIDTH=960
TRACKNET_LARGE_VIDEO=false
TRACKNET_TIMEOUT_SEC=360
```

如果 Google Drive 下载慢，可手动下载 TrackNetV3 README 中的 checkpoints 压缩包，解压后确保上述两个 `.pt` 文件在 `data/models/tracknetv3/ckpts` 下。

为避免 Windows 本机被 TrackNetV3 占满资源，后端会限制同一时间只运行一个 TrackNetV3 子进程。`TRACKNET_BATCH_SIZE` 默认较保守；`TRACKNET_PROXY_MAX_WIDTH` 不建议低于 960，因为羽毛球目标很小，过度降采样会明显漏检。

## API

- `POST /api/videos/upload`
- `POST /api/jobs/{video_id}/analyze`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/videos/{video_id}/file`
- `GET /api/outputs/{job_id}/pose`
- `GET /api/outputs/{job_id}/summary`
- `GET /api/outputs/{job_id}/shuttle`
- `GET/PATCH /api/settings/analysis`
- `GET /api/health`

`POST /api/jobs/{video_id}/analyze` 支持可选 ROI，用归一化坐标限制目标场地，减少隔壁场地人员干扰：

```json
{
  "mock": false,
  "roi": { "x": 0.1, "y": 0.2, "width": 0.75, "height": 0.7 }
}
```

## Data Outputs

每个任务会写入：

- `data/outputs/{job_id}/pose.json`
- `data/outputs/{job_id}/summary.json`
- `data/outputs/{job_id}/shuttle.json`

`pose.json` 兼容第一版单人字段，同时每帧新增 `persons`：

- `frame.keypoints` / `frame.bbox`：当前主跟踪人，用于统计和旧 UI。
- `frame.persons[]`：所有检测到的人，包含 `track_id`、`bbox`、`keypoints`、`selected`。
- 低置信度或飘出人体框的关键点会被过滤，跨帧会做轻量平滑，减少飞点。

真实 YOLO 推理失败且 `ENABLE_MOCK_ANALYSIS=true` 时，会自动生成 mock 结果，方便继续验证前端完整流程。

## Current MVP Scope

已覆盖上传、目标场地 ROI 框选、四点场地标定、透视校正、任务列表、分析详情、视频播放器、多人 Canvas 骨架叠加、主目标跟踪、飞点过滤、移动轨迹、3x3 热区、基础统计、规则化训练建议、中英文切换、浅色/深色/系统外观切换。

羽毛球轨迹已接入 TrackNetV3 可选 runner；没有 TrackNetV3 repo/权重时会退回 OpenCV 候选检测。动作分类暂未包含。多人跟踪目前是轻量 nearest-neighbor 版本，后续可替换为 ByteTrack/DeepSORT。
