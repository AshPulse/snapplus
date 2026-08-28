import { Zap } from "lucide-react";

export default function Logo({ size = "md" }) {
    const cfg =
        size === "sm"
            ? { pad: "6px 14px", font: 14, icon: 14 }
            : size === "lg"
            ? { pad: "10px 20px", font: 18, icon: 18 }
            : { pad: "8px 16px", font: 16, icon: 16 };
    return (
        <span
            className="snap-badge"
            data-testid="snap-logo"
            style={{ padding: cfg.pad, fontSize: cfg.font }}
        >
            <Zap size={cfg.icon} strokeWidth={3} />
            Snap+
        </span>
    );
}
