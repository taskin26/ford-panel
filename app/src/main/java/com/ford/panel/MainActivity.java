package com.ford.panel;

import android.Manifest;
import android.app.AlertDialog;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.net.wifi.WifiNetworkSpecifier;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * FORD Panel - TEK UYGULAMA.
 *  - Panel (ford_ekran.html) APK'nin ICINE gomulu: uygulama acilinca panel HER ZAMAN gelir.
 *  - WiFi (FORD) ile Pi'ye ulasilabiliyorsa panel Pi'den CANLI yuklenir (tum ozellikler calisir).
 *  - WiFi yoksa gomulu panel gosterilir; butona basinca komut BLUETOOTH'tan gider.
 *  - Ikisi de yoksa panel yine ekranda kalir, "baglanti yok" uyarisi verir.
 *  - Ust seritte: "WiFi ile Baglan" ve "Bluetooth ile Baglan" + durum isigi.
 */
public class MainActivity extends android.app.Activity implements BtKontrol.Dinleyici {

    // Pi'ye once ford.local (ev wifi / telefon hotspot), sonra 10.42.0.1 (FORD-AP) denenir.
    static final String[] PI_ADAYLAR = {
            "http://ford.local:8080",
            "http://10.42.0.1:8080"
    };
    private volatile String piBase = "http://ford.local:8080";
    static final String YEREL_URL = "file:///android_asset/ford_ekran.html";
    static final String FORD_SSID = "FORD";
    static final String FORD_PASS = "fordconnect";

    private WebView web;
    private TextView durum;
    private Button wifiBtn, btBtn, homeBtn;
    private BtKontrol bt;
    private ConnectivityManager cm;
    private ConnectivityManager.NetworkCallback agGeri;

    private volatile boolean piCanli = false;   // panel su an Pi'den mi yuklu
    private final ExecutorService exec = Executors.newSingleThreadExecutor();
    private final Handler ana = new Handler(Looper.getMainLooper());

    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(R.layout.activity_main);

        cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        bt = new BtKontrol(this);

        web    = findViewById(R.id.web);
        durum  = findViewById(R.id.durum);
        wifiBtn= findViewById(R.id.wifiBtn);
        btBtn  = findViewById(R.id.btBtn);
        homeBtn= findViewById(R.id.homeBtn);

        kurWebView();
        wifiBtn.setOnClickListener(v -> wifiBaglan());
        btBtn.setOnClickListener(v -> btBaglan());
        homeBtn.setOnClickListener(v -> anaEkranaDon());

