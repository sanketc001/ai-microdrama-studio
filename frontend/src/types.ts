export type SceneType = "text" | "image";

export interface DialogueLine {
  speaker?: string;
  text: string;
  voice?: string;
  language?: string;
}

export interface Scene {
  id: string;
  type: SceneType;
  prompt: string;
  seconds: number;
  image_prompt?: string;
  image?: string | null;
  image_url?: string | null;
  audio?: string | null;
  audio_url?: string | null;
  guide_strength?: number;
  dialogue: DialogueLine[];
  character_ids?: string[];
  script?: string;
  sfx?: string | null;
  sfx_url?: string | null;
}

export interface StoryBeat { summary: string; scene: string; }
export interface StoryChoice { label: string; consequence: string; }
export interface Character {
  id?: string;
  name: string;
  description: string;
  voice?: string;
  look_prompt?: string;
  sample_text?: string;
  image?: string;
  image_url?: string | null;
  voice_sample?: string;
  voice_url?: string | null;
}

export interface Story {
  title?: string;
  logline?: string;
  characters?: Character[];
  beats?: StoryBeat[];
  choices?: StoryChoice[];
}

export interface Session {
  id: string;
  title: string;
  premise: string;
  global_prompt: string;
  story: Story;
  scenes: Scene[];
  frame_rate: number;
  music?: string | null;
  music_url?: string | null;
  video?: string | null;
  video_url?: string | null;
  parent_id?: string | null;
  updated?: number;
  story_error?: string;
}

export interface SessionSummary {
  id: string; title: string; premise: string; video?: string | null; updated?: number;
  parent_id?: string | null;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: { stage?: string; pct?: number; value?: number; max?: number; node?: string };
  preview?: string | null;
  logs: string[];
  result: any;
  error: string | null;
}

export interface JobSummary {
  id: string;
  kind: string;
  status: Job["status"];
  progress: Job["progress"];
  preview?: string | null;
  meta: { session?: string; [k: string]: unknown };
  created: number;
  log?: string;
  error?: boolean;
}

export interface GalleryItem { name: string; url: string | null; mtime: number; is_current: boolean; }
export interface SceneGallery { id: string; prompt: string; current_image_url: string | null; stills: GalleryItem[]; }
export interface Gallery { renders: GalleryItem[]; scenes: SceneGallery[]; }

export interface Presets {
  characters: Character[];
  scenes: { id: string; name: string; description: string; setting_prompt?: string; mood?: string; image?: string }[];
  voices: { id: string; name: string; tags: string; sample_text?: string; sample?: string }[];
  dialogues: { id: string; name: string; speaker?: string; text: string; voice?: string }[];
  storylines: { id: string; title: string; logline: string; premise: string }[];
}
