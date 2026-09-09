// Progressive enhancement only: the site must render and work with this file absent.
// Loaded with `defer`, so the DOM is ready by the time this runs.

// Keep the footer year current without a build step.
for (const el of document.querySelectorAll('[data-year]')) {
  el.textContent = String(new Date().getFullYear());
}
