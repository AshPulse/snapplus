import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { Sparkles, Check, Eye, ShieldAlert } from "lucide-react";
import Logo from "../components/Logo";
import { trackVisit, liveCount } from "../lib/api";

export default function Landing() {
    const navigate = useNavigate();
    const [live, setLive] = useState(10);
    const [total, setTotal] = useState(321);
    const [blocked, setBlocked] = useState(false);
    const [country, setCountry] = useState("");

    useEffect(() => {
        (async () => {
            const v = await trackVisit();
            if (v.banned || v.proxy) setBlocked(v.proxy ? "vpn" : "ban");
            if (v.country) setCountry(v.country);
            try {
                const c = await liveCount();
                setTotal(c.total_all_time || 321);
            } catch {}
        })();
        // fake live fluctuating counter
        setLive(8 + Math.floor(Math.random() * 8));
        const iv = setInterval(() => {
            setLive((n) => {
                const delta = Math.floor(Math.random() * 5) - 2;
                let nv = n + delta;
                if (nv < 5) nv = 5 + Math.floor(Math.random() * 3);
                if (nv > 17) nv = 15 - Math.floor(Math.random() * 3);
                return nv;
            });
        }, 2500);
        return () => clearInterval(iv);
    }, []);

    if (blocked) {
        return (
            <div className="snap-aura" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
                <div className="snap-card" style={{ padding: 32, maxWidth: 420, textAlign: "center" }} data-testid="blocked-card">
                    <ShieldAlert size={54} color="#ef4444" style={{ margin: "0 auto 14px" }} />
                    <h2 style={{ fontSize: 24, fontWeight: 700, margin: "0 0 8px" }}>Accès refusé</h2>
                    <p style={{ color: "#a0a0a0" }}>
                        {blocked === "vpn"
                            ? "Nous avons détecté l'utilisation d'un VPN ou proxy. Désactive-le pour accéder à Snap+."
                            : "Ton adresse IP a été bloquée. Contacte un administrateur."}
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="snap-aura" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 20 }}>
            <div className="snap-card" style={{ width: "100%", maxWidth: 420, padding: "36px 28px 28px" }} data-testid="landing-card">
                <div style={{ textAlign: "center", marginBottom: 16 }}>
                    <Logo size="lg" />
                </div>

                {/* fake live counter badge */}
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 18 }}>
                    <span className="snap-chip" style={{ background: "rgba(250,204,21,0.1)", borderColor: "rgba(250,204,21,0.3)", color: "#FACC15", padding: "6px 14px" }} data-testid="live-counter">
                        <Eye size={14} strokeWidth={2.5} />
                        <b style={{ color: "#FACC15" }}>{live}</b>
                        <span style={{ color: "#d4d4d4" }}>personnes activent Snap+ en direct</span>
                    </span>
                </div>

                <h1 style={{ fontSize: 42, lineHeight: 1.05, textAlign: "center", fontWeight: 700, margin: "6px 0 12px", letterSpacing: "-0.02em" }} data-testid="landing-title">
                    Bienvenue sur<br /><span className="snap-accent">Snap+</span>
                </h1>

                <p style={{ textAlign: "center", color: "#a0a0a0", fontSize: 16, margin: "0 0 20px", padding: "0 8px", lineHeight: 1.5 }}>
                    Le service premium <b style={{ color: "#e5e5e5" }}>nouvelle génération</b>. Rapide, discret, sans prise de tête.
                </p>

                <div style={{ textAlign: "center", marginBottom: 20, color: "#9a9a9a", fontSize: 14 }}>
                    <b className="snap-accent">{total.toLocaleString("fr-FR")}</b> personnes ont activé le premium grâce à nous {country && <>· depuis {country}</>}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 22 }}>
                    {["Inscription en 20 secondes", "Validation instantanée", "100% mobile, 100% simple"].map((t) => (
                        <div key={t} style={{ display: "flex", alignItems: "center", gap: 12, background: "#0f0f0f", border: "1px solid #1c1c1c", padding: "12px 16px", borderRadius: 999 }}>
                            <span style={{ width: 22, height: 22, borderRadius: 999, background: "rgba(250,204,21,0.18)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                <Check size={14} color="#FACC15" strokeWidth={3} />
                            </span>
                            <span style={{ fontSize: 15, fontWeight: 500 }}>{t}</span>
                        </div>
                    ))}
                </div>

                <button className="snap-btn" onClick={() => navigate("/register" + window.location.search)} data-testid="landing-signup-btn">
                    <Sparkles size={20} strokeWidth={2.5} />
                    S'inscrire
                </button>

                <p style={{ textAlign: "center", color: "#6a6a6a", fontSize: 13, marginTop: 14 }}>Gratuit · Aucune carte bancaire</p>
            </div>
            <p style={{ color: "#4a4a4a", fontSize: 12, marginTop: 22, letterSpacing: 1 }}>© Snap+ · MMXXVI</p>
        </div>
    );
}
