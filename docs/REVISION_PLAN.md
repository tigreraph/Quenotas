# Revisión del plan de implementación

**Fecha:** 2026-09-05
**Revisa:** `docs/PLAN.md` (20 tareas) contra `docs/DISENO.md` y contra el entorno real de esta máquina.
**Estado:** aplicada el 2026-09-05 sobre `PLAN.md`, `DISENO.md` y `CLAUDE.md`. Qué fue a dónde:

| Sección | Destino |
|---|---|
| A1 a A9 | corregidas en el plan, en la tarea que tocaba cada una (A3 con la opción 2, `pytest-django`) |
| B1 a B4 | plan y diseño alineados (respaldo en CPU, humo real en la tarea 1, cabeceras de estado, dependencias de la web reducidas al contrato) |
| C1 a C4 y D1 | incorporadas al plan como pasos de las tareas 5, 8, 12, 14, 16, 17 y 19 |
| C5, C6, D4 y el WAL de C8 | tarea 21, opcional |
| resto de C8 | aplicado (defaults de `Config`, `formato_tiempo`, `default_storage`, `patch.object`, sin variante `mido`, `.gitignore`) |
| D2, D3 y la histéresis de D1 | sección 14 del diseño, "Limitaciones conocidas", y la tabla de calibración de la tarea 20 |
| D5 | no aplicado: el test de vibrato a ±50 cents pasa tal como está y D1 lo protege |

El resto del documento queda como estaba, como registro de lo que se encontró.

Veredicto general: el plan es ejecutable y está bien construido (prueba primero, contrato fijo, motor sin Django, red y modelos simulados en los tests). Tiene nueve defectos que harían fallar pasos concretos tal como están escritos, cuatro contradicciones con el diseño, y una lista de mejoras baratas que valen más que su costo. Se recomienda corregir las secciones A y B en el plan antes de arrancar la tarea 1, y decidir cuáles de C y D entran.

Lo que se verificó en la máquina (2026-09-05):

| Comprobación | Resultado |
|---|---|
| `demucs>=4.1.0` en PyPI | existe (4.1.0). Ya no depende de `torchaudio`; usa `sphn` para audio |
| `pretty_midi>=0.2.11` en PyPI | existe (0.2.11.post0) y funciona con numpy 2.5.2 |
| `torch` 2.14 para Python 3.14 en Windows | rueda en PyPI (CPU) y en los índices `cu126` y `cu130` |
| `numba` (arrastrado por `torchcrepe` vía `librosa`) | 0.67.0 tiene rueda `cp314` para Windows |
| `ffmpeg -ss 1.000 -to 2.500 -i a.wav` (opciones de entrada) | produce 1.500 s exactos. La tarea 6 está bien |
| `py -m django startproject quenotas web` sin que exista `web/` | Django 6.1 crea la carpeta. La tarea 15 está bien |
| `{{ 0.4 }}` en plantilla con `LANGUAGE_CODE = "es"` | renderiza `0,4`. Ver A4 |
| `pretty_midi` releyendo un MIDI con instrumento sin notas | `instruments` queda vacío. Ver A2 |

---

## A. Errores que hacen fallar el plan tal como está escrito

Corregir en `PLAN.md` antes de ejecutar la tarea afectada.

### A1. Tarea 8: el test de confianza baja compara en distinta caja

`test_avisa_cuando_toda_la_confianza_es_baja` busca `"no se detectó" in aviso`, y el mensaje del pipeline empieza con `"No se detectó ninguna melodía"`. La comparación es sensible a mayúsculas y el test falla.

**Arreglo:** `any("no se detectó" in aviso.lower() for aviso in resultado.avisos)`.

### A2. Tarea 9: releer un MIDI sin notas no devuelve instrumentos

`test_el_midi_sin_notas_se_genera_igual` hace `PrettyMIDI(...).instruments[0].notes == []`. Verificado: `pretty_midi` solo crea el instrumento al encontrar eventos de nota, así que con un archivo vacío `instruments` es `[]` y el test lanza `IndexError`.

**Arreglo:** comprobar que el archivo existe, que se abre sin error y que `sum(len(i.notes) for i in leido.instruments) == 0`.

