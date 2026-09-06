# Quenotas: diseño del sistema

**Fecha:** 2026-09-05
**Estado:** diseño aprobado; plan escrito y revisado el 2026-09-05 (`PLAN.md`, `REVISION_PLAN.md`)
**Autor del contexto:** Jonnathan Tigre (músico empírico, quena, banda de música andina)

**Actualización 2026-09-05:** el flujo de entrada (sección 3, 7.2 y 8.2) fue sustituido por el selector de frases sobre la forma de onda; ver `DISENO_SELECTOR_DE_FRASES.md`. El resto sigue vigente.

---

## 1. Problema

Sacar una melodía de oído toma aproximadamente una semana de tanteo con el instrumento: se escucha la canción, se prueban sonidos en la quena y la melodía va apareciendo por ensayo y error sobre la escala. El tiempo se va en descubrir qué notas son, no en practicarlas.

El objetivo es invertir esa proporción: que el sistema entregue las notas en minutos y el tiempo del músico se dedique íntegramente a la práctica.

## 2. Alcance

### Qué resuelve

Dado un fragmento corto de audio, devolver la **melodía monofónica** que suena en él, expresada como una lista de notas con nombre, momento de inicio, duración y grado de confianza, más los archivos para oírla y para imprimirla.

Se trabaja **frase por frase**, no la canción completa, porque en una canción la melodía del instrumento solo aparece en tramos concretos y porque un resultado corto es verificable de un vistazo.

### Qué NO resuelve (excluido deliberadamente)

* Acordes y polifonía. El sistema asume una sola voz sonando a la vez.
* Partitura y notación en pentagrama. El usuario no lee partituras; la salida es lista de notas.
* Digitación de quena. Se puede añadir más adelante como capa sobre las notas ya extraídas.
* Detección automática de tonalidad, compás y tempo.
* Cuentas de usuario y autenticación.
* Cola de trabajos distribuida (Celery, Redis).
* Despliegue en servidor remoto.

### Instrumentos objetivo

Diseñado para quena, pero el motor es genérico para cualquier melodía monofónica: zampoña, flauta traversa, saxo, trompeta, voz principal. La única adaptación por instrumento es el rango de frecuencias, que es un parámetro de configuración.

## 3. Entradas

Hay dos tipos de entrada y el sistema los trata distinto:

| Entrada | Origen típico | Necesita separación |
|---|---|---|
| Enlace de YouTube | Canción de banda completa | Sí |
| Archivo de audio subido | Grabación con teléfono de la quena sola, para ensayo | No |

En ambos casos el usuario indica un rango de tiempo en formato `m:ss`, por ejemplo de `0:30` a `1:30`. Solo ese fragmento se descarga, se recorta y se procesa.

## 4. Salidas

1. **Lista de notas en pantalla**, agrupada en frases separadas por los silencios naturales. Nomenclatura anglosajona: `G4`, `A4`, `F5`.
2. **Archivo MIDI** de la melodía detectada.
3. **Archivo TXT** con las mismas notas, para copiar y pegar.
4. **Archivo PDF** con las frases numeradas, pensado para imprimir y poner en el atril.
5. **Tres pistas de audio alineadas** sobre la misma línea de tiempo: la mezcla original del fragmento, la melodía aislada por el separador, y una sonificación de las notas detectadas convertidas en tonos simples.

La tercera pista es la herramienta de verificación: si suena igual que la melodía original, el análisis es correcto; donde suene distinto, ahí está el error y se ve marcado en la línea de tiempo.

## 5. Arquitectura

Dos capas con separación estricta. El motor no importa nada de Django y no sabe que existe una interfaz web.

```
Quenotas/
  motor/                  # Python puro, sin dependencias de Django
    config.py             # parámetros por variable de entorno
    descarga.py           # yt-dlp + ffmpeg: obtener y recortar el fragmento
    separacion.py         # Demucs: aislar la pista melódica
    afinacion.py          # CREPE: curva de afinación con confianza
    notas.py              # curva -> notas discretas -> frases
    exportar.py           # MIDI, TXT, PDF, sonificación WAV
    pipeline.py           # orquesta las etapas y devuelve el Resultado
  web/                    # proyecto Django
    quenotas/            # settings, urls
    transcripciones/      # app: modelos, vistas, plantillas
    static/
      pianoroll.js        # lienzo de notas sincronizado con la reproducción
  media/                  # audios y archivos generados
  docs/
    DISENO.md
  requirements.txt
  iniciar.bat
```

**Razón de la separación:** la capa de interfaz puede cambiar (hoy Django local, mañana una API en un servidor) sin tocar el motor, que es la parte difícil y cara del proyecto. Además el motor se prueba solo, sin abrir el navegador.

