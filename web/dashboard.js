const select = document.querySelector("#patient-select");
const heading = document.querySelector("#patient-heading");
const bars = document.querySelector("#activity-bars");
const alertList = document.querySelector("#alert-list");
const dayLabels = ["一", "二", "三", "四", "五", "六", "日"];
let users = [];
const fallbackUsers = [
  {
    userId: "patient_001",
    displayName: "Patient Test User",
    interactions: 12,
    medicationConfirmations: 5,
    concernSignals: 2,
    activityRequests: 3,
    weeklyActivity: [1, 3, 2, 0, 4, 1, 1],
    alerts: [{ level: "warning", message: "最近有需要持續留意的結構化訊號。這不是診斷。" }],
  },
];

document.querySelector("#today").textContent = new Intl.DateTimeFormat("zh-Hant", {
  year: "numeric",
  month: "long",
  day: "numeric",
}).format(new Date());

function renderUser(userId) {
  const user = users.find((item) => item.userId === userId);
  if (!user) return;

  heading.textContent = `${user.displayName} 的近期記錄`;
  for (const key of ["interactions", "medicationConfirmations", "concernSignals", "activityRequests"]) {
    const element = document.querySelector(`[data-metric="${key}"]`);
    element.textContent = String(user[key] ?? 0);
  }

  bars.replaceChildren();
  user.weeklyActivity.forEach((value, index) => {
    const column = document.createElement("div");
    column.className = "bar-wrap";
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.style.height = `${Math.max(8, value * 24)}px`;
    bar.setAttribute("aria-label", `${dayLabels[index]}：${value} 次互動`);
    const label = document.createElement("span");
    label.textContent = dayLabels[index];
    column.append(bar, label);
    bars.append(column);
  });

  alertList.replaceChildren();
  const alerts = user.alerts.length
    ? user.alerts
    : [{ level: "empty", message: "暫時沒有需要跟進的結構化訊號。" }];
  for (const alert of alerts) {
    const item = document.createElement("div");
    item.className = `alert ${alert.level}`;
    item.textContent = alert.message;
    alertList.append(item);
  }
}

function loadUsers(data) {
  users = Array.isArray(data.users) && data.users.length ? data.users : fallbackUsers;
  select.replaceChildren();
  for (const user of users) {
    const option = document.createElement("option");
    option.value = user.userId;
    option.textContent = `${user.displayName} · ${user.userId}`;
    select.append(option);
  }
  select.disabled = false;
  renderUser(users[0].userId);
}

fetch("dashboard-data.json")
  .then((response) => {
    if (!response.ok) throw new Error("Dashboard data unavailable");
    return response.json();
  })
  .then(loadUsers)
  .catch(() => {
    loadUsers({ users: fallbackUsers });
  });

select.addEventListener("change", () => renderUser(select.value));
