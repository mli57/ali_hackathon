// Shared frontend logic. No build step, no framework -- three views and a
// couple of fetches don't justify either.
//
// The one rule that matters here: every ¥ figure rendered on a card comes from
// the API response. The frontend never computes an amount and never reads one
// out of the model's prose.

// The only place the API port is written down. It used to be hardcoded to 8003
// in four <script> blocks across three pages while SETUP.md said 8000, so
// following the setup instructions produced a form that submitted into nothing.
// To point somewhere else, set window.API_BASE before this file loads.
const API = window.API_BASE || "http://127.0.0.1:8000";

// How to ask for each attribute the backend might request as a follow-up.
//
// `hint` renders under the input. NOTE the thresholds quoted in hints (4200,
// 2400, 570000, 760000) are DUPLICATED from the eligibility predicates in
// data/rules.json -- the API exposes no endpoint for them today. They are
// display-only guidance and no decision is made from them, but they can drift:
// if a policy threshold changes in data/programs/, change it here too. The
// amounts on the results cards are unaffected either way, since those come
// from the API response.
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
  household_monthly_income: {
    label: "家庭月总收入（元）",
    type: "number",
    min: 0,
    hint: "填全家税前月总收入。资格按人均计算：人均月收入 ≤4200 元可申请市场租房补贴，≤2400 元还可申请公租房租金补贴。人均越低补贴档次越高（≤2700 元为第三档）。",
  },
  household_assets: {
    label: "家庭总资产（元）",
    type: "number",
    min: 0,
    hint: "家庭总资产净值。3 人及以下需 ≤57 万元，4 人及以上需 ≤76 万元。",
  },
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
    // Deliberately states what this is NOT. 第一档/第二档 are 民政 designations,
    // not income bands -- that is why income_tier carries `overrides`. Someone
    // who reads "城市低收入家庭" as "my income is low" and selects it without
    // the certification jumps a 3-person household from 第六档 (¥1,200) to
    // 第二档 (¥3,000), and walks into a housing office expecting ¥1,800/month
    // that is not theirs. Overstating is the dangerous direction.
    hint: "须已由民政部门正式认定并持有相关证明，不能按自己的收入判断。未经认定请选「以上均否」——收入高低已由上一题计算。",
  },
  employment_status: {
    label: "就业状态",
    type: "select",
    options: [
      ["employed", "用人单位在职职工"],
      ["flexible", "灵活就业（个体经营、非全日制、新就业形态）"],
      ["self_employed_founder", "创办企业或个体，任法定代表人／主要负责人"],
      ["unemployed", "登记失业"],
      ["student", "在校学生"],
      ["retired", "已退休"],
      ["other", "以上均否"],
    ],
  },
  // Optional because 育儿补贴 makes /profile/confirm ask this of everyone, and
  // a household with no children has no answer to give. Left blank the attribute
  // simply isn't sent, and the program lands in needs_verification -- which is
  // the truth ("we don't know"), and is better than a form nobody can submit.
  children_ages: {
    label: "子女年龄（周岁，多个用逗号分隔；无子女请留空）",
    type: "text",
    optional: true,
  },
};

const DERIVED_LABELS = {
  per_capita_monthly_income: "家庭人均月收入",
  per_capita_household_assets: "家庭人均资产",
  num_children: "子女数量",
  // Derived attributes can also come back in unresolved_attributes -- 育儿补贴
  // reads youngest_child_age, which is derived from children_ages and so has no
  // FIELDS entry. Without a label here the card prints the raw attribute name.
  youngest_child_age: "最小子女年龄",
  oldest_child_age: "最大子女年龄",
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
  const required = field.optional ? "" : " required";

  let input;
  if (field.type === "select") {
    const options = field.options
      .map(
        ([v, label]) =>
          `<option value="${v}"${v === value ? " selected" : ""}>${label}</option>`
      )
      .join("");
    input = `<select name="${name}"${required}><option value="">请选择</option>${options}</select>`;
  } else {
    const min = field.min !== undefined ? ` min="${field.min}"` : "";
    const max = field.max !== undefined ? ` max="${field.max}"` : "";
    input = `<input type="${field.type}" name="${name}" value="${value}"${min}${max}${required}>`;
  }

  const hint = field.hint ? `<small class="field-hint">${field.hint}</small>` : "";
  return `<label><span>${field.label}</span>${input}${hint}</label>`;
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
  // 一次性 means once and never again. Saying it about a benefit that renews
  // every year until the child turns 3 understates it by up to two thirds.
  if (cadence === "annual") return `¥${formatted}（一年可领一次）`;
  if (cadence === "one_time") return `¥${formatted}（一次性）`;
  return `¥${formatted}/月`;
}
