document.addEventListener("change", function (event) {
  if (!event.target.matches("[data-team-filter]")) return;
  const panel = event.target.closest("section, #standings-table-panel");
  if (!panel) return;
  const division = event.target.value;
  panel.querySelectorAll("[data-team-division]").forEach(function (row) {
    row.hidden = !!division && row.dataset.teamDivision !== division;
  });
  panel.querySelectorAll("[data-team-export]").forEach(function (link) {
    const url = new URL(link.href);
    if (division) url.searchParams.set("division", division);
    else url.searchParams.delete("division");
    link.href = url.toString();
  });
});
