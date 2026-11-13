"use strict";

/**
 * Timetable editor for the fixture form.
 *
 * Manages a dynamic list of time + event rows and serialises them to a
 * hidden JSON field (``#timetable-json-input``) when the form is submitted.
 */

/** Add a new blank timetable row to the editor. */
function addTimetableRow() {
  const container = document.getElementById("timetable-rows");
  const index = container.querySelectorAll(".timetable-row").length + 1;

  const row = document.createElement("div");
  row.className = "timetable-row d-flex gap-2 mb-2 align-items-center";

  const timeInput = document.createElement("input");
  timeInput.type = "time";
  timeInput.className = "form-control w-auto";
  timeInput.setAttribute("aria-label", `Time for row ${index}`);
  timeInput.dataset.timetable = "time";

  const eventInput = document.createElement("input");
  eventInput.type = "text";
  eventInput.className = "form-control";
  eventInput.setAttribute("aria-label", `Event for row ${index}`);
  eventInput.dataset.timetable = "event";
  eventInput.maxLength = 255;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn btn-outline-danger btn-sm flex-shrink-0";
  removeBtn.textContent = "Remove";
  removeBtn.setAttribute("aria-label", `Remove row ${index}`);
  removeBtn.addEventListener("click", function () {
    removeTimetableRow(removeBtn);
  });

  row.appendChild(timeInput);
  row.appendChild(eventInput);
  const raceSelect = document.createElement("select");
  raceSelect.className = "form-select w-auto";
  raceSelect.dataset.timetable = "race_id";
  raceSelect.setAttribute("aria-label", "Linked race");
  const options = document.getElementById("timetable-race-options");
  if (options) raceSelect.appendChild(options.content.cloneNode(true));
  row.appendChild(raceSelect);
  row.appendChild(removeBtn);
  container.appendChild(row);
}

/** Remove the timetable row that contains the given button element. */
function removeTimetableRow(btn) {
  const row = btn.closest(".timetable-row");
  if (row) {
    row.remove();
  }
}

/** Serialise all timetable rows into the hidden JSON input before submission. */
function serializeTimetable() {
  const rows = document.querySelectorAll("#timetable-rows .timetable-row");
  const entries = [];

  rows.forEach(function (row) {
    const time = (row.querySelector("[data-timetable='time']") || {}).value || "";
    const event = (row.querySelector("[data-timetable='event']") || {}).value || "";
    if (time.trim() || event.trim()) {
      const id = (row.querySelector("[data-timetable='id']") || {}).value;
      const raceId = (row.querySelector("[data-timetable='race_id']") || {}).value;
      const sourceRaceId = (row.querySelector("[data-timetable='source_race_id']") || {}).value;
      entries.push({ time: time.trim(), event: event.trim(), id: id ? Number(id) : null, race_id: raceId ? Number(raceId) : null, source_race_id: sourceRaceId ? Number(sourceRaceId) : null });
    }
  });

  const hidden = document.getElementById("timetable-json-input");
  if (hidden) {
    hidden.value = JSON.stringify(entries);
  }
}

// Wire up the existing Remove buttons that were pre-rendered by the server.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("#timetable-rows .timetable-row").forEach(function (row) {
    const btn = row.querySelector("button");
    if (btn) {
      btn.addEventListener("click", function () {
        removeTimetableRow(btn);
      });
    }
  });

  const addBtn = document.getElementById("add-timetable-row");
  if (addBtn) {
    addBtn.addEventListener("click", addTimetableRow);
  }

  const form = document.getElementById("fixture-form");
  if (form) {
    form.addEventListener("submit", serializeTimetable);
  }
});
