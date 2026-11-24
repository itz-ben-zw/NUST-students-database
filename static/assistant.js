(() => {
  const form = document.getElementById("assistant-form");
  if (!form) return;
  const input = document.getElementById("assistant-question");
  const messages = document.getElementById("assistant-messages");
  const status = document.getElementById("assistant-status");
  const submit = form.querySelector('button[type="submit"]');

  function addMessage(kind, text) {
    const item = document.createElement("article");
    item.className = `assistant-message assistant-message-${kind}`;
    const heading = document.createElement("strong");
    heading.textContent = kind === "user" ? "You" : "NUST AI Assistant";
    const body = document.createElement("p");
    body.textContent = text;
    item.append(heading, body);
    messages.append(item);
    messages.scrollTop = messages.scrollHeight;
  }

  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.prompt || "";
      input.focus();
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || submit.disabled) return;
    addMessage("user", question);
    input.value = "";
    submit.disabled = true;
    status.textContent = "Checking authorised records and preparing an answer…";
    try {
      const endpoint = form.dataset.endpoint || "/api/assistant/chat";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector('[name="csrf_token"]').value,
        },
        body: JSON.stringify({ question }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The assistant could not respond.");
      addMessage("bot", payload.answer);
      status.textContent = "Read-only database access. Verify important financial information in source records.";
    } catch (error) {
      addMessage("bot", error.message || "The assistant is temporarily unavailable.");
      status.textContent = "Please try again. No database records were changed.";
    } finally {
      submit.disabled = false;
      input.focus();
    }
  });
})();
