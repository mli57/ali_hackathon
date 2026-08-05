// Shared frontend logic. No build step, no framework -- three views and a
// couple of fetches don't justify either.
//
// The one rule that matters here: every ¥ figure rendered on a card comes from
// the API response. The frontend never computes an amount and never reads one
// out of the model's prose.

const API = window.API_BASE || "http://127.0.0.1:8000";

// How to ask for each attribute the backend might request as a follow-up.
const FIELDS = {
  hukou_type: {
    label: "户籍类型",
    type: "select",
    options: [
      ["bj_urban", "北京市城镇户籍"],
      ["bj_rural", "北京市农村户籍"],
      ["non_bj", "非北京市户籍"],
    ],
  },
  household_size: { label: "家庭人口数", type: "number", min: 1, max: 20 },
  household_monthly_income: { label: "家庭月总收入（元）", type: "number", min: 0 },
  household_assets: { label: "家庭总资产（元）", type: "number", min: 0 },
  owns_property: {
    label: "家庭是否拥有自有住房",
    type: "select",
    options: [["false", "无自有住房"], ["true", "有自有住房"]],
  },
  district: {
    label: "居住区",
    type: "select",
    options: [
      "东城区", "西城区", "朝阳区", "海淀区", "丰台区", "石景山区",
      "门头沟区", "房山区", "通州区", "顺义区", "昌平区", "大兴区",
      "怀柔区", "平谷区", "密云区", "延庆区",
    ].map((d) => [d, d]),
  },
  monthly_rent: { label: "每月租金（元）", type: "number", min: 0 },
  welfare_status: {
    label: "民政部门认定情况",
    type: "select",
    options: [
      ["none", "以上均否"],
      ["dibao", "最低生活保障家庭"],
      ["tekun", "分散供养特困人员"],
      ["low_income", "城市低收入家庭"],
    ],
  },
  employment_status: { label: "就业状态", type: "text" },
  children_ages: { label: "子女年龄（用逗号分隔）", type: "text" },
};

const DERIVED_LABELS = {
  per_capita_monthly_income: "家庭人均月收入",
  per_capita_household_assets: "家庭人均资产",
  num_children: "子女数量",
};

const store = {
  get profile() {
    return JSON.parse(sessionStorage.getItem("profile") || "{}");
  },
  set profile(value) {
    sessionStorage.setItem("profile", JSON.stringify(value));
  },
  get results() {
    return JSON.parse(sessionStorage.getItem("results") || "null");
  },
  set results(value) {
    sessionStorage.setItem("results", JSON.stringify(value));
  },
};

function coerce(name, raw) {
  if (raw === "" || raw === null || raw === undefined) return undefined;
  const field = FIELDS[name];
  if (!field) return raw;
  if (field.type === "number") return Number(raw);
  if (name === "owns_property") return raw === "true";
  if (name === "children_ages") {
    return raw.split(/[,，\s]+/).filter(Boolean).map(Number);
  }
  return raw;
}

function readForm(form) {
  const profile = {};
  for (const [name, raw] of new FormData(form).entries()) {
    const value = coerce(name, raw);
    if (value !== undefined) profile[name] = value;
  }
  return profile;
}

function renderField(name, current) {
  const field = FIELDS[name];
  if (!field) return "";
  const value = current === undefined || current === null ? "" : String(current);

  let input;
  if (field.type === "select") {
    const options = field.options
      .map(
        ([v, label]) =>
          `<option value="${v}"${v === value ? " selected" : ""}>${label}</option>`
      )
      .join("");
    input = `<select name="${name}" required><option value="">请选择</option>${options}</select>`;
  } else {
    const min = field.min !== undefined ? ` min="${field.min}"` : "";
    const max = field.max !== undefined ? ` max="${field.max}"` : "";
    input = `<input type="${field.type}" name="${name}" value="${value}"${min}${max} required>`;
  }

  return `<label><span>${field.label}</span>${input}</label>`;
}

async function post(path, body) {
  const response = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${path} 返回 ${response.status}：${await response.text()}`);
  }
  return response.json();
}

function showError(message) {
  const box = document.getElementById("error");
  if (!box) return;
  box.textContent = message;
  box.hidden = false;
}

function money(amount, cadence) {
  if (amount === null || amount === undefined) return "待定";
  const formatted = Number(amount).toLocaleString("zh-CN");
  return cadence === "one_time" ? `¥${formatted}（一次性）` : `¥${formatted}/月`;
}
