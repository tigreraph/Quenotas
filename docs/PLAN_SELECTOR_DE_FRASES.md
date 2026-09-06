# Selector de frases sobre la forma de onda: plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usar `superpowers:subagent-driven-development` (recomendada) o `superpowers:executing-plans` para implementar este plan tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Objetivo:** que el usuario suba o enlace una canción una sola vez, vea su forma de onda completa, marque cada frase con dos manijas, la escuche y la analice, y que las frases analizadas queden listadas y pintadas sobre la onda.

**Arquitectura:** la `Cancion` pasa a ser la unidad de trabajo con su propio estado y su preparación en segundo plano (descarga o archivo, copia AAC para el navegador, picos de la onda en JSON). Cada frase es un `Fragmento` que se recorta desde el audio de la canción y se analiza en un solo trabajo bajo el semáforo de uno en uno. El motor gana dos funciones de audio y una función de obtención de audio; el contrato de datos no cambia. Un archivo `onda.js` autocontenido dibuja la onda y gestiona las manijas.

**Stack:** Python 3.14 global, numpy, soundfile, ffmpeg, Django 6.1 con SQLite, pytest con pytest-django, JavaScript sin dependencias.

**Spec:** `docs/DISENO_SELECTOR_DE_FRASES.md` (y `docs/DISENO.md` para todo lo que no cambia)

## Restricciones globales

Las mismas de `docs/PLAN.md`, que siguen vigentes, más lo específico de este plan:

- **Intérprete:** `py` (Python 3.14.7 global). Nunca entorno virtual. `web/manage.py` no tiene shebang a propósito.
- **`motor/` no importa `django` ni nada de `web/`.** El contrato (`motor/contrato.py`) no cambia.
- **Un solo runner:** `py -m pytest -q` (motor y web). `py -m pytest tests -q` solo motor, `py -m pytest web -q` solo web. Nunca `manage.py test`.
- **Subprocesos en UTF-8:** `encoding="utf-8", errors="replace"` y `PYTHONUTF8=1`; en `motor/audio.py` ya lo hace `_ejecutar`.
- **Ningún flotante para JavaScript pasa por plantilla** (`LANGUAGE_CODE = "es"` imprime `0,4`): el JS recibe URLs y enteros en `data-*` y el resto por JSON.
- **Límites de una frase:** mínimo 1 s, máximo `Config.max_fragmento_s` (180 s por defecto), y no más allá de la duración de la canción (tolerancia 0.25 s, la de `recortar`).
- **Estados de `Cancion`:** `pendiente`, `preparando`, `lista`, `error`. **Estados de `Fragmento` en el flujo nuevo:** `pendiente`, `procesando`, `listo`, `error` (`preparando` y `preparado` quedan en las opciones sin uso).
- **Archivos:** `media/canciones/<id>/escucha.m4a` y `media/canciones/<id>/onda.json`; el original queda donde estaba (`media/origen/` o `media/subidas/`); las frases siguen en `media/fragmentos/<id>/`.
- **Idioma:** código, nombres y mensajes en español.
- **Commits:** uno por tarea, mensaje exacto del brief, sin trailers de coautoría.
- **Estado inicial:** HEAD `7e2b7ab`; suite `py -m pytest -q -m "not lento"`: 130 tests en verde (87 motor + 43 web) y 4 deseleccionados.

## Estructura de archivos

```
motor/
  audio.py          + forma_de_onda, convertir_para_escucha
  pipeline.py       + Fuente, obtener_audio; preparar reescrita sobre obtener_audio
tests/
  test_audio.py     + tests de onda y conversión
  test_pipeline.py  + tests de obtener_audio
web/transcripciones/
  models.py         Cancion con estado, rutas, duración, separar
  migrations/0002_cancion_estado_y_audio.py
  trabajos.py       ejecutar_preparacion_cancion, ejecutar_frase (sustituyen a preparacion/analisis)
  audio_http.py     NUEVO: respuesta_audio con Range
  formularios.py    FormularioCancion (sustituye a FormularioFragmento); parsear_tiempo se conserva
  views.py          index, cancion, cancion_estado, cancion_onda, cancion_escucha, crear_frase,
                    cancion_reintentar, detalle, estado, reintentar, datos, audio, descargar, historial
  urls.py           rutas nuevas; desaparece analizar
  templates/transcripciones/
    index.html      solo enlace o archivo
    cancion.html    NUEVO: la pantalla central
    detalle.html    sin la rama "preparado", con enlace a la canción
    historial.html  canciones con sus frases
  tests_modelos.py, tests_trabajos.py, tests_vistas.py, tests_audio_http.py (nuevo)
web/static/
  onda.js           NUEVO
  estilo.css        + clases de la onda y las manijas
docs/
  PLAN_SELECTOR_DE_FRASES.md, DISENO_SELECTOR_DE_FRASES.md
CLAUDE.md           estado actualizado
```

---

### Tarea 1: Forma de onda y copia de escucha en el motor

**Archivos:**
- Modificar: `motor/audio.py` (añadir al final)
- Modificar: `tests/test_audio.py` (añadir al final)

**Interfaces:**
- Consume: `cargar_mono`, `_ejecutar`, `ErrorAudio` del propio módulo
- Produce:
  - `forma_de_onda(ruta, columnas=1200, sr_lectura=8000) -> list[float]`: pico absoluto por columna normalizado a 0..1; ceros si es silencio; lee cualquier formato pasando por ffmpeg a un WAV mono temporal a 8 kHz
  - `convertir_para_escucha(entrada, salida, bitrate="128k") -> Path`: AAC en contenedor m4a con ffmpeg

Por qué pasa por ffmpeg: `soundfile` no lee webm, opus ni m4a, que es lo que baja de YouTube. Decodificar a 8 kHz mono basta para dibujar y mantiene pequeño el temporal.

- [ ] **Paso 1: Escribir los tests que fallan**

Añadir al final de `tests/test_audio.py`:

```python
from motor.audio import convertir_para_escucha, forma_de_onda


def test_la_forma_de_onda_tiene_una_columna_por_pedido_y_va_de_0_a_1(tmp_path):
    ruta = tmp_path / "medio.wav"
    sf.write(ruta, secuencia([(440.0, 1.0), (None, 1.0)], sr=16000), 16000)
    picos = forma_de_onda(ruta, columnas=10)
    assert len(picos) == 10
    assert all(0.0 <= p <= 1.0 for p in picos)
    assert min(picos[:5]) > 0.9          # el tono ocupa la primera mitad
    # La columna 5 contiene el corte y el remuestreo de ffmpeg deja ahí un
    # rizado de hasta un 3 %; el silencio se mide a partir de la siguiente.
    assert max(picos[6:]) < 0.01


def test_la_forma_de_onda_del_silencio_es_todo_ceros(tmp_path):
    ruta = tmp_path / "silencio.wav"
    sf.write(ruta, secuencia([(None, 0.5)], sr=16000), 16000)
    assert forma_de_onda(ruta, columnas=8) == [0.0] * 8


def test_una_senal_mas_corta_que_las_columnas_no_revienta(tmp_path):
    ruta = tmp_path / "corta.wav"
    sf.write(ruta, secuencia([(440.0, 0.002)], sr=16000), 16000)
    picos = forma_de_onda(ruta, columnas=100)
    assert len(picos) == 100


def test_la_forma_de_onda_falla_con_claridad_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(ErrorAudio):
        forma_de_onda(tmp_path / "no.wav")


def test_convertir_para_escucha_produce_un_m4a_con_la_misma_duracion(tmp_path):
    ruta = tmp_path / "origen.wav"
    sf.write(ruta, secuencia([(440.0, 1.5)], sr=44100), 44100)
    salida = convertir_para_escucha(ruta, tmp_path / "escucha" / "escucha.m4a")
    assert salida.exists() and salida.suffix == ".m4a"
    assert duracion_s(salida) == pytest.approx(1.5, abs=0.15)
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest tests/test_audio.py -q`
Esperado: FALLA con `ImportError: cannot import name 'convertir_para_escucha' from 'motor.audio'`

- [ ] **Paso 3: Escribir la implementación**

Añadir al principio de `motor/audio.py`, junto a los otros imports: `import tempfile`.

Añadir al final de `motor/audio.py`:

```python
def forma_de_onda(ruta, columnas: int = 1200, sr_lectura: int = 8000) -> list[float]:
    """Pico absoluto por columna, normalizado a 0..1, para dibujar la onda.

    Pasa por ffmpeg porque soundfile no lee webm, opus ni m4a, que es lo
    que baja de YouTube. A 8 kHz mono el temporal es pequeño y sobra para
    dibujar.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"el archivo no existe: {ruta}")
    columnas = max(1, int(columnas))
    with tempfile.TemporaryDirectory() as carpeta:
        temporal = Path(carpeta) / "onda.wav"
        _ejecutar([
            "ffmpeg", "-y", "-v", "error", "-i", str(ruta),
            "-vn", "-ac", "1", "-ar", str(sr_lectura), "-c:a", "pcm_s16le",
            str(temporal),
        ])
        senal, _ = cargar_mono(temporal)
    if len(senal) == 0:
        return [0.0] * columnas
    bordes = np.linspace(0, len(senal), columnas + 1).astype(int)
    picos = np.array(
        [float(np.max(np.abs(senal[a:b]))) if b > a else 0.0 for a, b in zip(bordes[:-1], bordes[1:])],
        dtype=float,
    )
    maximo = float(picos.max())
    if maximo <= 0.0:
        return [0.0] * columnas
    return [round(float(p / maximo), 4) for p in picos]


def convertir_para_escucha(entrada, salida, bitrate: str = "128k") -> Path:
    """Copia AAC (m4a) para el navegador.

    Safari y el iPhone no reproducen webm/opus, y un WAV subido puede pesar
    50 MB. El original se conserva para recortar y analizar.
    """
    entrada, salida = Path(entrada), Path(salida)
    if not entrada.exists():
        raise ErrorAudio(f"el archivo no existe: {entrada}")
    salida.parent.mkdir(parents=True, exist_ok=True)
    _ejecutar([
        "ffmpeg", "-y", "-v", "error", "-i", str(entrada),
        "-vn", "-c:a", "aac", "-b:a", bitrate, "-movflags", "+faststart",
        str(salida),
    ])
    if not salida.exists():
        raise ErrorAudio("ffmpeg no generó el audio de escucha")
    return salida
```

- [ ] **Paso 4: Ejecutar y verificar que pasan**

Ejecutar: `py -m pytest tests/test_audio.py -q`
Esperado: 14 tests pasan (9 previos y 5 nuevos)

- [ ] **Paso 5: Commit**

```bash
git add motor/audio.py tests/test_audio.py
git commit -m "feat: forma de onda y copia de escucha en el motor de audio"
```

---

### Tarea 2: `obtener_audio` en el pipeline

**Archivos:**
- Modificar: `motor/pipeline.py` (añadir `Fuente` y `obtener_audio`; reescribir `preparar`)
- Modificar: `tests/test_pipeline.py` (añadir al final)

