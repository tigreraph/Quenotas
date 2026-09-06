# Quenotas

Extrae la melodía de una canción y la devuelve como notas en cifrado anglosajón (`G4`, `F#5`), MIDI, TXT y PDF. Pensado para sacar canciones de oído con la quena sin perder una semana de tanteo.

## Qué hace

Se sube un archivo de audio o se pega un enlace de YouTube. Aparece la forma de onda completa de la canción y sobre ella se marcan frases con dos manijas arrastrables. Cada frase se analiza por separado: opcionalmente se separa la melodía de la banda con Demucs (`htdemucs_6s`) y luego se detecta la altura con CREPE. El resultado de cada frase muestra un lienzo de notas con zoom, un panel de detalle por nota, fichas por frase, tres pistas de escucha alineadas en el tiempo (la mezcla original, la melodía aislada y una sonificación de las notas detectadas), control de velocidad, bucle por frase y atajos de teclado (espacio para reproducir o pausar, flechas para retroceder o avanzar 2 segundos).

## Requisitos

- Windows (probado en Windows 11).
- Python 3.14 con el intérprete global. Sin entorno virtual, por decisión del proyecto.
- ffmpeg y ffprobe en el PATH.
- GPU NVIDIA opcional (probado con 4 GB de VRAM). Sin GPU corre igual, pero más lento porque Demucs y CREPE caen a CPU.

## Instalación

```
py -m pip install -r requirements.txt
py verificar_entorno.py
```

`verificar_entorno.py` comprueba que ffmpeg y ffprobe estén en el PATH, que todas las librerías importen, y además pasa un seno por CREPE y un audio corto por Demucs para forzar la descarga de sus modelos y detectar cualquier incompatibilidad antes de la primera canción real. Con `--rapido` se salta esas dos pruebas y solo revisa imports y binarios.

Para arrancar, doble clic en `iniciar.bat` o `py web/manage.py runserver`. La primera vez hace falta preparar la base de datos con `py web/manage.py migrate`, aunque `iniciar.bat` ya lo hace solo antes de levantar el servidor.

## Cómo se usa

1. Abrir la aplicación (`iniciar.bat` o `runserver`) y entrar desde el navegador, en este equipo o desde el teléfono en la misma red.
2. Pegar un enlace de YouTube o subir un archivo de audio.
3. Esperar a que la canción quede lista: se descarga o se procesa el archivo y aparece su forma de onda.
4. Marcar una frase arrastrando las dos manijas sobre la onda, y escucharla antes de analizar.
5. Elegir si se separa la melodía de la banda y pulsar "Analizar esta selección".
6. Revisar el resultado: notas detectadas, las tres pistas de escucha y las descargas en MIDI, TXT y PDF.
7. Repetir el marcado de frases sobre la misma canción hasta cubrir toda la parte que interesa.

## Arquitectura

Dos capas separadas que no se mezclan. `motor/` es Python puro y no importa Django; `web/` es Django y no contiene lógica de audio.

| Carpeta | Contenido |
|---|---|
| `motor/` | Descarga con yt-dlp, recorte con ffmpeg, separación con Demucs, detección de altura con torchcrepe, segmentación en notas y frases, exportación con pretty_midi y fpdf2 |
| `web/` | Proyecto Django (SQLite), vistas y modelos en `transcripciones/`, JavaScript sin librerías en `web/static/` |
| `media/` | Audios originales, copias para escucha, fragmentos recortados y archivos generados |
| `docs/` | Diseño y planes del proyecto |
| `tests/` | Pruebas del motor, incluida la calibración con audio real |

El motor orquesta sus etapas en `motor/pipeline.py` y produce siempre la misma estructura de datos (fragmento, análisis, frases con sus notas), sin conocer que existe una interfaz web. Del lado de Django, los análisis corren de a uno por vez con un semáforo (`transcripciones/trabajos.py`), porque una GPU de 4 GB no aguanta dos separaciones de Demucs en simultáneo, y el audio se sirve con soporte de `Range` (`transcripciones/audio_http.py`) para poder saltar dentro de una canción larga o reproducir desde Safari. Más detalle en `CLAUDE.md` y en `docs/DISENO.md`.

## Pruebas

- Todo: `py -m pytest -q`
- Sin cargar CREPE (más rápido): `py -m pytest -q -m "not lento"`
- Solo la app web: `py -m pytest web -q`
- Calibración con la quena real: pendiente de grabar `tests/fijos/escala_quena.wav` (ver `tests/fijos/LEEME.md`); una vez grabado, `py -m pytest tests/test_calibracion.py -q`.

## Limitaciones

- La melodía tiene que ser monofónica: una sola voz sonando a la vez, nada de acordes.
- Dos notas iguales seguidas de la misma altura pueden salir como una sola nota larga en vez de dos separadas.
- `media/` crece con cada análisis y nadie lo limpia automáticamente; si el disco se llena, hay que borrar a mano las carpetas viejas.
- Sin autenticación ni despliegue remoto: pensado para correr en la propia red de casa.
- Cada frase tiene que durar entre 1 segundo y 3 minutos.

## Licencia

Uso personal; sin licencia definida todavía.
