import { useState } from "react";
import type { Presets, Scene } from "../types";

interface Props {
  presets: Presets | null;
  onUseScene: (scene: Partial<Scene>) => void;
  flash: (msg: string, err?: boolean) => void;
}

type Tab = "characters" | "scenes" | "voices" | "dialogues";

export function PresetsSidebar({ presets, onUseScene, flash }: Props) {
  const [tab, setTab] = useState<Tab>("scenes");
  if (!presets) return <div className="muted label">loading presets…</div>;

  const tabs: Tab[] = ["scenes", "characters", "voices", "dialogues"];

  return (
    <div>
      <div className="col-head"><span className="h">Presets</span></div>
      <div className="flex" style={{ flexWrap: "wrap", marginBottom: 14 }}>
        {tabs.map((t) => (
          <button key={t} className={`pill ${tab === t ? "teal" : ""}`} style={{ cursor: "pointer" }} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "scenes" && presets.scenes.map((s) => (
        <div key={s.id} className="preset-item" onClick={() => { onUseScene({ type: "image", prompt: s.description, image_prompt: s.setting_prompt || s.description, seconds: 3 }); flash(`Added scene: ${s.name}`); }}>
          {s.image && <img src={s.image} alt="" />}
          <div className="n">{s.name}</div>
          <div className="meta">{s.mood}</div>
        </div>
      ))}

      {tab === "characters" && presets.characters.map((c) => (
        <div key={c.id || c.name} className="preset-item" onClick={() => { onUseScene({ type: "image", prompt: `${c.name}: ${c.description}`, image_prompt: c.look_prompt || c.description, seconds: 3 }); flash(`Added ${c.name}`); }}>
          {c.image && <img src={c.image} alt="" />}
          <div className="n">{c.name}</div>
          <div className="meta">{c.voice}</div>
        </div>
      ))}

      {tab === "voices" && presets.voices.map((v) => (
        <div key={v.id} className="preset-item" onClick={() => { if (v.sample) new Audio(v.sample).play(); }}>
          <div className="n">{v.name} {v.sample && <span className="pill teal">▶</span>}</div>
          <div className="meta">{v.tags}</div>
        </div>
      ))}

      {tab === "dialogues" && presets.dialogues.map((d) => (
        <div key={d.id} className="preset-item" onClick={() => { onUseScene({ type: "text", prompt: "characters speak", seconds: 3, dialogue: [{ speaker: d.speaker || "", text: d.text, voice: d.voice || "neutral, clear" }] }); flash("Added dialogue shot"); }}>
          <div className="n">{d.name}</div>
          <div className="meta">"{d.text}"</div>
        </div>
      ))}
    </div>
  );
}
