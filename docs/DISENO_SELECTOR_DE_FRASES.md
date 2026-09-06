# Quenotas: selector de frases sobre la forma de onda

**Fecha:** 2026-09-05
**Estado:** implementado (ver PLAN_SELECTOR_DE_FRASES.md)
**Complementa a:** `DISENO.md` (el diseño base sigue vigente en todo lo que aquí no se cambia)

---

## 1. Problema

Hoy el usuario escribe a mano "desde" y "hasta" en m:ss antes de haber oído nada, y cada envío es un fragmento suelto. Equivocarse por diez segundos es habitual, los archivos subidos no se reutilizan para otro rango, y para sacar una canción entera hay que volver a empezar seis veces.

## 2. Qué cambia

La **canción** pasa a ser la unidad de trabajo. Se sube o se pega el enlace una sola vez; aparece la forma de onda completa; sobre ella se marcan las frases con dos manijas, se escucha lo que queda entre ellas, y cada "Analizar esta selección" crea una frase analizada que queda listada debajo y pintada sobre la onda. Desaparece la pantalla intermedia de "escucha el recorte y confirma": esa confirmación ocurre sobre la onda.

Lo que no cambia: el motor de análisis, el contrato de datos, la pantalla de resultado de cada frase (lienzo de notas, tres pistas, velocidad, bucle, descargas), el semáforo de un análisis a la vez, la caché de descargas por id de video y la recuperación de trabajos a medias.

## 3. Pantallas

### 3.1 Inicio

Un campo para el enlace de YouTube, un selector de archivo, y un botón "Abrir". Sin tiempos. Al enviar se crea la `Cancion` y se lanza su preparación en segundo plano; el navegador va a la pantalla de la canción, que muestra "Descargando el audio..." o "Preparando..." con el sondeo que ya existe, hasta que la canción está lista o en error.

### 3.2 Canción (pantalla nueva, la central)

- Título, fuente y duración total.
- **Forma de onda** completa en un `<canvas>`, con el cursor de reproducción.
- **Dos manijas** arrastrables (eventos de puntero, así funcionan con el dedo en el teléfono; zona de agarre de al menos 24 px). Al lado de cada una, su tiempo en m:ss en un campo editable: escribir un tiempo mueve la manija, arrastrar la manija actualiza el campo. La zona entre ambas queda resaltada.
- **Límite de 3 minutos** (`Config.max_fragmento_s`, que llega en el JSON de estado): si la selección lo supera, la zona se pinta de aviso, el botón de analizar se desactiva y se muestra el motivo. Selección mínima: 1 segundo.
- Botones: **"Escuchar la selección"** (reproduce desde la manija izquierda y se detiene en la derecha; un segundo clic para) y **"Analizar esta selección"**. Casilla "Separar la melodía de la banda", cuyo valor se recuerda en la canción.
- Clic en la onda fuera de las manijas: mueve el cursor de reproducción (no las manijas). Arrastrar una manija más allá de la otra las intercambia.
- **Lista de frases** de esa canción, cada una con su rango, estado ("en cola", "analizando", "lista", "error" con mensaje y botón "Reintentar") y enlace al resultado. Se refresca cada pocos segundos desde el JSON de estado sin recargar la página, así se puede marcar la siguiente frase mientras la anterior se analiza.
- Cada frase lista se pinta como una **banda tenue** sobre la onda, para ver de un vistazo qué partes de la canción ya están sacadas. Clic en una banda abre su resultado.

### 3.3 Resultado de una frase

La pantalla actual, sin cambios, más un enlace "Volver a la canción". Ya no existe la rama "preparado" con el botón Analizar.

### 3.4 Historial

Lista de canciones (título, fuente, cuántas frases, fecha) y dentro de cada una sus frases con estado y enlace.

## 4. Motor

Python puro, sin Django, sin cambiar el contrato de datos.