### A3. Tareas 17 a 19: dos tests nunca corren y los conteos no cuadran

`tests_vistas.py` define `test_parsear_tiempo_acepta_los_tres_formatos` y `test_parsear_tiempo_rechaza_basura` como funciones sueltas con `pytest.raises`. El runner de Django (`manage.py test`) es `unittest` y solo recoge clases `TestCase`; esas dos funciones se ignoran en silencio. Por eso los "21", "25" y "27 tests" esperados en las tareas 17, 18 y 19 son en realidad 19, 23 y 25.

**Arreglo (dos opciones, elegir una):**
1. Meter las dos funciones en una clase `PruebaTiempos(SimpleTestCase)` usando `self.assertRaises`.
2. Mejor: unificar todo con `pytest-django`. En `pytest.ini`: `DJANGO_SETTINGS_MODULE = quenotas.settings`, `pythonpath = . web`, `testpaths = tests web`. Un solo comando (`py -m pytest`), un solo estilo de assert, y desaparece la regla "tests del motor con pytest, tests de Django con manage.py". Añadir `pytest-django` a `requirements.txt`.

También en la tarea 2: el conteo "9 tests pasan" es 11 (6 parametrizados más 5).

### A4. Tareas 18 y 19: los flotantes de las plantillas salen con coma decimal

Con `LANGUAGE_CODE = "es"`, Django localiza los números en plantillas: `{{ nota.inicio_s }}` renderiza `0,4` (verificado). En `resultado.html` eso va a `data-inicio="0,4"` y en `pianoroll.js` `Number("0,4")` es `NaN`, así que la fila de la tabla nunca se resalta. Lo mismo pasa con `data-desplazamiento`.

**Arreglo:** emparejar lienzo y tabla por `orden`, que es un entero único dentro del fragmento: `data-orden="{{ nota.orden }}"` y en el JS `candidata.dataset.orden == actual.orden`. Quitar `data-desplazamiento` del HTML (el JS ya lo recibe en el JSON). Para cualquier otro flotante que deba leer JavaScript, usar `|stringformat:"g"` o `{% localize off %}`.

### A5. Tarea 19: al cambiar de pista se pierde la posición

En el `change` del radio se hace `reproductor.src = pista.url; reproductor.currentTime = instante;`. Asignar `currentTime` antes de que cargue la metadata de la nueva fuente se ignora en la mayoría de navegadores, y la pista nueva empieza desde cero. Es justo lo que el paso 6 de la tarea pide verificar ("al cambiar de pista la reproducción continúa en el mismo segundo").

**Arreglo:**
```javascript
reproductor.addEventListener("loadedmetadata", () => {
  reproductor.currentTime = instante;
  if (sonando) reproductor.play();
}, { once: true });
reproductor.src = pista.url;
```

### A6. Tareas 12 y 13: `subprocess.run(text=True)` decodifica con cp1252 en Windows

Sin `encoding`, Python 3.14 en Windows decodifica la salida del hijo con la codificación regional (cp1252). Un título de YouTube con `♪`, comillas tipográficas o caracteres asiáticos produce `UnicodeDecodeError`: en `obtener_titulo` se traga y el título se pierde; en `descargar_audio` no es `CalledProcessError`, así que escapa del `except` y el usuario ve un error genérico en vez del mensaje claro.

**Arreglo:** en `_EJECUTAR` de `descarga.py`, `separacion.py` y `_ejecutar` de `audio.py`: `subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True, env={**os.environ, "PYTHONUTF8": "1"})`. El `PYTHONUTF8=1` hace que los hijos Python (yt-dlp, demucs) escriban UTF-8.

### A7. Tarea 10: el PDF revienta con títulos fuera de Latin-1

`fpdf2` con las fuentes básicas (Helvetica, Courier) solo acepta Latin-1. `"Duración"` y `"Canción"` pasan, pero un título de YouTube con guion largo, `♪` o comillas tipográficas lanza `FPDFUnicodeEncodingException`, y como el PDF se genera dentro de `analizar_recorte`, el trabajo completo termina en `ERROR` después de haber hecho todo el análisis.

