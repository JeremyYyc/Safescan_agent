import "../styles/auth.css";

function LoginPage({
  loginForm,
  onEmailChange,
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
          <div className="auth-title">Safe-Scan Home Safety</div>
          <div className="auth-subtitle">Sign in to continue</div>
        </div>
        <form className="auth-form" onSubmit={onSubmit}>
          <label className="auth-label">
            Email
            <input
              className="auth-input"
              type="email"
              value={loginForm.email}
              onChange={onEmailChange}
              required
            />
          </label>
          <label className="auth-label">
            Password
            <input
              className="auth-input"
              type="password"
              value={loginForm.password}
              onChange={onPasswordChange}
              required
            />
          </label>
          {authError ? <div className="auth-error">{authError}</div> : null}
          <button className="btn solid full" type="submit" disabled={authLoading}>
            {authLoading ? "Signing in..." : "Sign in"}
          </button>
          <button className="auth-switch" type="button" onClick={onSwitch}>
            Create a new account
          </button>
        </form>
      </div>
    </div>
  );
}

export default LoginPage;
