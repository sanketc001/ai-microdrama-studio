import { useEffect, useState } from "react";
import { api, pollJob } from "../api";
import type { Character } from "../types";

const VOICE_HINT = "e.g. female, young adult, british accent  ·  male, elderly, low pitch";

export function CharacterStudio({ onClose, onChanged }: { onClose: () => void; onChanged?: () => void }) {
  const [chars, setChars] = useState<Character[]>([]);
  const [busy, setBusy] = useState<Record<string, "image" | "voice" | null>>({});
  const [prog, setProg] = useState<Record<string, number>>({});
  const [form, setForm] = useState({ name: "", description: "", look_prompt: "", voice: "", sample_text: "" });
  const [err, setErr] = useState<string | null>(null);
  const [rolling, setRolling] = useState(false);

  const load = () => api.listCharacters().then(setChars).catch((e) => setErr(String(e.message)));
  useEffect(() => { load(); }, []);

  async function roll() {
    setRolling(true);
    setErr(null);
    try {
      const f = await api.randomCharacter();
      setForm({
        name: f.name || "", description: f.description || "", look_prompt: f.look_prompt || "",
        voice: f.voice || "", sample_text: f.sample_text || "",
      });
    } catch (e: any) { setErr(String(e.message || e)); }
    finally { setRolling(false); }
  }

  async function create() {
    if (!form.name.trim()) return;
    try {
      await api.createCharacter({ ...form, look_prompt: form.look_prompt || form.description });
      setForm({ name: "", description: "", look_prompt: "", voice: "", sample_text: "" });
      await load();
      onChanged?.();
    } catch (e: any) { setErr(String(e.message || e)); }
  }

  async function gen(id: string, kind: "image" | "voice") {
    setBusy((b) => ({ ...b, [id]: kind }));
    setProg((p) => ({ ...p, [id]: 0 }));
    try {
      const job = kind === "image" ? await api.genCharacterImage(id) : await api.genCharacterVoice(id);
      await pollJob(job.id, (j) => setProg((p) => ({ ...p, [id]: j.progress?.pct ?? 0 })));
      await load();
      onChanged?.();
    } catch (e: any) { setErr(String(e.message || e)); }
    finally { setBusy((b) => ({ ...b, [id]: null })); }
  }

  async function uploadFor(id: string, kind: "image" | "voice", file: File) {
    setBusy((b) => ({ ...b, [id]: kind }));
    try {
      if (kind === "image") await api.uploadCharacterImage(id, file);
      else await api.uploadCharacterVoice(id, file);
      await load();
      onChanged?.();
    } catch (e: any) { setErr(String(e.message || e)); }
    finally { setBusy((b) => ({ ...b, [id]: null })); }
  }

  async function del(id: string) {
    await api.deleteCharacter(id);
    await load();
    onChanged?.();
  }

  return (
    <div className="stage-overlay" onClick={onClose}>
      <div className="panel char-studio" onClick={(e) => e.stopPropagation()}>
        <div className="row-between" style={{ marginBottom: 16 }}>
          <span className="display" style={{ fontSize: 30 }}>Casting</span>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>✕ close</button>
        </div>
        {err && <div className="pill red" style={{ marginBottom: 12 }}>{err}</div>}

        <div className="char-new panel">
          <div className="row-between" style={{ marginBottom: 8 }}>
            <span className="label">New character</span>
            <button className="btn btn-sm" onClick={roll} disabled={rolling} title="Let the director invent one">
              {rolling ? <span className="spin-inline" /> : "🎲"} Random
            </button>
          </div>
          <div className="char-form">
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input placeholder="Voice tags — " value={form.voice} onChange={(e) => setForm({ ...form, voice: e.target.value })} title={VOICE_HINT} />
            <textarea rows={2} placeholder="Description / personality" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <textarea rows={2} placeholder="Look prompt (for the portrait) — defaults to description" value={form.look_prompt} onChange={(e) => setForm({ ...form, look_prompt: e.target.value })} />
            <button className="btn btn-amber" onClick={create}>＋ Add to cast</button>
          </div>
        </div>

        <div className="char-grid">
          {chars.map((c) => (
            <div key={c.id} className="char-card panel">
              <div className="char-portrait">
                {c.image_url ? <img src={c.image_url} alt={c.name} /> : <div className="char-ph">no portrait</div>}
                {busy[c.id!] === "image" && <div className="char-overlay"><span className="spin-inline" /> {prog[c.id!] ?? 0}%</div>}
              </div>
              <div className="char-meta stack">
                <input className="char-name" defaultValue={c.name} onBlur={(e) => e.target.value !== c.name && api.updateCharacter(c.id!, { name: e.target.value }).then(load)} />
                <input style={{ fontSize: 11 }} defaultValue={c.voice} placeholder="voice tags" onBlur={(e) => e.target.value !== c.voice && api.updateCharacter(c.id!, { voice: e.target.value }).then(load)} title={VOICE_HINT} />
                <textarea rows={2} style={{ fontSize: 11.5 }} defaultValue={c.look_prompt || c.description} onBlur={(e) => api.updateCharacter(c.id!, { look_prompt: e.target.value }).then(load)} />
                <div className="flex" style={{ flexWrap: "wrap" }}>
                  <button className="btn btn-sm" disabled={!!busy[c.id!]} onClick={() => gen(c.id!, "image")}>
                    {busy[c.id!] === "image" ? <span className="spin-inline" /> : "↻"} {c.image_url ? "reroll image" : "image"}
                  </button>
                  <label className="btn btn-sm btn-ghost" title="Upload portrait">
                    ⤒<input type="file" accept="image/*" hidden onChange={(e) => {
                      const f = e.target.files?.[0]; if (f) uploadFor(c.id!, "image", f);
                      (e.target as HTMLInputElement).value = "";
                    }} />
                  </label>
                  <button className="btn btn-sm" disabled={!!busy[c.id!]} onClick={() => gen(c.id!, "voice")}>
                    {busy[c.id!] === "voice" ? <span className="spin-inline" /> : "↻"} {c.voice_url ? "reroll voice" : "voice"}
                  </button>
                  <label className="btn btn-sm btn-ghost" title="Upload voice clip (used to clone the voice)">
                    ⤒<input type="file" accept="audio/*" hidden onChange={(e) => {
                      const f = e.target.files?.[0]; if (f) uploadFor(c.id!, "voice", f);
                      (e.target as HTMLInputElement).value = "";
                    }} />
                  </label>
                  {c.voice_url && <button className="btn btn-sm btn-ghost" onClick={() => new Audio(c.voice_url!).play()}>▶</button>}
                  <button className="btn btn-sm btn-ghost" onClick={() => del(c.id!)}>🗑</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