**Arreglo (elegir uno):**
1. Rápido: sanear cada texto con `texto.encode("latin-1", "replace").decode("latin-1")` en `a_pdf`.
2. Correcto: `pdf.add_font("Segoe", "", r"C:\Windows\Fonts\segoeui.ttf")` y usar esa fuente. Windows la trae siempre; para monoespaciada, `consola.ttf`.

Y además envolver la generación de cada archivo en `analizar_recorte` en un `try` que convierta el fallo en aviso ("no se pudo generar el PDF") en lugar de tumbar el resultado. Las notas ya están calculadas; perderlas por un archivo secundario es lo peor que puede pasar.

### A8. Tarea 20: `iniciar.bat` falla en el primer arranque y depende del idioma

Tres problemas:
1. No ejecuta `migrate`: en un clon limpio no existe `db.sqlite3` y la primera petición falla.
2. `for /f "tokens=14" ... findstr "IPv4"` cuenta tokens de la línea de `ipconfig`, que en Windows en español es `Dirección IPv4. . . . . . . : 192.168.x.x` con un número de puntos que varía. Es frágil.
3. `start "" http://localhost:8000` se ejecuta antes de que el servidor escuche; el navegador abre con "conexión rechazada".

**Arreglo:**
```bat
@echo off
cd /d "%~dp0"
py web\manage.py migrate --noinput
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%a:8000
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
py web\manage.py runserver 0.0.0.0:8000 --noreload
```
El `--noreload` importa por C3: el recargador automático mata el hilo de análisis cuando cambia un archivo.

### A9. Tarea 1: el orden de instalación de torch hace trabajo doble

`pip install -r requirements.txt` instala el torch de PyPI (CPU) y después el paso 5 lo reinstala con `--force-reinstall`, que además vuelve a instalar todas sus dependencias. **Arreglo:** instalar primero `py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126` (verificado que hay rueda 2.14 para cp314; `cu130` también) y después el `requirements.txt` sin las líneas de torch y torchaudio, o dejándolas para que pip las vea ya satisfechas.

---

## B. Contradicciones entre el plan y el diseño

### B1. Sin VRAM, el diseño cae a CPU; el plan renuncia a separar

`DISENO.md` §10: "Sin GPU o VRAM insuficiente: cae a CPU automáticamente, avisando que tardará más". `PLAN.md` tarea 14: si `separar_melodia` lanza `ErrorSeparacion`, se analiza la mezcla completa sin separar. Con 4 GB de VRAM el `CUDA out of memory` de Demucs es un caso esperable, no raro, y perder la separación es perder la función principal para canciones de banda.

**Arreglo en `analizar_preparado`:** si el error contiene `out of memory` y el dispositivo era `cuda`, reintentar con `dispositivo="cpu"` y añadir el aviso "la separación corrió en CPU por falta de memoria de video"; solo si también falla en CPU, caer a la mezcla. Añadir el test correspondiente en la tarea 14. Además pasar `--segment 6` a Demucs cuando el dispositivo es `cuda` (Demucs lo recomienda por debajo de 8 GB); dejarlo en `Config` como `QUENOTAS_SEGMENTO_DEMUCS`.

### B2. Los modelos se descargan en la primera petición, no al arrancar

`DISENO.md` §9: "Los modelos deben quedar descargados al arrancar y no en la primera petición". Ninguna tarea lo hace: CREPE se descarga en el primer test lento de la tarea 7 y Demucs en la prueba manual de la tarea 13. Peor: `verificar_entorno.py` solo hace `import demucs`, así que una incompatibilidad entre torch y torchcrepe o demucs no se descubre en la tarea 1 sino en la 7 o la 13.

**Arreglo en la tarea 1:** `verificar_entorno.py` debe ejecutar un humo real: generar 2 s de seno a 440 Hz con numpy, pasarlos por `torchcrepe.predict` y comprobar que la mediana de f0 está cerca de 440; y correr `python -m demucs` sobre un WAV de 5 s y comprobar que aparece `other.wav`. Eso descarga los pesos de los dos modelos, prueba CUDA de verdad y convierte la tarea 1 en la verificación que el plan dice que es. Se ejecuta también desde `iniciar.bat` la primera vez (o con un `--modelos`).

