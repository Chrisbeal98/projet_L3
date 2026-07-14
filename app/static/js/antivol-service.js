/**
 * Service de verrouillage a distance — Antivol Intelligent
 * Ce script s'execute en arriere-plan sur le telephone.
 * Il interroge l'API toutes les 3 secondes et verrouille l'appareil si necessaire.
 */

const CONFIG = {
    API_URL: window.location.protocol + '//' + window.location.host + '/api',
    APPAREIL_ID: 1,
    IMEI: '351234567890123',
    POLL_INTERVAL: 3000,
    LOCK_DELAY: 1000,
};

let isLocked = false;
let lockOverlay = null;
let pollTimer = null;
let wakeLock = null;

// ═══════════════════════════════════════════
// BLOCAGE TOTAL — empêcher toute interaction
// ═══════════════════════════════════════════

document.addEventListener('keydown', function(e) {
    if (isLocked) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        return false;
    }
}, true);

document.addEventListener('touchmove', function(e) {
    if (isLocked) {
        e.preventDefault();
        return false;
    }
}, { passive: false, capture: true });

document.addEventListener('touchstart', function(e) {
    if (isLocked) {
        var touch = e.touches[0];
        if (touch.clientY < 50) {
            e.preventDefault();
            return false;
        }
    }
}, { passive: false, capture: true });

document.addEventListener('contextmenu', function(e) {
    e.preventDefault();
    return false;
}, true);

document.body.style.overscrollBehavior = 'none';

// ═══════════════════════════════════════════
// HISTORIQUE — empêcher bouton retour
// ═══════════════════════════════════════════
function bloquerRetour() {
    history.pushState(null, '', location.href);
    history.pushState(null, '', location.href);
}

window.addEventListener('popstate', function(e) {
    if (isLocked) {
        bloquerRetour();
    }
});

bloquerRetour();

window.addEventListener('beforeunload', function(e) {
    if (isLocked) {
        e.preventDefault();
        e.returnValue = '';
        return '';
    }
});

// ═══════════════════════════════════════════
// PLEIN ECRAN
// ═══════════════════════════════════════════
function activerPleinEcran() {
    try {
        var el = document.documentElement;
        if (el.requestFullscreen) {
            el.requestFullscreen().catch(function(){});
        } else if (el.webkitRequestFullscreen) {
            el.webkitRequestFullscreen();
        } else if (el.msRequestFullscreen) {
            el.msRequestFullscreen();
        }
    } catch(e) {}
}

// ═══════════════════════════════════════════
// WAKE LOCK — garder l'ecran allume
// ═══════════════════════════════════════════
async function activerWakeLock() {
    try {
        if ('wakeLock' in navigator) {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLock.addEventListener('release', function() {
                setTimeout(activerWakeLock, 1000);
            });
        }
    } catch(e) {}
}

document.addEventListener('visibilitychange', function() {
    if (isLocked && document.visibilityState === 'visible') {
        activerWakeLock();
        if (!lockOverlay) {
            showLockScreen();
        }
    }
});

// ═══════════════════════════════════════════
// AFFICHER L'ÉCRAN DE VERROUILLAGE INUTILISABLE
// ═══════════════════════════════════════════
function showLockScreen() {
    if (lockOverlay) return;

    activerPleinEcran();
    activerWakeLock();

    lockOverlay = document.createElement('div');
    lockOverlay.id = 'antivol-lock-screen';
    lockOverlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;width:100%;height:100%;background:linear-gradient(135deg,#1a0000,#0a0015,#000820);z-index:2147483647;display:flex;align-items:center;justify-content:center;touch-action:none;overscroll-behavior:none;';

    var codeHtml = '';
    if (CONFIG.CODE_VERROUILLAGE) {
        codeHtml = '<div style="background:rgba(239,68,68,0.1);border:1px dashed rgba(239,68,68,0.4);border-radius:12px;padding:16px;margin-bottom:20px;">' +
            '<div style="font-size:12px;color:#64748b;margin-bottom:6px;">Code de déverrouillage</div>' +
            '<div style="font-size:32px;font-weight:900;color:#ef4444;letter-spacing:8px;font-family:Courier New,monospace;">' + CONFIG.CODE_VERROUILLAGE + '</div>' +
            '</div>';
    }

    lockOverlay.innerHTML =
        '<div style="text-align:center;padding:40px 30px;max-width:380px;width:90%;background:rgba(20,0,30,0.95);backdrop-filter:blur(20px);border:1px solid rgba(239,68,68,0.3);border-radius:20px;box-shadow:0 0 60px rgba(239,68,68,0.3);">' +
            '<div style="margin-bottom:24px;">' +
                '<svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">' +
                    '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>' +
                    '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>' +
                    '<circle cx="12" cy="16" r="1"/>' +
                '</svg>' +
            '</div>' +
            '<h1 style="font-size:26px;font-weight:800;color:#ef4444;margin-bottom:12px;text-transform:uppercase;letter-spacing:1px;">Appareil Verrouillé</h1>' +
            '<p style="font-size:15px;color:#94a3b8;margin-bottom:8px;">Ce téléphone a été volé ! La localisation envoyée.</p>' +
            '<p style="color:#f59e0b;font-weight:600;font-size:13px;margin-bottom:20px;">Contactez le propriétaire ou les autorités.</p>' +
            codeHtml +
            '<div style="margin-top:16px;">' +
                '<input type="tel" id="unlock-code-input" placeholder="Entrez le code" maxlength="10" autocomplete="off" inputmode="numeric" ' +
                'style="width:100%;padding:14px 16px;background:rgba(255,255,255,0.05);border:1px solid rgba(239,68,68,0.3);border-radius:10px;color:white;font-size:18px;text-align:center;letter-spacing:6px;outline:none;font-family:Courier New,monospace;margin-bottom:12px;" />' +
                '<button id="unlock-btn" ' +
                'style="width:100%;padding:14px;background:#ef4444;border:none;border-radius:10px;color:white;font-weight:700;font-size:16px;cursor:pointer;font-family:Inter,sans-serif;">' +
                'Déverrouiller</button>' +
                '<div id="unlock-error" style="color:#ef4444;font-size:13px;margin-top:8px;min-height:20px;"></div>' +
            '</div>' +
            '<div style="margin-top:16px;padding:10px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:8px;font-size:12px;color:#22c55e;">' +
                'Localisation en cours de transmission...' +
            '</div>' +
            '<div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.1);">' +
                '<p style="color:#64748b;font-size:11px;font-family:monospace;margin-bottom:2px;">IMEI: ' + CONFIG.IMEI + '</p>' +
                '<p style="color:#64748b;font-size:11px;font-family:monospace;">ID: ' + CONFIG.APPAREIL_ID + '</p>' +
            '</div>' +
        '</div>';

    document.body.appendChild(lockOverlay);
    isLocked = true;

    bloquerRetour();

    lockOverlay.addEventListener('click', function(e) {
        e.stopPropagation();
    });

    document.getElementById('unlock-btn').addEventListener('click', attemptUnlock);

    var codeInput = document.getElementById('unlock-code-input');
    if (codeInput) {
        codeInput.addEventListener('touchstart', function(e) { e.stopPropagation(); }, { passive: true });
        codeInput.addEventListener('touchend', function(e) { e.stopPropagation(); }, { passive: true });
        codeInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                attemptUnlock();
            }
        });
        setTimeout(function() { codeInput.focus(); }, 500);
    }

    console.log('[AntiVol] Ecran de verrouillage ACTIVATE — appareil inutilisable');
}

