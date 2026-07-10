const clock = document.querySelector("#clock-face");
const clockHit = document.querySelector("#clock-hit");
const hourHand = document.querySelector("#hour-hand");
const minuteHand = document.querySelector("#minute-hand");
const readout = document.querySelector("#clock-readout");
const instruction = document.querySelector("#clock-instruction");
const validation = document.querySelector("#clock-validation");
const hourButton = document.querySelector("#set-hour");
const minuteButton = document.querySelector("#set-minute");
const resetButton = document.querySelector("#reset-clock");
const ticks = document.querySelector("#clock-ticks");
const pages = [...document.querySelectorAll("[data-screen-question]")];
const steps = [...document.querySelectorAll("[data-screen-step]")];

let hour = 12;
let minute = 0;
let mode = "hour";

for (let index = 0; index < 60; index += 1) {
  const angle = index * 6 * Math.PI / 180;
  const major = index % 5 === 0;
  const inner = major ? 40 : 42;
  const outer = 45;
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", String(50 + Math.sin(angle) * inner));
  line.setAttribute("y1", String(50 - Math.cos(angle) * inner));
  line.setAttribute("x2", String(50 + Math.sin(angle) * outer));
  line.setAttribute("y2", String(50 - Math.cos(angle) * outer));
  line.setAttribute("class", `clock-tick${major ? " major" : ""}`);
  ticks.append(line);
}

function updateClock() {
  const hourAngle = ((hour % 12) + minute / 60) * 30;
  const minuteAngle = minute * 6;
  hourHand.style.transform = `rotate(${hourAngle}deg)`;
  minuteHand.style.transform = `rotate(${minuteAngle}deg)`;
  const value = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  readout.textContent = value;
  clock.setAttribute("aria-label", `可調校的時鐘，目前時間 ${value}`);
  validation.textContent = hour === 10 && minute === 5 ? "時間正確，可以前往下一題。" : "";
}

function setMode(nextMode) {
  mode = nextMode;
  hourButton.classList.toggle("active", mode === "hour");
  minuteButton.classList.toggle("active", mode === "minute");
  instruction.textContent = mode === "hour" ? "請點擊鐘面設定小時" : "請點擊鐘面設定分鐘";
}

clockHit.addEventListener("pointerdown", (event) => {
  const rect = clock.getBoundingClientRect();
  const x = (event.clientX - rect.left) / rect.width * 100 - 50;
  const y = (event.clientY - rect.top) / rect.height * 100 - 50;
  const clockwiseAngle = (Math.atan2(x, -y) * 180 / Math.PI + 360) % 360;

  if (mode === "hour") {
    const selectedHour = Math.round(clockwiseAngle / 30) % 12;
    hour = selectedHour === 0 ? 12 : selectedHour;
    setMode("minute");
  } else {
    minute = (Math.round(clockwiseAngle / 6) % 60);
  }
  updateClock();
});

hourButton.addEventListener("click", () => setMode("hour"));
minuteButton.addEventListener("click", () => setMode("minute"));
resetButton.addEventListener("click", () => {
  hour = 12;
  minute = 0;
  setMode("hour");
  updateClock();
});

function showPage(index) {
  pages.forEach((page, pageIndex) => { page.hidden = pageIndex !== index; });
  steps.forEach((step, stepIndex) => {
    step.classList.toggle("active", stepIndex === index);
    step.classList.toggle("complete", stepIndex < index);
  });
}

pages.forEach((page, index) => {
  page.querySelector("[data-screen-next]").addEventListener("click", () => {
    if (index === 0 && (hour !== 10 || minute !== 5)) {
      validation.textContent = "請先將時間調校至 10:05。";
      return;
    }
    if (index < pages.length - 1) {
      showPage(index + 1);
      return;
    }
    pages[index].hidden = true;
    steps.forEach((step) => { step.classList.remove("active"); step.classList.add("complete"); });
    document.querySelector("#screening-result").hidden = false;
  });
});

updateClock();
