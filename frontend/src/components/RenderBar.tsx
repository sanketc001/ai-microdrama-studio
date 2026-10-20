import type { Job, Session } from "../types";

interface Props {
  session: Session;
  job: Job | null;
  onRender: () => void;
  onOpenStage: () => void;
  onPreview: () => void;
  onGallery: () => void;
  onBranch: () => void;
  onContinue: () => void;
}

export function RenderBar({ session, job, onRender, onOpenStage, onPreview, onGallery, onBranch, onContinue }: Props) {
  const rendering = job?.status === "running" || job?.status === "queued";
  const pct = job?.progress?.pct ?? 0;
  const stage = job?.progress?.stage;
  const total = session.scenes.reduce((a, s) => a + (s.seconds || 0), 0);
  const canRender = session.scenes.length > 0 && !rendering;

  return (
    <div className="render-bar">
      <div className="stack" style={{ gap: 3, minWidth: 150 }}>
        <span className="label">final cut</span>
        <span className="display" style={{ fontSize: 22, color: "var(--ink)" }}>
          {total.toFixed(1)}s · {session.scenes.length} shots
        </span>
      </div>

      {rendering ? (
        <>
          <div className="progress"><i style={{ width: `${pct}%` }} /></div>
          <span className="pill amber">
            <span className="spin-inline" /> &nbsp;{stage ? stage.toUpperCase() : "RENDER"} {pct ? `${pct}%` : ""}
          </span>
        </>
      ) : (
        <div style={{ flex: 1 }} />
      )}

      <button className="btn" onClick={onGallery}>🖼 Gallery</button>
      <button className="btn" onClick={onBranch} title="Copy as a new take">⎘ Branch</button>
      <button className="btn" onClick={onContinue} disabled={!session.video_url}
              title="New shot seeded from the last rendered frame">▸ Continue</button>
      <button className="btn" onClick={onPreview} disabled={session.scenes.length === 0}>
        ▶ Preview
      </button>
      {session.video_url && !rendering && (
        <button className="btn" onClick={onOpenStage}>🎞 View cut</button>
      )}
      <button className="btn btn-amber" onClick={onRender} disabled={!canRender}>
        {rendering ? "Rendering…" : "● Render micro-drama"}
      </button>
    </div>
  );
}
