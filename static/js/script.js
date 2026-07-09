// Ntuma customer form — send the order to the Flask backend.
const form = document.getElementById("order-form");
const msg = document.getElementById("message");
const btn = document.getElementById("submit-btn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.className = "message";
  msg.textContent = "";

  const payload = {
    text: document.getElementById("text").value.trim(),
    phone: document.getElementById("phone").value.trim(),
    location: document.getElementById("location").value.trim(),
  };

  if (!payload.text) { showError("Please describe what you'd like."); return; }

  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong");
    msg.className = "message ok";
    msg.textContent = `✅ Order #${data.id} received. We'll call you shortly.`;
    form.reset();
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Send Order";
  }
});

function showError(text) {
  msg.className = "message err";
  msg.textContent = "⚠️ " + text;
}
