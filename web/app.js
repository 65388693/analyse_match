const dateInput = document.querySelector("#match-date");
const searchInput = document.querySelector("#search");
const countrySelect = document.querySelector("#country-filter");
const leagueSelect = document.querySelector("#league-filter");
const matchList = document.querySelector("#match-list");
const emptyState = document.querySelector("#empty-state");
const detailPanel = document.querySelector("#detail-panel");
const detailContent = document.querySelector("#detail-content");
const totalCount = document.querySelector("#total-count");
const listMeta = document.querySelector("#list-meta");
const workspaceTabs = [...document.querySelectorAll(".workspace-tab")];

function activateWorkspaceView(view, { updateHash = true, focusTab = false } = {}) {
  const validViews = new Set(["calendar", "picks", "performance"]);
  const selectedView = validViews.has(view) ? view : "calendar";
  workspaceTabs.forEach((tab) => {
    const selected = tab.dataset.view === selectedView;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focusTab) tab.focus();
  });
  document.querySelectorAll("[data-view-panel]").forEach((panel) => {
    const selected = panel.dataset.viewPanel === selectedView;
    panel.hidden = !selected;
    panel.classList.toggle("active", selected);
  });
  if (updateHash && window.location.hash !== `#${selectedView}`) {
    window.history.pushState(null, "", `#${selectedView}`);
  }
  if (selectedView === "performance") loadPredictionStats();
}

workspaceTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => activateWorkspaceView(tab.dataset.view));
  tab.addEventListener("keydown", (event) => {
    let nextIndex = index;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % workspaceTabs.length;
    else if (event.key === "ArrowLeft") nextIndex = (index - 1 + workspaceTabs.length) % workspaceTabs.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = workspaceTabs.length - 1;
    else return;
    event.preventDefault();
    activateWorkspaceView(workspaceTabs[nextIndex].dataset.view, { focusTab: true });
  });
});

const AUTO_REFRESH_MS = 120_000;
function loadFavoriteIds() {
  try {
    const stored = JSON.parse(localStorage.getItem("matchdesk-favorites") || "[]");
    return Array.isArray(stored) ? stored.map(String) : [];
  } catch (error) {
    return [];
  }
}

function loadAlertsEnabled() {
  try {
    return localStorage.getItem("matchdesk-alerts") === "true"
      && "Notification" in window
      && Notification.permission === "granted";
  } catch (error) {
    return false;
  }
}

const state = { matches: [], selectedId: null, status: "all", availability: "all", analysis: null, busy: false, batchBusy: false, batchResults: new Map(), odds: new Map(), oddsLoading: new Set(), dailyPicks: null, dailyPicksBusy: false, autoRefreshEnabled: false, autoRefreshTimer: null, autoRefreshBusy: false, favorites: new Set(loadFavoriteIds()), alertsEnabled: loadAlertsEnabled() };

function todayLocal() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statusKind(match) {
  const value = `${match.status || ""} ${match.status_display || ""}`.toLowerCase();
  if (match.is_live || /live|progress|half|playing/.test(value)) return "live";
  if (/finish|ended|full.?time|\bft\b|complete/.test(value)) return "finished";
  return "upcoming";
}

function statusText(match) {
  if (statusKind(match) === "live") return "EN DIRECT";
  if (statusKind(match) === "finished") return "TERMINÉ";
  return match.status_display || match.time || "À venir";
}

function teamBadge(name, logo, large = false) {
  const badge = el("span", large ? "hero-badge" : "team-badge", (name || "?").slice(0, 2).toUpperCase());
  if (logo) {
    const image = document.createElement("img");
    image.alt = "";
    image.loading = "lazy";
    image.src = logo;
    image.addEventListener("error", () => image.remove(), { once: true });
    badge.replaceChildren(image);
  }
  return badge;
}

function refreshFilters() {
  const countries = [...new Set(state.matches.map((match) => match.country))].sort((a, b) => a.localeCompare(b));
  const selectedCountry = countrySelect.value;
  countrySelect.replaceChildren(new Option("Tous les pays", ""));
  countries.forEach((country) => countrySelect.add(new Option(country, country)));
  countrySelect.value = countries.includes(selectedCountry) ? selectedCountry : "";

  const competitions = [...new Set(state.matches
    .filter((match) => !countrySelect.value || match.country === countrySelect.value)
    .map((match) => match.real_league_name))].sort((a, b) => a.localeCompare(b));
  const selectedLeague = leagueSelect.value;
  leagueSelect.replaceChildren(new Option("Toutes", ""));
  competitions.forEach((competition) => leagueSelect.add(new Option(competition, competition)));
  leagueSelect.value = competitions.includes(selectedLeague) ? selectedLeague : "";
}

function updateStatusCounts() {
  const counts = { all: state.matches.length, live: 0, upcoming: 0, finished: 0 };
  state.matches.forEach((match) => counts[statusKind(match)]++);
  document.querySelectorAll(".status-tab").forEach((button) => {
    const count = counts[button.dataset.status];
    const countNode = button.querySelector("span:not(.tab-live-dot)");
    if (countNode) countNode.textContent = count;
  });
  totalCount.textContent = state.matches.length;
  document.querySelector("#coverage-all").textContent = state.matches.length;
  document.querySelector("#coverage-analyzable").textContent = state.matches.filter((match) => match.analysis_league_key).length;
  document.querySelector("#coverage-cache").textContent = state.matches.filter((match) => match.cache_ready).length;
  document.querySelector("#coverage-unmapped").textContent = state.matches.filter((match) => !match.analysis_league_key).length;
  document.querySelector("#coverage-favorites").textContent = state.matches.filter(
    (match) => state.favorites.has(String(match.source_match_id))
  ).length;
}

function applyMatches(data, preserveSelection = false, notifyEvents = false) {
  const previousMatches = state.matches;
  const hadSelection = preserveSelection && state.matches.some(
    (match) => String(match.source_match_id) === String(state.selectedId)
  );
  if (notifyEvents) notifyFavoriteChanges(previousMatches, data.matches);
  state.matches = data.matches;
  refreshFilters();
  updateStatusCounts();
  renderMatches();

  if (hadSelection) {
    const selected = state.matches.find(
      (match) => String(match.source_match_id) === String(state.selectedId)
    );
    if (selected && detailPanel.classList.contains("open")) renderDetail(selected);
  }
}

function notifyFavoriteChanges(previousMatches, updatedMatches) {
  if (!state.alertsEnabled || !window.Notification || Notification.permission !== "granted") return;
  const oldMatches = new Map(
    previousMatches.map((match) => [String(match.source_match_id), match])
  );
  for (const match of updatedMatches) {
    const matchId = String(match.source_match_id);
    const previous = oldMatches.get(matchId);
    if (!previous || !state.favorites.has(matchId)) continue;
    const matchName = `${match.home_team} - ${match.away_team}`;
    if (previous.score && match.score && previous.score !== match.score) {
      new Notification(`But · ${matchName}`, {
        body: `Nouveau score : ${match.score} (${match.status_display || "en direct"})`,
        tag: `match-${matchId}-score-${match.score}`,
      });
    } else if (statusKind(previous) !== "live" && statusKind(match) === "live") {
      new Notification(`Coup d'envoi · ${matchName}`, {
        body: `Le match est en direct (${match.status_display || "en direct"}).`,
        tag: `match-${matchId}-live`,
      });
    } else if (statusKind(previous) !== "finished" && statusKind(match) === "finished") {
      new Notification(`Match terminé · ${matchName}`, {
        body: `Score final : ${match.score || "disponible dans Match Desk"}`,
        tag: `match-${matchId}-finished`,
      });
    }
  }
}

