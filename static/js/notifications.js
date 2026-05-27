document.addEventListener('DOMContentLoaded', function() {
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

    initNotificationCenter();
});

function initNotificationCenter() {
    const headerActions = document.querySelector('.header-actions');
    if (!headerActions || document.querySelector('.notification-center')) {
        return;
    }

    const center = document.createElement('div');
    center.className = 'notification-center';
    center.innerHTML = `
        <button class="notification-button" type="button" aria-label="Уведомления">
            <i class="fa-regular fa-bell"></i>
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
        if (!dropdown.hidden) {
            markRead().then((data) => {
                if (data) {
                    notifications = notifications.map((item) => ({ ...item, is_read: true }));
                    render(data.unread_count || 0);
                }
            });
        }
    });

    readAllButton.addEventListener('click', () => {
        markRead().then((data) => {
            if (data) {
                notifications = notifications.map((item) => ({ ...item, is_read: true }));
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
            markRead(item.dataset.id);
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
