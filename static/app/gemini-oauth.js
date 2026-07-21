import { apiCall } from './auth.js';
import { copyToClipboard, showToast } from './utils.js';

function createOAuthFlowState() {
    return {
        sessionId: '',
        state: '',
        authUrl: '',
        authorized: false,
        token: null,
        snapshot: null,
        busy: false
    };
}

const flowStates = {
    add: createOAuthFlowState(),
    update: createOAuthFlowState()
};
const flowRevisions = { add: 0, update: 0 };
const oauthTypeReaders = {};
const initializedContexts = new Set();

export function getOAuthMethod(context) {
    return document.querySelector(`input[name="${context}-oauth-method"]:checked`)?.value || 'browser';
}

export function getOAuthToken(context) {
    return flowStates[context]?.token || null;
}

export function isOAuthAuthorized(context) {
    return Boolean(flowStates[context]?.authorized);
}

function getOAuthType(context) {
    return oauthTypeReaders[context]?.() || 'code_assist';
}

function setFlowStatus(context, message = '', type = '') {
    const status = document.getElementById(`${context}-oauth-status`);
    if (!status) return;
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle('success', type === 'success');
    status.classList.toggle('error', type === 'error');
}

function updateFlowControls(context) {
    const flow = flowStates[context];
    const generate = document.getElementById(`${context}-oauth-generate`);
    const exchange = document.getElementById(`${context}-oauth-exchange`);
    if (generate) generate.disabled = flow.busy;
    if (exchange) exchange.disabled = flow.busy || flow.authorized;
}

export function resetOAuthBrowserFlow(context, { clearTokens = true } = {}) {
    flowRevisions[context] += 1;
    const flow = flowStates[context];
    Object.assign(flow, createOAuthFlowState());
    const result = document.getElementById(`${context}-oauth-browser-result`);
    const url = document.getElementById(`${context}-oauth-auth-url`);
    const open = document.getElementById(`${context}-oauth-open`);
    const code = document.getElementById(`${context}-oauth-code`);
    if (result) result.hidden = true;
    if (url) url.value = '';
    if (open) open.removeAttribute('href');
    if (code) code.value = '';
    if (clearTokens) {
        const access = document.getElementById(`${context}-access-token`);
        const refresh = document.getElementById(`${context}-refresh-token`);
        if (access) access.value = '';
        if (refresh) refresh.value = '';
    }
    setFlowStatus(context);
    updateFlowControls(context);
}

export function syncOAuthMethodFields(context) {
    const browser = getOAuthMethod(context) === 'browser';
    const browserFields = document.getElementById(`${context}-oauth-browser-fields`);
    const manualFields = document.getElementById(`${context}-oauth-manual-fields`);
    if (browserFields) browserFields.hidden = !browser;
    if (manualFields) manualFields.hidden = browser;
}

export function oauthClientHint(oauthType) {
    return oauthType === 'ai_studio'
        ? 'AI Studio 浏览器授权需要自定义 OAuth Client ID 和 Client Secret'
        : 'Code Assist 留空时使用内置 Gemini CLI OAuth 客户端';
}

function handleOAuthMethodChange(context) {
    if (getOAuthMethod(context) === 'manual') {
        resetOAuthBrowserFlow(context);
    }
    syncOAuthMethodFields(context);
}

function invalidateFlowIfStarted(context) {
    const flow = flowStates[context];
    if (flow.busy || flow.sessionId || flow.authorized) resetOAuthBrowserFlow(context);
}

