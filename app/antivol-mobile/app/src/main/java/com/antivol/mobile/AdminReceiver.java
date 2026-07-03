package com.antivol.mobile;

import android.app.admin.DeviceAdminReceiver;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.Toast;

public class AdminReceiver extends DeviceAdminReceiver {

    @Override
    public void onEnabled(Context context, Intent intent) {
        DevicePolicyManager dpm = (DevicePolicyManager)
                context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(context, AdminReceiver.class);
        // Autoriser le mode kiosque (bloque Home/Récents)
        dpm.setLockTaskPackages(admin, new String[]{context.getPackageName()});
        Toast.makeText(context, "Protection AntiVol activée", Toast.LENGTH_LONG).show();
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        Toast.makeText(context, "⚠️ Protection AntiVol désactivée !", Toast.LENGTH_LONG).show();

        // Si l'appareil est en statut verrouillé, réactiver immédiatement
        DevicePolicyManager dpm = (DevicePolicyManager)
                context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(context, AdminReceiver.class);
        if (!dpm.isAdminActive(admin)) {
            // Lancer l'activité pour réactiver
            Intent activateIntent = new Intent(context, MainActivity.class);
            activateIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(activateIntent);
        }
    }

    @Override
    public void onPasswordChanged(Context context, Intent intent) {
        Toast.makeText(context, "Mot de passe verrouillage modifié", Toast.LENGTH_SHORT).show();
    }

    @Override
    public void onPasswordFailed(Context context, Intent intent) {
        // Tentative de déverrouillage échouée
    }

    @Override
    public void onPasswordSucceeded(Context context, Intent intent) {
        // Déverrouillage réussi
    }

    @Override
    public CharSequence onDisableRequested(Context context, Intent intent) {
        // Message affiché quand l'utilisateur tente de désactiver l'admin
        return "La protection Admin est nécessaire pour le verrouillage à distance. " +
               "Si vous désactivez cette protection, l'AntiVol ne pourra plus verrouiller " +
               "votre appareil en cas de vol. Êtes-vous sûr ?";
    }
}
