/*
  FORD - ESP32 ARAC KONTROL  (16 kanal)
  ======================================

  Faz3 (Pi/laptop) KARAR VERIR, ESP32 IS YAPAR.

  NEDEN AYRI ISLEMCI:
    Pi genel amacli bir bilgisayar - cokebilir, guncelleme yapar,
    yavaslar. Roleyi dogrudan ona surdurmek riskli.
    ESP32 tek is yapar ve hic durmaz.

  ---------------------------------------------------------------
  PIN HARITASI  (11 role kanali)
  ---------------------------------------------------------------
    D4   KAPI_AC            D19  MARS  (kumanda calistir butonu)
    D5   KAPI_KILIT         D21  ANAHTAR_GUC  (KALICI - 3 V pil yuvasi)
    D13  SURUCU_CAM_AC      D22  ISIK_AC
    D14  SURUCU_CAM_KAPAT   D23  ISIK_KAPAT
    D25  YOLCU_CAM_AC       D18  BAGAJ_AC
    D26  YOLCU_CAM_KAPAT    D2   dahili LED (kalp atisi)

  ---------------------------------------------------------------
  PIN REZERVASYONU  (ikinci asama - henuz kodda YOK)
  ---------------------------------------------------------------
  Arka cam kanallari iptal edildi, o pinler bu isler icin ayrildi.
  Montajda bu pinlere ROLE BAGLANMAYACAK.

    D27  KART E  yolcu kapisi      D16  DS18B20 veri (4.7k pull-up)
    D32  KART E  sag kayar kapi    D17  DFPlayer RX (1k direnc seri)
    D33  KART E  sol kayar kapi    D34  Aku voltaji (30k/7.5k bolucu)
    D15  BOS - kullanilmayacak     D35  KART D  surucu kapisi
         (strapping pini)          D36  KART D  kaput
                                   D39  KART D  bagaj kapagi

    12 Ekim 2026: RC522 bu pinlerden alindi, Raspberry Pi'nin kendi
    SPI'ina tasiniyor. Acilan uc pin alti musurun eksik kalan ucune
    verildi. KART E ayri bir karttir, KART D'ye dokunulmadi.

  ROLE KARTININ IN12..IN16'SI:
    ESP32'de cikis verebilen pin kalmadi. Hoparlor secimi gibi
    ARAC KONTROLU OLMAYAN isler icin Pi 4'un GPIO'sunu kullan -
    40 pini bos duruyor, lojigi de 3.3V, role kartina uyar.
    Arac kontrolu (kapi/cam/mars) HER ZAMAN ESP32'de kalir.

  KULLANILMAYAN PINLER VE NEDENI:
    GPIO 6-11   dahili flash bellek - kullanirsan kart acilmaz
    GPIO 0      BOOT tusu - acilista LOW olursa program moduna girer
    GPIO 12     ACILISTA HIGH OLURSA KART ACILMAZ.
                Low level kartta pasif seviye HIGH oldugu icin bu pine
                ROLE BAGLANAMAZ. Bos kalacak, baska amac icin de kullanma.
    GPIO 34-39  SADECE GIRIS, cikis veremez
    RX0/TX0     USB seri port (Pi koprusu) - kullanirsan kod yukleyemezsin

  ---------------------------------------------------------------
  GUVENLIK
  ---------------------------------------------------------------
    1. Acilista TUM CIKISLAR KAPALI. Once LOW, sonra OUTPUT.
       Ters sirada yapilirsa roleler bir kere "tik" eder.

    2. WATCHDOG: Pi'den 10 saniye haber gelmezse hepsini kapatir.
       Pi cokerse veya kablo cikarsa arac acik kalmasin.

    3. KILITLI CIFTLER: ayni camin ac ve kapat rolesi ayni anda
       cekilemez. Motoru yakar.

    4. AYNI ANDA EN FAZLA 4 ROLE. Hepsi birden cekilirse akim
       cok yuksek olur, besleme coker.

    5. MARS icin EL FRENI sarti - su an KAPALI (asagida ayar).

  ---------------------------------------------------------------
  PROTOKOL
  ---------------------------------------------------------------
    Pi  -> ESP32   KOMUT
    ESP32 -> Pi    OK|KOMUT   veya   RET|KOMUT|sebep

    Test komutlari:
      PING          baglanti testi
      DURUM         tum cikislarin hali
      GIRIS         musur girisleri + aku voltaji + sicakliklar
      ISI           ic / dis sicaklik
      ISI_TARA      isi sensorlerini yeniden ara, adresleri yaz
      ISI_IC        takili olan IC sensordur diye KAYDET (kalici)
      ISI_DEGISTIR  ic ile dis yer degistirsin (kalici)
      LISTE         tanimli komutlari say
      AC <pin>      pini surekli ac      (ornek: AC 19)
      KAPAT <pin>   pini kapat
      HEPSINI_KAPAT acil kapatma
*/

// ==================== AYARLAR ====================

// ROLE KARTI TETIKLEME YONU  --  EN KRITIK AYAR
//   true  : LOW LEVEL TRIGGER  (kartin uzerinde boyle yaziyorsa)
//           Role cikisa LOW verilince CEKER, HIGH verilince BIRAKIR.
//           >>> SENIN 16 KANAL KARTIN BU. <<<
//   false : HIGH LEVEL TRIGGER  (ve breadboard LED testi)
//           LED pin -> direnc -> GND baglandiginda HIGH ile yanar.
//
// YANLIS AYARLARSAN: ESP32 acilir acilmaz TUM ROLELER CEKER.
// Araca bagliyken bu; kapilarin acilmasi, camlarin inmesi,
// marsin basmasi demektir. Bagalantidan ONCE kontrol et.
const bool LOW_LEVEL_ROLE = true;

#define ROLE_AKTIF  (LOW_LEVEL_ROLE ? LOW  : HIGH)   // role CEKILI
#define ROLE_PASIF  (LOW_LEVEL_ROLE ? HIGH : LOW)    // role BIRAKILMIS

const unsigned long WATCHDOG_MS   = 10000;  // Pi susarsa kapat
const unsigned long DARBE_MS      = 500;    // normal role darbesi
const unsigned long CAM_DARBE_MS  = 3000;   // cam motoru daha uzun
// Kumandanin "uzaktan calistir" butonu KISA BASISLA calismiyor.
// Basili tuttukca SIRAYLA ilerliyor:
//    once kontak acilir (gosterge yanar) -> sonra mars basar
// Kullanicinin olcumu: 5-6 saniye. Uzerine pay koyup 7 saniye.
//
// ERKEN BIRAKMAK TEHLIKELI: kontak acik kalir, motor calismaz,
// gosterge yanik durur ve aku yavasca biter. O yuzden cimri olma.
//
// Motor calistiktan sonra butonun basili kalmasi sorun cikarirsa
// (motor calisip hemen duruyorsa) bu sayiyi dusur.
// 24 Ekim 2026: 7000 -> 5000. Araçta dogrulanan pencere 4-6 sn (bkz.
// MOTOR_DURDUR notu). 7 sn o pencerenin 1 sn disindaydi; modül basisi
// bazen yanlis okuyordu - ozellikle DURDURMADA (3-4 deneme). 5000 =
// dogrulanan 4-6 sn araliginin tam ortasi. Durdurma hala kacarsa
// 4500-5500 arasi oyna; asla 4000 altina / 6000 ustune cikma.
const unsigned long MARS_DARBE_MS = 5000;   // kumandanin calistir butonu
const unsigned long KALP_MS       = 1000;
const int MAKS_AYNI_ANDA          = 4;      // ayni anda en fazla kac role

// ==================== KALICI KANAL ====================
// sure = KALICI olan kanal darbe DEGILDIR. Acilinca acik kalir,
// ancak "KAPAT <ad>" komutuyla birakilir.
//
// Su an tek kullanicisi: ANAHTAR_GUC
//   Aracin anahtarsiz sistemi var. Yedek kumandanin pili cikarildi,
//   pil yuvasina bu role uzerinden 3 V veriliyor.
//     enerji VAR  -> arac anahtari goruyor -> kapilar acilir
//     enerji YOK  -> arac anahtar yok saniyor -> kapilar kilitlenir
//   Yani kapiyi acan sey darbe degil, kumandanin VARLIGI.
//
// Ayrintili tasarim: ANAHTAR_TASARIM.md
const unsigned long KALICI = 0;

// EL FRENI KILIDI - KAPALI (karar verildi, 2 Ekim 2026)
//   false : mars icin sart yok. "Motoru calistir" komutu fren konumuna
//           BAKMADAN marsi verir.  <-- su anki durum
//   true  : el freni cekili degilse mars VERILMEZ
//
// Araca el freni musuru TAKILI DEGIL ve takilmayacak. Kod duruyor ama
// kapali. Ileride musur takmak istersen:
//   1) musuru BOS bir pine bagla - asagidaki D35'e DEGIL, orada kapi
//      musurunun PC817'si var
//   2) GPIO 34-39'dan secersen disaridan 10k pull-up sart (dahili yok).
//      Daha kolayi: pull-up'i olan bir pin sec (orn. D27, D32, D33)
//   3) PIN_EL_FRENI'yi o pine cevir
//   4) burayi ve ford_faz3.py icindeki EL_FRENI_KONTROLU'nu True yap
// Ikisi birden True olmadan kilit calismaz.
const bool EL_FRENI_KONTROLU = false;
#define PIN_EL_FRENI  35   // KULLANILMIYOR (EL_FRENI_KONTROLU false)

// ==================== KART D GIRISLERI ====================
//  PC817'ler TERS calisir:  araçta 12 V VAR  ->  ESP32 pini LOW
//  Pull-up dirençleri KART D üzerinde (10 k, 3V3'e).
//  GPIO 34-39'un dahili pull-up'u YOKTUR, harici şart.
//
//  D35 ARTIK SADECE KAPI MÜŞÜRÜNÜN. El freni kilidi kapatıldığı için
//  çakışma yok. El freni müşürü takılırsa D35'e DEĞİL, başka bir pine.
#define PIN_AKU      34        // akü voltajı (30k + 7.5k bölücü)
#define PIN_SURUCU   35        // KART D · PC817 #1  sürücü kapısı (35 + harici 10k pull-up -> 3V3)
#define PIN_KAPUT    36        // KART D · PC817 #2  kaput
#define PIN_BAGAJ    39        // KART D · PC817 #3  bagaj kapağı

// ---- KART E  (12 Ekim 2026) ----------------------------------------
//  Taşkın'ın aracı (2010 Connect GLX full) hangi kapının açık olduğunu
//  kendi ekranında AYRI AYRI yazıyor. Demek ki altı müşür sinyali de
//  araçta ayrı ayrı mevcut. KART D kutulanmış durumdaydı ve sökülürse
//  lehimler kopuyor - bu yüzden üç yeni kanal KART D'ye eklenmedi,
//  ayrı bir KART E yapıldı. Kart D'ye hiç dokunulmadı.
//
//  Bu üç pin RC522'ye ayrılmıştı; RC522 Raspberry Pi'nin SPI'ına
//  taşınıyor. D15 BİLEREK boş bırakıldı - açılışta okunan strapping
//  pinlerden biri, kapı açıkken güç verilirse açılışı etkileyebilir.
//
//  34-39'un aksine bu pinlerde DAHİLİ pull-up var. Kart E'de harici
//  10k da var; ikisi birden sorun değil, tersine kablo koparsa pin
//  yukarıda kalır ve "kapalı" okunur - güvenli taraf.
#define PIN_YOLCU      27      // KART E · PC817 #4  yolcu kapısı
#define PIN_SAG_SURGU  32      // KART E · PC817 #5  sağ kayar kapı
#define PIN_SOL_SURGU  33      // KART E · PC817 #6  sol kayar kapı
// AKU_CARPAN teorik olarak 5.0 (30k+7.5k = 37.5k, 7.5/37.5 = 1/5) ama
// ESP32'nin ADC'si ust uclarda dusuk okur. 10 Ekim 2026'da masada
// olculdu: gercek 11.89 V iken yazilim 11.00 gosterdi. 11.89/11.00 =
// 1.081  ->  5.0 * 1.081 = 5.40. Arac akusune baglandiktan sonra
// 12.5-14.5 V araliginda bir kez daha dogrulanacak.
// 11 Ekim 2026: AKU_CARPAN artik SABIT DEGIL. Araçta multimetreyle
// olculen degeri panele yazinca ESP32 carpani kendi hesapliyor ve
// kalici hafizaya yaziyor. Asagidaki deger VARSAYILAN - hic
// kalibrasyon yapilmadiysa bu gecerli.
#define AKU_CARPAN_VARSAYILAN  5.40f
#define ADC_REF      3.30f