**Interfaces:**
- Consume: `modulo_descarga.es_url`, `obtener_info`, `descargar_audio`; `recortar`; `Config`
- Produce:
  - `Fuente(ruta: Path, titulo: str, fuente: str, referencia: str)` dataclass congelada del pipeline (no del contrato)
  - `obtener_audio(origen, cache_dir=None, titulo="", progreso=None) -> Fuente`
  - `preparar(...)` con la misma firma de hoy, ahora `obtener_audio` seguido de `recortar`

- [ ] **Paso 1: Escribir los tests que fallan**

Añadir al final de `tests/test_pipeline.py`:

```python
from motor.pipeline import Fuente, obtener_audio


def test_obtener_audio_de_un_archivo_local(cancion_larga):
    fuente = obtener_audio(cancion_larga)
    assert isinstance(fuente, Fuente)
    assert fuente.ruta == cancion_larga
    assert fuente.fuente == "archivo"
    assert fuente.referencia == "cancion.wav"
    assert fuente.titulo == "cancion"


def test_obtener_audio_de_una_url_descarga_a_la_cache(monkeypatch, cancion_larga, tmp_path):
    monkeypatch.setattr(modulo_descarga, "descargar_audio", _descarga_falsa(cancion_larga))
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    fuente = obtener_audio("https://youtu.be/abc", cache_dir=tmp_path / "origen")
    assert fuente.fuente == "youtube"
    assert fuente.titulo == "Huayno"
    assert fuente.referencia == "https://youtu.be/abc"
    assert fuente.ruta == tmp_path / "origen" / "abc.m4a"


def test_obtener_audio_avisa_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(pipeline.ErrorPipeline) as error:
        obtener_audio(tmp_path / "no_existe.wav")
    assert "no existe" in str(error.value)
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest tests/test_pipeline.py -q`
Esperado: FALLA con `ImportError: cannot import name 'Fuente' from 'motor.pipeline'`

- [ ] **Paso 3: Escribir la implementación**

En `motor/pipeline.py`, añadir a los imports: `from dataclasses import dataclass`.

Sustituir la función `preparar` completa por:

```python
@dataclass(frozen=True)
class Fuente:
    """De dónde salió el audio completo. Es del pipeline, no del contrato."""
    ruta: Path
    titulo: str
    fuente: str          # "youtube" | "archivo"
    referencia: str


def obtener_audio(origen, cache_dir=None, titulo: str = "", progreso=None) -> Fuente:
    """Descarga (con caché por id de video) o localiza el archivo. No recorta."""
    cache_dir = Path(cache_dir) if cache_dir else Config.desde_entorno().media_dir / "origen"
    if modulo_descarga.es_url(str(origen)):
        referencia = str(origen)
        _avisar(progreso, "Consultando el video")
        id_video, titulo_remoto = modulo_descarga.obtener_info(referencia)
        _avisar(progreso, "Descargando el audio")
        ruta = modulo_descarga.descargar_audio(referencia, cache_dir, id_video=id_video)
        return Fuente(
            ruta=Path(ruta), titulo=titulo or titulo_remoto or "Sin título",
            fuente="youtube", referencia=referencia,
        )
    ruta = Path(origen)
    if not ruta.exists():
        raise ErrorPipeline(f"el archivo no existe: {ruta}")
    return Fuente(ruta=ruta, titulo=titulo or ruta.stem, fuente="archivo", referencia=ruta.name)


def preparar(
    origen,
    inicio_s: float,
    fin_s: float,
    directorio_trabajo,
    titulo: str = "",
    progreso=None,
    cache_dir=None,
) -> tuple[Path, Fragmento]:
    """Obtiene el audio y recorta el rango. Devuelve (recorte, fragmento).

    Para consola y pruebas. La aplicación web ya no la usa: obtiene el audio
    una vez por canción con obtener_audio y recorta cada frase aparte.
    """
    trabajo = Path(directorio_trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    fuente = obtener_audio(origen, cache_dir=cache_dir, titulo=titulo, progreso=progreso)
    _avisar(progreso, "Recortando el fragmento")
    recorte = recortar(fuente.ruta, trabajo / "mezcla.wav", inicio_s, fin_s)
    fragmento = Fragmento(
        titulo=fuente.titulo, fuente=fuente.fuente, referencia=fuente.referencia,
        inicio_s=float(inicio_s), fin_s=float(fin_s),
    )
    return recorte, fragmento
```

- [ ] **Paso 4: Ejecutar y verificar que pasan**

Ejecutar: `py -m pytest tests -q -m "not lento"`
Esperado: 95 tests pasan (los 16 de `test_pipeline.py` previos siguen en verde, más 3 nuevos)

- [ ] **Paso 5: Commit**

```bash
git add motor/pipeline.py tests/test_pipeline.py
git commit -m "feat: obtener_audio separa la descarga del recorte en el pipeline"
```

---

### Tarea 3: La canción con estado, rutas de audio y duración

**Archivos:**
- Modificar: `web/transcripciones/models.py` (clase `Cancion`)
- Crear: `web/transcripciones/migrations/0002_cancion_estado_y_audio.py` (con `makemigrations`)
- Modificar: `web/transcripciones/tests_modelos.py` (añadir al final)

**Interfaces:**
- Produce: `Cancion` con `PENDIENTE`, `PREPARANDO`, `LISTA`, `ERROR`, `ESTADOS`, campos `origen`, `audio_original`, `audio_escucha`, `duracion_s`, `estado`, `paso`, `mensaje`, `separar`, la propiedad `lista` y el método `frases()` (fragmentos ordenados por `inicio_s`)

- [ ] **Paso 1: Escribir los tests que fallan**

Añadir al final de `web/transcripciones/tests_modelos.py`, como métodos de `PruebaModelos`:

```python
    def test_una_cancion_nace_pendiente_y_sin_audio(self):
        assert self.cancion.estado == Cancion.PENDIENTE
        assert self.cancion.lista is False
        assert self.cancion.duracion_s is None
        assert self.cancion.separar is True

    def test_las_frases_de_la_cancion_van_por_tiempo_no_por_fecha(self):
        Fragmento.objects.create(cancion=self.cancion, inicio_s=90.0, fin_s=120.0)
        Fragmento.objects.create(cancion=self.cancion, inicio_s=10.0, fin_s=20.0)
        assert [f.inicio_s for f in self.cancion.frases()] == [10.0, 30.0, 90.0]
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest web/transcripciones/tests_modelos.py -q`
Esperado: FALLA con `AttributeError: type object 'Cancion' has no attribute 'PENDIENTE'`

- [ ] **Paso 3: Escribir el modelo**

Sustituir la clase `Cancion` de `web/transcripciones/models.py` por:

```python
class Cancion(models.Model):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    LISTA = "lista"
    ERROR = "error"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (PREPARANDO, "Preparando el audio"),
        (LISTA, "Lista"),
        (ERROR, "Error"),
    ]

    titulo = models.CharField(max_length=300)
    fuente = models.CharField(
        max_length=20,
        choices=[("youtube", "YouTube"), ("archivo", "Archivo")],
        default="archivo",
    )
    referencia = models.TextField(blank=True)
    origen = models.TextField(blank=True)          # URL o ruta del archivo subido
    audio_original = models.TextField(blank=True)  # audio completo, para recortar
    audio_escucha = models.TextField(blank=True)   # m4a para el navegador
    duracion_s = models.FloatField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE)
    paso = models.CharField(max_length=120, blank=True)
    mensaje = models.TextField(blank=True)
    separar = models.BooleanField(default=True)    # última elección del usuario
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return self.titulo or "Sin título"

    @property
    def lista(self) -> bool:
        return self.estado == self.LISTA

    def frases(self):
        """Los fragmentos de la canción en el orden en que suenan."""
        return self.fragmentos.order_by("inicio_s", "pk")
```

- [ ] **Paso 4: Migración, tests y commit**

```bash
py web/manage.py makemigrations transcripciones -n cancion_estado_y_audio
py web/manage.py migrate
py -m pytest web -q
```

Esperado: 45 tests pasan (43 previos y 2 nuevos). El archivo generado es `web/transcripciones/migrations/0002_cancion_estado_y_audio.py`.

```bash
git add web/transcripciones/models.py web/transcripciones/migrations/0002_cancion_estado_y_audio.py web/transcripciones/tests_modelos.py
git commit -m "feat: la canción guarda su estado, su audio y su duración"
```

---

### Tarea 4: Trabajos por canción y por frase

Sustituye la pareja `ejecutar_preparacion` + `ejecutar_analisis` por `ejecutar_preparacion_cancion` (descarga, copia de escucha, picos) y `ejecutar_frase` (recorte más análisis, bajo el semáforo). Las vistas todavía llaman a las funciones viejas; se cambian en la tarea 6, por eso en esta tarea `views.py` no se toca y los tests de vistas que usan `lanzar_preparacion`/`lanzar_analisis` seguirán existiendo hasta entonces: para que la suite no rompa, esta tarea **conserva** `lanzar_preparacion` y `lanzar_analisis` como alias finos que lanzan los trabajos nuevos (se eliminan en la tarea 6).

**Archivos:**
- Modificar: `web/transcripciones/trabajos.py` (sustituir entero)
- Modificar: `web/transcripciones/tests_trabajos.py` (sustituir entero)

**Interfaces:**
- Consume: `motor.pipeline.obtener_audio` y `analizar_preparado`, `motor.audio.recortar`, `convertir_para_escucha`, `duracion_s`, `forma_de_onda`; los modelos
- Produce:
  - Puntos de sustitución: `_OBTENER`, `_ANALIZAR`, `_RECORTAR`, `_PREPARAR_ESCUCHA` (todos `None` por defecto)
  - `directorio_de(fragmento)`, `directorio_cancion(cancion)`, `cache_descargas()`
  - `ejecutar_preparacion_cancion(cancion_id)`, `ejecutar_frase(fragmento_id)`
  - `lanzar_preparacion_cancion(cancion_id)`, `lanzar_frase(fragmento_id)`
  - `recuperar_huerfanos() -> int` (canciones en `preparando` y fragmentos en `preparando`/`procesando`)
  - `UN_ANALISIS_A_LA_VEZ`, `MENSAJE_INTERRUMPIDO`

- [ ] **Paso 1: Escribir los tests que fallan**

Sustituir `web/transcripciones/tests_trabajos.py` entero por:

