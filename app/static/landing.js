/* ──────────────────────────────────────────────────────────────────
   Annotation Wizard — Landing Page Logic & Auth Flow
   ────────────────────────────────────────────────────────────────── */

(function () {
  "use strict";

  const STORAGE_KEY = "aw-api-key";

  // Elements
  const demoBtn = document.querySelector("#primary-hero-btn");
  const apiKeyInput = document.querySelector("#landing-api-key");
  const toggleVisibilityBtn = document.querySelector("#toggle-key-visibility");
  const eyeIcon = document.querySelector("#eye-icon");
  const apiKeyForm = document.querySelector("#api-key-form");
  const verifyBtn = document.querySelector("#verify-key-btn");
  const btnText = document.querySelector("#btn-text");
  const loginSpinner = document.querySelector("#login-spinner");
  const loginMessage = document.querySelector("#login-message");

  // Access Request Elements
  const accessForm = document.querySelector("#access-form");
  const submitRequestBtn = document.querySelector("#submit-request-btn");
  const requestBtnText = document.querySelector("#request-btn-text");
  const requestSpinner = document.querySelector("#request-spinner");
  const requestFeedback = document.querySelector("#request-feedback");
  const useTextarea = document.querySelector("#req-use");
  const useCharCount = document.querySelector("#use-char-count");

  // Field error elements
  const errName = document.querySelector("#err-name");
  const errEmail = document.querySelector("#err-email");
  const errOrg = document.querySelector("#err-org");
  const errUse = document.querySelector("#err-use");

  // Check URL params for session errors
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get("error") === "auth_failed" || urlParams.get("error") === "revoked") {
    showLoginMessage(
      "Your API key session was revoked or invalid. Please enter an active key.",
      "error"
    );
  }

  // try demo access button

  console.log("demoBtn", demoBtn);
  let demoKey = false;
  if (demoBtn) {
    console.log("hello there");
    demoBtn.addEventListener("click", async (e) => {
      // e.preventDefault();
      const response = await fetch("/auth/demo-api-key", {
        method: "POST"
      });
      if (response.ok) {
        const data = await response.json();
        apiKeyInput.value = data.demo_key;
        demoKey = true;
        console.log(response);
      }
      // document.querySelector("#login-panel").scrollIntoView({ behavior: "smooth" });
    });
  }
  if (demoKey && apiKeyInput) {
    apiKeyInput.value = "demo-key";
  }

  // Pre-fill existing session key if available
  const existingKey = sessionStorage.getItem(STORAGE_KEY);
  if (existingKey && apiKeyInput) {
    apiKeyInput.value = existingKey;
  }

  // ─── 1. Password Visibility Toggle ───
  if (toggleVisibilityBtn && apiKeyInput) {
    toggleVisibilityBtn.addEventListener("click", () => {
      const isPassword = apiKeyInput.type === "password";

      apiKeyInput.type = isPassword ? "text" : "password";
      toggleVisibilityBtn.setAttribute("aria-label", isPassword ? "Hide API key" : "Show API key");

      if (isPassword) {
        // Eye-off icon
        eyeIcon.innerHTML = `
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
          <line x1="1" y1="1" x2="23" y2="23"></line>
        `;
      } else {
        // Normal eye icon
        eyeIcon.innerHTML = `
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
          <circle cx="12" cy="12" r="3"></circle>
        `;
      }
    });
  }

  // ─── 2. Helpers ───
  function showLoginMessage(message, type) {
    loginMessage.textContent = message;
    loginMessage.className = `login-message-box ${type}`;
    loginMessage.classList.remove("hidden");
  }

  function hideLoginMessage() {
    loginMessage.textContent = "";
    loginMessage.className = "login-message-box hidden";
  }

  function showRequestFeedback(message, type) {
    requestFeedback.textContent = message;
    requestFeedback.className = `request-feedback ${type}`;
    requestFeedback.classList.remove("hidden");
  }

  function hideRequestFeedback() {
    requestFeedback.textContent = "";
    requestFeedback.className = "request-feedback hidden";
  }

  async function parseErrorResponse(response) {
    try {
      const data = await response.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((err) => err.msg || err.message || JSON.stringify(err)).join(", ");
      }
      return "The server rejected the request.";
    } catch {
      return `Server responded with HTTP ${response.status}.`;
    }
  }

  // ─── 3. API Key Verification & Redirect ───
  if (apiKeyForm) {
    apiKeyForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideLoginMessage();

      const rawKey = apiKeyInput.value.trim();
      if (!rawKey) {
        showLoginMessage("Please enter an API key to continue.", "error");
        apiKeyInput.focus();
        return;
      }

      // Loading state
      verifyBtn.disabled = true;
      loginSpinner.classList.remove("hidden");
      btnText.textContent = "Verifying key…";

      try {
        const response = await fetch("/auth/me", {
          method: "GET",
          headers: {
            "X-API-Key": rawKey,
          },
          cache: "no-store",
        });

        if (response.ok) {
          const clientData = await response.json();
          // Store key in sessionStorage for this browser tab
          sessionStorage.setItem(STORAGE_KEY, rawKey);
          sessionStorage.removeItem("aw-guide-dismissed");
          sessionStorage.setItem("aw-show-welcome-modal", "true");

          const clientName = clientData && clientData.name ? clientData.name : "client";
          showLoginMessage(
            `Key verified for ${clientName}! Redirecting to workspace…`,
            "success"
          );

          // Brief delay so user sees confirmed success before navigating
          setTimeout(() => {
            window.location.href = "/workspace";
          }, 600);
          return;
        }

        if (response.status === 401 || response.status === 403) {
          sessionStorage.removeItem(STORAGE_KEY);
          const detail = await parseErrorResponse(response);
          showLoginMessage(
            `Authentication failed: ${detail}. Please check your key or request access below.`,
            "error"
          );
        } else {
          const detail = await parseErrorResponse(response);
          showLoginMessage(`Temporary service error: ${detail}. Please retry.`, "error");
        }
      } catch (networkError) {
        showLoginMessage(
          "Temporary service error: Unable to reach the server. Please check your network and try again.",
          "error"
        );
      } finally {
        verifyBtn.disabled = false;
        loginSpinner.classList.add("hidden");
        btnText.textContent = "Verify key and continue";
      }
    });
  }

  // ─── 4. Access Request Form Validation & Submission ───
  if (useTextarea && useCharCount) {
    useTextarea.addEventListener("input", () => {
      useCharCount.textContent = useTextarea.value.length;
    });
  }

  function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  }

  function clearFieldErrors() {
    [errName, errEmail, errOrg, errUse].forEach((el) => {
      if (el) el.textContent = "";
    });
  }

  if (accessForm) {
    accessForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearFieldErrors();
      hideRequestFeedback();

      const nameInput = document.querySelector("#req-name");
      const emailInput = document.querySelector("#req-email");
      const orgInput = document.querySelector("#req-org");
      const useInput = document.querySelector("#req-use");

      const nameVal = nameInput ? nameInput.value.trim() : "";
      const emailVal = emailInput ? emailInput.value.trim() : "";
      const orgVal = orgInput ? orgInput.value.trim() : "";
      const useVal = useInput ? useInput.value.trim() : "";

      let hasError = false;

      if (!nameVal) {
        errName.textContent = "Name is required.";
        hasError = true;
      } else if (nameVal.length > 100) {
        errName.textContent = "Name cannot exceed 100 characters.";
        hasError = true;
      }

      if (!emailVal) {
        errEmail.textContent = "Email is required.";
        hasError = true;
      } else if (!validateEmail(emailVal)) {
        errEmail.textContent = "Please enter a valid email address.";
        hasError = true;
      } else if (emailVal.length > 255) {
        errEmail.textContent = "Email cannot exceed 255 characters.";
        hasError = true;
      }

      if (orgVal.length > 100) {
        errOrg.textContent = "Organization cannot exceed 100 characters.";
        hasError = true;
      }

      if (!useVal) {
        errUse.textContent = "Please describe your intended use.";
        hasError = true;
      } else if (useVal.length < 5) {
        errUse.textContent = "Please provide at least 5 characters.";
        hasError = true;
      } else if (useVal.length > 1000) {
        errUse.textContent = "Description cannot exceed 1000 characters.";
        hasError = true;
      }

      if (hasError) return;

      // Submit to backend
      submitRequestBtn.disabled = true;
      requestSpinner.classList.remove("hidden");
      requestBtnText.textContent = "Submitting request…";

      try {
        const response = await fetch("/auth/access-requests", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            name: nameVal,
            email: emailVal,
            organization: orgVal || null,
            intended_use: useVal,
          }),
        });

        if (response.status === 201) {
          showRequestFeedback(
            "Thank you! Your access request has been submitted successfully. The project owner will review it shortly.",
            "success"
          );
          accessForm.reset();
          if (useCharCount) useCharCount.textContent = "0";
        } else {
          const detail = await parseErrorResponse(response);
          showRequestFeedback(`Request failed: ${detail}`, "error");
        }
      } catch (err) {
        showRequestFeedback(
          "Temporary service error: Unable to submit request. Please check your network and try again.",
          "error"
        );
      } finally {
        submitRequestBtn.disabled = false;
        requestSpinner.classList.add("hidden");
        requestBtnText.textContent = "Submit Access Request";
      }
    });
  }
})();

