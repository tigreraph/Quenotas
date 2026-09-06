# SacaNotas

Herramienta local para extraer la melodía de un fragmento de audio y devolverla como lista de notas, MIDI, TXT y PDF. Pensada para sacar canciones de oído con la quena sin perder una semana de tanteo.

**Antes de tocar nada, leer [docs/DISENO.md](docs/DISENO.md).** Ahí está el diseño completo: alcance, arquitectura, contrato de datos, flujo de procesamiento, manejo de errores, pruebas y fases.

**Para implementar, seguir [docs/PLAN.md](docs/PLAN.md).** Son 20 tareas con el código de cada paso, prueba primero y un commit por tarea, más una tarea 21 opcional. No improvisar fuera del plan: si algo del plan está mal, corregir el plan y avisar, porque varias piezas se construyen en paralelo contra las mismas firmas.

El plan fue revisado contra el diseño y contra esta máquina el 2026-09-05; [docs/REVISION_PLAN.md](docs/REVISION_PLAN.md) registra qué se encontró y qué se cambió. Ya está aplicado: no hace falta releerlo para ejecutar el plan, sirve para entender por qué algunas decisiones son como son.

## Lo mínimo que hay que saber

* **Dos capas separadas y no se mezclan.** `motor/` es Python puro y no importa Django. `web/` es Django y no contiene lógica de audio. Cualquier cosa que huela a procesamiento de señal va en `motor/`.
* **El contrato de datos manda.** Toda pieza produce o consume la estructura JSON descrita en la sección 6 del diseño. Si hace falta cambiarla, se cambia primero ahí y se avisa, porque varias piezas dependen de ella a la vez.
* **Melodía monofónica, una sola voz.** Nada de acordes ni polifonía.
* **La unidad es la canción; las frases se marcan sobre su forma de onda.** Se sube o se enlaza una vez, la canción se prepara en segundo plano (audio original, copia `escucha.m4a` para el navegador y `onda.json` con los picos en `media/canciones/<id>/`), y cada "Analizar esta selección" crea un `Fragmento` que se recorta desde el audio de la canción y se analiza. Límites por frase: entre 1 s y 3 min.
* **Notas en cifrado anglosajón:** `G4`, `A4`, `F5`.
* **Nada de entornos virtuales.** Intérprete global de Python, `requirements.txt` y un `.bat` de doble clic, igual que el resto de proyectos del espacio de trabajo.
* **Un solo runner de pruebas:** `py -m pytest -q` corre motor y web (`pytest-django`). No usar `manage.py test`.
* **Las descargas se guardan y se reutilizan.** `media/origen/<id_de_video>.<ext>`; una canción se baja una sola vez aunque se analicen diez fragmentos, y la misma URL cuelga de la misma `Cancion`.
* **Un análisis a la vez** (semáforo en `trabajos.py`): la GPU de 4 GB no aguanta dos Demucs. Si se queda sin memoria, se reintenta en CPU antes de renunciar a separar.
* **El audio se sirve con `Range`** (`transcripciones/audio_http.py`): sin respuestas 206 no se puede saltar dentro de una canción larga ni reproducir en Safari.
* **Los subprocesos hablan UTF-8** (`encoding="utf-8"`, `PYTHONUTF8=1`), porque Windows decodifica con cp1252 y un título de YouTube con `♪` rompe la descarga.
* **Sin autenticación, sin Celery, sin despliegue remoto** por ahora. Están excluidos a propósito, no olvidados.

## Estado

Implementado (plan base de 20 tareas más el selector de frases sobre la forma de onda, `docs/PLAN_SELECTOR_DE_FRASES.md`). Se arranca con doble clic en `iniciar.bat`. Pendiente del músico: grabar `tests/fijos/escala_quena.wav`, correr la calibración, y probar el selector desde el teléfono con una canción real.

Entorno ya verificado en esta máquina: Python 3.14.7 global (`py`), ffmpeg y ffprobe 9.0 en el PATH, git 2.55, RTX 3050 Laptop con 4 GB de VRAM. Todas las dependencias tienen rueda para Python 3.14.

`media/fragmentos/` crece con cada análisis y nadie lo limpia todavía; si el disco se llena, borrar a mano las carpetas de fragmentos viejos. Si el teléfono es un iPhone, Safari puede exigir soporte de `Range` para reproducir el audio; ya está atendido (`transcripciones/audio_http.py`).

## Cómo se prueba

- Todo: `py -m pytest -q`
- Solo motor: `py -m pytest tests -q`
- Solo web: `py -m pytest web -q`
- Calibración con la quena real: `py -m pytest tests/test_calibracion.py -q`

Los tests marcados `lento` cargan CREPE. Para saltarlos: `py -m pytest -q -m "not lento"`.

## Umbrales calibrados

Pendiente: se anotan cuando pase `tests/test_calibracion.py` con la grabación
real. Hasta entonces rigen los valores por defecto de `motor/config.py`.