## 6. Contrato de datos

Este es el punto de acuerdo entre todas las piezas. Cualquier agente o desarrollador que construya un módulo programa contra esta estructura.

```json
{
  "fragmento": {
    "titulo": "Nombre de la canción",
    "fuente": "youtube | archivo",
    "referencia": "URL o nombre del archivo",
    "inicio_s": 30.0,
    "fin_s": 90.0
  },
  "analisis": {
    "separacion": "htdemucs | ninguna",
    "modelo_afinacion": "crepe:full",
    "hop_ms": 10,
    "fmin_hz": 261.6,
    "fmax_hz": 1568.0,
    "dispositivo": "cuda | cpu",
    "afinacion_cents": 0
  },
  "frases": [
    {
      "indice": 1,
      "inicio_s": 0.4,
      "fin_s": 5.1,
      "notas": [
        {
          "orden": 1,
          "nombre": "G4",
          "midi": 67,
          "inicio_s": 0.4,
          "duracion_s": 0.42,
          "confianza": 0.93,
          "cents": -12
        }
      ]
    }
  ],
  "archivos": {
    "mezcla_wav": "media/…/mezcla.wav",
    "melodia_wav": "media/…/melodia.wav",
    "notas_wav": "media/…/notas.wav",
    "midi": "media/…/melodia.mid",
    "txt": "media/…/notas.txt",
    "pdf": "media/…/notas.pdf"
  },
  "avisos": ["texto de advertencia para el usuario"]
}
```

**Los tiempos son relativos al inicio del fragmento.** El `inicio_s` de una nota o de una frase se cuenta desde el primer instante del recorte, donde 0 es el comienzo del WAV generado. El desplazamiento dentro de la canción vive únicamente en `fragmento.inicio_s`, y la pantalla muestra la suma de ambos. Es obligatorio que sea así porque el reproductor del navegador lee su posición desde 0, y cualquier otro criterio desalinearía el lienzo de notas respecto al audio.

Campos que merecen explicación:

* `orden`: número correlativo de la nota **dentro de todo el fragmento**, no dentro de su frase. Así una nota se identifica sin ambigüedad al hablar de ella.
* `confianza`: valor de 0 a 1 promediado sobre las tramas de la nota. En pantalla se traduce a alta, media o baja. Le dice al usuario qué notas revisar al oído y cuáles dar por buenas.
* `cents`: desviación respecto al semitonio exacto. Una nota a más de 35 cents es sospechosa: puede ser un error de detección, un glissando o una afinación real distinta del instrumento.
* `afinacion_cents`: desvío global del instrumento respecto a la referencia de 440 Hz, estimado sobre todo el fragmento. Los nombres de las notas ya lo tienen descontado (ver 7.5); los `cents` de cada nota no, para que el usuario vea el desvío real.
* `avisos`: mensajes no fatales, por ejemplo "toda la frase tiene confianza baja, es probable que la melodía no esté en este rango".

## 7. Flujo de procesamiento

### 7.1 Obtención del fragmento

`yt-dlp` descarga únicamente el audio del video, en su formato nativo (m4a u opus, unos 5 MB por canción). `ffmpeg` recorta el rango pedido con `-ss` y `-to`, y normaliza a WAV mono a 44.1 kHz.

**La canción completa se guarda y se reutiliza.** Va a `media/origen/<id_de_video>.<ext>`, y el siguiente fragmento de la misma canción no vuelve a descargar nada: el flujo es frase por frase, así que una canción típica se analiza en cinco o seis fragmentos, y bajarla cinco veces sería lento, llenaría el disco y multiplicaría las ocasiones de que YouTube pida verificación. La misma URL cuelga además de la misma `Cancion` en la base de datos, así que el historial muestra una canción con sus fragmentos y no seis entradas repetidas.

Antes de recortar se valida con `ffprobe` que el rango cae dentro de la duración real del audio.

Para archivos subidos se salta la descarga y se aplica el mismo recorte y normalización. El archivo subido se guarda en `media/subidas/` y también se puede reutilizar para otros rangos.

### 7.2 Vista previa

El recorte se devuelve al usuario para que lo escuche **antes** de analizar. El rango se indica de memoria y equivocarse por diez segundos es habitual; es más barato detectarlo oyendo que descubriéndolo después sobre notas que no cuadran.

El análisis se dispara con un botón aparte. Por eso el motor expone el trabajo partido en dos mitades, `preparar` (obtener y recortar) y `analizar_preparado` (separar, detectar y exportar), con una tercera función `analizar_fuente` que las encadena para poder usar el motor desde consola sin montar la aplicación.

