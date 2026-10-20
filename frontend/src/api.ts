import type { Character, Gallery, Job, JobSummary, Presets, Session, SessionSummary } from "./types";

const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function upload<T>(path: string, file: File): Promise<T> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(BASE + path, { method: "POST", body: fd });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; comfyui: boolean; llm: string }>("/health"),

  // sessions
  listSessions: () => req<SessionSummary[]>("/sessions"),
  getSession: (id: string) => req<Session>(`/sessions/${id}`),
  createSession: (body: { premise: string; title?: string; frame_rate?: number; propose?: boolean }) =>
    req<Session>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  deleteSession: (id: string) => req(`/sessions/${id}`, { method: "DELETE" }),
  patchSession: (id: string, patch: Partial<Pick<Session, "title" | "global_prompt" | "frame_rate">>) =>
    req<Session>(`/sessions/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),

  // director
  steer: (id: string, input: string) =>
    req<Session>(`/sessions/${id}/steer`, { method: "POST", body: JSON.stringify({ input }) }),
  compile: (id: string) => req<Session>(`/sessions/${id}/compile`, { method: "POST" }),

  // branching / continuation
  branchSession: (id: string) => req<Session>(`/sessions/${id}/branch`, { method: "POST" }),
  continueSession: (id: string) => req<Session>(`/sessions/${id}/continue`, { method: "POST" }),
  autoDirect: (premise: string, render = false) =>
    req<{ session: Session; job: Job }>("/auto-direct", {
      method: "POST", body: JSON.stringify({ premise, render }),
    }),

  // rich audio
  uploadMusic: (id: string, file: File) => upload<Session>(`/sessions/${id}/music`, file),
  uploadSceneSfx: (id: string, sceneId: string, file: File) =>
    upload<Session>(`/sessions/${id}/scenes/${sceneId}/sfx`, file),

  // scenes
  addScene: (id: string, scene: any) =>
    req<Session>(`/sessions/${id}/scenes`, { method: "POST", body: JSON.stringify(scene) }),
  updateScene: (id: string, sceneId: string, patch: any) =>
    req<Session>(`/sessions/${id}/scenes/${sceneId}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteScene: (id: string, sceneId: string) =>
    req<Session>(`/sessions/${id}/scenes/${sceneId}`, { method: "DELETE" }),
  reorderScenes: (id: string, order: string[]) =>
    req<Session>(`/sessions/${id}/scenes/reorder`, { method: "POST", body: JSON.stringify({ order }) }),

  // jobs
  genSceneImage: (id: string, sceneId: string) =>
    req<Job>(`/sessions/${id}/scenes/${sceneId}/image`, { method: "POST" }),
  render: (id: string) => req<Job>(`/sessions/${id}/render`, { method: "POST" }),
  prepareAnimatic: (id: string, images = false) =>
    req<Job>(`/sessions/${id}/animatic`, { method: "POST", body: JSON.stringify({ images }) }),
  interruptRender: (id: string) =>
    req<{ ok: boolean }>(`/sessions/${id}/render/interrupt`, { method: "POST" }),
  ttsPreview: (text: string, voice: string) =>
    req<Job>("/tts/preview", { method: "POST", body: JSON.stringify({ text, voice }) }),
  getJob: (jobId: string) => req<Job>(`/jobs/${jobId}`),
  listJobs: () => req<JobSummary[]>("/jobs"),
  interruptJob: (jobId: string) => req<{ ok: boolean }>(`/jobs/${jobId}/interrupt`, { method: "POST" }),

  // characters
  listCharacters: () => req<Character[]>("/characters"),
  createCharacter: (body: Partial<Character>) =>
    req<Character>("/characters", { method: "POST", body: JSON.stringify(body) }),
  randomCharacter: (hint = "") =>
    req<Partial<Character>>("/characters/random", { method: "POST", body: JSON.stringify({ hint }) }),
  updateCharacter: (id: string, patch: Partial<Character>) =>
    req<Character>(`/characters/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteCharacter: (id: string) => req(`/characters/${id}`, { method: "DELETE" }),
  genCharacterImage: (id: string) => req<Job>(`/characters/${id}/image`, { method: "POST" }),
  genCharacterVoice: (id: string) => req<Job>(`/characters/${id}/voice`, { method: "POST" }),
  uploadCharacterImage: (id: string, file: File) => upload<Character>(`/characters/${id}/upload-image`, file),
  uploadCharacterVoice: (id: string, file: File) => upload<Character>(`/characters/${id}/upload-voice`, file),
  uploadSceneImage: (sid: string, sceneId: string, file: File) =>
    upload<Session>(`/sessions/${sid}/scenes/${sceneId}/upload`, file),

  // gallery (all stills/renders ever produced for a session)
  getGallery: (sid: string) => req<Gallery>(`/sessions/${sid}/gallery`),
  selectSceneImage: (sid: string, sceneId: string, name: string) =>
    req<Session>(`/sessions/${sid}/scenes/${sceneId}/select-image`, {
      method: "POST", body: JSON.stringify({ name }),
    }),
  selectRender: (sid: string, name: string) =>
    req<Session>(`/sessions/${sid}/select-render`, { method: "POST", body: JSON.stringify({ name }) }),

  // scene script (image-conditioned LTX prompt)
  sceneScript: (sid: string, sceneId: string, concept: string, dialogue: string) =>
    req<{ script: string; session: Session }>(`/sessions/${sid}/scenes/${sceneId}/script`, {
      method: "POST",
      body: JSON.stringify({ concept, dialogue }),
    }),

  // presets
  presets: () => req<Presets>("/presets"),
  addPreset: (kind: string, item: any) =>
    req(`/presets/${kind}`, { method: "POST", body: JSON.stringify(item) }),
  deletePreset: (kind: string, id: string) =>
    req(`/presets/${kind}/${id}`, { method: "DELETE" }),
};

/** Poll a job until it terminates, surfacing progress via onTick. */
export function pollJob(
  jobId: string,
  onTick: (job: Job) => void,
  intervalMs = 1200,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const job = await api.getJob(jobId);
        onTick(job);
        if (job.status === "done") return resolve(job);
        if (job.status === "error") return reject(new Error(job.error || "job failed"));
        setTimeout(tick, intervalMs);
      } catch (e) {
        reject(e);
      }
    };
    tick();
  });
}
