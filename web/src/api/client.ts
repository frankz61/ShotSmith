export interface Asset {
  id: string;
  type: string;
  size_label: string | null;
  path: string;
  fidelity_score: number | null;
  qc_status: string;
  selected: boolean;
}

export interface Task {
  id: string;
  status: string;
  current_stage: string | null;
  progress: number;
  description: string | null;
  error_message: string | null;
  assets: Asset[];
}

export interface TaskSummary {
  id: string;
  status: string;
  current_stage: string | null;
  progress: number;
  description: string | null;
  created_at: string;
}

const API = "/api/v1";

export async function createTask(
  file: File | null,
  url: string,
  description: string,
  sceneEngine: string,
): Promise<Task> {
  const form = new FormData();
  if (file) form.append("file", file);
  if (url) form.append("url", url);
  if (description) form.append("description", description);
  form.append("options", JSON.stringify({ scene_engine: sceneEngine }));
  const res = await fetch(`${API}/tasks`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listTasks(): Promise<TaskSummary[]> {
  const res = await fetch(`${API}/tasks?limit=50`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTask(id: string): Promise<Task> {
  const res = await fetch(`${API}/tasks/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function regenerate(id: string): Promise<Task> {
  const res = await fetch(`${API}/tasks/${id}/regenerate`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function selectAsset(id: string, selected: boolean): Promise<void> {
  await fetch(`${API}/assets/${id}/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected }),
  });
}

export const fileUrl = (path: string) => `/files/${path}`;
export const packageUrl = (id: string) => `${API}/tasks/${id}/package`;
