"use client";

import { useEffect, useState } from "react";
import { API_BASE, getAnalysisSettings, getHealth, updateAnalysisSettings } from "@/lib/api";
import type { AnalysisSettings, Health } from "@/lib/types";
import { usePreferences } from "@/components/PreferencesProvider";

export default function SettingsPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [settings, setSettings] = useState<AnalysisSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const { language, setLanguage, theme, setTheme, t } = usePreferences();

  useEffect(() => {
    Promise.all([getHealth(), getAnalysisSettings()])
      .then(([nextHealth, nextSettings]) => {
        setHealth(nextHealth);
        setSettings(nextSettings);
      })
      .catch((err) => setError(err instanceof Error ? err.message : t("loadSettingsFailed")));
  }, [t]);

  async function handleSave() {
    if (!settings) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const nextSettings = await updateAnalysisSettings(settings);
      const nextHealth = await getHealth();
      setSettings(nextSettings);
      setHealth(nextHealth);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2200);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("saveSettingsFailed"));
    } finally {
      setSaving(false);
    }
  }

  function patchSettings(patch: Partial<AnalysisSettings>) {
    setSettings((current) => (current ? { ...current, ...patch } : current));
  }

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-5">
        <h1 className="text-2xl font-semibold text-ink">{t("settingsTitle")}</h1>
        <p className="mt-1 text-sm text-muted">{t("settingsDescription")}</p>
      </header>

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <PreferenceCard label={t("language")}>
          <div className="grid grid-cols-2 gap-2">
            <PreferenceButton active={language === "zh"} onClick={() => setLanguage("zh")}>中文</PreferenceButton>
            <PreferenceButton active={language === "en"} onClick={() => setLanguage("en")}>English</PreferenceButton>
          </div>
        </PreferenceCard>
        <PreferenceCard label={t("appearance")}>
          <div className="grid grid-cols-3 gap-2">
            <PreferenceButton active={theme === "light"} onClick={() => setTheme("light")}>{t("light")}</PreferenceButton>
            <PreferenceButton active={theme === "dark"} onClick={() => setTheme("dark")}>{t("dark")}</PreferenceButton>
            <PreferenceButton active={theme === "system"} onClick={() => setTheme("system")}>{t("system")}</PreferenceButton>
          </div>
        </PreferenceCard>
      </div>

      {error ? <div className="mb-4 rounded-md bg-danger/10 p-3 text-sm text-danger">{error}</div> : null}
      {!health && !error ? <div className="rounded-md border border-line bg-surface p-6 text-sm text-muted shadow-soft">{t("loadingSettings")}</div> : null}
      {settings ? (
        <section className="mb-4 rounded-md border border-line bg-surface p-4 shadow-soft">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-ink">{t("analysisDefaults")}</h2>
              <p className="mt-1 text-xs text-muted">{t("poseSampleFpsHelp")}</p>
            </div>
            <div className="flex items-center gap-3">
              {saved ? <span className="text-sm font-semibold text-court">{t("saved")}</span> : null}
              <button className="focus-ring rounded-md bg-court px-4 py-2 text-sm font-semibold text-white disabled:opacity-55" type="button" disabled={saving} onClick={handleSave}>
                {saving ? t("saving") : t("saveSettings")}
              </button>
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <NumberField label={t("sampleFps")} min={1} max={15} step={1} value={settings.sample_fps} onChange={(value) => patchSettings({ sample_fps: value })} />
            <NumberField label={t("yoloImageSize")} min={320} max={1920} step={32} value={settings.yolo_imgsz} onChange={(value) => patchSettings({ yolo_imgsz: value })} />
            <NumberField label={t("yoloConfidence")} min={0.01} max={0.8} step={0.01} value={settings.yolo_conf} onChange={(value) => patchSettings({ yolo_conf: value })} />
            <NumberField label={t("yoloIou")} min={0.1} max={0.9} step={0.01} value={settings.yolo_iou} onChange={(value) => patchSettings({ yolo_iou: value })} />
            <NumberField label={t("yoloMaxDet")} min={1} max={80} step={1} value={settings.yolo_max_det} onChange={(value) => patchSettings({ yolo_max_det: value })} />
            <NumberField label={t("cropImageSize")} min={320} max={2560} step={32} value={settings.yolo_court_crop_imgsz} onChange={(value) => patchSettings({ yolo_court_crop_imgsz: value })} />
            <NumberField label={t("cropConfidence")} min={0.01} max={0.5} step={0.01} value={settings.yolo_court_crop_conf} onChange={(value) => patchSettings({ yolo_court_crop_conf: value })} />
            <ToggleField label={t("cropSecondPass")} checked={settings.yolo_court_crop_second_pass} onChange={(value) => patchSettings({ yolo_court_crop_second_pass: value })} />
            <ToggleField label={t("shuttleDetection")} checked={settings.enable_shuttle_detection} onChange={(value) => patchSettings({ enable_shuttle_detection: value })} />
            <ToggleField label={t("tracknetDetection")} checked={settings.enable_tracknet} onChange={(value) => patchSettings({ enable_tracknet: value })} />
            <ToggleField label={t("tracknetLargeVideo")} checked={settings.tracknet_large_video} onChange={(value) => patchSettings({ tracknet_large_video: value })} />
            <NumberField label={t("tracknetBatchSize")} min={1} max={8} step={1} value={settings.tracknet_batch_size} onChange={(value) => patchSettings({ tracknet_batch_size: value })} />
            <NumberField label={t("tracknetProxyWidth")} min={480} max={1280} step={32} value={settings.tracknet_proxy_max_width} onChange={(value) => patchSettings({ tracknet_proxy_max_width: value })} />
            <NumberField label={t("tracknetMaxSamples")} min={64} max={1200} step={32} value={settings.tracknet_max_sample_num} onChange={(value) => patchSettings({ tracknet_max_sample_num: value })} />
            <NumberField label={t("tracknetTimeout")} min={60} max={1800} step={30} value={settings.tracknet_timeout_sec} onChange={(value) => patchSettings({ tracknet_timeout_sec: value })} />
          </div>
        </section>
      ) : null}

      {health ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Setting label={t("apiUrl")} value={API_BASE} />
          <Setting label={t("status")} value={health.status === "ok" ? t("enabled") : health.status} />
          <Setting label={t("inferenceDevice")} value={health.device} />
          <Setting label={t("cudaAvailable")} value={health.cuda_available ? t("yes") : t("no")} />
          <Setting label={t("model")} value={health.model_name} />
          <Setting
            label={t("yoloParams")}
            value={`imgsz ${health.yolo_imgsz} · conf ${health.yolo_conf} · iou ${health.yolo_iou} · max ${health.yolo_max_det} · crop ${health.yolo_court_crop_second_pass ? `${health.yolo_court_crop_imgsz}/${health.yolo_court_crop_conf}` : t("disabled")}`}
          />
          <Setting label={t("sampleFps")} value={`${health.sample_fps}`} />
          <Setting label={t("shuttleDetection")} value={health.shuttle_detection_enabled ? t("enabled") : t("disabled")} />
          <Setting label={t("tracknetDetection")} value={health.tracknet_enabled ? t("enabled") : t("disabled")} />
          <Setting label={t("tracknetReady")} value={health.tracknet_ready ? t("yes") : t("no")} />
          <Setting label={t("tracknetBusy")} value={health.tracknet_busy ? t("yes") : t("no")} />
          <Setting label={t("tracknetBatchSize")} value={`${health.tracknet_batch_size}`} />
          <Setting label={t("tracknetProxyWidth")} value={`${health.tracknet_proxy_max_width}`} />
          <Setting label={t("tracknetMaxSamples")} value={`${health.tracknet_max_sample_num}`} />
          <Setting label={t("tracknetTimeout")} value={`${health.tracknet_timeout_sec}`} />
          <Setting label={t("tracknetRepo")} value={health.tracknet_repo_dir} />
          <Setting label={t("tracknetModel")} value={health.tracknet_tracknet_file} />
          <Setting label={t("inpaintModel")} value={health.tracknet_inpaintnet_file} />
          <Setting label={t("mockFallback")} value={health.mock_enabled ? t("enabled") : t("disabled")} />
          <Setting label={t("dataDirectory")} value={health.data_dir} />
        </div>
      ) : null}
    </div>
  );
}

function Setting({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4 shadow-soft">
      <div className="text-xs font-medium uppercase text-muted">{label}</div>
      <div className="mt-2 break-all text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}

function PreferenceCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4 shadow-soft">
      <div className="mb-3 text-xs font-medium uppercase text-muted">{label}</div>
      {children}
    </div>
  );
}

function PreferenceButton({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      className={`focus-ring rounded-md border px-3 py-2 text-sm font-semibold transition ${
        active ? "border-court bg-court text-white" : "border-line bg-subtle text-muted hover:text-ink"
      }`}
      type="button"
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="grid gap-2">
      <span className="text-xs font-semibold uppercase text-muted">{label}</span>
      <input
        className="focus-ring rounded-md border border-line bg-subtle px-3 py-2 text-sm font-semibold text-ink"
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

function ToggleField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-md border border-line bg-subtle px-3 py-2">
      <span className="text-xs font-semibold uppercase text-muted">{label}</span>
      <input className="h-4 w-4 accent-court" type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
