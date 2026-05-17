"use strict";

(function () {
  var content = document.getElementById("rules-content");
  var tocList = document.getElementById("toc-list");
  if (!content || !tocList) return;

  var headings = content.querySelectorAll("h1, h2, h3");
  if (headings.length === 0) return;

  var slugCount = {};

  headings.forEach(function (heading) {
    var text = heading.textContent.trim();
    var base = text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    if (!base) base = "section";

    if (slugCount[base] === undefined) {
      slugCount[base] = 0;
    } else {
      slugCount[base] += 1;
      base = base + "-" + slugCount[base];
    }

    if (!heading.id) heading.id = base;

    var li = document.createElement("li");
    li.className = "toc-" + heading.tagName.toLowerCase();

    var a = document.createElement("a");
    a.href = "#" + heading.id;
    a.textContent = text;
    li.appendChild(a);
    tocList.appendChild(li);
  });

  if (!("IntersectionObserver" in window)) return;

  var links = tocList.querySelectorAll("a");
  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          links.forEach(function (l) { l.classList.remove("active"); });
          var active = tocList.querySelector("a[href='#" + entry.target.id + "']");
          if (active) active.classList.add("active");
        }
      });
    },
    { rootMargin: "0px 0px -60% 0px" }
  );

  headings.forEach(function (h) { observer.observe(h); });
})();
