// A versão muda quando se publica HTML, CSS ou JavaScript. Os ficheiros são
// servidos primeiro da cache, por isso sem mudar este nome a app instalada no
// telemóvel continuava a usar o CSS e o HTML antigos.
const CACHE = "sinal-estatico-v8";
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

// ——— Notificações ———
// O pipeline manda {titulo, corpo, endereco}, já cifrado pelo serviço de push.
// Quem chega aqui é só o browser, por isso o texto mostra-se como veio: uma
// notificação é sempre texto simples, nunca HTML.
self.addEventListener("push", (evento) => {
  let mensagem = {};
  try {
    mensagem = evento.data ? evento.data.json() : {};
  } catch {
    // Uma mensagem estragada ainda tem de dar notificação: o Chrome castiga
    // o site que recebe um push e não mostra nada.
  }
  // O endereço vem relativo e resolve-se contra a pasta do site. Assim um
  // valor estranho nunca abre outro domínio.
  const destino = new URL(mensagem.endereco || "./#/", self.registration.scope);
  const endereco = destino.origin === self.location.origin ? destino.href : self.registration.scope;

  evento.waitUntil(
    self.registration.showNotification(mensagem.titulo || "Sinal", {
      body: mensagem.corpo || "Há coisas novas Para ti.",
      icon: "icone.svg",
      // A mesma etiqueta faz o resumo de hoje substituir o de ontem, em vez
      // de se irem acumulando na gaveta.
      tag: "sinal-resumo",
      renotify: true,
      data: { endereco }
    })
  );
});

self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();
  const endereco = evento.notification.data?.endereco || self.registration.scope;
  evento.waitUntil((async () => {
    // Se o Sinal já está aberto, reaproveita-se esse separador em vez de
    // abrir outro por cima.
    const janelas = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const janela of janelas) {
      if (janela.url.startsWith(self.registration.scope) && "focus" in janela) {
        // Primeiro o foco: o browser só o deixa dar enquanto o toque é
        // recente, e esperar pela navegação podia passar desse prazo.
        await janela.focus();
        return janela.navigate(endereco).catch(() => {});
      }
    }
    return self.clients.openWindow(endereco);
  })());
});
