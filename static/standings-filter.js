"use strict";

(function () {
  function init() {
    const panel = document.getElementById("standings-table-panel");
    const controls = document.getElementById("standings-filter");
    if (!panel || !controls) return;
    const rows = Array.from(panel.querySelectorAll("[data-standing-row]"));
    const club = document.getElementById("standings-filter-club");
    const name = document.getElementById("standings-filter-name");
    const clubs = Array.from(new Set(rows.map(row => row.dataset.club).filter(Boolean))).sort();
    clubs.forEach(function (value) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      club.appendChild(option);
    });

    function apply() {
      const search = name.value.toLowerCase();
      let visible = 0;
      rows.forEach(function (row) {
        const match = (!club.value || row.dataset.club === club.value) &&
          (!search || row.dataset.name.includes(search));
        row.hidden = !match;
        if (match) visible++;
      });
      document.getElementById("standings-no-match").hidden = visible !== 0;
      panel.querySelectorAll("[data-standings-export]").forEach(function (link) {
        const url = new URL(link.href);
        [["club", club.value], ["name", name.value]].forEach(function ([key, value]) {
          if (value) url.searchParams.set(key, value);
          else url.searchParams.delete(key);
        });
        link.href = url.toString();
      });
    }
    club.addEventListener("change", apply);
    name.addEventListener("input", apply);
    apply();
  }

  document.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "standings-table-panel") init();
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}());
