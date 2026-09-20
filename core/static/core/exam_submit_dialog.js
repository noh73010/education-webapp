(() => {
  const dialog = document.getElementById('final-submit-dialog');
  const openButton = document.getElementById('open-final-submit-dialog');
  const cancelButton = document.getElementById('cancel-final-submit');
  const answerForm = document.getElementById('mission-answer-form');
  const answeredOutput = document.getElementById('final-answered-count');
  const unansweredOutput = document.getElementById('final-unanswered-count');
  const unansweredWarning = document.getElementById('final-unanswered-warning');
  if (!dialog || !openButton || !cancelButton) return;

  const currentFormHasAnswer = () => {
    if (!answerForm) return false;
    const answerFields = [...answerForm.querySelectorAll(
      '[name="submitted_answer"], [name="submitted_answers"], [name="is_correct"]',
    )];
    return answerFields.some((field) => (
      (field.type === 'radio' || field.type === 'checkbox')
        ? field.checked
        : Boolean(field.value.trim())
    ));
  };

  openButton.addEventListener('click', () => {
    const storedAnswered = Number(openButton.dataset.answeredCount || 0);
    const total = Number(openButton.dataset.totalCount || 0);
    const wasAnswered = openButton.dataset.currentAnswered === '1';
    const answered = Math.max(0, Math.min(total,
      storedAnswered - Number(wasAnswered) + Number(currentFormHasAnswer())));
    if (answeredOutput) answeredOutput.textContent = String(answered);
    if (unansweredOutput) unansweredOutput.textContent = String(total - answered);
    if (unansweredWarning) unansweredWarning.hidden = answered === total;
    if (typeof dialog.showModal === 'function') {
      dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
      cancelButton.focus();
    }
  });

  cancelButton.addEventListener('click', () => {
    if (typeof dialog.close === 'function') dialog.close();
    else dialog.removeAttribute('open');
    openButton.focus();
  });

  dialog.addEventListener('cancel', () => {
    window.setTimeout(() => openButton.focus(), 0);
  });
})();
