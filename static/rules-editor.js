"use strict";

(function () {
  // Register the quill-better-table module before creating the Quill instance.
  Quill.register(
    { "modules/better-table": QuillBetterTable },
    true
  );

  var toolbarOptions = [
    [{ header: [1, 2, 3, false] }],
    ["bold", "italic", "underline", "strike"],
    ["blockquote"],
    [{ list: "ordered" }, { list: "bullet" }],
    ["link", "image"],
    [{ "table": "insert-table" }],
    ["clean"],
  ];

  var quill = new Quill("#editor", {
    theme: "snow",
    modules: {
      toolbar: {
        container: toolbarOptions,
        handlers: { image: imageHandler },
      },
      "better-table": {
        operationMenu: {
          items: {
            insertColumnRight: { text: "Insert column right" },
            insertColumnLeft: { text: "Insert column left" },
            insertRowUp: { text: "Insert row above" },
            insertRowDown: { text: "Insert row below" },
            mergeCells: { text: "Merge cells" },
            unmergeCells: { text: "Unmerge cells" },
            deleteColumn: { text: "Delete column" },
            deleteRow: { text: "Delete row" },
            deleteTable: { text: "Delete table" },
          },
        },
      },
    },
  });

  function imageHandler() {
    var input = document.createElement("input");
    input.setAttribute("type", "file");
    input.setAttribute("accept", "image/jpeg,image/png,image/gif,image/webp");
    input.click();

    input.addEventListener("change", function () {
      var file = input.files[0];
      if (!file) return;

      var formData = new FormData();
      formData.append("file", file);

      fetch("/uploads/image", { method: "POST", body: formData })
        .then(function (resp) {
          if (!resp.ok) throw new Error("Upload failed: " + resp.status);
          return resp.json();
        })
        .then(function (data) {
          var range = quill.getSelection(true);
          quill.insertEmbed(range.index, "image", data.url);
          quill.setSelection(range.index + 1);
        })
        .catch(function (err) {
          alert("Image upload failed. " + err.message);
        });
    });
  }

  var form = document.getElementById("rules-form");
  var contentInput = document.getElementById("rules-content-input");

  form.addEventListener("submit", function () {
    contentInput.value = quill.root.innerHTML;
  });
})();
