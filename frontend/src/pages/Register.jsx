import "../styles/auth.css";
import { t } from "../i18n/index.js";
import LanguageSwitcher from "../components/LanguageSwitcher.jsx";

function RegisterPage({
  registerForm,
  onEmailChange,
  onUsernameChange,
  onPasswordChange,
  authError,
  authLoading,
  onSubmit,
  onSwitch,
}) {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-title">{t("Safe-Scan Home Safety")}</div>
          <div className="auth-subtitle">{t("Create a new account")}</div>
        </div>
        <form className="auth-form" onSubmit={onSubmit}>
          <label className="auth-label">
            {t("Email")}
            <input
              className="auth-input"
              type="email"
              value={registerForm.email}
              onChange={onEmailChange}
              required
            />
          </label>
          <label className="auth-label">
            {t("Username")}
            <input
              className="auth-input"
              type="text"
              value={registerForm.username}
              onChange={onUsernameChange}
              required
            />
          </label>
          <label className="auth-label">
            {t("Password")}
            <input
              className="auth-input"
              type="password"
              value={registerForm.password}
              onChange={onPasswordChange}
              required
            />
          </label>
          {authError ? <div className="auth-error">{authError}</div> : null}
          <button className="btn solid full" type="submit" disabled={authLoading}>
            {authLoading ? t("Creating...") : t("Create account")}
          </button>
          <button className="auth-switch" type="button" onClick={onSwitch}>
            {t("Already have an account? Sign in")}
          </button>
          <LanguageSwitcher className="auth-switch" />
        </form>
      </div>
    </div>
  );
}

export default RegisterPage;