async function generateAuthorization(context) {
    const oauthType = getOAuthType(context);
    const projectId = oauthType === 'code_assist'
        ? (document.getElementById(`${context}-project-id`)?.value.trim() || '')
        : '';
    const clientId = document.getElementById(`${context}-oauth-client-id`)?.value.trim() || '';
    const clientSecret = document.getElementById(`${context}-oauth-client-secret`)?.value.trim() || '';
    if (Boolean(clientId) !== Boolean(clientSecret)) {
        showToast('OAuth Client ID 和 Client Secret 必须同时填写', 'warning');
        return;
    }
    if (oauthType === 'ai_studio' && (!clientId || !clientSecret)) {
        showToast('AI Studio 浏览器授权需要 OAuth Client ID 和 Client Secret', 'warning');
        return;
    }

    resetOAuthBrowserFlow(context);
    const revision = flowRevisions[context];
    const flow = flowStates[context];
    flow.busy = true;
    updateFlowControls(context);
    setFlowStatus(context, '正在生成授权网址...');
    try {
        const result = await apiCall('POST', '/admin/gemini/oauth/auth-url', {
            oauth_type: oauthType,
            project_id: projectId,
            oauth_client_id: clientId,
            oauth_client_secret: clientSecret
        });
        if (revision !== flowRevisions[context]) return;
        flow.sessionId = result.session_id;
        flow.state = result.state;
        flow.authUrl = result.auth_url;
        flow.snapshot = { oauthType, clientId, clientSecret };
        const url = document.getElementById(`${context}-oauth-auth-url`);
        const open = document.getElementById(`${context}-oauth-open`);
        const browserResult = document.getElementById(`${context}-oauth-browser-result`);
        if (url) url.value = result.auth_url;
        if (open) open.href = result.auth_url;
        if (browserResult) browserResult.hidden = false;
        setFlowStatus(context, '授权网址已生成，请在 30 分钟内完成授权');
    } catch (error) {
        if (revision !== flowRevisions[context]) return;
        setFlowStatus(context, error.message, 'error');
        showToast(`生成授权网址失败: ${error.message}`, 'error');
    } finally {
        if (revision === flowRevisions[context]) {
            flow.busy = false;
            updateFlowControls(context);
        }
    }
}

async function copyAuthorizationUrl(context) {
    const authUrl = flowStates[context].authUrl;
    if (!authUrl) return;
    const copied = await copyToClipboard(authUrl);
    showToast(copied ? '授权网址已复制' : '复制授权网址失败', copied ? 'success' : 'error');
}

async function exchangeAuthorization(context) {
    const flow = flowStates[context];
    const revision = flowRevisions[context];
    const code = document.getElementById(`${context}-oauth-code`)?.value.trim() || '';
    if (!flow.sessionId || !flow.state) {
        showToast('请先生成授权网址', 'warning');
        return;
    }
    if (!code) {
        showToast('请填写授权码或回调地址', 'warning');
        return;
    }

    flow.busy = true;
    updateFlowControls(context);
    setFlowStatus(context, '正在兑换授权码...');
    try {
        const token = await apiCall('POST', '/admin/gemini/oauth/exchange-code', {
            session_id: flow.sessionId,
            state: flow.state,
            code,
            oauth_type: flow.snapshot?.oauthType || getOAuthType(context)
        });
        if (revision !== flowRevisions[context]) return;
        flow.token = token;
        flow.authorized = true;
        const access = document.getElementById(`${context}-access-token`);
        const refresh = document.getElementById(`${context}-refresh-token`);
        const project = document.getElementById(`${context}-project-id`);
        if (access) access.value = token.access_token || '';
        if (refresh) refresh.value = token.refresh_token || '';
        if (project && token.project_id && !project.value.trim()) project.value = token.project_id;
        setFlowStatus(
            context,
            token.refresh_token ? '浏览器授权已完成' : '授权已完成，但 Google 未返回 Refresh Token',
            'success'
        );
        showToast('OAuth 授权成功', 'success');
    } catch (error) {
        if (revision !== flowRevisions[context]) return;
        setFlowStatus(context, error.message, 'error');
        showToast(`OAuth 授权失败: ${error.message}`, 'error');
    } finally {
        if (revision === flowRevisions[context]) {
            flow.busy = false;
            updateFlowControls(context);
        }
    }
}

export function initGeminiOAuthFlow(context, getCurrentOAuthType) {
    oauthTypeReaders[context] = getCurrentOAuthType;
    if (initializedContexts.has(context)) return;
    initializedContexts.add(context);

    document.querySelectorAll(`input[name="${context}-oauth-method"]`).forEach(input => {
        input.addEventListener('change', () => handleOAuthMethodChange(context));
    });
    document.getElementById(`${context}-oauth-generate`)?.addEventListener('click', () => generateAuthorization(context));
    document.getElementById(`${context}-oauth-copy`)?.addEventListener('click', () => copyAuthorizationUrl(context));
    document.getElementById(`${context}-oauth-exchange`)?.addEventListener('click', () => exchangeAuthorization(context));
    [`${context}-project-id`, `${context}-oauth-client-id`, `${context}-oauth-client-secret`].forEach(id => {
        document.getElementById(id)?.addEventListener('input', () => invalidateFlowIfStarted(context));
    });
    syncOAuthMethodFields(context);
}
