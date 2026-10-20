import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, pollJob } from "../api";
import type { Character, Job, Presets, Scene, Session } from "../types";
import { DirectorPanel } from "./DirectorPanel";
import { Timeline } from "./Timeline";
import { PresetsSidebar } from "./PresetsSidebar";
import { RenderBar } from "./RenderBar";
import { CharacterStudio } from "./CharacterStudio";
import { Animatic } from "./Animatic";
import { Gallery } from "./Gallery";

export function Studio() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const [session, setSession] = useState<Session | null>(null);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [toast, setToast] = useState<{ msg: string; err?: boolean } | null>(null);
  const [renderJob, setRenderJob] = useState<Job | null>(null);
  const [showStage, setShowStage] = useState(false);
  const [showCasting, setShowCasting] = useState(false);
  const [showAnimatic, setShowAnimatic] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [preparingVoices, setPreparingVoices] = useState(false);

  const flash = useCallback((msg: string, err = false) => {
    setToast({ msg, err });
    setTimeout(() => setToast(null), err ? 6000 : 3000);
  }, []);

  useEffect(() => {
    api.getSession(id).then(setSession).catch((e) => flash(String(e.message), true));
    api.presets().then(setPresets).catch(() => {});
    api.listCharacters().then(setCharacters).catch(() => {});
  }, [id, flash]);

  const loadCharacters = useCallback(() => {
    api.listCharacters().then(setCharacters).catch(() => {});
  }, []);

  const guard = useCallback(
    async (p: Promise<Session>) => {
      try {
        setSession(await p);
      } catch (e: any) {
        flash(String(e.message || e), true);
      }
    },
    [flash],
  );

  // scene helpers
  const addScene = (scene: Partial<Scene>) => guard(api.addScene(id, scene));
  const updateScene = (sid: string, patch: Partial<Scene>) => guard(api.updateScene(id, sid, patch));
  const deleteScene = (sid: string) => guard(api.deleteScene(id, sid));
  const reorder = (order: string[]) => guard(api.reorderScenes(id, order));

  async function genSceneImage(sid: string, onProg: (p: number) => void) {
    try {
      const job = await api.genSceneImage(id, sid);
      await pollJob(job.id, (j) => onProg(j.progress?.pct ?? 0));
      setSession(await api.getSession(id));
      flash("Guide still generated.");
    } catch (e: any) {
      flash(String(e.message || e), true);
    }
  }

  async function render() {
    setShowStage(true); // show live preview frames as the render runs
    try {
      const job = await api.render(id);
      setRenderJob(job);
      const done = await pollJob(job.id, setRenderJob);
      setRenderJob(done);
      setSession(await api.getSession(id));
      flash("Render complete.");
    } catch (e: any) {
      flash(String(e.message || e), true);
      setRenderJob((j) => (j ? { ...j, status: "error" } : j));
    }
  }

  async function prepareVoices() {
    setPreparingVoices(true);
    try {
      const job = await api.prepareAnimatic(id);
      await pollJob(job.id, () => {});
      setSession(await api.getSession(id));
      flash("Voices ready — replay the animatic.");
    } catch (e: any) {
      flash(String(e.message || e), true);
    } finally {
      setPreparingVoices(false);
    }
  }

  async function abortRender() {
    try {
      await api.interruptRender(id);
      flash("Aborting render…");
    } catch (e: any) {
      flash(String(e.message || e), true);
    }
  }

  async function branch() {
    try { const s = await api.branchSession(id); flash("Branched into a new take."); nav(`/studio/${s.id}`); }
    catch (e: any) { flash(String(e.message || e), true); }
  }

  async function continueStory() {
    try {
      flash("Extracting last frame & directing what's next…");
      const s = await api.continueSession(id);
      nav(`/studio/${s.id}`);
    } catch (e: any) { flash(String(e.message || e), true); }
  }

  if (!session) {
    return (
      <div className="empty" style={{ paddingTop: 120 }}>
        <div className="spinner-film" />
        <div className="big">Loading set…</div>
      </div>
    );
  }

  return (
    <>
      <div className="studio">
        <aside className="studio-col left">
          {session.parent_id && (
            <Link className="pill teal" to={`/studio/${session.parent_id}`}
                  style={{ display: "inline-block", marginBottom: 12 }}>
              ↑ from parent take
            </Link>
          )}
          <DirectorPanel
            session={session}
            onSteer={(input) => guard(api.steer(id, input))}
            onCompile={() => guard(api.compile(id))}
            onPatch={(patch) => guard(api.patchSession(id, patch))}
          />
        </aside>

        <main className="studio-col center" style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1 }}>
            <Timeline
              session={session}
              characters={characters}
              onAdd={addScene}
              onUpdate={updateScene}
              onDelete={deleteScene}
              onReorder={reorder}
              onGenImage={genSceneImage}
              onSession={setSession}
              flash={flash}
            />
          </div>
          <RenderBar
            session={session}
            job={renderJob}
            onRender={render}
            onOpenStage={() => setShowStage(true)}
            onPreview={() => setShowAnimatic(true)}
            onGallery={() => setShowGallery(true)}
            onBranch={branch}
            onContinue={continueStory}
          />
        </main>

        <aside className="studio-col right">
          <button
            className="btn btn-amber"
            style={{ width: "100%", justifyContent: "center", marginBottom: 16 }}
            onClick={() => setShowCasting(true)}
          >
            🎭 Casting — characters
          </button>
          <PresetsSidebar presets={presets} onUseScene={addScene} flash={flash} />
        </aside>
      </div>

      {showCasting && (
        <CharacterStudio onClose={() => setShowCasting(false)} onChanged={loadCharacters} />
      )}

      {showAnimatic && (
        <Animatic
          session={session}
          onClose={() => setShowAnimatic(false)}
          onPrepareVoices={prepareVoices}
          preparingVoices={preparingVoices}
        />
      )}

      {showGallery && (
        <Gallery
          sessionId={session.id}
          onClose={() => setShowGallery(false)}
          onSession={setSession}
          flash={flash}
        />
      )}

      {showStage && (
        <div className="stage-overlay" onClick={() => setShowStage(false)}>
          <div className="stage panel" onClick={(e) => e.stopPropagation()}>
            {renderJob && (renderJob.status === "running" || renderJob.status === "queued") ? (
              <>
                {renderJob.preview ? (
                  <img className="live-preview" src={renderJob.preview} alt="live preview" />
                ) : (
                  <div className="spinner-film" />
                )}
                <div className="reel">ROLLING…</div>
                <p className="muted">
                  {(renderJob.progress?.stage || "render").toUpperCase()}
                  {renderJob.progress?.pct ? ` · ${renderJob.progress.pct}%` : ""}
                  {" · "}{renderJob.logs?.slice(-1)[0] || ""}
                </p>
                <div className="flex" style={{ justifyContent: "center", marginTop: 12 }}>
                  <button className="btn btn-ghost" onClick={() => setShowStage(false)}>Hide (keeps rendering)</button>
                  <button className="btn" onClick={abortRender}>✕ Abort</button>
                </div>
              </>
            ) : session.video_url ? (
              <>
                <div className="reel">THAT'S A WRAP</div>
                <video src={session.video_url} controls autoPlay loop />
                <div className="flex" style={{ justifyContent: "center", marginTop: 16 }}>
                  <a className="btn" href={session.video_url} download>↓ Download</a>
                  <button className="btn btn-ghost" onClick={() => setShowStage(false)}>Back to set</button>
                </div>
              </>
            ) : (
              <>
                <div className="spinner-film" />
                <div className="reel">PREPARING…</div>
              </>
            )}
          </div>
        </div>
      )}

      {toast && <div className={`toast ${toast.err ? "err" : ""}`}>{toast.msg}</div>}
    </>
  );
}
