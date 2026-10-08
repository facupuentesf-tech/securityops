"use strict";
const $ = (id) => document.getElementById(id);
const statuses = {open: "Abierto", investigating: "En investigación", resolved: "Resuelto"};
const severities = {low: "Baja", medium: "Media", high: "Alta", critical: "Crítica"};
const roles = {administrador: "Administrador", analista: "Analista", lector: "Lector"};
const assetTypes = {hardware: "Hardware", software: "Software", service: "Servicio", data: "Datos"};
let assetListVersion = 0;
let assetDetailVersion = 0;
const dateFormat = new Intl.DateTimeFormat("es", {dateStyle: "medium", timeStyle: "short"});
let selectedId = null;
let listVersion = 0;
let detailVersion = 0;
let currentUser = null;
let csrfToken = null;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function dateNode(value) {
  const node = element("time", dateFormat.format(new Date(value)));
  node.dateTime = value;
  return node;
}
function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "message error" : "message";
  $("message").hidden = !text;
}
function showLogin() {
  currentUser = null;
  csrfToken = null;
  selectedId = null;
  ++listVersion;
  ++detailVersion;
  ++assetListVersion;
  ++assetDetailVersion;
  $("asset-list").replaceChildren();
  $("asset-detail-content").hidden = true;
  $("asset-create-form").reset();
  $("asset-filter-form").reset();
  $("asset-list-panel").hidden = false;
  $("asset-detail-panel").hidden = true;
  $("account").hidden = true;
  $("app-view").hidden = true;
  $("login-view").hidden = false;
  $("incident-list").replaceChildren();
  $("user-list").replaceChildren();
  $("count").textContent = "";
  $("list-feedback").textContent = "";
  $("message").textContent = "";
  $("message").hidden = true;
  $("list-view").hidden = false;
  $("detail-view").hidden = true;
}
function showApplication(session) {
  currentUser = session.user;
  csrfToken = session.csrf_token;
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("account").hidden = false;
  $("account-name").textContent = `${currentUser.display_name} · ${roles[currentUser.role]}`;
  const canWrite = currentUser.role !== "lector";
  $("new-button").hidden = !canWrite;
  $("new-asset-button").hidden = !canWrite;
  $("asset-create-panel").hidden = true;
  loadAssets();
  $("create-panel").hidden = true;
  $("status-form").hidden = !canWrite;
  $("note-form").hidden = !canWrite;
  $("users-view").hidden = currentUser.role !== "administrador";
  loadList();
  if (currentUser.role === "administrador") loadUsers();
}
async function api(path, method = "GET", body) {
  let response;
  try {
    const headers = body === undefined ? {} : {"Content-Type": "application/json"};
    if (method !== "GET" && method !== "HEAD" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("No se pudo conectar con el servidor. Comprobá que esté iniciado y volvé a intentar.");
  }
  if (!response.ok) {
    if (response.status === 401) {
      if (path === "/auth/login") {
        throw new Error("Correo o contraseña incorrectos, o cuenta desactivada.");
      }
      showLogin();
      $("login-feedback").textContent = "La sesión finalizó. Iniciá sesión nuevamente.";
      $("login-feedback").hidden = false;
      throw new Error("La sesión finalizó. Iniciá sesión nuevamente.");
    }
    if (response.status === 403) throw new Error("Tu rol no tiene permiso para realizar esta operación.");
    if (response.status === 404) throw new Error("No se encontró el registro solicitado.");
    if (response.status === 409) throw new Error("La operación no se puede completar por un conflicto con los datos.");
    if (response.status === 422) throw new Error("Revisá los campos: completá los textos y usá valores válidos. Las notas admiten entre 1 y 5000 caracteres.");
    throw new Error("El servidor no pudo completar la operación. Volvé a intentar.");
  }
  return response.json();
}
function busy(form, value, text) {
  for (const control of form.elements) control.disabled = value;
  const button = form.querySelector('button[type="submit"]');
  if (value) { button.dataset.label = button.textContent; button.textContent = text; }
  else button.textContent = button.dataset.label;
}
async function loadList() {
  const version = ++listVersion;
  $("incident-list").replaceChildren();
  $("count").textContent = "";
  $("list-feedback").textContent = "Cargando incidentes…";
  const query = new URLSearchParams();
  for (const [key, value] of new FormData($("filter-form"))) if (value) query.set(key, value);
  try {
    const incidents = await api(`/incidents${query.size ? "?" + query : ""}`);
    if (version !== listVersion) return;
    $("count").textContent = `${incidents.length} ${incidents.length === 1 ? "incidente" : "incidentes"}`;
    $("list-feedback").textContent = incidents.length ? "" : (query.size ? "No hay incidentes que coincidan con los filtros." : "Todavía no hay incidentes. Creá el primero para comenzar.");
    for (const incident of incidents) {
      const row = element("article", undefined, "incident");
      const title = element("button", incident.title, "incident-title");
      title.type = "button";
      title.addEventListener("click", () => openDetail(incident.id));
      row.append(title, element("span", severities[incident.severity], `badge severity-${incident.severity}`), element("span", statuses[incident.status], "badge"), dateNode(incident.created_at));
      $("incident-list").append(row);
    }
  } catch (error) {
    if (version === listVersion) $("list-feedback").textContent = error.message + " Usá Aplicar filtros para reintentar.";
  }
}
async function loadUsers() {
  $("user-list").replaceChildren();
  $("users-feedback").textContent = "Cargando usuarios…";
  try {
    const users = await api("/users");
    $("users-feedback").textContent = users.length ? "" : "Todavía no hay usuarios.";
    for (const user of users) {
      const item = element("article", undefined, "user-item");
      const info = element("div", undefined, "user-info");
      info.append(element("strong", user.display_name), element("span", `${user.email} · Creado ${dateFormat.format(new Date(user.created_at))}`));
      const form = element("form", undefined, "user-edit-form");
      const roleLabel = element("label", "Rol");
      const role = document.createElement("select");
      role.name = "role";
      for (const [value, text] of Object.entries(roles)) {
        const option = element("option", text);
        option.value = value;
        option.selected = value === user.role;
        role.append(option);
      }
      roleLabel.append(role);
      const activeLabel = element("label", "Acceso");
      const active = document.createElement("select");
      active.name = "is_active";
      for (const [value, text] of [["true", "Activo"], ["false", "Desactivado"]]) {
        const option = element("option", text);
        option.value = value;
        option.selected = (value === "true") === user.is_active;
        active.append(option);
      }
      activeLabel.append(active);
      const save = element("button", "Guardar", "secondary");
      save.type = "submit";
      if (user.id === currentUser.id) active.disabled = true;
      form.append(roleLabel, activeLabel, save);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await api(`/users/${user.id}`, "PATCH", {
            role: role.value,
            is_active: active.value === "true",
          });
          if (user.id === currentUser.id) {
            const session = await api("/auth/session");
            if (session.user) showApplication(session);
            else showLogin();
            return;
          }
          $("users-feedback").textContent = "Usuario actualizado.";
          await loadUsers();
        } catch (error) {
          $("users-feedback").textContent = error.message;
        }
      });
      const reset = element("form", undefined, "user-reset-form");
      const passwordLabel = element("label", "Nueva contraseña");
      const password = document.createElement("input");
      password.type = "password";
      password.name = "password";
      password.minLength = 12;
      password.maxLength = 128;
      password.autocomplete = "new-password";
      password.required = true;
      passwordLabel.append(password);
      const resetButton = element("button", "Restablecer contraseña", "text-button");
      resetButton.type = "submit";
      reset.append(passwordLabel, resetButton);
      reset.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          await api(`/users/${user.id}/password`, "POST", {password: password.value});
          reset.reset();
          if (user.id === currentUser.id) {
            showLogin();
            $("login-feedback").textContent = "Contraseña actualizada. Iniciá sesión con la nueva contraseña.";
            $("login-feedback").hidden = false;
            return;
          }
          $("users-feedback").textContent = "Contraseña actualizada; se cerraron las sesiones de esa cuenta.";
        } catch (error) {
          $("users-feedback").textContent = error.message;
        }
      });
      item.append(info, form, reset);
      $("user-list").append(item);
    }
  } catch (error) {
    $("users-feedback").textContent = error.message;
  }
}
async function loadCollection(id, type, version) {
  const isHistory = type === "history";
  const feedback = $(isHistory ? "history-feedback" : "notes-feedback");
  const list = $(isHistory ? "history-list" : "notes-list");
  list.replaceChildren();
  feedback.textContent = isHistory ? "Cargando historial…" : "Cargando notas…";
  try {
    const entries = await api(`/incidents/${id}/${type}`);
    if (id !== selectedId || version !== detailVersion) return;
    feedback.textContent = entries.length ? "" : (isHistory ? "Todavía no hay cambios de estado." : "Todavía no hay notas de investigación.");
    for (const entry of entries) {
      const item = element("li");
      item.append(element("p", isHistory ? `${statuses[entry.previous_status]} → ${statuses[entry.new_status]}` : entry.content, "user-text"), dateNode(isHistory ? entry.changed_at : entry.created_at));
      const author = isHistory ? entry.changed_by_name : entry.created_by_name;
      if (author) item.append(element("small", `Por ${author}`, "muted"));
      list.append(item);
    }
  } catch (error) {
    if (id === selectedId && version === detailVersion) {
      feedback.textContent = error.message;
      const retry = element("button", "Reintentar", "text-button");
      retry.type = "button";
      retry.addEventListener("click", () => loadCollection(id, type, version));
      feedback.append(" ", retry);
    }
  }
}
async function openDetail(id, clearMessage = true) {
  selectedId = id;
  const version = ++detailVersion;
  if (clearMessage) message("");
  $("list-view").hidden = true;
  $("detail-view").hidden = false;
  $("detail-content").hidden = true;
  $("detail-feedback").textContent = "Cargando incidente…";
  $("note-form").reset();
  try {
    const incident = await api(`/incidents/${id}`);
    if (version !== detailVersion || selectedId !== id) return;
    $("detail-id").textContent = `INCIDENTE #${id}`;
    $("detail-title").textContent = incident.title;
    $("detail-description").textContent = incident.description;
    $("detail-date").replaceChildren("Creado el ", dateNode(incident.created_at));
    $("detail-severity").textContent = `Severidad ${severities[incident.severity].toLowerCase()}`;
    $("detail-severity").className = `badge severity-${incident.severity}`;
    $("status-form").elements.status.value = incident.status;
    $("detail-feedback").textContent = "";
    $("detail-content").hidden = false;
    $("detail-title").focus();
    await Promise.all([loadCollection(id, "history", version), loadCollection(id, "notes", version)]);
  } catch (error) {
    if (version === detailVersion) {
      $("detail-feedback").textContent = error.message;
      const retry = element("button", "Reintentar", "text-button");
      retry.type = "button";
      retry.addEventListener("click", () => openDetail(id));
      $("detail-feedback").append(" ", retry);
    }
  }
}
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const credentials = Object.fromEntries(new FormData(form));
  busy(form, true, "Ingresando…");
  $("login-feedback").textContent = "";
  $("login-feedback").hidden = true;
  try {
    const session = await api("/auth/login", "POST", credentials);
    form.reset();
    showApplication(session);
  } catch (error) {
    $("login-feedback").textContent = error.message;
    $("login-feedback").hidden = false;
  } finally {
    busy(form, false);
  }
});
$("logout-button").addEventListener("click", async () => {
  try {
    await api("/auth/logout", "POST");
  } catch (error) {
    $("login-feedback").textContent = error.message;
    $("login-feedback").hidden = false;
  } finally {
    showLogin();
  }
});
$("user-create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form));
  busy(form, true, "Creando…");
  $("users-feedback").textContent = "";
  try {
    await api("/users", "POST", body);
    form.reset();
    $("users-feedback").textContent = "Usuario creado.";
    await loadUsers();
  } catch (error) {
    $("users-feedback").textContent = error.message;
  } finally {
    busy(form, false);
  }
});
$("reload-users").addEventListener("click", loadUsers);
$("new-button").addEventListener("click", () => { $("create-panel").hidden = false; $("create-form").elements.title.focus(); });
$("cancel-create").addEventListener("click", () => { $("create-panel").hidden = true; $("new-button").focus(); });
$("filter-form").addEventListener("submit", (event) => { event.preventDefault(); message(""); loadList(); });
$("clear-filters").addEventListener("click", () => { $("filter-form").reset(); message(""); loadList(); });
$("back-button").addEventListener("click", () => {
  selectedId = null; ++detailVersion;
  $("detail-view").hidden = true; $("list-view").hidden = false;
  message(""); loadList(); $("new-button").focus();
});
$("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form));
  body.title = body.title.trim(); body.description = body.description.trim();
  if (!body.title || !body.description) { message("Completá el título y la descripción con texto.", true); return; }
  busy(form, true, "Creando…"); message("");
  try {
    const incident = await api("/incidents", "POST", body);
    form.reset(); $("create-panel").hidden = true;
    message("Incidente creado correctamente.");
    await openDetail(incident.id, false);
  } catch (error) { message(error.message, true); }
  finally { busy(form, false); }
});
$("status-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget; const id = selectedId; const version = detailVersion;
  const status = form.elements.status.value;
  busy(form, true, "Guardando…"); message("");
  try {
    await api(`/incidents/${id}/status`, "PATCH", {status});
    if (id !== selectedId || version !== detailVersion) return;
    message("Estado guardado correctamente.");
    await loadCollection(id, "history", version);
  } catch (error) { if (id === selectedId && version === detailVersion) message(error.message, true); }
  finally { busy(form, false); }
});
$("note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget; const id = selectedId; const version = detailVersion;
  const content = form.elements.content.value.trim();
  if (Array.from(content).length < 1 || Array.from(content).length > 5000) { message("La nota debe tener entre 1 y 5000 caracteres después de quitar los espacios de los extremos.", true); return; }
  busy(form, true, "Agregando…"); message("");
  try {
    await api(`/incidents/${id}/notes`, "POST", {content});
    if (id !== selectedId || version !== detailVersion) return;
    form.reset(); message("Nota agregada correctamente.");
    await loadCollection(id, "notes", version);
  } catch (error) { if (id === selectedId && version === detailVersion) message(error.message, true); }
  finally { busy(form, false); }
});
async function loadAssets() {
  const version = ++assetListVersion;
  $("asset-list").replaceChildren();
  $("asset-count").textContent = "";
  $("asset-list-feedback").textContent = "Cargando activos…";
  const query = new URLSearchParams();
  for (const [key, value] of new FormData($("asset-filter-form"))) if (value) query.set(key, value);
  try {
    const assets = await api(`/assets${query.size ? "?" + query : ""}`);
    if (version !== assetListVersion) return;
    $("asset-count").textContent = `${assets.length} ${assets.length === 1 ? "activo" : "activos"}`;
    $("asset-list-feedback").textContent = assets.length ? "" : (query.size ? "No hay activos que coincidan con los filtros." : "Todavía no hay activos registrados.");
    for (const asset of assets) {
      const row = element("article", undefined, "incident asset");
      const name = element("button", asset.name, "incident-title asset-name");
      name.type = "button";
      name.addEventListener("click", () => openAssetDetail(asset.id));
      row.append(name, element("span", assetTypes[asset.type], "badge"), element("span", severities[asset.criticality], `badge severity-${asset.criticality}`), dateNode(asset.created_at));
      $("asset-list").append(row);
    }
  } catch (error) {
    if (version === assetListVersion) $("asset-list-feedback").textContent = error.message + " Usá Aplicar filtros para reintentar.";
  }
}
async function openAssetDetail(id) {
  const version = ++assetDetailVersion;
  $("asset-create-panel").hidden = true;
  $("asset-list-panel").hidden = true;
  $("asset-detail-panel").hidden = false;
  $("asset-detail-content").hidden = true;
  $("asset-detail-feedback").textContent = "Cargando activo…";
  try {
    const asset = await api(`/assets/${id}`);
    if (version !== assetDetailVersion) return;
    $("asset-detail-id").textContent = `ACTIVO #${asset.id}`;
    $("asset-detail-name").textContent = asset.name;
    $("asset-detail-description").textContent = asset.description || "Sin descripción.";
    $("asset-detail-date").replaceChildren("Creado el ", dateNode(asset.created_at));
    $("asset-detail-type").textContent = `Tipo: ${assetTypes[asset.type]}`;
    $("asset-detail-criticality").textContent = `Criticidad ${severities[asset.criticality].toLowerCase()}`;
    $("asset-detail-criticality").className = `badge severity-${asset.criticality}`;
    $("asset-detail-feedback").textContent = "";
    $("asset-detail-content").hidden = false;
    $("asset-detail-name").focus();
  } catch (error) {
    if (version !== assetDetailVersion) return;
    $("asset-detail-feedback").textContent = error.message;
    const retry = element("button", "Reintentar", "text-button");
    retry.type = "button";
    retry.addEventListener("click", () => openAssetDetail(id));
    $("asset-detail-feedback").append(" ", retry);
  }
}
$("new-asset-button").addEventListener("click", () => {
  ++assetDetailVersion;
  $("asset-detail-panel").hidden = true;
  $("asset-list-panel").hidden = false;
  $("asset-create-panel").hidden = false;
  $("asset-create-form").elements.name.focus();
});
$("cancel-asset-create").addEventListener("click", () => { $("asset-create-panel").hidden = true; $("new-asset-button").focus(); });
$("asset-filter-form").addEventListener("submit", (event) => { event.preventDefault(); loadAssets(); });
$("clear-asset-filters").addEventListener("click", () => { $("asset-filter-form").reset(); loadAssets(); });
$("asset-back-button").addEventListener("click", () => {
  ++assetDetailVersion;
  $("asset-detail-panel").hidden = true;
  $("asset-list-panel").hidden = false;
  loadAssets(); $("asset-list-heading").scrollIntoView({block: "nearest"});
});
$("asset-create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const body = Object.fromEntries(new FormData(form));
  body.name = body.name.trim();
  if (!body.name) { message("Completá el nombre del activo con texto.", true); return; }
  body.description = body.description || null;
  const version = assetDetailVersion;
  busy(form, true, "Creando…"); message("");
  try {
    const asset = await api("/assets", "POST", body);
    if (version !== assetDetailVersion || !currentUser) return;
    form.reset();
    message("Activo creado correctamente.");
    await openAssetDetail(asset.id);
  } catch (error) { if (version === assetDetailVersion) message(error.message, true); }
  finally { busy(form, false); }
});
async function start() {
  $("app-view").hidden = true;
  $("login-view").hidden = true;
  try {
    const session = await api("/auth/session");
    if (session.user) showApplication(session);
    else showLogin();
  } catch (error) {
    showLogin();
    $("login-feedback").textContent = error.message;
  }
}
start();
