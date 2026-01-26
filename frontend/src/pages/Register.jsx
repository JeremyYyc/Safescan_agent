import "../styles/auth.css";

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
          <div className="auth-title">Safe-Scan Home Safety</div>
          <div className="auth-subtitle">Create a new account</div>
        </div>
        <form className="auth-form" onSubmit={onSubmit}>
          <label className="auth-label">
            Email
            <input
              className="auth-input"
              type="email"
              value={registerForm.email}
              onChange={onEmailChange}
              required
            />
          </label>
          <label className="auth-label">
            Username
            <input
              className="auth-input"
              type="text"
              value={registerForm.username}
              onChange={onUsernameChange}
              required
            />
          </label>
          <label className="auth-label">
            Password
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
            {authLoading ? "Creating..." : "Create account"}
          </button>
          <button className="auth-switch" type="button" onClick={onSwitch}>
            Already have an account? Sign in
          </button>
        </form>
      </div>
    </div>
  );
}

export default RegisterPage;
