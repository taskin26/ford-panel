package com.ford.panel;

import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothSocket;
import android.os.Handler;
import android.os.Looper;

import java.io.InputStream;
import java.io.OutputStream;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Bluetooth (SPP) ile Pi'ye komut yollar. WiFi/internet OLMASA da calisir.
 * Pi'de 'ford_btkomut.py' SPP sunucusu calisir.
 * Kullanmadan once telefon Pi ('ford') ile BIR KEZ eslestirilmeli.
 */
public class BtKontrol {

    public static final UUID SPP =
            UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
    public static final String PI_AD = "ford";

    public interface Dinleyici {
        void durum(String mesaj, boolean bagli);
        void cevap(String satir);
    }

    private final Dinleyici dinleyici;
    private final ExecutorService exec = Executors.newSingleThreadExecutor();
    private final Handler ana = new Handler(Looper.getMainLooper());

    private BluetoothSocket soket;
    private OutputStream cikis;
    private InputStream giris;
    private volatile boolean bagli = false;

    // Genel istek/yanit koprusu: "REQ|<method>|<b64yol>|<b64govde>" yolla, "RES|<status>|<b64body>" bekle.
    private final Object istekKilit = new Object();
    private volatile String sonYanit = null;
    // Ayni anda tek BT istegi aksin (SPP tek akis) - id eslestirme gerekmez.
    private final Object btReqLock = new Object();

    public BtKontrol(Dinleyici d) { this.dinleyici = d; }

    public boolean bagliMi() { return bagli; }

    /**
     * BT uzerinden HERHANGI bir panel API istegini (GET/POST + govde) Pi'ye tasir.
     * Doner: "statuskodu\u0001yanitgovdesi" (shim ayristirir), ulasilamazsa null.
     * Istekler sirayla gider (tek akis), her biri kendi yanitini bekler.
     */
    public String istek(String method, String path, String body) {
        synchronized (btReqLock) {
            if (!bagli || cikis == null) return null;
            String b64p, b64b;
            try {
                b64p = android.util.Base64.encodeToString(
                        path.getBytes("UTF-8"), android.util.Base64.NO_WRAP);
                b64b = android.util.Base64.encodeToString(
                        (body == null ? "" : body).getBytes("UTF-8"), android.util.Base64.NO_WRAP);
            } catch (Exception e) { return null; }

            synchronized (istekKilit) { sonYanit = null; }
            try {
                String req = "REQ|" + method + "|" + b64p + "|" + b64b + "\n";
                cikis.write(req.getBytes("UTF-8"));
                cikis.flush();
            } catch (Exception e) {
                bagli = false;
                kapatIc();
                return null;
            }

            String yanit;
            synchronized (istekKilit) {
                long bitis = System.currentTimeMillis() + 6000;  // yukleme/liste icin genis
                while (sonYanit == null) {
                    long kalan = bitis - System.currentTimeMillis();
                    if (kalan <= 0) break;
                    try { istekKilit.wait(kalan); } catch (InterruptedException e) { break; }
                }
                yanit = sonYanit;
            }
            if (yanit == null) return null;

            // yanit = "<status>|<b64body>"
            int p = yanit.indexOf('|');
            String st = (p >= 0) ? yanit.substring(0, p) : "200";
            String b64 = (p >= 0) ? yanit.substring(p + 1) : "";
            String gov;
            try {
                gov = new String(android.util.Base64.decode(b64, android.util.Base64.DEFAULT), "UTF-8");
            } catch (Exception e) { gov = "{}"; }
            return st + "\u0001" + gov;
        }
    }

    private void bildirDurum(String m, boolean b) { ana.post(() -> dinleyici.durum(m, b)); }
    private void bildirCevap(String s) { ana.post(() -> dinleyici.cevap(s)); }

    public void baglan() { exec.execute(this::baglanIc); }

