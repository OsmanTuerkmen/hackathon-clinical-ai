"use strict";
// Simulated ID Austria identity provider page (OpenID Connect authorization code flow, fictional test persons).

(async () => {
  const params = new URLSearchParams(location.search);
  const state = params.get("state") || "";
  const redirectUri = params.get("redirect_uri") || "/";
  const confirmBtn = document.getElementById("idp-confirm");
  const status = document.getElementById("idp-status");
  const showError = (msg) => {
    const e = document.getElementById("idp-error");
    e.textContent = msg;
    e.classList.remove("hidden");
  };
  if (params.get("response_type") !== "code" || !state) {
    showError("Invalid sign-in request: an OpenID Connect authorization code request with a state is expected.");
    return;
  }

  let chosen = null;
  const persons = await (await fetch("/api/auth/persons")).json();
  const list = document.getElementById("idp-persons");
  for (const p of persons) {
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "person";
    input.value = p.id;
    input.addEventListener("change", () => { chosen = p.id; confirmBtn.disabled = false; });
    const name = document.createElement("b");
    name.textContent = p.name;
    const role = document.createElement("small");
    role.textContent = `${p.role} · test identity`;
    const text = document.createElement("span");
    text.append(name, role);
    const label = document.createElement("label");
    label.className = "idp-person";
    label.append(input, text);
    list.append(label);
  }

  confirmBtn.addEventListener("click", async () => {
    if (!chosen) return;
    confirmBtn.disabled = true;
    status.classList.remove("hidden");
    await new Promise(r => setTimeout(r, 900));  // stands in for the confirmation in the ID Austria app
    const res = await fetch("/idp-sim/approve", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person: chosen, state, redirect_uri: redirectUri }),
    });
    const out = await res.json();
    if (!res.ok) {
      status.classList.add("hidden");
      confirmBtn.disabled = false;
      showError(out.error || "Sign-in failed.");
      return;
    }
    location.assign(out.redirect);
  });
})();
