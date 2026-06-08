import { useCallback, useEffect, useRef, useState } from "react";
import {
  createTask,
  fileUrl,
  getTask,
  listTasks,
  packageUrl,
  regenerate,
  selectAsset,
  type Asset,
  type Task,
  type TaskSummary,
} from "./api/client";

const DONE = ["success", "partial", "failed"];

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    pending: "排队中",
    processing: "处理中",
    success: "完成",
    partial: "部分完成",
    failed: "失败",
  };
  return m[s] ?? s;
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [desc, setDesc] = useState("");
  const [url, setUrl] = useState("");
  const [engine, setEngine] = useState("local"); // 场景图引擎：local 纯色 / aliyun_bg 在线万相
  const [task, setTask] = useState<Task | null>(null);
  const [history, setHistory] = useState<TaskSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const timer = useRef<number | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listTasks());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
    },
    [],
  );

  function poll(id: string) {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = window.setInterval(async () => {
      const t = await getTask(id);
      setTask(t);
      if (DONE.includes(t.status)) {
        if (timer.current) {
          window.clearInterval(timer.current);
          timer.current = null;
        }
        refreshHistory();
      }
    }, 1500);
  }

  async function onSubmit() {
    if (!file && !url) return;
    setBusy(true);
    try {
      const t = await createTask(file, url, desc, engine);
      setTask(t);
      poll(t.id);
      refreshHistory();
    } finally {
      setBusy(false);
    }
  }

  async function openTask(id: string) {
    const t = await getTask(id);
    setTask(t);
    if (!DONE.includes(t.status)) poll(id);
  }

  async function onRegenerate() {
    if (!task) return;
    const t = await regenerate(task.id);
    setTask(t);
    poll(t.id);
  }

  async function onToggle(a: Asset) {
    await selectAsset(a.id, !a.selected);
    if (task) setTask(await getTask(task.id));
  }

  const assets = task?.assets.filter((a) => a.type !== "cutout") ?? [];

  return (
    <main style={{ maxWidth: 1100, margin: "24px auto", fontFamily: "system-ui", padding: 16 }}>
      <h1>ShotSmith</h1>
      <p style={{ color: "#666" }}>上传商品图 + 可选描述，自动生成白底图与场景图。</p>

      <section style={{ display: "grid", gap: 8, marginBottom: 20 }}>
        <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input placeholder="或粘贴图片 URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        <input
          placeholder="商品描述/场景（可选）"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        <label style={{ fontSize: 13, color: "#555", display: "flex", alignItems: "center", gap: 8 }}>
          场景图引擎：
          <select value={engine} onChange={(e) => setEngine(e.target.value)} style={{ padding: 4 }}>
            <option value="local">纯色背景（离线 · 免费）</option>
            <option value="aliyun_bg">在线万相 AI（更真实 · 调用阿里）</option>
          </select>
        </label>
        <button onClick={onSubmit} disabled={busy || (!file && !url)}>
          {busy ? "提交中…" : "开始生成"}
        </button>
      </section>

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        <aside style={{ width: 260, flexShrink: 0 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <h3 style={{ margin: "0 0 8px" }}>历史记录</h3>
            <button onClick={refreshHistory} style={{ fontSize: 12 }}>
              刷新
            </button>
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
            {history.map((h) => (
              <li
                key={h.id}
                onClick={() => openTask(h.id)}
                style={{
                  border: "1px solid #eee",
                  borderRadius: 8,
                  padding: 8,
                  cursor: "pointer",
                  background: task?.id === h.id ? "#eef4ff" : "#fff",
                }}
              >
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {h.description || "（无描述）"}
                </div>
                <div style={{ fontSize: 11, color: "#888" }}>
                  {statusLabel(h.status)} · {new Date(h.created_at).toLocaleString()}
                </div>
              </li>
            ))}
            {history.length === 0 && (
              <li style={{ color: "#999", fontSize: 13 }}>暂无记录</li>
            )}
          </ul>
        </aside>

        <section style={{ flex: 1 }}>
          {!task && <p style={{ color: "#999" }}>从左侧历史记录选择，或上传新图开始。</p>}
          {task && (
            <>
              <p>
                状态：<b>{statusLabel(task.status)}</b>
                {task.current_stage && ` · ${task.current_stage}`} · {task.progress}%
                {task.error_message && (
                  <span style={{ color: "crimson" }}> · {task.error_message}</span>
                )}
              </p>
              <div style={{ height: 6, background: "#eee", borderRadius: 3 }}>
                <div
                  style={{
                    width: `${task.progress}%`,
                    height: 6,
                    background: "#4f8cff",
                    borderRadius: 3,
                  }}
                />
              </div>

              {DONE.includes(task.status) && (
                <div style={{ margin: "12px 0", display: "flex", gap: 8 }}>
                  <button onClick={onRegenerate}>重新生成</button>
                  <a href={packageUrl(task.id)}>
                    <button>下载素材包</button>
                  </a>
                </div>
              )}

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill,minmax(180px,1fr))",
                  gap: 12,
                }}
              >
                {assets.map((a) => (
                  <figure
                    key={a.id}
                    style={{ margin: 0, border: "1px solid #eee", borderRadius: 8, padding: 8 }}
                  >
                    <img
                      src={fileUrl(a.path)}
                      alt={a.type}
                      style={{ width: "100%", borderRadius: 4 }}
                    />
                    <figcaption style={{ fontSize: 12, color: "#555", marginTop: 6 }}>
                      {a.type} · {a.size_label}
                      <br />
                      还原度 {a.fidelity_score ?? "-"} ·{" "}
                      <span style={{ color: a.qc_status === "passed" ? "green" : "orange" }}>
                        {a.qc_status}
                      </span>
                      <br />
                      <label>
                        <input
                          type="checkbox"
                          checked={a.selected}
                          onChange={() => onToggle(a)}
                        />{" "}
                        选用
                      </label>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
