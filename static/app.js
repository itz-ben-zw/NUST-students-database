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


/* Animate financial summary figures when their section enters the viewport. */
(() => {
  const counters = Array.from(document.querySelectorAll("[data-count-up]"));
  if (!counters.length) return;

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

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      render(target);
      return;
    }

    const duration = 1350;
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 4);
      render(target * eased);
      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        render(target);
      }
    };
    requestAnimationFrame(tick);
  };

  const sections = new Set(counters.map((counter) => counter.closest(".preview-metrics, .quick-stats") || counter));
  if (!("IntersectionObserver" in window)) {
    counters.forEach(animateCounter);
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      counters.filter((counter) => sections.has(counter.closest(".preview-metrics, .quick-stats") || counter))
        .forEach(animateCounter);
      observer.disconnect();
    });
  }, { threshold: 0.2 });

  sections.forEach((section) => observer.observe(section));
})();