function toggleFavorite(matchId) {
  const key = String(matchId);
  if (state.favorites.has(key)) state.favorites.delete(key);
  else state.favorites.add(key);
  try {
    localStorage.setItem("matchdesk-favorites", JSON.stringify([...state.favorites]));
  } catch (error) {
    console.warn("Impossible de sauvegarder les favoris sur cet appareil.");
  }
  updateStatusCounts();
  renderMatches();
}

function updateNotificationControls() {
  const button = document.querySelector("#notifications-toggle");
  button.setAttribute("aria-pressed", String(state.alertsEnabled));
  document.querySelector("#notifications-label").textContent = state.alertsEnabled
    ? "ALERTES ON"
    : "ALERTES OFF";
}

async function toggleFavoriteNotifications() {
  const status = document.querySelector("#notifications-status");
  if (!state.favorites.size && !state.alertsEnabled) {
    status.textContent = "Ajoute un favori d'abord";
    return;
  }
  if (state.alertsEnabled) {
    state.alertsEnabled = false;
    localStorage.setItem("matchdesk-alerts", "false");
    status.textContent = "Désactivées";
    updateNotificationControls();
    return;
  }
  if (!("Notification" in window)) {
    status.textContent = "Notifications non prises en charge";
    return;
  }
  try {
    const permission = Notification.permission === "default"
      ? await Notification.requestPermission()
      : Notification.permission;
    state.alertsEnabled = permission === "granted";
    localStorage.setItem("matchdesk-alerts", String(state.alertsEnabled));
    status.textContent = state.alertsEnabled ? "Favoris surveillés" : "Permission refusée";
  } catch (error) {
    state.alertsEnabled = false;
    status.textContent = "Autorisation indisponible";
  }
  updateNotificationControls();
}

function setAutoRefreshStatus(message) {
  document.querySelector("#auto-refresh-status").textContent = message;
}

function syncAutoRefreshTimer(refreshNow = false) {
  if (state.autoRefreshTimer !== null) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  if (!state.autoRefreshEnabled) {
    setAutoRefreshStatus("En veille");
    return;
  }
  if (state.status !== "live") {
    setAutoRefreshStatus("Actif dans « En direct »");
    return;
  }
  if (document.hidden) {
    setAutoRefreshStatus("En pause · onglet masqué");
    return;
  }

  setAutoRefreshStatus("Actif · intervalle 2 min");
  if (refreshNow) refreshLiveCalendar();
  state.autoRefreshTimer = setInterval(refreshLiveCalendar, AUTO_REFRESH_MS);
}

async function refreshLiveCalendar() {
  if (state.autoRefreshBusy || document.hidden || state.status !== "live") return;
  state.autoRefreshBusy = true;
  setAutoRefreshStatus("Mise à jour en cours…");
  try {
    const response = await fetch(
      `/api/matches?date=${encodeURIComponent(dateInput.value)}&refresh=1`
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Échec de l'actualisation");
    applyMatches(data, true, true);
    const time = new Date().toLocaleTimeString("fr-FR", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    setAutoRefreshStatus(`Mis à jour ${time} · toutes les 2 min`);
  } catch (error) {
    setAutoRefreshStatus("Échec · nouvel essai dans 2 min");
  } finally {
    state.autoRefreshBusy = false;
  }
}

function filteredMatches() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  return state.matches.filter((match) => {
    const searchable = `${match.home_team} ${match.away_team} ${match.country} ${match.real_league_name}`.toLocaleLowerCase();
    return (!query || searchable.includes(query))
      && (!countrySelect.value || match.country === countrySelect.value)
      && (!leagueSelect.value || match.real_league_name === leagueSelect.value)
      && (state.availability === "all"
        || (state.availability === "analyzable" && Boolean(match.analysis_league_key))
        || (state.availability === "cache" && Boolean(match.cache_ready))
        || (state.availability === "unmapped" && !match.analysis_league_key)
        || (state.availability === "favorites" && state.favorites.has(String(match.source_match_id))))
      && (state.status === "all" || statusKind(match) === state.status);
  });
}

function makeLeagueHeading(match, count) {
  const heading = el("div", "league-heading");
  heading.append(el("span", "league-count", count));
  heading.append(el("span", "", match.real_league_name));
  heading.append(el("span", "league-country", match.country));
  return heading;
}

function makeFixture(match, index) {
  const item = el("div", "fixture-item");
  const button = el("button", `fixture-row${String(match.source_match_id) === String(state.selectedId) ? " selected" : ""}`);
  button.type = "button";
  button.style.animationDelay = `${Math.min(index % 12, 8) * 18}ms`;
  button.setAttribute("aria-label", `${match.home_team} contre ${match.away_team}, ${match.real_league_name}`);

  button.append(el("span", "fixture-time", match.time || "--:--"));
  const teams = el("span", "fixture-teams");
  for (const [name, logo] of [[match.home_team, match.home_logo], [match.away_team, match.away_logo]]) {
    const team = el("span", "fixture-team");
    team.append(teamBadge(name, logo), el("span", "", name));
    teams.append(team);
  }
  button.append(teams);
  button.append(el("span", "fixture-score", match.score || "vs"));
  const coverageClass = match.cache_ready ? " cache-ready" : match.analysis_league_key ? " covered" : " unsupported";
  const stateClass = `${statusKind(match) === "live" ? "fixture-state live" : "fixture-state"}${coverageClass}`;
  const cachedAnalysis = state.batchResults.has(String(match.source_match_id));
  const statusNode = el("span", stateClass, cachedAnalysis ? "ANALYSÉ · CACHE" : statusText(match));
  statusNode.title = match.cache_ready
    ? "Profils des deux équipes déjà en cache : analyse possible sans nouvel appel API"
    : match.analysis_league_key
      ? "Ligue reconnue; les profils d'équipe pourront nécessiter des appels API à la première analyse"
      : "Compétition non reliée aux statistiques du modèle";
  statusNode.setAttribute("aria-label", `${statusText(match)}. ${statusNode.title}`);
  button.append(statusNode);
  button.addEventListener("click", () => selectMatch(match));
  const matchId = String(match.source_match_id);
  const isFavorite = state.favorites.has(matchId);
  const favorite = el("button", `favorite-toggle${isFavorite ? " is-favorite" : ""}`, isFavorite ? "★" : "☆");
  favorite.type = "button";
  favorite.setAttribute("aria-pressed", String(isFavorite));
  favorite.setAttribute("aria-label", isFavorite ? "Retirer des favoris" : "Ajouter aux favoris");
  favorite.title = favorite.getAttribute("aria-label");
  favorite.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleFavorite(matchId);
  });
  item.append(button, favorite);
  return item;
}

