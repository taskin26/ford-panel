package com.ford.panel;

import android.Manifest;
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
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebSettings;
import android.widget.Button;
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

    static final String PI_BASE   = "http://10.42.0.1:8080";
    static final String YEREL_URL = "file:///android_asset/ford_ekran.html";
    static final String FORD_SSID = "FORD";
    static final String FORD_PASS = "fordconnect";

    private WebView web;
    private TextView durum;
    private Button wifiBtn, btBtn;
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

        kurWebView();
        wifiBtn.setOnClickListener(v -> wifiBaglan());
        btBtn.setOnClickListener(v -> btBaglan());

        // Panel HEMEN (gomulu) acilir -> her zaman gorunur.
        web.loadUrl(YEREL_URL);
        durumYaz("Panel yuklendi - baglanti araniyor...");
        // Arka planda Pi'ye ulasiliyor mu diye bak; ulasiliyorsa canliya gec.
        piDene(true);
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
                // Gomulu (file://) panelde: komutlari Bluetooth'a yonlendiren koprüyü enjekte et.
                if (url != null && url.startsWith("file://")) enjekteEt();
            }
        });
    }

    /** Gomulu panelde fetch('/api/komut') -> Bluetooth. Diger /api cagrilari sessizce bos doner. */
    private void enjekteEt() {
        String js =
            "(function(){if(window.__fordShim)return;window.__fordShim=1;var of=window.fetch;" +
            "window.fetch=function(u,o){try{var url=(typeof u==='string')?u:(u&&u.url)||'';" +
            "if(url.indexOf('/api/komut')>=0){var body=(o&&o.body)||'{}';var k='';" +
            "try{k=JSON.parse(body).komut||'';}catch(e){}" +
            "var ok=FordKopru.btKomut(k)==='1';" +
            "return Promise.resolve(new Response(JSON.stringify({ok:ok,hata:ok?'':'baglanti yok'})," +
            "{status:200,headers:{'Content-Type':'application/json'}}));}" +
            "if(url.indexOf('/api/')>=0){return Promise.resolve(new Response('{}'," +
            "{status:200,headers:{'Content-Type':'application/json'}}));}}catch(e){}" +
            "return of.apply(this,arguments);};})();";
        web.evaluateJavascript(js, null);
    }

    /** JS'ten cagrilir: paneldeki butonlar bu kopru uzerinden Bluetooth'a komut yollar. */
    private class Kopru {
        @JavascriptInterface public String btKomut(String komut) {
            if (komut == null || komut.trim().isEmpty()) return "0";
            if (bt != null && bt.bagliMi()) { bt.gonder(komut.trim()); return "1"; }
            ana.post(() -> durumYaz("Bluetooth bagli degil - 'Bluetooth ile Baglan'a bas"));
            return "0";
        }
    }

    /** Pi'ye HTTP ile ulasilabiliyor mu? Ulasiliyorsa paneli Pi'den canli yukle. */
    private void piDene(final boolean sessiz) {
        exec.execute(() -> {
            boolean ok = false;
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(PI_BASE + "/").openConnection();
                c.setConnectTimeout(2000);
                c.setReadTimeout(2000);
                c.setRequestMethod("GET");
                int kod = c.getResponseCode();
                c.disconnect();
                ok = (kod > 0);
            } catch (Exception ignored) {}
            final boolean ulasildi = ok;
            ana.post(() -> {
                if (ulasildi) {
                    if (!piCanli) {
                        piCanli = true;
                        web.loadUrl(PI_BASE + "/");   // CANLI panel - her sey calisir
                    }
                    durumYaz("WiFi bagli - canli panel");
                } else if (!sessiz) {
                    durumYaz("Pi'ye ulasilamadi - araca yakin misin?");
                }
            });
        });
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

    @Override protected void onResume() { super.onResume(); tamEkran(); }

    private void tamEkran() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (agGeri != null) { try { cm.unregisterNetworkCallback(agGeri); } catch (Exception ignored) {} }
        try { cm.bindProcessToNetwork(null); } catch (Exception ignored) {}
        if (bt != null) bt.kapat();
        super.onDestroy();
    }
}
