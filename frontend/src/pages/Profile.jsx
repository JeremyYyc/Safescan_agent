import { useEffect, useState } from "react";
import "../styles/profile.css";

function ProfilePage({ authUser, onBack, onSave, saving, error }) {
  const displayEmail = authUser?.email || "";
  const [username, setUsername] = useState(authUser?.username || "");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setUsername(authUser?.username || "");
  }, [authUser]);

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus("");
    if (!username.trim()) {
      setStatus("Please Type in the username!");
      return;
    }
    try {
      await onSave(username.trim());
      setStatus("Updated");
    } catch {
      setStatus("");
    }
  }

  return (
    <div className="profile-page">
      <div className="profile-card">
        <div className="profile-header">
          <div className="profile-title">Profile</div>
          <div className="profile-subtitle">Edit your account details</div>
        </div>
        <form className="profile-body" onSubmit={handleSubmit}>
          <label className="profile-label">
            Email
            <input className="profile-input" type="email" value={displayEmail} readOnly />
          </label>
          <label className="profile-label">
            Username
            <input
              className="profile-input"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>
          {error ? <div className="profile-error">{error}</div> : null}
          {status ? <div className="profile-status">{status}</div> : null}
          <div className="profile-actions">
            <button className="btn ghost" type="button" onClick={onBack}>
              Back to Home
            </button>
            <button className="btn solid" type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ProfilePage;
