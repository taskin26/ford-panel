package com.ford.panel;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
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
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * FORD Panel + Bluetooth Kontrol - TEK UYGULAMA
 *  - Acilinca Pi'deki TAM paneli (ford_ekran.html) WebView'de gosterir (IP yok).
 *  - Panel acilmazsa WiFi "BAGLAN" perdesi.
 *  - "BT" dugmesi: Bluetooth hizli kontrol (WiFi/internet olmadan).
 */
public class MainActivity extends Activity implements BtKontrol.Dinleyici {

    static final String PANEL_URL = "http://10.42.0.1:8080/";
    static final String FORD_SSID = "FORD";
    static final String FORD_PASS = "fordconnect";

    static final String[][] BT_KOMUTLAR = {
            {"Kapıları Aç",     "KAPILARI_AC"},
            {"Kapıları Kilitle","KAPILARI_KILITLE"},
            {"Motoru Çalıştır", "MOTORU_CALISTIR"},
            {"Motoru Durdur",   "MOTORU_DURDUR"},
            {"Bagajı Aç",       "BAGAJI_AC"},
            {"Camları Aç",      "CAMLARI_AC"},
            {"Camları Kapat",   "CAMLARI_KAPAT"},
            {"Işıkları Aç",     "ISIKLARI_AC"},
            {"Işıkları Kapat",  "ISIKLARI_KAPAT"},
            {"Araç Durumu",     "ARAC_DURUMU"},
    };

    private WebView web;
    private View baglanKatman, btKatman;
    private TextView durumYazi, btDurum;
    private ConnectivityManager cm;
    private ConnectivityManager.NetworkCallback agGeri;
    private boolean panelYuklendi = false;
    private BtKontrol bt;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(R.layout.activity_main);

        cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        bt = new BtKontrol(this);

        web = findViewById(R.id.web);
        baglanKatman = findViewById(R.id.baglanKatman);
        btKatman = findViewById(R.id.btKatman);
        durumYazi = findViewById(R.id.durumYazi);
        btDurum = findViewById(R.id.btDurum);

        kurWebView();

        ((Button) findViewById(R.id.baglanBtn)).setOnClickListener(v -> fordaBaglan());
        ((Button) findViewById(R.id.tekrarBtn)).setOnClickListener(v -> {
            baglanKatman.setVisibility(View.GONE); web.loadUrl(PANEL_URL);
        });
        ((Button) findViewById(R.id.btAcKatmanBtn)).setOnClickListener(v -> btKatmanGoster(true));
        ((Button) findViewById(R.id.btFab)).setOnClickListener(v -> btKatmanGoster(true));
        ((Button) findViewById(R.id.btKapatBtn)).setOnClickListener(v -> btKatmanGoster(false));
        ((Button) findViewById(R.id.btBaglanBtn)).setOnClickListener(v -> btBaglan());

