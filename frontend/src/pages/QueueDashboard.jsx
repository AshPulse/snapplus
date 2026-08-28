import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Loader2, LogOut, Users, Clock, Zap } from "lucide-react";
import { toast } from "sonner";
import Logo from "../components/Logo";

const COUNTRIES = [
    { code: "FR", flag: "🇫🇷", name: "France" },
    { code: "BE", flag: "🇧🇪", name: "Belgium" },
    { code: "BG", flag: "🇧🇬", name: "Bulgaria" }
];

const API_BASE = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

export default function QueueDashboard() {
    const { userId } = useParams();
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({});
    const [position, setPosition] = useState(null);
    const [inQueue, setInQueue] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch stats per ogni paese
                for (const country of COUNTRIES) {
                    const res = await fetch(`${API_BASE}/api/queue/stats/${country.code}`);
                    if (res.ok) {
                        const data = await res.json();
                        setStats(prev => ({ ...prev, [country.code]: data }));
                    }
                }

                // Fetch position
                const posRes = await fetch(`${API_BASE}/api/queue/position/${userId}`);
                if (posRes.ok) {
                    const data = await posRes.json();
                    if (data.position) {
                        setPosition(data);
                        setInQueue(data.country);
                    }
                }
            } catch (err) {
                console.error("Fetch error:", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, [userId]);

    const handleJoin = async (country) => {
        try {
            const res = await fetch(`${API_BASE}/api/queue/join`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    user_id: userId,
                    username: localStorage.getItem("snap_nickname") || "User",
                    country
                })
            });
            
            if (res.ok) {
                const data = await res.json();
                setInQueue(country);
                toast.success(`Joined #${data.position} in ${country} queue`);
            } else {
                toast.error("Already in queue");
            }
        } catch (err) {
            toast.error("Error joining queue");
        }
    };

    const handleLeave = async () => {
        try {
            await fetch(`${API_BASE}/api/queue/leave`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: userId, country: inQueue })
            });
            setInQueue(null);
            toast.success("Left queue");
        } catch (err) {
            toast.error("Error leaving queue");
        }
    };

    if (loading) {
        return (
            <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0a0a0a" }}>
                <Loader2 size={48} style={{ animation: "spin 1s linear infinite", color: "#FACC15" }} />
            </div>
        );
    }

    return (
        <div style={{ minHeight: "100vh", background: "#0a0a0a", padding: "20px", color: "#e0e0e0" }}>
            <div style={{ maxWidth: "1200px", margin: "0 auto" }}>
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "40px" }}>
                    <Logo />
                    <p style={{ color: "#FACC15", fontWeight: 700 }}>Queue Dashboard</p>
                </div>

                {/* Queue Cards */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
                    {COUNTRIES.map(country => (
                        <div
                            key={country.code}
                            style={{
                                background: "#1a1a2e",
                                border: "1px solid #333",
                                borderRadius: "12px",
                                padding: "20px",
                                borderLeft: `4px solid #FACC15`
                            }}
                        >
                            <h3 style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 15px" }}>
                                {country.flag} {country.name}
                            </h3>

                            {stats[country.code] && (
                                <>
                                    <div style={{ marginBottom: "15px" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
                                            <Users size={16} />
                                            <span style={{ color: "#888", fontSize: "12px" }}>People in queue</span>
                                        </div>
                                        <p style={{ fontSize: "24px", fontWeight: 700, margin: 0 }}>
                                            {stats[country.code].people_in_queue}
                                        </p>
                                    </div>

                                    <div style={{ marginBottom: "15px" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
                                            <Clock size={16} />
                                            <span style={{ color: "#888", fontSize: "12px" }}>Average wait</span>
                                        </div>
                                        <p style={{ fontSize: "16px", margin: 0 }}>
                                            {stats[country.code].average_wait}
                                        </p>
                                    </div>

                                    {inQueue === country.code && position && (
                                        <div style={{ background: "rgba(34,197,94,0.1)", padding: "10px", borderRadius: "6px", marginBottom: "15px" }}>
                                            <p style={{ color: "#22c55e", fontSize: "12px", margin: 0 }}>
                                                ✅ Position #{position.position}
                                            </p>
                                        </div>
                                    )}

                                    <button
                                        onClick={() => inQueue === country.code ? handleLeave() : handleJoin(country.code)}
                                        style={{
                                            width: "100%",
                                            padding: "10px",
                                            background: inQueue === country.code ? "#ef4444" : "#FACC15",
                                            color: inQueue === country.code ? "#fff" : "#000",
                                            border: "none",
                                            borderRadius: "6px",
                                            fontWeight: 700,
                                            cursor: "pointer",
                                            fontSize: "14px"
                                        }}
                                    >
                                        {inQueue === country.code ? "LEAVE QUEUE" : "JOIN QUEUE"}
                                    </button>
                                </>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
