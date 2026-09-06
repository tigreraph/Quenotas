/* Lienzo de notas sincronizado con la reproducción.
   Pieza autocontenida: recibe el JSON de notas, frases y pistas, y no
   depende de nada del resto de la aplicación salvo las fichas y filas de la
   tabla (data-orden), los títulos de frase (data-frase) y el panel de
   detalle (.detalle-nota), que actualiza si existen. */
(() => {
  const contenedor = document.getElementById("lienzo-notas");
  if (!contenedor) return;

  const COLORES = { alta: "#4ec98a", media: "#e0b341", baja: "#e06a5c" };
  const MARGEN_V = 8;
  const MARGEN_IZQ = 44;
  const ANCHO_MIN_NOMBRE = 18;
  const VELOCIDADES = [0.5, 0.75, 1];
  const OPCIONES_ZOOM = [
    { etiqueta: "5 s", segundos: 5 },
    { etiqueta: "10 s", segundos: 10 },
    { etiqueta: "20 s", segundos: 20 },
    { etiqueta: "Todo", segundos: null },
  ];
  const NOMBRES_NOTA = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const ESCALA_SOL = new Set([7, 9, 11, 0, 2, 4, 6]); // G, A, B, C, D, E, F#
  const ETIQUETAS_SIN_TECLADO = new Set(["INPUT", "SELECT", "TEXTAREA", "BUTTON"]);

  const formatoTiempo = (segundos) => {
    const minutos = Math.floor(segundos / 60);
    const resto = (segundos - minutos * 60).toFixed(1).padStart(4, "0");
    return `${minutos}:${resto}`;
  };

  const nombreDeMidi = (midi) => `${NOMBRES_NOTA[((midi % 12) + 12) % 12]}${Math.floor(midi / 12) - 1}`;

  const construir = (datos) => {
    const scroll = document.createElement("div");
    scroll.className = "lienzo-scroll";
    const canvas = document.createElement("canvas");
    scroll.append(canvas);
    const reproductor = document.createElement("audio");
    reproductor.controls = true;
    const pie = document.createElement("div");
    pie.className = "pistas";
    const controles = document.createElement("div");
    controles.className = "controles";
    const etiqueta = document.createElement("span");
    etiqueta.className = "nota-actual";
    contenedor.append(scroll, reproductor, pie, controles, etiqueta);

    const aside = document.querySelector(".detalle-nota");

    // Velocidad sin cambiar el tono: para sacar de oído, escuchar a la mitad
    // es lo que más ayuda. preservesPitch viene activo en los navegadores.
    // Se crea antes que el selector de pista porque el cambio de pista
    // necesita leer velocidad.value para no perder la velocidad elegida.
    const velocidad = document.createElement("select");
    VELOCIDADES.forEach((valor) => {
      const opcion = document.createElement("option");
      opcion.value = valor;
      opcion.textContent = `${valor}x`;
      opcion.selected = valor === 1;
      velocidad.append(opcion);
    });
    velocidad.addEventListener("change", () => {
      reproductor.playbackRate = Number(velocidad.value);
    });
    const etiquetaVelocidad = document.createElement("label");
    etiquetaVelocidad.append(document.createTextNode("Velocidad "), velocidad);
    controles.append(etiquetaVelocidad);

    // Zoom horizontal: cuántos segundos entran en el ancho visible. "Todo"
    // muestra la duración completa. Por defecto 10 s, o Todo si dura menos.
    const zoom = document.createElement("select");
    const indicePorDefecto = datos.duracion_s < 10
      ? OPCIONES_ZOOM.findIndex((o) => o.etiqueta === "Todo")
      : OPCIONES_ZOOM.findIndex((o) => o.etiqueta === "10 s");
    OPCIONES_ZOOM.forEach((opcion, indice) => {
      const el = document.createElement("option");
      el.value = indice;
      el.textContent = opcion.etiqueta;
      el.selected = indice === indicePorDefecto;
      zoom.append(el);
    });
    zoom.addEventListener("change", () => ajustarZoom());
    const etiquetaZoom = document.createElement("label");
    etiquetaZoom.append(document.createTextNode("Zoom "), zoom);
    controles.append(etiquetaZoom);

    // Selector de pista. La posición y la velocidad se restablecen cuando la
    // pista nueva ya cargó su metadata: asignarlas antes de eso se ignora.
    datos.pistas.forEach((pista, indice) => {
      const opcion = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "pista";
      radio.value = pista.url;
      radio.checked = indice === 0;
      radio.addEventListener("change", () => {
        const instante = reproductor.currentTime;
        const sonando = !reproductor.paused;
        reproductor.addEventListener("loadedmetadata", () => {
          reproductor.currentTime = instante;
          reproductor.playbackRate = Number(velocidad.value);
          if (sonando) reproductor.play();
        }, { once: true });
        reproductor.src = pista.url;
      });
      opcion.append(radio, document.createTextNode(" " + pista.etiqueta));
      pie.append(opcion);
    });
    if (datos.pistas.length) reproductor.src = datos.pistas[0].url;

    // Bucle por frase: clic en "Frase N" repite ese tramo; otro clic lo quita.
    let bucle = null;
    const titulosFrase = document.querySelectorAll("h2.frase");
    titulosFrase.forEach((titulo) => {
      titulo.addEventListener("click", () => {
        const frase = datos.frases.find((f) => f.indice === Number(titulo.dataset.frase));
        if (!frase) return;
        const mismo = bucle && bucle.indice === frase.indice;
        bucle = mismo ? null : frase;
        titulosFrase.forEach((t) => t.classList.toggle("en-bucle", t === titulo && !mismo));
        if (bucle) {
          reproductor.currentTime = bucle.inicio_s;
          reproductor.play();
        }
      });
    });
    reproductor.addEventListener("timeupdate", () => {
      if (bucle && reproductor.currentTime >= bucle.fin_s) {
        reproductor.currentTime = bucle.inicio_s;
      }
    });

    const alturas = datos.notas.map((nota) => nota.midi);
    const minimo = alturas.length ? Math.min(...alturas) - 1 : 59;
    const maximo = alturas.length ? Math.max(...alturas) + 1 : 73;
    const fichas = [...document.querySelectorAll(".ficha[data-orden]")];
    const fichaPorOrden = new Map(fichas.map((ficha) => [Number(ficha.dataset.orden), ficha]));
    const filas = [...document.querySelectorAll("table.notas tbody tr[data-orden]")];
    const filaPorOrden = new Map(filas.map((fila) => [Number(fila.dataset.orden), fila]));
    const notaPorOrden = new Map(datos.notas.map((nota) => [nota.orden, nota]));

    // pps (píxeles por segundo) y la altura de fila viven fuera de dibujar()
    // porque el clic en el lienzo necesita las mismas coordenadas que el
    // último dibujo, sin esperar al siguiente cuadro.
    let pps = 40;
    let altoFilaActual = 10;
    const aX = (segundos) => MARGEN_IZQ + segundos * pps;
    const aY = (midi) => MARGEN_V + (maximo - midi) * altoFilaActual;

    const ajustarZoom = () => {
      const opcion = OPCIONES_ZOOM[Number(zoom.value)];
      const segundosVisibles = opcion.segundos == null ? Math.max(datos.duracion_s, 0.001) : opcion.segundos;
      const anchoVisible = scroll.clientWidth || 600;
      pps = anchoVisible / segundosVisibles;
      canvas.style.width = `${MARGEN_IZQ + datos.duracion_s * pps}px`;
      // Al cambiar el zoom, el cursor se mantiene a la vista.
      scroll.scrollLeft = Math.max(0, aX(reproductor.currentTime) - scroll.clientWidth * 0.2);
    };
    ajustarZoom();

    let notaSeleccionada = null;
    let notaPanelActual = null;

    const pintarPanel = (nota) => {
      if (!aside) return;
      if (!nota) {
        aside.innerHTML = '<p class="detalle-vacio">Elige una nota en el gráfico o en la lista</p>';
        return;
      }
      const frase = datos.frases.find(
        (f) => nota.inicio_s >= f.inicio_s - 1e-6 && nota.inicio_s <= f.fin_s + 1e-6
      );
      aside.innerHTML = `
        <p class="detalle-nombre">${nota.nombre}</p>
        <dl>
          <div><dt>Frase</dt><dd>${frase ? frase.indice : "?"} · nota ${nota.orden}</dd></div>
          <div><dt>Inicio</dt><dd>${formatoTiempo(datos.desplazamiento_s + nota.inicio_s)}</dd></div>
          <div><dt>Duración</dt><dd>${nota.duracion_s.toFixed(2)} s</dd></div>
          <div><dt>Confianza</dt><dd>${nota.etiqueta} · ${nota.confianza.toFixed(2)}</dd></div>
          <div><dt>Desvío</dt><dd>${nota.cents > 0 ? "+" : ""}${nota.cents} cents</dd></div>
        </dl>
      `;
    };

    const seleccionar = (nota) => {
      notaSeleccionada = nota;
      fichas.forEach((f) => f.classList.toggle("seleccionada", Number(f.dataset.orden) === nota.orden));
      filas.forEach((f) => f.classList.toggle("seleccionada", Number(f.dataset.orden) === nota.orden));
      // Salta al inicio de la nota sin arrancar la reproducción si estaba en pausa.
      reproductor.currentTime = nota.inicio_s;
    };

    fichas.forEach((ficha) => {
      ficha.addEventListener("click", () => {
        const nota = notaPorOrden.get(Number(ficha.dataset.orden));
        if (nota) seleccionar(nota);
      });
    });

    const dibujar = () => {
      const escala = window.devicePixelRatio || 1;
      const anchoCss = canvas.clientWidth;
      const altoCss = canvas.clientHeight;
      canvas.width = anchoCss * escala;
      canvas.height = altoCss * escala;
      const pincel = canvas.getContext("2d");
      pincel.setTransform(escala, 0, 0, escala, 0, 0);
      pincel.clearRect(0, 0, anchoCss, altoCss);

      altoFilaActual = (altoCss - MARGEN_V * 2) / (maximo - minimo + 1);

      for (let midi = minimo; midi <= maximo; midi += 1) {
        const y = aY(midi);
        const clase = ((midi % 12) + 12) % 12;
        if (ESCALA_SOL.has(clase)) {
          pincel.fillStyle = "#242832";
          pincel.fillRect(0, y, anchoCss, altoFilaActual);
        }
        pincel.fillStyle = "#9aa0ab";
        pincel.font = "11px ui-monospace, monospace";
        pincel.textBaseline = "middle";
        pincel.fillText(nombreDeMidi(midi), 4, y + altoFilaActual / 2);
      }

      pincel.strokeStyle = "#2a2e37";
      pincel.lineWidth = 1;
      for (let midi = minimo; midi <= maximo; midi += 1) {
        const y = aY(midi) + altoFilaActual;
        pincel.beginPath();
        pincel.moveTo(0, y);
        pincel.lineTo(anchoCss, y);
        pincel.stroke();
      }
      pincel.beginPath();
      pincel.moveTo(MARGEN_IZQ, 0);
      pincel.lineTo(MARGEN_IZQ, altoCss);
      pincel.stroke();

      if (bucle) {
        pincel.fillStyle = "rgba(111, 180, 255, 0.10)";
        pincel.fillRect(aX(bucle.inicio_s), 0, (bucle.fin_s - bucle.inicio_s) * pps, altoCss);
      }

      const actual = datos.notas.find(
        (nota) =>
          reproductor.currentTime >= nota.inicio_s &&
          reproductor.currentTime < nota.inicio_s + nota.duracion_s
      );

      datos.notas.forEach((nota) => {
        const x = aX(nota.inicio_s);
        const y = aY(nota.midi);
        const ancho = Math.max(2, nota.duracion_s * pps);
        const alto = Math.max(3, altoFilaActual - 2);
        pincel.fillStyle = COLORES[nota.etiqueta] || COLORES.baja;
        pincel.globalAlpha = nota === actual || nota === notaSeleccionada ? 1 : 0.65;
        pincel.fillRect(x, y, ancho, alto);
        if (nota === notaSeleccionada) {
          pincel.globalAlpha = 1;
          pincel.strokeStyle = "#e6e8ec";
          pincel.lineWidth = 2;
          pincel.strokeRect(x + 1, y + 1, Math.max(0, ancho - 2), Math.max(0, alto - 2));
        }
        if (ancho >= ANCHO_MIN_NOMBRE) {
          pincel.globalAlpha = 1;
          pincel.fillStyle = "#14161a";
          pincel.font = "11px ui-monospace, monospace";
          pincel.textBaseline = "middle";
          pincel.fillText(nota.nombre, x + 3, y + alto / 2);
        }
      });
      pincel.globalAlpha = 1;

      const x = aX(reproductor.currentTime);
      pincel.strokeStyle = "#e6e8ec";
      pincel.beginPath();
      pincel.moveTo(x, 0);
      pincel.lineTo(x, altoCss);
      pincel.stroke();

      etiqueta.textContent = actual
        ? `${formatoTiempo(datos.desplazamiento_s + reproductor.currentTime)}  ·  ${actual.nombre}`
        : formatoTiempo(datos.desplazamiento_s + reproductor.currentTime);

      fichas.forEach((ficha) => ficha.classList.remove("sonando"));
      filas.forEach((fila) => fila.classList.remove("sonando"));
      if (actual) {
        const ficha = fichaPorOrden.get(actual.orden);
        if (ficha) ficha.classList.add("sonando");
        const fila = filaPorOrden.get(actual.orden);
        if (fila) fila.classList.add("sonando");
      }

      // El panel muestra la nota seleccionada en pausa, y la que suena
      // durante la reproducción; si no suena ninguna, mantiene la última.
      const notaParaPanel = reproductor.paused ? notaSeleccionada : (actual || notaPanelActual);
      if (notaParaPanel !== notaPanelActual) {
        pintarPanel(notaParaPanel);
        notaPanelActual = notaParaPanel;
      }

      // La vista sigue al cursor durante la reproducción: si sale de lo
      // visible, se desplaza para dejarlo al 20 % del ancho visible.
      if (!reproductor.paused) {
        const visibleIzq = scroll.scrollLeft;
        const visibleDer = visibleIzq + scroll.clientWidth;
        if (x < visibleIzq || x > visibleDer) {
          scroll.scrollLeft = Math.max(0, x - scroll.clientWidth * 0.2);
        }
      }

      requestAnimationFrame(dibujar);
    };

    canvas.addEventListener("click", (evento) => {
      const caja = canvas.getBoundingClientRect();
      const localX = evento.clientX - caja.left;
      const localY = evento.clientY - caja.top;
      if (localX < MARGEN_IZQ) return; // zona de nombres de carril, no hace nada
      const notaClicada = [...datos.notas].reverse().find((nota) => {
        const x = aX(nota.inicio_s);
        const ancho = Math.max(2, nota.duracion_s * pps);
        const y = aY(nota.midi);
        const alto = Math.max(3, altoFilaActual - 2);
        return localX >= x && localX <= x + ancho && localY >= y && localY <= y + alto;
      });
      if (notaClicada) {
        seleccionar(notaClicada);
        return;
      }
      const segundos = (localX - MARGEN_IZQ) / pps;
      reproductor.currentTime = Math.max(0, Math.min(datos.duracion_s, segundos));
    });

    document.addEventListener("keydown", (evento) => {
      const activo = document.activeElement;
      if (activo && ETIQUETAS_SIN_TECLADO.has(activo.tagName)) return;
      if (evento.code === "Space") {
        evento.preventDefault();
        if (reproductor.paused) reproductor.play(); else reproductor.pause();
      } else if (evento.code === "ArrowLeft") {
        evento.preventDefault();
        reproductor.currentTime = Math.max(0, reproductor.currentTime - 2);
      } else if (evento.code === "ArrowRight") {
        evento.preventDefault();
        reproductor.currentTime = Math.min(datos.duracion_s, reproductor.currentTime + 2);
      }
    });

    requestAnimationFrame(dibujar);
  };

  fetch(contenedor.dataset.datos)
    .then((respuesta) => respuesta.json())
    .then(construir)
    .catch(() => {
      contenedor.textContent = "No se pudieron cargar las notas para el lienzo.";
    });
})();
