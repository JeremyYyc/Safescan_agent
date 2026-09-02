import { useState } from "react";
import "../styles/profile.css";
import { t } from "../i18n/index.js";
import LanguageSwitcher from "../components/LanguageSwitcher.jsx";

function ProfilePage({ authUser, onBack, onSave, saving, error }) {
  const displayEmail = authUser?.email || "";
  const [draft, setUsername] = useState(null);
  const username = draft ?? authUser?.username ?? "";
  const [status, setStatus] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus("");
    if (!username.trim()) {
      setStatus(t("Please Type in the username!"));
      return;
    }
    try {
      await onSave(username.trim());
      setStatus(t("Updated"));
    } catch {
      setStatus("");
    }
  }

  return (
    <div className="profile-page">
      <div className="profile-card">
        <div className="profile-header">
          <div className="profile-title">{t("Profile")}</div>
          <div className="profile-subtitle">{t("Edit your account details")}</div>
        </div>
        <form className="profile-body" onSubmit={handleSubmit}>
          <label className="profile-label">
            {t("Email")}
            <input className="profile-input" type="email" value={displayEmail} readOnly />
          </label>
          <label className="profile-label">
            {t("Username")}
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
            <LanguageSwitcher />
            <button className="btn ghost" type="button" onClick={onBack}>
              {t("Back to Home")}
            </button>
            <button className="btn solid" type="submit" disabled={saving}>
              {saving ? t("Saving...") : t("Save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ProfilePage;