// ═══════════════════════════════════════════
// MASQUER L'ÉCRAN DE VERROUILLAGE
// ═══════════════════════════════════════════
function hideLockScreen() {
    if (lockOverlay) {
        lockOverlay.remove();
        lockOverlay = null;
    }
    isLocked = false;

    try {
        if (document.exitFullscreen) document.exitFullscreen().catch(function(){});
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    } catch(e) {}

    if (wakeLock) {
        wakeLock.release();
        wakeLock = null;
    }

    console.log('[AntiVol] Ecran de verrouillage desactive');
}

// ═══════════════════════════════════════════
// TENTATIVE DE DÉVERROUILLAGE
// ═══════════════════════════════════════════
function attemptUnlock() {
    var input = document.getElementById('unlock-code-input');
    var errorMsg = document.getElementById('unlock-error');
    var code = input ? input.value.trim() : '';

    if (!code) {
        errorMsg.textContent = 'Entrez le code de déverrouillage.';
        return;
    }

    errorMsg.textContent = 'Vérification...';

    fetch(CONFIG.API_URL + '/appareils/' + CONFIG.APPAREIL_ID + '/verifier-code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code})
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        if (data.statut === 'actif') {
            hideLockScreen();
            errorMsg.textContent = '';
            console.log('[AntiVol] Appareil deverrouille avec succes');
        } else {
            errorMsg.textContent = data.error || 'Code incorrect. Réessayez.';
            if (input) input.value = '';
        }
    })
    .catch(function() {
        errorMsg.textContent = 'Erreur réseau. Réessayez.';
    });
}

// ═══════════════════════════════════════════
// VÉRIFICATION DU STATUT (POLLING)
// ═══════════════════════════════════════════
function checkDeviceStatus() {
    fetch(CONFIG.API_URL + '/appareils/' + CONFIG.APPAREIL_ID + '/statut')
        .then(function(res) {
            if (!res.ok) throw new Error('Erreur reseau');
            return res.json();
        })
        .then(function(data) {
            console.log('[AntiVol] Statut: ' + data.statut + ' | Verrouille: ' + data.verrouille);

            CONFIG.CODE_VERROUILLAGE = data.code_verrouillage || CONFIG.CODE_VERROUILLAGE;

            if (data.verrouille && !isLocked) {
                console.log('[AntiVol] VERROUILLAGE ACTIVE !');
                setTimeout(showLockScreen, CONFIG.LOCK_DELAY);
            } else if (!data.verrouille && isLocked) {
                console.log('[AntiVol] VERROUILLAGE DESACTIVE');
                hideLockScreen();
            }
        })
        .catch(function(err) {
            console.error('[AntiVol] Erreur de verification: ' + err.message);
        });
}

// ═══════════════════════════════════════════
// RE-VERROUILLAGE si tentative d'evasion
// ═══════════════════════════════════════════
window.addEventListener('pagehide', function(e) {
    if (isLocked) e.preventDefault();
});

// ═══════════════════════════════════════════
// INITIALISATION DU SERVICE
// ═══════════════════════════════════════════
function startAntiVolService() {
    console.log('[AntiVol] Service de protection active');
    console.log('[AntiVol] Appareil ID: ' + CONFIG.APPAREIL_ID);
    console.log('[AntiVol] Polling toutes les ' + (CONFIG.POLL_INTERVAL / 1000) + 's');

    checkDeviceStatus();
    pollTimer = setInterval(checkDeviceStatus, CONFIG.POLL_INTERVAL);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startAntiVolService);
} else {
    startAntiVolService();
}
