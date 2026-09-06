/* Forma de onda de la canción con dos manijas para marcar una frase.
   Pieza autocontenida: recibe URLs y el token CSRF por data-*, y todo lo
   demás por JSON. Nunca lee flotantes de la plantilla. */
(() => {
  const raiz = document.getElementById("onda");
  if (!raiz) return;

  const urls = raiz.dataset;
  const canvas = raiz.querySelector("canvas");
  const manijas = {
    inicio: raiz.querySelector(".manija-inicio"),
    fin: raiz.querySelector(".manija-fin"),
  };
  const campos = {
    inicio: raiz.querySelector("input[name=inicio]"),
    fin: raiz.querySelector("input[name=fin]"),
  };
  const duracionSeleccion = raiz.querySelector(".duracion-seleccion");
  const botonEscuchar = raiz.querySelector("button.escuchar");
  const botonAnalizar = raiz.querySelector("button.analizar");
  const casillaSeparar = raiz.querySelector("input[name=separar]");
  const aviso = raiz.querySelector(".aviso-seleccion");
  const reproductor = raiz.querySelector("audio");
  const lista = document.getElementById("frases");

  const COLORES = {
    onda: "#3a4252", ondaSeleccion: "#6fb4ff", fondoSeleccion: "rgba(111, 180, 255, 0.12)",
    fondoAviso: "rgba(224, 106, 92, 0.18)", cursor: "#e6e8ec",
    listo: "rgba(78, 201, 138, 0.28)", procesando: "rgba(224, 179, 65, 0.28)", error: "rgba(224, 106, 92, 0.28)",
  };
  const MINIMO_S = 1;

  let picos = [];
  let duracion = 0;
  let maximo = 180;
  let frases = [];
  let seleccion = { inicio: 0, fin: 0 };
  let escuchando = false;
  let temporizador = null;
  let dibujoPendiente = false;
  let sondeando = false;

  const formatoTiempo = (segundos) => {
    const decimas = Math.round(Math.max(0, segundos) * 10);
    const minutos = Math.floor(decimas / 600);
    const resto = decimas - minutos * 600;
    return `${minutos}:${String(Math.floor(resto / 10)).padStart(2, "0")}.${resto % 10}`;
  };

  const parsearTiempo = (texto) => {
    const limpio = String(texto).trim();
    const partes = limpio.match(/^(?:(\d+):)?(\d+(?:\.\d+)?)$/);
    if (!partes) return NaN;
    const minutos = partes[1] ? Number(partes[1]) : 0;
    const segundos = Number(partes[2]);
    if (partes[1] && segundos >= 60) return NaN;
    return minutos * 60 + segundos;
  };

  const limitar = (valor, minimo, maximoValor) => Math.min(Math.max(valor, minimo), maximoValor);

  const aX = (segundos) => (duracion ? (segundos / duracion) * canvas.clientWidth : 0);
  const aSegundos = (x) => (canvas.clientWidth ? (x / canvas.clientWidth) * duracion : 0);

  const validar = () => {
    const largo = seleccion.fin - seleccion.inicio;
    let problema = "";
    if (largo < MINIMO_S) problema = "La selección debe durar al menos 1 segundo.";
    else if (largo > maximo) problema = `La selección dura ${formatoTiempo(largo)} y el máximo es ${formatoTiempo(maximo)}. Acércala: una canción entera se saca por frases.`;
    aviso.textContent = problema;
    botonAnalizar.disabled = Boolean(problema);
    duracionSeleccion.textContent = `(${formatoTiempo(largo)})`;
    return !problema;
  };

  const colocarManijas = () => {
    manijas.inicio.style.left = `${aX(seleccion.inicio)}px`;
    manijas.fin.style.left = `${aX(seleccion.fin)}px`;
    campos.inicio.value = formatoTiempo(seleccion.inicio);
    campos.fin.value = formatoTiempo(seleccion.fin);
  };

  const dibujar = () => {
    const escala = window.devicePixelRatio || 1;
    const ancho = canvas.clientWidth;
    const alto = canvas.clientHeight;
    canvas.width = ancho * escala;
    canvas.height = alto * escala;
    const pincel = canvas.getContext("2d");
    pincel.setTransform(escala, 0, 0, escala, 0, 0);
    pincel.clearRect(0, 0, ancho, alto);

    frases.forEach((frase) => {
      const color = COLORES[frase.estado] || COLORES.procesando;
      pincel.fillStyle = frase.estado === "listo" ? COLORES.listo : color;
      pincel.fillRect(aX(frase.inicio_s), 0, Math.max(2, aX(frase.fin_s) - aX(frase.inicio_s)), alto);
    });

    const largo = seleccion.fin - seleccion.inicio;
    pincel.fillStyle = largo > maximo || largo < MINIMO_S ? COLORES.fondoAviso : COLORES.fondoSeleccion;
    pincel.fillRect(aX(seleccion.inicio), 0, Math.max(1, aX(seleccion.fin) - aX(seleccion.inicio)), alto);

    const mitad = alto / 2;
    const anchoColumna = ancho / Math.max(1, picos.length);
    picos.forEach((pico, indice) => {
      const x = indice * anchoColumna;
      const segundos = aSegundos(x);
      pincel.fillStyle = segundos >= seleccion.inicio && segundos <= seleccion.fin ? COLORES.ondaSeleccion : COLORES.onda;
      const altura = Math.max(1, pico * (alto - 8));
      pincel.fillRect(x, mitad - altura / 2, Math.max(1, anchoColumna - 0.5), altura);
    });

    const x = aX(reproductor.currentTime);
    pincel.strokeStyle = COLORES.cursor;
    pincel.beginPath();
    pincel.moveTo(x, 0);
    pincel.lineTo(x, alto);
    pincel.stroke();

    if (!reproductor.paused || arrastrando) requestAnimationFrame(dibujar);
  };

  const programarDibujo = () => {
    if (dibujoPendiente) return;
    dibujoPendiente = true;
    requestAnimationFrame(() => {
      dibujoPendiente = false;
      dibujar();
    });
  };

  const fijarSeleccion = (inicio, fin) => {
    seleccion = { inicio: limitar(inicio, 0, duracion), fin: limitar(fin, 0, duracion) };
    if (seleccion.inicio > seleccion.fin) seleccion = { inicio: seleccion.fin, fin: seleccion.inicio };
    colocarManijas();
    validar();
    programarDibujo();
  };

  // Manijas: eventos de puntero, así funcionan con el ratón y con el dedo.
  let arrastrando = null;
  Object.entries(manijas).forEach(([nombre, manija]) => {
    manija.addEventListener("pointerdown", (evento) => {
      manija.setPointerCapture(evento.pointerId);
      manija.classList.add("activa");
      arrastrando = nombre;
    });
    manija.addEventListener("pointermove", (evento) => {
      if (!manija.classList.contains("activa") || !arrastrando) return;
      const caja = canvas.getBoundingClientRect();
      const segundos = aSegundos(limitar(evento.clientX - caja.left, 0, caja.width));
      const otro = arrastrando === "inicio" ? seleccion.fin : seleccion.inicio;
      // Si el borde arrastrado cruza al otro, pasa a ser el otro borde.
      if (arrastrando === "inicio" && segundos > otro) arrastrando = "fin";
      else if (arrastrando === "fin" && segundos < otro) arrastrando = "inicio";
      fijarSeleccion(Math.min(segundos, otro), Math.max(segundos, otro));
      programarDibujo();
    });
    const soltar = () => { manija.classList.remove("activa"); arrastrando = null; };
    manija.addEventListener("pointerup", soltar);
    manija.addEventListener("pointercancel", soltar);
  });

  Object.entries(campos).forEach(([nombre, campo]) => {
    campo.addEventListener("change", () => {
      const segundos = parsearTiempo(campo.value);
      if (Number.isNaN(segundos)) { colocarManijas(); return; }
      if (nombre === "inicio") fijarSeleccion(segundos, seleccion.fin);
      else fijarSeleccion(seleccion.inicio, segundos);
    });
  });

  // Clic en la onda: sobre una frase hecha la abre; si no, mueve el cursor.
  canvas.addEventListener("click", (evento) => {
    const caja = canvas.getBoundingClientRect();
    const segundos = aSegundos(evento.clientX - caja.left);
    const frase = frases.find((f) => f.estado === "listo" && segundos >= f.inicio_s && segundos <= f.fin_s);
    if (frase) { window.location.href = frase.url; return; }
    reproductor.currentTime = segundos;
  });

  botonEscuchar.addEventListener("click", () => {
    if (escuchando) { reproductor.pause(); return; }
    reproductor.currentTime = seleccion.inicio;
    escuchando = true;
    botonEscuchar.textContent = "Parar";
    reproductor.play();
  });
  reproductor.addEventListener("timeupdate", () => {
    if (escuchando && reproductor.currentTime >= seleccion.fin) reproductor.pause();
    programarDibujo();
  });
  const restaurarBotonEscuchar = () => {
    escuchando = false;
    botonEscuchar.textContent = "Escuchar la selección";
  };
  reproductor.addEventListener("pause", restaurarBotonEscuchar);
  reproductor.addEventListener("ended", restaurarBotonEscuchar);
  reproductor.addEventListener("play", () => programarDibujo());
  reproductor.addEventListener("seeked", () => programarDibujo());

  const pintarLista = () => {
    lista.innerHTML = "";
    if (!frases.length) {
      const vacio = document.createElement("li");
      vacio.className = "vacio";
      vacio.textContent = "Todavía no marcaste ninguna frase.";
      lista.append(vacio);
      programarDibujo();
      return;
    }
    frases.forEach((frase) => {
      const item = document.createElement("li");
      item.dataset.id = frase.id;
      const enlace = document.createElement("a");
      enlace.href = frase.url;
      enlace.textContent = `${formatoTiempo(frase.inicio_s)} a ${formatoTiempo(frase.fin_s)}`;
      const estado = document.createElement("span");
      estado.className = `estado estado-${frase.estado}`;
      estado.textContent = frase.estado === "procesando" ? (frase.paso || "Analizando") : frase.etiqueta;
      item.append(enlace, document.createTextNode(" "), estado);
      if (frase.estado === "error" && frase.mensaje) {
        const mensaje = document.createElement("span");
        mensaje.className = "mensaje-error";
        mensaje.textContent = ` · ${frase.mensaje}`;
        item.append(mensaje);
      }
      if (frase.estado === "error") {
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "reintentar";
        boton.textContent = "Reintentar";
        boton.addEventListener("click", async () => {
          await fetch(frase.reintentar, { method: "POST", headers: { "X-CSRFToken": urls.csrf } });
          await refrescarFrases();
        });
        item.append(boton);
      }
      lista.append(item);
    });
    programarDibujo();
  };

  const hayFrasesEnCurso = () =>
    frases.some((f) => f.estado === "procesando" || f.estado === "pendiente");

  const refrescarFrases = async () => {
    if (sondeando) return;
    sondeando = true;
    clearTimeout(temporizador);
    try {
      const respuesta = await fetch(urls.estado, { cache: "no-store" });
      const datos = await respuesta.json();
      frases = datos.frases;
      pintarLista();
    } catch (error) {
      // Un corte de red (el teléfono perdiendo el wifi un momento) no debe
      // parar el sondeo: se conserva la lista anterior y se reintenta.
    } finally {
      sondeando = false;
      if (hayFrasesEnCurso()) temporizador = setTimeout(refrescarFrases, 3000);
    }
  };

  botonAnalizar.addEventListener("click", async () => {
    if (!validar()) return;
    botonAnalizar.disabled = true;
    const cuerpo = new FormData();
    cuerpo.append("inicio_s", String(seleccion.inicio));
    cuerpo.append("fin_s", String(seleccion.fin));
    cuerpo.append("separar", casillaSeparar.checked ? "true" : "false");
    const respuesta = await fetch(urls.crear, {
      method: "POST", body: cuerpo, headers: { "X-CSRFToken": urls.csrf },
    });
    if (!respuesta.ok) {
      const datos = await respuesta.json().catch(() => ({}));
      aviso.textContent = datos.error || "No se pudo crear la frase.";
      botonAnalizar.disabled = false;
      return;
    }
    aviso.textContent = "";
    botonAnalizar.disabled = false;
    await refrescarFrases();
  });

  const arrancar = async () => {
    const estado = await (await fetch(urls.estado, { cache: "no-store" })).json();
    const onda = await (await fetch(urls.onda, { cache: "no-store" })).json();
    duracion = onda.duracion_s || estado.duracion_s || 0;
    maximo = estado.max_fragmento_s || 180;
    picos = onda.picos || [];
    frases = estado.frases || [];
    reproductor.src = urls.escucha;
    fijarSeleccion(0, Math.min(duracion, 30));
    pintarLista();
    if (hayFrasesEnCurso()) temporizador = setTimeout(refrescarFrases, 3000);
    window.addEventListener("resize", () => {
      colocarManijas();
      programarDibujo();
    });
    programarDibujo();
  };

  arrancar().catch(() => {
    aviso.textContent = "No se pudo cargar la forma de onda.";
  });
})();
