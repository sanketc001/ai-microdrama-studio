import { useState } from "react";
import { motion } from "framer-motion";
import type { Session } from "../types";

interface Props {
  session: Session;
  onSteer: (input: string) => Promise<void>;
  onCompile: () => Promise<void>;
  onPatch: (patch: { global_prompt?: string; title?: string }) => Promise<void>;
}

export function DirectorPanel({ session, onSteer, onCompile, onPatch }: Props) {
  const [steer, setSteer] = useState("");
  const [busy, setBusy] = useState<"steer" | "compile" | null>(null);
  const story = session.story || {};

  async function doSteer(text: string) {
    if (!text.trim()) return;
    setBusy("steer");
    await onSteer(text);
    setSteer("");
    setBusy(null);
  }

  async function doCompile() {
    setBusy("compile");
    await onCompile();
    setBusy(null);
  }

  return (
    <div>
      <div className="col-head">
        <span className="h">The Story</span>
        {busy === "steer" && <span className="spin-inline" />}
      </div>

      <div className="label">Logline</div>
      <p className="serif" style={{ fontSize: 16, lineHeight: 1.5, margin: "6px 0 18px" }}>
        {story.logline || session.premise || "—"}
      </p>

      {story.beats?.length ? (
        <>
          <div className="label" style={{ marginBottom: 8 }}>Beats</div>
          {story.beats.map((b, i) => (
            <motion.div key={i} className="beat" initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
              <div className="s">{String(i + 1).padStart(2, "0")} · {b.summary}</div>
              <div className="d">{b.scene}</div>
            </motion.div>
          ))}
        </>
      ) : null}

      {story.choices?.length ? (
        <>
          <div className="label" style={{ margin: "18px 0 8px" }}>Steer the story</div>
          {story.choices.map((c, i) => (
            <div key={i} className="choice" onClick={() => doSteer(`${c.label}: ${c.consequence}`)}>
              <div className="lab">→ {c.label}</div>
              <div className="con">{c.consequence}</div>
            </div>
          ))}
        </>
      ) : null}

      <div className="steer-box stack">
        <textarea
          rows={2}
          placeholder="Or type your own direction — a twist, a line, a mood…"
          value={steer}
          onChange={(e) => setSteer(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) doSteer(steer); }}
        />
        <div className="flex">
          <button className="btn btn-sm" onClick={() => doSteer(steer)} disabled={busy === "steer"}>
            Steer ⏎
          </button>
        </div>
      </div>

      <div className="label" style={{ margin: "22px 0 6px" }}>Global anchor prompt</div>
      <textarea
        rows={2}
        defaultValue={session.global_prompt}
        placeholder="Persistent style / character / setting for the whole video"
        onBlur={(e) => { if (e.target.value !== session.global_prompt) onPatch({ global_prompt: e.target.value }); }}
      />

      <button
        className="btn btn-amber"
        style={{ width: "100%", justifyContent: "center", marginTop: 18 }}
        onClick={doCompile}
        disabled={busy === "compile"}
      >
        {busy === "compile" ? <span className="spin-inline" /> : "🎬"} Compile to timeline
      </button>
      <p className="muted" style={{ fontSize: 11, marginTop: 8, textAlign: "center" }}>
        Lets the director lay out shots & dialogue you can refine →
      </p>
    </div>
  );
}
