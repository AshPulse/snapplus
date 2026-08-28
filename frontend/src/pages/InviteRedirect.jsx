import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";

export default function InviteRedirect() {
    const { code } = useParams();
    const navigate = useNavigate();
    useEffect(() => {
        navigate(`/register?invite=${encodeURIComponent(code)}`, { replace: true });
    }, [code, navigate]);
    return null;
}
