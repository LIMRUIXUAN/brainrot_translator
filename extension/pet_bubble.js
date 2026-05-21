if (!window.__brainrotPetBubbleLoaded) {
  window.__brainrotPetBubbleLoaded = true;

  (function () {
  class BrainrotPetBubble {
    constructor() {
      this.container = null;
      this.state = "hidden";
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
      return container;
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
      const bubbleHeight = container.offsetHeight || 220;
      const bubbleWidth = container.offsetWidth || 380;
      let top = rect.top - bubbleHeight - 12;
      if (top < 12) {
        top = Math.min(window.innerHeight - bubbleHeight - 12, rect.bottom + 12);
      }
      const maxLeft = Math.max(12, window.innerWidth - bubbleWidth - 12);
      const preferredLeft = rect.left + rect.width / 2 - bubbleWidth / 2;
      const left = Math.min(maxLeft, Math.max(12, preferredLeft));
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
      container.innerHTML = html;
      container.style.display = "block";
      this.state = state;
      this.positionNearAnchor(anchor);
    }

    isLoading() {
      return this.state === "loading";
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

    showInfo(anchor, title, message) {
      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Floating Pet</div>
          <div class="brainrot-bubble-heading">${this.escapeHtml(title)}</div>
          <div class="brainrot-bubble-copy">${this.escapeHtml(message)}</div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "info"
      );
      this.bindCloseButton();
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

    showTextAnalysisResult(anchor, result, originalText) {
      const confidence = Math.round((result.confidence_score || 0) * 100);
      const equivalent = result.equivalent_text || originalText;
      const explanation = result.formal_explanation || "No expanded explanation was returned.";
      const sentiment = result.sentiment_label || "unclear";
      const rationale = result.sentiment_rationale || "No sentiment rationale was returned.";
      const chips = [
        `<div class="brainrot-bubble-chip">Confidence ${confidence}%</div>`,
        `<div class="brainrot-bubble-chip">Sentiment ${this.escapeHtml(sentiment)}</div>`
      ];
      if (result.flagged_for_review) {
        chips.push(`<div class="brainrot-bubble-chip brainrot-bubble-chip--warn">Queued for review</div>`);
      }

      this.render(
        anchor,
        `
        <div class="brainrot-bubble-shell">
          <div class="brainrot-bubble-kicker">Highlighted Text</div>
          <div class="brainrot-bubble-heading">Formal translation</div>
          <div class="brainrot-bubble-copy">"${this.escapeHtml(originalText)}"</div>
          <div class="brainrot-bubble-block">
            <div class="brainrot-bubble-label">Equivalent Text</div>
            <div class="brainrot-bubble-value brainrot-bubble-value--formal">"${this.escapeHtml(equivalent)}"</div>
          </div>
          <div class="brainrot-bubble-block">
            <div class="brainrot-bubble-label">Context</div>
            <div class="brainrot-bubble-copy">${this.escapeHtml(explanation)}</div>
          </div>
          <div class="brainrot-bubble-block">
            <div class="brainrot-bubble-label">Sentiment Rationale</div>
            <div class="brainrot-bubble-copy">${this.escapeHtml(rationale)}</div>
          </div>
          <div class="brainrot-bubble-meta">
            ${chips.join("")}
          </div>
          <div class="brainrot-bubble-actions">
            <button class="brainrot-bubble-button brainrot-bubble-button--copy" data-brainrot-copy>Copy Translation</button>
            <button class="brainrot-bubble-button brainrot-bubble-button--close" data-brainrot-close>Close</button>
          </div>
        </div>
      `,
        "text"
      );
      this.bindCloseButton();
      this.bindCopyButton(equivalent);
    }

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
              <div class="brainrot-bubble-block">
                <div class="brainrot-bubble-label">Formal English</div>
                <div class="brainrot-bubble-value brainrot-bubble-value--formal">"${this.escapeHtml(explanation)}"</div>
              </div>
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
            button.textContent = "Copied";
          } catch (error) {
            button.textContent = "Copy failed";
          }
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
      if (this.container) {
        this.container.style.display = "none";
      }
      this.state = "hidden";
    }
  }

  window.BrainrotPetBubble = BrainrotPetBubble;
  })();
}