function renderMatches() {
  const matches = filteredMatches();
  matchList.replaceChildren();
  emptyState.hidden = matches.length !== 0;
  matchList.hidden = matches.length === 0;
  listMeta.textContent = `${matches.length} rencontre${matches.length === 1 ? "" : "s"}`;
  document.querySelector("#list-title").textContent = state.status === "all" ? "RENCONTRES" : state.status.toUpperCase();

  let previousGroup = "";
  const leagueCounts = new Map();
  matches.forEach((match) => {
    const group = `${match.country}\u0000${match.real_league_name}`;
    leagueCounts.set(group, (leagueCounts.get(group) || 0) + 1);
  });
  matches.forEach((match, index) => {
    const group = `${match.country}\u0000${match.real_league_name}`;
    if (group !== previousGroup) {
      matchList.append(makeLeagueHeading(match, leagueCounts.get(group)));
      previousGroup = group;
    }
    matchList.append(makeFixture(match, index));
  });
}

function selectMatch(match) {
  state.selectedId = match.source_match_id;
  state.analysis = state.batchResults.get(String(match.source_match_id)) || null;
  state.busy = false;
  renderMatches();
  renderDetail(match);
  detailPanel.classList.add("open");
  loadMatchOdds(match);
}

function renderOdds(match) {
  const odds = state.odds.get(String(match.source_match_id));
  const section = el("section", "odds-panel");
  const heading = el("div", "odds-heading");
  heading.append(el("span", "results-section-title", "COTES 1X2 · THE ODDS API"));
  const refresh = el("button", "odds-refresh", state.oddsLoading.has(String(match.source_match_id)) ? "…" : "↻");
  refresh.type = "button";
  refresh.title = "Actualiser les cotes";
  refresh.setAttribute("aria-label", "Actualiser les cotes");
  refresh.disabled = state.oddsLoading.has(String(match.source_match_id));
  refresh.addEventListener("click", () => loadMatchOdds(match, true));
  heading.append(refresh);
  section.append(heading);

  if (state.oddsLoading.has(String(match.source_match_id))) {
    section.append(el("div", "market-unavailable", "Recherche des cotes actuelles…"));
    return section;
  }
  if (!odds) {
    section.append(el("div", "market-unavailable", "Chargement des cotes…"));
    return section;
  }
  if (!odds.available) {
    section.append(el("div", "market-unavailable", odds.reason || "Cotes indisponibles pour ce match."));
    return section;
  }

  const best = el("div", "odds-best-grid");
  for (const [side, label] of [["home", "1"], ["draw", "N"], ["away", "2"]]) {
    const value = odds.best?.[side];
    const tile = el("div", "odds-best-tile");
    tile.append(el("span", "", label), el("strong", "", value == null ? "—" : Number(value).toFixed(2)));
    best.append(tile);
  }
  section.append(best);

  const list = el("div", "odds-bookmakers");
  odds.bookmakers.forEach((bookmaker) => {
    const row = el("div", "odds-bookmaker-row");
    row.append(el("span", "", bookmaker.name));
    row.append(el("strong", "", [bookmaker.home, bookmaker.draw, bookmaker.away]
      .map((price) => price == null ? "—" : Number(price).toFixed(2))
      .join(" · ")));
    list.append(row);
  });
  section.append(list);
  return section;
}

async function loadMatchOdds(match, forceRefresh = false) {
  const matchId = String(match.source_match_id);
  if (state.oddsLoading.has(matchId) || (state.odds.has(matchId) && !forceRefresh)) return;
  state.oddsLoading.add(matchId);
  if (String(state.selectedId) === matchId) renderDetail(match);
  try {
    const response = await fetch(
      `/api/odds?date=${encodeURIComponent(match.match_date)}&match_id=${encodeURIComponent(matchId)}${forceRefresh ? "&refresh=1" : ""}`
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Échec de récupération des cotes");
    state.odds.set(matchId, result);
  } catch (error) {
    state.odds.set(matchId, { available: false, reason: error.message });
  } finally {
    state.oddsLoading.delete(matchId);
    if (String(state.selectedId) === matchId) renderDetail(match);
  }
}

function renderDetail(match, error = "") {
  detailContent.className = "detail-content";
  detailContent.replaceChildren();

  const league = el("div", "selected-league");
  league.append(el("span", "", match.country));
  league.append(el("div", "selected-competition", match.real_league_name));
  detailContent.append(league);

  const hero = el("div", "match-hero");
  for (const [name, logo] of [[match.home_team, match.home_logo], [match.away_team, match.away_logo]]) {
    const team = el("div", "hero-team");
    team.append(teamBadge(name, logo, true), el("span", "hero-team-name", name));
    hero.append(team);
    if (name === match.home_team) hero.append(el("span", "versus", "VS"));
  }
  detailContent.append(hero);

  const meta = el("div", "match-meta");
  meta.append(el("span", "", new Date(`${match.match_date}T00:00:00`).toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })));
  meta.append(el("span", "meta-separator", "·"));
  meta.append(el("span", "", match.score || statusText(match)));
  detailContent.append(meta);
  detailContent.append(renderOdds(match));

  if (match.analysis_league_key) {
    const analyze = el("button", "analysis-button");
    analyze.type = "button";
    analyze.disabled = state.busy;
    analyze.append(el("span", "", state.busy ? "CALCUL EN COURS…" : state.analysis ? "ACTUALISER L'ANALYSE" : "ANALYSER CE MATCH"));
    analyze.append(el("span", "arrow", "↗"));
    analyze.addEventListener("click", () => analyzeMatch(match, analyze));
    detailContent.append(analyze);
  } else {
    const warning = el("div", "coverage-warning", "Le match est visible dans le calendrier, mais cette compétition n'a pas de statistiques reliées au modèle pour produire une analyse fiable.");
    detailContent.append(warning);
  }

  if (error) detailContent.append(el("div", "analysis-error", error));
  if (state.analysis) detailContent.append(renderAnalysis(state.analysis));
}

function formatOdds(value) {
  return Number(value).toFixed(2);
}

