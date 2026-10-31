"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const number = value => Number(value).toLocaleString();
const percent = value => `${(value * 100).toFixed(1)}%`;
const title = value => String(value).replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
const escape = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[char]));
const labels = {disaster_type:"Disaster type", severity:"Severity", affected_people:"Affected people", road_access:"Road access", area_type:"Area type", available_shelter_places:"Available shelter places", available_response_teams:"Available response teams"};
const numericFields = ["severity", "affected_people", "available_shelter_places", "available_response_teams"];
let state = null;
let query = null;
let matches = [];
let selected = null;
let adaptedFrom = null;
let duplicate = null;
let busy = false;
let libraryError = false;

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method: "POST", headers: {"Content-Type":"application/json", "X-CBR-Request":"dashboard"}, body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "The request failed. Please try again.");
  return data;
}

function showError(error) {
  $("#global-error").textContent = error.message || String(error);
  $("#global-error").hidden = false;
}

function clearError() { $("#global-error").hidden = true; }

async function task(button, pendingLabel, action) {
  if (busy) return;
  busy = true;
  clearError();
  const original = button.textContent;
  button.textContent = pendingLabel;
  $$("button").forEach(item => { item.disabled = true; });
  $("#scenario-fields").disabled = true;
  $("#review-fields").disabled = true;
  $$("input[name=match]").forEach(input => { input.disabled = true; });
  $("#results-panel").setAttribute("aria-busy", "true");
  try { await action(); } catch (error) { showError(error); }
  finally {
    button.textContent = original;
    busy = false;
    if (!$("#scenario-fields")) return;
    $$("button").forEach(item => { item.disabled = false; });
    $("#scenario-fields").disabled = libraryError;
    $("#review-fields").disabled = Boolean(duplicate);
    $$("input[name=match]").forEach(input => { input.disabled = false; });
    $$(".ineligible").forEach(item => { item.disabled = true; });
    $("#results-panel").setAttribute("aria-busy", "false");
  }
}

function view(name) {
  const library = name === "library";
  $("#analyze-view").hidden = library;
  $("#library-view").hidden = !library;
  $("#nav-analyze").classList.toggle("active", !library);
  $("#nav-library").classList.toggle("active", library);
  $(library ? "#nav-library" : "#nav-analyze").setAttribute("aria-current", "page");
  $(library ? "#nav-analyze" : "#nav-library").removeAttribute("aria-current");
  $("#page-title").textContent = library ? "Case library" : "Analyze scenario";
  $("#load-example").hidden = library;
}

function invalidate() {
  query = null;
  matches = [];
  selected = null;
  duplicate = null;
  adaptedFrom = null;
  $("#review-panel").hidden = true;
  $("#results-caption").textContent = "";
  $("#results-body").innerHTML = '<div class="empty-state"><p>Select Find similar cases to compare.</p></div>';
}

function readProblem() {
  const problem = Object.fromEntries(new FormData($("#scenario-form")));
  numericFields.forEach(key => { problem[key] = Number(problem[key]); });
  return problem;
}

function sample() {
  if (busy || !state) return;
  const example = {disaster_type:"flood", severity:5, affected_people:1200, road_access:"restricted", area_type:"urban", available_shelter_places:700, available_response_teams:5};
  Object.entries(example).forEach(([key, value]) => { $("#scenario-form").elements[key].value = value; });
  invalidate();
  view("analyze");
  $("#scenario-form").requestSubmit();
}

function renderMatches() {
  const eligible = matches.find(match => match.score >= state.min_similarity);
  selected = eligible?.case.id || matches[0]?.case.id || null;
  $("#results-caption").textContent = `${matches.length} ${matches.length === 1 ? "match" : "matches"}`;
  const list = matches.length ? `<div class="match-list">${matches.map((match, i) => `<div class="match"><label><input type="radio" name="match" value="${escape(match.case.id)}" ${match.case.id === selected ? "checked" : ""}><span><span class="match-title">${escape(match.case.id)}${i === 0 ? " · Closest match" : ""}</span><span class="match-meta">Severity ${match.case.problem.severity} · ${number(match.case.problem.affected_people)} people · ${escape(title(match.case.problem.area_type))}</span></span></label><div class="match-score"><strong>${percent(match.score)}</strong><small>${match.score >= state.min_similarity ? "Reusable" : "Below 65%"}</small></div></div>`).join("")}</div><div id="match-breakdown" class="breakdown"></div>` : '<div class="no-match"><p>No matching cases. Add a plan manually.</p></div>';
  $("#results-body").innerHTML = list + `<div class="result-actions">${matches.length ? '<button type="button" class="button primary" id="adapt-button">Use selected case</button>' : ""}<button type="button" class="text-button" id="manual-button">Add plan manually</button></div>${duplicate ? `<p class="result-note">Already saved as ${escape(duplicate)}.</p>` : ""}`;
  $$("input[name=match]").forEach(input => input.addEventListener("change", () => {
    selected = input.value;
    $("#review-panel").hidden = true;
    adaptedFrom = null;
    renderBreakdown();
  }));
  $("#manual-button").addEventListener("click", () => openReview(null));
  if (matches.length) {
    $("#adapt-button").addEventListener("click", () => task($("#adapt-button"), "Adapting…", async () => {
      const result = await api("/api/adapt", {problem:query, case_id:selected});
      openReview(result);
    }));
    renderBreakdown();
  }
}

