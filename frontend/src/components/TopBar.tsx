import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { RendersMonitor } from "./RendersMonitor";

export function TopBar() {
  const [health, setHealth] = useState<{ comfyui: boolean; llm: string } | null>(null);

  useEffect(() => {
    const ping = () => api.health().then(setHealth).catch(() => setHealth(null));
    ping();
    const t = setInterval(ping, 8000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="topbar">
      <Link to="/" className="wordmark">
        <span className="mark">MICRO<b>DRAMA</b></span>
        <span className="sub">director's console</span>
      </Link>
      <div className="status-dots">
        <RendersMonitor />
        <span className="status">
          <i className={`dot ${health?.comfyui ? "on" : "off"}`} /> ComfyUI
        </span>
        <span className="status">
          <i className={`dot ${health ? "on" : "off"}`} /> {health?.llm ?? "director"}
        </span>
      </div>
    </header>
  );
}
