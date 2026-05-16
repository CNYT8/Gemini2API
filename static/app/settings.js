import { apiCall } from './auth.js';
import { showToast } from './utils.js';

let originalSettings = {};
let modelMappings = {};

const GROUP_TITLES = {
  performance: '性能',
  rate_limiting: '速率限制',
  health_check: '健康检查',
  account_management: '账号管理',
  usage_stats: '用量统计'
};

const GROUP_ICONS = {
  performance: 'fa-bolt',
  rate_limiting: 'fa-shield-alt',
  health_check: 'fa-heartbeat',
  account_management: 'fa-users-cog',
  usage_stats: 'fa-chart-line'
};

const FIELD_LABELS = {
  refresh_interval: 'Cookie刷新间隔(分钟)',
  max_retries: '最大重试次数',
  jitter_enabled: '启用时间抖动',
  rate_limit_enabled: '启用速率限制',
  rate_limit_window: '限制窗口(秒)',
  rate_limit_max: '窗口最大请求数',
  health_check_enabled: '启用健康检查',
  health_check_interval: '检查间隔(分钟)',
  rotation_strategy: '轮换策略',
  max_concurrent_per_account: '单账号最大并发',
  usage_stats_enabled: '启用用量统计',
  usage_stats_interval: '快照间隔(秒)',
  usage_stats_retention_days: '数据保留天数'
};

const ROTATION_OPTIONS = [
  { value: 'round-robin', label: '轮询 (Round Robin)' },
  { value: 'least-used', label: '最少使用 (Least Used)' }
];

function createFieldInput(key, value) {
  const type = typeof value;

  if (type === 'boolean') {
    return `
      <label class="toggle-switch">
        <input type="checkbox" data-key="${key}" ${value ? 'checked' : ''}>
      </label>
    `;
  }

  if (key.endsWith('.rotation_strategy')) {
    const radios = ROTATION_OPTIONS.map(opt =>
      `<label class="radio-option">
        <input type="radio" name="rotation_strategy" data-key="${key}" value="${opt.value}" ${value === opt.value ? 'checked' : ''}>
        <span>${opt.label}</span>
      </label>`
    ).join('');
    return `<div class="radio-group">${radios}</div>`;
  }

  if (type === 'number') {
    return `<input type="number" class="form-control" data-key="${key}" value="${value}">`;
  }

  return `<input type="text" class="form-control" data-key="${key}" value="${value}">`;
}

function renderSettings(settings) {
  const container = document.getElementById('settings-container');
  if (!container) return;

  let html = '';

  for (const [groupKey, groupSettings] of Object.entries(settings)) {
    const groupTitle = GROUP_TITLES[groupKey] || groupKey;
    const groupIcon = GROUP_ICONS[groupKey] || 'fa-cog';

    html += '<div class="settings-group">';
    html += '<h3><i class="fas ' + groupIcon + '"></i> ' + groupTitle + '</h3>';
    html += '<div class="settings-fields">';

    for (const [key, value] of Object.entries(groupSettings)) {
      const label = FIELD_LABELS[key] || key;
      const fullKey = groupKey + '.' + key;
      const input = createFieldInput(fullKey, value);
      html += '<div class="setting-field"><label>' + label + '</label>' + input + '</div>';
    }

    html += '</div></div>';
  }

  container.innerHTML = html;
}

function renderModelMapping() {
  const container = document.getElementById('model-mapping-container');
  if (!container) return;

  const entries = Object.entries(modelMappings);

  let html = '<div class="settings-group">';
  html += '<h3><i class="fas fa-exchange-alt"></i> 模型映射</h3>';
  html += '<p class="mapping-desc">将请求中的模型名映射到实际使用的模型</p>';
  html += '<div class="mapping-header"><span>别名</span><span>目标模型</span><span></span></div>';

  for (const [alias, target] of entries) {
    html += '<div class="mapping-row" data-alias="' + alias + '">';
    html += '<input type="text" class="form-control mapping-alias" value="' + alias + '" readonly>';
    html += '<input type="text" class="form-control mapping-target" value="' + target + '">';
    html += '<button class="btn-icon btn-delete-mapping" data-alias="' + alias + '"><i class="fas fa-trash"></i></button>';
    html += '</div>';
  }

  html += '<div class="mapping-row mapping-new">';
  html += '<input type="text" class="form-control" id="new-mapping-alias" placeholder="别名 (如 gpt-4o)">';
  html += '<input type="text" class="form-control" id="new-mapping-target" placeholder="目标模型 (如 gemini-2.5-pro)">';
  html += '<button class="btn-icon btn-add-mapping" id="btn-add-mapping"><i class="fas fa-plus"></i></button>';
  html += '</div>';
  html += '</div>';
  html += '<div class="mapping-actions">';
  html += '<button class="btn btn-primary" id="btn-save-mapping">保存映射</button>';
  html += '</div>';
  html += '</div>';

  container.innerHTML = html;
  bindMappingEvents();
}