#define PIN_KALP       2   // dahili mavi LED

// ==================== RC522 RFID ====================
//
// Kart okuyucu camin ic yuzune yapistirilacak, kart disaridan cama
// degdirilecek. 13,56 MHz camı geçer, metali geçmez.
//
//   D27 -> SCK      D33 -> MOSI     RST -> 3V3 (sabit)
//   D32 -> MISO     D15 -> SS       VCC -> 3V3   *** 5 V YAKAR ***
//
// Kutuphane KULLANILMIYOR. Arduino IDE'de kutuphane kurma derdi
// olmasin diye okuyucu burada dogrudan suruluyor. Sadece UID
// okunuyor - sektor/sifre islerine girmiyoruz, gerek yok.
//
// Modul TAKILI DEGILSE sistem normal calisir. Acilista modul
// aranir, yoksa RFID sessizce devre disi kalir.
// *** 13 Ekim 2026 — RC522 ARTIK ESP32'DE DEGIL, RASPBERRY PI'DE ***
//
// Bu uc pin (27, 32, 33) simdi KART E'nin kapi girisleri:
//   D27 = yolcu kapisi    D32 = sag kayar    D33 = sol kayar
//
// Asagidaki RC522 surucusu bu pinleri SPI'ye aliyordu:
//   SCK (27) ve MOSI (33) OUTPUT olup LOW suruluyordu  -> kapi
//   hep "acik" okunuyordu. MISO (32) INPUT kaldigi icin o kanal
//   dogru calisiyordu. Yolcu + sol kayar takili kalmasinin sebebi
//   buydu; kartta hicbir lehim hatasi yoktu.
//
// Surucu kodu silinmedi (karavan projesinde lazim olabilir) ama
// bu anahtar 0 iken HICBIR yeri bu pinlere dokunmaz.
#define RFID_ESP32  0          // 0 = RC522 Pi'de, ESP32 pinlere dokunmaz

#define RFID_SCK   27
#define RFID_MISO  32
#define RFID_MOSI  33
#define RFID_SS    15
#define RFID_ARALIK_MS 150     // kac ms'de bir kart aranir


// ==================== RC522 SURUCUSU ====================
//
// MFRC522 yongasinin SPI ile surulmesi. Sadece UID okuma.
// Akis:  REQA/WUPA yolla -> kart cevap verirse ANTICOLL ile UID al.
// 4 baytlik UID'ler dogrudan gelir; 7 baytliklarda ilk bayt 0x88
// (cascade isareti) olur ve ikinci tur gerekir - o da destekleniyor.

#include <SPI.h>
#include <Preferences.h>    // ESP32 cekirdeginde var, kurulum gerekmez

void cevap(String s);             // asagida tanimli - RFID once kullaniyor

static SPIClass rfidSpi(VSPI);
bool  rfidVar = false;            // modul bulundu mu
String sonKart = "";              // okunan UID, Pi alana kadar durur
String sonKartHam = "";           // tekrari engellemek icin
unsigned long sonKartZaman = 0;
unsigned long sonKartArama = 0;

// --- MFRC522 yazmac adresleri ---
#define RC_CommandReg      0x01
#define RC_ComIrqReg       0x04
#define RC_ErrorReg        0x06
#define RC_FIFODataReg     0x09
#define RC_FIFOLevelReg    0x0A
#define RC_ControlReg      0x0C
#define RC_BitFramingReg   0x0D
#define RC_ModeReg         0x11
#define RC_TxControlReg    0x14
#define RC_TxASKReg        0x15
#define RC_TModeReg        0x2A
#define RC_TPrescalerReg   0x2B
#define RC_TReloadRegH     0x2C
#define RC_TReloadRegL     0x2D
#define RC_VersionReg      0x37

#define RC_CMD_IDLE        0x00
#define RC_CMD_TRANSCEIVE  0x0C
#define RC_CMD_SOFTRESET   0x0F

#define PICC_WUPA          0x52   // uyuyan karti da uyandirir
#define PICC_ANTICOLL_CL1  0x93
#define PICC_ANTICOLL_CL2  0x95

static void rcYaz(byte reg, byte deger) {
  rfidSpi.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(RFID_SS, LOW);
  rfidSpi.transfer((reg << 1) & 0x7E);
  rfidSpi.transfer(deger);
  digitalWrite(RFID_SS, HIGH);
  rfidSpi.endTransaction();
}

static byte rcOku(byte reg) {
  rfidSpi.beginTransaction(SPISettings(1000000, MSBFIRST, SPI_MODE0));
  digitalWrite(RFID_SS, LOW);
  rfidSpi.transfer(((reg << 1) & 0x7E) | 0x80);
  byte d = rfidSpi.transfer(0x00);
  digitalWrite(RFID_SS, HIGH);
  rfidSpi.endTransaction();
  return d;
}

static void rcBitAc(byte reg, byte maske)  { rcYaz(reg, rcOku(reg) |  maske); }
static void rcBitKapa(byte reg, byte maske){ rcYaz(reg, rcOku(reg) & (~maske)); }

// Karta veri yollar, cevabi alir. Basarili ise true.
static bool rcGonderAl(byte *gonder, byte gonderN,
                       byte *al, byte *alN, byte bitCercevesi) {
  rcYaz(RC_CommandReg, RC_CMD_IDLE);
  rcYaz(RC_ComIrqReg, 0x7F);             // tum kesme bayraklarini temizle
  rcBitAc(RC_FIFOLevelReg, 0x80);        // FIFO'yu bosalt
  for (byte i = 0; i < gonderN; i++) rcYaz(RC_FIFODataReg, gonder[i]);
  rcYaz(RC_BitFramingReg, bitCercevesi);
  rcYaz(RC_CommandReg, RC_CMD_TRANSCEIVE);
  rcBitAc(RC_BitFramingReg, 0x80);       // gonderimi baslat

  // Cevap bekle - en fazla ~36 ms
  unsigned long bitis = millis() + 40;
  byte n = 0;
  while (millis() < bitis) {
    n = rcOku(RC_ComIrqReg);
    if (n & 0x30) break;                 // RxIRq veya IdleIRq
    if (n & 0x01) return false;          // zamanasimi (kart yok)
  }
  rcBitKapa(RC_BitFramingReg, 0x80);
  if (!(n & 0x30)) return false;
  if (rcOku(RC_ErrorReg) & 0x13) return false;   // Buffer/Parity/Protocol

  byte adet = rcOku(RC_FIFOLevelReg);
  if (adet == 0 || adet > *alN) return false;
  for (byte i = 0; i < adet; i++) al[i] = rcOku(RC_FIFODataReg);
  *alN = adet;
  return true;
}

// UID okur. Basarili ise metin olarak doner ("04a1b2c3"), yoksa "".
static String rcUidOku() {
  byte cevap[8];
  byte n;

  // 1) Kart orada mi?  WUPA (7 bit)
  byte wupa = PICC_WUPA;
  n = sizeof(cevap);
  if (!rcGonderAl(&wupa, 1, cevap, &n, 0x07)) return "";

  String uid = "";
  byte seviye[2] = {PICC_ANTICOLL_CL1, PICC_ANTICOLL_CL2};
  for (byte s = 0; s < 2; s++) {
    byte komut[2] = {seviye[s], 0x20};
    n = sizeof(cevap);
    if (!rcGonderAl(komut, 2, cevap, &n, 0x00)) return "";
    if (n < 5) return "";

    byte bas = 0, adet = 4;
    bool devam = false;
    if (cevap[0] == 0x88) {        // cascade isareti - UID 7 bayt
      bas = 1; adet = 3; devam = true;
    }
    for (byte i = bas; i < bas + adet; i++) {
      if (cevap[i] < 0x10) uid += "0";
      uid += String(cevap[i], HEX);
    }
    if (!devam) break;
  }
  uid.toLowerCase();
  return uid;
}

// ---- TESHIS: donanim SPI'yi HIC kullanmadan, elle bit surerek oku ----
// Donanim SPI ayari mi bozuk, kablo mu kopuk, modul mu olu - ayirmak icin.
// Yavas ama guvenilir: her biti elle surup elle okuyoruz.
static byte rcOkuElle(byte reg) {
  pinMode(RFID_SCK,  OUTPUT);
  pinMode(RFID_MOSI, OUTPUT);
  pinMode(RFID_MISO, INPUT);
  pinMode(RFID_SS,   OUTPUT);
  digitalWrite(RFID_SCK, LOW);
  digitalWrite(RFID_SS,  HIGH);
  delayMicroseconds(20);
  digitalWrite(RFID_SS,  LOW);
  delayMicroseconds(20);

  byte adres = ((reg << 1) & 0x7E) | 0x80;      // okuma biti
  for (int i = 7; i >= 0; i--) {                 // adresi yolla
    digitalWrite(RFID_MOSI, (adres >> i) & 1);
    delayMicroseconds(10);
    digitalWrite(RFID_SCK, HIGH);
    delayMicroseconds(10);
    digitalWrite(RFID_SCK, LOW);
    delayMicroseconds(10);
  }
  byte d = 0;
  for (int i = 7; i >= 0; i--) {                 // cevabi al
    digitalWrite(RFID_MOSI, LOW);
    delayMicroseconds(10);
    digitalWrite(RFID_SCK, HIGH);
    delayMicroseconds(10);
    if (digitalRead(RFID_MISO)) d |= (1 << i);
    digitalWrite(RFID_SCK, LOW);
    delayMicroseconds(10);
  }
  digitalWrite(RFID_SS, HIGH);
  return d;
}

// ---- DONGU TESTI ----
// Modulun MOSI ve MISO bacaklari bir jumperla birlestirilir.
// ESP32 MOSI'den bir deger surer, MISO'dan okur. Ayni deger
// geri geliyorsa: ESP32 pinleri SAGLAM ve iki kablo da SAGLAM.
// Gelmiyorsa sorun kabloda ya da ESP32 pininde - modulde degil.
// Modulu denklemden tamamen cikarir.
static byte rcDongu(byte deger) {
  pinMode(RFID_MOSI, OUTPUT);
  pinMode(RFID_MISO, INPUT);
  byte okunan = 0;
  for (int i = 7; i >= 0; i--) {
    digitalWrite(RFID_MOSI, (deger >> i) & 1);
    delayMicroseconds(200);                 // hat otursun
    if (digitalRead(RFID_MISO)) okunan |= (1 << i);
  }
  return okunan;
}

// Bir cikis pinini test eder: HIGH yaz-oku, LOW yaz-oku.
// Pin toprak veya beslemeye kacmissa yakalanir.
static bool pinSaglamMi(int pin) {
  pinMode(pin, OUTPUT);
  digitalWrite(pin, HIGH);
  delayMicroseconds(50);
  bool y = digitalRead(pin);
  digitalWrite(pin, LOW);
  delayMicroseconds(50);
  bool a = digitalRead(pin);
  return y && !a;
}

