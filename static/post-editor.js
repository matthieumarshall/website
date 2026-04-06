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
          quill.insertEmbed(range.index, "image", data.url);
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
