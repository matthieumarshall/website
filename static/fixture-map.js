"use strict";

/**
 * fixture-map.js — Leaflet map island for fixture location.
 *
 * Sentinel element: <div id="fixture-map" data-lat="..." data-lon="...">
 * The element must have an explicit height set via CSS or inline style.
 */
(function () {
  var sentinel = document.getElementById("fixture-map");
  if (!sentinel) return;

  var lat = parseFloat(sentinel.dataset.lat);
  var lon = parseFloat(sentinel.dataset.lon);
  if (isNaN(lat) || isNaN(lon)) return;

  // Point Leaflet's default icon loader at our self-hosted images.
  L.Icon.Default.imagePath = "/static/images/";

  // All fixtures are in South England — constrain the map so Leaflet never
  // fetches tiles outside this region and prevent zooming out to world level.
  var southEngland = L.latLngBounds([50.5, -2.8], [52.2, 0.3]);

  var map = L.map("fixture-map", {
    scrollWheelZoom: false,
    maxBounds: southEngland.pad(0.25),
    minZoom: 8,
  }).setView([lat, lon], 14);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  L.marker([lat, lon]).addTo(map);
})();