function bindMappingEvents() {
  document.getElementById('btn-add-mapping')?.addEventListener('click', addMapping);
  document.getElementById('btn-save-mapping')?.addEventListener('click', saveAllMappings);
  document.querySelectorAll('.btn-delete-mapping').forEach(btn => {
    btn.addEventListener('click', () => deleteMapping(btn.dataset.alias));
  });
  document.getElementById('new-mapping-target')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addMapping();
  });
}

async function addMapping() {
  const aliasInput = document.getElementById('new-mapping-alias');
  const targetInput = document.getElementById('new-mapping-target');
  const alias = aliasInput.value.trim();
  const target = targetInput.value.trim();

  if (!alias || !target) {
    showToast('请填写别名和目标模型', 'warning');
    return;
  }
  if (alias === target) {
    showToast('别名不能与目标相同', 'warning');
    return;
  }

  try {
    await apiCall('POST', '/admin/model-mapping', { alias, target });
    showToast('映射已添加', 'success');
    await loadModelMapping();
  } catch (error) {
    showToast('添加失败: ' + error.message, 'error');
  }
}

async function deleteMapping(alias) {
  try {
    await apiCall('DELETE', '/admin/model-mapping/' + encodeURIComponent(alias));
    showToast('映射已删除', 'success');
    await loadModelMapping();
  } catch (error) {
    showToast('删除失败: ' + error.message, 'error');
  }
}

async function saveAllMappings() {
  const rows = document.querySelectorAll('.mapping-row:not(.mapping-new)');
  let updated = 0;

  for (const row of rows) {
    const alias = row.dataset.alias;
    const target = row.querySelector('.mapping-target').value.trim();
    if (target && target !== modelMappings[alias]) {
      try {
        await apiCall('POST', '/admin/model-mapping', { alias, target });
        updated++;
      } catch (error) {
        showToast('更新 ' + alias + ' 失败: ' + error.message, 'error');
      }
    }
  }

  if (updated > 0) {
    showToast('已更新 ' + updated + ' 条映射', 'success');
  } else {
    showToast('无变更', 'info');
  }
  await loadModelMapping();
}

async function loadModelMapping() {
  try {
    const data = await apiCall('GET', '/admin/model-mapping');
    modelMappings = data.mappings || {};
    renderModelMapping();
  } catch (error) {
    showToast('加载模型映射失败: ' + error.message, 'error');
  }
}

function collectFormValues() {
  const values = {};

  document.querySelectorAll('#settings-container [data-key]').forEach(input => {
    const key = input.dataset.key;

    if (input.type === 'radio') {
      if (input.checked) {
        values[key] = input.value;
      }
      return;
    }

    let value;
    if (input.type === 'checkbox') {
      value = input.checked;
    } else if (input.type === 'number') {
      value = parseInt(input.value, 10);
    } else {
      value = input.value;
    }

    values[key] = value;
  });

  return values;
}

function getChangedSettings(current, original) {
  const changed = {};
  for (const [key, value] of Object.entries(current)) {
    if (original[key] !== value) {
      changed[key] = value;
    }
  }
  return changed;
}

function flattenSettings(settings) {
  const flat = {};
  for (const [groupKey, groupSettings] of Object.entries(settings)) {
    for (const [key, value] of Object.entries(groupSettings)) {
      flat[groupKey + '.' + key] = value;
    }
  }
  return flat;
}

export async function loadSettings() {
  try {
    const data = await apiCall('GET', '/admin/settings');
    originalSettings = flattenSettings(data);
    renderSettings(data);
    await loadModelMapping();
  } catch (error) {
    showToast('加载设置失败: ' + error.message, 'error');
  }
}

async function saveSettings() {
  const currentValues = collectFormValues();
  const changedSettings = getChangedSettings(currentValues, originalSettings);

  if (Object.keys(changedSettings).length === 0) {
    showToast('没有修改', 'info');
    return;
  }

  const apiSettings = {};
  for (const [key, value] of Object.entries(changedSettings)) {
    const fieldName = key.split('.').pop();
    apiSettings[fieldName] = value;
  }

  try {
    await apiCall('POST', '/admin/settings', { settings: apiSettings });
    showToast('设置已保存', 'success');
    await loadSettings();
  } catch (error) {
    showToast('保存设置失败: ' + error.message, 'error');
  }
}

async function resetSettings() {
  await loadSettings();
  showToast('设置已重置', 'info');
}

export function initSettings() {
  const saveBtn = document.getElementById('settings-save-btn');
  const resetBtn = document.getElementById('settings-reset-btn');

  if (saveBtn) {
    saveBtn.addEventListener('click', saveSettings);
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', resetSettings);
  }
}