function renderBreakdown() {
  const match = matches.find(item => item.case.id === selected);
  const button = $("#adapt-button");
  const weak = match.score < state.min_similarity;
  button.disabled = weak;
  button.classList.toggle("ineligible", weak);
  button.textContent = weak ? "Below reuse threshold" : "Use selected case";
  $("#match-breakdown").innerHTML = `<details><summary>Match details</summary><div class="table-wrap"><table><thead><tr><th>Feature</th><th>New</th><th>Stored</th><th>Weight</th><th>Similarity</th><th>Contribution</th></tr></thead><tbody>${match.features.map(feature => `<tr><td>${labels[feature.feature]}</td><td>${escape(query[feature.feature])}</td><td>${escape(match.case.problem[feature.feature])}</td><td>${percent(feature.weight)}</td><td>${percent(feature.similarity)}</td><td>${percent(feature.contribution)}</td></tr>`).join("")}</tbody></table></div><p class="field-hint">Similarity: ${percent(match.score)}. Reuse requires 65%. Resemblance, not success probability.</p></details>`;
}

function openReview(adaptation) {
  const form = $("#review-form");
  form.reset();
  adaptedFrom = adaptation ? selected : null;
  const plan = adaptation?.solution || {priority:"routine", shelter_places:0, response_teams:1, actions:[]};
  ["priority", "shelter_places", "response_teams"].forEach(key => { form.elements[key].value = plan[key]; });
  form.elements.shelter_places.max = query.affected_people;
  form.elements.actions.value = plan.actions.join("\n");
  $("#review-title").textContent = adaptation ? "Review plan" : "Add plan";
  $("#review-caption").textContent = adaptation ? `From ${adaptedFrom}` : "";
  $("#adaptation-details").innerHTML = adaptation ? `<div class="adaptation-note"><details><summary>Adaptation details</summary><ul>${adaptation.explanation.map(line => `<li>${escape(line)}</li>`).join("")}</ul></details></div>` : "";
  $("#review-feedback").hidden = true;
  $("#review-fields").disabled = Boolean(duplicate);
  if (duplicate) {
    $("#review-feedback").className = "feedback";
    $("#review-feedback").textContent = `Already saved as ${duplicate}. Duplicate saving is disabled.`;
    $("#review-feedback").hidden = false;
  }
  $("#review-panel").hidden = false;
  updateShortfalls();
  $("#review-panel").scrollIntoView({behavior:"instant", block:"nearest"});
}

function updateShortfalls() {
  if (!query) return;
  const form = $("#review-form");
  const shelterGap = Math.max(0, Number(form.elements.shelter_places.value) - query.available_shelter_places);
  const teamGap = Math.max(0, Number(form.elements.response_teams.value) - query.available_response_teams);
  $("#shortfalls").textContent = `Additional needed: ${number(shelterGap)} shelter places · ${number(teamGap)} response teams.`;
}

async function refresh() {
  state = await api("/api/state");
  $("#case-count").textContent = `(${state.cases.length})`;
  renderLibrary();
}

function renderLibrary() {
  if (!state) return;
  const search = $("#case-search").value.trim().toLowerCase();
  const filter = $("#case-filter").value;
  const cases = state.cases.filter(item => (!filter || item.problem.disaster_type === filter) && `${item.id} ${item.problem.disaster_type} ${item.outcome} ${item.source}`.toLowerCase().includes(search));
  $("#library-body").innerHTML = cases.length ? cases.map(item => `<tr><td><strong>${escape(item.id)}</strong></td><td>${escape(title(item.problem.disaster_type))}</td><td>${item.problem.severity} / 5</td><td>${number(item.problem.affected_people)}</td><td><span class="source-label">${item.source === "synthetic" ? "Synthetic example" : "Classroom review"}${item.reviewed ? " · Reviewed" : " · Unreviewed"}</span></td><td><button type="button" class="text-button" data-case="${escape(item.id)}">View case</button></td></tr>`).join("") : '<tr><td colspan="6" class="library-empty">No cases match your search. Try another term or disaster type.</td></tr>';
  $("#library-count").textContent = `${cases.length} of ${state.cases.length} cases`;
  $$("[data-case]").forEach(button => button.addEventListener("click", () => showCase(button.dataset.case)));
}