```python
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from motor.pipeline import Fuente
from transcripciones import trabajos
from transcripciones.models import Cancion, Fragmento


def _resultado_falso():
    nota = NotaContrato(orden=1, nombre="G4", midi=67, inicio_s=0.1, duracion_s=0.3,
                        confianza=0.9, cents=0)
    return Resultado(
        fragmento=FragmentoContrato(titulo="X", fuente="archivo", referencia="x.wav",
                                    inicio_s=30.0, fin_s=40.0),
        analisis=ParametrosAnalisis(separacion="ninguna", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cpu"),
        frases=(Frase(indice=1, inicio_s=0.1, fin_s=0.4, notas=(nota,)),),
        archivos={"midi": "media/x.mid"},
        avisos=(),
    )


def _fuente_falsa(**kwargs):
    return Fuente(ruta=Path("media/origen/abc.m4a"), titulo="Huayno", fuente="youtube",
                  referencia="https://youtu.be/abc")


def _escucha_falsa(ruta_original, directorio):
    return Path(directorio) / "escucha.m4a", 42.5


class PruebaTrabajos(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="X", fuente="archivo", referencia="x.wav", origen="media/subidas/x.wav",
            audio_original="media/subidas/x.wav", estado=Cancion.LISTA, duracion_s=120.0,
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, inicio_s=30.0, fin_s=40.0, separar=False,
        )

    # --- preparación de la canción ---

    def test_la_preparacion_deja_la_cancion_lista_con_audio_y_duracion(self):
        cancion = Cancion.objects.create(titulo="", fuente="youtube",
                                         referencia="https://youtu.be/abc", origen="https://youtu.be/abc")
        with patch.object(trabajos, "_OBTENER", _fuente_falsa), \
             patch.object(trabajos, "_PREPARAR_ESCUCHA", _escucha_falsa):
            trabajos.ejecutar_preparacion_cancion(cancion.pk)
        cancion.refresh_from_db()
        assert cancion.estado == Cancion.LISTA
        assert cancion.titulo == "Huayno"
        assert cancion.audio_original.endswith("abc.m4a")
        assert cancion.audio_escucha.endswith("escucha.m4a")
        assert cancion.duracion_s == 42.5
        assert cancion.paso == ""

    def test_la_preparacion_usa_la_cache_compartida_y_la_carpeta_de_la_cancion(self):
        recibido = {}

        def obtener(origen, **kwargs):
            recibido.update(kwargs)
            return _fuente_falsa()

        carpetas = []

        def escucha(ruta_original, directorio):
            carpetas.append(Path(directorio))
            return Path(directorio) / "escucha.m4a", 1.0

        with patch.object(trabajos, "_OBTENER", obtener), patch.object(trabajos, "_PREPARAR_ESCUCHA", escucha):
            trabajos.ejecutar_preparacion_cancion(self.cancion.pk)
        assert recibido["cache_dir"] == trabajos.cache_descargas()
        assert carpetas == [trabajos.directorio_cancion(self.cancion)]
        assert str(self.cancion.pk) in str(carpetas[0])

    def test_un_fallo_de_preparacion_deja_la_cancion_en_error_con_mensaje(self):
        def revienta(origen, **kwargs):
            raise RuntimeError("No se pudo descargar el audio del enlace")

        with patch.object(trabajos, "_OBTENER", revienta):
            trabajos.ejecutar_preparacion_cancion(self.cancion.pk)
        self.cancion.refresh_from_db()
        assert self.cancion.estado == Cancion.ERROR
        assert "No se pudo descargar" in self.cancion.mensaje

    # --- frases ---

    def test_ejecutar_frase_recorta_desde_el_audio_de_la_cancion_y_deja_listo(self):
        recortes = []

        def recortar(entrada, salida, inicio_s, fin_s):
            recortes.append((str(entrada), inicio_s, fin_s))
            return Path(salida)

        with patch.object(trabajos, "_RECORTAR", recortar), \
             patch.object(trabajos, "_ANALIZAR", lambda **kwargs: _resultado_falso()):
            trabajos.ejecutar_frase(self.fragmento.pk)
        self.fragmento.refresh_from_db()
        assert recortes == [("media/subidas/x.wav", 30.0, 40.0)]
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.notas.count() == 1

    def test_el_analisis_recibe_el_recorte_y_el_fragmento_del_contrato(self):
        recibido = {}

        def analizar(**kwargs):
            recibido.update(kwargs)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert str(recibido["recorte"]).endswith("mezcla.wav")
        assert recibido["fragmento"].inicio_s == 30.0
        assert recibido["fragmento"].titulo == "X"
        assert recibido["separar"] is False

    def test_el_progreso_se_guarda_en_el_paso(self):
        pasos_vistos = []

        def analizar(**kwargs):
            kwargs["progreso"]("Separando la pista melódica")
            pasos_vistos.append(Fragmento.objects.get(pk=self.fragmento.pk).paso)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert pasos_vistos == ["Separando la pista melódica"]

    def test_la_frase_corre_con_el_semaforo_tomado_y_lo_devuelve(self):
        libres_durante = []

        def analizar(**kwargs):
            libres_durante.append(trabajos.UN_ANALISIS_A_LA_VEZ._value)
            return _resultado_falso()

        with patch.object(trabajos, "_RECORTAR", lambda e, s, i, f: Path(s)), \
             patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert libres_durante == [0]
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1

    def test_el_semaforo_se_devuelve_y_queda_error_si_el_recorte_falla(self):
        def revienta(entrada, salida, inicio_s, fin_s):
            raise RuntimeError("el rango pedido llega hasta 40.0 s pero la duración del audio es de 35.0 s")

        with patch.object(trabajos, "_RECORTAR", revienta):
            trabajos.ejecutar_frase(self.fragmento.pk)
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "duración del audio" in self.fragmento.mensaje

    # --- recuperación ---

    def test_recuperar_huerfanos_cubre_canciones_y_frases(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.save()
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.save()
        otra = Cancion.objects.create(titulo="Y", estado=Cancion.LISTA)
        assert trabajos.recuperar_huerfanos() == 2
        self.cancion.refresh_from_db()
        self.fragmento.refresh_from_db()
        otra.refresh_from_db()
        assert self.cancion.estado == Cancion.ERROR
        assert "interrumpi" in self.cancion.mensaje
        assert self.fragmento.estado == Fragmento.ERROR
        assert otra.estado == Cancion.LISTA

    def test_el_comando_recuperar_trabajos_existe(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.save()
        call_command("recuperar_trabajos")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_los_directorios_son_propios_de_cada_objeto(self):
        assert str(self.fragmento.pk) in str(trabajos.directorio_de(self.fragmento))
        assert "canciones" in str(trabajos.directorio_cancion(self.cancion))
        assert str(self.cancion.pk) in str(trabajos.directorio_cancion(self.cancion))
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest web/transcripciones/tests_trabajos.py -q`
Esperado: FALLA con `AttributeError: module 'transcripciones.trabajos' has no attribute '_OBTENER'` (o equivalente)

- [ ] **Paso 3: Escribir la implementación**

Sustituir `web/transcripciones/trabajos.py` entero por:

```python
"""Ejecución de los trabajos largos fuera del ciclo de la petición HTTP.

Dos trabajos: preparar una canción (descargar o localizar el audio, hacer
la copia de escucha y los picos de la onda) y analizar una frase (recortar
y analizar). Para un solo usuario en local un hilo basta; la pieza está
aislada para poder sustituirla por una cola real sin tocar vistas ni motor.
"""
from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path

from django.conf import settings
from django.db import connection

from motor.contrato import Fragmento as FragmentoContrato

# Puntos de sustitución para las pruebas. None significa "usar el real",
# que se importa dentro de las funciones.
_OBTENER = None            # obtener_audio(origen, cache_dir=, titulo=, progreso=) -> Fuente
_ANALIZAR = None           # analizar_preparado(recorte=, fragmento=, separar=, progreso=) -> Resultado
_RECORTAR = None           # recortar(entrada, salida, inicio_s, fin_s) -> Path
_PREPARAR_ESCUCHA = None   # (ruta_original, directorio) -> (ruta_escucha, duracion_s)

# Demucs y CREPE no caben dos veces en 4 GB de VRAM. El segundo espera.
UN_ANALISIS_A_LA_VEZ = threading.Semaphore(1)

MENSAJE_INTERRUMPIDO = "El trabajo se interrumpió (se cerró el programa a mitad). Reintenta."


def _obtener_real():
    if _OBTENER is not None:
        return _OBTENER
    from motor.pipeline import obtener_audio
    return obtener_audio


def _analizar_real():
    if _ANALIZAR is not None:
        return _ANALIZAR
    from motor.pipeline import analizar_preparado
    return analizar_preparado


def _recortar_real():
    if _RECORTAR is not None:
        return _RECORTAR
    from motor.audio import recortar
    return recortar


def _preparar_escucha(ruta_original, directorio):
    """Copia AAC para el navegador y picos de la onda en JSON. Devuelve (escucha, duración)."""
    if _PREPARAR_ESCUCHA is not None:
        return _PREPARAR_ESCUCHA(ruta_original, directorio)
    from motor.audio import convertir_para_escucha, duracion_s, forma_de_onda

    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    escucha = convertir_para_escucha(ruta_original, directorio / "escucha.m4a")
    (directorio / "onda.json").write_text(json.dumps(forma_de_onda(ruta_original)), encoding="utf-8")
    return escucha, duracion_s(ruta_original)


def directorio_de(fragmento) -> Path:
    return Path(settings.MEDIA_ROOT) / "fragmentos" / str(fragmento.pk)


def directorio_cancion(cancion) -> Path:
    return Path(settings.MEDIA_ROOT) / "canciones" / str(cancion.pk)


def cache_descargas() -> Path:
    """Compartida por todas las canciones: un video se baja una sola vez."""
    return Path(settings.MEDIA_ROOT) / "origen"


def _progreso_de(fragmento_id):
    from .models import Fragmento

    def progreso(mensaje):
        Fragmento.objects.filter(pk=fragmento_id).update(paso=mensaje)

    return progreso


def _progreso_cancion(cancion_id):
    from .models import Cancion

    def progreso(mensaje):
        Cancion.objects.filter(pk=cancion_id).update(paso=mensaje)

    return progreso


def _marcar_error(fragmento_id, error):
    from .models import Fragmento

    traceback.print_exc()
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.ERROR, paso="", mensaje=str(error)
    )


def _marcar_error_cancion(cancion_id, error):
    from .models import Cancion

    traceback.print_exc()
    Cancion.objects.filter(pk=cancion_id).update(
        estado=Cancion.ERROR, paso="", mensaje=str(error)
    )


def ejecutar_preparacion_cancion(cancion_id: int) -> None:
    """Descarga o localiza el audio, hace la copia de escucha y los picos. No usa la GPU."""
    from .models import Cancion

    cancion = Cancion.objects.get(pk=cancion_id)
    Cancion.objects.filter(pk=cancion_id).update(
        estado=Cancion.PREPARANDO, paso="Preparando", mensaje=""
    )
    progreso = _progreso_cancion(cancion_id)
    try:
        fuente = _obtener_real()(
            origen=cancion.origen, cache_dir=cache_descargas(), titulo=cancion.titulo, progreso=progreso,
        )
        progreso("Preparando el audio para escucharlo")
        escucha, duracion = _preparar_escucha(fuente.ruta, directorio_cancion(cancion))
        Cancion.objects.filter(pk=cancion_id).update(
            titulo=fuente.titulo, fuente=fuente.fuente, referencia=fuente.referencia,
            audio_original=str(fuente.ruta), audio_escucha=str(escucha), duracion_s=float(duracion),
            estado=Cancion.LISTA, paso="", mensaje="",
        )
    except Exception as error:  # noqa: BLE001
        _marcar_error_cancion(cancion_id, error)
    finally:
        connection.close()


def ejecutar_frase(fragmento_id: int) -> None:
    """Recorta la frase desde el audio de la canción y la analiza, de a una."""
    from .models import Fragmento

    fragmento = Fragmento.objects.select_related("cancion").get(pk=fragmento_id)
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    progreso = _progreso_de(fragmento_id)
    try:
        with UN_ANALISIS_A_LA_VEZ:
            progreso("Recortando el fragmento")
            recorte = _recortar_real()(
                fragmento.cancion.audio_original,
                directorio_de(fragmento) / "mezcla.wav",
                fragmento.inicio_s,
                fragmento.fin_s,
            )
            resultado = _analizar_real()(
                recorte=recorte,
                fragmento=FragmentoContrato(
                    titulo=fragmento.cancion.titulo,
                    fuente=fragmento.cancion.fuente,
                    referencia=fragmento.cancion.referencia,
                    inicio_s=fragmento.inicio_s,
                    fin_s=fragmento.fin_s,
                ),
                separar=fragmento.separar,
                progreso=progreso,
            )
        fragmento.refresh_from_db()
        fragmento.guardar_resultado(resultado)
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def lanzar_preparacion_cancion(cancion_id: int) -> None:
    threading.Thread(target=ejecutar_preparacion_cancion, args=(cancion_id,), daemon=True).start()


def lanzar_frase(fragmento_id: int) -> None:
    threading.Thread(target=ejecutar_frase, args=(fragmento_id,), daemon=True).start()


# Alias provisionales: las vistas de la tarea 17 del plan anterior los usan
# hasta que la tarea 6 de este plan las sustituya. Se eliminan entonces.
def lanzar_preparacion(fragmento_id: int, origen: str) -> None:
    lanzar_frase(fragmento_id)


def lanzar_analisis(fragmento_id: int) -> None:
    lanzar_frase(fragmento_id)


def recuperar_huerfanos() -> int:
    """Al arrancar: lo que quedó a medias en la sesión anterior pasa a error."""
    from .models import Cancion, Fragmento

    canciones = Cancion.objects.filter(estado=Cancion.PREPARANDO).update(
        estado=Cancion.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO
    )
    fragmentos = Fragmento.objects.filter(
        estado__in=[Fragmento.PREPARANDO, Fragmento.PROCESANDO]
    ).update(estado=Fragmento.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO)
    return canciones + fragmentos
```