### B3. La sección "Ajustes hechos sobre el diseño" ya está aplicada

El final de `PLAN.md` lista cuatro ajustes "que hay que reflejar en `docs/DISENO.md`" (tiempos relativos, `preparar`/`analizar_preparado`, seis estados, `orden` global). Los cuatro ya están en `DISENO.md` tal como está hoy. En cambio `DISENO.md` sigue diciendo en la cabecera "Estado: diseño aprobado, pendiente de plan de implementación".

**Arreglo:** en el plan, cambiar el encabezado a "Ajustes aplicados al diseño"; en el diseño, poner "Estado: diseño aprobado, plan escrito el 2026-09-05".

### B4. La paralelización propuesta tiene dependencias ocultas

"Cómo ejecutar este plan" dice que la web (tareas 15 a 19) va en paralelo con exportadores (9 a 11) y fuentes (12 a 14) hasta la 17. Pero:
- la tarea 15 (`models.py`) importa `motor.exportar.etiqueta_confianza`, que nace en la tarea 9;
- la tarea 16 (`trabajos.py`) importa `motor.pipeline.preparar` y `analizar_preparado`, que nacen en la tarea 14.

Un agente que arranque la 15 en paralelo con la 9 falla al importar.

**Arreglo:** mover `etiqueta_confianza` y `formato_tiempo` de `exportar.py` a `contrato.py` (son semántica del contrato: qué es "alta", cómo se muestra un tiempo; el JavaScript ya los duplica) y en `trabajos.py` importar `motor.pipeline` dentro de las funciones, no arriba del módulo. Con eso la web depende solo de las tareas 2 y 8, y el grafo del plan queda como se describe. Actualizar la tabla de interfaces de las tareas 9, 15 y 16.

---

## C. Mejoras de funcionamiento

Ordenadas por relación valor/costo. Las tres primeras se recomienda meterlas en el plan ahora; el resto es decisión del usuario.

### C1. No volver a descargar la canción por cada fragmento (tareas 12 y 17)

El flujo previsto es frase por frase: cinco o seis fragmentos de la misma canción. Hoy cada envío crea una `Cancion` nueva y descarga la canción completa otra vez, convertida a WAV (unos 50 MB por cada 5 minutos), en `media/fragmentos/<id>/origen/`. Son cinco descargas donde bastaba una, cinco oportunidades de que YouTube pida verificación, y cinco copias en disco.

**Arreglo:**
- `descargar_audio` guarda en `media/origen/<id_de_video>.<ext>` y, si ya existe, no descarga. El id sale de `yt-dlp --print id` o de la URL.
- Quitar `-x --audio-format wav`: descargar `bestaudio` en su formato nativo (m4a u opus, 5 MB en vez de 50). `recortar` ya acepta cualquier entrada porque es ffmpeg quien convierte.
- Obtener título e id en la misma llamada de red con `--print "%(id)s\n%(title)s"` y `--print-to-file`, en vez de una llamada aparte para el título.
- En `views.index`, reutilizar la `Cancion` cuya `referencia` coincide con la URL en vez de crear otra. El historial deja de mostrar la misma canción seis veces.

### C2. Un análisis a la vez (tarea 16)

Dos clics en "Analizar" en dos pestañas lanzan dos Demucs simultáneos sobre 4 GB de VRAM: el segundo muere por memoria. **Arreglo:** un `threading.Semaphore(1)` a nivel de módulo en `trabajos.py`; mientras espera, el fragmento muestra `paso = "En cola"`. Cuatro líneas.

### C3. Trabajos huérfanos y reintento (tareas 16 y 17)

Si se cierra la consola, se recarga el servidor o Python muere, el fragmento queda en `preparando` o `procesando` para siempre, la página sondea eternamente y no hay forma de reintentar sin borrar el registro. **Arreglo:**
- En `TranscripcionesConfig.ready()` (o en `iniciar.bat` con un comando de gestión), pasar a `error` con mensaje "El análisis se interrumpió" todo fragmento que esté en un estado intermedio.
- Botón "Reintentar" en `detalle.html` cuando el estado es `error`, que vuelve a lanzar la preparación o el análisis según lo que haya en `archivos`.
- `runserver --noreload` en el bat (ver A8).

