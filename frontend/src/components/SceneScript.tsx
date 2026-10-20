import { useState } from "react";
import { api } from "../api";
import type { Session } from "../types";
import { CopyBox } from "./CopyBox";

interface Props {
  sessionId: string;
  sceneId: string;
  initialScript?: string;
  onGenerated: (s: Session) => void;
  flash: (msg: string, err?: boolean) => void;
}

export function SceneScript({ sessionId, sceneId, initialScript, onGenerated, flash }: Props) {
  const [open, setOpen] = useState(!!initialScript);
  const [concept, setConcept] = useState("");
  const [dialogue, setDialogue] = useState("");
  const [busy, setBusy] = useState(false);
  const [script, setScript] = useState(initialScript || "");

  async function generate() {
    setBusy(true);
    try {
      const res = await api.sceneScript(sessionId, sceneId, concept, dialogue);
      setScript(res.script);
      onGenerated(res.session);
      flash("Scene script generated → used as the shot prompt");
    } catch (e: any) {
      flash(String(e.message || e), true);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button className="btn btn-sm btn-ghost" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(true)}>
        🎬 scene script
      </button>
    );
  }

  return (
    <div className="scene-script stack">
      <div className="row-between">
        <span className="label">scene script — image-grounded video prompt</span>
        <button className="btn btn-sm btn-ghost" onClick={() => setOpen(false)}>▾</button>
      </div>
      <input placeholder="concept — the basic idea / motion to center on" value={concept} onChange={(e) => setConcept(e.target.value)} />
      <input placeholder="dialogue or sound concept (optional)" value={dialogue} onChange={(e) => setDialogue(e.target.value)} />
      <div className="flex">
        <button className="btn btn-sm btn-amber" onClick={generate} disabled={busy}>
          {busy ? <span className="spin-inline" /> : "✦"} {script ? "Regenerate" : "Generate"}
        </button>
        <span className="muted" style={{ fontSize: 10 }}>uses this shot's guide still as the reference frame</span>
      </div>
      {script && <CopyBox text={script} />}
    </div>
  );
}