    private void baglanIc() {
        try {
            BluetoothAdapter ad = BluetoothAdapter.getDefaultAdapter();
            if (ad == null) { bildirDurum("Bu cihazda Bluetooth yok", false); return; }
            if (!ad.isEnabled()) { bildirDurum("Bluetooth kapali - once ac", false); return; }

            // "ford" iceren TUM esli cihazlar aday; "fordconnect" olani basa al.
            // (Telefonda Ford Transit Courier = araba radyosu, Ford-Connect vb. de olabilir.)
            java.util.List<BluetoothDevice> adaylar = new java.util.ArrayList<>();
            for (BluetoothDevice d : ad.getBondedDevices()) {
                String n = null;
                try { n = d.getName(); } catch (SecurityException ignored) {}
                if (n == null) continue;
                String norm = n.toLowerCase().replaceAll("[^a-z0-9]", "");
                if (norm.contains("fordconnect")) adaylar.add(0, d);        // Pi'yi basa al
                else if (n.toLowerCase().contains(PI_AD)) adaylar.add(d);
            }
            if (adaylar.isEmpty()) {
                bildirDurum("Esli 'FordConnect' cihazi yok.\n"
                        + "Telefon Bluetooth'tan Pi ile eslestir.", false);
                return;
            }

            ad.cancelDiscovery();
            BluetoothSocket s = null;
            for (BluetoothDevice pi : adaylar) {
                String isim = null;
                try { isim = pi.getName(); } catch (Exception ignored) {}
                bildirDurum("Baglaniyor: " + (isim != null ? isim : "?") + "...", false);
                s = baglanDenemeleri(ad, pi);
                if (s != null) break;
            }
            soket = s;
            if (soket == null) {
                bagli = false;
                bildirDurum("BT baglanamadi - Pi/servis acik mi?", false);
                return;
            }
            cikis = soket.getOutputStream();
            giris = soket.getInputStream();
            bagli = true;
            bildirDurum("Bluetooth bagli", true);

            new Thread(this::okuDongusu, "bt-oku").start();

        } catch (Exception e) {
            bagli = false;
            bildirDurum("BT baglanamadi: " + kisaHata(e), false);
            kapatIc();
        }
    }

    private interface SoketUret { BluetoothSocket uret() throws Exception; }

    /** Birkac yontemle baglanmayi dener; ilk basarili soketi doner, olmazsa null. */
    private BluetoothSocket baglanDenemeleri(BluetoothAdapter ad, final BluetoothDevice pi) {
        // 1) Guvenli, SDP ile
        BluetoothSocket s = dene(() -> pi.createRfcommSocketToServiceRecord(SPP), ad);
        if (s != null) return s;
        // 2) Servis listesini tazele, sonra guvensiz SDP ile (onbellek sorununu asar)
        try { pi.fetchUuidsWithSdp(); } catch (Exception ignored) {}
        try { Thread.sleep(1600); } catch (InterruptedException ignored) {}
        s = dene(() -> pi.createInsecureRfcommSocketToServiceRecord(SPP), ad);
        if (s != null) return s;
        // 3) Sabit kanala dogrudan (SDP olmadan) - yansima
        for (int kanal : new int[]{1, 22, 3}) {
            final int k = kanal;
            s = dene(() -> (BluetoothSocket) pi.getClass()
                    .getMethod("createInsecureRfcommSocket", int.class).invoke(pi, k), ad);
            if (s != null) return s;
            s = dene(() -> (BluetoothSocket) pi.getClass()
                    .getMethod("createRfcommSocket", int.class).invoke(pi, k), ad);
            if (s != null) return s;
        }
        return null;
    }

    private BluetoothSocket dene(SoketUret uretici, BluetoothAdapter ad) {
        BluetoothSocket s = null;
        try {
            s = uretici.uret();
            if (s == null) return null;
            ad.cancelDiscovery();
            s.connect();
            return s;
        } catch (Exception e) {
            if (s != null) { try { s.close(); } catch (Exception ignored) {} }
            return null;
        }
    }

    private void okuDongusu() {
        byte[] tmp = new byte[256];
        StringBuilder sb = new StringBuilder();
        try {
            int n;
            while (bagli && giris != null && (n = giris.read(tmp)) > 0) {
                sb.append(new String(tmp, 0, n, "UTF-8"));
                int idx;
                while ((idx = sb.indexOf("\n")) >= 0) {
                    String satir = sb.substring(0, idx).trim();
                    sb.delete(0, idx + 1);
                    if (satir.isEmpty()) continue;
                    if (satir.startsWith("RES|")) {
                        // Genel istege yanit: "RES|<status>|<b64body>"
                        synchronized (istekKilit) {
                            sonYanit = satir.substring(4);
                            istekKilit.notifyAll();
                        }
                    }
                    // RES| disi satirlar (selamlama "FORD BT HAZIR", eski Pi'nin
                    // "RET|...izinsiz" gurultusu vb.) SESSIZCE yok sayilir -> toast spam olmaz.
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (bagli) { bagli = false; bildirDurum("BT baglantisi dustu", false); }
        }
    }

    public void gonder(final String komut) {
        exec.execute(() -> {
            if (!bagli || cikis == null) { bildirDurum("Once Bluetooth'a baglan", false); return; }
            try {
                cikis.write((komut + "\n").getBytes("UTF-8"));
                cikis.flush();
            } catch (Exception e) {
                bagli = false;
                bildirDurum("Gonderilemedi: " + kisaHata(e), false);
                kapatIc();
            }
        });
    }

    public void kapat() { exec.execute(this::kapatIc); }

    private void kapatIc() {
        bagli = false;
        try { if (soket != null) soket.close(); } catch (Exception ignored) {}
        soket = null; cikis = null; giris = null;
    }

    private String kisaHata(Exception e) {
        String m = e.getMessage();
        return m == null ? e.getClass().getSimpleName() : m;
    }
}