- [ ] **Paso 4: Ejecutar y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 45 tests pasan (7 modelos, 11 trabajos, 27 vistas). Los tests de vistas que parchean `lanzar_preparacion`/`lanzar_analisis` siguen pasando gracias a los alias.

- [ ] **Paso 5: Commit**

```bash
git add web/transcripciones/trabajos.py web/transcripciones/tests_trabajos.py
git commit -m "feat: trabajos por canción (preparar audio) y por frase (recortar y analizar)"
```

---

### Tarea 5: Audio con `Range`

**Archivos:**
- Crear: `web/transcripciones/audio_http.py`
- Crear: `web/transcripciones/tests_audio_http.py`
- Modificar: `web/transcripciones/views.py` (la vista `audio` usa el helper)

**Interfaces:**
- Produce: `respuesta_audio(ruta, request) -> HttpResponse` que atiende `Range: bytes=a-b`, `bytes=a-` y `bytes=-n` con 206 y `Content-Range`, devuelve 200 completo sin cabecera y 416 si el rango no cabe; `TIPOS_AUDIO` por extensión

- [ ] **Paso 1: Escribir los tests que fallan**

Crear `web/transcripciones/tests_audio_http.py`:

```python
import tempfile
from pathlib import Path

from django.test import RequestFactory, SimpleTestCase

from transcripciones.audio_http import respuesta_audio


def _cuerpo(respuesta) -> bytes:
    if hasattr(respuesta, "streaming_content"):
        return b"".join(respuesta.streaming_content)
    return respuesta.content


class PruebaRange(SimpleTestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.ruta = Path(self.carpeta.name) / "pista.wav"
        self.ruta.write_bytes(bytes(range(256)) * 4)   # 1024 bytes conocidos
        self.fabrica = RequestFactory()

    def tearDown(self):
        self.carpeta.cleanup()

    def test_sin_range_devuelve_todo_y_anuncia_que_acepta_rangos(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a"))
        assert respuesta.status_code == 200
        assert respuesta["Accept-Ranges"] == "bytes"
        assert respuesta["Content-Length"] == "1024"
        assert respuesta["Content-Type"] == "audio/wav"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()

    def test_un_rango_cerrado_devuelve_206_con_content_range(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=0-99"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 0-99/1024"
        assert respuesta["Content-Length"] == "100"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()[:100]

    def test_un_rango_abierto_llega_hasta_el_final(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=1000-"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 1000-1023/1024"
        assert _cuerpo(respuesta) == self.ruta.read_bytes()[1000:]

    def test_un_sufijo_devuelve_los_ultimos_bytes(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=-24"))
        assert respuesta.status_code == 206
        assert respuesta["Content-Range"] == "bytes 1000-1023/1024"

    def test_un_rango_fuera_del_archivo_da_416(self):
        respuesta = respuesta_audio(self.ruta, self.fabrica.get("/a", HTTP_RANGE="bytes=5000-"))
        assert respuesta.status_code == 416
        assert respuesta["Content-Range"] == "bytes */1024"

    def test_el_tipo_sale_de_la_extension(self):
        m4a = self.ruta.with_suffix(".m4a")
        m4a.write_bytes(b"x" * 10)
        assert respuesta_audio(m4a, self.fabrica.get("/a"))["Content-Type"] == "audio/mp4"
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest web/transcripciones/tests_audio_http.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'transcripciones.audio_http'`

- [ ] **Paso 3: Escribir la implementación**

Crear `web/transcripciones/audio_http.py`:

```python
"""Servir audio con soporte de Range.

Sin respuestas 206, saltar dentro de una canción de cinco minutos no
funciona bien en Chrome y no funciona en Safari. FileResponse de Django
no lo hace, así que se hace aquí, para un solo rango por petición.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

_RANGO = re.compile(r"^bytes=(\d*)-(\d*)$")
_TROZO = 64 * 1024

TIPOS_AUDIO = {
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}


def _trozos(ruta: Path, inicio: int, longitud: int):
    with open(ruta, "rb") as archivo:
        archivo.seek(inicio)
        restante = longitud
        while restante > 0:
            datos = archivo.read(min(_TROZO, restante))
            if not datos:
                break
            restante -= len(datos)
            yield datos


def respuesta_audio(ruta, request):
    ruta = Path(ruta)
    tamano = ruta.stat().st_size
    tipo = TIPOS_AUDIO.get(ruta.suffix.lower(), "application/octet-stream")
    coincidencia = _RANGO.match(request.META.get("HTTP_RANGE", ""))

    if not coincidencia or coincidencia.group(1) == coincidencia.group(2) == "":
        respuesta = FileResponse(open(ruta, "rb"), content_type=tipo)
        respuesta["Accept-Ranges"] = "bytes"
        respuesta["Content-Length"] = str(tamano)
        return respuesta

    desde, hasta = coincidencia.groups()
    if desde == "":                       # bytes=-n: los últimos n bytes
        inicio = max(0, tamano - int(hasta))
        fin = tamano - 1
    else:
        inicio = int(desde)
        fin = int(hasta) if hasta else tamano - 1
    fin = min(fin, tamano - 1)
    if inicio >= tamano or inicio > fin:
        respuesta = HttpResponse(status=416)
        respuesta["Content-Range"] = f"bytes */{tamano}"
        return respuesta

    longitud = fin - inicio + 1
    respuesta = StreamingHttpResponse(_trozos(ruta, inicio, longitud), status=206, content_type=tipo)
    respuesta["Content-Range"] = f"bytes {inicio}-{fin}/{tamano}"
    respuesta["Content-Length"] = str(longitud)
    respuesta["Accept-Ranges"] = "bytes"
    return respuesta
```

En `web/transcripciones/views.py`, añadir el import `from .audio_http import respuesta_audio` y sustituir la vista `audio` por:

```python
def audio(request, pk, clave):
    """Entrega el audio para reproducirlo en la página, con soporte de Range."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    return respuesta_audio(_archivo_de(fragmento, clave), request)
```

- [ ] **Paso 4: Ejecutar y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 51 tests pasan (45 previos y 6 nuevos)

- [ ] **Paso 5: Commit**

```bash
git add web/transcripciones/audio_http.py web/transcripciones/tests_audio_http.py web/transcripciones/views.py
git commit -m "feat: el audio se sirve con soporte de Range"
```

---

### Tarea 6: Vistas, rutas, formulario y plantillas del flujo por canción

La tarea grande. Sustituye el formulario con tiempos por "enlace o archivo", crea la pantalla de la canción con sus JSON, la creación de frases por POST y el reintento por canción, y adapta detalle e historial. El JavaScript de la onda es la tarea 7; aquí la plantilla de la canción ya deja el HTML que ese JS necesita.

**Archivos:**
- Modificar: `web/transcripciones/formularios.py` (sustituir `FormularioFragmento` por `FormularioCancion`; conservar `parsear_tiempo`)
- Modificar: `web/transcripciones/views.py` (sustituir entero)
- Modificar: `web/transcripciones/urls.py` (sustituir entero)
- Modificar: `web/transcripciones/trabajos.py` (borrar los alias `lanzar_preparacion` y `lanzar_analisis`)
- Modificar: plantillas `index.html`, `detalle.html`, `historial.html`; crear `cancion.html`
- Modificar: `web/transcripciones/tests_vistas.py` (sustituir entero)

**Interfaces:**
- Consume: `trabajos.lanzar_preparacion_cancion`, `trabajos.lanzar_frase`, `trabajos.directorio_cancion`, `respuesta_audio`, `parsear_tiempo`, `Config.max_fragmento_s`
- Produce: rutas con nombre `index`, `cancion`, `cancion_estado`, `cancion_onda`, `cancion_escucha`, `crear_frase`, `cancion_reintentar`, `detalle`, `estado`, `reintentar`, `datos`, `audio`, `descargar`, `historial`; el JSON de `cancion_estado`:

```json
{"estado": "lista", "paso": "", "mensaje": "", "titulo": "Huayno", "duracion_s": 200.0,
 "max_fragmento_s": 180.0, "separar": true,
 "frases": [{"id": 3, "inicio_s": 10.0, "fin_s": 25.0, "estado": "listo", "etiqueta": "Listo",
             "paso": "", "mensaje": "", "url": "/fragmento/3/"}]}
```

y el de `cancion_onda`: `{"duracion_s": 200.0, "picos": [0.1, 0.4, ...]}`.

- [ ] **Paso 1: Escribir los tests que fallan**

Sustituir `web/transcripciones/tests_vistas.py` entero por:

