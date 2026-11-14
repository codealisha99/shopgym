// Progressive enhancement only: every form works without JS. Dialogs open via data-open.
document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-open]");
  if (opener) {
    const dialog = document.getElementById(opener.dataset.open);
    if (dialog && dialog.showModal) dialog.showModal();
  }
  const closer = event.target.closest("[data-close]");
  if (closer) closer.closest("dialog")?.close();
  const backdrop = event.target.matches("dialog.modal") ? event.target : null;
  if (backdrop) backdrop.close();
});
