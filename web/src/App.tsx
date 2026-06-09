import { useCallback, useEffect, useRef, useState } from "react";
import Login from "./Login";
import {
  clearToken,
  createTask,
  deleteTask,
  fileUrl,
  getTask,
  getToken,
  listTasks,
  packageUrl,
  regenerate,
  selectAsset,
  setOnUnauthorized,
  type Asset,
  type Task,
  type TaskSummary,
} from "./api/client";

const DONE = ["success", "partial", "failed"];

const STATUS_LABEL: Record<string, string> = {
  pending: "排队中",
  processing: "处理中",
  success: "完成",
  partial: "部分完成",
  failed: "失败",
};
const statusLabel = (s: string) => STATUS_LABEL[s] ?? s;

const TYPE_LABEL: Record<string, string> = { white_bg: "白底主图", scene: "场景图" };
const typeLabel = (t: string) => TYPE_LABEL[t] ?? t;

function qcBadge(s: string): { cls: string; text: string } {
  if (s === "passed") return { cls: "badge-pass", text: "通过" };
  if (s === "needs_review") return { cls: "badge-review", text: "待复核" };
  return { cls: "badge-pending", text: "待校验" };
}

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
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
    // 令牌失效（任意请求 401）时退回登录页
    setOnUnauthorized(() => {
      setAuthed(false);
      setTask(null);
    });
  }, []);

  useEffect(() => {
    if (authed) refreshHistory();
  }, [authed, refreshHistory]);

  function logout() {
    clearToken();
    setAuthed(false);
    setTask(null);
  }

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );

  function onPickFile(f: File | null) {
    setFile(f);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return f ? URL.createObjectURL(f) : null;
    });
  }

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

  async function onDelete(id: string) {
    if (!window.confirm("确定删除这条历史记录？将同时删除生成的素材，且不可恢复。")) return;
    try {
      await deleteTask(id);
      if (task?.id === id) setTask(null);
      refreshHistory();
    } catch {
      /* 401 等已由 apiFetch 统一处理 */
    }
  }

  const assets = task?.assets.filter((a) => a.type !== "cutout") ?? [];

  if (!authed) return <Login onSuccess={() => setAuthed(true)} />;

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand-logo">S</div>
          <div>
            <div className="brand-title">ShotSmith</div>
            <div className="brand-sub">AI 电商商品素材图生成 · 抠图保真 · 一键多尺寸</div>
          </div>
          <button className="btn btn-sm topbar-logout" onClick={logout}>
            退出
          </button>
        </div>
      </header>

      <div className="container">
        {/* 创建任务 */}
        <section className="panel create">
          <div>
            <label className="field-label">商品图</label>
            <label className="dropzone">
              <input
                type="file"
                accept="image/*"
                onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
              />
              {preview ? (
                <img src={preview} alt="预览" />
              ) : (
                <div>
                  <div className="dz-icon">🖼️</div>
                  <div className="dz-main">点击上传商品图</div>
                  <div className="dz-sub">支持 JPG / PNG / WebP，建议主体清晰</div>
                </div>
              )}
            </label>
          </div>

          <div className="stack">
            <div>
              <label className="field-label">或粘贴图片 URL</label>
              <input
                className="input"
                placeholder="https://…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label">商品描述 / 场景（可选）</label>
              <input
                className="input"
                placeholder="如：户外冲锋衣，山野自然光场景"
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label">场景图引擎</label>
              <div className="segment">
                <button
                  className={engine === "local" ? "active" : ""}
                  onClick={() => setEngine("local")}
                >
                  纯色背景
                  <span className="seg-sub">离线 · 免费</span>
                </button>
                <button
                  className={engine === "aliyun_bg" ? "active" : ""}
                  onClick={() => setEngine("aliyun_bg")}
                >
                  在线万相 AI
                  <span className="seg-sub">更真实 · 调用阿里</span>
                </button>
              </div>
            </div>
            <button
              className="btn btn-primary"
              onClick={onSubmit}
              disabled={busy || (!file && !url)}
            >
              {busy ? "提交中…" : "开始生成"}
            </button>
          </div>
        </section>

        {/* 历史 + 结果 */}
        <div className="layout">
          <aside>
            <div className="side-head">
              <h3>历史记录</h3>
              <button className="btn btn-sm" onClick={refreshHistory}>
                刷新
              </button>
            </div>
            <ul className="history">
              {history.map((h) => (
                <li
                  key={h.id}
                  className={`history-item${task?.id === h.id ? " active" : ""}`}
                  onClick={() => openTask(h.id)}
                >
                  {h.source_image && (
                    <img className="history-thumb" src={h.source_image} alt="" />
                  )}
                  <div className="history-text">
                    <div className="history-title">{h.description || "（无描述）"}</div>
                    <div className="history-meta">
                      <span className={`pill pill-${h.status}`}>{statusLabel(h.status)}</span>
                      {new Date(h.created_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    className="history-del"
                    title="删除记录"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(h.id);
                    }}
                  >
                    🗑
                  </button>
                </li>
              ))}
              {history.length === 0 && <li className="empty">暂无记录</li>}
            </ul>
          </aside>

          <section className="panel main-card">
            {!task && (
              <div className="empty empty-lg">
                <div className="e-icon">✨</div>
                从左侧历史记录选择，或上传新图开始生成
              </div>
            )}
            {task && (
              <>
                {task.source_image && (
                  <div className="source-row">
                    <img className="source-thumb" src={task.source_image} alt="原图" />
                    <div className="source-cap">
                      原图<span>{task.description || "（无描述）"}</span>
                    </div>
                  </div>
                )}
                <div className="status-row">
                  <span className={`pill pill-${task.status}`}>{statusLabel(task.status)}</span>
                  {task.current_stage && <span className="status-stage">{task.current_stage}</span>}
                  <span className="status-stage">{task.progress}%</span>
                  {task.error_message && <span className="status-err">· {task.error_message}</span>}
                </div>
                <div className="progress">
                  <div className="progress-bar" style={{ width: `${task.progress}%` }} />
                </div>

                {DONE.includes(task.status) && (
                  <div className="toolbar">
                    <button className="btn" onClick={onRegenerate}>
                      重新生成
                    </button>
                    <a href={packageUrl(task.id)}>
                      <button className="btn btn-primary">下载素材包</button>
                    </a>
                  </div>
                )}

                {assets.length > 0 && (
                  <div className="grid">
                    {assets.map((a) => {
                      const b = qcBadge(a.qc_status);
                      return (
                        <figure
                          key={a.id}
                          className={`asset${a.selected ? " selected" : ""}`}
                          style={{ margin: 0 }}
                        >
                          <img className="asset-thumb" src={fileUrl(a.path)} alt={a.type} />
                          <figcaption className="asset-body">
                            <div className="asset-row">
                              <span className="asset-type">{typeLabel(a.type)}</span>
                              <span className="asset-size">{a.size_label}</span>
                            </div>
                            <div className="asset-row">
                              <span className="fidelity">
                                还原度 <b>{a.fidelity_score ?? "-"}</b>
                              </span>
                              <span className={`badge ${b.cls}`}>{b.text}</span>
                            </div>
                            <label className="select-row">
                              <input
                                type="checkbox"
                                checked={a.selected}
                                onChange={() => onToggle(a)}
                              />
                              选用
                            </label>
                          </figcaption>
                        </figure>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
