import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import Logo from "../components/Logo";
import { registerUser, resolveInvite, validatePhone } from "../lib/api";

const COUNTRIES = [
    { code: "FR", flag: "🇫🇷", dial: "+33", len: 9, hint: "6 12 34 56 78", note: "9 chiffres, sans le 0", sims: "Orange, SFR, Bouygues Telecom" },
    { code: "IT", flag: "🇮🇹", dial: "+39", len: 10, hint: "312 345 6789", note: "10 chiffres", sims: "TIM, Vodafone, WindTre, Iliad" },
    { code: "DE", flag: "🇩🇪", dial: "+49", len: 10, hint: "151 2345678", note: "10 chiffres", sims: "Telekom, Vodafone, O2" },
    { code: "ES", flag: "🇪🇸", dial: "+34", len: 9, hint: "612 345 678", note: "9 chiffres", sims: "Movistar, Vodafone, Orange" },
    { code: "GB", flag: "🇬🇧", dial: "+44", len: 10, hint: "7400 123456", note: "10 chiffres", sims: "EE, Vodafone, O2, Three" },
    { code: "BE", flag: "🇧🇪", dial: "+32", len: 9, hint: "470 12 34 56", note: "9 chiffres", sims: "Proximus, Orange, BASE" },
];

export default function Register() {
    const navigate = useNavigate();
    const [params] = useSearchParams();
    const [nickname, setNickname] = useState("");
    const [phone, setPhone] = useState("");
    const [country, setCountry] = useState("FR");
    const [loading, setLoading] = useState(false);
    const [invite, setInvite] = useState(params.get("invite") || "");

    // idle | checking | valid | invalid
    const [checkState, setCheckState] = useState("idle");
    const [checkMsg, setCheckMsg] = useState("");
    const [carrier, setCarrier] = useState("");
    const debounce = useRef(null);

    const cfg = COUNTRIES.find((c) => c.code === country) || COUNTRIES[0];
    const cleanPhone = phone.replace(/\D/g, "");

    useEffect(() => {
        if (invite) {
            resolveInvite(invite).catch(() => setInvite(""));
        }
    }, [invite]);

    // Validation NumVerify en temps reel (debounce 500ms)
    useEffect(() => {
        if (debounce.current) clearTimeout(debounce.current);
        setCarrier("");

        if (cleanPhone.length === 0) {
            setCheckState("idle");
            setCheckMsg("");
            return;
        }
        if (cleanPhone.length !== cfg.len) {
            setCheckState("invalid");
            setCheckMsg(`${cfg.len} chiffres attendus`);
            return;
        }

        setCheckState("checking");
        setCheckMsg("");
        debounce.current = setTimeout(async () => {
            try {
                const res = await validatePhone(cleanPhone, country);
                if (res.valid) {
                    setCheckState("valid");
                    setCheckMsg("");
                    if (res.carrier && res.carrier !== "Unknown") setCarrier(res.carrier);
                } else {
                    setCheckState("invalid");
                    setCheckMsg(res.error || "Numero invalide");
                }
            } catch {
                setCheckState("valid");
                setCheckMsg("");
            }
        }, 500);

        return () => clearTimeout(debounce.current);
    }, [cleanPhone, country, cfg.len]);

    const canSubmit = nickname.trim().length >= 1 && checkState === "valid" && !loading;

    const handlePhone = (e) => {
        let v = e.target.value.replace(/\D/g, "");
        if (country === "FR" && v.startsWith("0")) v = v.slice(1);
        if (v.length > cfg.len) v = v.slice(0, cfg.len);
        const parts = v.match(/.{1,2}/g) || [];
        setPhone(parts.join(" "));
    };

    const submit = async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        setLoading(true);
        try {
            const clean = nickname.trim().replace(/[<>`]/g, "").slice(0, 40);
            const res = await registerUser({
                nickname: clean,
                phone: cleanPhone,
                country_code: country,
                invite: invite || null,
            });
            localStorage.setItem("snap_user_id", res.id);
            localStorage.setItem("snap_nickname", clean);
            toast.success("Inscription recue !");
            navigate(`/status/${res.id}`);
        } catch (err) {
            const detail = err?.response?.data?.detail;
            if (err?.response?.status === 503) {
                toast.error("🛠 Maintenance en cours. Reessaie bientot.");
            } else if (err?.response?.status === 429) {
                toast.error("Trop de tentatives. Attends une minute.");
            } else if (detail === "Access denied") {
                toast.error("Acces refuse.");
            } else {
                toast.error(typeof detail === "string" ? detail : "Oups, reessaie.");
            }
        } finally {
            setLoading(false);
        }
    };

    const borderColor =
        checkState === "invalid" ? "rgba(239,68,68,0.5)" :
        checkState === "valid" ? "rgba(34,197,94,0.45)" : "rgba(255,255,255,0.07)";

    return (
        <div className="snap-aura" style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
            <form onSubmit={submit} className="snap-card" style={{ width: "100%", maxWidth: 420, padding: "32px 26px" }} data-testid="register-card">
                <div style={{ textAlign: "center", marginBottom: 16 }}><Logo /></div>
                <h1 style={{ fontSize: 34, textAlign: "center", fontWeight: 700, margin: "8px 0 6px", letterSpacing: "-0.02em" }}>
                    Creer mon <span className="snap-accent">compte</span>
                </h1>
                <p style={{ textAlign: "center", color: "#9a9a9a", margin: "0 0 24px", fontSize: 15 }}>2 champs. 20 secondes. C'est tout.</p>

                <label className="snap-label">Nickname Snap</label>
                <input className="snap-input" placeholder="Ex : Alex" value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={40} data-testid="register-nickname-input" autoFocus />

                <div style={{ height: 18 }} />

                <label className="snap-label">Telephone</label>
                <div style={{ display: "flex", alignItems: "center", background: "#0f0f0f", border: `1px solid ${borderColor}`, borderRadius: 18, overflow: "hidden", transition: "border-color .2s" }}>
                    <select
                        value={country}
                        onChange={(e) => { setCountry(e.target.value); setPhone(""); setCheckState("idle"); setCheckMsg(""); }}
                        data-testid="register-country-select"
                        style={{ padding: "16px 10px", color: "#FACC15", fontWeight: 700, fontSize: 15, background: "rgba(250,204,21,0.05)", border: "none", outline: "none", borderRight: "1px solid rgba(255,255,255,0.07)", cursor: "pointer" }}
                    >
                        {COUNTRIES.map((c) => (
                            <option key={c.code} value={c.code} style={{ background: "#0f0f0f" }}>
                                {c.flag} {c.dial}
                            </option>
                        ))}
                    </select>

                    <input
                        className="snap-input"
                        style={{ border: "none", background: "transparent", padding: "16px 14px", flex: 1, minWidth: 0 }}
                        placeholder={cfg.hint}
                        value={phone}
                        onChange={handlePhone}
                        inputMode="numeric"
                        data-testid="register-phone-input"
                    />

                    <div style={{ width: 42, display: "flex", alignItems: "center", justifyContent: "center" }} data-testid="phone-check-icon">
                        {checkState === "checking" && <Loader2 size={18} color="#FACC15" style={{ animation: "snapspin 1s linear infinite" }} />}
                        {checkState === "valid" && <Check size={18} color="#22c55e" strokeWidth={3} />}
                        {checkState === "invalid" && <X size={18} color="#ef4444" strokeWidth={3} />}
                    </div>
                </div>

                <p style={{ color: checkState === "invalid" ? "#ef4444" : "#6a6a6a", fontSize: 12, margin: "8px 0 0" }}>
                    {checkState === "invalid" ? `⚠️ ${checkMsg}` : carrier ? `✅ Operateur : ${carrier}` : cfg.note}
                </p>

                <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(250,145,0,0.08)", border: "1px solid rgba(250,145,0,0.35)", borderRadius: 14, fontSize: 12, color: "#ffb84d" }} data-testid="sim-notice">
                    ⚠️ Operateurs compatibles : <b>{cfg.sims}</b>.
                </div>

                <div style={{ height: 26 }} />
                <button type="submit" className="snap-btn" disabled={!canSubmit} data-testid="register-submit-btn">
                    {loading ? "En cours..." : "Continuer"} {!loading && <ArrowRight size={20} strokeWidth={3} />}
                </button>
            </form>
        </div>
    );
}
