const CACHE = "sinal-estatico-v4";
const FICHEIROS_ESTATICOS = [
  "./",
  "./index.html",
  "./estilo.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icone.svg"
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(FICHEIROS_ESTATICOS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((nomes) => Promise.all(
      nomes
        .filter((nome) => nome !== CACHE)
        .map((nome) => caches.delete(nome))
    ))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (evento) => {
  if (evento.request.method !== "GET") return;

  const pedido = new URL(evento.request.url);
  if (pedido.pathname.endsWith("/dados/itens.json")) {
    // Os dados mudam todos os dias: tenta sempre a recolha nova e usa a
    // cópia anterior só quando o telemóvel estiver sem rede.
    evento.respondWith(
      fetch(evento.request)
        .then((resposta) => {
          const copia = resposta.clone();
          caches.open(CACHE).then((cache) => cache.put(evento.request, copia));
          return resposta;
        })
        .catch(() => caches.match(evento.request))
    );
    return;
  }

  evento.respondWith(
    caches.match(evento.request).then((guardado) => guardado || fetch(evento.request))
  );
});
