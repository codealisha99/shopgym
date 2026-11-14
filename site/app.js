// Replay: switch episodes with tabs, step through frames with the list or arrow keys.
(function () {
  var root = document.querySelector("[data-replay]");
  if (!root) return;
  var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
  var episodes = root.querySelectorAll(".replay-episode");

  function showEpisode(slug) {
    tabs.forEach(function (tab) {
      tab.setAttribute("aria-selected", String(tab.dataset.ep === slug));
    });
    episodes.forEach(function (section) {
      section.hidden = section.id !== "ep-" + slug;
    });
    showFrame(document.getElementById("ep-" + slug), 0);
  }

  function showFrame(section, index) {
    var buttons = section.querySelectorAll(".replay-steps button");
    var frames = section.querySelectorAll(".replay-view img");
    if (!buttons.length) return;
    index = Math.max(0, Math.min(index, buttons.length - 1));
    buttons.forEach(function (b, i) { b.setAttribute("aria-current", String(i === index)); });
    frames.forEach(function (img, i) { img.hidden = i !== index; });
    return buttons[index];
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () { showEpisode(tab.dataset.ep); });
  });

  root.addEventListener("click", function (event) {
    var button = event.target.closest(".replay-steps button");
    if (!button) return;
    var section = button.closest(".replay-episode");
    showFrame(section, parseInt(button.dataset.frame, 10));
  });

  root.addEventListener("keydown", function (event) {
    var button = event.target.closest(".replay-steps button");
    if (!button || (event.key !== "ArrowDown" && event.key !== "ArrowUp")) return;
    event.preventDefault();
    var section = button.closest(".replay-episode");
    var current = parseInt(button.dataset.frame, 10);
    var next = event.key === "ArrowDown" ? current + 1 : current - 1;
    var target = showFrame(section, next);
    if (target) target.focus();
  });
})();
