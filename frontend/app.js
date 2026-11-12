async function startTutor() {
  const session = await fetch("/auth/me");
  if (!session.ok) { location.replace("/login"); return; }
  const account = await session.json();
  document.getElementById("account-name").textContent = "Signed in as " + account.username;
  document.getElementById("logout").addEventListener("click", async () => {
    const logout = document.getElementById("logout");
    logout.disabled = true;
    try {
      const response = await fetch("/auth/logout", {
        method: "POST", headers: { "X-CSRF-Token": account.csrf_token }
      });
      if (!response.ok && response.status !== 401) throw new Error("Sign out failed. Refresh and try again.");
      location.replace("/login");
    } catch (error) {
      document.getElementById("answer").textContent = error.message;
      logout.disabled = false;
    }
  });

    const form = document.getElementById("question-form");
    const question = document.getElementById("question");
    const button = document.getElementById("submit");
    const answer = document.getElementById("answer");

    const newChat = document.getElementById("new-chat");
    const conversation = document.getElementById("conversation");
    let history = [];

    const lessons = [{"id": "navigation", "title": "Find your way", "description": "Use pwd to print your current directory, ls to list contents, and cd to move between directories.", "example": "pwd\nls\ncd Documents\ncd ..", "quiz": "Which command moves to the parent directory?", "choices": ["pwd", "cd ..", "ls"], "correct": 1, "explanation": "cd .. moves up one directory. The two dots refer to the parent directory."}, {"id": "files", "title": "Files and folders", "description": "mkdir creates a directory, touch creates an empty file if it does not exist, and cp copies files. Practice in a dedicated folder.", "example": "mkdir -p linux-practice\ncd linux-practice\ntouch notes.txt\ncp notes.txt notes-copy.txt", "quiz": "Which command copies notes.txt to backup.txt?", "choices": ["cd notes.txt backup.txt", "mkdir backup.txt", "cp notes.txt backup.txt"], "correct": 2, "explanation": "cp takes a source and destination. Existing destination files can be overwritten."}, {"id": "reading", "title": "Read text files", "description": "cat prints a file, head shows its first lines, and less lets you browse longer files. Press q to exit less.", "example": "cat /etc/os-release\nhead -n 5 /etc/os-release\nless /etc/os-release", "quiz": "How do you exit less?", "choices": ["Press q", "Press the space bar", "Type cd"], "correct": 0, "explanation": "Press q to quit less and return to the terminal."}, {"id": "search", "title": "Search text", "description": "grep finds matching lines. Use -i to ignore capitalization and -n to include line numbers.", "example": "grep -i 'name' /etc/os-release\ngrep -n 'ID' /etc/os-release", "quiz": "Which grep option ignores capitalization?", "choices": ["-n", "-i", "-l"], "correct": 1, "explanation": "grep -i matches without distinguishing uppercase and lowercase."}, {"id": "permissions", "title": "Permissions", "description": "Linux tracks read, write, and execute access for the owner, group, and others. chmod u+x adds execute permission for the owner.", "example": "ls -l notes.txt\n# For an existing script you created and trust:\nchmod u+x my-script.sh", "quiz": "What does chmod u+x my-script.sh add?", "choices": ["Write access for everyone", "A new owner", "Execute permission for the owner"], "correct": 2, "explanation": "u means owner, + means add, and x means execute."}, {"id": "pipes", "title": "Combine commands", "description": "A pipe sends output to the next command. The > operator writes to a file and overwrites existing contents; >> appends.", "example": "printf 'apple\\nbanana\\napricot\\n' | grep '^a'\nprintf 'apple\\nbanana\\napricot\\n' | grep '^a' | wc -l", "quiz": "What does the pipe symbol | do?", "choices": ["Sends output to the next command", "Deletes the previous command", "Always saves output to a file"], "correct": 0, "explanation": "A pipe connects standard output of the left command to standard input of the right command."}];
    let completed = new Set();
    try {
      const saved = JSON.parse(localStorage.getItem("linux-tutor-progress:" + account.username) || "[]");
      if (Array.isArray(saved)) completed = new Set(saved.filter(id => lessons.some(l => l.id === id)));
    } catch {}
    let activeLesson = 0;
    const tabs = document.getElementById("lesson-tabs");

    function renderLesson() {
      const lesson = lessons[activeLesson];
      tabs.replaceChildren();
      lessons.forEach((item, index) => {
        const tab = document.createElement("button");
        tab.type = "button";
        tab.className = "lesson-tab";
        tab.textContent = (index + 1) + ". " + item.title + (completed.has(item.id) ? " ✓" : "");
        tab.setAttribute("aria-pressed", String(index === activeLesson));
        tab.addEventListener("click", () => { activeLesson = index; renderLesson(); });
        tabs.append(tab);
      });
      document.getElementById("progress").value = completed.size;
      document.getElementById("progress-label").textContent = completed.size === lessons.length
        ? "All 6 lessons complete. Keep practicing with your tutor!"
        : completed.size + " of 6 lessons complete";
      document.getElementById("lesson-title").textContent = lesson.title;
      document.getElementById("lesson-description").textContent = lesson.description;
      document.getElementById("lesson-example").textContent = lesson.example;
      document.getElementById("quiz-question").textContent = lesson.quiz;
      document.getElementById("feedback").textContent = "";
      const choices = document.getElementById("quiz-choices");
      choices.replaceChildren();
      lesson.choices.forEach((text, index) => {
        const choice = document.createElement("button");
        choice.type = "button";
        choice.className = "choice";
        choice.textContent = text;
        choice.addEventListener("click", () => {
          if (index === lesson.correct) {
            completed.add(lesson.id);
            let saved = true;
            try { localStorage.setItem("linux-tutor-progress:" + account.username, JSON.stringify([...completed])); }
            catch { saved = false; }
            renderLesson();
            const correct = document.getElementById("quiz-choices").children[index];
            correct.classList.add("correct");
            correct.focus();
            document.getElementById("feedback").textContent = "Correct! " + lesson.explanation +
              (saved ? "" : " Progress could not be saved in this browser.");
          } else {
            choice.classList.add("incorrect");
            document.getElementById("feedback").textContent = "Try again. " + lesson.explanation;
          }
        });
        choices.append(choice);
      });
      document.getElementById("next-lesson").disabled = activeLesson === lessons.length - 1;
    }

    document.getElementById("next-lesson").addEventListener("click", () => {
      if (activeLesson < lessons.length - 1) { activeLesson++; renderLesson(); }
    });
    document.getElementById("explain").addEventListener("click", () => {
      if (button.disabled) return;
      question.value = "Explain this Linux topic for a beginner, with a safe practice example: " +
        lessons[activeLesson].title;
      question.focus();
      question.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    renderLesson();



    function showMessage(label, text) {
      const entry = document.createElement("section");
      const heading = document.createElement("h2");
      const body = document.createElement("div");
      heading.textContent = label;
      body.textContent = text;
      body.className = "message-body";
      entry.append(heading, body);
      conversation.append(entry);
      return body;
    }

    newChat.addEventListener("click", () => {
      history = [];
      conversation.replaceChildren();
      answer.textContent = "";
      question.value = "";
      question.focus();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      const text = question.value.trim();
      if (!text) {
        answer.textContent = "Please enter a question.";
        return;
      }

      button.disabled = true;
      newChat.disabled = true;
      answer.textContent = "Thinking…";

      let tutorBody = null;
      try {
        const response = await fetch("/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": account.csrf_token },
          body: JSON.stringify({ question: text, history })
        });

        if (response.status === 401) { location.assign("/login"); return; }
        if (!response.ok) {
          const data = await response.json();
          throw new Error(typeof data.detail === "string"
            ? data.detail : "The request failed. Please try again.");
        }
        if (!response.body) throw new Error("Streaming is unavailable in this browser.");

        showMessage("You", text);
        tutorBody = showMessage("Tutor", "");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let reply = "";
        let done = false;

        function processLine(line) {
          if (!line.trim()) return;
          const item = JSON.parse(line);
          if (item.error) throw new Error(item.error);
          if (item.token) {
            reply += item.token;
            tutorBody.textContent = reply;
            answer.textContent = "Writing…";
          }
          if (item.done) done = true;
        }

        try {
          while (true) {
            const part = await reader.read();
            buffer += decoder.decode(part.value, { stream: !part.done });
            let newline;
            while ((newline = buffer.indexOf("\n")) !== -1) {
              processLine(buffer.slice(0, newline));
              buffer = buffer.slice(newline + 1);
            }
            if (part.done) break;
          }
          if (buffer.trim()) processLine(buffer);
          if (!done || !reply.trim()) throw new Error("The response ended early. Please try again.");
        } finally {
          await reader.cancel().catch(() => {});
          reader.releaseLock();
        }

        history.push(
          { role: "user", content: text },
          { role: "assistant", content: reply.slice(0, 16000) }
        );
        history = history.slice(-12);
        question.value = "";
        answer.textContent = "";
      } catch (error) {
        if (tutorBody) tutorBody.textContent += "\n[Response incomplete — not saved to chat memory.]";
        answer.textContent = `Could not get an answer: ${error.message}`;
      } finally {
        button.disabled = false;
        newChat.disabled = false;
      }
    });

}
startTutor().catch(() => {
  document.getElementById("answer").textContent = "Unable to load your session. Refresh and try again.";
});