### C4. Velocidad de reproducción y bucle por frase (tarea 19)

Para sacar de oído, lo que más ayuda es escuchar despacio sin que cambie el tono. Los navegadores lo dan gratis: `reproductor.playbackRate = 0.5` con `preservesPitch` (activo por defecto). Añadir al lienzo un selector 0.5x, 0.75x, 1x, y que hacer clic en el título "Frase N" de la tabla ponga el reproductor en bucle entre `inicio_s` y `fin_s` de esa frase. Son unas veinte líneas de JavaScript y es la función que convierte la herramienta en algo con lo que practicar, no solo consultar.

### C5. Nombres de nota en el lienzo (tarea 19)

El lienzo dibuja bloques sin etiqueta salvo la nota que suena. Dibujar en el margen izquierdo el nombre de cada carril (`G4`, `A4`, ...) y sombrear los carriles que no pertenecen a la escala de Sol mayor. Así el músico lee el lienzo como una tablatura sin mirar la tabla.

### C6. Peticiones `Range` para el audio (tarea 17)

`FileResponse` no atiende cabeceras `Range`. Chrome, al no ver `Accept-Ranges`, tarda en permitir `currentTime` hasta tener el archivo completo, y a veces reinicia la descarga al buscar. Con archivos de 5 a 10 MB funciona pero a saltos, y el clic en el lienzo para saltar a un segundo depende justo de eso. **Arreglo:** una vista `audio` que lea la cabecera `Range` y responda 206 con `Content-Range` (unas veinte líneas), o servir las pistas como OGG de 96 kbps generadas en `exportar.py` (diez veces más pequeñas; ffmpeg ya está).

### C7. Umbrales de confianza en un solo sitio (tareas 9, 18, 19)

`alta/media/baja` se decide en Python (`etiqueta_confianza`) y otra vez en `pianoroll.js` (`0.85`, `0.6`). Cuando se calibren y cambien, cambiarán en uno solo. **Arreglo:** que `views.datos` envíe `etiqueta` ya calculada por nota y el JS no calcule nada.

### C8. Menores

- `Config` (tarea 3): los valores por defecto están escritos dos veces, en la dataclass y en `desde_entorno` (`261.63` aparece en ambas). Usar `Config.__dataclass_fields__[campo].default` para todos, como ya se hace con `media_dir`.
- `formato_tiempo(59.96)` (tarea 9) devuelve `"0:60.0"`. Redondear a décimas antes de separar minutos.
- `_guardar_subida` (tarea 17) escribe en `media/subidas/<nombre>` y sobrescribe si se sube dos veces el mismo nombre. Usar `default_storage.save`, que añade sufijo.
- Tests de `trabajos` (tarea 16): asignan `trabajos._PREPARAR = ...` y nunca lo restauran. Usar `unittest.mock.patch.object`.
- El test `test_los_datos_solo_listan_las_pistas_que_existen` (tarea 19) tiene variables sin usar (`pista`, `ruta`) e imports dentro del método. Limpiar.
- La variante con `mido` de la tarea 9 puede borrarse: `pretty_midi` 0.2.11.post0 funciona con numpy 2.5 (verificado). Acorta el plan.
- SQLite (tarea 15): el hilo escribe `paso` mientras la página sondea `estado`. `timeout: 30` evita casi todos los "database is locked"; activar WAL con `PRAGMA journal_mode=WAL` en la señal `connection_created` los elimina.
- `.gitignore` ignora `*.pdf` en todo el repositorio. Si algún día se guarda un PDF en `docs/`, no entrará. Limitarlo a `media/`.

---

## D. Riesgos musicales del segmentador

No bloquean el plan. Son los puntos donde el resultado con material real puede decepcionar y conviene tenerlos anotados antes de la calibración de la tarea 20.

### D1. Afinación desplazada y redondeo directo (tarea 5)

