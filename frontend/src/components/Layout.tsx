import { Link, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function Layout() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  async function handleSignOut() {
    await signOut();
    navigate("/login", { replace: true });
  }

  return (
    <>
      <nav className="nav">
        <Link to="/" className="brand">
          Nexis
        </Link>
        <div className="spacer" />
        <span className="muted">{user?.email}</span>
        <button type="button" className="btn" onClick={handleSignOut}>
          Sign out
        </button>
      </nav>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
