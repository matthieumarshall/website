"use strict";

(function () {
  // Custom image blot that stores alt text in the Quill Delta so it survives
  // undo/redo and DOM re-renders. Handles both object {url, alt} (new) and
  // plain string (legacy) values so existing post content continues to work.
  const BaseImage = Quill.import("formats/image");
  class ImageWithAlt extends BaseImage {
    static create(value) {
      const node = super.create(typeof value === "object" ? value.url : value);
      if (typeof value === "object" && value.alt) {
        node.setAttribute("alt", value.alt);
      }
      return node;
    }
    static value(node) {
      return { url: node.getAttribute("src") || "", alt: node.getAttribute("alt") || "" };
    }
  }
  Quill.register(ImageWithAlt, /* overwrite */ true);

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
          quill.insertEmbed(range.index, "image", { url: data.url, alt: altText });
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
