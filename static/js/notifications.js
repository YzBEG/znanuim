function bootNotifications() {
    const messages = document.querySelectorAll('.message');

    messages.forEach(function(message, index) {
        const hideDelay = 5000 + (index * 500);

        setTimeout(function() {
            message.classList.add('hiding');

            setTimeout(function() {
                const messagesContainer = message.closest('.messages');
                message.remove();
                if (messagesContainer && messagesContainer.children.length === 0) {
                    messagesContainer.remove();
                }
            }, 300);
        }, hideDelay);

        message.style.cursor = 'pointer';
        message.addEventListener('click', function() {
            message.classList.add('hiding');
            setTimeout(function() {
                message.remove();
            }, 300);
        });
    });

    initMobileHeaderMenu();
    initNotificationCenter();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootNotifications);
} else {
    bootNotifications();
}

function initNotificationCenter() {
    const headerActions = document.querySelector('.header-actions');
    if (!headerActions || document.querySelector('.notification-center') || !document.body.dataset.authenticated) {
        return;
    }

    const center = document.createElement('div');
    center.className = 'notification-center';
    center.innerHTML = `
        <button class="notification-button" type="button" aria-label="Уведомления">
            <svg class="notification-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none">
                <path d="M15 17H9m9-1v-5a6 6 0 1 0-12 0v5l-2 2h16l-2-2Zm-4 4a2 2 0 0 1-4 0" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span class="notification-badge" hidden>0</span>
        </button>
        <div class="notification-dropdown" hidden>
            <div class="notification-head">
                <strong>Уведомления</strong>
                <button type="button" class="notification-read-all">Прочитано</button>
            </div>
            <div class="notification-list">
                <div class="notification-empty">Пока уведомлений нет</div>
            </div>
        </div>
    `;
    headerActions.prepend(center);

    const button = center.querySelector('.notification-button');
    const badge = center.querySelector('.notification-badge');
    const dropdown = center.querySelector('.notification-dropdown');
    const list = center.querySelector('.notification-list');
    const readAllButton = center.querySelector('.notification-read-all');
    let notifications = [];
    let socket = null;

    function render(unreadCount) {
        badge.hidden = !unreadCount;
        badge.textContent = unreadCount || 0;

        if (!notifications.length) {
            list.innerHTML = '<div class="notification-empty">Пока уведомлений нет</div>';
            return;
        }

        list.innerHTML = notifications.map((item) => `
            <a class="notification-item ${item.is_read ? '' : 'is-unread'}" href="${item.url || '#'}" data-id="${item.id}">
                <span class="notification-kind">${kindLabel(item.kind)}</span>
                <strong>${escapeHtml(item.title)}</strong>
                ${item.body ? `<p>${escapeHtml(item.body)}</p>` : ''}
                <time>${escapeHtml(item.created_at)}</time>
            </a>
        `).join('');
    }

    function kindLabel(kind) {
        if (kind === 'lesson') return 'Урок';
        if (kind === 'message') return 'Чат';
        return 'Система';
    }

    function showToast(item) {
        const toast = document.createElement('a');
        toast.className = 'notification-toast';
        toast.href = item.url || '#';
        toast.innerHTML = `
            <span>${kindLabel(item.kind)}</span>
            <strong>${escapeHtml(item.title)}</strong>
            ${item.body ? `<p>${escapeHtml(item.body)}</p>` : ''}
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add('is-visible'), 20);
        setTimeout(() => {
            toast.classList.remove('is-visible');
            setTimeout(() => toast.remove(), 220);
        }, 5200);
    }

    function markRead(id) {
        const formData = new FormData();
        if (id) {
            formData.append('id', id);
        }
        return fetch('/chat/notifications/read/', {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
            credentials: 'same-origin',
            body: formData,
        }).then((response) => response.ok ? response.json() : null);
    }

    fetch('/chat/notifications/')
        .then((response) => {
            if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) {
                throw new Error('Notifications are unavailable');
            }
            return response.json();
        })
        .then((data) => {
            notifications = data.notifications || [];
            render(data.unread_count || 0);
            connectSocket();
        })
        .catch(() => {
            center.remove();
        });

    button.addEventListener('click', () => {
        dropdown.hidden = !dropdown.hidden;
    });

    readAllButton.addEventListener('click', () => {
        notifications = [];
        render(0);
        dropdown.hidden = true;
        markRead().then((data) => {
            if (data) {
                notifications = data.notifications || [];
                render(data.unread_count || 0);
            }
        });
    });

    document.addEventListener('click', (event) => {
        if (!center.contains(event.target)) {
            dropdown.hidden = true;
        }
    });

    list.addEventListener('click', (event) => {
        const item = event.target.closest('.notification-item');
        if (item) {
            event.preventDefault();
            const targetUrl = item.getAttribute('href');
            notifications = notifications.filter((notification) => String(notification.id) !== String(item.dataset.id));
            render(Math.max(notifications.length, 0));
            markRead(item.dataset.id).then((data) => {
                if (data) {
                    notifications = data.notifications || notifications;
                    render(data.unread_count || 0);
                }
                if (targetUrl && targetUrl !== '#') {
                    window.location.href = targetUrl;
                }
            }).catch(() => {
                if (targetUrl && targetUrl !== '#') {
                    window.location.href = targetUrl;
                }
            });
        }
    });

    function connectSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        socket = new WebSocket(`${protocol}://${window.location.host}/ws/notifications/`);

        socket.addEventListener('message', (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'notifications_state') {
                notifications = data.notifications || [];
                render(data.unread_count || 0);
            }
            if (data.type === 'notification_created') {
                notifications = [data.notification, ...notifications].slice(0, 8);
                render(data.unread_count || 0);
                showToast(data.notification);
            }
        });
    }
}

function initMobileHeaderMenu() {
    const header = document.querySelector('.site-header');
    const headerInner = document.querySelector('.header-inner');
    const headerActions = document.querySelector('.header-actions');

    if (!header || !headerInner || !headerActions || header.querySelector('.mobile-menu-button')) {
        return;
    }

    const menuButton = document.createElement('button');
    menuButton.className = 'mobile-menu-button';
    menuButton.type = 'button';
    menuButton.setAttribute('aria-label', 'Открыть меню');
    menuButton.setAttribute('aria-expanded', 'false');
    menuButton.innerHTML = `
        <span></span>
        <span></span>
        <span></span>
    `;

    headerInner.insertBefore(menuButton, headerActions);

    menuButton.addEventListener('click', () => {
        const isOpen = header.classList.toggle('is-menu-open');
        menuButton.setAttribute('aria-expanded', String(isOpen));
        menuButton.setAttribute('aria-label', isOpen ? 'Закрыть меню' : 'Открыть меню');
    });
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return '';
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value || '';
    return div.innerHTML;
}
