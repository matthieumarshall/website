"use strict";

(function () {
  function showEditorError(msg) {
    var editorDiv = document.getElementById("editor");
    if (editorDiv) {
      editorDiv.innerHTML =
        '<div style="color:red;padding:1rem;border:1px solid red;border-radius:4px">' +
        "<strong>Editor failed to load:</strong> " + msg +
        "<br><small>Open browser DevTools (F12) → Console for details.</small></div>";
    }
    console.error("rules-editor: " + msg);
  }

  if (typeof Quill === "undefined") {
    showEditorError("quill.min.js did not load.");
    return;
  }

  // quill-better-table exposes itself as window.quillBetterTable.
  // Guard against both a direct class export and an ES-module-style { default } wrapper.
  var BetterTable =
    (typeof quillBetterTable !== "undefined" && quillBetterTable) ||
    (typeof window.quillBetterTable !== "undefined" && window.quillBetterTable);
  if (!BetterTable) {
    showEditorError("quill-better-table.min.js did not load.");
    return;
  }
  if (BetterTable.default) {
    BetterTable = BetterTable.default;
  }

  try {
    Quill.register({ "modules/better-table": BetterTable }, true);
  } catch (e) {
    showEditorError("Quill.register failed: " + e.message);
    return;
  }

  var toolbarOptions = [
    [{ header: [1, 2, 3, false] }],
    ["bold", "italic", "underline", "strike"],
    ["blockquote"],
    [{ list: "ordered" }, { list: "bullet" }],
    ["link", "image"],
    [{ "table": "insert-table" }],
    ["clean"],
  ];

  var quill;
  try {
    quill = new Quill("#editor", {
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
  } catch (e) {
    showEditorError("new Quill() failed: " + e.message);
    return;
  }

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