```python
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from transcripciones.formularios import parsear_tiempo
from transcripciones.models import Cancion, Fragmento, Nota


def test_parsear_tiempo_acepta_los_tres_formatos():
    assert parsear_tiempo("90") == 90.0
    assert parsear_tiempo("1:30") == 90.0
    assert parsear_tiempo("1:30.5") == 90.5
    assert parsear_tiempo("0:07") == 7.0


def test_parsear_tiempo_rechaza_basura():
    for texto in ["", "abc", "1:2:3", "-5", "1:75"]:
        with pytest.raises(ValueError):
            parsear_tiempo(texto)


class PruebaVistas(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="Huayno", fuente="youtube", referencia="https://youtu.be/abc",
            origen="https://youtu.be/abc", audio_original="media/origen/abc.m4a",
            audio_escucha="media/canciones/1/escucha.m4a", duracion_s=200.0,
            estado=Cancion.LISTA,
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, origen="https://youtu.be/abc",
            inicio_s=30.0, fin_s=90.0, separar=True,
        )

    # --- inicio ---

    def test_el_index_responde_y_ya_no_pide_tiempos(self):
        respuesta = self.client.get(reverse("index"))
        assert respuesta.status_code == 200
        assert b"YouTube" in respuesta.content
        assert b'name="inicio"' not in respuesta.content

    def test_enviar_una_url_crea_la_cancion_y_lanza_su_preparacion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("index"), {"url": "https://youtu.be/xyz"})
        creada = Cancion.objects.get(referencia="https://youtu.be/xyz")
        assert respuesta.status_code == 302
        assert respuesta["Location"] == reverse("cancion", args=[creada.pk])
        assert creada.origen == "https://youtu.be/xyz"
        assert creada.estado == Cancion.PREPARANDO
        lanzar.assert_called_once_with(creada.pk)

    def test_la_misma_url_reutiliza_la_cancion_y_no_la_vuelve_a_preparar(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("index"), {"url": "https://youtu.be/abc"})
        assert Cancion.objects.filter(referencia="https://youtu.be/abc").count() == 1
        assert respuesta["Location"] == reverse("cancion", args=[self.cancion.pk])
        lanzar.assert_not_called()

    def test_una_cancion_en_error_se_vuelve_a_preparar_al_enviar_su_url(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            self.client.post(reverse("index"), {"url": "https://youtu.be/abc"})
        lanzar.assert_called_once_with(self.cancion.pk)

    def test_subir_un_archivo_crea_la_cancion_con_su_ruta(self):
        with tempfile.TemporaryDirectory() as carpeta, override_settings(MEDIA_ROOT=carpeta):
            archivo = SimpleUploadedFile("ensayo.mp3", b"ID3fingido", content_type="audio/mpeg")
            with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
                self.client.post(reverse("index"), {"archivo": archivo})
            creada = Cancion.objects.get(fuente="archivo")
            assert creada.titulo == "ensayo"
            assert creada.origen.endswith("ensayo.mp3")
            assert Path(creada.origen).exists()
            lanzar.assert_called_once_with(creada.pk)

    def test_enviar_vacio_muestra_el_error(self):
        respuesta = self.client.post(reverse("index"), {})
        assert respuesta.status_code == 200
        assert "Pega un enlace".encode() in respuesta.content
        assert Cancion.objects.count() == 1

    # --- canción ---

    def test_la_cancion_lista_muestra_el_selector(self):
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert respuesta.status_code == 200
        assert b'id="onda"' in respuesta.content
        assert "Analizar esta selección".encode() in respuesta.content
        assert reverse("cancion_onda", args=[self.cancion.pk]).encode() in respuesta.content

    def test_la_cancion_en_preparacion_muestra_el_paso(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.paso = "Descargando el audio"
        self.cancion.save()
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert "Descargando el audio".encode() in respuesta.content
        assert b'id="onda"' not in respuesta.content

    def test_la_cancion_en_error_ofrece_reintentar(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.mensaje = "No se pudo descargar el audio del enlace"
        self.cancion.save()
        respuesta = self.client.get(reverse("cancion", args=[self.cancion.pk]))
        assert "No se pudo descargar".encode() in respuesta.content
        assert reverse("cancion_reintentar", args=[self.cancion.pk]).encode() in respuesta.content

    def test_el_estado_de_la_cancion_trae_sus_frases_en_orden(self):
        Fragmento.objects.create(cancion=self.cancion, inicio_s=5.0, fin_s=15.0,
                                 estado=Fragmento.LISTO)
        datos = self.client.get(reverse("cancion_estado", args=[self.cancion.pk])).json()
        assert datos["estado"] == "lista"
        assert datos["duracion_s"] == 200.0
        assert datos["max_fragmento_s"] == 180.0
        assert datos["separar"] is True
        assert [f["inicio_s"] for f in datos["frases"]] == [5.0, 30.0]
        assert datos["frases"][0]["estado"] == "listo"
        assert datos["frases"][0]["url"] == reverse("detalle", args=[datos["frases"][0]["id"]])

    def test_la_onda_da_404_si_todavia_no_existe(self):
        respuesta = self.client.get(reverse("cancion_onda", args=[self.cancion.pk]))
        assert respuesta.status_code == 404

    def test_la_onda_devuelve_los_picos_guardados(self):
        with tempfile.TemporaryDirectory() as carpeta, override_settings(MEDIA_ROOT=carpeta):
            directorio = Path(carpeta) / "canciones" / str(self.cancion.pk)
            directorio.mkdir(parents=True)
            (directorio / "onda.json").write_text(json.dumps([0.0, 0.5, 1.0]), encoding="utf-8")
            datos = self.client.get(reverse("cancion_onda", args=[self.cancion.pk])).json()
        assert datos["picos"] == [0.0, 0.5, 1.0]
        assert datos["duracion_s"] == 200.0

    def test_la_escucha_sirve_el_m4a_con_range(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "escucha.m4a"
            ruta.write_bytes(b"0123456789")
            self.cancion.audio_escucha = str(ruta)
            self.cancion.save()
            respuesta = self.client.get(reverse("cancion_escucha", args=[self.cancion.pk]),
                                        HTTP_RANGE="bytes=0-3")
            assert respuesta.status_code == 206
            assert respuesta["Content-Range"] == "bytes 0-3/10"
            assert b"".join(respuesta.streaming_content) == b"0123"

    def test_la_escucha_da_404_si_no_hay_archivo(self):
        respuesta = self.client.get(reverse("cancion_escucha", args=[self.cancion.pk]))
        assert respuesta.status_code == 404

    # --- crear frases ---

    def _crear(self, **campos):
        return self.client.post(reverse("crear_frase", args=[self.cancion.pk]), campos)

    def test_crear_una_frase_valida_la_deja_en_cola_y_lanza_el_trabajo(self):
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self._crear(inicio_s="10.5", fin_s="25", separar="true")
        assert respuesta.status_code == 201
        datos = respuesta.json()
        frase = Fragmento.objects.get(pk=datos["id"])
        assert frase.inicio_s == 10.5 and frase.fin_s == 25.0
        assert frase.estado == Fragmento.PROCESANDO and frase.paso == "En cola"
        assert frase.separar is True
        assert frase.origen == "https://youtu.be/abc"
        assert datos["url"] == reverse("detalle", args=[frase.pk])
        lanzar.assert_called_once_with(frase.pk)

    def test_crear_una_frase_acepta_tiempos_en_m_ss_y_recuerda_la_casilla(self):
        with patch("transcripciones.views.trabajos.lanzar_frase"):
            respuesta = self._crear(inicio_s="1:00", fin_s="1:30", separar="false")
        assert respuesta.status_code == 201
        frase = Fragmento.objects.get(pk=respuesta.json()["id"])
        assert frase.inicio_s == 60.0 and frase.fin_s == 90.0
        assert frase.separar is False
        self.cancion.refresh_from_db()
        assert self.cancion.separar is False

    def test_una_seleccion_invertida_corta_larga_o_fuera_da_400(self):
        casos = [
            dict(inicio_s="50", fin_s="40"),      # invertida
            dict(inicio_s="10", fin_s="10.5"),    # menos de 1 s
            dict(inicio_s="0", fin_s="190"),      # más de 180 s
            dict(inicio_s="150", fin_s="210"),    # más allá de la duración (200)
            dict(inicio_s="abc", fin_s="10"),     # basura
        ]
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            for campos in casos:
                respuesta = self._crear(**campos)
                assert respuesta.status_code == 400, campos
                assert "error" in respuesta.json()
        lanzar.assert_not_called()
        assert Fragmento.objects.count() == 1

    def test_no_se_pueden_crear_frases_si_la_cancion_no_esta_lista(self):
        self.cancion.estado = Cancion.PREPARANDO
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self._crear(inicio_s="0", fin_s="10")
        assert respuesta.status_code == 409
        lanzar.assert_not_called()

    def test_crear_frase_solo_acepta_post(self):
        respuesta = self.client.get(reverse("crear_frase", args=[self.cancion.pk]))
        assert respuesta.status_code == 405

    # --- reintentos ---

    def test_reintentar_una_frase_en_error_la_relanza(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            respuesta = self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PROCESANDO

    def test_reintentar_no_hace_nada_si_la_frase_no_esta_en_error(self):
        with patch("transcripciones.views.trabajos.lanzar_frase") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_not_called()

    def test_reintentar_la_cancion_en_error_la_vuelve_a_preparar(self):
        self.cancion.estado = Cancion.ERROR
        self.cancion.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion_cancion") as lanzar:
            respuesta = self.client.post(reverse("cancion_reintentar", args=[self.cancion.pk]))
        lanzar.assert_called_once_with(self.cancion.pk)
        assert respuesta["Location"] == reverse("cancion", args=[self.cancion.pk])
        self.cancion.refresh_from_db()
        assert self.cancion.estado == Cancion.PREPARANDO

    # --- detalle y resultado ---

    def _dejar_listo(self):
        self.fragmento.estado = Fragmento.LISTO
        self.fragmento.archivos = {"midi": "media/x.mid", "txt": "media/x.txt"}
        self.fragmento.avisos = ["La confianza media es baja."]
        self.fragmento.save()
        Nota.objects.create(fragmento=self.fragmento, frase=1, orden=1, nombre="G4",
                            midi=67, inicio_s=0.4, duracion_s=0.42, confianza=0.93, cents=-12)
        Nota.objects.create(fragmento=self.fragmento, frase=2, orden=2, nombre="B4",
                            midi=71, inicio_s=2.0, duracion_s=0.60, confianza=0.40, cents=30)

    def test_el_detalle_en_proceso_muestra_el_paso_y_el_enlace_a_la_cancion(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.paso = "Separando la pista melódica"
        self.fragmento.save()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "Separando la pista".encode() in contenido
        assert reverse("cancion", args=[self.cancion.pk]).encode() in contenido
        assert b"Analizar</button>" not in contenido

    def test_el_detalle_muestra_el_mensaje_de_error_y_reintentar(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.mensaje = "CUDA out of memory"
        self.fragmento.save()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"CUDA out of memory" in contenido
        assert reverse("reintentar", args=[self.fragmento.pk]).encode() in contenido

    def test_el_resultado_muestra_las_notas_agrupadas_por_frase(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Frase 1" in contenido and b"Frase 2" in contenido
        assert b"G4" in contenido and b"B4" in contenido
        assert "alta".encode() in contenido and "baja".encode() in contenido

    def test_el_resultado_muestra_los_avisos_y_la_limitacion(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "confianza media es baja".encode() in contenido
        assert "una sola nota larga".encode() in contenido

    def test_el_resultado_solo_ofrece_descargar_los_archivos_que_existen(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Descargar MIDI" in contenido
        assert b"Descargar PDF" not in contenido

    def test_descargar_un_archivo_que_no_existe_da_404(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("descargar", args=[self.fragmento.pk, "pdf"]))
        assert respuesta.status_code == 404

    def test_el_estado_del_fragmento_se_consulta_en_json(self):
        respuesta = self.client.get(reverse("estado", args=[self.fragmento.pk]))
        assert respuesta.json() == {"estado": "pendiente", "paso": "", "mensaje": "", "avisos": []}

    def test_los_datos_del_lienzo_traen_notas_frases_y_pistas(self):
        self._dejar_listo()
        datos = self.client.get(reverse("datos", args=[self.fragmento.pk])).json()
        assert datos["duracion_s"] == 60.0
        assert datos["desplazamiento_s"] == 30.0
        assert [nota["nombre"] for nota in datos["notas"]] == ["G4", "B4"]
        assert [nota["etiqueta"] for nota in datos["notas"]] == ["alta", "baja"]
        assert [frase["indice"] for frase in datos["frases"]] == [1, 2]
        assert datos["pistas"] == []

    def test_los_datos_solo_listan_las_pistas_que_existen(self):
        self._dejar_listo()
        with tempfile.TemporaryDirectory() as carpeta:
            temporal = Path(carpeta) / "mezcla.wav"
            temporal.write_bytes(b"RIFF")
            self.fragmento.archivos = {**self.fragmento.archivos, "mezcla_wav": str(temporal)}
            self.fragmento.save()
            datos = self.client.get(reverse("datos", args=[self.fragmento.pk])).json()
        assert [p["clave"] for p in datos["pistas"]] == ["mezcla_wav"]

    # --- historial ---

    def test_el_historial_lista_canciones_con_sus_frases(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("historial")).content
        assert b"Huayno" in contenido
        assert reverse("cancion", args=[self.cancion.pk]).encode() in contenido
        assert reverse("detalle", args=[self.fragmento.pk]).encode() in contenido
```