// Modulu kurar. Bulamazsa false doner - sistem RFID'siz devam eder.
static bool rfidBaslat() {
  pinMode(RFID_SS, OUTPUT);
  digitalWrite(RFID_SS, HIGH);
  rfidSpi.begin(RFID_SCK, RFID_MISO, RFID_MOSI, RFID_SS);

  rcYaz(RC_CommandReg, RC_CMD_SOFTRESET);
  delay(60);

  // 30 Ekim 2026 - CIZIRTI DUZELTMESI.
  // RC522 artik Pi'de (RFID_ESP32=0). Eskiden bu bayrak KONTROL EDILMIYORDU:
  // ESP yine de anteni aciyor (asagida 0x03) ve loop() 150 ms'de bir
  // yokluyordu. RC522'nin 13.56 MHz anteni surekli yayin yapinca yan
  // taraftaki analog mikrofona SABIT CIZIRTI biniyordu. Cozum: bayrak 0
  // iken anteni ACMADAN cik. Soft reset zaten anteni kapatir; ek olarak
  // TxControl surucu bitlerini sifirla. Boylece rfidVar=false kalir,
  // rfidKontrol() hic calismaz, anten yayin yapmaz, cizirti gider.
  if (!RFID_ESP32) {
    rcYaz(RC_TxControlReg, 0x00);   // anten surucu bitleri KAPALI (yayin yok)
    return false;
  }

  byte s = rcOku(RC_VersionReg);
  // 0x00 ve 0xFF = modul yok / kablo kopuk. Gercek yongalar 0x88-0x92.
  if (s == 0x00 || s == 0xFF) return false;

  rcYaz(RC_TModeReg, 0x8D);
  rcYaz(RC_TPrescalerReg, 0x3E);
  rcYaz(RC_TReloadRegL, 30);
  rcYaz(RC_TReloadRegH, 0);
  rcYaz(RC_TxASKReg, 0x40);        // %100 ASK
  rcYaz(RC_ModeReg, 0x3D);         // CRC baslangic degeri 0x6363
  rcBitAc(RC_TxControlReg, 0x03);  // anteni ac
  return true;
}

// Dongude cagrilir. Kart okunursa sonKart'a yazar.
static void rfidKontrol() {
  if (!rfidVar) return;
  if (millis() - sonKartArama < RFID_ARALIK_MS) return;
  sonKartArama = millis();

  String uid = rcUidOku();
  if (uid.length() < 8) return;

  // Ayni kart cama dayali duruyorsa saniyede bir defa bildir
  if (uid == sonKartHam && millis() - sonKartZaman < 3000) return;
  sonKartHam = uid;
  sonKartZaman = millis();
  sonKart = uid;                   // Pi GIRIS ile alacak
  cevap("KART|" + uid);            // anlik bildirim
}


// ==================== KOMUT TABLOSU ====================
// Tek yerden yonetiliyor. Yeni komut eklemek icin buraya
// bir satir yazman yeterli - gerisi otomatik.
struct Kanal {
  const char* ad;        // Pi'den gelecek komut
  int pin;               // hangi GPIO
  unsigned long sure;    // darbe kac ms
  int kilit;             // hangi kanalla ayni anda cekilemez (-1 yok)
};

// ARKA CAM KANALLARI KALDIRILDI (11 kanal kaldi).
// Ford Connect 2010'da arka camlar SABIT. O dort pin (D27/D32/D33/D15)
// RC522 RFID okuyucuya ayrildi - asagidaki PIN REZERVASYONU bolumune bak.
Kanal kanallar[] = {
  // ad                 pin  sure            kilit
  {"KAPI_AC",            4,  DARBE_MS,        1},   // 0
  {"KAPI_KILIT",         5,  DARBE_MS,        0},   // 1
  {"SURUCU_CAM_AC",     13,  CAM_DARBE_MS,    3},   // 2
  {"SURUCU_CAM_KAPAT",  14,  CAM_DARBE_MS,    2},   // 3
  {"YOLCU_CAM_AC",      25,  CAM_DARBE_MS,    5},   // 4
  {"YOLCU_CAM_KAPAT",   26,  CAM_DARBE_MS,    4},   // 5
  {"BAGAJ_AC",          18,  DARBE_MS,       -1},   // 6
  {"MARS",              19,  MARS_DARBE_MS,  -1},   // 7
  {"ANAHTAR_GUC",       21,  KALICI,         -1},   // 8  <- KALICI
  {"ISIK_AC",           22,  DARBE_MS,        10},  // 9
  {"ISIK_KAPAT",        23,  DARBE_MS,        9},   // 10
};
const int KANAL_SAYISI = sizeof(kanallar) / sizeof(kanallar[0]);

// Her kanalin anlik durumu
unsigned long bitisZamani[16];
bool kanalAktif[16];


// ==================== DURUM ====================
unsigned long sonHaber = 0;
unsigned long kalpZaman = 0;
bool kalpDurum = false;
bool watchdogAktif = false;
String tampon = "";
int kaliciPin = -1;          // AC <pin> ile surekli acilan


// ==================== YARDIMCILAR ====================
// Ileri bildirimler (Arduino kendisi uretir ama acikca yazmak daha saglam)
float akuVolt();
bool  motorDurmus();
bool  anahtarKesilebilir();

void cevap(String s) {
  Serial.println(s);
}

int kanalBul(String ad) {
  for (int i = 0; i < KANAL_SAYISI; i++) {
    if (ad == kanallar[i].ad) return i;
  }
  return -1;
}

// Toplam aktif kanal (kalicilar dahil) - sadece raporlama icin.
int aktifSayisiTum() {
  int n = 0;
  for (int i = 0; i < KANAL_SAYISI; i++) if (kanalAktif[i]) n++;
  return n;
}

// "Ayni anda cok role" siniri icin sayim.
// KALICI kanallar HARIC: ANAHTAR_GUC saatlerce acik kalacak,
// sayima girerse bir sure sonra diger kanallari kilitler.
int aktifSayisi() {
  int n = 0;
  for (int i = 0; i < KANAL_SAYISI; i++) {
    if (kanalAktif[i] && kanallar[i].sure != KALICI) n++;
  }
  return n;
}

// kaliciDahil = false  : sadece darbe kanallarini birakir.
//   Watchdog bunu kullanir. Pi susunca ANAHTAR_GUC kesilirse
//   arac yolda giderken anahtari kaybeder - bir daha calismaz.
//   Motor kilidi Pi tarafinda, Pi olunce kilit de olur.
//   O yuzden kalici kanallara DOKUNMUYORUZ.
// kaliciDahil = true   : her seyi birakir. Sadece acik komutla.
void hepsiniKapat(bool kaliciDahil) {
  // Motor calisirken kalici kanal hicbir sekilde birakilmaz -
  // HEPSINI_KAPAT ile bile. esp.kapat() bu komutu yolluyor;
  // servis yeniden baslarken arac stop etmesin.
  if (kaliciDahil && !anahtarKesilebilir()) kaliciDahil = false;
  for (int i = 0; i < KANAL_SAYISI; i++) {
    if (!kaliciDahil && kanallar[i].sure == KALICI) continue;
    digitalWrite(kanallar[i].pin, ROLE_PASIF);
    kanalAktif[i] = false;
  }
  if (kaliciPin >= 0) {
    digitalWrite(kaliciPin, ROLE_PASIF);
    kaliciPin = -1;
  }
}

bool elFreniCekili() {
  return digitalRead(PIN_EL_FRENI) == LOW;
}

// ==================== MOTOR TESPITI (AKU VOLTAJI) ====================
// NEDEN BURADA, ESP32'DE:
//   Bu araçta anahtar kaybolursa motor ANINDA stop ediyor. Araç
//   giderken ANAHTAR_GUC kesilirse direksiyon ve fren takviyesi de
//   gider. Bu kilit Pi'ye birakilamaz - Pi cokebilir, yeniden
//   baslayabilir, kapanirken HEPSINI_KAPAT yollayabilir.
//   Son soz ESP32'nin.
//
// Motor calisirken alternator 13.9-14.4 V veriyor, dururken ~12.4 V.
// 11 Ekim 2026: bu esik de panelden ayarlanabilir. Her aracin sarj
// dinamosu farkli: kimi rolantide 13.6 verir, kimi 14.2. Varsayilan
// 13.2 cogu araçta dogru ama araçta olcup duzeltmek gerekebilir.
#define MOTOR_ESIK_VARSAYILAN  13.2f
const float MOTOR_ESIK_MIN = 12.0f;   // 23 Ekim: bu araç calisirken sadece
                                      // 13.1V'a cikiyor (stop 11.9V). Eski
                                      // sinir 12.8 cok yuksekti - esik hic
                                      // tutmuyordu. Onerilen ayar ~12.5.
const float MOTOR_ESIK_MAKS = 14.0f;

float akuCarpan     = AKU_CARPAN_VARSAYILAN;
float motorVoltEsik = MOTOR_ESIK_VARSAYILAN;

// Gecerli akü araligi. Disina cikan okuma = bolucu takili degil
// veya bozuk. O durumda "bilinmiyor" deyip GUVENLI tarafa düşüyoruz:
// motor calisiyor sayiyoruz, enerji KESILMIYOR. Kapilar kilitlenmez,
// bunu hemen fark edersin - ama arac yolda stop etmez.
const float AKU_MIN_GECERLI = 11.0f;
const float AKU_MAKS_GECERLI = 15.5f;

float akuVolt() {
  long toplam = 0;
  for (int i = 0; i < 8; i++) { toplam += analogRead(PIN_AKU); delay(1); }
  return (toplam / 8.0f) / 4095.0f * ADC_REF * akuCarpan;
}

// true  : motor calisiyor VEYA olcum guvenilir degil  -> enerji kesme
// false : motor kesin duruyor                          -> kesilebilir
bool motorDurmus() {
  float v = akuVolt();
  if (v < AKU_MIN_GECERLI || v > AKU_MAKS_GECERLI) return false;  // bilinmiyor
  return v < motorVoltEsik;
}

// Suphesiz "motor calisiyor" - bayragi kaldirmak icin.
bool motorKesinCalisiyor() {
  float v = akuVolt();
  return (v >= motorVoltEsik && v <= AKU_MAKS_GECERLI);
}

// ==================== "ARAC SURULUYOR OLABILIR" BAYRAGI ====================
// NEDEN GEREKLI:
//   Akü voltaji tek basina yetmiyor. Alternator zayiflarsa motor
//   calisirken voltaj 12.8 V'ta kalabilir ve sistem "motor durdu"
//   sanip enerjiyi keser - arac trafikte stop eder.
//
// KAPI SARTI:
//   Aractan inmek icin kapiyi acmak ZORUNDASIN. O yuzden:
//     motor calistigi goruldu          -> suruluyor = true
//     kapi acildi (birisi indi/bindi)  -> suruluyor = false
//   Arac giderken kapi acilmaz, bayrak hep true kalir, enerji kesilmez.
//   Voltajdan tamamen bagimsiz calisir.
bool suruluyor = false;