- `motor/audio.py`:
  - `forma_de_onda(ruta, columnas=1200) -> list[float]`: carga en mono, parte la señal en `columnas` bloques y devuelve el pico absoluto de cada uno normalizado a 0..1 (todo ceros si la señal es silencio). Es lo que dibuja el navegador; 1200 valores caben en un JSON de unos 8 KB.
  - `convertir_para_escucha(entrada, salida, bitrate="128k") -> Path`: ffmpeg a AAC en contenedor m4a. Motivo: lo que baja de YouTube suele ser webm/opus, que Safari y el iPhone no reproducen, y un WAV subido puede pesar 50 MB. El original se conserva para recortar y analizar.
- `motor/pipeline.py`:
  - `obtener_audio(origen, cache_dir, titulo="", progreso=None) -> Fuente` donde `Fuente` es una dataclass congelada nueva del pipeline (no del contrato) con `ruta`, `titulo`, `fuente` ("youtube" | "archivo") y `referencia`. Es la mitad "descargar o localizar" de la `preparar` actual.
  - `preparar` se reescribe como `obtener_audio` seguido de `recortar`, con la misma firma de hoy: sigue sirviendo para consola y tests, y no cambia `analizar_preparado` ni `analizar_fuente`.

## 5. Web

### 5.1 Modelo

`Cancion` gana: `origen` (URL o ruta del archivo subido), `audio_original` (ruta del audio completo: en la caché de `media/origen/` si es YouTube, en `media/subidas/` si es archivo), `audio_escucha` (ruta del m4a), `duracion_s`, `estado` (`pendiente`, `preparando`, `lista`, `error`), `paso`, `mensaje`, `separar` (booleano recordado). Migración `0002`.

`Fragmento` no cambia de campos. En el flujo nuevo solo pasa por `pendiente`, `procesando`, `listo` y `error`; `preparando` y `preparado` quedan en las opciones por compatibilidad, sin uso.

### 5.2 Trabajos (`trabajos.py`)

- `ejecutar_preparacion_cancion(cancion_id)`: `obtener_audio`, `duracion_s`, `convertir_para_escucha`, `forma_de_onda` guardada como `media/canciones/<id>/onda.json`, y la canción pasa a `lista`. Va fuera del semáforo (no usa la GPU).
- `ejecutar_frase(fragmento_id)`: recorta desde `cancion.audio_original` a `media/fragmentos/<id>/mezcla.wav` con `recortar` y sigue con `analizar_preparado`, dentro del semáforo, con `paso="En cola"` mientras espera. Sustituye a la pareja `ejecutar_preparacion` + `ejecutar_analisis`, que se eliminan junto con sus tests.
- `recuperar_huerfanos` cubre también las canciones en `preparando`.
- Los puntos de sustitución para tests siguen el patrón actual (`_OBTENER`, `_ANALIZAR`, valores `None` que significan "usar el real").

### 5.3 Rutas y vistas

| Ruta | Nombre | Qué hace |
|---|---|---|
| `/` | `index` | GET: formulario. POST: crea la canción (reutiliza la de la misma URL), lanza la preparación, redirige a la canción |
| `/cancion/<pk>/` | `cancion` | La pantalla central |
| `/cancion/<pk>/estado/` | `cancion_estado` | JSON: estado, paso, mensaje, duración, `max_fragmento_s`, `separar`, y la lista de frases con id, inicio, fin, estado, mensaje y URL del resultado |
| `/cancion/<pk>/onda/` | `cancion_onda` | JSON con los picos (lee `onda.json`) |
| `/cancion/<pk>/escucha/` | `cancion_escucha` | El m4a, con soporte de `Range` |
| `/cancion/<pk>/frases/` | `crear_frase` | POST con `inicio_s`, `fin_s` (segundos con decimales) y `separar`; valida orden, mínimo 1 s, máximo `max_fragmento_s` y que quepa en la duración; crea el fragmento en `procesando`/"En cola" con un `update` atómico y lanza `ejecutar_frase`. Responde JSON con la frase creada (o el error con 400) |
| `/cancion/<pk>/reintentar/` | `cancion_reintentar` | Relanza la preparación si está en error |
| `/fragmento/<pk>/` | `detalle` | Igual que hoy, sin la rama "preparado", con enlace a la canción |
| `/fragmento/<pk>/reintentar/` | `reintentar` | Relanza `ejecutar_frase` si está en error |
| `/fragmento/<pk>/{estado,datos,audio,descargar}/` | sin cambios | `audio` pasa a usar el helper con `Range` |
| `/historial/` | `historial` | Canciones con sus frases |

