/* 地図の本体とデータをキャッシュして、電波が弱い場所でも開けるようにする。
   記録API（/api/）は常にネットワークを見る。

   キャッシュは2つに分けてある。
     SHELL … アプリ本体（HTML・spots.js・Leaflet・フォント）。数が知れているので全部持つ
     TILES … 地図タイル。際限なく増えるので TILE_MAX 枚で打ち切る

   タイルは <img> から no-cors で取られるので response.ok が false（type:'opaque'）になる。
   ここを見落とすと1枚もキャッシュされず、圏外で真っ白な地図になる。 */
const SHELL_CACHE = 'odekake-map-v2';
const TILE_CACHE = 'odekake-tiles-v1';
const TILE_MAX = 600;

const SHELL = ['./', './index.html', './spots.js', './manifest.webmanifest', './icon-192.png', './icon-512.png'];
/* 外部だが本体扱い。落ちてもインストールは通す */
const VENDOR = [
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'
];
const VENDOR_HOSTS = ['cdnjs.cloudflare.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];
const isTile = url => url.hostname.endsWith('cartocdn.com');
const isVendor = url => VENDOR_HOSTS.includes(url.hostname);
const keepable = res => res && (res.ok || res.type === 'opaque');

self.addEventListener('install', e=>{
  e.waitUntil((async ()=>{
    const c = await caches.open(SHELL_CACHE);
    await c.addAll(SHELL);
    await Promise.all(VENDOR.map(u => c.add(u).catch(()=>{})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e=>{
  e.waitUntil((async ()=>{
    const keep = [SHELL_CACHE, TILE_CACHE];
    const ks = await caches.keys();
    await Promise.all(ks.filter(k => !keep.includes(k)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

/* 古いものから捨てる。Cache.keys() は入れた順に返る */
async function putTile(req, res){
  const c = await caches.open(TILE_CACHE);
  await c.put(req, res);
  const ks = await c.keys();
  if(ks.length > TILE_MAX){
    await Promise.all(ks.slice(0, ks.length - TILE_MAX).map(k => c.delete(k)));
  }
}

async function cacheFirst(req, cacheName, onMiss){
  const hit = await caches.match(req);
  if(hit){
    /* 裏で更新しておく。失敗しても黙って古いまま使う */
    fetch(req).then(res=>{ if(keepable(res)) onMiss ? onMiss(req, res.clone()) : caches.open(cacheName).then(c=>c.put(req,res.clone())); }).catch(()=>{});
    return hit;
  }
  const res = await fetch(req);
  if(keepable(res)){
    const copy = res.clone();
    onMiss ? await onMiss(req, copy) : (await caches.open(cacheName)).put(req, copy);
  }
  return res;
}

self.addEventListener('fetch', e=>{
  const req = e.request;
  const url = new URL(req.url);
  if(req.method !== 'GET') return;
  if(url.origin === location.origin && url.pathname.startsWith('/api/')) return;  // 記録は常に最新を

  /* HTMLはネットワーク優先。そうしないとデプロイしても古い画面が出続ける */
  if(req.mode === 'navigate'){
    e.respondWith((async ()=>{
      try{
        const res = await fetch(req);
        if(res.ok) (await caches.open(SHELL_CACHE)).put(req, res.clone());
        return res;
      }catch(err){
        return (await caches.match(req)) || (await caches.match('./index.html')) || Response.error();
      }
    })());
    return;
  }

  if(url.origin === location.origin || isVendor(url)){
    e.respondWith(cacheFirst(req, SHELL_CACHE).catch(async ()=> (await caches.match(req)) || Response.error()));
    return;
  }

  if(isTile(url)){
    e.respondWith(cacheFirst(req, TILE_CACHE, putTile).catch(async ()=> (await caches.match(req)) || Response.error()));
  }
  /* それ以外（Googleマップへのリンク先など）は素通し */
});
