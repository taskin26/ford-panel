(function(){
  if(window.__mp3Arac) return; window.__mp3Arac=1;
  var BT = (location.protocol === 'file:');   // file:// => Bluetooth/gömülü (yükleme kapalı)

  // Stil (bir kez)
  var st=document.createElement('style');
  st.textContent=''
   +'.mp3-arac{margin-top:14px;border-top:1px solid rgba(255,255,255,.08);padding-top:12px;}'
   +'.mp3-ac{width:100%;border:0;border-radius:12px;padding:13px;font-size:15px;font-weight:700;'
   +'color:#fff;background:linear-gradient(180deg,#9c27b0,#7b1fa2);cursor:pointer;}'
   +'.mp3-govde{margin-top:12px;}'
   +'.mp3-satir{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}'
   +'.mp3-btn{border:0;border-radius:10px;padding:11px 14px;font-size:14px;font-weight:600;color:#fff;cursor:pointer;}'
   +'.mp3-btn.mor{background:#8e24aa;} .mp3-btn.yesil{background:#2e7d32;} .mp3-btn[disabled]{opacity:.45;}'
   +'.mp3-secad{flex:1;min-width:110px;font-size:12.5px;color:#9fc0e4;}'
   +'.mp3-bar{height:7px;border-radius:5px;background:#0a2037;overflow:hidden;margin-top:10px;display:none;}'
   +'.mp3-bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7b1fa2,#e040fb);}'
   +'.mp3-uyari{font-size:12px;color:#ffcc80;background:#3a2a10;border:1px solid #5a4015;'
   +'padding:8px 10px;border-radius:9px;margin-top:10px;}'
   +'.mp3-liste{margin-top:12px;max-height:46vh;overflow-y:auto;-webkit-overflow-scrolling:touch;'
   +'padding-right:2px;}'
   +'.mp3-it{display:flex;align-items:center;gap:10px;padding:10px;border-radius:10px;'
   +'background:rgba(255,255,255,.05);margin-bottom:7px;}'
   +'.mp3-it .ad{flex:1;min-width:0;}'
   +'.mp3-it .ad .t{font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}'
   +'.mp3-it .ad .b{font-size:11px;color:#9fc0e4;margin-top:2px;}'
   +'.mp3-it .sil{border:0;background:#2a1414;color:#ff8a80;border-radius:8px;padding:8px 12px;font-size:13px;font-weight:600;cursor:pointer;}'
   +'.mp3-bos{color:#9fc0e4;font-size:12.5px;text-align:center;padding:14px 0;}';
  document.head.appendChild(st);

  function boyut(b){ if(b>=1048576)return (b/1048576).toFixed(1)+' MB';
    if(b>=1024)return (b/1024).toFixed(0)+' KB'; return b+' B'; }
  function kac(s){return (s||'').replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}

  function kur(inner){
    if(inner.querySelector('#mp3Arac')) return;
    var d=document.createElement('div');
    d.className='mp3-arac'; d.id='mp3Arac';
    d.innerHTML=''
     +'<button class="mp3-ac" id="mp3Ac">📁 MP3 Yükle / Sil</button>'
     +'<div class="mp3-govde" id="mp3Govde" style="display:none">'
     +  '<div class="mp3-satir">'
     +    '<button class="mp3-btn mor" id="mp3Sec">＋ Dosya Seç</button>'
     +    '<span class="mp3-secad" id="mp3Secad">Dosya seçilmedi</span>'
     +    '<button class="mp3-btn yesil" id="mp3Gonder" disabled>Yükle</button>'
     +    '<input type="file" id="mp3Dosya" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" multiple style="display:none">'
     +  '</div>'
     +  '<div class="mp3-bar" id="mp3Bar"><i></i></div>'
     +  '<div class="mp3-uyari" id="mp3Uyari" style="display:none">Bu modda (Bluetooth) yükleme kapalı — yüklemek için <b>WiFi ile Bağlan</b>. Silme çalışır.</div>'
     +  '<div class="mp3-liste" id="mp3Liste"></div>'
     +'</div>';
    inner.appendChild(d);

    var ac=d.querySelector('#mp3Ac'), govde=d.querySelector('#mp3Govde');
    var sec=d.querySelector('#mp3Sec'), dosya=d.querySelector('#mp3Dosya');
    var secad=d.querySelector('#mp3Secad'), gonder=d.querySelector('#mp3Gonder');
    var bar=d.querySelector('#mp3Bar'), liste=d.querySelector('#mp3Liste');
    if(BT){ gonder.disabled=true; sec.disabled=true; d.querySelector('#mp3Uyari').style.display='block'; }

    ac.onclick=function(){
      var g=(govde.style.display==='none');
      govde.style.display=g?'block':'none';
      if(g) listele();
    };
    sec.onclick=function(){ if(!BT) dosya.click(); };
    dosya.onchange=function(){
      secad.textContent=dosya.files.length?(dosya.files.length+' dosya seçildi'):'Dosya seçilmedi';
      gonder.disabled=(BT||dosya.files.length===0);
    };
    gonder.onclick=function(){
      if(BT||!dosya.files.length) return;
      var fd=new FormData();
      for(var i=0;i<dosya.files.length;i++) fd.append('dosya',dosya.files[i]);
      bar.style.display='block'; bar.firstChild.style.width='0%'; gonder.disabled=true;
      var x=new XMLHttpRequest(); x.open('POST','/api/muzik/yukle');
      x.upload.onprogress=function(e){ if(e.lengthComputable)
        bar.firstChild.style.width=Math.round(e.loaded/e.total*100)+'%'; };
      x.onload=function(){ bar.style.display='none';
        var r={}; try{r=JSON.parse(x.responseText);}catch(e){}
        if(r.ok){ dosya.value=''; secad.textContent='Dosya seçilmedi'; listele(); }
        else alert('Yükleme hatası: '+(r.hata||x.status));
        gonder.disabled=(BT||dosya.files.length===0); };
      x.onerror=function(){ bar.style.display='none'; alert('Yükleme başarısız.');
        gonder.disabled=(BT||dosya.files.length===0); };
      x.send(fd);
    };

    function sil(ad){
      if(!confirm('"'+ad+'" silinsin mi?')) return;
      fetch('/api/muzik/sil',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ad:ad})}).then(function(r){return r.json();})
        .then(function(r){ if(r.ok) listele(); else alert('Silinemedi: '+(r.hata||'')); })
        .catch(function(){ alert('Silme başarısız.'); });
    }
    function listele(){
      liste.innerHTML='<div class="mp3-bos">Yükleniyor…</div>';
      fetch('/api/muzik/liste').then(function(r){return r.json();}).then(function(r){
        var d2=(r&&r.dosyalar)||[]; liste.innerHTML='';
        if(!d2.length){ liste.innerHTML='<div class="mp3-bos">Hiç müzik yok.</div>'; return; }
        d2.forEach(function(it){
          var row=document.createElement('div'); row.className='mp3-it';
          row.innerHTML='<span>🎵</span><div class="ad"><div class="t">'+kac(it.ad)+
            '</div><div class="b">'+boyut(it.boyut||0)+'</div></div>'+
            '<button class="sil">Sil</button>';
          row.querySelector('.sil').onclick=function(){ sil(it.ad); };
          liste.appendChild(row);
        });
      }).catch(function(){ liste.innerHTML='<div class="mp3-bos">Liste alınamadı — bağlantı?</div>'; });
    }
  }

  // #overlay-music .music-app-inner gelene kadar birkaç kez dene
  var say=0;
  var t=setInterval(function(){
    say++;
    var inner=document.querySelector('#overlay-music .music-app-inner');
    if(inner){ kur(inner); clearInterval(t); }
    if(say>40) clearInterval(t);
  },300);
})();
