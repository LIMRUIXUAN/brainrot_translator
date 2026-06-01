if (!window.__brainrotPetBubbleLoaded) {
  window.__brainrotPetBubbleLoaded = true;

  (function () {
  class BrainrotPetBubble {
    constructor() {
      this.container = null;
      this.state = "hidden";
      this.autoCloseTimer = null;
      this.countdownTimer = null;
    }

    ensureContainer() {
      if (this.container) {
        return this.container;
      }

      const container = document.createElement("div");
      container.id = "brainrot-pet-bubble";
      container.setAttribute("role", "dialog");
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
      this.container = container;
      this.makeDraggable(container, container);
      return container;
    }

    makeDraggable(container, handle) {
      if (!handle) {
        return;
      }
      let dragState = null;

      function finishDrag() {
        if (!dragState) {
          return;
        }
        handle.classList.remove("is-dragging");
        dragState = null;
      }

      handle.addEventListener("pointerdown", (event) => {
        // Do not drag if clicking input, button, select, details, or summary
        const target = event.target;
        if (
          target.closest("button, a, input, details, summary, select, img, [data-brainrot-copy], [data-brainrot-recheck], [data-brainrot-close]")
        ) {
          return;
        }
        if (event.button !== 0) {
          return;
        }

        const rect = container.getBoundingClientRect();
        dragState = {
          offsetX: event.clientX - rect.left,
          offsetY: event.clientY - rect.top
        };
        handle.classList.add("is-dragging");
        handle.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });

      handle.addEventListener("pointermove", (event) => {
        if (!dragState) {
          return;
        }

        const left = event.clientX - dragState.offsetX;
        const top = event.clientY - dragState.offsetY;

        // Constraint bounds (stay in screen viewport)
        const maxLeft = window.innerWidth - container.offsetWidth;
        const maxTop = window.innerHeight - container.offsetHeight;

        container.style.left = `${Math.max(0, Math.min(maxLeft, left))}px`;
        container.style.top = `${Math.max(0, Math.min(maxTop, top))}px`;
        container.style.right = "auto";
        container.style.bottom = "auto";
      });

      handle.addEventListener("pointerup", finishDrag);
      handle.addEventListener("pointercancel", finishDrag);
    }

    getRect(anchor) {
      if (anchor instanceof DOMRect) {
        return anchor;
      }
      if (anchor && typeof anchor.getBoundingClientRect === "function") {
        return anchor.getBoundingClientRect();
      }
      return new DOMRect(window.innerWidth / 2, 120, 1, 1);
    }

    positionNearAnchor(anchor) {
      const container = this.ensureContainer();
      const rect = this.getRect(anchor);
      const viewportPadding = 16;
      const availableHeight = Math.max(220, window.innerHeight - viewportPadding * 2);
      container.style.maxHeight = `${availableHeight}px`;

      const bubbleHeight = container.offsetHeight || 220;
      const bubbleWidth = container.offsetWidth || 380;
      const maxTop = Math.max(viewportPadding, window.innerHeight - bubbleHeight - viewportPadding);
      const topAbove = rect.top - bubbleHeight - 12;
      const topBelow = rect.bottom + 12;
      let top = topAbove;

      if (topAbove < viewportPadding) {
        top = topBelow;
      }
      top = Math.min(maxTop, Math.max(viewportPadding, top));

      const maxLeft = Math.max(viewportPadding, window.innerWidth - bubbleWidth - viewportPadding);
      const preferredLeft = rect.left + rect.width / 2 - bubbleWidth / 2;
      const left = Math.min(maxLeft, Math.max(viewportPadding, preferredLeft));
      container.style.top = `${top}px`;
      container.style.left = `${left}px`;
    }

    escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    render(anchor, html, state) {
      const container = this.ensureContainer();
      this.clearAutoCloseTimers();
      container.innerHTML = html;
      container.style.display = "block";
      this.state = state;
      this.positionNearAnchor(anchor);
    }

    clearAutoCloseTimers() {
      if (this.autoCloseTimer) {
        window.clearTimeout(this.autoCloseTimer);
        this.autoCloseTimer = null;
      }
      if (this.countdownTimer) {
        window.clearInterval(this.countdownTimer);
        this.countdownTimer = null;
      }
    }

    isLoading() {
      return this.state === "loading";
    }

    _sentimentColor(label) {
      const map = {
        positive: "#22c55e",
        negative: "#ef4444",
        neutral: "#a3a3a3",
        mixed: "#f59e0b",
        unclear: "#6b7280"
      };
      return map[(label || "").toLowerCase()] || map.unclear;
    }

    showLoadingState(anchor, message = "Analyzing...") {
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-loading">
            <div class="brainrot-bubble-avatar">🧠</div>
            <div>
              <div class="brainrot-bubble-kicker">Floating Pet</div>
              <div class="brainrot-bubble-heading">Working</div>
              <div class="brainrot-bubble-copy">${this.escapeHtml(message)}</div>
            </div>
          </div>
        </div>
      `,
        "loading"
      );
    }

    showError(anchor, message) {
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Floating Pet</div>
          <div class="brainrot-bubble-heading">Analysis unavailable</div>
          <div class="brainrot-bubble-copy brainrot-bubble-error">${this.escapeHtml(message)}</div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "error"
      );
      this.bindCloseButton();
    }

    showInfo(anchor, title, message, actionLabel, onAction) {
      const actionButton =
        typeof onAction === "function" && actionLabel
          ? `<button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-info-action>${this.escapeHtml(actionLabel)}</button>`
          : "";
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Floating Pet</div>
          <div class="brainrot-bubble-heading">${this.escapeHtml(title)}</div>
          <div class="brainrot-bubble-copy">${this.escapeHtml(message)}</div>
          <div class="brainrot-bubble-actions">
            ${actionButton}
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "info"
      );
      this.bindCloseButton();
      this.bindInfoActionButton(onAction);
    }

    showTimedInfo(anchor, title, message, durationSeconds = 3) {
      const safeDuration = Math.max(1, Math.round(Number(durationSeconds) || 3));
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Floating Pet</div>
          <div class="brainrot-bubble-heading">${this.escapeHtml(title)}</div>
          <div class="brainrot-bubble-copy">${this.escapeHtml(message)}</div>
          <div class="brainrot-bubble-countdown" aria-live="polite">
            <div class="brainrot-bubble-countdown-label" data-brainrot-countdown-label>Closing in ${safeDuration}s</div>
            <div class="brainrot-bubble-countdown-track">
              <div class="brainrot-bubble-countdown-line" data-brainrot-countdown-line></div>
            </div>
          </div>
        </div>
      `,
        "timed-info"
      );

      const label = this.container?.querySelector("[data-brainrot-countdown-label]");
      const line = this.container?.querySelector("[data-brainrot-countdown-line]");
      const startedAt = Date.now();
      const durationMs = safeDuration * 1000;

      this.countdownTimer = window.setInterval(() => {
        const elapsedMs = Date.now() - startedAt;
        const remainingMs = Math.max(0, durationMs - elapsedMs);
        const remainingSeconds = Math.ceil(remainingMs / 1000);
        const progress = Math.max(0, remainingMs / durationMs);

        if (label) {
          label.textContent = `Closing in ${remainingSeconds}s`;
        }
        if (line) {
          line.style.transform = `scaleX(${progress})`;
        }
      }, 100);

      this.autoCloseTimer = window.setTimeout(() => {
        this.hide();
      }, durationMs);
    }

    showConfirmation(anchor, title, message, confirmLabel, cancelLabel, onConfirm, onCancel) {
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Floating Pet</div>
          <div class="brainrot-bubble-heading">${this.escapeHtml(title)}</div>
          <div class="brainrot-bubble-copy">${this.escapeHtml(message)}</div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-confirm>${this.escapeHtml(confirmLabel)}</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-cancel>${this.escapeHtml(cancelLabel)}</button>
          </div>
        </div>
      `,
        "confirm"
      );
      this.bindDecisionButtons(onConfirm, onCancel);
    }

    /* ── Phase 2: Redesigned rich text result ────────────────────────── */
    showTextAnalysisResult(anchor, result, originalText, onRecheck) {
      const confidence = Math.round((result.confidence_score || 0) * 100);
      const equivalent = result.equivalent_text || originalText;
      const explanation = result.formal_explanation || "No expanded explanation was returned.";
      const sentiment = result.sentiment_label || "unclear";
      const sentimentColor = this._sentimentColor(sentiment);
      const chips = [
        `<div class="brainrot-bubble-chip">Confidence ${confidence}%</div>`,
        `<div class="brainrot-bubble-chip" style="border-color:${sentimentColor};color:${sentimentColor}">● ${this.escapeHtml(sentiment)}</div>`
      ];
      if (result.flagged_for_review) {
        chips.push(`<div class="brainrot-bubble-chip brainrot-bubble-chip--warn">Queued for review</div>`);
      }

      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Highlighted Text</div>
          <div class="brainrot-bubble-heading">Brainrot Translation</div>
          <div class="brainrot-bubble-translation-card">
            <div class="brainrot-bubble-original">"${this.escapeHtml(originalText)}"</div>
            <div class="brainrot-bubble-arrow">⟶</div>
            <div class="brainrot-bubble-translated">"${this.escapeHtml(equivalent)}"</div>
          </div>
          <details class="brainrot-bubble-details">
            <summary class="brainrot-bubble-summary">Explain Context</summary>
            <div class="brainrot-bubble-details-content">
              ${this.escapeHtml(explanation)}
            </div>
          </details>
          <div class="brainrot-bubble-meta">
            ${chips.join("")}
          </div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-copy-original title="Copy original text">Copy Original</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-copy title="Copy translation">Copy Translation</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-recheck>Recheck</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "text"
      );
      this.bindCloseButton();
      this.bindCopyButton(equivalent);
      this.bindCopyOriginalButton(originalText);
      this.bindRecheckButton(onRecheck);
    }

    /* ── Phase 2: Redesigned rich image result ───────────────────────── */
    showImageAnalysisResult(anchor, result, previewSrc) {
      const confidence = Math.round((result.confidence_score || 0) * 100);
      const meaning = result.brainrot_meaning || "Unclear";
      const explanation =
        result.formal_explanation ||
        result.equivalent_text ||
        "No formal explanation was returned.";
      const chips = [`<div class="brainrot-bubble-chip">Confidence ${confidence}%</div>`];
      if (result.used_frame_fallback) {
        chips.push(`<div class="brainrot-bubble-chip brainrot-bubble-chip--fallback">GIF first-frame fallback</div>`);
      }
      if (result.flagged_for_review) {
        chips.push(`<div class="brainrot-bubble-chip brainrot-bubble-chip--warn">Queued for review</div>`);
      }

      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-preview-layout">
            <img
              class="brainrot-bubble-preview-image"
              src="${this.escapeHtml(previewSrc)}"
              alt="Brainrot media preview"
            />
            <div>
              <div class="brainrot-bubble-kicker">Image or GIF</div>
              <div class="brainrot-bubble-heading">This meme means</div>
              <div class="brainrot-bubble-value">"${this.escapeHtml(meaning)}"</div>
              <details class="brainrot-bubble-details">
                <summary class="brainrot-bubble-summary">Explain Context</summary>
                <div class="brainrot-bubble-details-content">
                  ${this.escapeHtml(explanation)}
                </div>
              </details>
              <div class="brainrot-bubble-meta">
                ${chips.join("")}
              </div>
            </div>
          </div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-copy>Copy Explanation</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "image"
      );
      this.bindCloseButton();
      this.bindCopyButton(explanation);
    }

    bindCloseButton() {
      const button = this.container?.querySelector("[data-brainrot-close]");
      if (button) {
        button.addEventListener("click", () => this.hide(), { once: true });
      }
    }

    bindCopyButton(text) {
      const button = this.container?.querySelector("[data-brainrot-copy]");
      if (!button) {
        return;
      }

      button.addEventListener(
        "click",
        async () => {
          try {
            await navigator.clipboard.writeText(text);
            button.textContent = "Copied ✓";
          } catch (error) {
            button.textContent = "Copy failed";
          }
        },
        { once: true }
      );
    }

    bindCopyOriginalButton(text) {
      const button = this.container?.querySelector("[data-brainrot-copy-original]");
      if (!button) {
        return;
      }

      button.addEventListener(
        "click",
        async () => {
          try {
            await navigator.clipboard.writeText(text);
            button.textContent = "Copied ✓";
          } catch (error) {
            button.textContent = "Copy failed";
          }
        },
        { once: true }
      );
    }

    bindRecheckButton(onRecheck) {
      const button = this.container?.querySelector("[data-brainrot-recheck]");
      if (!button) {
        return;
      }

      if (typeof onRecheck !== "function") {
        button.disabled = true;
        return;
      }

      button.addEventListener(
        "click",
        async () => {
          button.textContent = "Rechecking";
          button.disabled = true;
          await onRecheck();
        },
        { once: true }
      );
    }

    bindInfoActionButton(onAction) {
      const button = this.container?.querySelector("[data-brainrot-info-action]");
      if (!button || typeof onAction !== "function") {
        return;
      }

      button.addEventListener(
        "click",
        async () => {
          button.textContent = "Rechecking";
          button.disabled = true;
          await onAction();
        },
        { once: true }
      );
    }

    bindDecisionButtons(onConfirm, onCancel) {
      const confirmButton = this.container?.querySelector("[data-brainrot-confirm]");
      const cancelButton = this.container?.querySelector("[data-brainrot-cancel]");

      if (confirmButton) {
        confirmButton.addEventListener(
          "click",
          async () => {
            if (typeof onConfirm === "function") {
              await onConfirm();
            }
          },
          { once: true }
        );
      }

      if (cancelButton) {
        cancelButton.addEventListener(
          "click",
          () => {
            if (typeof onCancel === "function") {
              onCancel();
            } else {
              this.hide();
            }
          },
          { once: true }
        );
      }
    }

    hide() {
      this.clearAutoCloseTimers();
      if (this.container) {
        this.container.style.display = "none";
      }
      this.state = "hidden";
    }
  }

  window.BrainrotPetBubble = BrainrotPetBubble;
  })();
}
