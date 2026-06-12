export interface Asset {
  id: string;
  type: string;
  size_label: string | null;
  path: string;
  fidelity_score: number | null;
  qc_status: string;
  selected: boolean;
  // 后端实时生成的可展示地址：OSS 预签名 URL（有时效）或本地 /files/…
  url: string | null;
  thumb_url: string | null;
}

export interface Task {
  id: string;
  status: string;
  current_stage: string | null;
  progress: number;
  description: string | null;
  error_message: string | null;
  source_image: string | null;
  assets: Asset[];
}

export interface TaskSummary {
  id: string;
  status: string;
  current_stage: string | null;
  progress: number;
  description: string | null;
  created_at: string;
  source_image: string | null;
}

const API = "/api/v1";
const TOKEN_KEY = "shotsmith_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

// 令牌失效（401）时回调，App 据此退回登录页
let onUnauthorized: (() => void) | null = null;
export const setOnUnauthorized = (cb: () => void) => {
  onUnauthorized = cb;
};

// 统一请求：自动带 Bearer 令牌；401 时清理令牌并通知 App
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers ?? {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    onUnauthorized?.();
    throw new Error("登录已过期，请重新输入密码");
  }
  return res;
}

export async function login(password: string): Promise<void> {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    throw new Error(res.status === 401 ? "密码错误" : await res.text());
  }
  const data = (await res.json()) as { token: string };
  setToken(data.token);
}

// 服务端签名直传：向后端要预签名 PUT 地址 → 浏览器直传 OSS → 返回 object key。
// 后端未启用 OSS（409）或直传失败时返回 null，回退为 multipart 经后端中转。
async function uploadDirect(file: File): Promise<string | null> {
  try {
    const res = await apiFetch(`${API}/uploads/presign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name || "paste.png",
        content_type: file.type || "image/png",
      }),
    });
    if (!res.ok) return null;
    const { key, url, headers } = (await res.json()) as {
      key: string;
      url: string;
      headers: Record<string, string>;
    };
    const up = await fetch(url, { method: "PUT", headers, body: file });
    return up.ok ? key : null;
  } catch {
    return null;
  }
}

export async function createTask(
  file: File | null,
  url: string,
  description: string,
  productUrl: string,
  textLang: string,
): Promise<Task> {
  const form = new FormData();
  if (file) {
    const key = await uploadDirect(file);
    if (key) form.append("source_key", key);
    else form.append("file", file);
  }
  if (url) form.append("url", url);
  if (description) form.append("description", description);
  form.append(
    "options",
    JSON.stringify({
      product_url: productUrl || undefined,
      // 图中文字语言：none=画面禁文字；其余按所选语言在图中融入贴合的文字
      text_lang: textLang,
    }),
  );
  const res = await apiFetch(`${API}/tasks`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listTasks(): Promise<TaskSummary[]> {
  const res = await apiFetch(`${API}/tasks?limit=50`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getTask(id: string): Promise<Task> {
  const res = await apiFetch(`${API}/tasks/${id}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function regenerate(id: string): Promise<Task> {
  const res = await apiFetch(`${API}/tasks/${id}/regenerate`, { method: "POST" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteTask(id: string): Promise<void> {
  const res = await apiFetch(`${API}/tasks/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function selectAsset(id: string, selected: boolean): Promise<void> {
  await apiFetch(`${API}/assets/${id}/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selected }),
  });
}

// 本地存储模式的兜底地址；OSS 模式下优先用后端返回的 url / thumb_url
export const fileUrl = (path: string) => `/files/${path}`;
// 下载走 <a href> 无法设请求头，令牌以查询参数携带（后端 require_auth 兼容 ?token=）
export const packageUrl = (id: string) =>
  `${API}/tasks/${id}/package?token=${encodeURIComponent(getToken() ?? "")}`;
