package com.antivol;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

public class ScreenOnReceiver extends BroadcastReceiver {
    private static final String TAG = "ScreenOnReceiver";
    private static final String PREF_NAME = "antivol_prefs";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_SCREEN_ON.equals(intent.getAction())) {
            SharedPreferences prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
            boolean isLocked = prefs.getBoolean("was_locked", false);

            if (isLocked) {
                Log.d(TAG, "Écran allumé — appareil verrouillé, lancement LockActivity");
                Intent lockIntent = new Intent(context, LockActivity.class);
                lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_NO_ANIMATION
                    | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                context.startActivity(lockIntent);
            }
        }
    }
}