function renderDailyPick(pick, combo = false) {
  const article = el("article", combo ? "daily-pick combo-pick" : "daily-pick");
  const top = el("div", "daily-pick-top");
  if (combo) {
    top.append(el("strong", "daily-pick-total-odds", `Cote ${formatOdds(pick.total_odds)}`));
    top.append(el("span", "daily-pick-probability", `Probabilité estimée ${percent(pick.estimated_probability)}`));
    article.append(top);
    const legs = el("ol", "daily-pick-legs");
    pick.legs.forEach((leg) => {
      const row = el("li", "daily-pick-leg");
      row.append(el("span", "", `${leg.home_team} - ${leg.away_team} · ${leg.label}`));
      row.append(el("strong", "", formatOdds(leg.odds)));
      legs.append(row);
    });
    article.append(legs);
    article.append(el("div", "daily-pick-meta", `${pick.legs.length} matchs distincts · rendement théorique estimé ${percent(pick.expected_return)}`));
    return article;
  }

  top.append(el("strong", "daily-pick-total-odds", formatOdds(pick.odds)));
  top.append(el("span", "daily-pick-probability", `Probabilité estimée ${percent(pick.probability)}`));
  article.append(top);
  article.append(el("div", "daily-pick-match", `${pick.home_team} - ${pick.away_team}`));
  article.append(el("div", "daily-pick-meta", `${pick.competition || "Compétition"} · ${pick.label} · ${pick.bookmaker} · Données ${pick.data_quality === "usable" ? "exploitables" : "limitées"}`));
  article.append(el("div", "daily-pick-meta", `Rendement théorique estimé ${percent(pick.expected_return)}`));
  return article;
}

function renderDailyPicks(data) {
  const panel = document.querySelector("#daily-picks-panel");
  panel.replaceChildren();
  panel.hidden = false;

  const heading = el("div", "daily-picks-heading");
  heading.append(el("div", "eyebrow", `SÉLECTIONS 1XBET · ${data.date || dateInput.value}`));
  const refresh = el("button", "odds-refresh", state.dailyPicksBusy ? "…" : "↻");
  refresh.type = "button";
  refresh.title = "Recalculer les propositions";
  refresh.setAttribute("aria-label", "Recalculer les propositions");
  refresh.disabled = state.dailyPicksBusy;
  refresh.addEventListener("click", generateDailyPicks);
  heading.append(refresh);
  panel.append(heading);

  const coverage = data.coverage || {};
  const coverageText = `${coverage.matches_with_1xbet_odds || 0} matchs avec cotes 1xBet · ${coverage.candidate_selections || 0} sélections évaluées · ${coverage.combo_eligible_selections || 0} admissibles aux combinés · ${data.matches_scanned || 0}/${data.matches_in_calendar || 0} rencontres examinées`;
  panel.append(el("div", "daily-picks-coverage", coverageText));
  if (data.tracking?.message || data.tracking?.available) {
    panel.append(el(
      "div",
      `daily-picks-tracking${data.tracking.available ? " is-saved" : " is-warning"}`,
      `${data.tracking.message}${data.tracking.available ? ` (${data.tracking.model_predictions} issues 1X2; ${data.tracking.simple_bets} simples proposés)` : ""}`,
    ));
  }

  if (data.singles?.length) {
    const section = el("section", "daily-picks-section");
    section.append(el("h2", "daily-picks-section-title", "Paris simples à considérer"));
    const list = el("div", "daily-picks-list");
    data.singles.forEach((pick) => list.append(renderDailyPick(pick)));
    section.append(list);
    panel.append(section);
  }

  const tierDetails = [
    ["grosse_cote", "Grosses cotes · 100+"],
    ["moyen", "Combinés moyens · 10 à 100"],
    ["prudent", "Combinés prudents · 2 à 10"],
  ];
  tierDetails.forEach(([key, title]) => {
    const combos = data.combos?.[key] || [];
    const section = el("section", "daily-picks-section");
    const sectionHeading = el("div", "daily-picks-section-heading");
    sectionHeading.append(el("h2", "daily-picks-section-title", title));
    sectionHeading.append(el("span", "daily-picks-count", `${combos.length}/5`));
    section.append(sectionHeading);
    if (combos.length) {
      const list = el("div", "daily-picks-list");
      combos.forEach((pick) => list.append(renderDailyPick(pick, true)));
      section.append(list);
    } else {
      section.append(el("div", "market-unavailable", "Aucun combiné ne remplit les critères avec les cotes 1xBet et les données actuellement disponibles."));
    }
    panel.append(section);
  });

  if (!data.singles?.length) {
    panel.append(el("div", "market-unavailable", data.empty_note || "Aucun pari simple ne remplit les critères aujourd'hui."));
  }
  panel.append(el("p", "daily-picks-disclaimer", data.method_note || "Estimations non garanties."));
}

