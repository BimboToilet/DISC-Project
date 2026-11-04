(function () {
  "use strict";

  var toggle = document.getElementById("toggle-upload");
  var uploadCard = document.getElementById("upload-card");
  if (toggle && uploadCard) {
    toggle.addEventListener("click", function (e) {
      e.preventDefault();
      var hidden = uploadCard.style.display === "none";
      uploadCard.style.display = hidden ? "block" : "none";
      toggle.textContent = hidden ? "Скрыть форму" : "Загрузить опрос";
    });
  }

  var form = document.getElementById("chat-form");
  if (form) {
    var teamId = form.getAttribute("data-team-id");
    var box = document.getElementById("chat-messages");
    var input = document.getElementById("chat-input");
    var lastId = 0;
    var ownId = window.CURRENT_USER_ID || null;

    Array.prototype.forEach.call(
      box.querySelectorAll("[data-msg-id]"),
      function (el) {
        var id = parseInt(el.getAttribute("data-msg-id"), 10);
        if (id > lastId) lastId = id;
      }
    );

    function el(tag, cls, text) {
      var node = document.createElement(tag);
      if (cls) node.className = cls;
      if (text !== undefined && text !== null) node.textContent = text;
      return node;
    }

    function appendMessage(m) {
      if (box.querySelector('[data-msg-id="' + m.id + '"]')) return;
      var own = m.user_id && ownId && m.user_id === ownId;
      var wrap = el("div", "chat-msg");
      if (m.kind === "system") {
        wrap.className += " chat-msg-system";
        wrap.appendChild(el("div", "chat-msg-body", m.body));
      } else {
        if (m.kind === "report") wrap.className += " chat-msg-report";
        else if (own) wrap.className += " chat-msg-own";
        var meta = el(
          "div",
          "chat-msg-meta",
          (m.kind === "report" ? "Система · " : (m.user || "Система") + " · ") + (m.time || "")
        );
        var body = el("div", "chat-msg-body", m.body);
        if (m.kind === "report" && m.meta && m.meta.team_survey_id) {
          var br = el("br");
          var link = el("a", "muted-link", "Открыть командный отчет →");
          link.setAttribute("href", "/reports/" + m.meta.team_survey_id + "/team");
          body.appendChild(br);
          body.appendChild(link);
        }
        wrap.appendChild(meta);
        wrap.appendChild(body);
      }
      wrap.setAttribute("data-msg-id", m.id);
      box.appendChild(wrap);
      box.scrollTop = box.scrollHeight;
    }

    function poll() {
      fetch("/teams/" + teamId + "/chat/poll?after=" + lastId)
        .then(function (r) {
          if (!r.ok) throw new Error("poll failed");
          return r.json();
        })
        .then(function (data) {
          (data.messages || []).forEach(function (m) {
            appendMessage(m);
            if (m.id > lastId) lastId = m.id;
          });
        })
        .catch(function () {});
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var text = (input.value || "").trim();
      if (!text) return;
      fetch("/teams/" + teamId + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: text }),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data.ok) {
            appendMessage(data.message);
            if (data.message.id > lastId) lastId = data.message.id;
            input.value = "";
            input.focus();
          }
        })
        .catch(function () {
          form.submit();
        });
    });

    box.scrollTop = box.scrollHeight;
    setInterval(poll, 4000);
    poll();
  }

  var counter = document.getElementById("notif-count");
  if (counter) {
    var refreshCount = function () {
      fetch("/notifications/unread-count")
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          counter.textContent = data.count;
          counter.setAttribute("data-count", data.count);
        })
        .catch(function () {});
    };
    refreshCount();
    setInterval(refreshCount, 15000);
  }
})();
