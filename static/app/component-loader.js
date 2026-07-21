/**
 * 组件加载器 - 用于动态加载 HTML 组件片段
 * Component Loader - For dynamically loading HTML component fragments
 */

// 组件缓存
const componentCache = new Map();
const stylesheetCache = new Map();
let initializationPromise = null;

function loadStylesheet(href) {
    const absoluteHref = new URL(href, document.baseURI).href;
    if (stylesheetCache.has(absoluteHref)) {
        return stylesheetCache.get(absoluteHref);
    }

    const promise = new Promise((resolve, reject) => {
        const existing = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
            .find(link => link.href === absoluteHref);
        if (existing?.sheet) {
            resolve();
            return;
        }

        const link = existing || document.createElement('link');
        const onLoad = () => {
            link.removeEventListener('load', onLoad);
            link.removeEventListener('error', onError);
            resolve();
        };
        const onError = () => {
            link.removeEventListener('load', onLoad);
            link.removeEventListener('error', onError);
            reject(new Error(`Failed to load stylesheet: ${href}`));
        };
        link.addEventListener('load', onLoad, { once: true });
        link.addEventListener('error', onError, { once: true });
        if (!existing) {
            link.rel = 'stylesheet';
            link.href = href;
            document.head.appendChild(link);
        }
    });
    stylesheetCache.set(absoluteHref, promise);
    return promise;
}

function prepareComponent(html) {
    const template = document.createElement('template');
    template.innerHTML = html;
    const styles = Array.from(template.content.querySelectorAll('link[rel="stylesheet"][href]'))
        .map(link => {
            const promise = loadStylesheet(link.getAttribute('href'));
            link.remove();
            return promise;
        });
    return { html: template.innerHTML, styles };
}

function insertPreparedComponent(html, container, position = 'beforeend') {
    const containerElement = typeof container === 'string'
        ? document.querySelector(container)
        : container;

    if (!containerElement) {
        throw new Error(`Container not found: ${container}`);
    }

    if (position === 'replace') {
        containerElement.innerHTML = html;
    } else {
        containerElement.insertAdjacentHTML(position, html);
    }
}

/**
 * 加载单个组件
 * @param {string} componentPath - 组件文件路径
 * @returns {Promise<string>} - 组件 HTML 内容
 */
async function loadComponent(componentPath) {
    // 检查缓存
    if (componentCache.has(componentPath)) {
        return componentCache.get(componentPath);
    }

    try {
        const response = await fetch(componentPath);
        if (!response.ok) {
            throw new Error(`Failed to load component: ${componentPath} (${response.status})`);
        }
        const html = await response.text();
        // 缓存组件
        componentCache.set(componentPath, html);
        return html;
    } catch (error) {
        console.error(`Error loading component ${componentPath}:`, error);
        throw error;
    }
}

/**
 * 将组件插入到指定容器
 * @param {string} componentPath - 组件文件路径
 * @param {string|HTMLElement} container - 容器选择器或元素
 * @param {string} position - 插入位置: 'replace', 'append', 'prepend', 'beforeend', 'afterbegin'
 * @returns {Promise<void>}
 */
async function insertComponent(componentPath, container, position = 'beforeend') {
    const component = prepareComponent(await loadComponent(componentPath));
    await Promise.all(component.styles);
    insertPreparedComponent(component.html, container, position);
}

/**
 * 批量加载多个组件
 * @param {Array<{path: string, container: string, position?: string}>} components - 组件配置数组
 * @returns {Promise<void>}
 */
async function loadComponents(components) {
    const prepared = await Promise.all(components.map(async component => ({
        ...component,
        ...prepareComponent(await loadComponent(component.path)),
    })));
    await Promise.all(prepared.flatMap(component => component.styles));
    prepared.forEach(component => {
        insertPreparedComponent(component.html, component.container, component.position);
    });
}

/**
 * 初始化页面组件
 * 加载所有页面组件并插入到相应位置
 * @returns {Promise<void>}
 */
async function initializeComponents() {
    if (initializationPromise) return initializationPromise;
    initializationPromise = (async () => {
        const basePath = 'components/';
        const components = [
            { path: `${basePath}header.html`, container: '.container', position: 'afterbegin' },
            { path: `${basePath}sidebar.html`, container: '#sidebar-container', position: 'replace' },
            { path: `${basePath}section-dashboard.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-accounts.html?v=5`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-playground.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-usage-stats.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-logs.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-api-keys.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-gems.html`, container: '#content-container', position: 'beforeend' },
            { path: `${basePath}section-settings.html`, container: '#content-container', position: 'beforeend' },
        ];
        await loadComponents(components);
        console.log('All components loaded successfully');
        window.dispatchEvent(new CustomEvent('componentsLoaded'));
    })();
    return initializationPromise;
}

/**
 * 清除组件缓存
 */
function clearComponentCache() {
    componentCache.clear();
    stylesheetCache.clear();
    initializationPromise = null;
}

// 导出函数
export {
    loadComponent,
    insertComponent,
    loadComponents,
    initializeComponents,
    clearComponentCache
};
