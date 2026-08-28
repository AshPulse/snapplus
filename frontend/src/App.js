import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import Landing from "./pages/Landing";
import Register from "./pages/Register";
import UserStatus from "./pages/UserStatus";
import AdminLogin from "./pages/AdminLogin";
import AdminPanel from "./pages/AdminPanel";
import QueueDashboard from "./pages/QueueDashboard";
import InviteRedirect from "./pages/InviteRedirect";

function App() {
    return (
        <div className="App">
            <BrowserRouter>
                <Toaster position="top-center" theme="dark" richColors={false} />
                <Routes>
                    <Route path="/" element={<Landing />} />
                    <Route path="/register" element={<Register />} />
                    <Route path="/j/:code" element={<InviteRedirect />} />
                    <Route path="/status/:id" element={<UserStatus />} />
                    <Route path="/admin-login" element={<AdminLogin />} />
                    <Route path="/admin-secret-panel" element={<AdminPanel />} />
                    <Route path="/queue/:userId" element={<QueueDashboard />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </BrowserRouter>
        </div>
    );
}

export default App;