Se elimina la ruta `analizar`. El formulario de la tarea 17 (`FormularioFragmento`) se reemplaza por `FormularioCancion` (enlace o archivo); `parsear_tiempo` se conserva para los campos editables de las manijas (el JS envía segundos, pero el servidor también acepta m:ss).

### 5.4 Audio con `Range`

Un helper `respuesta_audio(ruta, request, tipo)` que atiende `Range: bytes=a-b` con 206, `Content-Range`, `Content-Length` y `Accept-Ranges: bytes`, y devuelve 200 completo si no hay cabecera. Lo usan `cancion_escucha` y `audio`. Sin él, saltar dentro de cinco minutos de audio no funciona bien en Chrome y no funciona en Safari.

### 5.5 JavaScript (`web/static/onda.js`)

Pieza autocontenida como `pianoroll.js`: recibe las URL de onda, estado y escucha desde atributos `data-*` del contenedor (solo URLs y enteros, nunca flotantes por plantilla). Dibuja los picos, las bandas de frases listas, la zona seleccionada y el cursor; gestiona las manijas con `pointerdown`/`pointermove`/`pointerup` y `setPointerCapture`; sincroniza los campos m:ss; reproduce la selección deteniéndose en `fin` vía `timeupdate`; envía el POST de crear frase con `fetch` (token CSRF de la cookie) y refresca la lista de frases cada 3 s mientras haya alguna en cola o analizando.

### 5.6 Archivos en disco

```
media/
  origen/<id_video>.<ext>      caché de YouTube, sin cambios
  subidas/<nombre>             archivos subidos, sin cambios
  canciones/<id>/escucha.m4a   copia para el navegador
  canciones/<id>/onda.json     picos
  fragmentos/<id>/...          sin cambios
```

## 6. Manejo de errores

| Situación | Comportamiento |
|---|---|
| Enlace inválido o bloqueado, archivo ilegible | Canción en `error` con el mensaje de `ErrorDescarga`/`ErrorAudio` y botón Reintentar |
| ffmpeg no puede convertir a m4a | Canción en `error` con el mensaje; el original no se borra |
| Selección fuera de la duración, invertida, menor de 1 s o mayor del límite | El JS lo impide antes de enviar; el servidor lo valida igual y responde 400 con el motivo |
| Análisis de una frase falla | La frase muestra el error en la lista y "Reintentar"; la canción sigue usable |
| Cierre del programa a mitad | `recuperar_trabajos` pasa a `error` canciones en `preparando` y frases en `procesando` |
| Dos clics en "Analizar esta selección" | El segundo crea otra frase igual; el semáforo las serializa. Se acepta: el usuario ve dos frases y borra una si quiere (borrar frases queda fuera de esta versión) |

## 7. Pruebas

- Motor: `forma_de_onda` con `secuencia` (columnas correctas, picos en 0..1, silencio da ceros, señal más corta que las columnas no revienta); `convertir_para_escucha` con un WAV sintético (produce m4a legible por `duracion_s`, marcado `lento` si tarda); `obtener_audio` con descarga simulada y con archivo local; `preparar` sigue pasando sus tests actuales.
- Web: creación de canción por URL (reutilización) y por archivo; JSON de estado y de onda; POST de frase válido, invertido, corto, largo y fuera de duración; `Range` con `bytes=0-99` (206, `Content-Range` correcto) y sin cabecera (200); `recuperar_huerfanos` con canciones; `ejecutar_frase` con motor simulado; historial.
- JavaScript: `node --check`; comprobación visual del usuario: arrastrar manijas en escritorio y en el teléfono, escuchar la selección, marcar dos frases seguidas, ver las bandas.

## 8. Fuera de alcance

Borrar frases o canciones, zoom sobre la onda, marcar varias selecciones a la vez, detectar silencios para proponer cortes automáticos. Todo posible después sobre la misma base.
