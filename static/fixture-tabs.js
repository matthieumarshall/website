"use strict";

document.addEventListener("click", function (event) {
  const button = event.target.closest("[data-fixture-tab]");
  if (!button) return;

  const group = button.closest('[role="group"]');
  if (!group) return;

  group.querySelectorAll("[data-fixture-tab]").forEach(function (tab) {
    tab.classList.remove("active");
    tab.setAttribute("aria-pressed", "false");
  });

  button.classList.add("active");
  button.setAttribute("aria-pressed", "true");
});