// ==================== KULLANICI MOTORU ISTEDI (KOMUT KILIDI) ====================
// 23 Ekim 2026: Bu araçta aku voltaji GUVENILMEZ - motor calisirken
// 12.2-13.7 arasi oynuyor, durunca 11.9. Araliklar cok dar. Voltaj esik
// altina her dusende suruluyor false oluyor, anahtar kesilebilir hale
// geliyor ve motor kendiliginden stop ediyordu.
// COZUM: motoru VOLTAJLA degil KOMUTLA koru. "motoru calistir" (MARS)
// gelince bu kilit true olur; kilit true iken ANAHTAR_GUC HICBIR sekilde
// kesilemez (anahtarKesilebilir=false). Yalnizca "motoru durdur" temizler.
// Boylece motor, kullanici durdurana kadar calisir; durdurunca "sistemi
// kapat" da calisir (kilit temizlenince anahtar kesilebilir).
bool kullaniciMotorIstedi = false;

// MOTOR_DURDUR, MARS kanalini kullanir. kanalCalistir() icindeki
// "motor zaten calisiyor" kilidi sadece CALISTIRMA icindir; durdurma
// o yoldan gelirken atlanmalidir. Bu bayrak onu soyler.
bool motorDurdurmaIstegi = false;
unsigned long sonSuruluyorKontrol = 0;
const unsigned long SURULUYOR_ARALIK = 500;

// PC817 ters calisir: arac tarafinda akim varsa pin LOW olur.
// 12 Ekim 2026: artik DORT kapi birden okunuyor. Herhangi biri acikken
// "kapi acik" sayilir - suruluyor bayragini temizlemek icin dogrusu bu.
// ---- KART D kapi girisleri TITREME FILTRESI ----  (29 Ekim 2026)
// GPIO 34-39 dahili pull-up'siz; zayif/eksik harici pull-up olunca bos giris
// gurultuyle salinir ve kapi "acik" gibi TITRER. Gercek acik kapi ise PC817'yi
// SUREKLI LOW'a ceker. Bu yuzden "acik" demek icin pinin KESINTISIZ en az
// KAPI_ACIK_ESIK ms LOW kalmasini sart kosuyoruz: bir an bile HIGH -> aninda
// kapali. Titreme bastirilir, gercek acik gecer. (Sadece KART D: 35/36/39.)
const unsigned long KAPI_ACIK_ESIK = 2000;   // ms, kesintisiz LOW
const int     KARTD_PIN[3]     = { PIN_SURUCU, PIN_KAPUT, PIN_BAGAJ };
bool          kartdStabil[3]   = { false, false, false };
unsigned long kartdLowBasla[3] = { 0, 0, 0 };

void kartdFiltreGuncelle() {
  unsigned long simdi = millis();
  for (int i = 0; i < 3; i++) {
    if (digitalRead(KARTD_PIN[i]) == HIGH) {          // kapali -> aninda
      kartdStabil[i] = false; kartdLowBasla[i] = 0;
    } else {                                          // LOW
      if (kartdLowBasla[i] == 0) kartdLowBasla[i] = simdi;
      if (simdi - kartdLowBasla[i] >= KAPI_ACIK_ESIK) kartdStabil[i] = true;
    }
  }
}
bool kartdAcik(int pin) {
  for (int i = 0; i < 3; i++) if (KARTD_PIN[i] == pin) return kartdStabil[i];
  return digitalRead(pin) == LOW;
}

bool kapiAcik() {
  return kartdAcik(PIN_SURUCU)
      || digitalRead(PIN_YOLCU)     == LOW
      || digitalRead(PIN_SAG_SURGU) == LOW
      || digitalRead(PIN_SOL_SURGU) == LOW;
}

void suruluyorGuncelle() {
  if (millis() - sonSuruluyorKontrol < SURULUYOR_ARALIK) return;
  sonSuruluyorKontrol = millis();
  // 23 Ekim 2026 - MUSUR TAKILI DEGIL:
  // Eski mantik: motor calisinca suruluyor=true, KAPI acilinca=false.
  // Ama musur yok -> kapiAcik() hic true olmuyor -> suruluyor bir kez
  // true olunca ASLA temizlenmiyordu. Bu da anahtarKesilebilir()'i kalici
  // false yapip "sistemi kapat" / kilit ANAHTAR_GUC'u hic kesemiyordu.
  // Musur yokken suruluyor'u dogrudan motor voltajina bagliyoruz: motor
  // durunca (voltaj esik alti) suruluyor da biter, anahtar kesilebilir.
  // NOT: Dogru calismasi icin aku kalibrasyonu + esik DOGRU olmali
  // (motor dururken voltaj esik ALTINDA okunmali).
  // Musur takilinca eski mantik geri gelmeli (kapiAcik ile temizleme).
  suruluyor = motorKesinCalisiyor();
}

// Anahtar enerjisi kesilebilir mi?
// Kullanici motoru istediyse ASLA kesilemez (voltaj ne okursa okusun).
// Aksi halde eski sart: motor durmus VE arac suruluyor degil.
bool anahtarKesilebilir() {
  if (kullaniciMotorIstedi) return false;
  return motorDurmus() && !suruluyor;
}

// Kanali calistirir. Sonuc metnini doner.
String kanalCalistir(int i) {
  Kanal &k = kanallar[i];

  // KILIT KONTROLU: ters yondeki role cekiliyse RET.
  // Cam motorunu ayni anda iki yone surmek motoru yakar.
  if (k.kilit >= 0 && kanalAktif[k.kilit]) {
    return String("RET|") + k.ad + "|ters_yon_aktif|"
           + kanallar[k.kilit].ad;
  }

  // AYNI ANDA COK ROLE: besleme cokmesin
  if (!kanalAktif[i] && aktifSayisi() >= MAKS_AYNI_ANDA) {
    return String("RET|") + k.ad + "|cok_role_aktif|"
           + String(aktifSayisi());
  }

  // MARS: el freni sarti (ayar acikken)
  if (String(k.ad) == "MARS" && EL_FRENI_KONTROLU && !elFreniCekili()) {
    return String("RET|MARS|el_freni_bos");
  }

  // MARS: motor ZATEN calisiyorsa basma - ayni buton motoru DURDURUR.
  // "Motoru calistir" deyince motorun durmasi sasirtici ve tehlikeli
  // olurdu. Durdurmak icin ayri komut var: MOTOR_DURDUR.
  //
  // MOTOR_DURDUR ayni kanali kullandigi icin o yoldan gelirken bu
  // kilit atlanir - durdurmanin SARTI zaten motorun calisiyor olmasi.
  // 24 Ekim 2026: Voltaj bu araçta motor durumunu AYIRMIYOR - dinlenen aku
  // ~13V, motor calisirken de ~13V (cakisiyor). O yuzden "zaten calisiyor"
  // karari VOLTAJDAN DEGIL komut hafizasindan: komutla calistirildiysa
  // (kullaniciMotorIstedi) tekrar basma. Boylece dinlenen 13V "calisiyor"
  // sanilip "calistir" reddedilmiyor, role tetikleniyor.
  // 30 Ekim 2026 - BLOKE KILIT KALDIRILDI.
  // Eskiden: kullaniciMotorIstedi bayragi acikken "calistir" MARS'a basmazdi.
  // Sorun: motor kendiliginden durunca (stall/oto-stop) bayrak ACIK kaliyordu;
  // o anda "calistir" is yapmiyor, "durdur" ise kilidi atlayip motoru
  // calistiriyordu -> komutlar TERS gorunuyordu. Ekran artik durumu dogru
  // takip ediyor (panelde Motor'a basili tutunca senkronlaniyor), bu yuzden
  // MARS'i HER "calistir" komutunda tetikliyoruz. Tek-buton toggle guvenle
  // calisir; bayrak sadece keep-alive (ANAHTAR_GUC) icin set edilir.
  // (Bloke eden RET cikarildi.)

  // MOTORU CALISTIR (MARS, durdurma DEGIL): kullanici motoru istedi.
  // Bu andan itibaren ANAHTAR_GUC otomatik kesilemez (voltaj dusuk okunsa
  // da). Yalnizca MOTOR_DURDUR bu kilidi temizler.
  if (String(k.ad) == "MARS" && !motorDurdurmaIstegi) {
    kullaniciMotorIstedi = true;
  }

  // KALICI kanal: ac ve birakma. Kendi kendine dusmez.
  if (k.sure == KALICI) {
    digitalWrite(k.pin, ROLE_AKTIF);
    bitisZamani[i] = 0;          // kullanilmiyor
    kanalAktif[i] = true;
    return String("OK|") + k.ad + "|D" + String(k.pin) + "|kalici";
  }

  digitalWrite(k.pin, ROLE_AKTIF);
  bitisZamani[i] = millis() + k.sure;
  kanalAktif[i] = true;
  return String("OK|") + k.ad + "|D" + String(k.pin)
         + "|" + String(k.sure) + "ms";
}

// Kalici kanali birakir. Darbe kanallarinda da calisir (erken birakir).
String kanalBirak(int i) {
  Kanal &k = kanallar[i];

  // GUVENLIK KILIDI: motor calisirken ANAHTAR_GUC kesilmez.
  // Kesilirse arac stop eder - yolda giderken olursa tehlikeli.
  if (k.sure == KALICI && !anahtarKesilebilir()) {
    return String("RET|") + k.ad
           + (suruluyor ? "|arac_suruluyor" : "|motor_calisiyor")
           + "|aku=" + String(akuVolt(), 2);
  }

  digitalWrite(k.pin, ROLE_PASIF);
  kanalAktif[i] = false;
  bitisZamani[i] = 0;
  return String("OK|") + k.ad + "|D" + String(k.pin) + "|birakildi";
}

void darbeleriKontrol() {
  unsigned long simdi = millis();
  for (int i = 0; i < KANAL_SAYISI; i++) {
    if (kanallar[i].sure == KALICI) continue;   // kalici dusmez
    if (kanalAktif[i] && simdi >= bitisZamani[i]) {
      digitalWrite(kanallar[i].pin, ROLE_PASIF);
      kanalAktif[i] = false;
    }
  }
}


// ==================== DS18B20 ISI SENSORLERI ====================
//
// Tek hat (1-Wire) uzerinde iki sensor: IC ve DIS.
// Ikisi de AYNI pine (D16) paralel baglanir, tek 4.7k pull-up
// ikisine birden yeter. Her sensorun fabrikada yazilmis 64 bitlik
// kendi adresi var, ayirt etme oradan.
//
// KUTUPHANE KULLANILMIYOR. OneWire/DallasTemperature kurman
// gerekmesin diye surucusu burada yazili - RC522'de oldugu gibi.
//
// IC / DIS hangisi? Adres sirasina gore ilki IC, ikincisi DIS.
// Ters dustuyse  ISI_DEGISTIR  komutu yer degistirir ve kaydeder,
// bir daha ugrasmazsin.
//
// OLCUM BLOKLAMAZ. Donusum 750 ms suruyor; ana dongu o kadar
// beklerse roleler ve guvenlik kilitleri aksar. Bu yuzden
// "baslat -> 800 ms sonra oku" seklinde parca parca yapiliyor.

#define PIN_ISI     16        // D16 (kartta RX2 yaziyor)
#define ISI_MAKS     4

Preferences kalici;

uint8_t  isiAdres[ISI_MAKS][8];
float    isiDeger[ISI_MAKS];
int      isiSayisi   = 0;
// IC sensorun ADRESI kalici hafizada durur.
// Neden sira degil de adres: sensorler adrese gore siralaniyor.
// Tek sensorle "bu ictir" deyip ikincisini sonradan takarsan,
// yeni sensorun adresi kucukse listede one gecer ve ic sensorun
// kendiliginden disa donerdi. Adres sabit oldugu icin bu olmaz.
// Bos ise listedeki ilk sensor ic sayilir.
String   isiIcAdres  = "";
bool     isiCevapVar = false;    // son taramada hattan cevap geldi mi
bool     isiBekliyor = false;
unsigned long isiZaman = 0;
const unsigned long ISI_ARALIK = 5000;   // kac ms'de bir olcsun
const unsigned long ISI_SURE   = 800;    // donusum suresi (750 ms + pay)
const unsigned long ISI_TARAMA = 30000;  // sensor yoksa tekrar arama araligi

