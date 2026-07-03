/**
 * Système Anti-Vol Intelligent
 * JavaScript principal — Interactions UI
 */

// ═══════════════════════════════════════
// THEME TOGGLE (mode sombre / clair)
// ═══════════════════════════════════════
(function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }
})();

function toggleTheme() {
    const html = document.documentElement;
    const isLight = html.getAttribute('data-theme') === 'light';
    if (isLight) {
        html.removeAttribute('data-theme');
        localStorage.setItem('theme', 'dark');
    } else {
        html.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
    }
    updateThemeIcon();
}

function updateThemeIcon() {
    const icon = document.getElementById('themeIcon');
    if (!icon) return;
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    icon.setAttribute('data-lucide', isLight ? 'sun' : 'moon');
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
}

document.addEventListener('DOMContentLoaded', updateThemeIcon);

// ═══════════════════════════════════════
// SIDEBAR TOGGLE
// ═══════════════════════════════════════
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        const isOpen = sidebar.classList.toggle('open');
        document.body.style.overflow = isOpen ? 'hidden' : '';
    }
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar && sidebar.classList.contains('open')) {
        sidebar.classList.remove('open');
        document.body.style.overflow = '';
    }
}

// Fermer sidebar en cliquant en dehors (mobile)
document.addEventListener('click', (e) => {
    const sidebar = document.getElementById('sidebar');
    const menuToggle = document.getElementById('menuToggle');
    if (sidebar && sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        (!menuToggle || !menuToggle.contains(e.target))) {
        closeSidebar();
    }
});

// Fermer sidebar avec Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeSidebar();
    }
});


// ═══════════════════════════════════════
// MODALS
// ═══════════════════════════════════════
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
        // Re-render Lucide icons dans le modal
        if (typeof lucide !== 'undefined') {
            setTimeout(() => lucide.createIcons(), 50);
        }
    }
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Fermer modal en cliquant sur l'overlay
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Fermer modal avec Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal-overlay.active');
        modals.forEach(modal => {
            modal.classList.remove('active');
        });
        document.body.style.overflow = '';
    }
});


// ═══════════════════════════════════════
// PASSWORD TOGGLE
// ═══════════════════════════════════════
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
    }
}


// ═══════════════════════════════════════
// FLASH MESSAGES AUTO-DISMISS
// ═══════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach((msg, index) => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transform = 'translateX(-20px)';
            setTimeout(() => msg.remove(), 300);
        }, 4000 + (index * 500));
    });
});


// ═══════════════════════════════════════
// ANIMATIONS D'ENTRÉE
// ═══════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    // Animer les cartes statistiques
    const statCards = document.querySelectorAll('.stat-card');
    statCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.5s cubic-bezier(0.4, 0, 0.2, 1)';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 + (index * 80));
    });

    // Animer les cartes
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(15px)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 300 + (index * 100));
    });

    // Animer les valeurs statistiques (compteur)
    const statValues = document.querySelectorAll('.stat-value');
    statValues.forEach(el => {
        const target = parseInt(el.textContent);
        if (isNaN(target) || target === 0) return;

        el.textContent = '0';
        const duration = 1000;
        const start = performance.now();

        function animate(currentTime) {
            const elapsed = currentTime - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            el.textContent = Math.round(target * eased);

            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        }

        setTimeout(() => requestAnimationFrame(animate), 500);
    });
});


// ═══════════════════════════════════════
// UTILITAIRES
// ═══════════════════════════════════════

// Confirmer les actions destructives
document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
        if (!confirm(el.dataset.confirm)) {
            e.preventDefault();
        }
    });
});

// ═══════════════════════════════════════
// LANGUAGE DROPDOWN
// ═══════════════════════════════════════
function toggleLangDropdown() {
    const dropdown = document.getElementById('langDropdown');
    const current = document.querySelector('.lang-current');
    if (dropdown) {
        dropdown.classList.toggle('open');
        current.classList.toggle('open');
        if (dropdown.classList.contains('open')) {
            setTimeout(() => {
                const search = document.getElementById('langSearch');
                if (search) search.focus();
            }, 100);
        }
    }
}

function filterLangs() {
    const search = document.getElementById('langSearch');
    const filter = search.value.toLowerCase();
    const items = document.querySelectorAll('.lang-option');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(filter) ? 'block' : 'none';
    });
}

// Fermer le dropdown en cliquant dehors
document.addEventListener('click', (e) => {
    const selector = document.querySelector('.lang-selector');
    const dropdown = document.getElementById('langDropdown');
    if (selector && dropdown && !selector.contains(e.target)) {
        dropdown.classList.remove('open');
        const current = document.querySelector('.lang-current');
        if (current) current.classList.remove('open');
    }
});

// Fermer le dropdown avec Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const dropdown = document.getElementById('langDropdown');
        if (dropdown && dropdown.classList.contains('open')) {
            dropdown.classList.remove('open');
            const current = document.querySelector('.lang-current');
            if (current) current.classList.remove('open');
        }
    }
});

// Format de date relatif
function timeAgo(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return 'À l\'instant';
    if (diff < 3600) return `Il y a ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `Il y a ${Math.floor(diff / 3600)} h`;
    if (diff < 604800) return `Il y a ${Math.floor(diff / 86400)} j`;
    return date.toLocaleDateString('fr-FR');
}
