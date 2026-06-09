import { useState } from "react";
import { login } from "./api/client";

/** 密码门：输入访问密码 → 换取后端令牌 → 通知 App 进入主界面。 */
export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!password || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await login(password);
      onSuccess();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card panel">
        <div className="brand-logo login-logo">S</div>
        <div className="login-title">ShotSmith</div>
        <div className="login-sub">请输入访问密码以继续</div>
        <input
          className="input"
          type="password"
          placeholder="访问密码"
          value={password}
          autoFocus
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        {err && <div className="login-err">{err}</div>}
        <button
          className="btn btn-primary login-btn"
          onClick={submit}
          disabled={busy || !password}
        >
          {busy ? "验证中…" : "进入"}
        </button>
      </div>
    </div>
  );
}