// ---- 1-Wire temel islemler ----
// Hat "acik kollektor": pini OUTPUT+LOW yapmak hatti asagi ceker,
// INPUT yapmak birakir ve 4.7k yukari ceker.

// 11 Ekim 2026 - ZAMANLAMA DUZELTMESI
// Ilk surumde her bit icin pinMode() cagriliyordu. ESP32'de pinMode
// YAVAS (mikrosaniyeler suruyor); 1-Wire'in okuma penceresi ise
// dusen kenardan sonra 15 us. pinMode gecikmesi eklenince ornekleme
// penceresi kaciriyordu: reset darbesi goruluyor ama hicbir bit
// dogru okunmuyordu, dolayisiyla ROM aramasi hep BOS donuyordu.
//
// Cozum: pin BIR KEZ "acik kollektor" (OUTPUT_OPEN_DRAIN) yapiliyor.
// Sonrasinda sadece digitalWrite var:
//     LOW  yazmak  -> hatti asagi ceker
//     HIGH yazmak  -> hatti birakir, 4.7k yukari ceker
// digitalWrite ESP32'de pinMode'dan cok daha hizli, zamanlama tutuyor.
// Acik kollektor modunda digitalRead de calisir.

static inline void owAsagi() { digitalWrite(PIN_ISI, LOW);  }
static inline void owBirak() { digitalWrite(PIN_ISI, HIGH); }

static void owHazirla() {
  pinMode(PIN_ISI, OUTPUT_OPEN_DRAIN);
  digitalWrite(PIN_ISI, HIGH);
}

static bool owReset() {
  owHazirla();
  owAsagi();
  delayMicroseconds(480);
  noInterrupts();
  owBirak();
  delayMicroseconds(70);
  bool var = (digitalRead(PIN_ISI) == LOW);   // sensor kendini bildirdi
  interrupts();
  delayMicroseconds(410);
  return var;
}

static void owYazBit(uint8_t b) {
  noInterrupts();
  owAsagi();
  delayMicroseconds(b ? 6 : 60);
  owBirak();
  delayMicroseconds(b ? 64 : 10);
  interrupts();
}

static uint8_t owOkuBit() {
  noInterrupts();
  owAsagi();
  delayMicroseconds(3);
  owBirak();
  delayMicroseconds(9);
  uint8_t b = digitalRead(PIN_ISI);
  interrupts();
  delayMicroseconds(53);
  return b;
}

static void owYaz(uint8_t v) {
  for (int i = 0; i < 8; i++) { owYazBit(v & 1); v >>= 1; }
}

static uint8_t owOku() {
  uint8_t v = 0;
  for (int i = 0; i < 8; i++) if (owOkuBit()) v |= (1 << i);
  return v;
}

// Dallas CRC8 - okunan verinin bozulmadigini dogrular
static uint8_t owCrc(const uint8_t *d, int n) {
  uint8_t crc = 0;
  while (n--) {
    uint8_t b = *d++;
    for (int i = 0; i < 8; i++) {
      uint8_t k = (crc ^ b) & 0x01;
      crc >>= 1;
      if (k) crc ^= 0x8C;
      b >>= 1;
    }
  }
  return crc;
}

// ---- ROM arama (Maxim SEARCH ROM) ----
// Hattaki butun sensorlerin adresini tek tek bulur.
static int  owCakisma = 0;
static bool owBitti   = false;
static uint8_t owRom[8];

static bool owAra(bool ilk) {
  if (ilk) { owCakisma = 0; owBitti = false; memset(owRom, 0, 8); }
  if (owBitti) return false;
  if (!owReset()) { owCakisma = 0; owBitti = false; return false; }
  owYaz(0xF0);                       // SEARCH ROM
  int sonSifir = 0;
  for (int i = 1; i <= 64; i++) {
    int bayt = (i - 1) / 8;
    uint8_t mask = 1 << ((i - 1) % 8);
    uint8_t b1 = owOkuBit();
    uint8_t b2 = owOkuBit();
    if (b1 && b2) return false;      // hatta aygit yok
    uint8_t sec;
    if (b1 != b2) {
      sec = b1;                      // butun aygitlar ayni bitte hemfikir
    } else {
      if (i < owCakisma)       sec = (owRom[bayt] & mask) ? 1 : 0;
      else if (i == owCakisma) sec = 1;
      else                     sec = 0;
      if (sec == 0) sonSifir = i;
    }
    if (sec) owRom[bayt] |=  mask;
    else     owRom[bayt] &= ~mask;
    owYazBit(sec);
  }
  owCakisma = sonSifir;
  if (owCakisma == 0) owBitti = true;
  return (owCrc(owRom, 7) == owRom[7]);
}

static String isiAdresYazi(const uint8_t *a) {
  String s;
  for (int i = 0; i < 8; i++) {
    if (a[i] < 16) s += "0";
    s += String(a[i], HEX);
  }
  return s;
}

// Hatti tarar, bulunan DS18B20'leri adrese gore SIRALAR.
// Siralama sart: her acilista ayni sensor ayni sirada olsun,
// yoksa IC ile DIS kendiliginden yer degistirir.
void isiTara() {
  isiSayisi = 0;
  // ONEMLI TESHIS: reset darbesine cevap gelmis mi?
  // Hatta CALISAN bir sensor varsa, yazilim zamanlamasi bozuk olsa
  // bile bu cevap gelir - penceresi genis. Yani:
  //   cevap=var,  sayi=0  ->  sensor hatta, sorun YAZILIMDA
  //   cevap=yok,  sayi=0  ->  sensor hatta hic yok, sorun DONANIMDA
  // Bu tek bit, aranacak yeri ikiye boluyor.
  isiCevapVar = owReset();
  if (!isiCevapVar) return;
  bool ilk = true;
  while (isiSayisi < ISI_MAKS && owAra(ilk)) {
    ilk = false;
    if (owRom[0] == 0x28) {                  // DS18B20 aile kodu
      memcpy(isiAdres[isiSayisi], owRom, 8);
      isiDeger[isiSayisi] = NAN;
      isiSayisi++;
    }
  }
  for (int i = 0; i < isiSayisi; i++)
    for (int j = i + 1; j < isiSayisi; j++)
      if (memcmp(isiAdres[j], isiAdres[i], 8) < 0) {
        uint8_t t[8];
        memcpy(t, isiAdres[i], 8);
        memcpy(isiAdres[i], isiAdres[j], 8);
        memcpy(isiAdres[j], t, 8);
      }
}

// Ana donguden cagrilir. Hicbir yerde beklemez.
void isiGuncelle() {
  unsigned long s = millis();

  if (!isiBekliyor) {
    if (isiSayisi == 0) {
      if (s - isiZaman < ISI_TARAMA) return;   // sensor yok, ara sira bak
      isiZaman = s;
      isiTara();
      return;
    }
    if (s - isiZaman < ISI_ARALIK) return;
    isiZaman = s;
    if (!owReset()) { isiSayisi = 0; return; }  // hat koptu, yeniden ara
    owYaz(0xCC);                 // SKIP ROM  - hepsi birden
    owYaz(0x44);                 // CONVERT T
    isiBekliyor = true;
    return;
  }

  if (s - isiZaman < ISI_SURE) return;
  isiBekliyor = false;

  for (int i = 0; i < isiSayisi; i++) {
    if (!owReset()) continue;
    owYaz(0x55);                                      // MATCH ROM
    for (int j = 0; j < 8; j++) owYaz(isiAdres[i][j]);
    owYaz(0xBE);                                      // READ SCRATCHPAD
    uint8_t sp[9];
    for (int j = 0; j < 9; j++) sp[j] = owOku();
    if (owCrc(sp, 8) != sp[8]) continue;              // bozuk okuma, atla
    int16_t ham = (int16_t)((sp[1] << 8) | sp[0]);
    if (ham == 0x0550) continue;   // 85.0 = sensore yeni guc geldi, gecersiz
    isiDeger[i] = ham / 16.0f;
  }
}

// Kayitli IC adresi hattaki sensorlerden birine uyuyorsa o IC'dir.
// Uymuyorsa (sensor sokulmus ya da hic kayit yok) listedeki ilk
// sensor IC sayilir - tek sensorle calisirken makul davranis.
int isiIcIndeks() {
  if (isiSayisi == 0) return -1;
  if (isiIcAdres.length() == 16)
    for (int i = 0; i < isiSayisi; i++)
      if (isiAdresYazi(isiAdres[i]) == isiIcAdres) return i;
  return 0;
}

// DIS = IC olmayan ilk sensor. Tek sensor varsa DIS yoktur.
int isiDisIndeks() {
  int ic = isiIcIndeks();
  for (int i = 0; i < isiSayisi; i++) if (i != ic) return i;
  return -1;
}

float isiIc()  { int i = isiIcIndeks();  return (i >= 0) ? isiDeger[i] : NAN; }
float isiDis() { int i = isiDisIndeks(); return (i >= 0) ? isiDeger[i] : NAN; }

// Cevapta kullanilacak metin. Okuma yoksa "-" gonderilir,
// Pi tarafi onu "bilinmiyor" sayar ve eski degeri bozmaz.
static String isiYazi(float v) {
  if (isnan(v)) return "-";
  return String(v, 1);
}


// ==================== DARBE SURELERI  (ayarlanabilir) ====================
//
// 11 Ekim 2026
// Cam motorlari ayni sureyle ayni mesafeyi acmiyor: biri 3 saniyede
// tam aciliyor, oteki yarida kaliyor. Araca gore, hatta cama gore
// degisiyor. Her seferinde yazilim degistirmek yerine sureler artik
// PANELDEN ayarlanabiliyor ve kalici hafizaya yaziliyor.
//
// Tablodaki degerler VARSAYILAN olarak duruyor; ayar yapilmadiysa
// onlar gecerli. SURE_SIFIRLA ile her zaman onlara donulebilir.

const unsigned long SURE_MIN  = 100;      // 0.1 sn - altina inilmez
const unsigned long SURE_MAKS = 15000;    // 15 sn - ustune cikilmaz

unsigned long varsayilanSure[16];

// Kalici hafiza anahtari. Kanal ADI kullanilamaz: NVS anahtarlari en
// fazla 15 karakter, "SURUCU_CAM_KAPAT" 16. O yuzden sira numarasi.
static void sureAnahtari(int i, char* hedef, size_t n) {
  snprintf(hedef, n, "s%d", i);
}

void sureleriYukle() {
  for (int i = 0; i < KANAL_SAYISI; i++) {
    varsayilanSure[i] = kanallar[i].sure;
    if (kanallar[i].sure == KALICI) continue;   // kalici kanal darbe degil
    char k[8]; sureAnahtari(i, k, sizeof(k));
    unsigned long v = kalici.getULong(k, 0);
    if (v >= SURE_MIN && v <= SURE_MAKS) kanallar[i].sure = v;
  }
}

String sureleriYaz() {
  String g = "SURELER";
  for (int i = 0; i < KANAL_SAYISI; i++) {
    g += "|";
    g += kanallar[i].ad;
    g += "=";
    if (kanallar[i].sure == KALICI) g += "kalici";
    else {
      g += String(kanallar[i].sure);
      // Varsayilandan farkliysa yildizla isaretle - panelde gorunur
      if (kanallar[i].sure != varsayilanSure[i]) g += "*";
    }
  }
  return g;
}

