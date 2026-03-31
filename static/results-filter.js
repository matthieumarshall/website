"use strict";

/**
 * Results filter island.
 *
 * Sentinel: <div id="results-filter"> in _results_race_panel.html.
 *
 * Reads filter state from URL params on page load, populates Category and Club
 * dropdowns from the table data, and hides non-matching rows. Syncs filter
 * state back to the URL via replaceState so links are shareable.
 *
 * Also updates #export-csv-link and #export-pdf-link hrefs whenever filters
 * change, so exports always reflect the current view.
 *
 * Re-initialises on htmx:afterSwap of #race-table so a new race swap
 * repopulates the dropdowns and re-applies URL filters.
 */

(function () {
  function getRaceId() {
    const sentinel = document.getElementById("results-filter");
    return sentinel ? sentinel.dataset.raceId : null;
  }

  function getTableRows() {
    const table = document.getElementById("results-table");
    if (!table) return [];
    return Array.from(table.querySelectorAll("tbody tr"));
  }

  /** Populate a <select> from a sorted list of distinct values. */
  function populateSelect(selectEl, values, allLabel) {
    const current = selectEl.value;
    while (selectEl.options.length > 1) selectEl.remove(1);
    values.forEach(function (v) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      selectEl.appendChild(opt);
    });
    // Restore previous selection if still valid
    if (current && values.includes(current)) selectEl.value = current;
  }

  function getDistinct(rows, attr) {
    const seen = new Set();
    rows.forEach(function (row) {
      const val = row.dataset[attr];
      if (val) seen.add(val);
    });
    return Array.from(seen).sort();
  }

  function applyFilters() {
    const rows = getTableRows();
    const category = document.getElementById("filter-category")?.value || "";
    const club = document.getElementById("filter-club")?.value || "";
    const gender = document.getElementById("filter-gender")?.value || "";
    const name = (document.getElementById("filter-name")?.value || "").toLowerCase();

    let visibleCount = 0;
    rows.forEach(function (row) {
      const match =
        (!category || row.dataset.category === category) &&
        (!club || row.dataset.club === club) &&
        (!gender || row.dataset.gender === gender) &&
        (!name || row.dataset.name.includes(name));
      row.style.display = match ? "" : "none";
      if (match) visibleCount++;
    });

    const noMatch = document.getElementById("results-no-match");
    if (noMatch) noMatch.style.display = visibleCount === 0 ? "" : "none";

    syncUrl();
    syncExportLinks();
  }

  function syncUrl() {
    const params = new URLSearchParams(window.location.search);
    const filterIds = ["filter-category", "filter-club", "filter-gender", "filter-name"];
    const paramKeys = ["category", "club", "gender", "name"];
    filterIds.forEach(function (id, i) {
      const val = document.getElementById(id)?.value || "";
      if (val) {
        params.set(paramKeys[i], val);
      } else {
        params.delete(paramKeys[i]);
      }
    });
    const newUrl = window.location.pathname + (params.toString() ? "?" + params.toString() : "");
    window.history.replaceState(null, "", newUrl);
  }

  function syncExportLinks() {
    const raceId = getRaceId();
    if (!raceId) return;

    const category = document.getElementById("filter-category")?.value || "";
    const club = document.getElementById("filter-club")?.value || "";
    const gender = document.getElementById("filter-gender")?.value || "";
    const name = document.getElementById("filter-name")?.value || "";

    const params = new URLSearchParams({ race_id: raceId });
    if (category) params.set("category", category);
    if (club) params.set("club", club);
    if (gender) params.set("gender", gender);
    if (name) params.set("name", name);
    const qs = params.toString();

    const csvLink = document.getElementById("export-csv-link");
    const pdfLink = document.getElementById("export-pdf-link");
    if (csvLink) csvLink.href = "/results/export/csv?" + qs;
    if (pdfLink) pdfLink.href = "/results/export/pdf?" + qs;
  }

  function applyColumnToggles() {
    const showPos = document.getElementById("toggle-pos")?.checked;
    const showGenPos = document.getElementById("toggle-gen-pos")?.checked;

    // Toggle .col-pos cells
    document.querySelectorAll(".col-pos").forEach(function (el) {
      el.style.display = showPos ? "" : "none";
    });
    // Toggle .col-gen-pos cells
    document.querySelectorAll(".col-gen-pos").forEach(function (el) {
      el.style.display = showGenPos ? "" : "none";
    });
  }

  function restoreFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const filterIds = ["filter-category", "filter-club", "filter-gender", "filter-name"];
    const paramKeys = ["category", "club", "gender", "name"];
    filterIds.forEach(function (id, i) {
      const el = document.getElementById(id);
      if (el && params.has(paramKeys[i])) el.value = params.get(paramKeys[i]);
    });
  }

  function init() {
    const sentinel = document.getElementById("results-filter");
    if (!sentinel) return;

    const rows = getTableRows();

    // Populate dynamic dropdowns
    const categorySelect = document.getElementById("filter-category");
    const clubSelect = document.getElementById("filter-club");
    if (categorySelect) populateSelect(categorySelect, getDistinct(rows, "category"), "All categories");
    if (clubSelect) populateSelect(clubSelect, getDistinct(rows, "club"), "All clubs");

    // Restore filter state from URL
    restoreFromUrl();

    // Wire up filter controls
    ["filter-category", "filter-club", "filter-gender"].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.addEventListener("change", applyFilters);
    });
    const nameInput = document.getElementById("filter-name");
    if (nameInput) nameInput.addEventListener("input", applyFilters);

    // Column toggle checkboxes
    const posToggle = document.getElementById("toggle-pos");
    const genPosToggle = document.getElementById("toggle-gen-pos");
    if (posToggle) posToggle.addEventListener("change", applyColumnToggles);
    if (genPosToggle) genPosToggle.addEventListener("change", applyColumnToggles);

    // Apply initial state
    applyFilters();
    applyColumnToggles();
    syncExportLinks();
  }

  // Re-init when the race table is swapped by HTMX
  document.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === "race-table") {
      // Repopulate dropdowns based on new table rows
      const rows = getTableRows();
      const categorySelect = document.getElementById("filter-category");
      const clubSelect = document.getElementById("filter-club");
      if (categorySelect) {
        populateSelect(categorySelect, getDistinct(rows, "category"), "All categories");
        categorySelect.value = "";
      }
      if (clubSelect) {
        populateSelect(clubSelect, getDistinct(rows, "club"), "All clubs");
        clubSelect.value = "";
      }
      // Clear name search
      const nameInput = document.getElementById("filter-name");
      if (nameInput) nameInput.value = "";
      const genderSelect = document.getElementById("filter-gender");
      if (genderSelect) genderSelect.value = "";

      // Update sentinel race ID from the new panel if available
      const sentinel = document.getElementById("results-filter");
      if (sentinel) {
        // race_id is embedded in the race tab button that was clicked
        const activeBtn = document.querySelector(
          "#race-panel .btn-group button.active, #race-panel .btn.active"
        );
        if (activeBtn) {
          // Extract race_id from hx-get attribute
          const hxGet = activeBtn.getAttribute("hx-get") || "";
          const match = hxGet.match(/race_id=(\d+)/);
          if (match) sentinel.dataset.raceId = match[1];
        }
      }

      applyFilters();
      applyColumnToggles();
      syncExportLinks();
    }
  });

  // Initial page load
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