`curva_a_notas` redondea el MIDI continuo al semitono más cercano. Si la quena está 40 o 50 cents desplazada respecto a 440 Hz (normal en instrumentos artesanales, y también si la grabación viene de un video acelerado), cada nota queda justo en la frontera entre dos semitonos: la mediana móvil oscila entre `68.49` y `68.51`, el redondeo alterna entre 68 y 69, y `_absorber_transitorios` parte la nota en pedazos que luego `duracion_min_s` descarta. La tabla de la tarea 20 dice "todo desviado en el mismo sentido: es dato real, no error", pero antes de llegar a leer los cents el segmentador ya rompió las notas.

**Arreglo (el más valioso de esta sección):**
1. Estimar el desplazamiento de afinación del fragmento: moda de la parte fraccionaria de `midi_continuo` sobre las tramas con voz (el mismo método de `librosa.estimate_tuning`, con un histograma de 100 bins basta).
2. Restarlo antes de redondear y guardarlo en `ParametrosAnalisis.afinacion_cents` (nuevo campo del contrato, avisar).
3. Si supera 30 cents, aviso: "el instrumento está afinado N cents por encima o por debajo".
4. Histéresis en el cambio de nota: abrir nota nueva solo cuando el MIDI suavizado se aleja más de 0.5 más un margen (por ejemplo 0.15) del centro de la nota actual, no en cuanto cruza la frontera.

Añadir a la tarea 5 el caso de prueba: `[(68.55, 0.8)]` debe dar una sola nota, no varias.

### D2. Notas repetidas (tarea 5, fase posterior)

Dos G4 seguidos con lengüeteo, sin que la confianza de CREPE baje del umbral entre ellos, salen como un único G4 largo. En huaynos y sanjuanitos las notas repetidas son constantes. El segmentador solo mira altura y confianza; no tiene ninguna señal de energía.

**Arreglo (fase 5, después de calibrar):** calcular RMS por trama del audio con el mismo salto de 10 ms, pasarlo como `energia` opcional a `curva_a_notas`, y partir una nota cuando la energía cae más de 6 dB respecto a su pico local y vuelve a subir. Mientras no exista, documentar la limitación en la pantalla de resultado: "las notas repetidas pueden aparecer como una sola nota larga".

### D3. Demucs y los instrumentos de viento (tarea 13)

El plan da por hecho que la quena cae en `other.wav`. Con instrumentos de viento con aire (quena, zampoña) Demucs reparte parte de la señal a `vocals.wav`, porque se parece a una voz. Si pasa, la melodía aislada sonará apagada y CREPE perderá confianza. **Arreglo:** en la prueba manual de la tarea 13, escuchar también `vocals.wav`. Dejar en `Config` un `QUENOTAS_STEMS = "other"` que admita `"other,vocals"` y en `separar_melodia` sumar los stems indicados. Decidirlo con la primera canción real, no antes.

### D4. Sonificación con seno puro (tarea 10)

Un seno puro se percibe con menos definición de altura que un tono con armónicos, y al compararlo con la quena real se nota. Sumar los armónicos 2 y 3 con amplitudes 0.5 y 0.25 es una línea más en `sonificar` y suena reconociblemente "a flauta".

### D5. Vibrato al límite (tarea 5)

El test `test_el_vibrato_no_parte_la_nota` usa exactamente ±50 cents, que es la frontera del redondeo. Con `ventana_mediana = 5` pasa porque el pico tras la mediana queda en 69.48, pero está al límite; una fase distinta de la senoide lo movería. No es un error del plan, pero conviene bajar el vibrato del test a ±40 cents (lo realista para quena) y dejar el caso de ±50 como test marcado `xfail` con la nota de que D1 lo resuelve.

---

## Orden recomendado para aplicar esta revisión

1. **Corregir `PLAN.md` y `DISENO.md`** con todo A y B. Es una sesión de edición de documentos, sin código.
2. **Decidir C y D.** Recomendación: entran C1, C2, C3, C4 y D1 en el plan como pasos de las tareas que tocan; C5, C6, C7 y D4 se dejan como tarea 21 opcional; D2 y D3 se anotan en el diseño como limitaciones conocidas de la primera versión.
3. **Ejecutar las tareas 1 a 8 en orden**, con `verificar_entorno.py` ya haciendo el humo real de B2.
4. Desde la 9, en los tres caminos paralelos del plan, que con B4 sí son independientes.
5. La tarea 20 la hace el músico: grabar la escala de Sol con el teléfono.