### 7.3 Separación (opcional)

Demucs con el modelo `htdemucs` separa el fragmento en voz, batería, bajo y resto. Un instrumento de viento cae en el stem `other`, que es el que se usa como pista melódica.

Desde el 2026-09-05 el modelo por defecto es `htdemucs_6s` (seis pistas): la guitarra y el piano salen a pistas propias y `other` queda con los vientos. Medido con Carabuela: de 23 a 197 notas en 59 s.

Se ejecuta en GPU si hay CUDA disponible y en CPU si no, con aviso de que tardará más. Se omite por completo cuando el usuario marca que el audio ya viene limpio.

Como el fragmento dura entre veinte segundos y un par de minutos, el costo es asumible incluso con 4 GB de VRAM, pasando a Demucs un `--segment` reducido (6 por defecto). Si aun así la tarjeta se queda sin memoria, se reintenta en CPU con aviso; solo si también falla ahí se analiza la mezcla completa, avisando de que el resultado puede mezclar instrumentos. Nunca se corre más de una separación a la vez.

### 7.4 Detección de afinación

CREPE (vía `torchcrepe`) recorre la pista con un salto de 10 ms y devuelve dos series: la frecuencia fundamental estimada y la confianza de cada estimación. Se le acota el rango de búsqueda a `fmin`/`fmax` para que no persiga armónicos ni sonidos graves de la banda.

Rango por defecto para quena: de C4 (261.6 Hz) a G6 (1568 Hz). Configurable por instrumento.

### 7.5 Conversión a notas discretas

Esta es la etapa que concentra la dificultad del proyecto y la que habrá que ajustar contra material real.

1. Las tramas con confianza por debajo del umbral (0.5 por defecto) se marcan como silencio.
2. Las frecuencias se convierten a número MIDI continuo.
3. Se estima el desvío global de afinación del fragmento (media circular de la parte fraccionaria del MIDI de las tramas con voz) y se resta antes de redondear. Motivo: una quena artesanal 40 o 50 cents desplazada, o un video acelerado, deja cada nota justo en la frontera entre dos semitonos, y sin esta corrección el redondeo alterna y parte la nota en trocitos. Si las tramas no se concentran alrededor de un desvío (vibrato ancho), no se corrige nada. El valor queda en `afinacion_cents` y, si supera 30 cents, se avisa.
4. Se aplica una mediana móvil de unas 5 tramas para absorber el vibrato y eliminar saltos de octava espurios.
5. Se abre una nota nueva cuando aparece un silencio, o cuando el semitono redondeado cambia y se mantiene estable durante al menos 50 ms.
6. Los segmentos de menos de 60 ms se descartan por considerarse artefactos.
7. La nota final es la mediana de los semitonos del segmento, redondeada. La diferencia entre la mediana sin corregir y el semitono exacto se guarda como `cents`, para que el usuario vea el desvío real del instrumento.
8. La confianza de la nota es la media de la confianza de sus tramas.

Todos los umbrales viven en `config.py` y son ajustables sin tocar la lógica.

### 7.6 Agrupación en frases

Un silencio de más de 0.6 segundos cierra la frase y abre la siguiente. El propósito es de legibilidad y de práctica: seis frases de quince notas se estudian de una en una, mientras que una lista de cien notas seguidas es inservible.

### 7.7 Generación de salidas

MIDI, TXT y PDF se generan desde la misma estructura de datos. La sonificación es una onda senoidal por nota con envolvente suave para evitar chasquidos, escrita como WAV alineado temporalmente con el fragmento original.

## 8. Interfaz web

Django con SQLite, sin autenticación, un solo usuario. Se lanza con un `.bat` de doble clic usando el intérprete global de Python y `requirements.txt`, sin entorno virtual, siguiendo la convención de los demás proyectos del espacio de trabajo.

### 8.1 Modelo de datos

* `Cancion`: título, fuente, referencia, fecha de creación.
* `Fragmento`: canción asociada, origen (la URL o la ruta del archivo subido, para poder reintentar), inicio, fin, estado, paso actual, mensaje de error, avisos, rutas de los archivos generados y parámetros del análisis. Los estados son seis: `pendiente`, `preparando`, `preparado`, `procesando`, `listo` y `error`. Hacen falta los dos intermedios porque entre obtener el recorte y analizarlo el sistema se detiene a que el usuario lo escuche.
* `Nota`: fragmento asociado, número de frase, orden, nombre, número MIDI, inicio, duración, confianza, cents.

