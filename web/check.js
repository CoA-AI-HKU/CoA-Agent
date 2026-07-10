const panels = [...document.querySelectorAll("[data-question]")];
const steps = [...document.querySelectorAll("[data-step]")];
const answers = [];

function showQuestion(index) {
  panels.forEach((panel, panelIndex) => { panel.hidden = panelIndex !== index; });
  steps.forEach((step, stepIndex) => {
    step.classList.toggle("active", stepIndex === index);
    step.classList.toggle("complete", stepIndex < index);
  });
  panels[index].querySelector("input").focus();
}

function showResult() {
  document.querySelector("#check-form").hidden = true;
  steps.forEach((step) => { step.classList.remove("active"); step.classList.add("complete"); });
  const result = document.querySelector("#result");
  const title = document.querySelector("#result-title");
  const message = document.querySelector("#result-message");
  result.hidden = false;

  if (answers[4] === 2) {
    title.textContent = "請先處理安全需要";
    message.textContent = "如有人目前走失、迷路或身處危險，請立即聯絡緊急服務及可信任的家人或照顧者。";
  } else if (answers.filter((answer) => answer >= 1).length >= 2 || answers.some((answer) => answer === 2)) {
    title.textContent = "建議安排跟進";
    message.textContent = "你的回答顯示有些情況值得持續記錄。可以與家人或照顧者分享，並考慮向醫護人員查詢。";
  } else {
    title.textContent = "暫未見明顯關注訊號";
    message.textContent = "目前回答沒有顯示明顯轉變，但這不能排除任何健康問題。如你仍感到擔心，請向醫護人員查詢。";
  }
}

panels.forEach((panel, index) => {
  panel.querySelector(".next").addEventListener("click", () => {
    const selected = panel.querySelector("input:checked");
    const validation = panel.querySelector(".validation");
    if (!selected) {
      validation.textContent = "請先選擇一個答案。";
      return;
    }
    validation.textContent = "";
    answers[index] = Number(selected.value);
    if (index < panels.length - 1) showQuestion(index + 1);
    else showResult();
  });
});