        // Panel HEMEN (gomulu) acilir -> her zaman gorunur.
        web.loadUrl(YEREL_URL);
        durumYaz("Baglanti araniyor...");
        // Arka planda Pi'ye ulasiliyor mu diye bak; ulasiliyorsa canliya gec.
        // Ag gec oturabilir diye birkac kez tekrar dene.
        piDene(true);
        ana.postDelayed(() -> { if (!piCanli) piDene(true); }, 2500);
        ana.postDelayed(() -> { if (!piCanli) piDene(true); }, 6000);
    }

    private void kurWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        web.addJavascriptInterface(new Kopru(), "FordKopru");
        web.setWebViewClient(new WebViewClient() {
            @Override public void onPageFinished(WebView v, String url) {
                // Gomulu (file://) panelde: TUM /api cagrilarini Bluetooth'a yonlendiren shim.
                if (url != null && url.startsWith("file://")) enjekteEt();
                // MP3 yukle/listele/sil araci: paneldeki MUZIK sekmesine enjekte et.
                // Hem WiFi (canli panel) hem BT (gomulu panel) icin -> her sayfada.
                enjekteMuzik();
            }
        });
        // Panel confirm()/alert()/prompt() kullaniyor ( or. "emin misiniz?" onay kutusu).
        // WebView bunlari kendiliginden gostermez -> komut sessizce iptal olur.
        // Native dialoglarla isleyelim ki onay isteyen komutlar (motor, sistem...) calissin.
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onJsConfirm(WebView v, String url, String mesaj, final JsResult sonuc) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(mesaj)
                        .setPositiveButton("Evet", (d, w) -> sonuc.confirm())
                        .setNegativeButton("Vazgeç", (d, w) -> sonuc.cancel())
                        .setOnCancelListener(d -> sonuc.cancel())
                        .show();
                return true;
            }
            @Override public boolean onJsAlert(WebView v, String url, String mesaj, final JsResult sonuc) {
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(mesaj)
                        .setPositiveButton("Tamam", (d, w) -> sonuc.confirm())
                        .setOnCancelListener(d -> sonuc.confirm())
                        .show();
                return true;
            }
            @Override public boolean onJsPrompt(WebView v, String url, String mesaj,
                                                String varsayilan, final JsPromptResult sonuc) {
                final EditText giris = new EditText(MainActivity.this);
                if (varsayilan != null) giris.setText(varsayilan);
                new AlertDialog.Builder(MainActivity.this)
                        .setMessage(mesaj)
                        .setView(giris)
                        .setPositiveButton("Tamam", (d, w) -> sonuc.confirm(giris.getText().toString()))
                        .setNegativeButton("Vazgeç", (d, w) -> sonuc.cancel())
                        .setOnCancelListener(d -> sonuc.cancel())
                        .show();
                return true;
            }
        });
    }

    /**
     * Gomulu panelde HER '/api/' cagrisini (GET/POST + govde) Bluetooth uzerinden Pi'ye tasir.
     * Boylece BT modunda panelin TAMAMI calisir: komut, durum, muzik, medya, ayarlar...
     * (Muzik SESI Pi'den/arac hoparloru'nden cikar; buradan yalnizca kontrol gider.)
     */
    private void enjekteEt() {
        String js =
            "(function(){if(window.__fordShim)return;window.__fordShim=1;var of=window.fetch;" +
            "window.fetch=function(u,o){try{" +
            "var url=(typeof u==='string')?u:(u&&u.url)||'';" +
            "if(url.indexOf('/api/')>=0){" +
            "var yol=url.substring(url.indexOf('/api/'));" +
            "var m=((o&&o.method)||'GET').toUpperCase();" +
            "var body=(o&&o.body!=null)?String(o.body):'';" +
            "var r=FordKopru.btIstek(m,yol,body);" +
            "var st=200,bd='{}';" +
            "if(r){var p=r.indexOf('\\u0001');if(p>=0){st=parseInt(r.substring(0,p))||200;bd=r.substring(p+1);}else{bd=r;}}" +
            "else{st=503;bd=JSON.stringify({ok:false,hata:'Bluetooth baglanti yok'});}" +
            "return Promise.resolve(new Response(bd,{status:st,headers:{'Content-Type':'application/json'}}));" +
            "}}catch(e){}" +
            "return of.apply(this,arguments);};})();";
        web.evaluateJavascript(js, null);
    }

    /** MP3 yukle/listele/sil aracini (assets/mp3_arac.js) panele enjekte eder. */
    private String mp3AracJs = null;
    private void enjekteMuzik() {
        if (mp3AracJs == null) mp3AracJs = assetOku("mp3_arac.js");
        if (mp3AracJs != null && !mp3AracJs.isEmpty()) web.evaluateJavascript(mp3AracJs, null);
    }

    /** assets/ altindaki bir metin dosyasini okur (yoksa null). */
    private String assetOku(String ad) {
        try (java.io.InputStream is = getAssets().open(ad);
             java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream()) {
            byte[] tmp = new byte[8192]; int n;
            while ((n = is.read(tmp)) > 0) bo.write(tmp, 0, n);
            return new String(bo.toByteArray(), "UTF-8");
        } catch (Exception e) { return null; }
    }

    /** JS'ten cagrilir: paneldeki HER /api istegi bu kopru uzerinden Bluetooth'a gider. */
    private class Kopru {
        // method (GET/POST...), yol (/api/...), govde (istek body; GET'te bos).
        // Doner: "statuskodu\u0001yanitgovdesi" (shim ayristirir), bagli degilse null.
        @JavascriptInterface public String btIstek(String method, String yol, String govde) {
            if (bt == null || !bt.bagliMi() || yol == null) return null;
            if (method == null || method.isEmpty()) method = "GET";
            String c = bt.istek(method, yol, govde);
            if (c == null) ana.post(() -> durumYaz("Bluetooth bagli degil / yanit yok"));
            return c;
        }
    }

    /** Pi'ye HTTP ile ulasilabiliyor mu? Ulasiliyorsa paneli Pi'den canli yukle. */
    private volatile boolean taraniyor = false;

    private void piDene(final boolean sessiz) {
        if (taraniyor) return;
        taraniyor = true;
        new Thread(() -> {
            // 1) Hizli adaylar: ford.local (ev wifi) ve 10.42.0.1 (FORD-AP)
            String base = ilkCevapVeren();
            // 2) Bulamazsa: bulundugun agi tara, paneli yaniti vereni bul
            //    (telefon hotspot gibi degisken IP'lerde de calisir)
            if (base == null) base = agiTara();
            final String b = base;
            ana.post(() -> {
                taraniyor = false;
                if (b != null) {
                    piBase = b;
                    if (!piCanli) {
                        piCanli = true;
                        web.loadUrl(b + "/");   // CANLI panel - her sey calisir
                    }
                    durumYaz("● Bagli");
                } else if (!sessiz) {
                    durumYaz("Araca ulasilamadi");
                }
            });
        }, "pi-tara").start();
    }

    /** Verilen adres panelin /api/durum'unu dondurebiliyor mu? */
    private boolean ulasiliyor(String base, int zaman) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + "/api/durum").openConnection();
            c.setConnectTimeout(zaman);
            c.setReadTimeout(zaman);
            c.setRequestMethod("GET");
            int kod = c.getResponseCode();
            return kod >= 200 && kod < 500;
        } catch (Exception e) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private String ilkCevapVeren() {
        for (String aday : PI_ADAYLAR) {
            if (ulasiliyor(aday, 1500)) return aday;
        }
        return null;
    }

    /** Telefonun bagli oldugu her /24 agini tarar, paneli yaniti vereni bulur. */
    private String agiTara() {
        for (String onek : yerelOnekler()) {
            String bulunan = onekTara(onek);
            if (bulunan != null) return bulunan;
        }
        return null;
    }

    private java.util.List<String> yerelOnekler() {
        java.util.List<String> l = new java.util.ArrayList<>();
        try {
            for (java.net.NetworkInterface ni :
                    java.util.Collections.list(java.net.NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (java.net.InterfaceAddress ia : ni.getInterfaceAddresses()) {
                    java.net.InetAddress a = ia.getAddress();
                    if (a instanceof java.net.Inet4Address) {
                        String ip = a.getHostAddress();
                        int p = ip.lastIndexOf('.');
                        if (p > 0) {
                            String onek = ip.substring(0, p);
                            if (!l.contains(onek)) l.add(onek);
                        }
                    }
                }
            }
        } catch (Exception ignored) {}
        return l;
    }

    private String onekTara(final String onek) {
        final java.util.concurrent.atomic.AtomicReference<String> sonuc =
                new java.util.concurrent.atomic.AtomicReference<>(null);
        java.util.concurrent.ExecutorService havuz =
                java.util.concurrent.Executors.newFixedThreadPool(40);
        final java.util.concurrent.CountDownLatch latch =
                new java.util.concurrent.CountDownLatch(254);
        for (int i = 1; i <= 254; i++) {
            final String ip = onek + "." + i;
            havuz.execute(() -> {
                if (sonuc.get() == null) {
                    String base = "http://" + ip + ":8080";
                    if (ulasiliyor(base, 350)) sonuc.compareAndSet(null, base);
                }
                latch.countDown();
            });
        }
        try { latch.await(8, java.util.concurrent.TimeUnit.SECONDS); } catch (Exception ignored) {}
        havuz.shutdownNow();
        return sonuc.get();
    }

    // ---- WiFi (FORD agi) baglanti ----
    private void wifiBaglan() {
        durumYaz("FORD agina baglaniliyor...");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            WifiNetworkSpecifier spec = new WifiNetworkSpecifier.Builder()
                    .setSsid(FORD_SSID).setWpa2Passphrase(FORD_PASS).build();
            NetworkRequest istek = new NetworkRequest.Builder()
                    .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
                    .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    .setNetworkSpecifier(spec).build();
            if (agGeri != null) { try { cm.unregisterNetworkCallback(agGeri); } catch (Exception ignored) {} }
            agGeri = new ConnectivityManager.NetworkCallback() {
                @Override public void onAvailable(Network network) {
                    cm.bindProcessToNetwork(network);
                    ana.post(() -> { Toast.makeText(MainActivity.this, "FORD'a baglandi", Toast.LENGTH_SHORT).show();
                                     piDene(false); });
                }
                @Override public void onUnavailable() {
                    ana.post(() -> durumYaz("FORD'a baglanilamadi - tekrar dene"));
                }
            };
            cm.requestNetwork(istek, agGeri);
        } else {
            durumYaz("WiFi ayarlarindan FORD agina baglan");
            try { startActivity(new android.content.Intent(
                    android.provider.Settings.ACTION_WIFI_SETTINGS)); } catch (Exception ignored) {}
        }
    }

    // ---- Bluetooth baglanti ----
    private void btBaglan() {
        if (!btIzinVar()) { btIzinIste(); return; }
        // Komutlarin BT'ye gitmesi icin gomulu panele gec (koprü orada aktif).
        if (piCanli) { piCanli = false; web.loadUrl(YEREL_URL); }
        durumYaz("Bluetooth baglaniliyor...");
        bt.baglan();
    }

    @Override public void durum(String mesaj, boolean bagli) { durumYaz((bagli ? "BT: " : "") + mesaj); }
    @Override public void cevap(String satir) { Toast.makeText(this, satir, Toast.LENGTH_SHORT).show(); }

    private void durumYaz(String m) { if (durum != null) durum.setText(m); }

    // ---- izinler ----
    private static final int IZIN_BT = 42;
    private boolean btIzinVar() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED;
    }
    private void btIzinIste() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            requestPermissions(new String[]{Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.BLUETOOTH_SCAN}, IZIN_BT);
    }
    @Override public void onRequestPermissionsResult(int kod, String[] izinler, int[] sonuc) {
        super.onRequestPermissionsResult(kod, izinler, sonuc);
        if (kod == IZIN_BT && sonuc.length > 0 && sonuc[0] == PackageManager.PERMISSION_GRANTED) btBaglan();
        else if (kod == IZIN_BT) durumYaz("Bluetooth izni verilmedi");
    }

    @Override protected void onResume() {
        super.onResume(); tamEkran();
        if (!piCanli) piDene(true);   // ekrana donunce tekrar baglanmayi dene
    }

    private void tamEkran() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    /** Paneldeki acik ekrani (muzik/medya/nav/ayarlar) kapatip ana ekrana dondurur. */
    private void anaEkranaDon() {
        if (web != null) web.evaluateJavascript(
                "(function(){try{if(window.goHome){goHome();return 'ok';}" +
                "var o=document.querySelector('.app-overlay.open');" +
                "if(o){o.classList.remove('open');return 'ok';}}catch(e){}return 'yok';})();", null);
    }

    @Override public void onBackPressed() {
        if (web == null) { super.onBackPressed(); return; }
        // Panelde bir alt ekran acıksa once onu kapat (uygulamadan cikma).
        web.evaluateJavascript(
                "(function(){try{var o=document.querySelector('.app-overlay.open');" +
                "if(o){if(window.goHome){goHome();}else{o.classList.remove('open');}return 'kapandi';}}" +
                "catch(e){}return 'ana';})();",
                deger -> {
                    if (deger != null && deger.contains("ana")) {
                        // Zaten ana ekran: uygulamayi kapatmak yerine arka plana al.
                        moveTaskToBack(true);
                    }
                });
    }

    @Override protected void onDestroy() {
        if (agGeri != null) { try { cm.unregisterNetworkCallback(agGeri); } catch (Exception ignored) {} }
        try { cm.bindProcessToNetwork(null); } catch (Exception ignored) {}
        if (bt != null) bt.kapat();
        super.onDestroy();
    }
}
