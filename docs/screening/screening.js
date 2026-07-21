(function () {
  'use strict';

  const SCREENING_VERSION = 'cognitive_concern_screening_v1';
  const MAX_SCORE = 12;
  // Kept only in this page's JavaScript memory. It is never rendered or persisted.
  const screeningToken = new URLSearchParams(window.location.search).get('token') || '';
  const resultMessages = {
    no_immediate_concern: '目前沒有明顯需要即時跟進的訊號。若情況持續或加重，仍可諮詢專業人士。',
    monitor: '有一些情況值得繼續留意。這不是診斷。可以和家人或照顧者討論。',
    follow_up_suggested: '結果顯示有幾項情況值得跟進。這不是診斷，但建議與照顧者或醫護人員討論。',
    urgent_safety: '如果涉及走失、即時危險或安全問題，請立即聯絡家人、照顧者、醫護人員或緊急服務。'
  };

  function calculateRiskFlag(answers) {
    if (Number(answers.safety) > 0) return 'urgent_safety';
    const coreConcerns = ['memory', 'orientation', 'daily_tasks']
      .filter((key) => Number(answers[key]) > 0).length;
    if (coreConcerns >= 2) return 'follow_up_suggested';
    const anyConcern = Object.values(answers).some((value) => Number(value) > 0);
    if (Number(answers.medication) > 0 || anyConcern) return 'monitor';
    return 'no_immediate_concern';
  }

  function calculateResult(answers) {
    const totalScore = Object.values(answers).reduce((sum, value) => sum + Number(value || 0), 0);
    return { risk_flag: calculateRiskFlag(answers), total_score: totalScore, max_score: MAX_SCORE };
  }

  async function submitStructuredResult(result) {
    if (!screeningToken) return false;
    try {
      const response = await fetch('/api/screening/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: screeningToken, screening_version: SCREENING_VERSION, result })
      });
      return response.ok;
    } catch (_error) {
      // GitHub Pages has no backend. The result remains local and no raw answers are saved.
      return false;
    }
  }

  document.querySelector('#screening-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const answers = Object.fromEntries(data.entries());
    const result = calculateResult(answers);
    const panel = document.querySelector('#result');
    document.querySelector('#result-text').textContent = resultMessages[result.risk_flag];
    panel.classList.toggle('urgent', result.risk_flag === 'urgent_safety');
    panel.hidden = false;
    const submitted = await submitStructuredResult(result);
    document.querySelector('#submission-note').textContent = submitted
      ? '結果已安全提交；不會儲存逐題答案。'
      : '結果只顯示在此頁，你可以自行與照顧者或醫護人員分享。';
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  window.calculateScreeningRiskFlag = calculateRiskFlag;
  window.calculateScreeningResult = calculateResult;
})();
