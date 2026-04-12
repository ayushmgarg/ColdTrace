document.addEventListener("DOMContentLoaded", () => {
  if (getToken()) { window.location.href = "/"; return; }

  const form    = document.getElementById("login-form");
  const errBox  = document.getElementById("error-box");
  const btn     = document.getElementById("login-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errBox.classList.add("hidden");
    btn.textContent = "Signing in…";
    btn.disabled = true;

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email:    document.getElementById("email").value.trim(),
          password: document.getElementById("password").value,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Login failed");
      saveSession(data.access_token, data.user);
      window.location.href = data.user.role === "vaccinator" ? "/operator" : "/";
    } catch (err) {
      errBox.textContent = err.message;
      errBox.classList.remove("hidden");
      btn.textContent = "Sign in";
      btn.disabled = false;
    }
  });
});
