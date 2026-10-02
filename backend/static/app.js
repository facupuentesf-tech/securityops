"use strict";
const $ = (id) => document.getElementById(id);
const statuses = {open: "Abierto", investigating: "En investigación", resolved: "Resuelto"};
const severities = {low: "Baja", medium: "Media", high: "Alta", critical: "Crítica"};
const dateFormat = new Intl.DateTimeFormat("es", {dateStyle: "medium", timeStyle: "short"});
let selectedId = null;
let listVersion = 0;
let detailVersion = 0;

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
async function api(path, method = "GET", body) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? {} : {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error("No se pudo conectar con el servidor. Comprobá que esté iniciado y volvé a intentar.");
  }
  if (!response.ok) {
    if (response.status === 404) throw new Error("El incidente no existe. Volvé al listado y actualizalo.");
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
loadList();
