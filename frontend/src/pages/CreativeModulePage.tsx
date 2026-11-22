import React, { useEffect, useState } from "react";
import { Box, Download, Image as ImageIcon, Mic, Music, RefreshCw, Video } from "lucide-react";
import { apiFetch, downloadAuthFile } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { VoiceView } from "../components/CoreViews";
import {
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";

export default function CreativeModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("creative");
  const page = getSubPage("creative", subPage);
  const { pushToast } = useToast();

  const [jobs, setJobs] = useState<any[]>([]);
  const [statusData, setStatusData] = useState<any>(null);
  const [prompt, setPrompt] = useState("");
  const [threeDOutput, setThreeDOutput] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const [jRes, sRes] = await Promise.all([
        apiFetch<any>("/api/v1/creative/jobs").catch(() => ({ jobs: [] })),
        apiFetch<any>("/api/v1/integrations/status").catch(() => null),
      ]);
      setJobs(jRes.jobs || []);
      setStatusData(sRes);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function submitJob(mediaType: string) {
    if (!prompt.trim()) return;
    try {
      await apiFetch("/api/v1/creative/jobs", {
        method: "POST",
        body: { media_type: mediaType, prompt: prompt.trim() },
      });
      setPrompt("");
      pushToast(`${mediaType} creative job created.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function invoke3DAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/agents/AGT-24/invoke", {
        method: "POST",
        body: { prompt: prompt.trim() },
      });
      setThreeDOutput(res);
      pushToast("AGT-24 3D Modelling Agent completed spec.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const imgCap = statusData?.capabilities?.image_generation;
  const imgReady = imgCap?.capability_state === "AVAILABLE";

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`CREATIVE STUDIO // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 67. CREATIVE OVERVIEW */}
      {page.id === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-3">
            <MetricDisplay
              label="Local Spec & Vector Tools"
              value="Active"
              sub="SVG Vector (AGT-43) · 3D JSON Spec (AGT-24) · Voice (AGT-46)"
              tone="success"
            />
            <MetricDisplay
              label="External Image Provider"
              value={imgReady ? "Live Configured" : "Integration Required"}
              sub={imgCap?.detail || "External raster media requires provider configuration"}
              tone={imgReady ? "success" : "warn"}
            />
            <MetricDisplay label="Creative Jobs" value={jobs.length} sub="Persisted assets & specs" tone="neutral" />
          </div>
          <div className="grid-2">
            <div className="card">
              <div className="card-title">
                <span>Working Local Design &amp; Specification Tools</span>
                <StatusIndicator label="LOCAL READY" tone="success" />
              </div>
              <p className="muted" style={{ margin: 0 }}>
                SVG Brand Vector drafting (AGT-43), Three.js / WebGL 3D scene specifications (AGT-24), and browser Web Speech Voice Studio (AGT-46) run directly without external media renderers.
              </p>
            </div>
            <div className="card">
              <div className="card-title">
                <span>External Media Generation Integrations</span>
                <StatusIndicator label={imgReady ? "CONFIGURED" : "PROVIDER REQUIRED"} tone={imgReady ? "info" : "warn"} />
              </div>
              <p className="muted" style={{ margin: 0 }}>
                Raster image rendering, video synthesis, and external audio generation report real backend provider readiness. ULTRON never fabricates placeholder media outputs.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 68. IMAGE GENERATION */}
      {page.id === "image" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 680 }}>
          <div className="card-title">
            <span><ImageIcon size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Image &amp; Brand Vector Studio</span>
            <StatusIndicator label={imgReady ? "EXTERNAL PROVIDER READY" : "EXTERNAL CONFIG REQUIRED"} tone={imgReady ? "success" : "warn"} />
          </div>
          <p className="muted" style={{ margin: 0 }}>
            <strong>Brand Vector (AGT-43)</strong> generates real SVG specifications locally; <strong>Image Job (AGT-13)</strong> requires configured external image generation credentials.
          </p>
          <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the high-precision visual concept or brand vector..." />
          <div className="row">
            <button type="button" className="btn" onClick={() => submitJob("IMAGE")}>Submit External Image Job</button>
            <button type="button" className="btn btn-secondary" onClick={() => submitJob("GRAPHIC")}>Generate Local Brand Vector (AGT-43)</button>
          </div>
        </div>
      )}

      {/* 69. VIDEO PRODUCTION */}
      {page.id === "video" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 680 }}>
          <div className="card-title">
            <span><Video size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Video Storyboard &amp; Production (AGT-14)</span>
            <StatusIndicator label="SPEC + EXTERNAL RENDER" tone="info" />
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Drafts structured shot lists and production scripts via AGT-14. Final rendered video requires a connected external video rendering integration.
          </p>
          <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe video narrative, pacing, and shot list..." />
          <button type="button" className="btn" style={{ alignSelf: "flex-start" }} onClick={() => submitJob("VIDEO")}>Create Video Storyboard Job</button>
        </div>
      )}

      {/* 70. AUDIO WORKSPACE */}
      {page.id === "audio" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 680 }}>
          <div className="card-title">
            <span><Music size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Audio Production &amp; Diarization (AGT-45)</span>
            <StatusIndicator label="SPEC + EXTERNAL SYNTHESIS" tone="info" />
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Generates structured sound design &amp; narration briefs via AGT-45. External studio audio synthesis requires a configured external audio provider.
          </p>
          <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe sound design, voiceover script, or podcast production brief..." />
          <button type="button" className="btn" style={{ alignSelf: "flex-start" }} onClick={() => submitJob("AUDIO")}>Create Audio Job</button>
        </div>
      )}

      {/* 71. VOICE STUDIO */}
      {page.id === "voice" && (
        <div>
          <div className="row" style={{ marginBottom: 10 }}>
            <Mic size={15} className="muted" />
            <span className="muted">Working local browser Web Speech API voice capture &amp; interruptible speech synthesis via AGT-46.</span>
          </div>
          <VoiceView />
        </div>
      )}

      {/* 72. 3D MODELLING WORKSPACE */}
      {page.id === "3d" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span><Box size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />3D Modelling Workspace (AGT-24)</span>
            <StatusIndicator label="LOCAL SPEC READY" tone="success" />
          </div>
          <p className="muted" style={{ margin: 0 }}>
            Produces structured WebGL / Three.js JSON scene specifications directly via AGT-24. Binary mesh rendering requires external 3D asset tooling.
          </p>
          <form onSubmit={invoke3DAgent} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the 3D scene geometry, lighting, or WebGL/Three.js specification..." />
            <div className="row">
              <button type="submit" className="btn">Invoke AGT-24 Directly</button>
              <button type="button" className="btn btn-secondary" onClick={() => submitJob("3D")}>Queue 3D Studio Job</button>
            </div>
          </form>
          {threeDOutput && (
            <ReadableSummary title="3D Scene Specification (AGT-24)" data={threeDOutput} diagnosticsTitle="Technical Diagnostics — 3D Scene Payload" />
          )}
        </div>
      )}

      {/* 73. GENERATED ASSETS LIBRARY */}
      {page.id === "library" && (
        <div className="card">
          <div className="card-title"><span>Creative Studio Assets & Jobs ({jobs.length})</span></div>
          {jobs.length === 0 ? (
            <EmptyState title="No Generated Assets Yet" description="Submit a job in Image, Video, Audio, or 3D workspaces." />
          ) : (
            <DataTable
              rows={jobs}
              rowKey={(j) => j.job_id}
              columns={[
                { key: "type", header: "Type", mono: true, render: (j) => <strong>{j.media_type}</strong> },
                { key: "agent", header: "Agent", mono: true, render: (j) => j.agent_id },
                { key: "prompt", header: "Brief", render: (j) => j.prompt },
                { key: "status", header: "Status", render: (j) => <StatusIndicator label={j.status} tone={j.status === "COMPLETED" ? "success" : "warn"} /> },
                {
                  key: "dl",
                  header: "Artifact",
                  render: (j) =>
                    j.result?.download_url ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => downloadAuthFile(j.result.download_url, `studio_${j.job_id}`).catch((e) => pushToast(e.message, "error"))}
                      >
                        <Download size={12} /> Download
                      </button>
                    ) : (
                      <span className="muted">—</span>
                    ),
                },
              ]}
            />
          )}
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
