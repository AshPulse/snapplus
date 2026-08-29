import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import Logo from "../components/Logo";
import { registerUser, resolveInvite, validatePhone } from "../lib/api";

// Each country carries its own phone rules AND its own UI language.
const COUNTRIES = [
    {
        code: "FR",
        flag: "🇫🇷",
        dial: "+33",
        len: 9,
        hint: "6 12 34 56 78",
        sims: "Orange, SFR, Bouygues Telecom",
        lang: "fr",
    },
    {
        code: "BE",
        flag: "🇧🇪",
        dial: "+32",
        len: 9,
        hint: "470 12 34 56",
        sims: "Proximus, Orange, BASE",
        lang: "fr",
    },
    {
        code: "BG",
        flag: "🇧🇬",
        dial: "+359",
        len: 9,
        hint: "87 123 4567",
        sims: "A1, Yettel, Vivacom",
        lang: "bg",
    },
];

// UI strings per language. {n} and {sims} are placeholders.
const T = {
    fr: {
        title_a: "Créer mon ",
        title_b: "compte",
        subtitle: "Sélectionne ton pays et c'est parti !",
        country_label: "Pays",
        nickname_label: "Nickname Snap",
        nickname_ph: "Ex : Alex",
        phone_label: "Numéro de téléphone",
        note: "{n} chiffres, sans le 0",
        digits_expected: "{n} chiffres attendus",
        invalid_number: "Numéro invalide",
        carrier: "Opérateur : {c}",
        sim_notice: "Fonctionne uniquement avec les SIM {sims}.",
        submit: "Continuer",
        submitting: "En cours...",
        success: "Inscription reçue !",
        maintenance: "🛠 Maintenance en cours. Réessaie bientôt.",
        too_many: "Trop de tentatives. Attends une minute.",
        denied: "Accès refusé.",
        oops: "Oups, réessaie.",
        FR: "France",
        BE: "Belgique",
        BG: "Bulgarie",
    },
    bg: {
        title_a: "Създай ",
        title_b: "акаунт",
        subtitle: "Избери своята държава и започваме!",
        country_label: "Държава",
        nickname_label: "Snap потребителско име",
        nickname_ph: "Напр.: Alex",
        phone_label: "Телефонен номер",
        note: "{n} цифри, без нулата",
        digits_expected: "Очакват се {n} цифри",
        invalid_number: "Невалиден номер",
        carrier: "Оператор: {c}",
        sim_notice: "Работи само със SIM карти {sims}.",
        submit: "Продължи",
        submitting: "Обработва се...",
        success: "Регистрацията е приета!",
        maintenance: "🛠 Извършва се поддръжка. Опитай пак скоро.",
        too_many: "Твърде много опити. Изчакай минута.",
        denied: "Достъпът е отказан.",
        oops: "Опа, опитай пак.",
        FR: "Франция",
        BE: "Белгия",
        BG: "България",
    },
};

const fill = (s, map) =>
    Object.entries(map).reduce((acc, [k, v]) => acc.replaceAll(`{${k}}`, v), s);

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
    const t = T[cfg.lang] || T.fr;
    const cleanPhone = phone.replace(/\D/g, "");

    useEffect(() => {
        if (invite) {
            resolveInvite(invite).catch(() => setInvite(""));
        }
    }, [invite]);

    // Live NumVerify validation (debounce 500ms)
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
            setCheckMsg(fill(t.digits_expected, { n: cfg.len }));
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
                    setCheckMsg(res.error || t.invalid_number);
                }
            } catch {
                setCheckState("valid");
                setCheckMsg("");
            }
        }, 500);

        return () => clearTimeout(debounce.current);
    }, [cleanPhone, country, cfg.len, t]);

    const canSubmit = nickname.trim().length >= 1 && checkState === "valid" && !loading;

    const handlePhone = (e) => {
        let v = e.target.value.replace(/\D/g, "");
        if (country === "FR" && v.startsWith("0")) v = v.slice(1);
        if (v.length > cfg.len) v = v.slice(0, cfg.len);
        const parts = v.match(/.{1,2}/g) || [];
        setPhone(parts.join(" "));
    };

    const pickCountry = (code) => {
        setCountry(code);
        setPhone("");
        setCheckState("idle");
        setCheckMsg("");
        setCarrier("");
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
            toast.success(t.success);
            navigate(`/status/${res.id}`);
        } catch (err) {
            const detail = err?.response?.data?.detail;
            if (err?.response?.status === 503) {
                toast.error(t.maintenance);
            } else if (err?.response?.status === 429) {
                toast.error(t.too_many);
            } else if (detail === "Access denied") {
                toast.error(t.denied);
            } else {
                toast.error(typeof detail === "string" ? detail : t.oops);
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
                    {t.title_a}<span className="snap-accent">{t.title_b}</span>
                </h1>
                <p style={{ textAlign: "center", color: "#9a9a9a", margin: "0 0 24px", fontSize: 15 }}>{t.subtitle}</p>

                {/* Country picker as tappable cards */}
                <label className="snap-label">{t.country_label}</label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginBottom: 18 }} data-testid="country-cards">
                    {COUNTRIES.map((c) => {
                        const active = c.code === country;
                        return (
                            <button
                                type="button"
                                key={c.code}
                                onClick={() => pickCountry(c.code)}
                                data-testid={`country-${c.code}`}
                                style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                    gap: 6,
                                    padding: "14px 6px",
                                    borderRadius: 16,
                                    cursor: "pointer",
                                    background: active ? "rgba(250,204,21,0.06)" : "#0f0f0f",
                                    border: active ? "1px solid rgba(250,204,21,0.6)" : "1px solid rgba(255,255,255,0.07)",
                                    transition: "border-color .2s, background .2s",
                                }}
                            >
                                <span style={{ fontSize: 22, lineHeight: 1 }}>{c.flag}</span>
                                <span style={{ fontSize: 13, fontWeight: 700, color: active ? "#FACC15" : "#e5e5e5" }}>
                                    {t[c.code]}
                                </span>
                            </button>
                        );
                    })}
                </div>

                <label className="snap-label">{t.nickname_label}</label>
                <input className="snap-input" placeholder={t.nickname_ph} value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={40} data-testid="register-nickname-input" autoFocus />

                <div style={{ height: 18 }} />

                <label className="snap-label">{t.phone_label}</label>
                <div style={{ display: "flex", alignItems: "center", background: "#0f0f0f", border: `1px solid ${borderColor}`, borderRadius: 18, overflow: "hidden", transition: "border-color .2s" }}>
                    <div style={{ padding: "16px 12px", color: "#FACC15", fontWeight: 700, fontSize: 15, background: "rgba(250,204,21,0.05)", borderRight: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }} data-testid="dial-code">
                        {cfg.flag} {cfg.dial}
                    </div>

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
                    {checkState === "invalid"
                        ? `⚠️ ${checkMsg}`
                        : carrier
                            ? `✅ ${fill(t.carrier, { c: carrier })}`
                            : fill(t.note, { n: cfg.len })}
                </p>

                <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(250,145,0,0.08)", border: "1px solid rgba(250,145,0,0.35)", borderRadius: 14, fontSize: 12, color: "#ffb84d" }} data-testid="sim-notice">
                    ⚠️ {fill(t.sim_notice, { sims: cfg.sims })}
                </div>

                <div style={{ height: 26 }} />
                <button type="submit" className="snap-btn" disabled={!canSubmit} data-testid="register-submit-btn">
                    {loading ? t.submitting : t.submit} {!loading && <ArrowRight size={20} strokeWidth={3} />}
                </button>
            </form>
        </div>
    );
}
