/* Save optional confidence without navigating away from the explanation. */
document.querySelectorAll('.guest-confidence').forEach(function (section) {
  const form = section.closest('form');
  const status = section.querySelector('[role="status"]');
  let saving = false;
  section.addEventListener('click', async function (event) {
    const button = event.target.closest('button[name="confidence"]');
    if (!button) return;
    event.preventDefault();
    if (saving) return;
    saving = true;
    const controls = Array.from(form.querySelectorAll('button[type="submit"], button.main-button'));
    const data = new FormData(form);
    data.set('action', 'confidence');
    data.set('confidence', button.value);
    controls.forEach(function (control) { control.disabled = true; });
    status.textContent = '반영 중이에요…';
    try {
      const response = await fetch(form.getAttribute('action') || window.location.href, {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: {'X-Requested-With': 'XMLHttpRequest'}
      });
      if (response.redirected) throw new Error('문제 상태가 변경됐어요. 새로고침 후 다시 선택해 주세요.');
      const result = await response.json();
      if (!response.ok || !result.saved) throw new Error(result.error || '선택을 반영하지 못했어요. 다시 눌러 주세요.');
      section.querySelectorAll('button[name="confidence"]').forEach(function (control) {
        control.setAttribute('aria-pressed', String(control.value === result.confidence));
      });
      status.textContent = '✓ 이 체험에 반영했어요. 복습할 문제로 안내합니다.';
    } catch (error) {
      status.textContent = error instanceof TypeError || error instanceof SyntaxError
        ? '연결을 확인하고 다시 눌러 주세요. 선택을 반영하지 못했어요.' : error.message;
    } finally {
      saving = false;
      controls.forEach(function (control) { control.disabled = false; });
    }
  });
});
