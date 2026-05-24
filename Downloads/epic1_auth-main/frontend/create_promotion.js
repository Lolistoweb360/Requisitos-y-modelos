const API_BASE = "http://127.0.0.1:5001/api";

function showMsg(text, type) {
  const el = document.getElementById("msg");
  el.textContent = text;
  el.className = `msg ${type}`;
}

function requireAuth() {
  const token = localStorage.getItem("token");
  if (!token) {
    window.location.href = "login.html";
    return null;
  }
  return token;
}

async function createPromotion() {
  const token = requireAuth();
  if (!token) return;

const payload = {
  name: document.getElementById("name").value.trim(),
  description: document.getElementById("description").value.trim(),
  price: document.getElementById("price").value,   // déjalo como string, backend lo convierte
  stock: document.getElementById("stock").value,   // idem
  image_url: document.getElementById("image_url").value.trim(),
  start_date: document.getElementById("start_date").value.trim(),
  end_date: document.getElementById("end_date").value.trim(),
};
console.log("payload", payload);

  // Debug útil: así ves EXACTO qué se está mandando
  console.log("payload", payload);

  if (
    !payload.name ||
    !payload.description ||
    !payload.image_url ||
    !payload.start_date_raw ||
    !payload.end_date_raw ||
    !Number.isFinite(payload.price) ||
    !Number.isFinite(payload.stock)
  ) {
    showMsg("Todos los campos son obligatorios", "error");
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/promotions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      showMsg(data.error || `Error (status ${res.status})`, "error");
      return;
    }

    showMsg("Promoción creada correctamente", "success");
  } catch {
    showMsg("Error al conectar con el servidor", "error");
  }
}