- [ ] **Paso 2: Ejecutar y verificar que fallan**

Ejecutar: `py -m pytest web/transcripciones/tests_vistas.py -q`
Esperado: FALLA (por ejemplo `NoReverseMatch: Reverse for 'cancion' not found`)

- [ ] **Paso 3: Escribir `formularios.py`**

Sustituir la clase `FormularioFragmento` (y solo ella; `parsear_tiempo` y `_PATRON` se conservan) por:

```python
class FormularioCancion(forms.Form):
    url = forms.CharField(required=False)
    archivo = forms.FileField(required=False)

    def clean(self):
        datos = super().clean()
        if not (datos.get("url") or "").strip() and not datos.get("archivo"):
            raise forms.ValidationError("Pega un enlace de YouTube o sube un archivo.")
        return datos
```

Como `Config` ya no se usa en este archivo, quitar su import.

- [ ] **Paso 4: Escribir `views.py`**

Sustituir `web/transcripciones/views.py` entero por:

```python
import json
from pathlib import Path

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from motor.config import Config
from motor.contrato import formato_tiempo

from . import trabajos
from .audio_http import respuesta_audio
from .formularios import FormularioCancion, parsear_tiempo
from .models import Cancion, Fragmento

NOMBRES_DESCARGA = {"midi": "melodia.mid", "txt": "notas.txt", "pdf": "notas.pdf"}
SELECCION_MINIMA_S = 1.0
TOLERANCIA_FIN_S = 0.25   # la misma que recortar()


# --- inicio ---

def index(request):
    # Se vincula siempre que sea POST: con `request.POST or None` un envío
    # vacío (QueryDict vacío es falsy) dejaría el formulario sin vincular y
    # el error "Pega un enlace o sube un archivo" nunca se mostraría.
    es_envio = request.method == "POST"
    formulario = FormularioCancion(
        request.POST if es_envio else None, request.FILES if es_envio else None,
    )
    if es_envio and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("archivo"):
            ruta = _guardar_subida(datos["archivo"])
            cancion = Cancion.objects.create(
                titulo=ruta.stem, fuente="archivo", referencia=ruta.name, origen=str(ruta),
            )
        else:
            url = datos["url"].strip()
            # La misma URL es la misma canción: la descarga ya está en caché y
            # el historial no se llena de repeticiones.
            cancion = Cancion.objects.filter(fuente="youtube", referencia=url).first()
            if cancion is None:
                cancion = Cancion.objects.create(titulo="", fuente="youtube", referencia=url, origen=url)
        _preparar_si_hace_falta(cancion)
        return redirect("cancion", pk=cancion.pk)

    return render(request, "transcripciones/index.html", {
        "formulario": formulario,
        "recientes": Cancion.objects.all()[:8],
    })


def _guardar_subida(archivo) -> Path:
    """default_storage añade un sufijo si ya existe un archivo con ese nombre."""
    nombre = default_storage.save(f"subidas/{archivo.name}", archivo)
    return Path(default_storage.path(nombre))


def _preparar_si_hace_falta(cancion):
    """Lanza la preparación salvo que ya esté lista o en marcha. Atómico."""
    actualizados = Cancion.objects.filter(pk=cancion.pk).exclude(
        estado__in=[Cancion.LISTA, Cancion.PREPARANDO]
    ).update(estado=Cancion.PREPARANDO, paso="Preparando", mensaje="")
    if actualizados:
        trabajos.lanzar_preparacion_cancion(cancion.pk)


# --- canción ---

def cancion(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    return render(request, "transcripciones/cancion.html", {
        "cancion": cancion,
        "frases": cancion.frases(),
        "duracion": formato_tiempo(cancion.duracion_s or 0),
    })


def _frase_a_dict(fragmento):
    return {
        "id": fragmento.pk,
        "inicio_s": fragmento.inicio_s,
        "fin_s": fragmento.fin_s,
        "estado": fragmento.estado,
        "etiqueta": fragmento.get_estado_display(),
        "paso": fragmento.paso,
        "mensaje": fragmento.mensaje,
        "url": reverse("detalle", args=[fragmento.pk]),
    }


def cancion_estado(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    return JsonResponse({
        "estado": cancion.estado,
        "paso": cancion.paso,
        "mensaje": cancion.mensaje,
        "titulo": cancion.titulo,
        "duracion_s": cancion.duracion_s,
        "max_fragmento_s": Config.desde_entorno().max_fragmento_s,
        "separar": cancion.separar,
        "frases": [_frase_a_dict(f) for f in cancion.frases()],
    })


def cancion_onda(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    ruta = trabajos.directorio_cancion(cancion) / "onda.json"
    if not cancion.lista or not ruta.exists():
        raise Http404("la forma de onda todavía no existe")
    return JsonResponse({
        "duracion_s": cancion.duracion_s,
        "picos": json.loads(ruta.read_text(encoding="utf-8")),
    })


def cancion_escucha(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    if not cancion.audio_escucha or not Path(cancion.audio_escucha).exists():
        raise Http404("el audio de escucha todavía no existe")
    return respuesta_audio(cancion.audio_escucha, request)


def _leer_tiempo(texto) -> float:
    """Acepta segundos con decimales ('10.5') o m:ss ('1:30')."""
    texto = str(texto or "").strip()
    try:
        return float(texto)
    except ValueError:
        return parsear_tiempo(texto)


@require_POST
def crear_frase(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    if not cancion.lista:
        return JsonResponse({"error": "La canción todavía no está lista."}, status=409)
    try:
        inicio = _leer_tiempo(request.POST.get("inicio_s"))
        fin = _leer_tiempo(request.POST.get("fin_s"))
    except ValueError as error:
        return JsonResponse({"error": str(error)}, status=400)
    limite = Config.desde_entorno().max_fragmento_s
    if fin <= inicio:
        return JsonResponse({"error": "El final debe ser posterior al inicio."}, status=400)
    if fin - inicio < SELECCION_MINIMA_S:
        return JsonResponse({"error": "La selección debe durar al menos 1 segundo."}, status=400)
    if fin - inicio > limite:
        return JsonResponse({"error": f"La selección dura {fin - inicio:.0f} s y el límite es {limite:.0f} s."}, status=400)
    if cancion.duracion_s is not None and fin > cancion.duracion_s + TOLERANCIA_FIN_S:
        return JsonResponse({"error": "La selección termina después del final de la canción."}, status=400)

    separar = str(request.POST.get("separar", "true")).lower() in ("true", "on", "1")
    fragmento = Fragmento.objects.create(
        cancion=cancion, origen=cancion.origen, inicio_s=inicio, fin_s=fin, separar=separar,
        estado=Fragmento.PROCESANDO, paso="En cola",
    )
    Cancion.objects.filter(pk=cancion.pk).update(separar=separar)
    trabajos.lanzar_frase(fragmento.pk)
    return JsonResponse(_frase_a_dict(fragmento), status=201)


@require_POST
def cancion_reintentar(request, pk):
    cancion = get_object_or_404(Cancion, pk=pk)
    actualizados = Cancion.objects.filter(pk=pk, estado=Cancion.ERROR).update(
        estado=Cancion.PREPARANDO, paso="Preparando", mensaje=""
    )
    if actualizados:
        trabajos.lanzar_preparacion_cancion(cancion.pk)
    return redirect("cancion", pk=pk)


# --- fragmento (frase) ---

def detalle(request, pk):
    fragmento = get_object_or_404(Fragmento.objects.select_related("cancion"), pk=pk)
    return render(request, "transcripciones/detalle.html", {
        "fragmento": fragmento,
        "frases": fragmento.por_frases(),
        "rango": f"{formato_tiempo(fragmento.inicio_s)} a {formato_tiempo(fragmento.fin_s)}",
    })


def estado(request, pk):
    fragmento = get_object_or_404(Fragmento, pk=pk)
    return JsonResponse({
        "estado": fragmento.estado,
        "paso": fragmento.paso,
        "mensaje": fragmento.mensaje,
        "avisos": fragmento.avisos,
    })


@require_POST
def reintentar(request, pk):
    """Desde error: vuelve a recortar y analizar. Atómico para no lanzar dos veces."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    actualizados = Fragmento.objects.filter(pk=pk, estado=Fragmento.ERROR).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    if actualizados:
        trabajos.lanzar_frase(fragmento.pk)
    return redirect("detalle", pk=pk)


def historial(request):
    return render(request, "transcripciones/historial.html", {
        "canciones": Cancion.objects.prefetch_related("fragmentos"),
    })


def _archivo_de(fragmento, clave) -> Path:
    ruta = fragmento.archivos.get(clave)
    if not ruta or not Path(ruta).exists():
        raise Http404("ese archivo no existe todavía")
    return Path(ruta)


def descargar(request, pk, clave):
    """Entrega el archivo como descarga."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    ruta = _archivo_de(fragmento, clave)
    return FileResponse(open(ruta, "rb"), as_attachment=True,
                        filename=NOMBRES_DESCARGA.get(clave, ruta.name))


def audio(request, pk, clave):
    """Entrega el audio para reproducirlo en la página, con soporte de Range."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    return respuesta_audio(_archivo_de(fragmento, clave), request)


ETIQUETAS_PISTA = (
    ("mezcla_wav", "Mezcla original"),
    ("melodia_wav", "Melodía aislada"),
    ("notas_wav", "Notas detectadas"),
)


def datos(request, pk):
    """Todo lo que el lienzo de notas necesita, en una sola petición."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    pistas = [
        {"clave": clave, "etiqueta": etiqueta, "url": reverse("audio", args=[fragmento.pk, clave])}
        for clave, etiqueta in ETIQUETAS_PISTA
        if fragmento.archivos.get(clave) and Path(fragmento.archivos[clave]).exists()
    ]
    frases = [
        {"indice": indice, "inicio_s": notas[0].inicio_s, "fin_s": notas[-1].fin_s}
        for indice, notas in fragmento.por_frases()
    ]
    return JsonResponse({
        "duracion_s": fragmento.duracion_s,
        "desplazamiento_s": fragmento.inicio_s,
        "notas": [
            {
                "orden": nota.orden,
                "nombre": nota.nombre,
                "midi": nota.midi,
                "inicio_s": nota.inicio_s,
                "duracion_s": nota.duracion_s,
                "confianza": nota.confianza,
                "etiqueta": nota.etiqueta_confianza,
            }
            for nota in fragmento.notas.all()
        ],
        "frases": frases,
        "pistas": pistas,
    })
```