String sureAyarla(String ad, long ms) {
  ad.trim();
  int i = kanalBul(ad);
  if (i < 0) return "HATA|bilinmeyen_kanal|" + ad;
  if (varsayilanSure[i] == KALICI)
    return "HATA|kalici_kanal|" + ad + "|darbe_suresi_yok";
  if (ms < (long)SURE_MIN || ms > (long)SURE_MAKS)
    return "HATA|sure_disinda|" + String(SURE_MIN) + "-" + String(SURE_MAKS);
  kanallar[i].sure = (unsigned long)ms;
  char k[8]; sureAnahtari(i, k, sizeof(k));
  kalici.putULong(k, (unsigned long)ms);
  return "OK|SURE|" + ad + "=" + String(ms);
}

// ==================== AKU KALIBRASYONU VE MOTOR ESIGI ====================
//
// 11 Ekim 2026
// Bolucu direncleri ve ESP32'nin ADC'si birebir ayni degil; her
// kartta kucuk bir sapma oluyor. Bu sabah masada elle hesapladik:
//     gercek 11.89 V iken yazilim 11.00 gosterdi  ->  carpan x1.081
// Ayni islemi artik cihaz kendi yapiyor. Araçta multimetreyle
// akü ucundan okudugun degeri yaz, gerisi otomatik.
//
// NEDEN ONEMLI: anahtar kesme guvenlik kilidi bu okumaya bakiyor.
// Yanlis okursa ya hic kesmez ya da yanlis anda keser.

void ayarlariYukle() {
  float c = kalici.getFloat("akuCarpan", 0.0f);
  if (c > 1.0f && c < 20.0f) akuCarpan = c;
  float e = kalici.getFloat("motorEsik", 0.0f);
  if (e >= MOTOR_ESIK_MIN && e <= MOTOR_ESIK_MAKS) motorVoltEsik = e;
}

String ayarlariYaz() {
  String g = "AYARLAR";
  g += "|aku_carpan=" + String(akuCarpan, 3);
  g += "|aku_carpan_v=" + String(AKU_CARPAN_VARSAYILAN, 3);
  g += "|motor_esik=" + String(motorVoltEsik, 2);
  g += "|motor_esik_v=" + String(MOTOR_ESIK_VARSAYILAN, 2);
  g += "|aku=" + String(akuVolt(), 2);
  return g;
}

// Multimetreyle olculen gercek degeri alir, carpani buna gore duzeltir.
String akuKalibre(float gercek) {
  if (gercek < 5.0f || gercek > 20.0f)
    return "HATA|olcum_disinda|5-20V_arasi_olmali";
  float okunan = akuVolt();
  if (okunan < 1.0f)
    return "HATA|okuma_yok|bolucu_bagli_mi";
  float yeni = akuCarpan * (gercek / okunan);
  if (yeni < 1.0f || yeni > 20.0f)
    return "HATA|carpan_disinda|" + String(yeni, 3);
  float eski = akuCarpan;
  akuCarpan = yeni;
  kalici.putFloat("akuCarpan", yeni);
  return "OK|AKU_KALIBRE|okunan=" + String(okunan, 2)
       + "|gercek=" + String(gercek, 2)
       + "|carpan=" + String(eski, 3) + "->" + String(yeni, 3)
       + "|simdi=" + String(akuVolt(), 2);
}

String motorEsikAyarla(float v) {
  if (v < MOTOR_ESIK_MIN || v > MOTOR_ESIK_MAKS)
    return "HATA|esik_disinda|" + String(MOTOR_ESIK_MIN, 1)
         + "-" + String(MOTOR_ESIK_MAKS, 1);
  motorVoltEsik = v;
  kalici.putFloat("motorEsik", v);
  return "OK|MOTOR_ESIK|" + String(v, 2);
}

String ayarlariSifirla() {
  akuCarpan = AKU_CARPAN_VARSAYILAN;
  motorVoltEsik = MOTOR_ESIK_VARSAYILAN;
  kalici.remove("akuCarpan");
  kalici.remove("motorEsik");
  return "OK|AYAR_SIFIRLA|varsayilanlara_donuldu";
}


String sureleriSifirla() {
  for (int i = 0; i < KANAL_SAYISI; i++) {
    kanallar[i].sure = varsayilanSure[i];
    char k[8]; sureAnahtari(i, k, sizeof(k));
    kalici.remove(k);
  }
  return "OK|SURE_SIFIRLA|varsayilanlara_donuldu";
}


