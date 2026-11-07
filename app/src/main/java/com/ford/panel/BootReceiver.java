package com.ford.panel;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * Teyp (araç başlığı) açıldığında FORD panelini otomatik başlatır.
 *
 * NEDEN: Bu tip Android teypler bazen soğuk açılır (Android logosu ->
 * BOOT_COMPLETED), bazen hızlı/sıcak açılır (QUICKBOOT_POWERON). İkisini de
 * yakalayıp MainActivity'yi öne getiriyoruz ki kullanıcı elle uygulamayı
 * açmak zorunda kalmasın. Ağ (hotspot) henüz gelmemiş olsa bile sorun değil;
 * panel kendi içinde bağlantıyı tekrar tekrar deniyor.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null) return;
        String act = intent.getAction();
        if (act == null) return;
        // Sadece açılış yayınlarına tepki ver.
        if (!act.equals(Intent.ACTION_BOOT_COMPLETED)
                && !act.equals("android.intent.action.QUICKBOOT_POWERON")
                && !act.equals("com.htc.intent.action.QUICKBOOT_POWERON")) {
            return;
        }
        // Soğuk açılışta paneli doğrudan öne getir (HOME ayarı da bunu kapsar,
        // bu ek bir güvence). Uyku-uyanma zaten HOME ile çözülür.
        try {
            Intent i = new Intent(context, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
        } catch (Exception e) {
            // Erken açılışta nadiren engellenebilir; yoksay.
        }
    }
}
