// pydata-sphinx-theme 0.20 puts its own `.primary-toggle` in the top navbar,
// which sphinx-book-theme 1.4 hides; both themes bind their click handlers to
// `document.querySelector(".primary-toggle")`, the first in the page, so the
// visible toggle in the article header is bound to nothing. Forward its
// clicks (and the secondary sidebar's) to the button the themes listen on.
document.addEventListener("DOMContentLoaded", () => {
  for (const cls of [".primary-toggle", ".secondary-toggle"]) {
    const [bound, ...others] = document.querySelectorAll(cls);
    for (const button of others) {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        bound.click();
      });
    }
  }
});