// ==================== KOMUT ISLEME ====================
void komutIsle(String k) {
  k.trim();
  k.toUpperCase();
  if (k.length() == 0) return;

  sonHaber = millis();
  watchdogAktif = true;

  // ---- PING ----
  if (k == "PING") { cevap("PONG"); return; }

  // ---- DURUM ----
  if (k == "DURUM") {
    String d = "DURUM|aktif=" + String(aktifSayisiTum());
    for (int i = 0; i < KANAL_SAYISI; i++) {
      if (kanalAktif[i]) {
        d += "|"; d += kanallar[i].ad;
        if (kanallar[i].sure == KALICI) d += "(kalici)";
      }
    }
    d += "|elfreni=";
    d += EL_FRENI_KONTROLU
         ? (elFreniCekili() ? "cekili" : "bos")
         : "kontrol_kapali";
    d += "|aku=" + String(akuVolt(), 2);
    d += "|suruluyor=";  d += suruluyor ? "1" : "0";
    d += "|anahtar_kesilebilir="; d += anahtarKesilebilir() ? "1" : "0";
    d += "|calisma=" + String(millis() / 1000);
    cevap(d);
    return;
  }

  // ---- MOTOR_DURDUR ----
  //
  // ARACTA DOGRULANDI (8 Ekim 2026): kumandanin BAGAJ butonu
  //   kisa basis        -> bagaj acilir
  //   4-6 sn basili     -> motor CALISIR
  //   tekrar 4-6 sn     -> motor DURUR
  // Ucu de ayni fiziksel kontak. Calistirma ile durdurma arasindaki
  // TEK fark, o anda motorun calisip calismadigi.
  //
  // Bu yuzden bu komut korumasiz birakilamaz:
  //   motorun calistigi dogrulanamiyorsa -> basmak motoru CALISTIRIR
  //   arac suruluyorsa -> motoru durdurmak direksiyon ve fren
  //                       takviyesini goturur, TEHLIKELI
  //
  // Iki sart birden saglanmadan role cekilmez. Akü bölücüsü takili
  // degilse (aku=0.00) motor durumu bilinemez ve komut hep reddedilir -
  // guvenli taraf budur.
  if (k == "MOTOR_DURDUR") {
    // 23 Ekim 2026: "suruluyor" guard'i KALDIRILDI.
    // O guard musur (kapi sensoru) ile "arac gidiyor mu" anlamaya
    // calisiyordu; ama bu araçta MUSUR TAKILI DEGIL. Musur olmayinca
    // suruluyor bir kez true olunca (motor calisir calismaz) ASLA
    // temizlenemiyor ve motoru durdurmayi KALICI blokluyordu - role hic
    // tetiklenmiyordu. Koruma olarak motorKesinCalisiyor() yetiyor:
    // motor calismiyorsa MARS toggle'i onu CALISTIRIRDI, o yuzden komut
    // yalnizca motor GERCEKTEN calisirken gecer.
    // NOT: musur takildiginda "giderken durdurma" guvenligi geri eklenmeli.
    // 23 Ekim 2026: Voltaj bu araçta guvenilmez (calisirken 12.2'ye
    // dusebiliyor). O yuzden "motor calisiyor mu"yu voltajdan DEGIL
    // komut kilidinden anla: kullanici motoru istediyse (kullaniciMotorIstedi)
    // durdur. Yalnizca kilit YOK ve voltaj da dusukse "zaten durmus" de -
    // o durumda MARS toggle motoru CALISTIRIRDI, onu engelle.
    // 24 Ekim 2026: Voltaj guvenilmez (dinlenen ~13V ile calisan ~13V
    // cakisiyor). "Zaten durmus" karari SADECE komut hafizasindan:
    // komutla calistirilmadiysa durmus say. (Elle calistirdiysan komutla
    // durduramazsin; o zaman elle durdur ya da sistemi yeniden baslat.)
    if (!kullaniciMotorIstedi) {
      cevap("RET|MOTOR_DURDUR|motor_zaten_durmus|komutla");
      return;
    }
    int mi = kanalBul("MARS");
    if (mi < 0) { cevap("HATA|MARS_kanali_yok"); return; }
    // Kullanici durdurdu: komut kilidini temizle (artik anahtar kesilebilir,
    // "sistemi kapat" calisir). Latch'i ATESLEMEDEN once temizle ki
    // kanalCalistir bu MARS'i yeniden "calistir" sanip kilidi geri koymasin.
    kullaniciMotorIstedi = false;
    motorDurdurmaIstegi = true;
    String c = kanalCalistir(mi);
    motorDurdurmaIstegi = false;
    cevap(c);
    return;
  }

  // ---- GIRIS : musurler + aku ----
  //  Cevap:  GIRIS|kapi=0|surucu=0|yolcu=0|sagsurgu=0|solsurgu=0
  //          |kaput=0|bagaj=1|aku=12.42|ic=21.4|dis=8.1|kart=-
  //  kapi = dort kapidan HERHANGI biri acik mi (eski alan, duruyor).
  //  1 = ACIK.  PC817 tersligi BURADA cevrilir, Pi duz okur.
  //  ic/dis: DS18B20 sicakliklari. Sensor yoksa "-" gelir.
  if (k == "GIRIS") {
    bool surucu    = kartdAcik(PIN_SURUCU);   // filtreli
    bool yolcu     = (digitalRead(PIN_YOLCU)     == LOW);
    bool sagSurgu  = (digitalRead(PIN_SAG_SURGU) == LOW);
    bool solSurgu  = (digitalRead(PIN_SOL_SURGU) == LOW);
    bool kaput     = kartdAcik(PIN_KAPUT);    // filtreli
    bool bagaj     = kartdAcik(PIN_BAGAJ);    // filtreli
    // "kapi" = dort kapidan herhangi biri. Eski alan, yerinde duruyor:
    // kilitleme guvenligi ve eski Pi yazilimi bu alani okuyor.
    bool kapi      = surucu || yolcu || sagSurgu || solSurgu;

    float volt = akuVolt();   // 8 olcumun ortalamasi

    String g = "GIRIS";
    g += "|kapi=";      g += kapi     ? "1" : "0";
    g += "|surucu=";    g += surucu   ? "1" : "0";
    g += "|yolcu=";     g += yolcu    ? "1" : "0";
    g += "|sagsurgu=";  g += sagSurgu ? "1" : "0";
    g += "|solsurgu=";  g += solSurgu ? "1" : "0";
    g += "|kaput="; g += kaput ? "1" : "0";
    g += "|bagaj="; g += bagaj ? "1" : "0";
    g += "|aku=";   g += String(volt, 2);
    g += "|ic=";    g += isiYazi(isiIc());
    g += "|dis=";   g += isiYazi(isiDis());
    // Okunan kart burada bildirilir ve TEMIZLENIR. Boylece Pi
    // saniyede bir GIRIS sorarken karti kacirmaz - kart okundugu
    // anda beklemeye alinir, Pi alinca silinir.
    g += "|kart=";  g += sonKart.length() ? sonKart : "-";
    sonKart = "";
    cevap(g);
    return;
  }

  // ---- AYARLAR : kalibrasyon ve esik degerleri ----
  if (k == "AYARLAR") { cevap(ayarlariYaz()); return; }

  // ---- AKU_KALIBRE <gercek_volt> ----
  // Multimetreyle olculeni yaz, carpani cihaz kendi hesaplasin.
  if (k.startsWith("AKU_KALIBRE ")) {
    cevap(akuKalibre(k.substring(12).toFloat()));
    return;
  }

  // ---- MOTOR_ESIK <volt> ----
  if (k.startsWith("MOTOR_ESIK ")) {
    cevap(motorEsikAyarla(k.substring(11).toFloat()));
    return;
  }

  // ---- AYAR_SIFIRLA : kalibrasyon ve esik varsayilana ----
  if (k == "AYAR_SIFIRLA") { cevap(ayarlariSifirla()); return; }

  // ---- SURELER : darbe surelerini listele ----
  //  Cevap:  SURELER|KAPI_AC=500|SURUCU_CAM_AC=3000*|...
  //  Yildiz = varsayilandan degistirilmis
  if (k == "SURELER") { cevap(sureleriYaz()); return; }

  // ---- SURE <kanal> <ms> : darbe suresini ayarla (kalici) ----
  //  Ornek:  SURE SURUCU_CAM_AC 4500
  if (k.startsWith("SURE ")) {
    String a = k.substring(5); a.trim();
    int bosluk = a.lastIndexOf(' ');
    if (bosluk < 0) { cevap("HATA|kullanim|SURE <kanal> <ms>"); return; }
    String ad = a.substring(0, bosluk); ad.trim();
    long ms = a.substring(bosluk + 1).toInt();
    cevap(sureAyarla(ad, ms));
    return;
  }

  // ---- SURE_SIFIRLA : hepsini varsayilana dondur ----
  if (k == "SURE_SIFIRLA") { cevap(sureleriSifirla()); return; }

  // ---- ISI : sicakliklar ----
  //  Cevap:  ISI|ic=21.4|dis=8.1|sayi=2
  if (k == "ISI") {
    String g = "ISI";
    g += "|ic=";   g += isiYazi(isiIc());
    g += "|dis=";  g += isiYazi(isiDis());
    g += "|sayi="; g += String(isiSayisi);
    cevap(g);
    return;
  }

  // ---- ISI_TARA : hatti yeniden tara, adresleri listele ----
  // Yeni sensor ekledikten sonra ESP32'yi yeniden baslatmadan
  // bulmasi icin. IC adresi kayitliysa o sensor IC kalir -
  // yeni sensor hangi sirada cikarsa ciksin degismez.
  if (k == "ISI_TARA") {
    isiTara();
    isiBekliyor = false;
    isiZaman = millis() - ISI_ARALIK;   // hemen olcsun
    int ic = isiIcIndeks(), dis = isiDisIndeks();
    String g = "ISI_TARA|sayi=" + String(isiSayisi);
    g += isiCevapVar ? "|cevap=var" : "|cevap=yok";
    for (int i = 0; i < isiSayisi; i++) {
      g += "|";
      g += (i == ic) ? "ic=" : ((i == dis) ? "dis=" : "fazla=");
      g += isiAdresYazi(isiAdres[i]);
    }
    if (isiIcAdres.length() != 16) g += "|kayit=yok";
    cevap(g);
    return;
  }

  // ---- ISI_IC : "su an IC okuyan sensor IC'dir" diye KAYDET ----
  // Tek sensorle calisirken en kullanisli komut: elindeki probu
  // tak, ISI_IC gonder, adresi kalici hafizaya yazilir. Ikinci
  // sensoru aylar sonra eklesen de bu IC kalir, yeni gelen DIS olur.
  if (k == "ISI_IC") {
    int i = isiIcIndeks();
    if (i < 0) { cevap("ISI_IC|HATA|sensor_yok"); return; }
    isiIcAdres = isiAdresYazi(isiAdres[i]);
    kalici.putString("isiIc", isiIcAdres);
    cevap("ISI_IC|kaydedildi|" + isiIcAdres);
    return;
  }

  // ---- ISI_DEGISTIR : IC ile DIS yer degistirsin ----
  // Ekranda ic/dis ters gorunuyorsa tek komut. Kalici hafizaya
  // yazilir, elektrik kesilse de unutmaz.
  if (k == "ISI_DEGISTIR") {
    int dis = isiDisIndeks();
    if (dis < 0) { cevap("ISI_DEGISTIR|HATA|ikinci_sensor_yok"); return; }
    isiIcAdres = isiAdresYazi(isiAdres[dis]);   // DIS olan artik IC
    kalici.putString("isiIc", isiIcAdres);
    cevap(String("ISI_DEGISTIR|degisti")
          + "|ic=" + isiYazi(isiIc())
          + "|dis=" + isiYazi(isiDis()));
    return;
  }

  // ---- KART : RFID durumu / son okunan ----
  if (k == "KART") {
#if !RFID_ESP32
    cevap("KART|rfid_pi_tarafinda"); return;
#endif
    if (!rfidVar) { cevap("KART|yok|okuyucu_bulunamadi"); return; }
    String u = sonKart; sonKart = "";
    cevap("KART|" + String(u.length() ? u : "-"));
    return;
  }

  // ---- RFID TESHIS KOMUTLARI KAPALI ----
  // Hepsi RFID_SCK / RFID_MOSI / RFID_MISO pinlerini elle suruyor.
  // RC522 Pi'ye tasindigina gore bu pinler artik kapi girisi; bir
  // teshis komutu kazara gelirse uc kapiyi birden bozar. Kapatildi.
#if !RFID_ESP32
  if (k == "KART_TEST" || k == "KART_PIN" || k == "KART_DONGU"
      || k.startsWith("KART_KABLO ")) {
    cevap("KART|rfid_pi_tarafinda|D27_D32_D33_kapi_girisi");
    return;
  }
#endif

  // ---- KART_TEST : kablolama dogru mu ----
  // Okuyucunun yonga surumunu okur. 0x00 veya 0xFF gelirse
  // kablo kopuk ya da modul takili degil demektir.
  if (k == "KART_TEST") {
    byte s = rcOku(RC_VersionReg);
    String m = "KART_TEST|surum=0x";
    if (s < 0x10) m += "0";
    m += String(s, HEX);
    m += (s == 0x00 || s == 0xFF) ? "|MODUL_YOK" : "|TAMAM";
    cevap(m);
    return;
  }

  // ---- KART_PIN : RFID kablolama teshisi ----
  if (k == "KART_PIN") {
    String m = "KART_PIN";

    // MISO bagli mi? Dahili direncle yukari ve asagi cekip bakiyoruz.
    pinMode(RFID_MISO, INPUT_PULLUP);
    delay(5);
    bool mYukari = digitalRead(RFID_MISO);
    pinMode(RFID_MISO, INPUT_PULLDOWN);
    delay(5);
    bool mAsagi = digitalRead(RFID_MISO);
    pinMode(RFID_MISO, INPUT);

    m += "|miso_cekili_yukari="; m += mYukari ? "1" : "0";
    m += "|miso_cekili_asagi=";  m += mAsagi  ? "1" : "0";
    m += "|miso=";
    if (!mYukari && !mAsagi)      m += "TOPRAGA_KACMIS";
    else if (mYukari && mAsagi)   m += "BESLEMEYE_KACMIS_ya_da_modul_suruyor";
    else                          m += "BOSTA_ya_da_normal";

    m += "|sck=";  m += pinSaglamMi(RFID_SCK)  ? "ok" : "SORUNLU";
    m += "|mosi="; m += pinSaglamMi(RFID_MOSI) ? "ok" : "SORUNLU";
    m += "|ss=";   m += pinSaglamMi(RFID_SS)   ? "ok" : "SORUNLU";

    // Donanim SPI'yi atlayip elle oku
    byte e = rcOkuElle(RC_VersionReg);
    m += "|elle_surum=0x";
    if (e < 0x10) m += "0";
    m += String(e, HEX);

    // Pinleri SPI'ye geri ver ve donanimla da oku
    rfidSpi.begin(RFID_SCK, RFID_MISO, RFID_MOSI, RFID_SS);
    pinMode(RFID_SS, OUTPUT);
    digitalWrite(RFID_SS, HIGH);
    byte h = rcOku(RC_VersionReg);
    m += "|donanim_surum=0x";
    if (h < 0x10) m += "0";
    m += String(h, HEX);

    cevap(m);
    return;
  }

  // ---- KART_KABLO <ad> : tek bir kabloyu temiz test eder ----
  //
  // NEDEN AYRI KOMUT (10 Ekim 2026 - once yanlis yapildi):
  // Ilk denemede KART_PIN'in elle okuma kismi kullanildi. O kod SS'i
  // ASAGI cekiyor; SS asagidayken modul MISO hattini surme hakki
  // kazaniyor ve koprudan gelen sinyalle cekisiyor. Sonuc guvenilmez
  // cikiyordu - saglam bir kabloyu "kopuk" diye isaretledik.
  //
  // Bu komut SS'i YUKARIDA tutar. Modul susar, hat temiz kalir.
  // Kullanim: modulun <ad> bacagi ile MISO bacagi jumperla koprulenir.
  if (k.startsWith("KART_KABLO ")) {
    String ad = k.substring(11);
    ad.trim();
    int pin = -1;
    if      (ad == "SCK")  pin = RFID_SCK;
    else if (ad == "MOSI") pin = RFID_MOSI;
    else if (ad == "SDA" || ad == "SS") pin = RFID_SS;
    else { cevap("HATA|gecersiz|SCK_MOSI_SDA"); return; }

    // SS yukarida kalsin ki modul MISO'yu birakip sussun
    pinMode(RFID_SS, OUTPUT);
    digitalWrite(RFID_SS, HIGH);
    pinMode(pin, OUTPUT);
    // MISO dahili direncle ASAGI cekilir. Kablo kopuksa hat bosta
    // kalmaz, kesin 0 okur - sonuc rastgele degil, net olur.
    pinMode(RFID_MISO, INPUT_PULLDOWN);
    delayMicroseconds(500);

    // Dort kez yuksek-alcak yap, her seferinde MISO'yu oku
    int dogru = 0;
    for (int i = 0; i < 4; i++) {
      digitalWrite(pin, HIGH);
      delayMicroseconds(500);
      if (digitalRead(RFID_MISO) == HIGH) dogru++;
      digitalWrite(pin, LOW);
      delayMicroseconds(500);
      if (digitalRead(RFID_MISO) == LOW)  dogru++;
    }
    digitalWrite(pin, LOW);
    pinMode(RFID_MISO, INPUT);

    // MISO asagi cekili oldugu icin:
    //   8/8 -> kablo saglam
    //   4/8 -> yuksek hic gelmemis, kablo KOPUK
    //   arasi -> temassizlik / kararsiz
    String m = "KART_KABLO|" + ad + "|dogru=" + String(dogru) + "/8|";
    m += (dogru == 8) ? "KABLO_SAGLAM"
                      : (dogru <= 4 ? "KABLO_KOPUK" : "KARARSIZ_temassizlik");
    cevap(m);
    return;
  }

  // ---- KART_DONGU : MOSI-MISO koprulenince geri geliyor mu ----
  if (k == "KART_DONGU") {
    byte a = rcDongu(0xA5);
    byte b = rcDongu(0x5A);
    pinMode(RFID_MISO, INPUT);
    String m = "KART_DONGU|yollanan=0xa5|okunan=0x";
    if (a < 0x10) m += "0";
    m += String(a, HEX);
    m += "|yollanan=0x5a|okunan=0x";
    if (b < 0x10) m += "0";
    m += String(b, HEX);
    m += (a == 0xA5 && b == 0x5A)
         ? "|KABLOLAR_SAGLAM" : "|KOPRU_YOK_ya_da_KABLO_KOPUK";
    cevap(m);
    return;
  }

  // ---- LISTE ----
  if (k == "LISTE") {
    cevap("LISTE|" + String(KANAL_SAYISI) + " kanal");
    for (int i = 0; i < KANAL_SAYISI; i++) {
      Serial.print("  ");
      Serial.print(kanallar[i].ad);
      Serial.print("  ->  D");
      Serial.print(kanallar[i].pin);
      Serial.print("  ");
      Serial.print(kanallar[i].sure);
      Serial.print(" ms");
      Serial.println();
    }
    cevap("LISTE|bitti");
    return;
  }

  // ---- HEPSINI KAPAT ----
  // Acik komut: KALICI kanallar da birakilir (kumanda enerjisi dahil).
  if (k == "HEPSINI_KAPAT") {
    hepsiniKapat(true);
    cevap("OK|HEPSINI_KAPAT");
    return;
  }

  // ---- AC <pin> / KAPAT <pin>  (test) ----
  if (k.startsWith("AC ")) {
    int p = k.substring(3).toInt();
    if (p <= 0) { cevap("HATA|gecersiz_pin"); return; }
    if (kaliciPin >= 0) digitalWrite(kaliciPin, ROLE_PASIF);
    digitalWrite(p, ROLE_PASIF);
    pinMode(p, OUTPUT);
    digitalWrite(p, ROLE_AKTIF);
    kaliciPin = p;
    cevap("OK|D" + String(p) + "_SUREKLI_ACIK|kapatmak: KAPAT "
          + String(p));
    return;
  }
  if (k.startsWith("KAPAT ")) {
    // Once kanal ADI mi diye bak: "KAPAT ANAHTAR_GUC"
    String ad = k.substring(6);
    ad.trim();
    int ki = kanalBul(ad);
    if (ki >= 0) { cevap(kanalBirak(ki)); return; }
    // Degilse sayisal pin: "KAPAT 21"
    int p = ad.toInt();
    if (p <= 0) { cevap("HATA|bilinmeyen_kanal|" + ad); return; }
    digitalWrite(p, ROLE_PASIF);
    if (kaliciPin == p) kaliciPin = -1;
    cevap("OK|D" + String(p) + "_KAPALI");
    return;
  }

  // ---- IPTAL EDILMIS KOMUTLAR ----
  // Arka cam kanallari kaldirildi, pinleri KART E'ye gitti.
  // Eski bir faz3 surumu bu komutlari yollarsa SPI hattina
  // darbe basmasin - burada yakalanip cope atiliyor.
  if (k == "ARKA_SOL_AC"  || k == "ARKA_SOL_KAPAT" ||
      k == "ARKA_SAG_AC"  || k == "ARKA_SAG_KAPAT") {
    cevap("RET|" + k + "|arka_cam_yok|pin_rfid_icin_ayrildi");
    return;
  }

  // KONTAK iptal: arac anahtarsiz + start butonlu, kontak bareli YOK.
  // D21 artik ANAHTAR_GUC. Eski bir faz3 "KONTAK" yollarsa kumanda
  // enerjisine yanlislikla darbe basmasin diye burada yakaliyoruz.
  if (k == "KONTAK") {
    cevap("RET|KONTAK|kontak_bareli_yok|D21_artik_ANAHTAR_GUC");
    return;
  }

  // ---- ARAC KOMUTU ----
  int i = kanalBul(k);
  if (i >= 0) {
    cevap(kanalCalistir(i));
    return;
  }

  cevap("HATA|bilinmeyen_komut|" + k);
}