Guardar el resultado en base de datos convierte la herramienta en un archivo personal: a los meses existe un repertorio consultable con cada frase ya sacada, su canción y su rango de tiempo, sin volver a analizarla.

### 8.2 Pantallas

Una pantalla principal con:

* Campo para enlace de YouTube o subida de archivo.
* Campos de inicio y fin en formato `m:ss`.
* Casilla de "audio limpio, no separar".
* Reproductor del recorte para confirmar el rango.
* Botón de analizar.

Una pantalla de resultado con:

* Lienzo de notas con línea de tiempo, donde cada nota es un bloque cuya altura indica la nota y su ancho la duración.
* Reproductor sincronizado: al reproducir o al arrastrar la barra, la nota que suena se resalta y su nombre se muestra.
* Selector de pista: mezcla original, melodía aislada, notas detectadas.
* Selector de velocidad (0.5x, 0.75x, 1x) sin cambiar el tono: para sacar de oído, escuchar despacio es lo que más ayuda.
* Bucle por frase: un clic en "Frase N" repite ese tramo hasta que se vuelve a hacer clic.
* Tabla de notas agrupada por frases, con la confianza de cada una.
* Botones de descarga de MIDI, TXT y PDF.
* Si el fragmento quedó en error (por fallo o porque se cerró el programa a mitad), un botón "Reintentar" que relanza el análisis si ya hay recorte, o la preparación si no.

Y una pantalla de historial con las canciones y fragmentos ya analizados.

### 8.3 El lienzo de notas

Se implementa como HTML y JavaScript propios sobre `<canvas>` y un elemento `<audio>`, sin biblioteca externa. La sincronización ocurre entera dentro del navegador leyendo `currentTime` del reproductor, sin viajes al servidor.

Es una pieza autocontenida: recibe el JSON de notas y las rutas de las tres pistas, y no depende del resto de la aplicación. Si en el futuro la interfaz cambia, se traslada sin reescribirse.

### 8.4 Procesamiento en segundo plano

Analizar tarda del orden de un minuto, más de lo que aguanta una petición HTTP normal. El flujo es:

1. El navegador pide el análisis y recibe de inmediato un identificador de trabajo.
2. El trabajo corre en un hilo aparte y va actualizando el estado del `Fragmento`.
3. El navegador consulta el estado cada pocos segundos hasta que pasa a `listo` o a `error`.

Para un solo usuario en local, un hilo es suficiente. La pieza queda aislada para poder sustituirla por una cola real si algún día hiciera falta.

Dos reglas alrededor del hilo:

* **Un análisis a la vez.** Un semáforo impide que dos Demucs corran juntos sobre 4 GB de VRAM. El segundo espera y la página muestra "En cola".
* **Nada queda a medias para siempre.** Si se cierra el programa con un análisis en marcha, al siguiente arranque los fragmentos en `preparando` o `procesando` pasan a `error` con el mensaje "el trabajo se interrumpió" y el botón de reintentar. El servidor de desarrollo corre sin recargador automático, porque el recargador mataría el hilo cada vez que cambia un archivo.

## 9. Decisiones tomadas pensando en un despliegue futuro

No se va a desplegar ahora. Pero tres decisiones cuestan cero hoy y evitan reescribir después:

1. **Motor separado de la interfaz.** Añadir una API encima no toca el motor.
2. **Nada escrito a mano en el código.** Rutas, dispositivo de cómputo y puerto salen de configuración, de modo que la misma carpeta corre en una laptop con GPU y en un servidor sin ella.
3. **Análisis tratado como trabajo con identificador**, no como respuesta inmediata.

Advertencias conocidas para ese escenario, documentadas para no descubrirlas tarde:

* Un servidor de datos comparte IP de centro de datos, y YouTube responde con frecuencia pidiendo verificación antibot a esas IP. La subida de archivos siempre funciona; el pegado de enlaces sería la función frágil.
* Demucs necesita al menos 4 GB de RAM.
* Los modelos deben quedar descargados al arrancar y no en la primera petición. En esta máquina lo hace `verificar_entorno.py` en la tarea 1 del plan: pasa un seno por CREPE y un WAV corto por Demucs, lo que descarga los pesos y además prueba de verdad que torch, torchcrepe y demucs se entienden.

## 10. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Enlace inválido, privado o bloqueado | Mensaje claro y sugerencia de subir el archivo |
| Rango fuera de la duración del audio | Validación previa con `ffprobe` y aviso antes de procesar |
| Fragmento demasiado largo (más de 3 minutos) | Se rechaza con explicación, para no bloquear la máquina |
| Sin GPU o VRAM insuficiente | Cae a CPU automáticamente, avisando que tardará más |
| Confianza baja en todo el fragmento | Se devuelve el resultado igual, con un aviso de que la melodía probablemente no está en ese rango o el instrumento no destaca |
| Fallo del trabajo en segundo plano | Estado `error` con el mensaje visible, nunca una página en blanco |

