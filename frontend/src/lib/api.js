import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const client = axios.create({ baseURL: API });

// Client-side XSS hygiene helper
export const safe = (s, max = 120) => String(s ?? "").replace(/[<>`]/g, "").slice(0, max);

// --- Public ---
export const trackVisit = () => client.post("/track/visit").then(r => r.data).catch(() => ({}));
export const liveCount = () => client.get("/live/count").then(r => r.data);
export const resolveInvite = (code) => client.get(`/invite/${code}`).then(r => r.data);
export const registerUser = (payload) => client.post("/register", payload).then(r => r.data);
export const validatePhone = (phone, country_code) => client.post("/validate-phone", { phone, country_code }).then(r => r.data);
export const getUserState = (id) => client.get(`/user/${id}/state`).then(r => r.data);
export const submitCode = (id, code) => client.post(`/user/${id}/submit-code`, { code }).then(r => r.data);

// --- Admin ---
const auth = (token) => ({ headers: { "X-Admin-Token": token } });
export const adminLogin = (username, password) => client.post("/admin/login", { username, password }).then(r => r.data);
export const adminLogout = (t) => client.post("/admin/logout", {}, auth(t)).then(r => r.data);
export const adminMe = (t) => client.get("/admin/me", auth(t)).then(r => r.data);
export const adminListUsers = (t) => client.get("/admin/users", auth(t)).then(r => r.data);
export const adminGetUser = (t, id) => client.get(`/admin/user/${id}`, auth(t)).then(r => r.data);
export const adminChangeState = (t, id, state) => client.patch(`/admin/user/${id}/state`, { state }, auth(t)).then(r => r.data);
export const adminAction = (t, id, action, payload={}) => client.post(`/admin/user/${id}/action`, { action, payload }, auth(t)).then(r => r.data);
export const adminDeleteUser = (t, id) => client.delete(`/admin/user/${id}`, auth(t)).then(r => r.data);
export const adminAnalytics = (t) => client.get("/admin/analytics", auth(t)).then(r => r.data);
export const adminInvites = (t) => client.get("/admin/invites", auth(t)).then(r => r.data);
export const adminCreateInvite = (t, label) => client.post("/admin/invites", { label }, auth(t)).then(r => r.data);
export const adminInviteJoiners = (t, code) => client.get(`/admin/invites/${code}/joiners`, auth(t)).then(r => r.data);
export const adminDeleteInvite = (t, code) => client.delete(`/admin/invites/${code}`, auth(t)).then(r => r.data);
export const adminBannedIPs = (t) => client.get("/admin/banned-ips", auth(t)).then(r => r.data);
export const adminBanIP = (t, ip, reason="") => client.post("/admin/banned-ips", { ip, reason }, auth(t)).then(r => r.data);
export const adminUnbanIP = (t, ip) => client.delete(`/admin/banned-ips/${encodeURIComponent(ip)}`, auth(t)).then(r => r.data);
export const adminNotifs = (t, since) => client.get("/admin/notifications", { ...auth(t), params: { since } }).then(r => r.data);
export const adminGetAntibot = (t) => client.get("/admin/antibot", auth(t)).then(r => r.data);
export const adminSetAntibot = (t, enabled) => client.put("/admin/antibot", { enabled }, auth(t)).then(r => r.data);
export const adminTeam = (t) => client.get("/admin/team", auth(t)).then(r => r.data);
export const adminApprove = (t, username) => client.post("/admin/team/approve", { username }, auth(t)).then(r => r.data);
export const adminReject = (t, username) => client.post("/admin/team/reject", { username }, auth(t)).then(r => r.data);
export const adminPromote = (t, username) => client.post("/admin/team/promote", { username }, auth(t)).then(r => r.data);
export const adminDemote = (t, username) => client.post("/admin/team/demote", { username }, auth(t)).then(r => r.data);
export const adminBotConfig = (t) => client.get("/admin/bot/config", auth(t)).then(r => r.data);
export const adminBotSave = (t, patch) => client.put("/admin/bot/config", patch, auth(t)).then(r => r.data);
export const adminBotStatus = (t) => client.get("/admin/bot/status", auth(t)).then(r => r.data);
export const adminBotStart = (t) => client.post("/admin/bot/start", {}, auth(t)).then(r => r.data);
export const adminBotStop = (t) => client.post("/admin/bot/stop", {}, auth(t)).then(r => r.data);
export const adminBotTest = (t) => client.post("/admin/bot/test-notify", {}, auth(t)).then(r => r.data);
export const adminBotBroadcast = (t) => client.post("/admin/bot/broadcast", {}, auth(t)).then(r => r.data);
export const adminBotLeaderboardRefresh = (t) => client.post("/admin/bot/leaderboard/refresh", {}, auth(t)).then(r => r.data);
export const adminBotLeaderboard = (t) => client.get("/admin/bot/leaderboard", auth(t)).then(r => r.data);
export const adminGetMaintenance = (t) => client.get("/maintenance").then(r => r.data);
export const adminSetMaintenance = (t, enabled) => client.post("/admin/maintenance", { enabled }, auth(t)).then(r => r.data);
export const adminSetPermissions = (t, username, permissions) => client.post("/admin/team/permissions", { username, permissions }, auth(t)).then(r => r.data);

// Queue API
export const queueJoin = (userId, username, country) => 
    client.post("/queue/join", { user_id: userId, username, country }).then(r => r.data);
export const queueLeave = (userId, country) => 
    client.post("/queue/leave", { user_id: userId, country }).then(r => r.data);
export const getQueuePosition = (userId) => 
    client.get(`/queue/position/${userId}`).then(r => r.data);
export const getQueueStats = (country) => 
    client.get(`/queue/stats/${country}`).then(r => r.data);

// Countries
export const adminGetCountries = (t) => client.get("/countries", auth(t)).then(r => r.data);
export const adminUpdateCountry = (t, code, patch) => client.put("/admin/countries", { code, ...patch }, auth(t)).then(r => r.data);

// Countries
