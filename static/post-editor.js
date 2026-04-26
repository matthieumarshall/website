"use strict";

(function () {
  const toolbarOptions = [
    [{ header: [1, 2, 3, false] }],
    ["bold", "italic", "underline", "strike"],
    ["blockquote"],
    [{ list: "ordered" }, { list: "bullet" }],
    ["link", "image"],
    ["clean"],
  ];

  const quill = new Quill("#editor", {
    theme: "snow",
    modules: { toolbar: { container: toolbarOptions, handlers: { image: imageHandler } } },
  });

  function imageHandler() {
    const input = document.createElement("input");
    input.setAttribute("type", "file");
    input.setAttribute("accept", "image/jpeg,image/png,image/gif,image/webp");
    input.click();

    input.addEventListener("change", function () {
      const file = input.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append("file", file);

      fetch("/api/upload/image", { method: "POST", body: formData })
        .then(function (resp) {
          if (!resp.ok) throw new Error("Upload failed: " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          const range = quill.getSelection(true);
          const altText =
            prompt("Enter alternative text for this image (describe what it shows):") || "";
          quill.insertEmbed(range.index, "image", data.url);
          const allImgs = Array.from(quill.root.querySelectorAll("img"));
          const inserted = allImgs.filter(function (el) {
            return el.getAttribute("src") === data.url;
          });
          const img = inserted[inserted.length - 1];
          if (img) img.alt = altText;
          quill.setSelection(range.index + 1);
        })
        .catch(function (err) {
          alert("Image upload failed. " + err.message);
        });
    });
  }

  const form = document.getElementById("post-form");
  const contentInput = document.getElementById("content-input");

  form.addEventListener("submit", function (e) {
    contentInput.value = quill.root.innerHTML;
  });
})();
