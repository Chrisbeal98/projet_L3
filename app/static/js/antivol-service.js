/**
 * Service de vérification de verrouillage à distance — Antivol Intelligent
 * Ce script s'exécute en arrière-plan sur le téléphone.
 * Il interroge l'API toutes les 5 secondes pour vérifier si l'appareil doit être verrouillé.
 */

const CONFIG = {
    API_URL: 'http://192.168.45.36:8000/api', // IP du serveur Flask
    APPAREIL_ID: 1,                           // ID de l'appareil
    IMEI: '351234567890123',                  // IMEI du téléphone
    POLL_INTERVAL: 5000,                      // Vérification toutes les 5 secondes
    LOCK_DELAY: 3000,                         // Délai avant verrouillage (3s)
    SECRET_CODE: '987654321',                 // Code de déverrouillage (pour l'app)
};

let isLocked = false;
let lockOverlay = null;
let pollTimer = null;

// ═══════════════════════════════════════════
// AFFICHER L'ÉCRAN DE VERROUILLAGE
// ═══════════════════════════════════════════
function showLockScreen() {
    if (lockOverlay) return;

    lockOverlay = document.createElement('div');
    lockOverlay.id = 'antivol-lock-screen';
    lockOverlay.innerHTML = `
        <div class="lock-overlay">
            <div class="lock-content">
                <div class="lock-icon">
                    <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2">
                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        <circle cx="12" cy="16" r="1"/>
                    </svg>
                </div>
                <h1>Appareil Verrouillé</h1>
                <p>Cet appareil a été signalé comme volé ou perdu.</p>
                <p class="warning-text">Contactez le propriétaire ou les autorités.</p>
                <div class="code-input">
                    <input type="password" id="unlock-code" placeholder="Code de déverrouillage" maxlength="9" />
                    <button onclick="attemptUnlock()">Déverrouiller</button>
                </div>
                <p id="unlock-error" class="error-msg"></p>
                <div class="device-info">
                    <p>IMEI: ${CONFIG.IMEI}</p>
                    <p>ID: ${CONFIG.APPAREIL_ID}</p>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(lockOverlay);
    isLocked = true;
    console.log('[AntiVol] Écran de verrouillage activé');
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
    console.log('[AntiVol] Écran de verrouillage désactivé');
}

// ═══════════════════════════════════════════
// TENTATIVE DE DÉVERROUILLAGE
// ═══════════════════════════════════════════
function attemptUnlock() {
    const code = document.getElementById('unlock-code').value;
    const errorMsg = document.getElementById('unlock-error');

    if (code === CONFIG.SECRET_CODE) {
        // Vérifier côté serveur que le statut est bien 'actif'
        fetch(`${CONFIG.API_URL}/appareils/${CONFIG.APPAREIL_ID}/statut`)
            .then(res => res.json())
            .then(data => {
                if (!data.verrouille) {
                    hideLockScreen();
                    errorMsg.textContent = '';
                    console.log('[AntiVol] Appareil déverrouillé avec succès');
                } else {
                    errorMsg.textContent = "L'appareil est toujours verrouillé côté serveur.";
                }
            });
    } else {
        errorMsg.textContent = 'Code incorrect.';
        console.log('[AntiVol] Code de déverrouillage incorrect');
    }
}

// ═══════════════════════════════════════════
// VÉRIFICATION DU STATUT (POLLING)
// ═══════════════════════════════════════════
function checkDeviceStatus() {
    fetch(`${CONFIG.API_URL}/appareils/${CONFIG.APPAREIL_ID}/statut`)
        .then(res => {
            if (!res.ok) throw new Error('Erreur réseau');
            return res.json();
        })
        .then(data => {
            console.log(`[AntiVol] Statut: ${data.statut} | Verrouillé: ${data.verrouille}`);

            if (data.verrouille && !isLocked) {
                console.log('[AntiVol] VERROUILLAGE ACTIVÉ !');
                setTimeout(() => showLockScreen(), CONFIG.LOCK_DELAY);
            } else if (!data.verrouille && isLocked) {
                console.log('[AntiVol] VERROUILLAGE DÉSACTIVÉ');
                hideLockScreen();
            }
        })
        .catch(err => {
            console.error(`[AntiVol] Erreur de vérification: ${err.message}`);
        });
}

// ═══════════════════════════════════════════
// EMPÊCHER LA SUPPRESSION DU SCRIPT
// ═══════════════════════════════════════════
function protectService() {
    // Empêcher la fermeture par raccourcis clavier
    document.addEventListener('keydown', (e) => {
        if (isLocked) {
            if (e.key === 'F4' || (e.altKey && e.key === 'F4') || (e.ctrlKey && e.key === 'w')) {
                e.preventDefault();
                console.log('[AntiVol] Fermeture bloquée');
            }
        }
    });
}

// ═══════════════════════════════════════════
// INITIALISATION DU SERVICE
// ═══════════════════════════════════════════
function startAntiVolService() {
    console.log('[AntiVol] Service de protection activé');
    console.log(`[AntiVol] Appareil ID: ${CONFIG.APPAREIL_ID}`);
    console.log(`[AntiVol] IMEI: ${CONFIG.IMEI}`);
    console.log(`[AntiVol] Vérification toutes les ${CONFIG.POLL_INTERVAL / 1000}s`);

    // Vérification immédiate
    checkDeviceStatus();

    // Polling régulier
    pollTimer = setInterval(checkDeviceStatus, CONFIG.POLL_INTERVAL);

    // Protection
    protectService();
}

// Lancer le service au chargement
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startAntiVolService);
} else {
    startAntiVolService();
}