async function generateDailyPicks() {
  if (state.dailyPicksBusy) return;
  state.dailyPicksBusy = true;
  const button = document.querySelector("#generate-daily-picks");
  const panel = document.querySelector("#daily-picks-panel");
  button.disabled = true;
  button.querySelector(".daily-picks-button-label").textContent = "ANALYSE EN COURS…";
  panel.hidden = false;
  panel.replaceChildren(el("div", "loading-screen", ""));
  const loader = panel.firstChild;
  loader.append(el("strong", "", "Analyse des matchs en cache et des cotes 1xBet"));
  loader.append(el("span", "", "Aucun profil manquant ne sera téléchargé pendant ce calcul."));
  try {
    const response = await fetch("/api/daily-picks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateInput.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "La génération des propositions a échoué.");
    state.dailyPicks = data;
    const picksCount = document.querySelector("#tab-picks-count");
    const singlesCount = data.singles?.length || 0;
    picksCount.textContent = singlesCount ? String(singlesCount) : "0";
    picksCount.hidden = false;
    renderDailyPicks(data);
  } catch (error) {
    panel.replaceChildren(el("div", "analysis-error", error.message));
  } finally {
    state.dailyPicksBusy = false;
    button.disabled = false;
    button.querySelector(".daily-picks-button-label").textContent = "PRONOSTICS DU JOUR";
    loadPredictionStats();
  }
}

async function loadPredictionStats() {
  const panel = document.querySelector("#prediction-performance");
  panel.hidden = false;
  panel.replaceChildren(el("div", "market-unavailable", "Chargement des résultats enregistrés…"));
  try {
    const response = await fetch("/api/prediction-stats");
    const stats = await response.json();
    if (!response.ok) throw new Error(stats.error || "Suivi indisponible");
    panel.replaceChildren();
    panel.hidden = false;
    panel.append(el("div", "results-section-title", "RÉSULTATS HISTORIQUES · MODÈLE 1X2"));

    const metrics = el("div", "prediction-performance-grid");
    const values = stats.settled_predictions
      ? [
          ["Échantillon réglé", `${stats.settled_predictions}`],
          ["Précision · meilleur 1X2", percent(stats.hit_rate)],
          ["Brier multiclasses · plus bas = mieux", Number(stats.brier_score).toFixed(3)],
          ["Log-loss · plus bas = mieux", Number(stats.log_loss).toFixed(3)],
          [`Réussite simples · ${stats.settled_simple_bets} réglés`, stats.simple_bet_hit_rate == null ? "—" : percent(stats.simple_bet_hit_rate)],
          [`Rendement simples · ${stats.settled_simple_bets} réglés`, stats.flat_stake_yield == null ? "—" : percent(stats.flat_stake_yield)],
          ["En attente du score", `${stats.pending_predictions}`],
        ]
      : [["Matchs évaluables", "Aucun"], ["En attente du score", `${stats.pending_predictions}`]];
    values.forEach(([label, value]) => {
      const metric = el("div", "prediction-performance-metric");
      metric.append(el("span", "", label), el("strong", "", value));
      metrics.append(metric);
    });
    panel.append(metrics);
    if (!stats.settled_predictions) {
      panel.append(el("div", "market-unavailable", "Les performances apparaîtront après l’enregistrement des pronostics puis le chargement des scores finaux dans le calendrier."));
    }
    const calibration = (stats.calibration_bins || []).filter((item) => item.count > 0);
    if (calibration.length) {
      const calibrationList = el("div", "calibration-list");
      calibrationList.append(el("div", "calibration-title", "Calibration · probabilité prévue / fréquence observée"));
      calibration.forEach((item) => {
        calibrationList.append(el(
          "div",
          "calibration-row",
          `${item.range} · ${percent(item.mean_probability)} / ${percent(item.observed_rate)} · n=${item.count}`,
        ));
      });
      panel.append(calibrationList);
    }
    panel.append(el("p", "prediction-performance-note", stats.warning));
  } catch (error) {
    panel.replaceChildren(el("div", "analysis-error", `Impossible de charger les performances : ${error.message}`));
  }
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function addProbabilityRow(container, label, value) {
  const row = el("div", "probability-row");
  row.append(el("span", "", label));
  const track = el("div", "prob-track");
  const fill = el("div", "prob-fill");
  fill.style.width = `${Math.max(0, Math.min(100, Number(value || 0) * 100))}%`;
  track.append(fill);
  row.append(track, el("strong", "", percent(value)));
  container.append(row);
}

function collectBetCandidates(result) {
  const markets = result.markets;
  const candidates = [];
  const add = (key, label, probability, kind = "event") => {
    if (typeof probability === "number" && Number.isFinite(probability) && probability > 0 && probability < 1) {
      candidates.push({ key, label, probability, kind });
    }
  };

  add("home_win", `Victoire ${result.match.home_team}`, markets["1X2"].dom);
  add("draw", "Match nul", markets["1X2"].nul);
  add("away_win", `Victoire ${result.match.away_team}`, markets["1X2"].ext);
  add("double_1x", "Double chance 1X", markets.double_chance?.["1X"]);
  add("double_12", "Double chance 12", markets.double_chance?.["12"]);
  add("double_x2", "Double chance X2", markets.double_chance?.["X2"]);

  for (const line of [1.5, 2.5, 3.5]) {
    const key = String(line).replace(".", "_");
    add(`over_${key}`, `Plus de ${String(line).replace(".", ",")} buts`, markets.total_buts?.[`over_${key}`]);
    add(`under_${key}`, `Moins de ${String(line).replace(".", ",")} buts`, markets.total_buts?.[`under_${key}`]);
  }
  add("btts_yes", "Les deux équipes marquent · oui", markets.btts?.oui);
  add("btts_no", "Les deux équipes marquent · non", markets.btts?.non);
  for (const [side, team] of [["dom", result.match.home_team], ["ext", result.match.away_team]]) {
    const teamMarkets = markets.buts_par_equipe?.[side] || {};
    const atLeastOne = 1 - Number(teamMarkets["0"] || 0);
    const atLeastTwo = Number(teamMarkets["2"] || 0) + Number(teamMarkets["3+"] || 0);
    add(`${side}_team_1plus`, `${team} · au moins 1 but`, atLeastOne);
    add(`${side}_team_2plus`, `${team} · au moins 2 buts`, atLeastTwo);
  }
  add("first_scorer_home", `${result.match.home_team} marque en premier`, result.extended.first_scorer?.dom);
  add("first_scorer_away", `${result.match.away_team} marque en premier`, result.extended.first_scorer?.ext);
  add("first_scorer_none", "Aucun but", result.extended.first_scorer?.no_goal);
  return candidates.sort((first, second) => second.probability - first.probability);
}

function readDecimalOdds(value) {
  const odds = Number(String(value || "").trim().replace(",", "."));
  return Number.isFinite(odds) && odds > 1 ? odds : null;
}

function updateBetCandidate(row, probability, input) {
  const odds = readDecimalOdds(input.value);
  const fair = row.querySelector(".bet-fair-odds");
  const edge = row.querySelector(".bet-edge");
  const returnValue = row.querySelector(".bet-return");
  if (!odds) {
    fair.textContent = `Cote d'équilibre ${ (1 / probability).toFixed(2) }`;
    edge.textContent = "Saisis une cote";
    edge.className = "bet-edge";
    returnValue.textContent = "Rendement non calculé";
    return;
  }

  const impliedProbability = 1 / odds;
  const edgePoints = (probability - impliedProbability) * 100;
  const expectedReturn = (probability * odds - 1) * 100;
  fair.textContent = `Cote d'équilibre ${ (1 / probability).toFixed(2) }`;
  edge.textContent = `${edgePoints >= 0 ? "+" : ""}${edgePoints.toFixed(1)} pts vs cote`;
  edge.className = `bet-edge ${edgePoints > 0 ? "positive" : "negative"}`;
  returnValue.textContent = `Rendement théorique / unité ${expectedReturn >= 0 ? "+" : ""}${expectedReturn.toFixed(1)}%`;
}

function renderBettingAssistant(result) {
  const assistant = el("details", "bet-assistant");
  const summary = el("summary", "bet-assistant-summary");
  summary.append(el("span", "assistant-mark", "∑"), el("span", "", "Assistant de décision"), el("span", "assistant-summary-note", "Calcul local · sans garantie"));
  assistant.append(summary);

  const body = el("div", "bet-assistant-body");
  const candidates = collectBetCandidates(result);
  body.append(el("p", "assistant-disclaimer", "Classement selon la fréquence de succès estimée par le modèle. Une forte probabilité ne signifie pas un pari rentable; le rendement exige la cote exacte du bookmaker."));

  const quality = result.data_quality?.label === "usable"
    ? "Historique disponible; modèle non validé comme avantage bookmaker."
    : "Données limitées pour ce match : traite les probabilités avec prudence.";
  body.append(el("div", `assistant-quality ${result.data_quality?.label || "limited"}`, quality));

  const topSection = el("div", "assistant-top-picks");
  topSection.append(el("div", "results-section-title", "PLUS HAUTES PROBABILITÉS ESTIMÉES"));
  const topPicks = el("div", "assistant-picks");
  candidates.slice(0, 3).forEach((candidate, index) => {
    const pick = el("div", "assistant-pick");
    pick.append(el("span", "assistant-pick-rank", `0${index + 1}`), el("span", "assistant-pick-name", candidate.label), el("strong", "assistant-pick-probability", percent(candidate.probability)));
    topPicks.append(pick);
  });
  topSection.append(topPicks);
  body.append(topSection);

  body.append(el("div", "results-section-title", "COMPARER À TES COTES DÉCIMALES"));
  const marketRows = el("div", "assistant-market-list");
  const storageKey = `matchdesk-odds-${result.match.date}-${result.match.source_match_id}`;
  let savedOdds = {};
  try {
    savedOdds = JSON.parse(localStorage.getItem(storageKey) || "{}");
  } catch (error) {
    savedOdds = {};
  }

  candidates.forEach((candidate) => {
    const row = el("div", "assistant-market-row");
    const information = el("div", "assistant-market-info");
    information.append(el("span", "assistant-market-name", candidate.label), el("strong", "assistant-market-probability", percent(candidate.probability)));
    const oddsInput = document.createElement("input");
    oddsInput.className = "assistant-odds-input";
    oddsInput.type = "text";
    oddsInput.inputMode = "decimal";
    oddsInput.placeholder = "Cote";
    oddsInput.setAttribute("aria-label", `Cote bookmaker pour ${candidate.label}`);
    oddsInput.value = savedOdds[candidate.key] || "";
    const valuation = el("div", "assistant-market-valuation");
    const fair = el("span", "bet-fair-odds", "");
    const edge = el("span", "bet-edge", "");
    const expectedReturn = el("span", "bet-return", "");
    valuation.append(fair, edge, expectedReturn);
    row.append(information, oddsInput, valuation);
    updateBetCandidate(row, candidate.probability, oddsInput);
    oddsInput.addEventListener("input", () => {
      savedOdds[candidate.key] = oddsInput.value;
      try {
        localStorage.setItem(storageKey, JSON.stringify(savedOdds));
      } catch (error) {
        console.warn("Impossible de sauvegarder les cotes saisies.");
      }
      updateBetCandidate(row, candidate.probability, oddsInput);
    });
    marketRows.append(row);
  });
  body.append(marketRows);
  body.append(el("p", "assistant-risk-note", "Le calcul n'intègre ni marge complète du bookmaker, ni évolution des cotes, ni toutes les incertitudes du modèle. Il n'indique pas de mise à engager. Si l'avantage estimé est nul ou négatif, l'assistant n'identifie pas de valeur théorique."));
  assistant.append(body);
  return assistant;
}

function renderAnalysis(result) {
  const section = el("section", "analysis-results");
  const markets = result.markets;
  const fixture = result.match;
  section.append(el("div", "results-kicker", "MODÈLE DE POISSON"));
  section.append(el("h2", "results-title", "Probabilités"));

  const oneXTwo = markets["1X2"];
  addProbabilityRow(section, "1", oneXTwo.dom);
  addProbabilityRow(section, "N", oneXTwo.nul);
  addProbabilityRow(section, "2", oneXTwo.ext);

  const metrics = el("div", "metrics-grid");
  const homeMetric = el("div", "metric");
  homeMetric.append(el("span", "metric-label", `BUTS ATTENDUS · ${fixture.home_team}`), el("strong", "metric-value", Number(result.lambda_home).toFixed(2)));
  const awayMetric = el("div", "metric");
  awayMetric.append(el("span", "metric-label", `BUTS ATTENDUS · ${fixture.away_team}`), el("strong", "metric-value", Number(result.lambda_away).toFixed(2)));
  metrics.append(homeMetric, awayMetric);
  section.append(metrics);

  const scores = el("div", "results-section");
  scores.append(el("div", "results-section-title", "SCORES LES PLUS PROBABLES"));
  const chips = el("div", "score-chips");
  markets.score_exact.slice(0, 4).forEach((score) => {
    const chip = el("div", "score-chip", score.score);
    chip.append(el("span", "", percent(score.prob)));
    chips.append(chip);
  });
  scores.append(chips);
  section.append(scores);

  const totals = el("div", "results-section");
  totals.append(el("div", "results-section-title", "BONS REPÈRES"));
  [
    ["Plus de 2,5 buts", markets.total_buts.over_2_5],
    ["Les deux équipes marquent", markets.btts.oui],
    ["But en première période", result.extended.ht_total_buts.ht_over_0_5],
  ].forEach(([label, value]) => {
    const line = el("div", "market-line");
    line.append(el("span", "", label), el("strong", "", percent(value)));
    totals.append(line);
  });
  section.append(totals);

  const forms = result.teams;
  if (forms.home || forms.away) {
    const formSection = el("div", "results-section");
    formSection.append(el("div", "results-section-title", "FORME RÉCENTE"));
    for (const team of [forms.home, forms.away]) {
      if (!team) continue;
      const line = el("div", "market-line");
      const label = team.form ? `${team.team} · ${team.form}` : team.team;
      line.append(el("span", "", label), el("strong", "", team.xg == null ? "xG —" : `xG ${Number(team.xg).toFixed(2)}`));
      formSection.append(line);
    }
    section.append(formSection);
  }

  if (result.explanations?.["1X2"]) section.append(el("div", "explanation", result.explanations["1X2"]));

  const exactTotals = el("div", "results-section");
  exactTotals.append(el("div", "results-section-title", "TOTAL EXACT DE BUTS"));
  const totalTiles = el("div", "market-grid");
  Object.entries(markets.total_exact || {}).forEach(([key, value]) => {
    const tile = el("div", "market-tile");
    tile.append(el("span", "", key.replace("exact_", "").replace("_", ",") + (key.endsWith("+") ? " buts ou plus" : " but(s)")), el("strong", "", percent(value)));
    totalTiles.append(tile);
  });
  exactTotals.append(totalTiles);
  section.append(exactTotals);

  const perTeam = el("div", "results-section");
  perTeam.append(el("div", "results-section-title", "TOTAL BUTS PAR ÉQUIPE"));
  const teamTiles = el("div", "market-grid");
  for (const [side, name] of [["dom", fixture.home_team], ["ext", fixture.away_team]]) {
    Object.entries(markets.buts_par_equipe?.[side] || {}).forEach(([goals, value]) => {
      const tile = el("div", "market-tile");
      tile.append(el("span", "", `${name} · ${goals} but(s)`), el("strong", "", percent(value)));
      teamTiles.append(tile);
    });
  }
  perTeam.append(teamTiles);
  section.append(perTeam);

  const specials = el("div", "results-section");
  specials.append(el("div", "results-section-title", "MARCHÉS 1X2 & TOTALS"));
  const specialTiles = el("div", "market-grid");
  [
    ["Double chance 1X", markets.double_chance?.["1X"]],
    ["Double chance 12", markets.double_chance?.["12"]],
    ["Double chance X2", markets.double_chance?.["X2"]],
    ["DNB domicile · hors nul", markets.draw_no_bet?.dom],
    ["DNB extérieur · hors nul", markets.draw_no_bet?.ext],
    ["Total impair", markets.total_parity?.odd],
    ["Total pair", markets.total_parity?.even],
    ["Domicile gagne sans encaisser", markets.win_to_nil?.dom_win_to_nil],
    ["Extérieur gagne sans encaisser", markets.win_to_nil?.ext_win_to_nil],
    ["Domicile clean sheet", markets.clean_sheet?.dom_clean_sheet],
    ["Extérieur clean sheet", markets.clean_sheet?.ext_clean_sheet],
  ].forEach(([label, value]) => {
    if (value == null) return;
    const tile = el("div", "market-tile");
    tile.append(el("span", "", label), el("strong", "", percent(value)));
    specialTiles.append(tile);
  });
  Object.entries(markets.winning_margin || {}).forEach(([key, value]) => {
    const tile = el("div", "market-tile");
    const side = key.startsWith("dom") ? fixture.home_team : fixture.away_team;
    const margin = key.endsWith("3_plus") ? "3+ buts" : `${key.slice(-1)} but${key.endsWith("2") ? "s" : ""}`;
    tile.append(el("span", "", `${side} gagne par ${margin}`), el("strong", "", percent(value)));
    specialTiles.append(tile);
  });
  specials.append(specialTiles);
  section.append(specials);

  const handicaps = el("div", "results-section");
  handicaps.append(el("div", "results-section-title", "HANDICAPS ASIATIQUES · GAIN / REMBOURSEMENT / PERTE"));
  Object.entries(markets.handicap_asiatique || {}).forEach(([line, probabilities]) => {
    const row = el("div", "market-line");
    const push = probabilities.push == null ? "—" : percent(probabilities.push);
    row.append(el("span", "", `${line.replace("ah_", "")} · ${percent(probabilities.win)} / ${push} / ${percent(probabilities.lose)}`));
    handicaps.append(row);
  });
  section.append(handicaps);

  const halves = result.extended || {};
  const halfSection = el("div", "results-section");
  halfSection.append(el("div", "results-section-title", "MI-TEMPS & SECONDE PÉRIODE"));
  const halfTiles = el("div", "market-grid");
  const halfOneXTwo = halves.ht_1x2 || {};
  [["1re MT · 1", halfOneXTwo.dom], ["1re MT · N", halfOneXTwo.nul], ["1re MT · 2", halfOneXTwo.ext], ["1re MT · +0,5", halves.ht_total_buts?.ht_over_0_5]].forEach(([label, value]) => {
    if (value == null) return;
    const tile = el("div", "market-tile");
    tile.append(el("span", "", label), el("strong", "", percent(value)));
    halfTiles.append(tile);
  });
  halfSection.append(halfTiles);
  const secondHalf = halves.second_half_1x2 || {};
  const secondHalfTiles = el("div", "market-grid");
  [["2e MT · 1", secondHalf.dom], ["2e MT · N", secondHalf.nul], ["2e MT · 2", secondHalf.ext], ["2e MT · +0,5", halves.second_half_total_buts?.ht_over_0_5], ["Marque dans les 2 MT · dom.", halves.team_to_score_both_halves?.dom], ["Marque dans les 2 MT · ext.", halves.team_to_score_both_halves?.ext]].forEach(([label, value]) => {
    if (value == null) return;
    const tile = el("div", "market-tile");
    tile.append(el("span", "", label), el("strong", "", percent(value)));
    secondHalfTiles.append(tile);
  });
  halfSection.append(secondHalfTiles);
  for (const [title, key] of [["Scores exacts à la pause", "first_half_score_exact"], ["Scores exacts en 2e période", "second_half_score_exact"]]) {
    const scoreBox = el("div", "results-section");
    scoreBox.append(el("div", "results-section-title", title.toUpperCase()));
    const chipsBox = el("div", "score-chips");
    (halves.goals_by_period?.[key] || []).slice(0, 5).forEach((score) => {
      const chip = el("div", "score-chip", score.score);
      chip.append(el("span", "", percent(score.prob)));
      chipsBox.append(chip);
    });
    scoreBox.append(chipsBox);
    halfSection.append(scoreBox);
  }
  section.append(halfSection);

  const timing = result.goal_timing?.combined;
  const timingSection = el("div", "results-section");
  timingSection.append(el("div", "results-section-title", "FRÉQUENCE HISTORIQUE DU PREMIER BUT"));
  if (timing?.available) {
    timingSection.append(el("div", "market-line", `${timing.events} buts d'ouverture observés dans les profils d'équipe`));
    const chart = el("div", "timing-bar");
    const maxProbability = Math.max(...timing.intervals.map((item) => item.probability), 0.01);
    timing.intervals.forEach((item) => {
      const column = el("div", "timing-column");
      const bar = document.createElement("i");
      bar.style.height = `${Math.max(4, item.probability / maxProbability * 66)}px`;
      column.append(bar, el("b", "", percent(item.probability)), el("span", "", item.interval));
      chart.append(column);
    });
    timingSection.append(chart);
  } else {
    timingSection.append(el("div", "market-unavailable", "Aucun historique temporel exploitable pour ces équipes."));
  }
  section.append(timingSection);

  const extras = el("div", "results-section");
  extras.append(el("div", "results-section-title", "MARCHÉS CONTEXTUELS"));
  const extraTiles = el("div", "market-grid");
  const corners = halves.corners || {};
  if (corners.corners_total != null) {
    [[`Corners attendus · ${fixture.home_team}`, corners.corners_dom], [`Corners attendus · ${fixture.away_team}`, corners.corners_ext], ["Corners attendus · total", corners.corners_total]].forEach(([label, value]) => {
      const tile = el("div", "market-tile");
      tile.append(el("span", "", label), el("strong", "", Number(value).toFixed(1)));
      extraTiles.append(tile);
    });
  }
  Object.entries(corners).filter(([key]) => key.startsWith("over_")).forEach(([key, value]) => {
    const tile = el("div", "market-tile");
    tile.append(el("span", "", `Corners ${key.replace("over_", "+ ").replace("_", ",")}`), el("strong", "", percent(value)));
    extraTiles.append(tile);
  });
  Object.entries(corners).filter(([key]) => key.startsWith("under_")).forEach(([key, value]) => {
    const tile = el("div", "market-tile");
    tile.append(el("span", "", `Corners - ${key.replace("under_", "").replace("_", ",")}`), el("strong", "", percent(value)));
    extraTiles.append(tile);
  });
  Object.entries(halves.cards || {}).forEach(([key, value]) => {
    if (typeof value !== "number") return;
    const tile = el("div", "market-tile");
    tile.append(el("span", "", `Cartons · ${key.replaceAll("_", " ")}`), el("strong", "", percent(value)));
    extraTiles.append(tile);
  });
  extras.append(extraTiles);
  if (corners.source === "generic_fallback" || halves.cards?.source === "generic_fallback") {
    extras.append(el("div", "market-unavailable", "Les probabilités de corners ou cartons concernées reposent sur des valeurs génériques de repli, pas sur une mesure vérifiée pour cette rencontre."));
  }
  extras.append(el("div", "market-unavailable", result.penalties?.known_event_score
    ? `Score de séance de tirs au but observé : ${result.penalties.known_event_score}. Aucune probabilité pré-match de penalty n'est disponible.`
    : "Penalties / tirs au but : les sources ne fournissent pas d'historique prédictif fiable; aucun pourcentage n'est inventé."));
  section.append(extras);

  const modelNote = el("div", "model-note");
  const history = result.model?.team_history_matches || {};
  const firstHalfNote = result.model?.half_time_basis === "football_charts_model" ? "source statistique" : "approximation à 40% des buts attendus";
  modelNote.textContent = `${result.model?.name || "Modèle probabiliste"}. Historique équipe : ${history.home ?? "?"} / ${history.away ?? "?"} matchs. Mi-temps : ${firstHalfNote}. ${result.data_quality?.note || ""} Les probabilités ne sont pas des cotes bookmakers.`;
  section.append(modelNote);
  section.append(renderBettingAssistant(result));
  return section;
}

async function analyzeCachedMatches() {
  const button = document.querySelector("#analyze-cached");
  const resultBox = document.querySelector("#batch-result");
  if (state.batchBusy) return;
  state.batchBusy = true;
  button.disabled = true;
  button.querySelector(".batch-action-label").textContent = "CALCUL LOCAL…";
  resultBox.hidden = true;
  try {
    const response = await fetch("/api/analyze-cached", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateInput.value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Le calcul local a échoué.");
    state.batchResults = new Map(data.results.map((item) => [String(item.match.source_match_id), item]));
    resultBox.hidden = false;
    resultBox.textContent = `${data.analyzed} analyse(s) obtenue(s) à partir du cache sur ${data.matches_in_calendar} rencontres. ${data.skipped} ignorée(s), profils manquants ou ligue non reliée. ${data.additional_api_requests} appel API supplémentaire.`;
    renderMatches();
    const selected = state.matches.find((match) => String(match.source_match_id) === String(state.selectedId));
    if (selected && state.batchResults.has(String(selected.source_match_id))) {
      state.analysis = state.batchResults.get(String(selected.source_match_id));
      renderDetail(selected);
    }
  } catch (error) {
    resultBox.hidden = false;
    resultBox.textContent = error.message;
  } finally {
    state.batchBusy = false;
    button.disabled = false;
    button.querySelector(".batch-action-label").textContent = "ANALYSER LE CACHE";
  }
}

async function analyzeMatch(match) {
  if (state.busy) return;
  state.busy = true;
  renderDetail(match);
  let errorMessage = "";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: match.match_date, match_id: match.source_match_id }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "L'analyse a échoué.");
    state.analysis = result;
  } catch (error) {
    errorMessage = error.message;
  } finally {
    state.busy = false;
    renderDetail(match, errorMessage);
  }
}

