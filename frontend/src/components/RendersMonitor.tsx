import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { JobSummary } from "../types";

const KIND_LABEL: Record<string, string> = {
  render: "Render",
  animatic: "Voices",
  scene_image: "Scene still",
  character_image: "Portrait",
  character_voice: "Voice",
  tts_preview: "TTS preview",
};

function rel(ts: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

/** Global, always-visible monitor of running renders & jobs (top bar). */
export function RendersMonitor() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [open, setOpen] = useState(false);
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    let alive = true;
    const tick = () =>
      api.listJobs()
        .then((j) => { if (alive) { setJobs(j); setReachable(true); } })
        .catch(() => { if (alive) setReachable(false); });
    tick();
    const t = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const active = jobs.filter((j) => j.status === "running" || j.status === "queued");

  return (
    <div className="renders-monitor">
      <button className="btn btn-sm" onClick={() => setOpen((o) => !o)} title="Running renders & jobs">
        {active.length ? <i className="pulse-dot" /> : "◷"}&nbsp;Renders{active.length ? ` ${active.length}` : ""}
      </button>

      {open && (
        <div className="renders-panel panel">
          <div className="row-between" style={{ marginBottom: 8 }}>
            <span className="label">Activity</span>
            <button className="btn btn-sm btn-ghost" onClick={() => setOpen(false)}>✕</button>
          </div>

          {!reachable && <div className="pill red">backend unreachable</div>}
          {reachable && jobs.length === 0 && (
            <div className="muted" style={{ fontSize: 12 }}>No jobs yet.</div>
          )}

          {jobs.map((j) => {
            const running = j.status === "running" || j.status === "queued";
            const pct = j.progress?.pct;
            return (
              <div key={j.id} className="job-row">
                {j.preview
                  ? <img className="job-thumb" src={j.preview} alt="" />
                  : <div className="job-thumb ph" />}
                <div className="job-info">
                  <div className="row-between">
                    <span className="job-kind">{KIND_LABEL[j.kind] || j.kind}</span>
                    <span className={`pill ${j.status === "error" ? "red" : running ? "amber" : "teal"}`}>
                      {j.status}
                    </span>
                  </div>
                  {running && (
                    <div className="progress" style={{ margin: "5px 0" }}>
                      <i style={{ width: `${pct ?? 5}%` }} />
                    </div>
                  )}
                  <div className="job-meta">
                    {j.progress?.stage ? `${j.progress.stage}${pct ? ` ${pct}%` : ""} · ` : ""}
                    {rel(j.created)}
                    {j.error ? " · failed" : ""}
                  </div>
                  <div className="flex" style={{ marginTop: 4 }}>
                    {j.meta?.session && (
                      <Link className="btn btn-sm btn-ghost" to={`/studio/${j.meta.session}`} onClick={() => setOpen(false)}>
                        open
                      </Link>
                    )}
                    {running && j.kind === "render" && (
                      <button className="btn btn-sm btn-ghost" onClick={() => api.interruptJob(j.id).catch(() => {})}>
                        ✕ abort
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
