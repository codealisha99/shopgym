// ShopGym landing. Replay player: episodes as tabs, one frame per action, the acted-on element outlined,
// autoplay once it scrolls into view (never under prefers-reduced-motion), and every control by keyboard.
(function () {
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var STEP_MS = 1700;
  var LAST_MS = 3200;
  var root = document.querySelector("[data-replay]");
  if (!root) return;

  var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
  var episodes = Array.prototype.slice.call(root.querySelectorAll(".player-episode"));
  var timers = new WeakMap();

  function activeEpisode() {
    return episodes.find(function (s) { return !s.hidden; }) || episodes[0];
  }

  function stop(section) {
    clearTimeout(timers.get(section));
    timers.delete(section);
    var button = section.querySelector('[data-act="play"]');
    button.setAttribute("aria-pressed", "false");
    button.textContent = "Play";
    button.setAttribute("aria-label", "Play");
  }

  function show(section, index) {
    var total = parseInt(section.dataset.total, 10);
    index = Math.max(0, Math.min(index, total - 1));
    section.dataset.index = String(index);
    section.querySelectorAll("img[data-n]").forEach(function (img) {
      img.hidden = parseInt(img.dataset.n, 10) !== index;
    });
    section.querySelectorAll(".target, .caption-text").forEach(function (el) {
      el.hidden = parseInt(el.dataset.n, 10) !== index;
    });
    section.querySelectorAll(".replay-steps button").forEach(function (b, i) {
      b.setAttribute("aria-current", String(i === index));
    });
    section.querySelector(".step-count").textContent = "Step " + (index + 1) + " of " + total;
    section.querySelector("[data-scrub]").value = String(index);
    section.querySelector(".verdict").hidden = index !== total - 1;
    section.querySelector('[data-act="prev"]').disabled = index === 0;
    section.querySelector('[data-act="next"]').disabled = index === total - 1;
    return index;
  }

  function schedule(section) {
    var index = parseInt(section.dataset.index, 10);
    var total = parseInt(section.dataset.total, 10);
    if (index >= total - 1) {
      stop(section);
      return;
    }
    var delay = index + 1 === total - 1 ? LAST_MS : STEP_MS;
    timers.set(section, setTimeout(function () {
      show(section, index + 1);
      schedule(section);
    }, delay));
  }

  function play(section) {
    if (reduceMotion) return;
    if (parseInt(section.dataset.index, 10) >= parseInt(section.dataset.total, 10) - 1) show(section, 0);
    clearTimeout(timers.get(section));
    var button = section.querySelector('[data-act="play"]');
    button.setAttribute("aria-pressed", "true");
    button.textContent = "Pause";
    button.setAttribute("aria-label", "Pause");
    schedule(section);
  }

  function pause(section) {
    clearTimeout(timers.get(section));
    stop(section);
  }

  function selectEpisode(slug) {
    tabs.forEach(function (tab) {
      tab.setAttribute("aria-selected", String(tab.dataset.ep === slug));
    });
    episodes.forEach(function (section) {
      if (section.id !== "ep-" + slug) pause(section);
      section.hidden = section.id !== "ep-" + slug;
    });
    show(activeEpisode(), 0);
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      selectEpisode(tab.dataset.ep);
    });
  });

  root.addEventListener("click", function (event) {
    var section = activeEpisode();
    var act = event.target.closest("[data-act]");
    var chip = event.target.closest(".replay-steps button");
    if (chip) {
      pause(section);
      show(section, parseInt(chip.dataset.frame, 10));
      return;
    }
    if (!act) return;
    var index = parseInt(section.dataset.index, 10);
    if (act.dataset.act === "play") {
      if (timers.get(section)) pause(section); else play(section);
      return;
    }
    pause(section);
    if (act.dataset.act === "restart") show(section, 0);
    if (act.dataset.act === "prev") show(section, index - 1);
    if (act.dataset.act === "next") show(section, index + 1);
  });

  root.addEventListener("input", function (event) {
    if (!event.target.matches("[data-scrub]")) return;
    var section = activeEpisode();
    pause(section);
    show(section, parseInt(event.target.value, 10));
  });

  root.addEventListener("keydown", function (event) {
    if (event.target.matches("input[type=range]")) return;
    var keys = { ArrowLeft: -1, ArrowRight: 1 };
    var section = activeEpisode();
    if (event.target.closest(".replay-steps button") && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      var target = event.target.closest(".replay-steps button");
      var next = parseInt(target.dataset.frame, 10) + (event.key === "ArrowDown" ? 1 : -1);
      pause(section);
      show(section, next);
      section.querySelectorAll(".replay-steps button")[show(section, next)].focus();
      return;
    }
    if (keys[event.key] !== undefined && !event.target.closest("input")) {
      event.preventDefault();
      pause(section);
      show(section, parseInt(section.dataset.index, 10) + keys[event.key]);
    }
  });

  // Autoplay once the player is actually on screen, and only once.
  if (!reduceMotion && "IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      if (!entries.some(function (e) { return e.isIntersecting && e.intersectionRatio >= 0.6; })) return;
      observer.disconnect();
      play(activeEpisode());
    }, { threshold: [0, 0.6] });
    observer.observe(root);
  }

  // "Watch a run" starts the player if it has not already started.
  document.querySelectorAll("[data-play-replay]").forEach(function (link) {
    link.addEventListener("click", function () {
      if (!reduceMotion) play(activeEpisode());
    });
  });

  // Copy buttons next to commands.
  document.querySelectorAll("button.copy").forEach(function (button) {
    button.addEventListener("click", function () {
      var source = document.getElementById(button.dataset.copy);
      if (!source || !navigator.clipboard) return;
      navigator.clipboard.writeText(source.textContent).then(function () {
        button.textContent = "Copied";
        setTimeout(function () { button.textContent = "Copy"; }, 1600);
      });
    });
  });

  episodes.forEach(function (section) { show(section, 0); });
})();
