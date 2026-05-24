const API_BASE = "http://127.0.0.1:5001/api";

function showMsg(text, type) {
  const el = document.getElementById("msg");
  if (!el) return;
  el.textContent = text;
  el.className = `msg ${type}`;
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "login.html";
}

function requireAuth() {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "login.html";
    return null;
  }
  return token;
}

function initHome() {
  requireAuth();

  const user = JSON.parse(localStorage.getItem("user") || "null");
  const welcome = document.getElementById("welcome");
  const subtitle = document.getElementById("subtitle");

  if (welcome && user?.name) welcome.textContent = `Hola, ${user.name}!`;
  if (subtitle) subtitle.textContent = "Home listo. El listado de promociones lo implementará tu compañero.";

  showMsg("Sesión iniciada correctamente.", "success");
}

document.addEventListener("DOMContentLoaded", initHome);