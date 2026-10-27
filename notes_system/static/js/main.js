(function () {
  "use strict";

  // Mobile menu
  var toggle = document.getElementById("navToggle");
  var links = document.getElementById("navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? "Close" : "Menu";
    });
  }

  // Dismiss flash messages; success messages fade after a few seconds
  document.querySelectorAll(".flash").forEach(function (box) {
    var close = box.querySelector(".flash-close");
    if (close) close.addEventListener("click", function () { box.remove(); });
    if (box.classList.contains("flash-success")) {
      setTimeout(function () { box.remove(); }, 6000);
    }
  });

  // Confirm before destructive actions
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // Show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.getAttribute("data-toggle-password"));
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
    });
  });

  // Auto-apply filter dropdowns
  var filterForm = document.getElementById("filterForm");
  if (filterForm) {
    filterForm.querySelectorAll("select").forEach(function (s) {
      s.addEventListener("change", function () { filterForm.submit(); });
    });
  }

  // Client-side upload checks (the server repeats every check)
  var up = document.getElementById("uploadForm");
  if (up) {
    var input = document.getElementById("file");
    var info = document.getElementById("fileInfo");
    var maxMb = parseInt(up.getAttribute("data-max-mb"), 10);
    var exts = up.getAttribute("data-exts").split(",");

    function check() {
      var f = input.files[0];
      info.className = "file-info";
      if (!f) { info.textContent = ""; return true; }
      var dot = f.name.lastIndexOf(".");
      var ext = dot > -1 ? f.name.slice(dot + 1).toLowerCase() : "";
      var mb = (f.size / 1048576).toFixed(2);
      if (exts.indexOf(ext) === -1) {
        info.textContent = "." + ext + " files are not allowed. Choose one of: " + exts.join(", ") + ".";
        info.className = "file-info bad"; return false;
      }
      if (f.size > maxMb * 1048576) {
        info.textContent = f.name + " is " + mb + " MB. The limit is " + maxMb + " MB.";
        info.className = "file-info bad"; return false;
      }
      info.textContent = f.name + " (" + mb + " MB) is ready to upload.";
      info.className = "file-info good"; return true;
    }
    input.addEventListener("change", check);
    up.addEventListener("submit", function (e) {
      if (!check()) { e.preventDefault(); }
      else if (!input.files[0]) { e.preventDefault(); info.textContent = "Choose a file to upload."; info.className = "file-info bad"; }
    });
  }
})();
