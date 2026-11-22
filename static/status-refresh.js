"use strict";

(function () {
  let retryAfter = 0;

  document.body.addEventListener("htmx:afterRequest", function (event) {
    if (event.detail.requestConfig.path !== "/status/summary") return;
    if (event.detail.xhr.status === 429) {
      const seconds = Number(event.detail.xhr.getResponseHeader("Retry-After"));
      retryAfter = Date.now() + (Number.isFinite(seconds) && seconds > 0 ? seconds : 60) * 1000;
    } else if (event.detail.xhr.status < 400) {
      retryAfter = 0;
    }
  });

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    if (event.detail.requestConfig.path === "/status/summary" && Date.now() < retryAfter) {
      event.preventDefault();
    }
  });
})();