function showCase(id) {
  const item = state.cases.find(entry => entry.id === id);
  $("#case-dialog-title").textContent = item.id;
  const definition = (name, value) => `<div><dt>${escape(name)}</dt><dd>${escape(value)}</dd></div>`;
  $("#case-dialog-body").innerHTML = `<h3>Scenario</h3><dl class="detail-grid">${Object.entries(item.problem).map(([key, value]) => definition(labels[key], typeof value === "number" ? number(value) : title(value))).join("")}</dl><div class="detail-section"><h3>Stored solution</h3><dl class="detail-grid">${definition("Priority", title(item.solution.priority))}${definition("Total shelter places", number(item.solution.shelter_places))}${definition("Total response teams", number(item.solution.response_teams))}${definition("Reviewed", item.reviewed ? "Yes" : "No")}</dl><ul>${item.solution.actions.map(action => `<li>${escape(action)}</li>`).join("")}</ul></div><div class="detail-section"><h3>Outcome / review note</h3><p>${escape(item.outcome)}</p><dl class="detail-grid">${definition("Source", title(item.source))}${definition("Created", new Date(item.created_at).toLocaleString())}${definition("Adapted from", item.adapted_from || "Original case")}</dl></div>`;
  $("#case-dialog").showModal();
}

$("#nav-analyze").addEventListener("click", () => view("analyze"));
$("#nav-library").addEventListener("click", () => view("library"));
$("#load-example").addEventListener("click", sample);
$("#scenario-form").addEventListener("input", invalidate);
$("#scenario-form").addEventListener("submit", event => {
  event.preventDefault();
  const problem = readProblem();
  task($("#analyze-button"), "Finding similar cases…", async () => {
    const result = await api("/api/analyze", {problem});
    query = problem;
    matches = result.matches;
    duplicate = result.duplicate;
    $("#review-panel").hidden = true;
    renderMatches();
  });
});
$("#review-form").addEventListener("input", updateShortfalls);
$("#review-form").addEventListener("submit", event => {
  event.preventDefault();
  const form = $("#review-form");
  const actions = form.elements.actions.value.split("\n").map(line => line.trim()).filter(Boolean);
  if (actions.length < 1 || actions.length > 10 || actions.some(line => line.length > 300)) {
    showError(new Error("Enter 1–10 review actions, each up to 300 characters, on separate lines."));
    return;
  }
  const payload = {
    problem:query, adapted_from:adaptedFrom, reviewed:form.elements.reviewed.checked,
    outcome:form.elements.outcome.value.trim(),
    solution:{priority:form.elements.priority.value, shelter_places:Number(form.elements.shelter_places.value), response_teams:Number(form.elements.response_teams.value), actions}
  };
  task($("#retain-button"), "Saving reviewed case…", async () => {
    const saved = await api("/api/retain", payload);
    duplicate = saved.id;
    $("#review-feedback").className = "feedback success";
    $("#review-feedback").textContent = `Saved ${saved.id}.`;
    $("#review-feedback").hidden = false;

    await refresh();
  });
});
$("#case-search").addEventListener("input", renderLibrary);
$("#case-filter").addEventListener("change", renderLibrary);
$("#close-dialog").addEventListener("click", () => $("#case-dialog").close());
$("#stop-dashboard").addEventListener("click", () => task($("#stop-dashboard"), "Stopping…", async () => {
  await api("/api/shutdown", {});
  document.body.innerHTML = '<main><section class="panel"><div class="empty-state"><h1>Dashboard stopped</h1><p>Reopen Run Disaster DSS to start again.</p></div></section></main>';
}));

async function initialize() {
  try {
    await refresh();
    Object.entries(state.options).forEach(([name, values]) => {
      $$(`select[name="${name}"]`).forEach(select => {
        select.innerHTML = values.map(value => `<option value="${escape(value)}">${escape(title(value))}</option>`).join("");
      });
    });
    $("#case-filter").innerHTML += state.options.disaster_type.map(value => `<option value="${escape(value)}">${escape(title(value))}</option>`).join("");
    $("#scenario-fields").disabled = false;
  } catch (error) {
    libraryError = true;
    showError(error);
    $("#load-example").disabled = true;
  }
}
initialize();
