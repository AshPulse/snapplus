import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Lock, User } from "lucide-react";
import { adminLogin } from "../lib/api";

export default function AdminLogin() {
    const navigate = useNavigate();
    const [username, setUsername] = useState(localStorage.getItem("snap_admin_username") || "");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await adminLogin(username.trim().toLowerCase(), password);
            localStorage.setItem("snap_admin_token", res.token);
            localStorage.setItem("snap_admin_username", res.username);
            localStorage.setItem("snap_admin_role", res.role || "admin");
            toast.success(`Welcome, ${res.username}${res.role === "owner" ? " (owner)" : ""}`);
            navigate("/admin-secret-panel");
        } catch (err) {
            const status = err?.response?.status;
            const detail = err?.response?.data?.detail || "Login failed";
            toast.error(status === 429 ? detail : detail);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="admin-panel snap-aura" style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
            <form onSubmit={submit} style={{ width: "100%", maxWidth: 400, background: "#111", border: "1px solid #1f1f1f", borderRadius: 22, padding: "28px 24px" }} data-testid="admin-login-card">
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
                    <span style={{ background: "rgba(250,204,21,0.14)", padding: 10, borderRadius: 12, display: "flex" }}>
                        <Lock size={18} color="#FACC15" />
                    </span>
                    <div>
                        <div style={{ fontSize: 12, color: "#FACC15", letterSpacing: 2, fontWeight: 700 }}>SNAP+ ADMIN</div>
                        <div style={{ fontSize: 20, fontWeight: 700 }}>Sign in</div>
                    </div>
                </div>

                <label className="snap-label" style={{ color: "#9a9a9a" }}>Username <span style={{ color: "#6a6a6a" }}>(chosen once per IP)</span></label>
                <div style={{ display: "flex", alignItems: "center", background: "#0f0f0f", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 18, overflow: "hidden", marginBottom: 12 }}>
                    <div style={{ padding: "16px 14px", display: "flex" }}><User size={16} color="#FACC15" /></div>
                    <input className="snap-input" style={{ border: "none", background: "transparent" }} value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Your admin handle" maxLength={30} data-testid="admin-username-input" />
                </div>

                <label className="snap-label" style={{ color: "#9a9a9a" }}>Password</label>
                <input className="snap-input" type="password" placeholder="Admin password" value={password} onChange={(e) => setPassword(e.target.value)} data-testid="admin-password-input" />

                <p style={{ color: "#6a6a6a", fontSize: 12, margin: "10px 0 0" }}>
                    5 wrong attempts = 30 min lockout · your username is locked to this IP forever
                </p>
                <div style={{ height: 16 }} />
                <button className="snap-btn" disabled={loading || !password || !username.trim()} data-testid="admin-login-btn">
                    {loading ? "..." : "Enter panel"}
                </button>
            </form>
        </div>
    );
}