- [ ] **Paso 5: Escribir `urls.py` y quitar los alias de `trabajos.py`**

Sustituir `web/transcripciones/urls.py` por:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("historial/", views.historial, name="historial"),
    path("cancion/<int:pk>/", views.cancion, name="cancion"),
    path("cancion/<int:pk>/estado/", views.cancion_estado, name="cancion_estado"),
    path("cancion/<int:pk>/onda/", views.cancion_onda, name="cancion_onda"),
    path("cancion/<int:pk>/escucha/", views.cancion_escucha, name="cancion_escucha"),
    path("cancion/<int:pk>/frases/", views.crear_frase, name="crear_frase"),
    path("cancion/<int:pk>/reintentar/", views.cancion_reintentar, name="cancion_reintentar"),
    path("fragmento/<int:pk>/", views.detalle, name="detalle"),
    path("fragmento/<int:pk>/estado/", views.estado, name="estado"),
    path("fragmento/<int:pk>/reintentar/", views.reintentar, name="reintentar"),
    path("fragmento/<int:pk>/datos/", views.datos, name="datos"),
    path("fragmento/<int:pk>/audio/<str:clave>/", views.audio, name="audio"),
    path("fragmento/<int:pk>/descargar/<str:clave>/", views.descargar, name="descargar"),
]
```

En `web/transcripciones/trabajos.py`, borrar el bloque de "Alias provisionales" (`lanzar_preparacion` y `lanzar_analisis`) con su comentario.

- [ ] **Paso 6: Escribir las plantillas**

`web/transcripciones/templates/transcripciones/index.html`:

```html
{% extends "transcripciones/base.html" %}
{% block contenido %}
<h1>Sacar una melodía</h1>

{% if formulario.errors %}
  <div class="error">
    {% for error in formulario.non_field_errors %}<p>{{ error }}</p>{% endfor %}
  </div>
{% endif %}

<form method="post" enctype="multipart/form-data">
  {% csrf_token %}
  <label>Enlace de YouTube
    <input type="text" name="url" placeholder="https://www.youtube.com/watch?v=..."
           value="{{ formulario.url.value|default:'' }}">
  </label>
  <p class="separador">o</p>
  <label>Subir un archivo de audio
    <input type="file" name="archivo" accept="audio/*,video/*,.mp3,.m4a,.wav,.ogg,.opus,.flac,.aac,.mp4,.webm">
  </label>
  <p class="ayuda">Después vas a ver la forma de onda de la canción entera y elegir cada frase con dos manijas.</p>
  <button type="submit">Abrir</button>
</form>

{% if recientes %}
<h2>Últimas canciones</h2>
<ul>
  {% for cancion in recientes %}
    <li><a href="{% url 'cancion' cancion.pk %}">{{ cancion }}</a>
        <span class="estado">{{ cancion.get_estado_display }}</span></li>
  {% endfor %}
</ul>
{% endif %}
{% endblock %}
```

`web/transcripciones/templates/transcripciones/cancion.html`:

```html
{% extends "transcripciones/base.html" %}
{% load static %}
{% block titulo %}{{ cancion }} · SacaNotas{% endblock %}
{% block contenido %}
<h1>{{ cancion }}</h1>

{% if cancion.estado == "error" %}
  <div class="error"><p>{{ cancion.mensaje }}</p></div>
  <form method="post" action="{% url 'cancion_reintentar' cancion.pk %}">
    {% csrf_token %}
    <button type="submit">Reintentar</button>
  </form>

{% elif cancion.estado == "lista" %}
  <p class="rango">Duración {{ duracion }}. Arrastra las manijas para marcar una frase, escúchala y analízala.</p>

  <div id="onda"
       data-onda="{% url 'cancion_onda' cancion.pk %}"
       data-estado="{% url 'cancion_estado' cancion.pk %}"
       data-escucha="{% url 'cancion_escucha' cancion.pk %}"
       data-crear="{% url 'crear_frase' cancion.pk %}"
       data-csrf="{{ csrf_token }}">
    <div class="pista-onda">
      <canvas></canvas>
      <div class="manija manija-inicio" title="Inicio de la frase"></div>
      <div class="manija manija-fin" title="Final de la frase"></div>
    </div>
    <div class="controles seleccion">
      <label>Desde <input type="text" name="inicio" size="7"></label>
      <label>Hasta <input type="text" name="fin" size="7"></label>
      <span class="duracion-seleccion"></span>
      <button type="button" class="escuchar">Escuchar la selección</button>
    </div>
    <audio preload="metadata"></audio>
    <p class="aviso-seleccion"></p>
    <div class="controles">
      <label class="casilla">
        <input type="checkbox" name="separar" {% if cancion.separar %}checked{% endif %}>
        Separar la melodía de la banda (desmarca si el audio ya es solo el instrumento)
      </label>
    </div>
    <button type="button" class="analizar">Analizar esta selección</button>
  </div>

  <h2>Frases de esta canción</h2>
  <ol id="frases" class="frases">
    {% for frase in frases %}
      <li data-id="{{ frase.pk }}">
        <a href="{% url 'detalle' frase.pk %}">{{ frase.inicio_s|floatformat:0 }} s a {{ frase.fin_s|floatformat:0 }} s</a>
        <span class="estado">{{ frase.get_estado_display }}</span>
      </li>
    {% empty %}
      <li class="vacio">Todavía no marcaste ninguna frase.</li>
    {% endfor %}
  </ol>
  <script src="{% static 'onda.js' %}" defer></script>

{% else %}
  <p class="trabajando" id="paso">{{ cancion.paso|default:"Preparando" }}…</p>
  <script>
    setInterval(async () => {
      const respuesta = await fetch("{% url 'cancion_estado' cancion.pk %}");
      const datos = await respuesta.json();
      document.getElementById("paso").textContent = (datos.paso || datos.estado) + "…";
      if (["lista", "error"].includes(datos.estado)) location.reload();
    }, 2000);
  </script>
{% endif %}
{% endblock %}
```

`web/transcripciones/templates/transcripciones/detalle.html`:

```html
{% extends "transcripciones/base.html" %}
{% block contenido %}
<h1>{{ fragmento.cancion }}</h1>
<p class="rango">Frase {{ rango }} · <a href="{% url 'cancion' fragmento.cancion.pk %}">Volver a la canción</a></p>

{% if fragmento.estado == "error" %}
  <div class="error"><p>{{ fragmento.mensaje }}</p></div>
  <form method="post" action="{% url 'reintentar' fragmento.pk %}">
    {% csrf_token %}
    <button type="submit">Reintentar</button>
  </form>

{% elif fragmento.estado == "listo" %}
  {% include "transcripciones/resultado.html" %}

{% else %}
  <p class="trabajando" id="paso">{{ fragmento.paso|default:"En cola" }}…</p>
  <script>
    setInterval(async () => {
      const respuesta = await fetch("{% url 'estado' fragmento.pk %}");
      const datos = await respuesta.json();
      document.getElementById("paso").textContent = (datos.paso || datos.estado) + "…";
      if (["listo", "error"].includes(datos.estado)) location.reload();
    }, 2000);
  </script>
{% endif %}
{% endblock %}
```

`web/transcripciones/templates/transcripciones/historial.html`:

```html
{% extends "transcripciones/base.html" %}
{% block contenido %}
<h1>Historial</h1>
{% for cancion in canciones %}
  <h2><a href="{% url 'cancion' cancion.pk %}">{{ cancion }}</a>
      <span class="estado">{{ cancion.get_estado_display }} · {{ cancion.creada|date:"d/m/Y H:i" }}</span></h2>
  <table class="notas">
    <thead><tr><th>Frase</th><th>Estado</th><th>Fecha</th></tr></thead>
    <tbody>
      {% for frase in cancion.frases %}
        <tr>
          <td><a href="{% url 'detalle' frase.pk %}">{{ frase.inicio_s|floatformat:0 }} a {{ frase.fin_s|floatformat:0 }} s</a></td>
          <td>{{ frase.get_estado_display }}</td>
          <td>{{ frase.creado|date:"d/m/Y H:i" }}</td>
        </tr>
      {% empty %}
        <tr><td colspan="3">Sin frases todavía.</td></tr>
      {% endfor %}
    </tbody>
  </table>
{% empty %}
  <p>Todavía no has abierto ninguna canción.</p>
{% endfor %}
{% endblock %}
```

- [ ] **Paso 7: Ejecutar y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 58 tests pasan (7 modelos, 11 trabajos, 6 audio_http, 34 vistas: 2 funciones y 32 métodos)

Después, `py -m pytest -q -m "not lento"`: toda la suite en verde (95 motor + 58 web).

- [ ] **Paso 8: Commit**

```bash
git add web/transcripciones web/static
git commit -m "feat: pantalla de la canción con estado, onda, escucha y creación de frases"
```

---

### Tarea 7: `onda.js`, estilos y comprobación visual

**Archivos:**
- Crear: `web/static/onda.js`
- Modificar: `web/static/estilo.css` (añadir al final)

**Interfaces:**
- Consume: el contenedor `#onda` con `data-onda`, `data-estado`, `data-escucha`, `data-crear`, `data-csrf`; dentro, `canvas`, `.manija-inicio`, `.manija-fin`, `input[name=inicio]`, `input[name=fin]`, `.duracion-seleccion`, `button.escuchar`, `audio`, `.aviso-seleccion`, `input[name=separar]`, `button.analizar`; y la lista `#frases` con `li[data-id]`
- Produce: la interacción completa descrita en la sección 3.2 del diseño

