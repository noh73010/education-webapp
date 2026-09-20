/* Drafts are not graded. A stable server receipt makes a repeated POST safe. */
(() => {
  const form = document.getElementById('mission-answer-form');
  if (!form) return;
  const status = document.getElementById('draft-status');
  const retryButton = document.getElementById('draft-retry');
  const finalDialog = document.getElementById('final-submit-dialog');
  const buttons = [
    ...form.querySelectorAll('button[type="submit"]'),
    ...document.querySelectorAll(`button[type="submit"][form="${form.id}"]`),
  ];
  const key = 'mission-draft:' + form.elements.work_token.value;
  const allowed = ['submitted_answer', 'submitted_answers', 'is_correct', 'confidence_level', 'wrong_reason_ids'];
  let timer, queue = Promise.resolve(), submitting = false, lastSubmitter = null;
  const showRetry = (show = true) => {
    if (retryButton) retryButton.hidden = !show;
  };
  const restore = (answers) => {
    for (const name of allowed) {
      if (!answers[name]) continue;
      const fields = [...form.querySelectorAll(`[name="${name}"]`)];
      fields.forEach((field, index) => {
        if (field.type === 'radio' || field.type === 'checkbox') field.checked = answers[name].includes(field.value);
        else field.value = answers[name][index] || '';
      });
    }
  };
  restore(JSON.parse(document.getElementById('draft-answers').textContent));
  try {
    const local = JSON.parse(sessionStorage.getItem(key));
    if (local && (!form.dataset.serverUpdated || local.at > Date.parse(form.dataset.serverUpdated))) { restore(local.answers); status.textContent = '이 기기에 남아 있던 답안을 복원했어요. 답안을 다시 선택하면 서버에 저장합니다.'; }
  } catch (_) { /* Private browsing/storage restrictions do not block learning. */ }
  const capture = () => {
    const data = new FormData(form), answers = {};
    for (const name of allowed) answers[name] = data.getAll(name);
    try { sessionStorage.setItem(key, JSON.stringify({answers, at: Date.now()})); } catch (_) {}
    return data;
  };
  const save = () => {
    const data = capture();
    queue = queue.catch(() => {}).then(async () => {
      if (submitting) return;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(form.dataset.draftUrl, {method: 'POST', body: data, credentials: 'same-origin', signal: controller.signal});
        if (!response.ok || response.redirected) throw new Error('not saved');
        const result = await response.json();
        status.textContent = result.submitted ? '이미 제출된 답안입니다.' : '답안이 저장됐어요. 아직 채점하지 않았습니다.';
        showRetry(false);
        // Keep local fallback until submission; local storage is scoped to this unique work token.
      } catch (_) {
        status.textContent = '저장하지 못했어요. 답안은 이 기기에 남아 있으며, 다시 선택하거나 인터넷 연결이 돌아오면 다시 저장합니다.';
        showRetry();
      } finally {
        clearTimeout(timeout);
      }
    });
  };
  form.addEventListener('input', () => {
    capture();
    status.textContent = '저장 중…';
    clearTimeout(timer);
    timer = setTimeout(save, 500);
  });
  window.addEventListener('online', save);
  window.addEventListener('offline', () => { status.textContent = '오프라인입니다. 답안은 이 탭에 유지되지만 제출은 연결 후 가능합니다.'; });
  const submit = async (submitter) => {
    if (submitting) return;
    lastSubmitter = submitter;
    if (!navigator.onLine) {
      status.textContent = '인터넷 연결 후 다시 시도해 주세요. 선택한 답안은 이 기기에 남아 있습니다.';
      showRetry();
      return;
    }
    const data = capture();
    if (submitter?.name) data.append(submitter.name, submitter.value);
    clearTimeout(timer);
    submitting = true;
    buttons.forEach((button) => { button.disabled = true; });
    showRetry(false);
    if (finalDialog?.open) finalDialog.close();
    status.textContent = '답안과 이동 상태를 저장하고 있어요…';

    // Keep draft and navigation writes ordered. Otherwise a slow draft POST can
    // contend with the next POST on SQLite and make a successful click look lost.
    await queue.catch(() => {});
    status.textContent = '답안과 이동 상태를 저장하고 있어요…';

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(submitter?.formAction || form.action || window.location.href, {
        method: 'POST', body: data, credentials: 'same-origin', signal: controller.signal,
      });
      if (response.ok && response.redirected && !response.url.includes('/login/')) {
        try { sessionStorage.removeItem(key); } catch (_) {}
        window.location.assign(response.url);
        return;
      }
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      status.textContent = html.getElementById('submission-error')?.textContent.trim()
        || `저장 요청을 완료하지 못했어요 (HTTP ${response.status}). 선택한 답안은 유지됩니다.`;
      showRetry();
    } catch (_) {
      status.textContent = '통신이 끊겨 저장 결과를 확인하지 못했어요. 선택한 답안은 유지되며, 같은 동작을 다시 시도해도 중복 채점되지 않습니다.';
      showRetry();
    } finally {
      clearTimeout(timeout);
      submitting = false;
      buttons.forEach((button) => { button.disabled = false; });
    }
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    submit(event.submitter);
  });

  retryButton?.addEventListener('click', () => {
    if (lastSubmitter) submit(lastSubmitter);
    else save();
  });
})();