## 11. Estrategia de pruebas

**Motor, con señales sintéticas.** La parte difícil se prueba sin depender de descargas ni de modelos pesados: se generan tonos con numpy (por ejemplo 440 Hz durante 0.5 s, silencio, 494 Hz) y se comprueba que `notas.py` devuelve exactamente `A4` y `B4` con las duraciones esperadas.

**Casos límite del segmentador:** vibrato de más o menos 50 cents que no debe partir la nota, glissando, nota más corta que el umbral, silencio inicial y final, salto de octava espurio.

**Calibración con material real.** Una grabación de teléfono con una escala conocida tocada en la quena se guarda como material de referencia, y una prueba verifica que el sistema la devuelve correcta. Este es el termómetro honesto del proyecto: mientras no pase, no hay motivo para confiar en el resultado de una canción.

**Django.** Las vistas se prueban con un motor simulado. No se ejecuta Demucs dentro de las pruebas.

**Un solo runner.** Todo corre con `pytest` (`pytest-django` para la parte web): `py -m pytest -q` desde la raíz ejecuta motor y web. No se usa `manage.py test`, que solo recoge clases `TestCase` e ignora en silencio los tests escritos como funciones.

**Red.** `yt-dlp` se simula siempre. Ninguna prueba depende de internet.

## 12. Dependencias

* `yt-dlp` para la descarga
* `ffmpeg` como binario externo, para recorte y conversión
* `demucs` y `torch` para la separación
* `torchcrepe` para la detección de afinación
* `numpy`, `scipy`, `soundfile` para el procesamiento
* `pretty_midi` o `mido` para el MIDI
* `fpdf2` para el PDF
* `Django` para la interfaz

Riesgo conocido: la instalación de `torch` con CUDA en Windows es la parte más frágil del montaje. Conviene resolverla y verificarla antes de escribir código que dependa de ella.

## 13. Fases de construcción

| Fase | Contenido | Paralelizable |
|---|---|---|
| 0 | Contrato de datos y motor sobre audio limpio, sin YouTube ni Demucs. Se valida con grabaciones de teléfono. | No |
| 1 | Exportadores: MIDI, TXT, PDF, sonificación | Sí |
| 2 | Descarga de YouTube, recorte y separación con Demucs | Sí |
| 3 | Django: modelos, vistas, historial, trabajo en segundo plano | Sí |
| 4 | Lienzo de notas sincronizado con las tres pistas | Sí |

La fase 0 va primero y sola, porque produce valor inmediato con las grabaciones de ensayo y porque fija el contrato del que dependen todas las demás. El ajuste fino del segmentador no se paraleliza: su cuello de botella es el músico escuchando si el resultado suena bien.

## 14. Limitaciones conocidas de la primera versión

Anotadas en la revisión del plan del 2026-09-05 para no descubrirlas con una canción real. No bloquean la construcción; se deciden después de la calibración.

**Notas repetidas.** El segmentador solo mira altura y confianza. Dos G4 seguidos con lengüeteo, sin que la confianza de CREPE baje entre ellos, salen como un único G4 largo. En huaynos y sanjuanitos las notas repetidas son constantes. La solución es una señal de energía: RMS por trama con el mismo salto de 10 ms, y partir una nota cuando la energía cae más de 6 dB respecto a su pico local y vuelve a subir. Queda como fase 5, después de calibrar con la quena real. Mientras tanto, la pantalla de resultado lo advierte.

**Demucs y los instrumentos de viento.** El diseño da por hecho que la quena cae en la pista `other`. Con instrumentos de viento con aire (quena, zampoña), Demucs a veces manda parte de la señal a `vocals`, porque se parece a una voz; si pasa, la melodía aislada suena apagada y CREPE pierde confianza. Se decide con la primera canción real: escuchar `other.wav` y `vocals.wav`, y si la melodía se reparte, sumar ambas pistas (parámetro `QUENOTAS_STEMS`). No se implementa antes de verlo.

**Histéresis en el cambio de nota.** La compensación del desvío global (7.5, paso 3) resuelve el caso de un instrumento afinado distinto. Si además una nota concreta queda entre dos semitonos y el redondeo la parte, el siguiente recurso es histéresis: cambiar de nota solo cuando el desvío supera medio semitono más un margen. Está anotado en la tabla de calibración del plan y no se implementa hasta que el material real lo pida.
