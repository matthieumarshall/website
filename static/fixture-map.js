"use strict";

/**
 * fixture-map.js — Leaflet map island for fixture location.
 *
 * Sentinel element: <div class="fixture-map" data-lat="..." data-lon="...">
 * immediately preceding this <script> tag. The element must have an explicit
 * height set via CSS or inline style.
 *
 * The sentinel's id is unique per fixture (e.g. "fixture-map-12") rather than
 * a fixed "fixture-map" id. This matters because htmx swaps this whole block
 * in via hx-swap="innerHTML" on every fixture tab click, and htmx settles
 * (re-syncs) class/style/width/height attributes between old and new elements
 * that share the same id across a swap. With a fixed shared id, htmx would
 * strip the leaflet-container class Leaflet adds here moments after this
 * script runs, breaking the map's CSS containment (it would render huge,
 * overflowing the page). Using document.currentScript to self-locate avoids
 * depending on a fixed id at all.
 */
(function () {
  var script = document.currentScript;
  var sentinel = script && script.previousElementSibling;
  if (!sentinel || !sentinel.classList.contains("fixture-map")) return;

  // Leaflet must already be loaded (see fixtures.html: leaflet.min.js is
  // loaded in <head> so it always runs before this island).
  if (typeof L === "undefined") return;

  var lat = parseFloat(sentinel.dataset.lat);
  var lon = parseFloat(sentinel.dataset.lon);
  if (isNaN(lat) || isNaN(lon)) return;

  // All fixtures are in South England — constrain the map so Leaflet never
  // fetches tiles outside this region and prevent zooming out to world level.
  var southEngland = L.latLngBounds([50.5, -2.8], [52.2, 0.3]);

  // Bad/placeholder coordinates (e.g. unconfirmed venue data) fall outside
  // this box and, combined with maxBounds below, make Leaflet render a
  // nonsensical zoomed-out view. Treat them as "no location yet" instead.
  if (!southEngland.contains([lat, lon])) {
    var heading = sentinel.previousElementSibling;
    if (heading && heading.tagName === "H3") heading.remove();
    sentinel.remove();
    return;
  }

  // Point Leaflet's default icon loader at our self-hosted images.
  L.Icon.Default.imagePath = "/static/images/";

  var map = L.map(sentinel, {
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