        btButonlariOlustur();
        web.loadUrl(PANEL_URL);
    }

    private void kurWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setBuiltInZoomControls(false);
        s.setSupportZoom(false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return false; }
            @Override public void onPageFinished(WebView v, String url) {
                if (url != null && url.startsWith("http")) {
                    panelYuklendi = true; baglanKatman.setVisibility(View.GONE);
                }
            }
            @Override public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    panelYuklendi = false;
                    durumYazi.setText("Panel açılamadı.\nFORD ağına bağlı değilsin.");
                    baglanKatman.setVisibility(View.VISIBLE);
                }
            }
        });
    }

    private void fordaBaglan() {
        durumYazi.setText("FORD ağına bağlanılıyor...");
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
                    new Handler(Looper.getMainLooper()).post(() -> {
                        Toast.makeText(MainActivity.this, "FORD'a bağlandı", Toast.LENGTH_SHORT).show();
                        baglanKatman.setVisibility(View.GONE); web.loadUrl(PANEL_URL);
                    });
                }
                @Override public void onUnavailable() {
                    new Handler(Looper.getMainLooper()).post(() ->
                            durumYazi.setText("FORD'a bağlanılamadı.\nAraç yakınında mısın? Tekrar dene."));
                }
            };
            cm.requestNetwork(istek, agGeri);
        } else {
            durumYazi.setText("WiFi ayarlarından FORD ağına bağlan,\nsonra 'Tekrar Dene'ye bas.");
            try { startActivity(new android.content.Intent(
                    android.provider.Settings.ACTION_WIFI_SETTINGS)); } catch (Exception ignored) {}
        }
    }

    private void btKatmanGoster(boolean ac) { btKatman.setVisibility(ac ? View.VISIBLE : View.GONE); }

    private void btButonlariOlustur() {
        LinearLayout kap = findViewById(R.id.btButonlar);
        float d = getResources().getDisplayMetrics().density;
        int pad = (int) (12 * d);
        for (final String[] kv : BT_KOMUTLAR) {
            Button b = new Button(this);
            b.setText(kv[0]); b.setTextColor(Color.WHITE); b.setTextSize(18);
            b.setAllCaps(false); b.setBackgroundColor(renkSec(kv[1]));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, (int) (60 * d));
            lp.setMargins(0, pad / 2, 0, pad / 2);
            b.setLayoutParams(lp);
            b.setOnClickListener(v -> btGonder(kv[0], kv[1]));
            kap.addView(b);
        }
    }

    private int renkSec(String komut) {
        if (komut.equals("MOTORU_DURDUR") || komut.equals("KAPILARI_KILITLE"))
            return Color.parseColor("#c62828");
        if (komut.equals("MOTORU_CALISTIR") || komut.equals("KAPILARI_AC"))
            return Color.parseColor("#2e7d32");
        return Color.parseColor("#37474f");
    }

    private void btBaglan() {
        if (!btIzinVar()) { btIzinIste(); return; }
        btDurum.setText("Bağlanıyor..."); bt.baglan();
    }

    private void btGonder(String etiket, String komut) {
        if (!btIzinVar()) { btIzinIste(); return; }
        if (!bt.bagliMi()) { btDurum.setText("Önce 'Bluetooth'a Bağlan'a bas."); return; }
        bt.gonder(komut);
        Toast.makeText(this, etiket, Toast.LENGTH_SHORT).show();
    }

    @Override public void durum(String mesaj, boolean bagli) {
        btDurum.setText((bagli ? "● " : "○ ") + mesaj);
    }
    @Override public void cevap(String satir) {
        Toast.makeText(this, satir, Toast.LENGTH_SHORT).show();
    }

    private static final int IZIN_BT = 42;
    private boolean btIzinVar() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        return checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)
                == PackageManager.PERMISSION_GRANTED;
    }
    private void btIzinIste() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            requestPermissions(new String[]{
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.BLUETOOTH_SCAN}, IZIN_BT);
        }
    }
    @Override public void onRequestPermissionsResult(int kod, String[] izinler, int[] sonuc) {
        super.onRequestPermissionsResult(kod, izinler, sonuc);
        if (kod == IZIN_BT && sonuc.length > 0 && sonuc[0] == PackageManager.PERMISSION_GRANTED) btBaglan();
        else if (kod == IZIN_BT) btDurum.setText("Bluetooth izni verilmedi.");
    }

    @Override protected void onResume() {
        super.onResume(); tamEkran();
        if (!panelYuklendi) web.loadUrl(PANEL_URL);
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

    @Override public void onBackPressed() {
        if (btKatman.getVisibility() == View.VISIBLE) { btKatmanGoster(false); return; }
        if (web != null && web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (agGeri != null) { try { cm.unregisterNetworkCallback(agGeri); } catch (Exception ignored) {} }
        try { cm.bindProcessToNetwork(null); } catch (Exception ignored) {}
        if (bt != null) bt.kapat();
        super.onDestroy();
    }
}