// ==================== KURULUM ====================
void setup() {
  // GUVENLIK: once ROLE_PASIF, sonra OUTPUT.
  // Ters sirada roleler acilista bir kere "tik" eder.
  // Low level kartta ROLE_PASIF = HIGH oldugu icin bu sira SART:
  // pini once OUTPUT yapip sonra HIGH verirsen arada LOW kalir
  // ve TUM ROLELER bir anlik ceker.
  for (int i = 0; i < KANAL_SAYISI; i++) {
    digitalWrite(kanallar[i].pin, ROLE_PASIF);
    pinMode(kanallar[i].pin, OUTPUT);
    digitalWrite(kanallar[i].pin, ROLE_PASIF);
    kanalAktif[i] = false;
    bitisZamani[i] = 0;
  }

  // ---- ANAHTAR_GUC: BOOT'TA OTOMATIK ACIK ----  (29 Ekim 2026)
  // Arac anahtarsiz; yedek kumandaya SUREKLI 3V gitmeli ki arac
  // "anahtar var" gorsun. Boot'ta tum roleler PASIF basliyor ve bu
  // kanali acan baska bir sey yoktu: reset / guc kesintisi sonrasi
  // anahtar OLU kaliyordu (LED yanmaz, role cekmez). Burada acik
  // baslatiyoruz. KALICI oldugu icin acik kalir; yalnizca KAPI_KILIT /
  // SISTEMI_KAPAT (anahtarKesilebilir ise) kesebilir.
  {
    int _ag = kanalBul("ANAHTAR_GUC");
    if (_ag >= 0) {
      digitalWrite(kanallar[_ag].pin, ROLE_AKTIF);
      kanalAktif[_ag] = true;
      bitisZamani[_ag] = 0;
    }
  }

  pinMode(PIN_KALP, OUTPUT);
  if (EL_FRENI_KONTROLU) pinMode(PIN_EL_FRENI, INPUT_PULLUP);

  // KART D girişleri — pull-up kartta, burada sadece INPUT
  pinMode(PIN_AKU,    INPUT);
  pinMode(PIN_SURUCU, INPUT);
  pinMode(PIN_KAPUT,  INPUT);
  pinMode(PIN_BAGAJ,  INPUT);

  // KART E girişleri — bu pinlerde dahili pull-up VAR, açıyoruz.
  // Kart E takılı değilken ya da kablo koparsa pin yukarıda kalır,
  // kapı "kapalı" okunur. D36'da başımıza gelen sahte "açık" olmaz.
  pinMode(PIN_YOLCU,     INPUT_PULLUP);
  pinMode(PIN_SAG_SURGU, INPUT_PULLUP);
  pinMode(PIN_SOL_SURGU, INPUT_PULLUP);

  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("==========================================");
  Serial.println("  FORD ESP32 - ARAC KONTROL");
  Serial.println("==========================================");
  Serial.print("  Kanal sayisi     : ");
  Serial.println(KANAL_SAYISI);
  Serial.print("  Role tetikleme   : ");
  Serial.println(LOW_LEVEL_ROLE ? "LOW LEVEL (role karti)"
                                : "HIGH LEVEL (LED testi)");
  Serial.print("  El freni kontrolu: ");
  Serial.println(EL_FRENI_KONTROLU ? "ACIK" : "KAPALI");
  Serial.print("  Ayni anda maks   : ");
  Serial.println(MAKS_AYNI_ANDA);
  Serial.print("  Watchdog         : ");
  Serial.print(WATCHDOG_MS / 1000);
  Serial.println(" sn");
  Serial.println();
  // RFID kurulumu SERIAL ACILDIKTAN SONRA yapilir.
  // Once setup()'in basindaydi: kurulum sirasinda takilirsa ESP32
  // hicbir sey yazmadan susuyordu ve ne oldugu anlasilmiyordu.
  // Artik once "araniyor" yaziliyor - nerede durdugu goruluyor.
  Serial.print("  RFID okuyucu     : ");
  Serial.flush();
#if RFID_ESP32
  rfidVar = rfidBaslat();
  Serial.println(rfidVar ? "BULUNDU" : "yok (sistem RFID'siz calisir)");
#else
  // RC522 Pi'de. rfidBaslat() cagrilirsa SPI.begin() D27/D32/D33'u
  // ele gecirir ve kapi girisleri bozulur - cagirmiyoruz.
  rfidVar = false;
  Serial.println("Pi tarafinda (ESP32 pinleri kapi girisi)");
#endif

  // ---- ISI SENSORLERI ----
  kalici.begin("ford", false);

  // ---- KALIBRASYON VE ESIK ----
  ayarlariYukle();
  Serial.print("  Aku carpani      : ");
  Serial.print(akuCarpan, 3);
  Serial.println(akuCarpan == AKU_CARPAN_VARSAYILAN
                 ? "  (varsayilan - araçta kalibre edilmeli)"
                 : "  (kalibre edilmis)");
  Serial.print("  Motor esigi      : ");
  Serial.print(motorVoltEsik, 2);
  Serial.println(" V");

  // ---- DARBE SURELERI ----
  // Panelden ayarlanmis sureler varsa tablodakilerin yerine gecer.
  sureleriYukle();
  Serial.println("  Darbe sureleri   :");
  for (int i = 0; i < KANAL_SAYISI; i++) {
    if (kanallar[i].sure == KALICI) continue;
    if (kanallar[i].sure == varsayilanSure[i]) continue;
    Serial.print("      ");
    Serial.print(kanallar[i].ad);
    Serial.print(" = ");
    Serial.print(kanallar[i].sure);
    Serial.print(" ms  (varsayilan ");
    Serial.print(varsayilanSure[i]);
    Serial.println(")");
  }
  Serial.println("      (yazilmayanlar varsayilan)");

  isiIcAdres = kalici.getString("isiIc", "");
  Serial.print("  Isi sensoru      : ");
  isiTara();
  isiZaman = millis();
  if (isiSayisi == 0) {
    Serial.println(isiCevapVar
      ? "hatta cevap VAR ama okunamadi - yazilim/zamanlama"
      : "yok (hattan hic cevap gelmiyor - kablo/sensor)");
  } else {
    Serial.print(isiSayisi);
    Serial.println(" adet bulundu");
    int _ic = isiIcIndeks(), _dis = isiDisIndeks();
    for (int i = 0; i < isiSayisi; i++) {
      Serial.print("      ");
      Serial.print(isiAdresYazi(isiAdres[i]));
      Serial.print("  -> ");
      Serial.println((i == _ic) ? "IC"
                   : ((i == _dis) ? "DIS" : "kullanilmiyor"));
    }
    if (isiIcAdres.length() != 16)
      Serial.println("      ! IC sensor KAYITLI DEGIL - simdilik ilki IC sayiliyor.");
    if (isiSayisi == 1)
      Serial.println("      ! Tek sensor var, DIS bos kalacak.");
    Serial.println("      Bu sensor IC olsun:  ISI_IC");
    Serial.println("      Ters dustuyse     :  ISI_DEGISTIR");
  }
  Serial.println();
  Serial.println("  ! ARKA CAM kanallari IPTAL. D27/D32/D33 pinleri");
  Serial.println("    KART E kapi girisleri - ROLE BAGLAMAYIN.");
  Serial.println("  ! D15 bos birakildi (acilis/strapping pini).");
  Serial.println("  ! D12 hic kullanilmayacak (acilis pini).");
  Serial.println();
  Serial.println("  LISTE  yazarak tum komutlari gorebilirsin.");
  Serial.println("==========================================");
}


// ==================== ANA DONGU ====================
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (tampon.length() > 0) { komutIsle(tampon); tampon = ""; }
    } else {
      tampon += c;
      if (tampon.length() > 80) tampon = "";
    }
  }

  darbeleriKontrol();
  suruluyorGuncelle();
  kartdFiltreGuncelle();   // KART D titreme filtresi
  rfidKontrol();
  isiGuncelle();

  // WATCHDOG - kalici test sirasinda calismasin
  if (watchdogAktif && kaliciPin < 0
      && (millis() - sonHaber > WATCHDOG_MS)) {
    hepsiniKapat(false);   // KALICI kanallara dokunma - bkz. hepsiniKapat()
    cevap("UYARI|watchdog|Pi_sustu_darbe_cikislari_kapatildi");
    watchdogAktif = false;
  }

  if (millis() - kalpZaman > KALP_MS) {
    kalpZaman = millis();
    kalpDurum = !kalpDurum;
    digitalWrite(PIN_KALP, kalpDurum);
  }
}
