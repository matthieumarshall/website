"use strict";

(function () {
  const content = document.getElementById("rules-content");
  const tocLists = document.querySelectorAll(".toc-list");
  if (!content || tocLists.length === 0) return;

  const headings = content.querySelectorAll("h1, h2, h3");
  if (headings.length === 0) return;

  const slugCount = {};

  headings.forEach(function (heading) {
    const text = heading.textContent.trim();
    const slug = text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    let uniqueSlug = slug || "section";

    if (slugCount[uniqueSlug] === undefined) {
      slugCount[uniqueSlug] = 0;
    } else {
      slugCount[uniqueSlug] += 1;
      uniqueSlug = uniqueSlug + "-" + slugCount[uniqueSlug];
    }

    if (!heading.id) heading.id = uniqueSlug;

    tocLists.forEach(function (tocList) {
      const li = document.createElement("li");
      li.className = "toc-" + heading.tagName.toLowerCase();

      const a = document.createElement("a");
      a.href = "#" + heading.id;
      a.textContent = text;
      li.appendChild(a);
      tocList.appendChild(li);
    });
  });

  if (!("IntersectionObserver" in window)) return;

  const observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          document.querySelectorAll(".toc-list a").forEach(function (link) {
            link.classList.remove("active");
          });
          document
            .querySelectorAll(".toc-list a[href='#" + entry.target.id + "']")
            .forEach(function (activeLink) {
              activeLink.classList.add("active");
            });
        }
      });
    },
    { rootMargin: "0px 0px -60% 0px" }
  );

  headings.forEach(function (heading) {
    observer.observe(heading);
  });
})();
