/* Lienzo de notas sincronizado con la reproducción.
   Pieza autocontenida: recibe el JSON de notas, frases y pistas, y no
   depende de nada del resto de la aplicación salvo las filas de la tabla
   (data-orden) y los títulos de frase (data-frase), que resalta si existen. */
(() => {
  const contenedor = document.getElementById("lienzo-notas");
  if (!contenedor) return;

  const COLORES = { alta: "#4ec98a", media: "#e0b341", baja: "#e06a5c" };
  const MARGEN = 8;
  const VELOCIDADES = [0.5, 0.75, 1];

  const formatoTiempo = (segundos) => {
    const minutos = Math.floor(segundos / 60);
    const resto = (segundos - minutos * 60).toFixed(1).padStart(4, "0");
    return `${minutos}:${resto}`;
  };

  const construir = (datos) => {
    const canvas = document.createElement("canvas");
    const reproductor = document.createElement("audio");
    reproductor.controls = true;
    const pie = document.createElement("div");
    pie.className = "pistas";
    const controles = document.createElement("div");
    controles.className = "controles";
    const etiqueta = document.createElement("span");
    etiqueta.className = "nota-actual";
    contenedor.append(canvas, reproductor, pie, controles, etiqueta);

    // Selector de pista. La posición se restablece cuando la pista nueva ya
    // cargó su metadata: asignar currentTime antes de eso se ignora.
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
          if (sonando) reproductor.play();
        }, { once: true });
        reproductor.src = pista.url;
      });
      opcion.append(radio, document.createTextNode(" " + pista.etiqueta));
      pie.append(opcion);
    });
    if (datos.pistas.length) reproductor.src = datos.pistas[0].url;

    // Velocidad sin cambiar el tono: para sacar de oído, escuchar a la mitad
    // es lo que más ayuda. preservesPitch viene activo en los navegadores.
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
    const minimo = alturas.length ? Math.min(...alturas) - 2 : 60;
    const maximo = alturas.length ? Math.max(...alturas) + 2 : 72;
    const filas = [...document.querySelectorAll("table.notas tbody tr")];
    const filaPorOrden = new Map(filas.map((fila) => [Number(fila.dataset.orden), fila]));

    const dibujar = () => {
      const escala = window.devicePixelRatio || 1;
      const ancho = canvas.clientWidth;
      const alto = canvas.clientHeight;
      canvas.width = ancho * escala;
      canvas.height = alto * escala;
      const pincel = canvas.getContext("2d");
      pincel.setTransform(escala, 0, 0, escala, 0, 0);
      pincel.clearRect(0, 0, ancho, alto);

      const aX = (segundos) => (segundos / datos.duracion_s) * ancho;
      const altoFila = (alto - MARGEN * 2) / (maximo - minimo + 1);
      const aY = (midi) => MARGEN + (maximo - midi) * altoFila;

      pincel.strokeStyle = "#2a2e37";
      pincel.lineWidth = 1;
      for (let midi = minimo; midi <= maximo; midi += 1) {
        const y = aY(midi) + altoFila;
        pincel.beginPath();
        pincel.moveTo(0, y);
        pincel.lineTo(ancho, y);
        pincel.stroke();
      }

      if (bucle) {
        pincel.fillStyle = "rgba(111, 180, 255, 0.10)";
        pincel.fillRect(aX(bucle.inicio_s), 0, aX(bucle.fin_s - bucle.inicio_s), alto);
      }

      const actual = datos.notas.find(
        (nota) =>
          reproductor.currentTime >= nota.inicio_s &&
          reproductor.currentTime < nota.inicio_s + nota.duracion_s
      );

      datos.notas.forEach((nota) => {
        pincel.fillStyle = COLORES[nota.etiqueta] || COLORES.baja;
        pincel.globalAlpha = nota === actual ? 1 : 0.65;
        pincel.fillRect(
          aX(nota.inicio_s),
          aY(nota.midi),
          Math.max(2, aX(nota.duracion_s)),
          Math.max(3, altoFila - 2)
        );
      });
      pincel.globalAlpha = 1;

      const x = aX(reproductor.currentTime);
      pincel.strokeStyle = "#e6e8ec";
      pincel.beginPath();
      pincel.moveTo(x, 0);
      pincel.lineTo(x, alto);
      pincel.stroke();

      etiqueta.textContent = actual
        ? `${formatoTiempo(datos.desplazamiento_s + reproductor.currentTime)}  ·  ${actual.nombre}`
        : formatoTiempo(datos.desplazamiento_s + reproductor.currentTime);

      filas.forEach((fila) => fila.classList.remove("sonando"));
      if (actual) {
        const fila = filaPorOrden.get(actual.orden);
        if (fila) fila.classList.add("sonando");
      }

      requestAnimationFrame(dibujar);
    };

    canvas.addEventListener("click", (evento) => {
      const caja = canvas.getBoundingClientRect();
      reproductor.currentTime =
        ((evento.clientX - caja.left) / caja.width) * datos.duracion_s;
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
