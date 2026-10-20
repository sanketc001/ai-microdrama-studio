import { useEffect, useRef, useState } from "react";
import type { Session } from "../types";

interface Props {
  session: Session;
  onClose: () => void;
  onPrepareVoices: () => Promise<void>;
  preparingVoices: boolean;
}

/** Instant timeline preview: steps through guide stills + per-scene audio +
 *  dialogue captions, timed by each shot's `seconds`. No video render. */
export function Animatic({ session, onClose, onPrepareVoices, preparingVoices }: Props) {
  const scenes = session.scenes;
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const scene = scenes[idx];
  const total = scenes.reduce((a, s) => a + (s.seconds || 0), 0) || 1;
  const missingVoices = scenes.some(
    (s) => (s.dialogue?.some((d) => d.text?.trim())) && !s.audio_url,
  );

  // Advance after max(seconds, audio length) so dialogue is never cut off.
  useEffect(() => {
    if (!playing || !scene) return;
    const done = { time: false, audio: !scene.audio_url };
    const step = () => {
      if (!done.time || !done.audio) return;
      if (idx < scenes.length - 1) setIdx(idx + 1);
      else setPlaying(false);
    };
    const timer = setTimeout(() => { done.time = true; step(); },
      Math.max(500, (scene.seconds || 3) * 1000));
    let audio: HTMLAudioElement | undefined;
    if (scene.audio_url) {
      audio = new Audio(scene.audio_url);
      audioRef.current = audio;
      audio.play().catch(() => { done.audio = true; step(); });
      audio.onended = () => { done.audio = true; step(); };
    }
    return () => { clearTimeout(timer); if (audio) { audio.pause(); audio.onended = null; } };
  }, [idx, playing]); // eslint-disable-line react-hooks/exhaustive-deps

  function jump(i: number) {
    audioRef.current?.pause();
    setIdx(Math.max(0, Math.min(scenes.length - 1, i)));
  }
  function restart() { jump(0); setPlaying(true); }

  if (!scene) {
    return (
      <div className="stage-overlay" onClick={onClose}>
        <div className="panel stage" onClick={(e) => e.stopPropagation()}>
          <div className="reel">NO SHOTS YET</div>
          <p className="muted">Add or compile some shots, then preview.</p>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  return (
    <div className="stage-overlay" onClick={onClose}>
      <div className="animatic" onClick={(e) => e.stopPropagation()}>
        <div className="animatic-frame">
          {scene.image_url ? (
            <img key={scene.id} className="kenburns" src={scene.image_url} alt="" />
          ) : (
            <div className="animatic-card">
              <div className="display" style={{ fontSize: 16, color: "var(--ink-faint)" }}>
                SHOT {String(idx + 1).padStart(2, "0")}
              </div>
              <p className="serif" style={{ fontSize: 24, lineHeight: 1.35, maxWidth: "28ch" }}>
                {scene.prompt || "(untitled shot)"}
              </p>
            </div>
          )}

          {scene.dialogue?.length ? (
            <div className="captions">
              {scene.dialogue.map((d, i) => d.text ? (
                <div key={i}>
                  {d.speaker && <span className="cap-sp">{d.speaker}: </span>}
                  {d.text}
                </div>
              ) : null)}
            </div>
          ) : null}

          <div className="animatic-badge label">
            shot {idx + 1}/{scenes.length} · {(scene.seconds || 0).toFixed(1)}s
            {scene.audio_url ? " · 🔊" : ""}
          </div>
          <button className="btn btn-sm btn-ghost animatic-close" onClick={onClose}>✕</button>
        </div>

        {/* segmented scrubber */}
        <div className="scrubber">
          {scenes.map((s, i) => (
            <div
              key={s.id}
              className={`seg ${i === idx ? "on" : ""} ${i < idx ? "done" : ""}`}
              style={{ flexGrow: s.seconds || 1 }}
              onClick={() => jump(i)}
              title={`shot ${i + 1}`}
            />
          ))}
        </div>

        <div className="animatic-bar">
          <div className="flex">
            <button className="btn btn-sm btn-ghost" onClick={() => jump(idx - 1)} disabled={idx === 0}>⏮</button>
            <button className="btn btn-sm btn-amber" onClick={() => setPlaying((p) => !p)}>
              {playing ? "⏸ pause" : "▶ play"}
            </button>
            <button className="btn btn-sm btn-ghost" onClick={() => jump(idx + 1)} disabled={idx === scenes.length - 1}>⏭</button>
            <button className="btn btn-sm btn-ghost" onClick={restart}>↺</button>
          </div>
          <span className="label">{total.toFixed(1)}s animatic</span>
          <div className="flex">
            {missingVoices && (
              <button className="btn btn-sm" onClick={onPrepareVoices} disabled={preparingVoices}>
                {preparingVoices ? <span className="spin-inline" /> : "🗣"} Prepare voices
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
