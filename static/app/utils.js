/**
 * 工具函数模块
 */

/**
 * 遮蔽敏感字符串
 * @param {string} str - 原始字符串
 * @param {number} showChars - 显示的字符数
 * @returns {string}
 */
function maskString(str, showChars = 10) {
    if (!str) return '';
    if (str.length <= showChars) return str;
    return str.substring(0, showChars) + '...';
}

/**
 * 格式化数字
 * @param {number} num - 数字
 * @returns {string}
 */
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString('zh-CN');
}

/**
 * 获取状态徽章HTML
 * @param {string} status - 状态
 * @returns {string}
 */
function getStatusBadge(status) {
    const statusMap = {
        'active': { text: '活跃', class: 'success' },
        'inactive': { text: '不活跃', class: 'secondary' },
        'error': { text: '错误', class: 'danger' },
        'disabled': { text: '已禁用', class: 'secondary' }
    };

    const statusInfo = statusMap[status] || { text: status, class: 'secondary' };
    return `<span class="badge badge-${statusInfo.class}">${statusInfo.text}</span>`;
}

/**
 * 格式化日期
 * @param {string} isoString - ISO日期字符串
 * @returns {string}
 */
function formatDate(isoString) {
    if (!isoString) return '-';
    try {
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch (error) {
        return isoString;
    }
}

/**
 * 复制文本到剪贴板
 * @param {string} text - 要复制的文本
 * @returns {Promise<void>}
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('复制成功', 'success');
    } catch (error) {
        console.error('复制失败:', error);
        showToast('复制失败', 'error');
    }
}

/**
 * 显示Toast通知
 * @param {string} message - 消息内容
 * @param {string} type - 消息类型: 'success', 'error', 'warning', 'info'
 */
function showToast(message, type = 'info') {
    // 创建toast容器（如果不存在）
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container';
        document.body.appendChild(toastContainer);
    }

    // 创建toast元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // 图标映射
    const iconMap = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const icon = iconMap[type] || iconMap.info;

    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;

    toastContainer.appendChild(toast);

    // 触发动画
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    // 3秒后移除
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);
}

/**
 * 转义HTML特殊字符
 * @param {string} str - 原始字符串
 * @returns {string}
 */
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string}
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * 防抖函数
 * @param {Function} func - 要防抖的函数
 * @param {number} wait - 等待时间（毫秒）
 * @returns {Function}
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数
 * @param {Function} func - 要节流的函数
 * @param {number} limit - 时间限制（毫秒）
 * @returns {Function}
 */
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// 导出函数
export {
    maskString,
    formatNumber,
    getStatusBadge,
    formatDate,
    copyToClipboard,
    showToast,
    escapeHtml,
    formatFileSize,
    debounce,
    throttle
};
