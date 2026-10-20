import { useState } from "react";

export function CopyBox({ text, label = "scene script" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard may be blocked; selection still works */
    }
  }
  return (
    <div className="copybox">
      <div className="copybox-head">
        <span className="label">{label}</span>
        <button className="btn btn-sm" onClick={copy}>{copied ? "✓ copied" : "⧉ copy"}</button>
      </div>
      <textarea className="copybox-text" readOnly value={text} rows={Math.min(18, Math.max(6, Math.ceil(text.length / 64)))} onFocus={(e) => e.target.select()} />
    </div>
  );
}
