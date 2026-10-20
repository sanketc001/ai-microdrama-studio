import { useEffect, useState } from "react";
import { api } from "../api";
import type { Gallery as GalleryT, Session } from "../types";

interface Props {
  sessionId: string;
  onClose: () => void;
  onSession: (s: Session) => void;
  flash: (msg: string, err?: boolean) => void;
}

function when(mtime: number): string {
  return new Date(mtime * 1000).toLocaleString();
}

/** All stills (per scene) and renders ever produced for a session, with the
 *  ability to restore any previous one as the current. */
export function Gallery({ sessionId, onClose, onSession, flash }: Props) {
  const [g, setG] = useState<GalleryT | null>(null);

  const load = () => api.getGallery(sessionId).then(setG).catch((e) => flash(String(e.message), true));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function useStill(sceneId: string, name: string) {
    try { onSession(await api.selectSceneImage(sessionId, sceneId, name)); flash("Still restored."); load(); }
    catch (e: any) { flash(String(e.message || e), true); }
  }
  async function useRender(name: string) {
    try { onSession(await api.selectRender(sessionId, name)); flash("Render set as current."); load(); }
    catch (e: any) { flash(String(e.message || e), true); }
  }

  return (
    <div className="stage-overlay" onClick={onClose}>
      <div className="panel gallery" onClick={(e) => e.stopPropagation()}>
        <div className="row-between" style={{ marginBottom: 14 }}>
          <span className="display" style={{ fontSize: 30 }}>Gallery</span>
          <div className="flex">
            <button className="btn btn-sm btn-ghost" onClick={load}>↻ refresh</button>
            <button className="btn btn-sm btn-ghost" onClick={onClose}>✕ close</button>
          </div>
        </div>

        {!g && <div className="muted">Loading…</div>}

        {g && (
          <>
            <div className="gallery-section">
              <div className="label" style={{ marginBottom: 8 }}>Renders ({g.renders.length})</div>
              {g.renders.length === 0 ? (
                <div className="muted" style={{ fontSize: 12 }}>No renders yet.</div>
              ) : (
                <div className="gallery-grid">
                  {g.renders.map((r) => (
                    <div key={r.name} className={`gallery-card ${r.is_current ? "current" : ""}`}>
                      {r.url && <video src={r.url} controls muted preload="metadata" />}
                      <div className="g-meta">{when(r.mtime)}</div>
                      <div className="flex">
                        {r.is_current
                          ? <span className="pill amber">current</span>
                          : <button className="btn btn-sm" onClick={() => useRender(r.name)}>use</button>}
                        {r.url && <a className="btn btn-sm btn-ghost" href={r.url} download>↓</a>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {g.scenes.map((sc, i) => (
              <div key={sc.id} className="gallery-section">
                <div className="label" style={{ marginBottom: 8 }}>
                  Shot {String(i + 1).padStart(2, "0")} — {sc.prompt?.slice(0, 70) || "(untitled)"} · {sc.stills.length} still(s)
                </div>
                {sc.stills.length === 0 ? (
                  <div className="muted" style={{ fontSize: 12 }}>No stills generated for this shot yet.</div>
                ) : (
                  <div className="gallery-grid stills">
                    {sc.stills.map((st) => (
                      <div key={st.name} className={`gallery-card ${st.is_current ? "current" : ""}`}>
                        {st.url && <img className="g-thumb" src={st.url} alt="" />}
                        <div className="g-meta">{when(st.mtime)}</div>
                        {st.is_current
                          ? <span className="pill amber">current</span>
                          : <button className="btn btn-sm" onClick={() => useStill(sc.id, st.name)}>use this still</button>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
