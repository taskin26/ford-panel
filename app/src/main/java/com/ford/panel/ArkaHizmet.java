package com.ford.panel;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Build;
import android.os.IBinder;

/**
 * Teyp UYKUDAN UYANINCA FORD panelini öne getiren kalıcı arka plan hizmeti.
 *
 * NEDEN: Teyp kontak kapanınca uyur, açılınca anında uyanır (soğuk açılış
 * değil -> BOOT_COMPLETED gelmez). Uyanmanın tek evrensel işareti ekranın
 * açılmasıdır (ACTION_SCREEN_ON). Bu yayın yalnız KOD İÇİNDEN (dinamik)
 * kaydedilebilir; manifest receiver yakalayamaz. Bu yüzden ayakta kalan bir
 * foreground servis tutup SCREEN_ON'u burada dinliyoruz ve MainActivity'yi
 * öne alıyoruz.
 *
 * Arka plandan aktivite başlatma Android 10+ kısıtlı; "diğer uygulamaların
 * üstünde göster" (SYSTEM_ALERT_WINDOW) izni verilince serbesttir. MainActivity
 * ilk açılışta bu izni ister.
 */
public class ArkaHizmet extends Service {

    static final String KANAL = "ford_arka";
    private BroadcastReceiver alici;

    @Override
    public void onCreate() {
        super.onCreate();
        oneGec();
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_USER_PRESENT);
        alici = new BroadcastReceiver() {
            @Override public void onReceive(Context c, Intent i) { paneliOneAl(c); }
        };
        try { registerReceiver(alici, f); } catch (Exception e) { /* yoksay */ }
    }

    /** MainActivity'yi öne getirir (uyandırır). Her yerden çağrılabilir. */
    static void paneliOneAl(Context c) {
        try {
            Intent i = new Intent(c, MainActivity.class);
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                    | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                    | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            c.startActivity(i);
        } catch (Exception e) { /* izin yoksa engellenebilir; yoksay */ }
    }

    private void oneGec() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationManager nm =
                        (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
                if (nm != null && nm.getNotificationChannel(KANAL) == null) {
                    nm.createNotificationChannel(new NotificationChannel(
                            KANAL, "FORD arka plan",
                            NotificationManager.IMPORTANCE_MIN));
                }
            }
            Notification.Builder b = (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
                    ? new Notification.Builder(this, KANAL)
                    : new Notification.Builder(this);
            Notification n = b.setContentTitle("FORD")
                    .setContentText("Panel hazır")
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .build();
            startForeground(42, n);
        } catch (Exception e) {
            // Foreground kurulamazsa servis yine de normal çalışır (START_STICKY).
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        try { if (alici != null) unregisterReceiver(alici); } catch (Exception e) { /* yoksay */ }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
