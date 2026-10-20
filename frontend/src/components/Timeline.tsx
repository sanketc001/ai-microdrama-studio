import type { Character, Scene, Session } from "../types";
import { SceneCard } from "./SceneCard";

interface Props {
  session: Session;
  characters: Character[];
  onAdd: (scene: Partial<Scene>) => void;
  onUpdate: (sid: string, patch: Partial<Scene>) => void;
  onDelete: (sid: string) => void;
  onReorder: (order: string[]) => void;
  onGenImage: (sid: string, onProg: (p: number) => void) => Promise<void>;
  onSession: (s: Session) => void;
  flash: (msg: string, err?: boolean) => void;
}

export function Timeline({ session, characters, onAdd, onUpdate, onDelete, onReorder, onGenImage, onSession, flash }: Props) {
  const scenes = session.scenes;
  const total = scenes.reduce((a, s) => a + (s.seconds || 0), 0);

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= scenes.length) return;
    const ids = scenes.map((s) => s.id);
    [ids[i], ids[j]] = [ids[j], ids[i]];
    onReorder(ids);
  }

  return (
    <div>
      <div className="timeline-head">
        <div>
          <span className="col-head" style={{ display: "block" }}>
            <span className="h">Timeline</span>
          </span>
          <span className="label">{scenes.length} shots · {total.toFixed(1)}s total</span>
        </div>
      </div>

      <div className="ruler">
        {Array.from({ length: 40 }).map((_, i) => <span key={i} className="tick" />)}
      </div>

      {scenes.length === 0 ? (
        <div className="empty">
          <div className="big">Empty reel</div>
          <p className="muted">Compile the story into shots, or add one below.</p>
        </div>
      ) : (
        scenes.map((sc, i) => (
          <SceneCard
            key={sc.id}
            scene={sc}
            index={i}
            total={scenes.length}
            sessionId={session.id}
            characters={characters}
            onUpdate={(patch) => onUpdate(sc.id, patch)}
            onDelete={() => onDelete(sc.id)}
            onMove={(dir) => move(i, dir)}
            onGenImage={(onProg) => onGenImage(sc.id, onProg)}
            onSession={onSession}
            flash={flash}
          />
        ))
      )}

      <div className="add-scene">
        <button className="btn btn-sm" onClick={() => onAdd({ type: "text", prompt: "", seconds: 3 })}>
          + text shot
        </button>
        <button className="btn btn-sm" onClick={() => onAdd({ type: "image", prompt: "", image_prompt: "", seconds: 3 })}>
          + image shot
        </button>
      </div>
    </div>
  );
}
