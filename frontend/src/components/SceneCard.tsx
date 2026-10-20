import { useState } from "react";
import { api, pollJob } from "../api";
import type { Character, DialogueLine, Scene, Session } from "../types";
import { SceneScript } from "./SceneScript";

interface Props {
  scene: Scene;
  index: number;
  total: number;
  sessionId: string;
  characters: Character[];
  onUpdate: (patch: Partial<Scene>) => void;
  onDelete: () => void;
  onMove: (dir: -1 | 1) => void;
  onGenImage: (onProg: (p: number) => void) => Promise<void>;
  onSession: (s: Session) => void;
  flash: (msg: string, err?: boolean) => void;
}

export function SceneCard({ scene, index, total, sessionId, characters, onUpdate, onDelete, onMove, onGenImage, onSession, flash }: Props) {
  const [imgProg, setImgProg] = useState<number | null>(null);
  const [ttsBusy, setTtsBusy] = useState<number | null>(null);
  const isImage = scene.type === "image";

  async function generate() {
    setImgProg(0);
    await onGenImage((p) => setImgProg(p));
    setImgProg(null);
  }

  async function uploadImage(file: File) {
    setImgProg(0);
    try {
      onSession(await api.uploadSceneImage(sessionId, scene.id, file));
      flash("Guide image uploaded");
    } catch (e: any) {
      flash(String(e.message || e), true);
    } finally {
      setImgProg(null);
    }
  }

  function setDialogue(i: number, patch: Partial<DialogueLine>) {
    const dialogue = scene.dialogue.map((d, j) => (j === i ? { ...d, ...patch } : d));
    onUpdate({ dialogue });
  }
  function addLine() {
    onUpdate({ dialogue: [...scene.dialogue, { speaker: "", text: "", voice: "neutral, clear" }] });
  }
  function removeLine(i: number) {
    onUpdate({ dialogue: scene.dialogue.filter((_, j) => j !== i) });
  }

  async function previewVoice(i: number) {
    const line = scene.dialogue[i];
    if (!line.text.trim()) return;
    setTtsBusy(i);
    try {
      const job = await api.ttsPreview(line.text, line.voice || "neutral, clear");
      const done = await pollJob(job.id, () => {});
      const url = done.result?.url;
      if (url) new Audio(url).play();
      else flash("No audio produced", true);
    } catch (e: any) {
      flash(String(e.message || e), true);
    } finally {
      setTtsBusy(null);
    }
  }

  return (
    <div className="scene">
      <div className="slate">
        {isImage && scene.image_url ? (
          <img src={scene.image_url} alt="" />
        ) : null}
        <div className={`scene-no ${isImage ? "" : "teal"}`}>{String(index + 1).padStart(2, "0")}</div>
        {imgProg !== null ? (
          <div className="ph"><span className="spin-inline" /> {imgProg}%</div>
        ) : isImage && !scene.image_url ? (
          <div className="ph">no still yet</div>
        ) : (
          <div className="ph">{isImage ? "guide still" : "text shot"}</div>
        )}
      </div>

      <div className="body stack">
        <div className="top">
          <div className="flex">
            <button
              className={`pill ${isImage ? "amber" : "teal"}`}
              onClick={() => onUpdate({ type: isImage ? "text" : "image" })}
              style={{ cursor: "pointer" }}
              title="Toggle shot type"
            >
              {isImage ? "▣ image" : "≣ text"}
            </button>
            <span className="dur">
              <input
                type="number" min={1} max={10} step={0.5}
                style={{ width: 64, padding: "5px 8px" }}
                defaultValue={scene.seconds}
                onChange={(e) => onUpdate({ seconds: Number(e.target.value) })}
              />
              <span className="tc">{scene.seconds.toFixed(1)}s</span>
            </span>
          </div>
          <div className="flex">
            <button className="btn btn-sm btn-ghost" disabled={index === 0} onClick={() => onMove(-1)}>↑</button>
            <button className="btn btn-sm btn-ghost" disabled={index === total - 1} onClick={() => onMove(1)}>↓</button>
            <button className="btn btn-sm btn-ghost" onClick={onDelete} title="Delete shot">✕</button>
          </div>
        </div>

        <textarea
          className="serif" rows={2}
          placeholder="What happens in this shot (action / motion, present tense)…"
          defaultValue={scene.prompt}
          onBlur={(e) => e.target.value !== scene.prompt && onUpdate({ prompt: e.target.value })}
        />

        <label className="btn btn-sm btn-ghost" style={{ alignSelf: "flex-start" }}>
          ⤒ upload guide image
          <input type="file" accept="image/*" hidden onChange={(e) => {
            const f = e.target.files?.[0]; if (f) uploadImage(f);
            (e.target as HTMLInputElement).value = "";
          }} />
        </label>

        {isImage && (
          <>
            <textarea
              rows={1}
              placeholder="Image prompt for the guide still…"
              defaultValue={scene.image_prompt}
              onBlur={(e) => e.target.value !== scene.image_prompt && onUpdate({ image_prompt: e.target.value })}
            />
            <div className="flex row-between">
              <button className="btn btn-sm" onClick={generate} disabled={imgProg !== null}>
                {imgProg !== null ? <span className="spin-inline" /> : "✦"} {scene.image_url ? "Regenerate still" : "Generate still"}
              </button>
              <label className="flex" style={{ fontSize: 10 }} title="Guide strength">
                <span className="label">guide</span>
                <input
                  type="range" min={0} max={1} step={0.05}
                  defaultValue={scene.guide_strength ?? 1}
                  style={{ width: 80 }}
                  onChange={(e) => onUpdate({ guide_strength: Number(e.target.value) })}
                />
              </label>
            </div>
          </>
        )}

        {characters.length > 0 && (
          <div className="stack" style={{ gap: 5 }}>
            <span className="label">characters in this shot (uses their portrait as reference)</span>
            <div className="flex" style={{ flexWrap: "wrap" }}>
              {characters.map((c) => {
                const on = (scene.character_ids || []).includes(c.id!);
                return (
                  <button
                    key={c.id}
                    className={`pill ${on ? "amber" : ""}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => {
                      const ids = new Set(scene.character_ids || []);
                      if (on) ids.delete(c.id!); else ids.add(c.id!);
                      onUpdate({ character_ids: [...ids] });
                    }}
                  >
                    {c.image_url ? "◉" : "○"} {c.name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <div className="row-between" style={{ marginTop: 4 }}>
          <span className="label">Dialogue</span>
          <button className="btn btn-sm btn-ghost" onClick={addLine}>+ line</button>
        </div>
        {scene.dialogue.map((d, i) => (
          <div key={i} className="dialogue-line">
            <input
              className="sp" style={{ width: 80 }}
              placeholder="who"
              defaultValue={d.speaker}
              onBlur={(e) => setDialogue(i, { speaker: e.target.value })}
            />
            <div className="stack" style={{ flex: 1 }}>
              <input
                placeholder="line of dialogue (supports [laughter], [sigh]…)"
                defaultValue={d.text}
                onBlur={(e) => setDialogue(i, { text: e.target.value })}
              />
              <div className="flex">
                <input
                  style={{ flex: 1, fontSize: 11 }}
                  placeholder="voice tags: female, warm, british accent"
                  defaultValue={d.voice}
                  onBlur={(e) => setDialogue(i, { voice: e.target.value })}
                />
                <button className="btn btn-sm btn-ghost" onClick={() => previewVoice(i)} disabled={ttsBusy === i}>
                  {ttsBusy === i ? <span className="spin-inline" /> : "▶"}
                </button>
                <button className="btn btn-sm btn-ghost" onClick={() => removeLine(i)}>✕</button>
              </div>
            </div>
          </div>
        ))}

        <SceneScript
          sessionId={sessionId}
          sceneId={scene.id}
          initialScript={scene.script}
          onGenerated={onSession}
          flash={flash}
        />
      </div>
    </div>
  );
}