- [ ] **Paso 1: Escribir `web/static/onda.js`**

```javascript
/* Forma de onda de la canción con dos manijas para marcar una frase.
   Pieza autocontenida: recibe URLs y el token CSRF por data-*, y todo lo
   demás por JSON. Nunca lee flotantes de la plantilla. */
(() => {
  const raiz = document.getElementById("onda");
  if (!raiz) return;

  const urls = raiz.dataset;
  const canvas = raiz.querySelector("canvas");
  const pista = raiz.querySelector(".pista-onda");
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

    requestAnimationFrame(dibujar);
  };

  const fijarSeleccion = (inicio, fin) => {
    seleccion = { inicio: limitar(inicio, 0, duracion), fin: limitar(fin, 0, duracion) };
    if (seleccion.inicio > seleccion.fin) seleccion = { inicio: seleccion.fin, fin: seleccion.inicio };
    colocarManijas();
    validar();
  };

  // Manijas: eventos de puntero, así funcionan con el ratón y con el dedo.
  Object.entries(manijas).forEach(([nombre, manija]) => {
    manija.addEventListener("pointerdown", (evento) => {
      manija.setPointerCapture(evento.pointerId);
      manija.classList.add("activa");
    });
    manija.addEventListener("pointermove", (evento) => {
      if (!manija.classList.contains("activa")) return;
      const caja = canvas.getBoundingClientRect();
      const segundos = aSegundos(limitar(evento.clientX - caja.left, 0, caja.width));
      if (nombre === "inicio") fijarSeleccion(segundos, seleccion.fin);
      else fijarSeleccion(seleccion.inicio, segundos);
    });
    const soltar = () => manija.classList.remove("activa");
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
  });
  reproductor.addEventListener("pause", () => {
    escuchando = false;
    botonEscuchar.textContent = "Escuchar la selección";
  });

  const pintarLista = () => {
    lista.innerHTML = "";
    if (!frases.length) {
      const vacio = document.createElement("li");
      vacio.className = "vacio";
      vacio.textContent = "Todavía no marcaste ninguna frase.";
      lista.append(vacio);
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
      lista.append(item);
    });
  };

  const refrescarFrases = async () => {
    const respuesta = await fetch(urls.estado);
    const datos = await respuesta.json();
    frases = datos.frases;
    pintarLista();
    clearTimeout(temporizador);
    if (frases.some((f) => f.estado === "procesando" || f.estado === "pendiente")) {
      temporizador = setTimeout(refrescarFrases, 3000);
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
    const estado = await (await fetch(urls.estado)).json();
    const onda = await (await fetch(urls.onda)).json();
    duracion = onda.duracion_s || estado.duracion_s || 0;
    maximo = estado.max_fragmento_s || 180;
    picos = onda.picos || [];
    frases = estado.frases || [];
    reproductor.src = urls.escucha;
    fijarSeleccion(0, Math.min(duracion, 30));
    pintarLista();
    if (frases.some((f) => f.estado === "procesando" || f.estado === "pendiente")) {
      temporizador = setTimeout(refrescarFrases, 3000);
    }
    window.addEventListener("resize", colocarManijas);
    requestAnimationFrame(dibujar);
  };

  arrancar().catch(() => {
    aviso.textContent = "No se pudo cargar la forma de onda.";
  });
})();
```

- [ ] **Paso 2: Añadir los estilos al final de `web/static/estilo.css`**

```css
.pista-onda { position: relative; margin: 1rem 0 0.5rem; touch-action: none; }
.pista-onda canvas { width: 100%; height: 160px; background: var(--panel); border-radius: 8px; display: block; }
.manija {
  position: absolute; top: 0; bottom: 0; width: 24px; margin-left: -12px;
  cursor: ew-resize; touch-action: none;
}
.manija::before {
  content: ""; position: absolute; top: 0; bottom: 0; left: 11px; width: 2px;
  background: var(--acento);
}
.manija::after {
  content: ""; position: absolute; top: -4px; left: 4px; width: 16px; height: 16px;
  background: var(--acento); border-radius: 4px;
}
.manija.activa::after { background: #ffffff; }
.seleccion input[type="text"] { width: 6rem; display: inline-block; margin: 0 0.25rem; }
.seleccion label { display: inline; }
.duracion-seleccion { color: var(--tenue); }
.aviso-seleccion { color: var(--baja); min-height: 1.4em; margin: 0.25rem 0; }
button.escuchar { margin-top: 0; padding: 0.4rem 0.9rem; background: var(--panel); color: var(--texto); border: 1px solid #2a2e37; }
button.analizar:disabled { opacity: 0.45; cursor: not-allowed; }
ol.frases { padding-left: 1.25rem; }
ol.frases li { margin: 0.35rem 0; }
ol.frases a { color: var(--acento); }
.estado-listo { color: var(--alta); }
.estado-procesando { color: var(--media); }
.estado-error { color: var(--baja); }
.mensaje-error { color: var(--tenue); }
```

- [ ] **Paso 3: Comprobar la sintaxis y la suite**

```bash
node --check web/static/onda.js
py -m pytest -q -m "not lento"
```

Esperado: sin errores de sintaxis; la suite sigue en verde (esta tarea no añade tests de Python).

- [ ] **Paso 4: Comprobación visual (la hace el usuario o el coordinador con un navegador real, no con Playwright)**

Con `iniciar.bat` o `py web/manage.py runserver 0.0.0.0:8000 --noreload`: abrir una canción lista (por ejemplo, subir `media/prueba/escala_sintetica.wav` o pegar `https://www.youtube.com/watch?v=jNQXAC9IVRw`, que está en caché). Verificar: la onda se dibuja; las manijas se arrastran con el ratón y con el dedo; los campos m:ss siguen a las manijas y las mueven al editarlos; una selección mayor de 3 minutos desactiva el botón y muestra el motivo; "Escuchar la selección" reproduce solo ese tramo y se para; "Analizar esta selección" añade la frase a la lista con "En cola" y la lista se actualiza sola hasta "Listo"; la frase lista aparece como banda verde y al hacer clic en ella abre su resultado.

- [ ] **Paso 5: Commit**

```bash
git add web/static/onda.js web/static/estilo.css
git commit -m "feat: forma de onda con manijas para marcar, escuchar y analizar frases"
```

---

### Tarea 8: Documentación y cierre

**Archivos:**
- Modificar: `CLAUDE.md` (sección "Lo mínimo que hay que saber" y "Estado")
- Modificar: `docs/DISENO.md` (nota al principio)
- Modificar: `docs/DISENO_SELECTOR_DE_FRASES.md` (cabecera de estado)

- [ ] **Paso 1: `CLAUDE.md`**

En "Lo mínimo que hay que saber", sustituir la viñeta que empieza por "**Se trabaja por fragmentos**" por:

```markdown
* **La unidad es la canción; las frases se marcan sobre su forma de onda.** Se sube o se enlaza una vez, la canción se prepara en segundo plano (audio original, copia `escucha.m4a` para el navegador y `onda.json` con los picos en `media/canciones/<id>/`), y cada "Analizar esta selección" crea un `Fragmento` que se recorta desde el audio de la canción y se analiza. Límites por frase: entre 1 s y 3 min.
```

Añadir después de la viñeta "**Un análisis a la vez**":

```markdown
* **El audio se sirve con `Range`** (`transcripciones/audio_http.py`): sin respuestas 206 no se puede saltar dentro de una canción larga ni reproducir en Safari.
```

En "Estado", sustituir el primer párrafo por:

```markdown
Implementado (plan base de 20 tareas más el selector de frases sobre la forma de onda, `docs/PLAN_SELECTOR_DE_FRASES.md`). Se arranca con doble clic en `iniciar.bat`. Pendiente del músico: grabar `tests/fijos/escala_quena.wav`, correr la calibración, y probar el selector desde el teléfono con una canción real.
```

- [ ] **Paso 2: Diseños**

Al principio de `docs/DISENO.md`, bajo la línea de "Estado", añadir:

```markdown
**Actualización 2026-09-05:** el flujo de entrada (sección 3, 7.2 y 8.2) fue sustituido por el selector de frases sobre la forma de onda; ver `DISENO_SELECTOR_DE_FRASES.md`. El resto sigue vigente.
```

En `docs/DISENO_SELECTOR_DE_FRASES.md`, cambiar la línea de estado a `**Estado:** implementado (ver PLAN_SELECTOR_DE_FRASES.md)`.

- [ ] **Paso 3: Suite completa y commit**

```bash
py -m pytest -q
git add CLAUDE.md docs/DISENO.md docs/DISENO_SELECTOR_DE_FRASES.md
git commit -m "docs: estado con el selector de frases sobre la forma de onda"
```

Esperado: toda la suite en verde (con los lentos, si se quiere: los dos de CREPE tardan un minuto; los dos de calibración quedan saltados).

---

## Revisión del plan contra el diseño

| Sección del diseño | Tarea |
|---|---|
| 3.1 Inicio sin tiempos | 6 |
| 3.2 Pantalla de la canción (onda, manijas, límite, escuchar, analizar, lista, bandas) | 6 (HTML, JSON, POST) y 7 (JS) |
| 3.3 Resultado sin rama "preparado", con enlace a la canción | 6 |
| 3.4 Historial por canciones | 6 |
| 4 Motor: `forma_de_onda`, `convertir_para_escucha` | 1 |
| 4 Motor: `Fuente`, `obtener_audio`, `preparar` reescrita | 2 |
| 5.1 Modelo de `Cancion` | 3 |
| 5.2 Trabajos por canción y por frase, recuperación | 4 |
| 5.3 Rutas y vistas | 6 |
| 5.4 `Range` | 5 |
| 5.5 `onda.js` | 7 |
| 5.6 Archivos en disco | 4 (canciones) y 6 (subidas) |
| 6 Errores | 4 (estados de error), 6 (400/409, reintentos), 7 (aviso en pantalla) |
| 7 Pruebas | 1, 2, 3, 4, 5, 6; visual en 7 |

## Cómo ejecutar este plan

Las tareas 1 y 2 (motor) son independientes de la web y pueden ir en cualquier orden. Las tareas 3, 4, 5 y 6 van en ese orden: cada una depende de la anterior (4 usa el modelo de 3; 6 usa 4 y 5). La 7 necesita el HTML de la 6. La 8 cierra. No se despachan dos implementadores a la vez porque todas tocan el mismo repositorio.

Al terminar la tarea 6 la aplicación ya funciona sin JavaScript (se pueden crear frases con `curl` o desde los tests); la 7 es la experiencia de usuario.
