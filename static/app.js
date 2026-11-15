const studentSelect = document.querySelector('#student-select');
const currencySelect = document.querySelector('#currency-select');
const amountInput = document.querySelector('input[name="amount"]');

if (studentSelect && currencySelect && amountInput) {
  studentSelect.addEventListener('change', () => {
    const option = studentSelect.selectedOptions[0];
    if (option?.dataset.currency) currencySelect.value = option.dataset.currency;
    if (option?.dataset.balance) amountInput.max = (Number(option.dataset.balance) / 100).toFixed(2);
  });
}


/* Coordinated motion for counters, progress bars and key content. */
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const observeOnce = (elements, onEnter, options = {}) => {
    if (!elements.length) return;
    if (reduceMotion || !("IntersectionObserver" in window)) {
      elements.forEach(onEnter);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        onEnter(entry.target);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.18, rootMargin: "0px 0px -24px 0px", ...options });
    elements.forEach((element) => observer.observe(element));
  };

  // Count financial values from zero while preserving currency and precision.
  const counters = Array.from(document.querySelectorAll("[data-count-up]"));
  const animateCounter = (element) => {
    if (element.dataset.counted === "true") return;
    element.dataset.counted = "true";
    const original = element.textContent.trim();
    const match = original.match(/-?[\d,]+(?:\.\d+)?/);
    if (!match) return;

    const rawNumber = match[0];
    const target = Number(rawNumber.replace(/,/g, ""));
    if (!Number.isFinite(target)) return;
    const decimals = (rawNumber.split(".")[1] || "").length;
    const prefix = original.slice(0, match.index);
    const suffix = original.slice(match.index + rawNumber.length);
    const formatter = new Intl.NumberFormat(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
    const render = (value) => {
      element.textContent = prefix + formatter.format(value) + suffix;
    };
    if (reduceMotion) {
      render(target);
      return;
    }
    const duration = 1450;
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 4);
      render(target * eased);
      if (progress < 1) requestAnimationFrame(tick);
      else render(target);
    };
    requestAnimationFrame(tick);
  };
  observeOnce(counters, animateCounter, { threshold: 0.25 });

  // Fill every marked progress bar from zero to its server-rendered value.
  const progressBars = Array.from(document.querySelectorAll("[data-progress-fill]"));
  const progressTargets = new Map(progressBars.map((bar) => [
    bar,
    bar.style.width || window.getComputedStyle(bar).width
  ]));
  progressBars.forEach((bar) => {
    bar.style.width = "0%";
    bar.setAttribute("aria-hidden", "true");
  });
  observeOnce(progressBars, (bar) => {
    bar.style.width = progressTargets.get(bar);
  }, { threshold: 0.2 });

  // Bring important cards and activity rows into view with a restrained stagger.
  const motionItems = Array.from(document.querySelectorAll(
    ".preview-metric, .preview-panel, .quick-stats article, .metric-card, " +
    ".faculty-panel, .recent-panel, .faculty-progress, .report-card, " +
    ".report-table, .recent-payment, .preview-receipt"
  ));
  if (!reduceMotion && "IntersectionObserver" in window) {
    motionItems.forEach((item, index) => {
      item.classList.add("motion-ready");
      const siblings = Array.from(item.parentElement.children).filter((child) =>
        child.matches(".preview-metric, .preview-panel, .quick-stats article, .metric-card, " +
          ".faculty-panel, .recent-panel, .faculty-progress, .report-card, " +
          ".report-table, .recent-payment, .preview-receipt")
      );
      item.style.setProperty("--motion-delay", Math.min(siblings.indexOf(item), 4) * 75 + "ms");
    });
    observeOnce(motionItems, (item) => item.classList.add("motion-visible"), { threshold: 0.08 });
  }
})();
