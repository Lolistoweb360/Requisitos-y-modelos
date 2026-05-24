const API_BASE = "http://127.0.0.1:5001/api";

function getToken(){ return localStorage.getItem("token"); }
function getUser(){
  try { return JSON.parse(localStorage.getItem("user") || "null"); }
  catch { return null; }
}
function logout(){
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = "login.html";
}
function requireAuth(){
  const t = getToken();
  if(!t){ window.location.href="login.html"; return null; }
  return t;
}
function showMsg(id, text, type){
  const el = document.getElementById(id);
  if(!el) return;
  el.textContent = text;
  el.className = `msg ${type}`;
}

async function apiFetch(path, { method="GET", body=null } = {}) {
  const token = getToken();
  const headers = { };
  if (body !== null) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === null ? null : JSON.stringify(body),
  });

  const data = await res.json().catch(() => ({}));
  return { res, data };
}