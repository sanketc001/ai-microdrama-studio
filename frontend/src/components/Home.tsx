import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { api } from "../api";
import type { Presets, SessionSummary } from "../types";

export function Home() {
  const nav = useNavigate();
  const [premise, setPremise] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [presets, setPresets] = useState<Presets | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.listSessions().then(setSessions).catch(() => {});
    api.presets().then(setPresets).catch(() => {});
  }, []);

  async function create() {
    if (!premise.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const s = await api.createSession({ premise: premise.trim() });
      nav(`/studio/${s.id}`);
    } catch (e: any) {
      setErr(String(e.message || e));
      setBusy(false);
    }
  }

  return (
    <div className="wrap">
      <motion.div
        className="hero"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      >
        <div>
          <h1>
            DIRECT A<span className="accent">MICRODRAMA</span>
          </h1>
          <p className="muted" style={{ marginTop: 18 }}>
            Plan a timeline of scenes — stills, dialogue, custom voices — guided by
            your AI director. Then render the whole thing in a single cut.
          </p>
        </div>
        <div className="new-drama panel">
          <h3>New production</h3>
          <textarea
            className="serif"
            rows={4}
            placeholder="A premise… e.g. 'A lighthouse keeper finds a message in a bottle that knows her name.'"
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
          />
          <div className="row">
            <button className="btn btn-amber" onClick={create} disabled={busy}>
              {busy ? <span className="spin-inline" /> : "◆"} Direct it
            </button>
          </div>
          {err && <p className="pill red" style={{ marginTop: 12 }}>{err}</p>}
        </div>
      </motion.div>

      {presets?.storylines?.length ? (
        <>
          <div className="section-title">
            <span className="label">Or start from a storyline</span>
            <span className="line" />
          </div>
          <div className="session-grid">
            {presets.storylines.map((s) => (
              <motion.div
                key={s.id}
                className="storyline-chip panel"
                whileHover={{ scale: 1.01 }}
                onClick={() => setPremise(s.premise || s.logline)}
              >
                <div className="t">{s.title}</div>
                <div className="l">{s.logline}</div>
              </motion.div>
            ))}
          </div>
        </>
      ) : null}

      <div className="section-title">
        <span className="label">Your reel</span>
        <span className="line" />
      </div>
      {sessions.length === 0 ? (
        <div className="empty">
          <div className="big">No takes yet</div>
          <p className="muted">Your productions will appear here.</p>
        </div>
      ) : (
        <div className="session-grid">
          {sessions.map((s, i) => (
            <motion.div
              key={s.id}
              className="session-card panel"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              onClick={() => nav(`/studio/${s.id}`)}
            >
              <div className="num">TAKE {String(i + 1).padStart(2, "0")}</div>
              <h4>{s.title || "Untitled"}</h4>
              <div className="premise">{s.premise}</div>
              <div className="flex" style={{ marginTop: 10 }}>
                {s.video ? <span className="pill amber">● rendered</span> : null}
                {s.parent_id ? <span className="pill teal">⎘ branch</span> : null}
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