async function loadMatches(forceRefresh = false) {
  if (forceRefresh) {
    listMeta.textContent = "Actualisation…";
  } else {
    matchList.hidden = false;
    matchList.replaceChildren();
    matchList.append(el("div", "loading-screen", ""));
    const loader = matchList.firstChild;
    loader.append(el("span", "loading-mark"), el("strong", "", "Le calendrier arrive"), el("span", "", "Récupération des rencontres de la journée"));
    listMeta.textContent = "Chargement…";
    state.matches = [];
    state.selectedId = null;
    state.analysis = null;
    state.batchResults = new Map();
    state.dailyPicks = null;
    const picksCount = document.querySelector("#tab-picks-count");
    picksCount.hidden = true;
    picksCount.textContent = "";
    document.querySelector("#daily-picks-panel").hidden = true;
    detailPanel.classList.remove("open");
    renderDetailPlaceholder();
  }

  try {
    const refreshParameter = forceRefresh ? "&refresh=1" : "";
    const response = await fetch(`/api/matches?date=${encodeURIComponent(dateInput.value)}${refreshParameter}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Le calendrier n'est pas disponible.");
    applyMatches(data, forceRefresh, forceRefresh);
    totalCount.textContent = data.count;
    loadPredictionStats();
  } catch (error) {
    if (forceRefresh) {
      listMeta.textContent = "Échec de l'actualisation";
      return;
    }
    matchList.replaceChildren();
    const message = el("div", "empty-state");
    message.append(el("span", "empty-mark", "!"), el("strong", "", "Calendrier indisponible"), el("span", "", error.message));
    matchList.append(message);
    listMeta.textContent = "Erreur de chargement";
  }
}

function renderDetailPlaceholder() {
  detailContent.className = "detail-content empty-detail";
  detailContent.replaceChildren();
  const art = el("div", "detail-placeholder-art");
  art.append(el("span", "pitch-circle"), el("span", "pitch-line"), el("span", "placeholder-ball", "●"));
  detailContent.append(art, el("div", "detail-placeholder-title", "Choisis\nton match."), el("p", "", "La fiche et l'analyse apparaîtront ici."), el("span", "detail-index", "SÉLECTIONNE UNE RENCONTRE DANS LE CALENDRIER"));
}

dateInput.value = todayLocal();
activateWorkspaceView(window.location.hash.slice(1), { updateHash: false });
dateInput.addEventListener("change", loadMatches);
document.querySelector("#refresh-calendar").addEventListener("click", () => loadMatches(true));
searchInput.addEventListener("input", renderMatches);
countrySelect.addEventListener("change", () => { refreshFilters(); renderMatches(); });
leagueSelect.addEventListener("change", renderMatches);
document.querySelectorAll(".availability-tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelector(".availability-tab.active")?.classList.remove("active");
  button.classList.add("active");
  state.availability = button.dataset.availability;
  renderMatches();
}));
document.querySelectorAll(".status-tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelector(".status-tab.active")?.classList.remove("active");
  button.classList.add("active");
  state.status = button.dataset.status;
  renderMatches();
  syncAutoRefreshTimer(state.autoRefreshEnabled && state.status === "live");
}));
document.querySelector("#clear-selection").addEventListener("click", () => {
  state.selectedId = null;
  state.analysis = null;
  detailPanel.classList.remove("open");
  renderMatches();
  renderDetailPlaceholder();
});
document.querySelector("#analyze-cached").addEventListener("click", analyzeCachedMatches);
document.querySelector("#generate-daily-picks").addEventListener("click", generateDailyPicks);
document.querySelector("#refresh-performance").addEventListener("click", loadPredictionStats);
window.addEventListener("popstate", () => {
  activateWorkspaceView(window.location.hash.slice(1), { updateHash: false });
});
document.querySelector("#notifications-toggle").addEventListener("click", toggleFavoriteNotifications);
document.querySelector("#auto-refresh").addEventListener("click", (event) => {
  state.autoRefreshEnabled = !state.autoRefreshEnabled;
  event.currentTarget.setAttribute("aria-pressed", String(state.autoRefreshEnabled));
  document.querySelector("#auto-refresh-label").textContent = state.autoRefreshEnabled
    ? "AUTO ACTIVÉ"
    : "AUTO DÉSACTIVÉ";
  syncAutoRefreshTimer(state.autoRefreshEnabled && state.status === "live");
});
document.addEventListener("visibilitychange", () => {
  syncAutoRefreshTimer(state.autoRefreshEnabled && state.status === "live" && !document.hidden);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) {
    event.preventDefault();
    searchInput.focus();
  }
  if (event.key === "Escape") {
    if (document.activeElement === searchInput) searchInput.value = "";
    detailPanel.classList.remove("open");
    renderMatches();
  }
});

loadMatches();
updateNotificationControls();