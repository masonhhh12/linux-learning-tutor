let registering = false;
const form = document.getElementById("auth-form");
const password = document.getElementById("password");
const submit = document.getElementById("submit");
const toggle = document.getElementById("switch");
const status = document.getElementById("status");

toggle.addEventListener("click", () => {
  registering = !registering;
  document.getElementById("title").textContent = registering ? "Start learning." : "Welcome back.";
  document.getElementById("intro").textContent = registering
    ? "Create your Linux Learning Tutor account." : "Sign in to continue your learning path.";
  submit.textContent = registering ? "Create account" : "Sign in";
  toggle.textContent = registering ? "Already registered? Sign in" : "New here? Create an account";
  password.autocomplete = registering ? "new-password" : "current-password";
  password.minLength = registering ? 15 : 1;
  password.value = "";
  status.textContent = "";
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (submit.disabled) return;
  submit.disabled = true;
  toggle.disabled = true;
  status.textContent = registering ? "Creating account…" : "Signing in…";
  try {
    const response = await fetch(registering ? "/auth/register" : "/auth/login", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        username:document.getElementById("username").value,
        password:password.value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string"
      ? data.detail : "Check your username and password requirements.");
    password.value = "";
    location.replace("/");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
    toggle.disabled = false;
  }
});
