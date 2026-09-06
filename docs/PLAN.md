# Quenotas: plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usar `superpowers:subagent-driven-development` (recomendada) o `superpowers:executing-plans` para implementar este plan tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguimiento.

**Objetivo:** construir una herramienta local que reciba un fragmento de audio y devuelva la melodía monofónica como lista de notas, MIDI, TXT y PDF, con un reproductor sincronizado que resalta la nota que suena.

**Arquitectura:** dos capas estrictamente separadas. `motor/` es Python puro y no importa Django en ninguna línea; `web/` es Django y no contiene ninguna operación de audio. El acuerdo entre ambas es el contrato de datos de `motor/contrato.py`.

**Stack:** Python 3.14 global, numpy, scipy, soundfile, torchcrepe, demucs, yt-dlp, ffmpeg, pretty_midi, fpdf2, Django con SQLite.

**Spec:** `docs/DISENO.md`

## Restricciones globales

Todas las tareas heredan estas reglas.

- **Intérprete:** `C:\Users\Raphael Tigre\AppData\Local\Python\pythoncore-3.14-64\python.exe` (Python 3.14.7), invocable como `py`. **Nunca crear entorno virtual.**
- **Binarios externos:** `ffmpeg` y `ffprobe` 9.0 ya están en el PATH. No se empaquetan.
- **Raíz del proyecto:** `D:\Documentos\claude proyectos\Quenotas`
- **`motor/` no puede importar `django` ni nada de `web/`.** Si un test necesita Django para probar el motor, el diseño está mal.
- **Tiempos relativos.** En el contrato, `inicio_s` de cada nota y de cada frase es **relativo al inicio del fragmento** (0 = primer instante del recorte). El desplazamiento dentro de la canción vive solo en `fragmento.inicio_s`. La pantalla muestra la suma. Esto es obligatorio porque los WAV generados empiezan en 0 y el reproductor del navegador lee `currentTime`, que también empieza en 0.
- **Nombres de nota en cifrado anglosajón** con Do central en `C4` (MIDI 60). Ejemplos: MIDI 67 es `G4`, MIDI 91 es `G6`.
- **Rango por defecto (quena en Sol):** `fmin_hz = 261.63` (C4), `fmax_hz = 1567.98` (G6).
- **Umbrales por defecto:** confianza 0.5, ventana de mediana 5 tramas (impar obligatorio), estabilidad mínima 0.05 s, duración mínima 0.06 s, silencio de frase 0.6 s, salto de análisis 10 ms.
- **Límite de fragmento:** 180 segundos. Más largo se rechaza.
- **Idioma del código:** nombres de funciones, variables y mensajes en español, como el resto del espacio de trabajo.
- **Un solo runner de pruebas:** `pytest` para todo, con `pytest-django` para la parte web. Motor: `py -m pytest tests -q`. Web (desde la tarea 15): `py -m pytest web -q`. Todo: `py -m pytest -q`. No se usa `manage.py test`.
- **Subprocesos en UTF-8.** Toda llamada a `subprocess.run` que capture texto lleva `encoding="utf-8", errors="replace"` y pasa `PYTHONUTF8=1` al hijo. Sin eso, Python en Windows decodifica con cp1252 y un título de YouTube con `♪` o comillas tipográficas revienta la descarga.
- **Los archivos de salida nunca tumban un análisis.** Si falla el PDF, el MIDI o la sonificación, se registra un aviso y el resultado se devuelve igual con las notas calculadas.
- **Las descargas se guardan por id de video** en `media/origen/<id>.<ext>` y se reutilizan. Una canción se baja una sola vez aunque se analicen diez fragmentos.
- **Commits:** uno por tarea, en español, formato `feat: …` / `test: …` / `chore: …`.

## Estructura de archivos

```
Quenotas/
  motor/
    __init__.py
    config.py          # parámetros desde variables de entorno
    contrato.py        # dataclasses del contrato + conversión MIDI/nombre + serialización
    audio.py           # ffprobe, ffmpeg, carga y remuestreo
    descarga.py        # yt-dlp
    separacion.py      # demucs
    afinacion.py       # torchcrepe
    notas.py           # curva de afinación -> notas -> frases
    exportar.py        # MIDI, TXT, PDF, sonificación
    pipeline.py        # orquestación de las etapas
  tests/
    __init__.py
    senales.py         # generadores de señales y curvas sintéticas
    test_contrato.py
    test_config.py
    test_senales.py
    test_notas.py
    test_audio.py
    test_afinacion.py
    test_exportar.py
    test_pipeline.py
    test_descarga.py
    test_separacion.py
    test_calibracion.py
    fijos/             # grabaciones reales de referencia (sí entran a git)
  web/
    manage.py
    quenotas/         # settings.py, urls.py, wsgi.py
    transcripciones/   # models.py, views.py, urls.py, formularios.py, trabajos.py,
                       # management/commands/recuperar_trabajos.py, tests_*.py, templates/
    static/            # pianoroll.js, estilo.css
  media/               # audios y archivos generados (fuera de git)
    origen/            # descargas de YouTube, una por id de video, reutilizables
    subidas/           # archivos que sube el usuario
    fragmentos/<id>/   # recorte, pista separada y salidas de cada fragmento
  docs/                # DISENO.md, PLAN.md, REVISION_PLAN.md
  requirements.txt
  verificar_entorno.py
  iniciar.bat
  pytest.ini
  .gitignore
  CLAUDE.md
```

Cada archivo del motor tiene una responsabilidad y ninguno pasa de unas doscientas líneas. `notas.py` es el corazón del proyecto y el único que concentra lógica difícil; por eso está aislado y se prueba sin cargar ningún modelo.

---

### Tarea 1: Esqueleto, dependencias y verificación del entorno

Antes de escribir lógica hay que saber que las dependencias pesadas instalan y funcionan en esta máquina. Instalar `torch` con CUDA en Windows es el riesgo número uno del proyecto y descubrirlo en la tarea 9 sería tarde. Por eso `verificar_entorno.py` no se limita a importar: pasa un seno por CREPE y un WAV corto por Demucs. Con eso los pesos de los dos modelos quedan descargados desde el principio (lo pide la sección 9 del diseño) y cualquier incompatibilidad entre torch, torchcrepe y demucs aparece aquí y no en la tarea 7 o la 13.

Verificado el 2026-09-05: `demucs` 4.1.0, `pretty_midi` 0.2.11.post0, `torch` 2.14 (índices `cu126` y `cu130`) y `numba` 0.67 tienen rueda para Python 3.14 en Windows. `demucs` 4.1.0 ya no depende de `torchaudio`; `torchcrepe` sí, y arrastra `librosa` y `numba`.

**Archivos:**
- Crear: `.gitignore`, `requirements.txt`, `pytest.ini`, `verificar_entorno.py`
- Crear: `motor/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Consume: nada
- Produce: entorno instalado y `verificar_entorno.py` ejecutable

- [ ] **Paso 1: Inicializar el repositorio**

```bash
cd "D:/Documentos/claude proyectos/Quenotas"
git init
git add CLAUDE.md docs/DISENO.md docs/PLAN.md
git commit -m "chore: diseño y plan iniciales"
```

- [ ] **Paso 2: Crear `.gitignore`**

```gitignore
__pycache__/
*.pyc
media/
db.sqlite3
.pytest_cache/
separado/
*.wav
*.mid
!tests/fijos/*.wav
```

Los PDF no se ignoran en general: los que genera el sistema viven en `media/`, que ya está fuera, y en `docs/` puede hacer falta guardar alguno.

- [ ] **Paso 3: Crear `requirements.txt`**

```
Django>=5.2
numpy>=2.1
scipy>=1.14
soundfile>=0.13
torch>=2.6
torchaudio>=2.6
torchcrepe>=0.0.24
demucs>=4.1.0
yt-dlp>=2026.8.19
pretty_midi>=0.2.11
fpdf2>=2.8
pytest>=8.0
pytest-django>=4.9
```

- [ ] **Paso 4: Crear `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py tests_*.py
markers =
    lento: carga modelos pesados o toca la red
```

La tarea 15 añade a este archivo la configuración de `pytest-django` cuando exista el proyecto web. No se añade antes: con `DJANGO_SETTINGS_MODULE` apuntando a un módulo inexistente, pytest no arranca.

- [ ] **Paso 5: Instalar**

Primero torch con CUDA desde el índice de PyTorch, y después el resto. Si se instala `requirements.txt` primero, pip trae el torch de PyPI (solo CPU) y luego hay que reinstalarlo entero.

```bash
py -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
py -m pip install -r requirements.txt
```

`cu126` es compatible con la RTX 3050 y tiene rueda para Python 3.14; `cu130` también, si el controlador de NVIDIA está actualizado.

- [ ] **Paso 6: Crear `verificar_entorno.py`**

```python
"""Comprueba que todo lo que Quenotas necesita está instalado y funciona.

No se limita a importar: pasa un seno por CREPE y un WAV corto por Demucs.
Así los pesos de los dos modelos quedan descargados desde el principio y
cualquier incompatibilidad aparece aquí, no en la primera canción.

Uso: py verificar_entorno.py            (todo, la primera vez tarda varios minutos)
     py verificar_entorno.py --rapido   (solo imports y binarios)
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}


def _comprobar(nombre, funcion):
    try:
        detalle = funcion()
    except Exception as error:  # noqa: BLE001
        print(f"  FALLA   {nombre}: {error}")
        return False
    print(f"  OK      {nombre}: {detalle}")
    return True


def binario(nombre):
    ruta = shutil.which(nombre)
    if not ruta:
        raise RuntimeError("no está en el PATH")
    salida = subprocess.run([nombre, "-version"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    return salida.stdout.splitlines()[0][:60]


def _seno(frecuencia_hz, duracion_s, sr):
    import numpy as np
    t = np.arange(int(duracion_s * sr)) / sr
    return (0.5 * np.sin(2 * np.pi * frecuencia_hz * t)).astype(np.float32)


def crepe_real():
    """CREPE sobre 2 s de La 440 debe devolver una mediana cercana a 440 Hz."""
    import numpy as np
    import torch
    import torchcrepe

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    audio = torch.from_numpy(_seno(440.0, 2.0, 16000))[None]
    f0, confianza = torchcrepe.predict(
        audio, 16000, 160, 200.0, 1000.0, "full",
        batch_size=512, device=dispositivo, return_periodicity=True,
    )
    f0 = f0[0].cpu().numpy()
    seguras = f0[confianza[0].cpu().numpy() > 0.5]
    if len(seguras) < 50:
        raise RuntimeError(f"solo {len(seguras)} tramas con confianza")
    mediana = float(np.median(seguras))
    if abs(mediana - 440.0) > 10:
        raise RuntimeError(f"detectó {mediana:.1f} Hz en vez de 440")
    return f"{mediana:.1f} Hz en {dispositivo}, modelo descargado"


def demucs_real():
    """Demucs sobre 5 s de audio debe dejar other.wav en la carpeta esperada."""
    import soundfile as sf
    import torch

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    with tempfile.TemporaryDirectory() as carpeta:
        entrada = Path(carpeta) / "humo.wav"
        sf.write(entrada, _seno(440.0, 5.0, 44100), 44100)
        comando = [sys.executable, "-m", "demucs", "-n", "htdemucs", "-d", dispositivo,
                   "--segment", "6", "--out", carpeta, str(entrada)]
        salida = subprocess.run(comando, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=ENTORNO_UTF8)
        if salida.returncode != 0:
            ultima = (salida.stderr or "").strip().splitlines()[-1:]
            raise RuntimeError(ultima[0] if ultima else "demucs falló sin mensaje")
        esperado = Path(carpeta) / "htdemucs" / "humo" / "other.wav"
        if not esperado.exists():
            raise RuntimeError(f"no apareció {esperado}")
    return f"separó en {dispositivo}, modelo descargado"


def main():
    rapido = "--rapido" in sys.argv
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    resultados = [
        _comprobar("ffmpeg", lambda: binario("ffmpeg")),
        _comprobar("ffprobe", lambda: binario("ffprobe")),
        _comprobar("numpy", lambda: __import__("numpy").__version__),
        _comprobar("scipy", lambda: __import__("scipy").__version__),
        _comprobar("soundfile", lambda: __import__("soundfile").__version__),
        _comprobar("pretty_midi", lambda: __import__("pretty_midi").__version__),
        _comprobar("fpdf", lambda: __import__("fpdf").__version__),
        _comprobar("django", lambda: __import__("django").get_version()),
        _comprobar("pytest_django", lambda: __import__("pytest_django").__version__),
        _comprobar("yt_dlp", lambda: __import__("yt_dlp").version.__version__),
    ]

    def torch_detalle():
        import torch
        disponible = torch.cuda.is_available()
        nombre = torch.cuda.get_device_name(0) if disponible else "sin CUDA, se usará CPU"
        return f"{torch.__version__}, CUDA={disponible}, {nombre}"

    resultados.append(_comprobar("torch", torch_detalle))
    resultados.append(_comprobar("torchcrepe", lambda: __import__("torchcrepe").__name__))
    resultados.append(_comprobar("demucs", lambda: __import__("demucs").__version__))

    if not rapido:
        print("Pruebas reales (la primera vez descargan los modelos):")
        resultados.append(_comprobar("CREPE sobre un seno", crepe_real))
        resultados.append(_comprobar("Demucs sobre 5 s", demucs_real))

    if all(resultados):
        print("\nEntorno completo.")
        return 0
    print("\nHay dependencias que fallan. Revisar arriba.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Paso 7: Ejecutar la verificación**

Ejecutar: `py verificar_entorno.py`
Esperado: todas las líneas con `OK` y `Entorno completo.` La primera vez tarda varios minutos porque descarga los pesos de CREPE y de Demucs; las siguientes, menos de un minuto.

Si `torch` reporta `CUDA=False`, comprobar que el paso 5 se hizo en el orden indicado y que el controlador de NVIDIA está al día. Si aun así sale `False`, dejarlo así y anotarlo: el proyecto funciona en CPU, solo más lento.

Si "Demucs sobre 5 s" falla con `out of memory`, bajar `--segment` a 4 en el script y anotar el valor: es el mismo que irá en `QUENOTAS_SEGMENTO_DEMUCS`.

- [ ] **Paso 8: Crear los paquetes vacíos**

```bash
py -c "open('motor/__init__.py','w').close(); open('tests/__init__.py','w').close()"
```

- [ ] **Paso 9: Commit**

```bash
git add .gitignore requirements.txt pytest.ini verificar_entorno.py motor tests
git commit -m "chore: esqueleto del proyecto y verificación del entorno"
```

---

### Tarea 2: Contrato de datos

Es la pieza de la que dependen todas las demás. Se hace primero y no se cambia sin avisar.

**Archivos:**
- Crear: `motor/contrato.py`
- Test: `tests/test_contrato.py`

**Interfaces:**
- Consume: nada
- Produce:
  - `NOMBRES: tuple[str, ...]`
  - `midi_a_nombre(midi: int) -> str`
  - `nombre_a_midi(nombre: str) -> int`
  - `hz_a_midi(hz: np.ndarray | float) -> np.ndarray`
  - `midi_a_hz(midi: int | float) -> float`
  - `formato_tiempo(segundos: float) -> str` que devuelve `"1:30.4"`
  - `etiqueta_confianza(valor: float) -> str` que devuelve `"alta"`, `"media"` o `"baja"`
  - `Nota(orden, nombre, midi, inicio_s, duracion_s, confianza, cents)` congelada
  - `Frase(indice, inicio_s, fin_s, notas: tuple[Nota, ...])` congelada
  - `Fragmento(titulo, fuente, referencia, inicio_s, fin_s)` congelada
  - `ParametrosAnalisis(separacion, modelo_afinacion, hop_ms, fmin_hz, fmax_hz, dispositivo, afinacion_cents=0)` congelada
  - `Resultado(fragmento, analisis, frases, archivos, avisos)` congelada, con `a_dict()` y `Resultado.desde_dict()`

`formato_tiempo` y `etiqueta_confianza` viven aquí y no en `exportar.py` porque son semántica del contrato (qué cuenta como confianza "alta", cómo se muestra un instante) y las usan el motor, la web y el JavaScript. Así la capa web depende solo del contrato y no de los exportadores.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_contrato.py`:

```python
import numpy as np
import pytest

from motor.contrato import (
    Fragmento,
    Frase,
    Nota,
    ParametrosAnalisis,
    Resultado,
    etiqueta_confianza,
    formato_tiempo,
    hz_a_midi,
    midi_a_hz,
    midi_a_nombre,
    nombre_a_midi,
)


def test_formato_tiempo():
    assert formato_tiempo(0.0) == "0:00.0"
    assert formato_tiempo(30.44) == "0:30.4"
    assert formato_tiempo(90.0) == "1:30.0"
    assert formato_tiempo(3661.5) == "61:01.5"
    assert formato_tiempo(59.96) == "1:00.0"


def test_etiqueta_confianza():
    assert etiqueta_confianza(0.93) == "alta"
    assert etiqueta_confianza(0.71) == "media"
    assert etiqueta_confianza(0.40) == "baja"


@pytest.mark.parametrize(
    "midi,nombre",
    [(60, "C4"), (67, "G4"), (69, "A4"), (71, "B4"), (91, "G6"), (61, "C#4")],
)
def test_conversion_midi_nombre_ida_y_vuelta(midi, nombre):
    assert midi_a_nombre(midi) == nombre
    assert nombre_a_midi(nombre) == midi


def test_hz_a_midi_reconoce_el_la_de_referencia():
    assert hz_a_midi(440.0) == pytest.approx(69.0)
    assert midi_a_hz(69) == pytest.approx(440.0)


def test_hz_a_midi_devuelve_nan_para_silencio():
    salida = hz_a_midi(np.array([440.0, 0.0, -1.0]))
    assert salida[0] == pytest.approx(69.0)
    assert np.isnan(salida[1])
    assert np.isnan(salida[2])


def _resultado_de_ejemplo():
    nota = Nota(orden=1, nombre="G4", midi=67, inicio_s=0.4,
                duracion_s=0.42, confianza=0.93, cents=-12)
    frase = Frase(indice=1, inicio_s=0.4, fin_s=0.82, notas=(nota,))
    return Resultado(
        fragmento=Fragmento(titulo="Prueba", fuente="archivo",
                            referencia="prueba.wav", inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="ninguna", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cpu"),
        frases=(frase,),
        archivos={"midi": "media/x.mid"},
        avisos=("un aviso",),
    )


def test_resultado_va_y_vuelve_de_diccionario():
    original = _resultado_de_ejemplo()
    copia = Resultado.desde_dict(original.a_dict())
    assert copia == original


def test_a_dict_usa_las_claves_del_contrato():
    diccionario = _resultado_de_ejemplo().a_dict()
    assert set(diccionario) == {"fragmento", "analisis", "frases", "archivos", "avisos"}
    assert set(diccionario["frases"][0]["notas"][0]) == {
        "orden", "nombre", "midi", "inicio_s", "duracion_s", "confianza", "cents"
    }


def test_las_notas_son_inmutables():
    nota = _resultado_de_ejemplo().frases[0].notas[0]
    with pytest.raises(Exception):
        nota.midi = 68
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_contrato.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.contrato'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/contrato.py`:

```python
"""Contrato de datos de Quenotas.

Todas las piezas del sistema producen y consumen estas estructuras.
Los tiempos son relativos al inicio del fragmento: 0 es el primer
instante del recorte, y el desplazamiento dentro de la canción vive
solo en Fragmento.inicio_s.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import numpy as np

NOMBRES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_PATRON_NOMBRE = re.compile(r"^([A-G]#?)(-?\d+)$")


def midi_a_nombre(midi: int) -> str:
    """67 -> 'G4'. Convención de Do central en C4 = MIDI 60."""
    midi = int(midi)
    return f"{NOMBRES[midi % 12]}{midi // 12 - 1}"


def nombre_a_midi(nombre: str) -> int:
    """'G4' -> 67."""
    coincidencia = _PATRON_NOMBRE.match(nombre.strip())
    if not coincidencia:
        raise ValueError(f"nombre de nota inválido: {nombre!r}")
    clase, octava = coincidencia.groups()
    return NOMBRES.index(clase) + (int(octava) + 1) * 12


def hz_a_midi(hz):
    """Frecuencia a número MIDI continuo. Cero o negativo devuelve nan."""
    valores = np.asarray(hz, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = 69.0 + 12.0 * np.log2(valores / 440.0)
    resultado = np.where(valores > 0, midi, np.nan)
    return resultado if resultado.ndim else float(resultado)


def midi_a_hz(midi) -> float:
    return float(440.0 * 2.0 ** ((float(midi) - 69.0) / 12.0))


def formato_tiempo(segundos: float) -> str:
    """30.44 -> '0:30.4'. Se redondea a décimas antes de partir en minutos
    para que 59.96 sea '1:00.0' y no '0:60.0'."""
    decimas = int(round(max(0.0, float(segundos)) * 10))
    minutos, resto = divmod(decimas, 600)
    return f"{minutos}:{resto // 10:02d}.{resto % 10}"


def etiqueta_confianza(valor: float) -> str:
    """Traduce la confianza 0..1 a lo que ve el usuario. Único sitio donde
    se decide el corte; la web y el JavaScript reciben la etiqueta hecha."""
    if valor >= 0.85:
        return "alta"
    if valor >= 0.60:
        return "media"
    return "baja"


@dataclass(frozen=True)
class Nota:
    orden: int
    nombre: str
    midi: int
    inicio_s: float
    duracion_s: float
    confianza: float
    cents: int

    @property
    def fin_s(self) -> float:
        return self.inicio_s + self.duracion_s


@dataclass(frozen=True)
class Frase:
    indice: int
    inicio_s: float
    fin_s: float
    notas: tuple[Nota, ...]


@dataclass(frozen=True)
class Fragmento:
    titulo: str
    fuente: str          # "youtube" | "archivo"
    referencia: str
    inicio_s: float
    fin_s: float

    @property
    def duracion_s(self) -> float:
        return self.fin_s - self.inicio_s


@dataclass(frozen=True)
class ParametrosAnalisis:
    separacion: str      # "htdemucs" | "ninguna"
    modelo_afinacion: str
    hop_ms: int
    fmin_hz: float
    fmax_hz: float
    dispositivo: str     # "cuda" | "cpu"
    afinacion_cents: int = 0   # desplazamiento global del instrumento respecto a 440 Hz


@dataclass(frozen=True)
class Resultado:
    fragmento: Fragmento
    analisis: ParametrosAnalisis
    frases: tuple[Frase, ...]
    archivos: dict
    avisos: tuple[str, ...]

    def a_dict(self) -> dict:
        return {
            "fragmento": asdict(self.fragmento),
            "analisis": asdict(self.analisis),
            "frases": [
                {
                    "indice": frase.indice,
                    "inicio_s": frase.inicio_s,
                    "fin_s": frase.fin_s,
                    "notas": [asdict(nota) for nota in frase.notas],
                }
                for frase in self.frases
            ],
            "archivos": dict(self.archivos),
            "avisos": list(self.avisos),
        }

    @staticmethod
    def desde_dict(datos: dict) -> "Resultado":
        return Resultado(
            fragmento=Fragmento(**datos["fragmento"]),
            analisis=ParametrosAnalisis(**datos["analisis"]),
            frases=tuple(
                Frase(
                    indice=frase["indice"],
                    inicio_s=frase["inicio_s"],
                    fin_s=frase["fin_s"],
                    notas=tuple(Nota(**nota) for nota in frase["notas"]),
                )
                for frase in datos["frases"]
            ),
            archivos=dict(datos["archivos"]),
            avisos=tuple(datos["avisos"]),
        )

    @property
    def notas(self) -> tuple[Nota, ...]:
        return tuple(nota for frase in self.frases for nota in frase.notas)
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_contrato.py -q`
Esperado: 13 tests pasan (6 parametrizados y 7 sueltos)

- [ ] **Paso 5: Commit**

```bash
git add motor/contrato.py tests/test_contrato.py
git commit -m "feat: contrato de datos con notas, frases y serialización"
```

---

### Tarea 3: Configuración

**Archivos:**
- Crear: `motor/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consume: nada
- Produce: `Config` congelada con `desde_entorno()` y los campos `media_dir: Path`, `dispositivo: str`, `hop_ms: int`, `fmin_hz: float`, `fmax_hz: float`, `umbral_confianza: float`, `ventana_mediana: int`, `estabilidad_min_s: float`, `duracion_min_s: float`, `silencio_frase_s: float`, `max_fragmento_s: float`, `modelo_afinacion: str`, `modelo_separacion: str`, `segmento_demucs: float`. Además `resolver_dispositivo(preferencia: str) -> str`.

Los valores por defecto se escriben una sola vez, en la dataclass. `desde_entorno` los lee de ahí; así no pueden divergir.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_config.py`:

```python
from pathlib import Path

from motor.config import Config, resolver_dispositivo


def test_valores_por_defecto_son_los_de_la_quena_en_sol():
    config = Config.desde_entorno({})
    assert config.fmin_hz == 261.63
    assert config.fmax_hz == 1567.98
    assert config.hop_ms == 10
    assert config.umbral_confianza == 0.5
    assert config.ventana_mediana == 5
    assert config.max_fragmento_s == 180.0
    assert config.segmento_demucs == 6.0


def test_el_entorno_sobrescribe_los_valores():
    config = Config.desde_entorno({
        "QUENOTAS_FMIN_HZ": "130.81",
        "QUENOTAS_MEDIA": "D:/tmp/media",
        "QUENOTAS_UMBRAL_CONFIANZA": "0.7",
    })
    assert config.fmin_hz == 130.81
    assert config.umbral_confianza == 0.7
    assert config.media_dir == Path("D:/tmp/media")


def test_la_ventana_de_mediana_debe_ser_impar():
    try:
        Config.desde_entorno({"QUENOTAS_VENTANA_MEDIANA": "4"})
    except ValueError as error:
        assert "impar" in str(error)
    else:
        raise AssertionError("debía rechazar una ventana par")


def test_resolver_dispositivo_respeta_lo_pedido():
    assert resolver_dispositivo("cpu") == "cpu"
    assert resolver_dispositivo("auto") in {"cpu", "cuda"}
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_config.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.config'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/config.py`:

```python
"""Parámetros del motor. Nada de esto se escribe a mano en el código.

Se leen de variables de entorno para que la misma carpeta corra en una
laptop con GPU y en un servidor sin ella cambiando solo la configuración.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def resolver_dispositivo(preferencia: str = "auto") -> str:
    """Devuelve 'cuda' o 'cpu'. 'auto' usa CUDA solo si está disponible."""
    if preferencia in {"cpu", "cuda"}:
        return preferencia
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # noqa: BLE001
        return "cpu"


@dataclass(frozen=True)
class Config:
    media_dir: Path = RAIZ / "media"
    dispositivo: str = "auto"
    hop_ms: int = 10
    fmin_hz: float = 261.63          # C4
    fmax_hz: float = 1567.98         # G6
    umbral_confianza: float = 0.5
    ventana_mediana: int = 5
    estabilidad_min_s: float = 0.05
    duracion_min_s: float = 0.06
    silencio_frase_s: float = 0.6
    max_fragmento_s: float = 180.0
    modelo_afinacion: str = "full"
    modelo_separacion: str = "htdemucs"
    segmento_demucs: float = 6.0     # Demucs lo recomienda por debajo de 8 GB de VRAM

    def __post_init__(self):
        if self.ventana_mediana % 2 == 0:
            raise ValueError("la ventana de mediana debe ser impar")
        if self.fmin_hz >= self.fmax_hz:
            raise ValueError("fmin_hz debe ser menor que fmax_hz")

    @staticmethod
    def desde_entorno(entorno=None) -> "Config":
        """Lee QUENOTAS_<CAMPO> para cada campo; lo que no esté, queda en su
        valor por defecto de la dataclass. Los tipos salen de la anotación."""
        entorno = os.environ if entorno is None else entorno
        conversores = {"Path": Path, "str": str, "int": int, "float": float}
        valores = {}
        for nombre, campo in Config.__dataclass_fields__.items():
            bruto = entorno.get(f"QUENOTAS_{nombre.upper()}")
            if nombre == "media_dir":
                bruto = entorno.get("QUENOTAS_MEDIA", bruto)
            if bruto is not None:
                valores[nombre] = conversores[campo.type](bruto)
        return Config(**valores)
```

`campo.type` es una cadena porque el módulo usa `from __future__ import annotations`; por eso el diccionario de conversores se indexa por nombre de tipo. La variable `QUENOTAS_MEDIA` se conserva como alias de `QUENOTAS_MEDIA_DIR` porque es la que usa el `.bat`.

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_config.py -q`
Esperado: 4 tests pasan

- [ ] **Paso 5: Commit**

```bash
git add motor/config.py tests/test_config.py
git commit -m "feat: configuración del motor por variables de entorno"
```

---

### Tarea 4: Generadores de señales sintéticas para pruebas

Esta tarea es la que hace testeable la parte difícil del proyecto sin descargar nada ni cargar modelos. Va antes de `notas.py` porque es su banco de pruebas.

**Archivos:**
- Crear: `tests/senales.py`
- Test: `tests/test_senales.py`

**Interfaces:**
- Consume: nada
- Produce:
  - `curva(tramos, hop_s=0.01, confianza_voz=0.95, confianza_silencio=0.1) -> tuple[np.ndarray, np.ndarray]` donde `tramos` es una lista de `(midi_o_None, duracion_s)` y `midi` puede ser un número o una función `f(indice, total) -> midi`
  - `tono(frecuencia_hz, duracion_s, sr=44100, amplitud=0.5) -> np.ndarray`
  - `silencio(duracion_s, sr=44100) -> np.ndarray`
  - `secuencia(tramos, sr=44100, amplitud=0.5) -> np.ndarray` donde `tramos` es una lista de `(frecuencia_hz_o_None, duracion_s)`

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_senales.py`:

```python
import numpy as np

from tests.senales import curva, secuencia, silencio, tono


def test_la_curva_alterna_voz_y_silencio():
    f0, confianza = curva([(69, 0.5), (None, 0.2), (71, 0.5)], hop_s=0.01)
    assert len(f0) == len(confianza) == 120
    assert np.allclose(f0[:50], 440.0, atol=0.01)
    assert np.all(confianza[50:70] < 0.5)
    assert np.all(f0[50:70] == 0)
    assert np.all(confianza[70:] > 0.5)


def test_la_curva_acepta_midi_flotante():
    f0, _ = curva([(69.25, 0.1)], hop_s=0.01)
    esperado = 440.0 * 2 ** (0.25 / 12)
    assert np.allclose(f0, esperado, atol=0.01)


def test_la_curva_acepta_una_funcion_para_el_vibrato():
    f0, _ = curva([(lambda i, n: 69 + 0.5 * np.sin(2 * np.pi * i / 20), 0.4)], hop_s=0.01)
    assert len(f0) == 40
    assert f0.max() > f0.min()


def test_el_tono_tiene_la_longitud_pedida():
    assert len(tono(440.0, 0.5, sr=16000)) == 8000
    assert len(silencio(0.25, sr=16000)) == 4000


def test_la_secuencia_concatena_tramos():
    señal = secuencia([(440.0, 0.5), (None, 0.2), (494.0, 0.5)], sr=16000)
    assert len(señal) == 19200
    assert np.allclose(señal[8000:11200], 0.0)
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_senales.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'tests.senales'`

- [ ] **Paso 3: Escribir la implementación**

Crear `tests/senales.py`:

```python
"""Generadores de señales y curvas sintéticas para las pruebas.

La curva permite probar la conversión a notas sin cargar CREPE: se le da
directamente la secuencia de alturas y confianzas que el detector habría
producido.
"""
from __future__ import annotations

import numpy as np


def curva(tramos, hop_s=0.01, confianza_voz=0.95, confianza_silencio=0.1):
    """Construye (f0_hz, confianza) a partir de tramos (midi_o_None, duracion_s).

    El midi puede ser un número o una función f(indice, total) -> midi, útil
    para simular vibrato y glissandos.
    """
    frecuencias = []
    confianzas = []
    for altura, duracion_s in tramos:
        tramas = int(round(duracion_s / hop_s))
        if altura is None:
            frecuencias.extend([0.0] * tramas)
            confianzas.extend([confianza_silencio] * tramas)
            continue
        for indice in range(tramas):
            midi = altura(indice, tramas) if callable(altura) else float(altura)
            frecuencias.append(440.0 * 2.0 ** ((midi - 69.0) / 12.0))
            confianzas.append(confianza_voz)
    return np.array(frecuencias, dtype=float), np.array(confianzas, dtype=float)


def tono(frecuencia_hz, duracion_s, sr=44100, amplitud=0.5):
    t = np.arange(int(round(duracion_s * sr))) / sr
    return (amplitud * np.sin(2 * np.pi * frecuencia_hz * t)).astype(np.float32)


def silencio(duracion_s, sr=44100):
    return np.zeros(int(round(duracion_s * sr)), dtype=np.float32)


def secuencia(tramos, sr=44100, amplitud=0.5):
    partes = [
        silencio(duracion_s, sr) if frecuencia is None
        else tono(frecuencia, duracion_s, sr, amplitud)
        for frecuencia, duracion_s in tramos
    ]
    return np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_senales.py -q`
Esperado: 5 tests pasan

- [ ] **Paso 5: Commit**

```bash
git add tests/senales.py tests/test_senales.py
git commit -m "test: generadores de señales y curvas sintéticas"
```

---

### Tarea 5: Conversión de la curva de afinación a notas

**Es la tarea más importante del proyecto.** Todo lo demás es fontanería alrededor de ella. Se prueba entera con curvas sintéticas, sin audio y sin modelos.

**Archivos:**
- Crear: `motor/notas.py`
- Test: `tests/test_notas.py`

**Interfaces:**
- Consume: `motor.contrato.Nota`, `motor.contrato.Frase`, `motor.contrato.hz_a_midi`, `motor.contrato.midi_a_nombre`
- Produce:
  - `estimar_afinacion(f0_hz, confianza, umbral_confianza=0.5) -> float`: desplazamiento global del instrumento respecto a la rejilla de semitonos, en semitonos, en el rango `(-0.5, 0.5]`. Devuelve `0.0` si las tramas no se concentran alrededor de un mismo desvío (por ejemplo, vibrato ancho).
  - `curva_a_notas(f0_hz, confianza, hop_s, umbral_confianza=0.5, ventana_mediana=5, estabilidad_min_s=0.05, duracion_min_s=0.06, afinacion=0.0) -> list[Nota]`
  - `agrupar_en_frases(notas, silencio_min_s=0.6) -> list[Frase]`

**Por qué existe `estimar_afinacion`.** El redondeo al semitono más cercano funciona si el instrumento está afinado a 440 Hz. Una quena artesanal (o un video acelerado) puede estar 40 o 50 cents desplazada; entonces cada nota cae justo en la frontera entre dos semitonos, el redondeo alterna entre ambos y el segmentador parte la nota en trocitos. Se estima el desvío global del fragmento (media circular de la parte fraccionaria del MIDI continuo, el mismo principio que `librosa.estimate_tuning`), se resta antes de redondear, y los `cents` de cada nota se siguen midiendo respecto al semitono exacto para que el usuario vea el desvío real. Si la concentración de las tramas alrededor del desvío estimado es baja, no se aplica nada: eso protege al vibrato simétrico, cuyas tramas se reparten por todo el rango.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_notas.py`:

```python
import numpy as np
import pytest

from motor.notas import agrupar_en_frases, curva_a_notas, estimar_afinacion
from tests.senales import curva

HOP = 0.01


def _analizar(tramos, **opciones):
    f0, confianza = curva(tramos, hop_s=HOP)
    return curva_a_notas(f0, confianza, hop_s=HOP, **opciones)


def _analizar_con_afinacion(tramos, **opciones):
    """Lo que hace el pipeline: estimar el desvío global y aplicarlo."""
    f0, confianza = curva(tramos, hop_s=HOP)
    afinacion = estimar_afinacion(f0, confianza)
    return curva_a_notas(f0, confianza, hop_s=HOP, afinacion=afinacion, **opciones)


def test_estimar_afinacion_detecta_un_desvio_global():
    f0, confianza = curva([(69.3, 0.5), (71.3, 0.5), (72.3, 0.5)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == pytest.approx(0.3, abs=0.02)


def test_estimar_afinacion_ignora_el_vibrato_simetrico():
    def vibrato(indice, total):
        return 69 + 0.5 * np.sin(2 * np.pi * indice / 20)

    f0, confianza = curva([(vibrato, 1.0)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == 0.0


def test_estimar_afinacion_en_silencio_es_cero():
    f0, confianza = curva([(None, 0.5)], hop_s=HOP)
    assert estimar_afinacion(f0, confianza) == 0.0


def test_una_nota_en_la_frontera_del_semitono_no_se_parte():
    """Instrumento 50 cents desplazado con una oscilación lenta y pequeña:
    sin compensar, el redondeo alterna entre 68 y 69 y salen muchas notas."""
    def en_la_frontera(indice, total):
        return 68.5 + 0.04 * np.sin(2 * np.pi * indice / 12)

    sin_compensar = _analizar([(en_la_frontera, 0.8)])
    assert len(sin_compensar) > 1

    notas = _analizar_con_afinacion([(en_la_frontera, 0.8)])
    assert len(notas) == 1
    assert notas[0].nombre in {"G#4", "A4"}
    assert notas[0].duracion_s == pytest.approx(0.8, abs=0.03)
    assert abs(notas[0].cents) == pytest.approx(50, abs=5)


def test_dos_notas_separadas_por_silencio():
    notas = _analizar([(69, 0.5), (None, 0.2), (71, 0.5)])
    assert [nota.nombre for nota in notas] == ["A4", "B4"]
    assert notas[0].inicio_s == pytest.approx(0.0, abs=0.02)
    assert notas[0].duracion_s == pytest.approx(0.5, abs=0.03)
    assert notas[1].inicio_s == pytest.approx(0.7, abs=0.02)
    assert [nota.orden for nota in notas] == [1, 2]


def test_notas_consecutivas_sin_silencio_se_separan_por_el_cambio_de_altura():
    notas = _analizar([(69, 0.4), (71, 0.4), (72, 0.4)])
    assert [nota.nombre for nota in notas] == ["A4", "B4", "C5"]


def test_el_vibrato_no_parte_la_nota():
    def vibrato(indice, total):
        return 69 + 0.5 * np.sin(2 * np.pi * indice / 20)

    notas = _analizar([(vibrato, 1.0)])
    assert len(notas) == 1
    assert notas[0].nombre == "A4"
    assert notas[0].duracion_s == pytest.approx(1.0, abs=0.05)


def test_un_pico_espurio_se_absorbe_entre_dos_tramos_iguales():
    notas = _analizar([(69, 0.3), (76, 0.02), (69, 0.3)])
    assert len(notas) == 1
    assert notas[0].nombre == "A4"
    assert notas[0].duracion_s == pytest.approx(0.62, abs=0.03)


def test_un_tramo_demasiado_corto_entre_alturas_distintas_se_descarta():
    notas = _analizar([(69, 0.3), (76, 0.02), (72, 0.3)])
    assert [nota.nombre for nota in notas] == ["A4", "C5"]


def test_una_nota_mas_corta_que_el_minimo_se_descarta():
    notas = _analizar([(69, 0.03), (None, 0.3), (71, 0.4)])
    assert [nota.nombre for nota in notas] == ["B4"]


def test_la_confianza_baja_cuenta_como_silencio():
    f0, confianza = curva([(69, 0.5), (71, 0.5)], hop_s=HOP)
    confianza[50:] = 0.2
    notas = curva_a_notas(f0, confianza, hop_s=HOP)
    assert [nota.nombre for nota in notas] == ["A4"]


def test_la_desviacion_en_cents_se_reporta():
    notas = _analizar([(69.25, 0.5)])
    assert notas[0].nombre == "A4"
    assert notas[0].cents == pytest.approx(25, abs=2)


def test_la_confianza_de_la_nota_es_el_promedio_de_sus_tramas():
    notas = _analizar([(69, 0.5)])
    assert notas[0].confianza == pytest.approx(0.95, abs=0.01)


def test_una_curva_toda_en_silencio_no_devuelve_notas():
    assert _analizar([(None, 1.0)]) == []


def test_las_frases_se_cortan_en_los_silencios_largos():
    notas = _analizar([(69, 0.4), (None, 1.0), (71, 0.4), (None, 0.1), (72, 0.4)])
    frases = agrupar_en_frases(notas, silencio_min_s=0.6)
    assert [frase.indice for frase in frases] == [1, 2]
    assert [nota.nombre for nota in frases[0].notas] == ["A4"]
    assert [nota.nombre for nota in frases[1].notas] == ["B4", "C5"]
    assert frases[1].inicio_s == pytest.approx(frases[1].notas[0].inicio_s)
    assert frases[1].fin_s == pytest.approx(frases[1].notas[-1].fin_s)


def test_agrupar_sin_notas_no_devuelve_frases():
    assert agrupar_en_frases([]) == []
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_notas.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.notas'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/notas.py`:

```python
"""Conversión de una curva de afinación continua en notas discretas.

Es el corazón del proyecto. Recibe lo que produce el detector de afinación
(frecuencia y confianza por trama) y devuelve notas con nombre, inicio,
duración, confianza y desviación en cents.
"""
from __future__ import annotations

import warnings

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from motor.contrato import Frase, Nota, hz_a_midi, midi_a_nombre


def _mediana_movil(valores: np.ndarray, ventana: int) -> np.ndarray:
    """Mediana deslizante que ignora los nan. La ventana debe ser impar."""
    if ventana <= 1:
        return valores.copy()
    if ventana % 2 == 0:
        raise ValueError("la ventana de mediana debe ser impar")
    mitad = ventana // 2
    relleno = np.pad(valores, mitad, mode="edge")
    ventanas = sliding_window_view(relleno, ventana)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(ventanas, axis=-1)


def _tramos(alturas: np.ndarray):
    """Corta la serie en tramos consecutivos de igual valor.

    Devuelve una lista de (inicio, fin_exclusivo, valor_o_None).
    """
    tramos = []
    indice = 0
    total = len(alturas)
    while indice < total:
        valor = alturas[indice]
        siguiente = indice + 1
        if np.isnan(valor):
            while siguiente < total and np.isnan(alturas[siguiente]):
                siguiente += 1
            tramos.append((indice, siguiente, None))
        else:
            while siguiente < total and alturas[siguiente] == valor:
                siguiente += 1
            tramos.append((indice, siguiente, int(valor)))
        indice = siguiente
    return tramos


def _absorber_transitorios(alturas, hop_s, estabilidad_min_s):
    """Elimina los tramos demasiado cortos para ser una nota real.

    Si el tramo corto está entre dos tramos de la misma altura, se funde con
    ellos. Si no, se descarta como silencio. Se repite hasta que no queda
    ningún tramo corto, lo cual termina siempre porque cada pasada elimina al
    menos uno y nunca crea uno nuevo.
    """
    minimo = max(1, int(round(estabilidad_min_s / hop_s)))
    salida = alturas.copy()
    while True:
        tramos = _tramos(salida)
        for posicion, (inicio, fin, valor) in enumerate(tramos):
            if valor is None or fin - inicio >= minimo:
                continue
            anterior = tramos[posicion - 1][2] if posicion > 0 else None
            siguiente = tramos[posicion + 1][2] if posicion < len(tramos) - 1 else None
            if anterior is not None and anterior == siguiente:
                salida[inicio:fin] = anterior
            else:
                salida[inicio:fin] = np.nan
            break
        else:
            return salida


CONCENTRACION_MINIMA = 0.5


def estimar_afinacion(f0_hz, confianza, umbral_confianza: float = 0.5) -> float:
    """Desvío global del instrumento respecto a la rejilla de semitonos.

    Media circular de la parte fraccionaria del MIDI continuo sobre las
    tramas con voz. Si las tramas no se concentran (por ejemplo, vibrato
    que barre medio semitono a cada lado), devuelve 0.0 y no se corrige nada.
    """
    f0_hz = np.asarray(f0_hz, dtype=float)
    confianza = np.asarray(confianza, dtype=float)
    midi = hz_a_midi(f0_hz)[confianza >= umbral_confianza]
    midi = midi[~np.isnan(midi)]
    if len(midi) == 0:
        return 0.0
    angulos = 2 * np.pi * (midi - np.round(midi))
    vector = complex(np.mean(np.cos(angulos)), np.mean(np.sin(angulos)))
    if abs(vector) < CONCENTRACION_MINIMA:
        return 0.0
    return float(np.angle(vector) / (2 * np.pi))


def curva_a_notas(
    f0_hz,
    confianza,
    hop_s: float,
    umbral_confianza: float = 0.5,
    ventana_mediana: int = 5,
    estabilidad_min_s: float = 0.05,
    duracion_min_s: float = 0.06,
    afinacion: float = 0.0,
) -> list[Nota]:
    f0_hz = np.asarray(f0_hz, dtype=float)
    confianza = np.asarray(confianza, dtype=float)
    if len(f0_hz) != len(confianza):
        raise ValueError("f0_hz y confianza deben tener la misma longitud")
    if len(f0_hz) == 0:
        return []

    hay_voz = confianza >= umbral_confianza
    midi_continuo = np.where(hay_voz, hz_a_midi(f0_hz), np.nan)
    # El desvío global se resta solo para decidir el nombre de la nota; los
    # cents se calculan más abajo sobre midi_continuo sin corregir.
    suavizado = _mediana_movil(midi_continuo - afinacion, ventana_mediana)
    suavizado = np.where(hay_voz, suavizado, np.nan)
    redondeado = np.where(np.isnan(suavizado), np.nan, np.round(suavizado))
    redondeado = _absorber_transitorios(redondeado, hop_s, estabilidad_min_s)

    minimo_tramas = max(1, int(round(duracion_min_s / hop_s)))
    notas: list[Nota] = []
    for inicio, fin, valor in _tramos(redondeado):
        if valor is None or fin - inicio < minimo_tramas:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mediana_real = np.nanmedian(midi_continuo[inicio:fin])
        desviacion = 0 if np.isnan(mediana_real) else int(round((mediana_real - valor) * 100))
        notas.append(
            Nota(
                orden=len(notas) + 1,
                nombre=midi_a_nombre(valor),
                midi=valor,
                inicio_s=round(inicio * hop_s, 4),
                duracion_s=round((fin - inicio) * hop_s, 4),
                confianza=round(float(np.mean(confianza[inicio:fin])), 4),
                cents=desviacion,
            )
        )
    return notas


def agrupar_en_frases(notas, silencio_min_s: float = 0.6) -> list[Frase]:
    """Corta la lista de notas en frases usando los silencios largos."""
    if not notas:
        return []
    grupos: list[list[Nota]] = [[notas[0]]]
    for nota in notas[1:]:
        anterior = grupos[-1][-1]
        if nota.inicio_s - anterior.fin_s > silencio_min_s:
            grupos.append([])
        grupos[-1].append(nota)
    return [
        Frase(
            indice=posicion + 1,
            inicio_s=grupo[0].inicio_s,
            fin_s=grupo[-1].fin_s,
            notas=tuple(grupo),
        )
        for posicion, grupo in enumerate(grupos)
    ]
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_notas.py -q`
Esperado: 16 tests pasan

- [ ] **Paso 5: Commit**

```bash
git add motor/notas.py tests/test_notas.py
git commit -m "feat: conversión de la curva de afinación a notas y frases"
```

---

### Tarea 6: Utilidades de audio

**Archivos:**
- Crear: `motor/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consume: nada del proyecto; usa `ffprobe`, `ffmpeg`, `soundfile` y `scipy.signal`
- Produce:
  - `ErrorAudio(Exception)`
  - `duracion_s(ruta) -> float`
  - `recortar(entrada, salida, inicio_s, fin_s, sr=44100) -> Path`
  - `cargar_mono(ruta) -> tuple[np.ndarray, int]`
  - `remuestrear(senal, sr_origen, sr_destino) -> np.ndarray`
  - `escribir_wav(ruta, senal, sr) -> Path`

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_audio.py`:

```python
import numpy as np
import pytest
import soundfile as sf

from motor.audio import (
    ErrorAudio,
    cargar_mono,
    duracion_s,
    escribir_wav,
    recortar,
    remuestrear,
)
from tests.senales import secuencia


@pytest.fixture
def wav_de_tres_segundos(tmp_path):
    ruta = tmp_path / "origen.wav"
    señal = secuencia([(440.0, 3.0)], sr=44100)
    sf.write(ruta, señal, 44100)
    return ruta


def test_duracion_lee_el_archivo(wav_de_tres_segundos):
    assert duracion_s(wav_de_tres_segundos) == pytest.approx(3.0, abs=0.05)


def test_duracion_falla_con_claridad_si_el_archivo_no_existe(tmp_path):
    with pytest.raises(ErrorAudio):
        duracion_s(tmp_path / "no_existe.wav")


def test_recortar_produce_la_duracion_pedida(wav_de_tres_segundos, tmp_path):
    salida = recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 1.0, 2.5)
    assert salida.exists()
    assert duracion_s(salida) == pytest.approx(1.5, abs=0.05)


def test_recortar_rechaza_un_rango_fuera_del_audio(wav_de_tres_segundos, tmp_path):
    with pytest.raises(ErrorAudio) as error:
        recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 1.0, 10.0)
    assert "duración" in str(error.value)


def test_recortar_rechaza_un_rango_invertido(wav_de_tres_segundos, tmp_path):
    with pytest.raises(ErrorAudio):
        recortar(wav_de_tres_segundos, tmp_path / "corte.wav", 2.0, 1.0)


def test_cargar_mono_promedia_los_canales(tmp_path):
    ruta = tmp_path / "estereo.wav"
    izquierda = np.ones(1000, dtype=np.float32)
    derecha = np.full(1000, -1.0, dtype=np.float32)
    sf.write(ruta, np.stack([izquierda, derecha], axis=1), 16000, subtype="FLOAT")
    señal, sr = cargar_mono(ruta)
    assert sr == 16000
    assert señal.ndim == 1
    assert np.allclose(señal, 0.0, atol=1e-6)


def test_remuestrear_cambia_la_longitud_proporcionalmente():
    señal = secuencia([(440.0, 1.0)], sr=44100)
    salida = remuestrear(señal, 44100, 16000)
    assert len(salida) == pytest.approx(16000, abs=50)


def test_remuestrear_no_toca_la_senal_si_la_frecuencia_coincide():
    señal = secuencia([(440.0, 0.1)], sr=16000)
    assert remuestrear(señal, 16000, 16000) is señal


def test_escribir_wav_y_volver_a_leerlo(tmp_path):
    señal = secuencia([(440.0, 0.5)], sr=16000)
    ruta = escribir_wav(tmp_path / "salida.wav", señal, 16000)
    leida, sr = cargar_mono(ruta)
    assert sr == 16000
    assert len(leida) == len(señal)
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_audio.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.audio'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/audio.py`:

```python
"""Lectura, recorte y conversión de audio. ffmpeg y ffprobe son externos."""
from __future__ import annotations

import json
import os
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}


class ErrorAudio(Exception):
    """Algo falló al leer, recortar o convertir audio."""


def _ejecutar(comando):
    try:
        return subprocess.run(
            comando, capture_output=True, text=True, check=True,
            encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
        )
    except FileNotFoundError as error:
        raise ErrorAudio(f"no se encontró el programa {comando[0]}") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        raise ErrorAudio(detalle[-1] if detalle else "ffmpeg falló sin mensaje") from error


def duracion_s(ruta) -> float:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"el archivo no existe: {ruta}")
    salida = _ejecutar([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(ruta),
    ])
    try:
        return float(json.loads(salida.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as error:
        raise ErrorAudio(f"ffprobe no pudo leer la duración de {ruta.name}") from error


def recortar(entrada, salida, inicio_s: float, fin_s: float, sr: int = 44100) -> Path:
    """Recorta el rango pedido a WAV mono. Valida el rango antes de trabajar."""
    entrada, salida = Path(entrada), Path(salida)
    if fin_s <= inicio_s:
        raise ErrorAudio("el final del fragmento debe ser posterior al inicio")
    if inicio_s < 0:
        raise ErrorAudio("el inicio del fragmento no puede ser negativo")
    total = duracion_s(entrada)
    if fin_s > total + 0.25:
        raise ErrorAudio(
            f"el rango pedido llega hasta {fin_s:.1f} s pero la duración del audio "
            f"es de {total:.1f} s"
        )
    salida.parent.mkdir(parents=True, exist_ok=True)
    _ejecutar([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{inicio_s:.3f}", "-to", f"{fin_s:.3f}",
        "-i", str(entrada),
        "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le",
        str(salida),
    ])
    if not salida.exists():
        raise ErrorAudio("ffmpeg no generó el recorte")
    return salida


def cargar_mono(ruta) -> tuple[np.ndarray, int]:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorAudio(f"el archivo no existe: {ruta}")
    datos, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    return datos.mean(axis=1), int(sr)


def remuestrear(senal: np.ndarray, sr_origen: int, sr_destino: int) -> np.ndarray:
    if sr_origen == sr_destino:
        return senal
    razon = Fraction(int(sr_destino), int(sr_origen)).limit_denominator(1000)
    return resample_poly(senal, razon.numerator, razon.denominator).astype(np.float32)


def escribir_wav(ruta, senal: np.ndarray, sr: int) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(ruta), np.asarray(senal, dtype=np.float32), int(sr))
    return ruta
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_audio.py -q`
Esperado: 9 tests pasan

- [ ] **Paso 5: Commit**

```bash
git add motor/audio.py tests/test_audio.py
git commit -m "feat: utilidades de audio con recorte validado por ffprobe"
```

---

### Tarea 7: Detección de afinación con CREPE

**Archivos:**
- Crear: `motor/afinacion.py`
- Test: `tests/test_afinacion.py`

**Interfaces:**
- Consume: `motor.audio.cargar_mono`, `motor.audio.remuestrear`
- Produce:
  - `SR_CREPE = 16000`
  - `detectar_afinacion(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full") -> tuple[np.ndarray, np.ndarray, float]` que devuelve `(f0_hz, confianza, hop_s)`

Nota para quien implemente: `torchcrepe` trabaja obligatoriamente a 16 kHz y espera un tensor de forma `(1, muestras)`. La confianza que devuelve se llama periodicidad en su documentación y es exactamente el valor de 0 a 1 que el contrato llama `confianza`.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_afinacion.py`:

```python
import numpy as np
import pytest
import soundfile as sf

from motor.afinacion import SR_CREPE, detectar_afinacion
from tests.senales import secuencia


@pytest.fixture
def wav_la_y_si(tmp_path):
    ruta = tmp_path / "la_si.wav"
    señal = secuencia([(440.0, 0.6), (None, 0.3), (493.88, 0.6)], sr=44100)
    sf.write(ruta, señal, 44100)
    return ruta


@pytest.mark.lento
def test_detecta_el_la_de_referencia(wav_la_y_si):
    f0, confianza, hop_s = detectar_afinacion(
        wav_la_y_si, fmin_hz=200.0, fmax_hz=1000.0, hop_ms=10, dispositivo="cpu"
    )
    assert hop_s == pytest.approx(0.01)
    assert len(f0) == len(confianza)
    seguro = confianza > 0.5
    assert seguro.sum() > 50
    primera_mitad = f0[: len(f0) // 3][seguro[: len(f0) // 3]]
    assert np.median(primera_mitad) == pytest.approx(440.0, rel=0.02)


@pytest.mark.lento
def test_la_cantidad_de_tramas_corresponde_a_la_duracion(wav_la_y_si):
    f0, _, hop_s = detectar_afinacion(
        wav_la_y_si, fmin_hz=200.0, fmax_hz=1000.0, dispositivo="cpu"
    )
    assert len(f0) * hop_s == pytest.approx(1.5, abs=0.1)


def test_el_salto_en_muestras_es_coherente_con_la_frecuencia_de_crepe():
    assert SR_CREPE == 16000
    assert int(SR_CREPE * 10 / 1000) == 160
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_afinacion.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.afinacion'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/afinacion.py`:

```python
"""Detección de la frecuencia fundamental con CREPE.

Devuelve dos series por trama: la frecuencia estimada y la confianza de
esa estimación. La confianza es lo que después permite distinguir el
sonido real del silencio y avisar al usuario de qué notas revisar.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from motor.audio import cargar_mono, remuestrear

SR_CREPE = 16000


def detectar_afinacion(
    ruta_wav,
    fmin_hz: float,
    fmax_hz: float,
    hop_ms: int = 10,
    dispositivo: str = "cpu",
    modelo: str = "full",
) -> tuple[np.ndarray, np.ndarray, float]:
    import torch
    import torchcrepe

    senal, sr = cargar_mono(Path(ruta_wav))
    senal = remuestrear(senal, sr, SR_CREPE)
    tensor = torch.from_numpy(np.ascontiguousarray(senal, dtype=np.float32))[None]

    salto = int(SR_CREPE * hop_ms / 1000)
    f0, confianza = torchcrepe.predict(
        tensor,
        SR_CREPE,
        salto,
        float(fmin_hz),
        float(fmax_hz),
        modelo,
        batch_size=512,
        device=dispositivo,
        return_periodicity=True,
    )
    return (
        f0[0].detach().cpu().numpy().astype(float),
        confianza[0].detach().cpu().numpy().astype(float),
        hop_ms / 1000.0,
    )
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_afinacion.py -q`
Esperado: 3 tests pasan. La primera ejecución descarga y carga el modelo de CREPE y puede tardar cerca de un minuto.

- [ ] **Paso 5: Commit**

```bash
git add motor/afinacion.py tests/test_afinacion.py
git commit -m "feat: detección de afinación con CREPE"
```

---

### Tarea 8: Pipeline sobre audio limpio (hito de la fase 0)

Al terminar esta tarea el sistema ya sirve: se le da una grabación del teléfono y devuelve las notas. Todavía sin YouTube, sin separación y sin archivos exportados.

**Archivos:**
- Crear: `motor/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consume: `motor.config.Config`, `motor.config.resolver_dispositivo`, `motor.afinacion.detectar_afinacion`, `motor.notas.curva_a_notas`, `motor.notas.agrupar_en_frases`, `motor.contrato.*`, `motor.audio.duracion_s`
- Produce:
  - `ErrorPipeline(Exception)`
  - `analizar_recorte(ruta_wav, fragmento, config=None, separar=False, progreso=None) -> Resultado`
  - `_DETECTAR = detectar_afinacion` a nivel de módulo, para que los tests lo puedan sustituir sin cargar CREPE

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_pipeline.py`:

```python
import pytest
import soundfile as sf

from motor import pipeline
from motor.config import Config
from motor.contrato import Fragmento
from tests.senales import curva, secuencia


@pytest.fixture
def recorte(tmp_path):
    ruta = tmp_path / "recorte.wav"
    sf.write(ruta, secuencia([(440.0, 0.5), (None, 0.8), (493.88, 0.5)], sr=44100), 44100)
    return ruta


@pytest.fixture
def detector_falso(monkeypatch):
    """Sustituye CREPE por una curva conocida para no cargar el modelo."""
    def detectar(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69, 0.5), (None, 0.8), (71, 0.5)], hop_s=hop_ms / 1000)
        return f0, confianza, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar)


def _fragmento():
    return Fragmento(titulo="Ensayo", fuente="archivo", referencia="recorte.wav",
                     inicio_s=30.0, fin_s=31.8)


def test_analizar_devuelve_las_notas_en_frases(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert [frase.indice for frase in resultado.frases] == [1, 2]
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]


def test_los_tiempos_son_relativos_al_inicio_del_fragmento(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.notas[0].inicio_s == pytest.approx(0.0, abs=0.02)
    assert resultado.fragmento.inicio_s == 30.0


def test_registra_los_parametros_del_analisis(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.analisis.separacion == "ninguna"
    assert resultado.analisis.hop_ms == 10
    assert resultado.analisis.fmin_hz == pytest.approx(261.63)
    assert resultado.analisis.dispositivo in {"cpu", "cuda"}


def test_avisa_cuando_toda_la_confianza_es_baja(recorte, monkeypatch):
    def detectar_ruido(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69, 1.0)], hop_s=hop_ms / 1000)
        return f0, confianza * 0.0 + 0.2, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar_ruido)
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.frases == ()
    assert any("no se detectó" in aviso.lower() for aviso in resultado.avisos)


def test_registra_la_afinacion_del_instrumento_y_avisa_si_es_grande(recorte, monkeypatch):
    def detectar_desafinado(ruta_wav, fmin_hz, fmax_hz, hop_ms=10, dispositivo="cpu", modelo="full"):
        f0, confianza = curva([(69.4, 0.6), (71.4, 0.6)], hop_s=hop_ms / 1000)
        return f0, confianza, hop_ms / 1000

    monkeypatch.setattr(pipeline, "_DETECTAR", detectar_desafinado)
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.analisis.afinacion_cents == pytest.approx(40, abs=3)
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert any("afinad" in aviso.lower() for aviso in resultado.avisos)


def test_rechaza_un_fragmento_mas_largo_que_el_limite(recorte, detector_falso):
    config = Config.desde_entorno({"QUENOTAS_MAX_FRAGMENTO_S": "1.0"})
    with pytest.raises(pipeline.ErrorPipeline) as error:
        pipeline.analizar_recorte(recorte, _fragmento(), config=config, separar=False)
    assert "180" in str(error.value) or "1.0" in str(error.value)


def test_informa_del_progreso(recorte, detector_falso):
    mensajes = []
    pipeline.analizar_recorte(recorte, _fragmento(), separar=False, progreso=mensajes.append)
    assert any("afinación" in mensaje for mensaje in mensajes)
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_pipeline.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.pipeline'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/pipeline.py`:

```python
"""Orquestación de las etapas del análisis.

En esta fase solo cubre audio ya limpio y recortado. Las etapas de
descarga y separación se añaden más adelante sin cambiar la firma.
"""
from __future__ import annotations

from pathlib import Path

from motor.afinacion import detectar_afinacion
from motor.audio import duracion_s
from motor.config import Config, resolver_dispositivo
from motor.contrato import Fragmento, ParametrosAnalisis, Resultado
from motor.notas import agrupar_en_frases, curva_a_notas, estimar_afinacion

# Punto de sustitución para las pruebas: así se puede probar el pipeline
# entero sin cargar CREPE.
_DETECTAR = detectar_afinacion

AFINACION_AVISO_CENTS = 30


class ErrorPipeline(Exception):
    """El análisis no se pudo completar."""


def _avisar(progreso, mensaje):
    if progreso is not None:
        progreso(mensaje)


def analizar_recorte(
    ruta_wav,
    fragmento: Fragmento,
    config: Config | None = None,
    separar: bool = False,
    progreso=None,
) -> Resultado:
    config = config or Config.desde_entorno()
    ruta_wav = Path(ruta_wav)

    duracion = duracion_s(ruta_wav)
    if duracion > config.max_fragmento_s:
        raise ErrorPipeline(
            f"el fragmento dura {duracion:.1f} s y el límite es "
            f"{config.max_fragmento_s:.1f} s. Recorta un trozo más corto."
        )

    dispositivo = resolver_dispositivo(config.dispositivo)
    avisos = []
    if dispositivo == "cpu" and config.dispositivo != "cpu":
        avisos.append("No hay GPU disponible, el análisis corre en CPU y tarda más.")

    _avisar(progreso, "Detectando la afinación")
    f0, confianza, hop_s = _DETECTAR(
        ruta_wav,
        fmin_hz=config.fmin_hz,
        fmax_hz=config.fmax_hz,
        hop_ms=config.hop_ms,
        dispositivo=dispositivo,
        modelo=config.modelo_afinacion,
    )

    _avisar(progreso, "Convirtiendo la curva en notas")
    afinacion = estimar_afinacion(f0, confianza, umbral_confianza=config.umbral_confianza)
    afinacion_cents = int(round(afinacion * 100))
    notas = curva_a_notas(
        f0,
        confianza,
        hop_s=hop_s,
        umbral_confianza=config.umbral_confianza,
        ventana_mediana=config.ventana_mediana,
        estabilidad_min_s=config.estabilidad_min_s,
        duracion_min_s=config.duracion_min_s,
        afinacion=afinacion,
    )
    frases = agrupar_en_frases(notas, silencio_min_s=config.silencio_frase_s)

    if not notas:
        avisos.append(
            "No se detectó ninguna melodía con confianza suficiente. Es probable "
            "que en este rango el instrumento no toque o no destaque sobre la banda."
        )
    elif sum(nota.confianza for nota in notas) / len(notas) < 0.65:
        avisos.append(
            "La confianza media es baja. Revisa las notas al oído antes de darlas "
            "por buenas, o prueba con otro rango donde la melodía destaque más."
        )
    if abs(afinacion_cents) > AFINACION_AVISO_CENTS:
        sentido = "por encima" if afinacion_cents > 0 else "por debajo"
        avisos.append(
            f"El instrumento suena afinado {abs(afinacion_cents)} cents {sentido} "
            f"de la referencia de 440 Hz. Los nombres de las notas ya lo tienen en "
            f"cuenta; si tocas con la quena, ajústala o transpón de oído."
        )

    return Resultado(
        fragmento=fragmento,
        analisis=ParametrosAnalisis(
            separacion=config.modelo_separacion if separar else "ninguna",
            modelo_afinacion=f"crepe:{config.modelo_afinacion}",
            hop_ms=config.hop_ms,
            fmin_hz=config.fmin_hz,
            fmax_hz=config.fmax_hz,
            dispositivo=dispositivo,
            afinacion_cents=afinacion_cents,
        ),
        frases=tuple(frases),
        archivos={},
        avisos=tuple(avisos),
    )
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests -q`
Esperado: toda la suite pasa

- [ ] **Paso 5: Commit**

```bash
git add motor/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline de análisis sobre audio limpio"
```

---

### Tarea 9: Exportar a MIDI y a TXT

**Archivos:**
- Crear: `motor/exportar.py`
- Test: `tests/test_exportar.py`

**Interfaces:**
- Consume: `motor.contrato.Resultado`, `motor.contrato.Frase`, `motor.contrato.formato_tiempo`, `motor.contrato.etiqueta_confianza`
- Produce:
  - `a_midi(frases, ruta, programa=73, velocidad=90) -> Path`
  - `a_txt(resultado, ruta) -> Path`

Nota: el programa 73 del estándar General MIDI es la flauta, que es lo más cercano a una quena y hace que el archivo suene reconocible en cualquier reproductor.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_exportar.py`:

```python
import pretty_midi
import pytest

from motor.contrato import Fragmento, Frase, Nota, ParametrosAnalisis, Resultado
from motor.exportar import a_midi, a_txt


def _resultado():
    notas_frase_uno = (
        Nota(orden=1, nombre="G4", midi=67, inicio_s=0.4, duracion_s=0.42,
             confianza=0.93, cents=-12),
        Nota(orden=2, nombre="A4", midi=69, inicio_s=0.9, duracion_s=0.21,
             confianza=0.71, cents=4),
    )
    notas_frase_dos = (
        Nota(orden=3, nombre="B4", midi=71, inicio_s=2.0, duracion_s=0.6,
             confianza=0.40, cents=30),
    )
    return Resultado(
        fragmento=Fragmento(titulo="Huayno de prueba", fuente="youtube",
                            referencia="https://ejemplo/abc", inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="htdemucs", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cuda"),
        frases=(
            Frase(indice=1, inicio_s=0.4, fin_s=1.11, notas=notas_frase_uno),
            Frase(indice=2, inicio_s=2.0, fin_s=2.6, notas=notas_frase_dos),
        ),
        archivos={},
        avisos=("La confianza media es baja.",),
    )


def test_el_midi_conserva_alturas_y_tiempos(tmp_path):
    ruta = a_midi(_resultado().frases, tmp_path / "melodia.mid")
    leido = pretty_midi.PrettyMIDI(str(ruta))
    assert len(leido.instruments) == 1
    assert leido.instruments[0].program == 73
    alturas = [nota.pitch for nota in leido.instruments[0].notes]
    assert alturas == [67, 69, 71]
    primera = leido.instruments[0].notes[0]
    assert primera.start == pytest.approx(0.4, abs=0.01)
    assert primera.end == pytest.approx(0.82, abs=0.01)


def test_el_midi_sin_notas_se_genera_igual(tmp_path):
    ruta = a_midi((), tmp_path / "vacio.mid")
    assert ruta.exists()
    # pretty_midi solo crea instrumentos al encontrar notas: al releer un
    # archivo vacío, instruments queda [] (verificado con 0.2.11.post0).
    leido = pretty_midi.PrettyMIDI(str(ruta))
    assert sum(len(instrumento.notes) for instrumento in leido.instruments) == 0


def test_el_txt_muestra_tiempos_absolutos_y_agrupa_por_frases(tmp_path):
    ruta = a_txt(_resultado(), tmp_path / "notas.txt")
    texto = ruta.read_text(encoding="utf-8")
    assert "Huayno de prueba" in texto
    assert "Frase 1" in texto and "Frase 2" in texto
    assert "0:30.4" in texto          # 30.0 del fragmento + 0.4 de la nota
    assert "G4" in texto and "B4" in texto
    assert "alta" in texto and "baja" in texto
    assert "La confianza media es baja." in texto


def test_el_txt_indica_cuando_no_hay_notas(tmp_path):
    vacio = Resultado(
        fragmento=_resultado().fragmento,
        analisis=_resultado().analisis,
        frases=(),
        archivos={},
        avisos=(),
    )
    texto = a_txt(vacio, tmp_path / "vacio.txt").read_text(encoding="utf-8")
    assert "No se detectaron notas" in texto
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_exportar.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.exportar'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/exportar.py`:

```python
"""Generación de los archivos que se lleva el usuario.

Todos salen de la misma estructura de datos. Los tiempos guardados en el
contrato son relativos al fragmento; aquí se les suma el desplazamiento
de la canción para que el usuario vea el minuto real.
"""
from __future__ import annotations

from pathlib import Path

from motor.contrato import etiqueta_confianza, formato_tiempo

PROGRAMA_FLAUTA = 73


def a_midi(frases, ruta, programa: int = PROGRAMA_FLAUTA, velocidad: int = 90) -> Path:
    import pretty_midi

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    archivo = pretty_midi.PrettyMIDI()
    instrumento = pretty_midi.Instrument(program=programa, name="melodia")
    for frase in frases:
        for nota in frase.notas:
            instrumento.notes.append(
                pretty_midi.Note(
                    velocity=velocidad,
                    pitch=int(nota.midi),
                    start=float(nota.inicio_s),
                    end=float(nota.inicio_s + nota.duracion_s),
                )
            )
    archivo.instruments.append(instrumento)
    archivo.write(str(ruta))
    return ruta


def _lineas_de_texto(resultado) -> list[str]:
    desplazamiento = resultado.fragmento.inicio_s
    lineas = [
        "Quenotas",
        f"Canción: {resultado.fragmento.titulo}",
        f"Fuente: {resultado.fragmento.referencia}",
        f"Fragmento: {formato_tiempo(resultado.fragmento.inicio_s)} a "
        f"{formato_tiempo(resultado.fragmento.fin_s)}",
        f"Análisis: separación {resultado.analisis.separacion}, "
        f"{resultado.analisis.modelo_afinacion}, {resultado.analisis.dispositivo}",
        "",
    ]
    if not resultado.frases:
        lineas.append("No se detectaron notas en este fragmento.")
    for frase in resultado.frases:
        lineas.append(
            f"Frase {frase.indice}  ({formato_tiempo(desplazamiento + frase.inicio_s)} a "
            f"{formato_tiempo(desplazamiento + frase.fin_s)})"
        )
        for nota in frase.notas:
            lineas.append(
                f"  {nota.orden:>3}  {nota.nombre:<4} "
                f"{formato_tiempo(desplazamiento + nota.inicio_s):>8}  "
                f"{nota.duracion_s:5.2f} s  confianza {etiqueta_confianza(nota.confianza)}"
            )
        lineas.append("")
    if resultado.avisos:
        lineas.append("Avisos:")
        lineas.extend(f"  - {aviso}" for aviso in resultado.avisos)
    return lineas


def a_txt(resultado, ruta) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(_lineas_de_texto(resultado)) + "\n", encoding="utf-8")
    return ruta
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_exportar.py -q`
Esperado: 4 tests pasan

(`pretty_midi` 0.2.11.post0 funciona con numpy 2.5; se verificó el 2026-09-05. No hace falta variante con `mido`.)

- [ ] **Paso 5: Commit**

```bash
git add motor/exportar.py tests/test_exportar.py
git commit -m "feat: exportación a MIDI y a texto"
```

---

### Tarea 10: Exportar a PDF y sonificar las notas

La sonificación es la pista de verificación: si suena igual que la melodía original, el análisis está bien.

**Archivos:**
- Modificar: `motor/exportar.py` (añadir al final)
- Modificar: `tests/test_exportar.py` (añadir al final)

**Interfaces:**
- Consume: lo de la tarea 9, más `motor.contrato.midi_a_hz` y `motor.audio.escribir_wav`
- Produce:
  - `a_pdf(resultado, ruta) -> Path`
  - `sonificar(frases, ruta, duracion_total_s, sr=44100, amplitud=0.3, rampa_s=0.005) -> Path`

- [ ] **Paso 1: Escribir el test que falla**

Añadir al final de `tests/test_exportar.py`:

```python
import numpy as np
import soundfile as sf

from motor.exportar import a_pdf, sonificar


def test_el_pdf_se_genera_y_no_esta_vacio(tmp_path):
    ruta = a_pdf(_resultado(), tmp_path / "notas.pdf")
    assert ruta.exists()
    contenido = ruta.read_bytes()
    assert contenido.startswith(b"%PDF")
    assert len(contenido) > 1000


def test_el_pdf_de_un_resultado_sin_notas_tambien_se_genera(tmp_path):
    vacio = Resultado(fragmento=_resultado().fragmento, analisis=_resultado().analisis,
                      frases=(), archivos={}, avisos=())
    assert a_pdf(vacio, tmp_path / "vacio.pdf").exists()


def test_el_pdf_aguanta_titulos_fuera_de_latin1(tmp_path):
    base = _resultado()
    raro = Resultado(
        fragmento=Fragmento(titulo="Huayno ♪ – “en vivo” 山", fuente="youtube",
                            referencia=base.fragmento.referencia, inicio_s=30.0, fin_s=90.0),
        analisis=base.analisis, frases=base.frases, archivos={},
        avisos=("aviso con ♪",),
    )
    assert a_pdf(raro, tmp_path / "raro.pdf").exists()


def test_la_sonificacion_dura_lo_pedido_y_suena_donde_hay_notas(tmp_path):
    ruta = sonificar(_resultado().frases, tmp_path / "notas.wav", duracion_total_s=3.0)
    señal, sr = sf.read(ruta)
    assert sr == 44100
    assert len(señal) == 3 * 44100
    silencio_inicial = señal[: int(0.35 * sr)]
    zona_con_nota = señal[int(0.45 * sr) : int(0.75 * sr)]
    assert np.max(np.abs(silencio_inicial)) < 1e-6
    assert np.max(np.abs(zona_con_nota)) > 0.1


def test_la_sonificacion_sin_notas_es_silencio(tmp_path):
    ruta = sonificar((), tmp_path / "silencio.wav", duracion_total_s=1.0)
    señal, _ = sf.read(ruta)
    assert np.max(np.abs(señal)) == 0.0
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_exportar.py -q`
Esperado: FALLA con `ImportError: cannot import name 'a_pdf' from 'motor.exportar'`

- [ ] **Paso 3: Escribir la implementación**

Añadir al final de `motor/exportar.py`:

```python
def _latin1(texto) -> str:
    """Las fuentes básicas de fpdf2 solo aceptan Latin-1. Un título de
    YouTube con ♪, guion largo o comillas tipográficas reventaría el PDF."""
    return str(texto).encode("latin-1", "replace").decode("latin-1")


def a_pdf(resultado, ruta) -> Path:
    """PDF pensado para imprimir y poner en el atril."""
    from fpdf import FPDF

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    desplazamiento = resultado.fragmento.inicio_s

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _latin1(resultado.fragmento.titulo or "Sin título"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6,
        f"Fragmento {formato_tiempo(resultado.fragmento.inicio_s)} a "
        f"{formato_tiempo(resultado.fragmento.fin_s)}   |   "
        f"{resultado.analisis.modelo_afinacion}   |   "
        f"separación {resultado.analisis.separacion}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.ln(4)

    if not resultado.frases:
        pdf.set_font("Helvetica", "", 12)
        pdf.cell(0, 8, "No se detectaron notas en este fragmento.",
                 new_x="LMARGIN", new_y="NEXT")

    for frase in resultado.frases:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(
            0, 8,
            f"Frase {frase.indice}   "
            f"({formato_tiempo(desplazamiento + frase.inicio_s)} a "
            f"{formato_tiempo(desplazamiento + frase.fin_s)})",
            new_x="LMARGIN", new_y="NEXT",
        )
        pdf.set_font("Courier", "B", 10)
        for etiqueta, ancho in (("#", 14), ("Nota", 22), ("Inicio", 26),
                                ("Duración", 26), ("Confianza", 26)):
            pdf.cell(ancho, 6, etiqueta, border="B")
        pdf.ln()
        pdf.set_font("Courier", "", 10)
        for nota in frase.notas:
            pdf.cell(14, 6, str(nota.orden))
            pdf.cell(22, 6, nota.nombre)
            pdf.cell(26, 6, formato_tiempo(desplazamiento + nota.inicio_s))
            pdf.cell(26, 6, f"{nota.duracion_s:.2f} s")
            pdf.cell(26, 6, etiqueta_confianza(nota.confianza))
            pdf.ln()
        pdf.ln(3)

    if resultado.avisos:
        pdf.set_font("Helvetica", "I", 9)
        for aviso in resultado.avisos:
            pdf.multi_cell(0, 5, _latin1(f"Aviso: {aviso}"))

    pdf.output(str(ruta))
    return ruta


def sonificar(frases, ruta, duracion_total_s: float, sr: int = 44100,
              amplitud: float = 0.3, rampa_s: float = 0.005) -> Path:
    """Convierte las notas detectadas en tonos simples alineados con el fragmento."""
    import numpy as np

    from motor.audio import escribir_wav
    from motor.contrato import midi_a_hz

    total = max(1, int(round(duracion_total_s * sr)))
    senal = np.zeros(total, dtype=np.float32)
    for frase in frases:
        for nota in frase.notas:
            muestras = int(round(nota.duracion_s * sr))
            if muestras <= 0:
                continue
            t = np.arange(muestras) / sr
            onda = amplitud * np.sin(2 * np.pi * midi_a_hz(nota.midi) * t)
            rampa = min(int(rampa_s * sr), muestras // 2)
            if rampa > 0:
                onda[:rampa] *= np.linspace(0.0, 1.0, rampa)
                onda[-rampa:] *= np.linspace(1.0, 0.0, rampa)
            inicio = int(round(nota.inicio_s * sr))
            fin = min(inicio + muestras, total)
            if inicio >= total:
                continue
            senal[inicio:fin] += onda[: fin - inicio].astype(np.float32)
    return escribir_wav(ruta, np.clip(senal, -1.0, 1.0), sr)
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_exportar.py -q`
Esperado: 9 tests pasan

- [ ] **Paso 5: Commit**

```bash
git add motor/exportar.py tests/test_exportar.py
git commit -m "feat: exportación a PDF y sonificación de las notas detectadas"
```

---

### Tarea 11: Conectar los exportadores al pipeline

**Archivos:**
- Modificar: `motor/pipeline.py`
- Modificar: `tests/test_pipeline.py` (añadir al final)

**Interfaces:**
- Consume: `motor.exportar.a_midi`, `a_txt`, `a_pdf`, `sonificar`
- Produce: `analizar_recorte(..., salidas_en=None)` que cuando recibe un directorio rellena `Resultado.archivos` con las claves `mezcla_wav`, `melodia_wav`, `notas_wav`, `midi`, `txt`, `pdf`

**Regla:** un archivo de salida que falla no tumba el análisis. Las notas ya están calculadas y son lo caro; si el PDF o el MIDI revientan, se omite esa clave de `archivos` y se añade un aviso. La pantalla y las descargas ya toleran claves ausentes (dan 404 en esa descarga y nada más).

- [ ] **Paso 1: Escribir el test que falla**

Añadir al final de `tests/test_pipeline.py`:

```python
def test_genera_los_archivos_cuando_se_le_da_un_directorio(recorte, detector_falso, tmp_path):
    salidas = tmp_path / "salidas"
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=salidas
    )
    assert set(resultado.archivos) >= {"mezcla_wav", "notas_wav", "midi", "txt", "pdf"}
    for clave, ruta in resultado.archivos.items():
        assert Path(ruta).exists(), f"falta el archivo de {clave}"


def test_sin_directorio_de_salida_no_genera_archivos(recorte, detector_falso):
    resultado = pipeline.analizar_recorte(recorte, _fragmento(), separar=False)
    assert resultado.archivos == {}


def test_un_exportador_que_falla_deja_aviso_y_no_tumba_el_analisis(
    recorte, detector_falso, tmp_path, monkeypatch
):
    def revienta(resultado, ruta):
        raise RuntimeError("fuente no encontrada")

    monkeypatch.setattr(pipeline, "a_pdf", revienta)
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=tmp_path / "salidas"
    )
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert "pdf" not in resultado.archivos
    assert "midi" in resultado.archivos
    assert any("PDF" in aviso for aviso in resultado.avisos)


def test_si_no_se_puede_crear_la_carpeta_de_salida_se_avisa_y_se_conservan_las_notas(
    recorte, detector_falso
):
    # Una carpeta "dentro" de un archivo no se puede crear: mkdir lanza OSError.
    resultado = pipeline.analizar_recorte(
        recorte, _fragmento(), separar=False, salidas_en=recorte / "salidas"
    )
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert set(resultado.archivos) == {"mezcla_wav"}
    assert any("carpeta" in aviso.lower() for aviso in resultado.avisos)
```

Añadir al principio del mismo archivo: `from pathlib import Path`

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_pipeline.py -q`
Esperado: FALLA con `TypeError: analizar_recorte() got an unexpected keyword argument 'salidas_en'`

- [ ] **Paso 3: Escribir la implementación**

En `motor/pipeline.py`, añadir el import y sustituir el final de `analizar_recorte`:

```python
from motor.exportar import a_midi, a_pdf, a_txt, sonificar
```

Cambiar la firma a:

```python
def analizar_recorte(
    ruta_wav,
    fragmento: Fragmento,
    config: Config | None = None,
    separar: bool = False,
    progreso=None,
    salidas_en=None,
    melodia_wav=None,
) -> Resultado:
```

Y sustituir el `return` final por:

```python
    resultado = Resultado(
        fragmento=fragmento,
        analisis=ParametrosAnalisis(
            separacion=config.modelo_separacion if separar else "ninguna",
            modelo_afinacion=f"crepe:{config.modelo_afinacion}",
            hop_ms=config.hop_ms,
            fmin_hz=config.fmin_hz,
            fmax_hz=config.fmax_hz,
            dispositivo=dispositivo,
        ),
        frases=tuple(frases),
        archivos={},
        avisos=tuple(avisos),
    )

    if salidas_en is None:
        return resultado

    _avisar(progreso, "Generando los archivos de salida")
    salidas = Path(salidas_en)
    archivos = {"mezcla_wav": str(ruta_wav)}
    if melodia_wav is not None:
        archivos["melodia_wav"] = str(melodia_wav)
    avisos_salida = []
    try:
        salidas.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        # Sin carpeta no hay dónde escribir, pero las notas ya están: se devuelven.
        return Resultado(
            fragmento=resultado.fragmento,
            analisis=resultado.analisis,
            frases=resultado.frases,
            archivos=archivos,
            avisos=resultado.avisos
            + (f"No se pudo crear la carpeta de salida ({error}); no se generaron archivos.",),
        )

    def intentar(clave, etiqueta, generar):
        """Un archivo que falla se omite con aviso; nunca tumba el resultado."""
        try:
            archivos[clave] = str(generar())
        except Exception as error:  # noqa: BLE001
            avisos_salida.append(f"No se pudo generar el {etiqueta} ({error}).")

    intentar("notas_wav", "audio de notas",
             lambda: sonificar(resultado.frases, salidas / "notas.wav", duracion))
    intentar("midi", "MIDI", lambda: a_midi(resultado.frases, salidas / "melodia.mid"))
    intentar("txt", "TXT", lambda: a_txt(resultado, salidas / "notas.txt"))
    intentar("pdf", "PDF", lambda: a_pdf(resultado, salidas / "notas.pdf"))
    return Resultado(
        fragmento=resultado.fragmento,
        analisis=resultado.analisis,
        frases=resultado.frases,
        archivos=archivos,
        avisos=resultado.avisos + tuple(avisos_salida),
    )
```

Los nombres `a_pdf`, `a_midi`, `a_txt` y `sonificar` se llaman a través del módulo (`from motor.exportar import ...` a nivel de módulo, sin alias), para que los tests puedan sustituirlos con `monkeypatch.setattr(pipeline, "a_pdf", ...)`.

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests -q`
Esperado: toda la suite pasa

- [ ] **Paso 5: Commit**

```bash
git add motor/pipeline.py tests/test_pipeline.py
git commit -m "feat: el pipeline genera MIDI, TXT, PDF y sonificación"
```

---

### Tarea 12: Descarga desde YouTube

**Archivos:**
- Crear: `motor/descarga.py`
- Test: `tests/test_descarga.py`

**Interfaces:**
- Consume: nada del proyecto
- Produce:
  - `ErrorDescarga(Exception)`
  - `es_url(texto: str) -> bool`
  - `obtener_info(url) -> tuple[str, str]` que devuelve `(id_del_video, titulo)` en una sola llamada de red, o `("", "")` si falla
  - `descargar_audio(url, cache_dir, id_video="") -> Path`
  - `_EJECUTAR` a nivel de módulo, envoltorio de `subprocess.run` que los tests sustituyen

Ninguna prueba toca la red. `_EJECUTAR` es el único punto que habla con el exterior y se sustituye entero.

**Caché por id de video.** El flujo del usuario es frase por frase: cinco o seis fragmentos de la misma canción. Descargarla cada vez es cinco veces más lento, cinco oportunidades de que YouTube pida verificación, y cinco copias en disco. Por eso `descargar_audio` guarda en `cache_dir/<id>.<ext>` y, si ya existe, lo devuelve sin tocar la red. Se descarga `bestaudio` en su formato nativo (m4a u opus, unos 5 MB por canción) y no WAV: `recortar` acepta cualquier formato porque quien convierte es ffmpeg. Los archivos `.part` y `.ytdl` de una descarga interrumpida no cuentan como caché.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_descarga.py`:

```python
import subprocess
import types

import pytest

from motor import descarga


def _respuesta(stdout="", stderr="", codigo=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=codigo)


def test_reconoce_una_url():
    assert descarga.es_url("https://www.youtube.com/watch?v=abc")
    assert descarga.es_url("http://youtu.be/abc")
    assert not descarga.es_url("C:/audios/ensayo.wav")
    assert not descarga.es_url("ensayo.wav")


def test_obtener_info_devuelve_id_y_titulo_en_una_llamada(monkeypatch):
    llamadas = []

    def simular(comando):
        llamadas.append(comando)
        return _respuesta(stdout="abc123\nHuayno de prueba\n")

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    assert descarga.obtener_info("https://youtu.be/abc123") == ("abc123", "Huayno de prueba")
    assert len(llamadas) == 1


def test_obtener_info_no_revienta_si_falla(monkeypatch):
    def falla(comando):
        raise subprocess.CalledProcessError(1, comando, stderr="Video unavailable")

    monkeypatch.setattr(descarga, "_EJECUTAR", falla)
    assert descarga.obtener_info("https://youtu.be/abc") == ("", "")


def test_descargar_guarda_por_id_en_formato_nativo(monkeypatch, tmp_path):
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        (tmp_path / "abc123.m4a").write_bytes(b"fingido")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"
    assert "-x" not in capturado["comando"]          # sin convertir a WAV


def test_descargar_reutiliza_el_archivo_en_cache(monkeypatch, tmp_path):
    (tmp_path / "abc123.m4a").write_bytes(b"ya estaba")

    def no_debia_llamarse(comando):
        raise AssertionError("no debía tocar la red: el archivo ya estaba en caché")

    monkeypatch.setattr(descarga, "_EJECUTAR", no_debia_llamarse)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"


def test_una_descarga_a_medias_no_cuenta_como_cache(monkeypatch, tmp_path):
    (tmp_path / "abc123.m4a.part").write_bytes(b"incompleto")

    def simular(comando):
        (tmp_path / "abc123.m4a").write_bytes(b"completo")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path, id_video="abc123")
    assert ruta == tmp_path / "abc123.m4a"


def test_descargar_averigua_el_id_si_no_se_lo_dan(monkeypatch, tmp_path):
    def simular(comando):
        if "--skip-download" in comando:
            return _respuesta(stdout="abc123\nHuayno\n")
        (tmp_path / "abc123.webm").write_bytes(b"fingido")
        return _respuesta()

    monkeypatch.setattr(descarga, "_EJECUTAR", simular)
    ruta = descarga.descargar_audio("https://youtu.be/abc123", tmp_path)
    assert ruta.name == "abc123.webm"


def test_descargar_avisa_con_claridad_si_youtube_bloquea(monkeypatch, tmp_path):
    def bloqueado(comando):
        raise subprocess.CalledProcessError(
            1, comando, stderr="ERROR: Sign in to confirm you are not a bot"
        )

    monkeypatch.setattr(descarga, "_EJECUTAR", bloqueado)
    with pytest.raises(descarga.ErrorDescarga) as error:
        descarga.descargar_audio("https://youtu.be/abc", tmp_path, id_video="abc")
    mensaje = str(error.value)
    assert "no se pudo descargar" in mensaje.lower()
    assert "sube el archivo" in mensaje.lower()


def test_descargar_avisa_si_no_aparece_el_archivo(monkeypatch, tmp_path):
    monkeypatch.setattr(descarga, "_EJECUTAR", lambda comando: _respuesta())
    with pytest.raises(descarga.ErrorDescarga):
        descarga.descargar_audio("https://youtu.be/abc", tmp_path, id_video="abc")
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_descarga.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.descarga'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/descarga.py`:

```python
"""Descarga del audio de un video con yt-dlp, con caché por id de video.

Se descarga la pista completa en su formato nativo y el recorte se hace
después con ffmpeg, que es preciso al milisegundo y acepta cualquier
formato. La canción se guarda como <cache_dir>/<id>.<ext> y se reutiliza:
diez fragmentos de la misma canción son una sola descarga.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}
SUFIJOS_A_MEDIAS = {".part", ".ytdl"}
NOMBRE_SIN_ID = "descarga"


class ErrorDescarga(Exception):
    """No se pudo obtener el audio del enlace."""


def _EJECUTAR(comando):  # noqa: N802
    return subprocess.run(
        comando, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
    )


def es_url(texto: str) -> bool:
    return str(texto).strip().lower().startswith(("http://", "https://"))


def obtener_info(url: str) -> tuple[str, str]:
    """(id_del_video, titulo) en una sola llamada. ('', '') si no se puede."""
    try:
        salida = _EJECUTAR([
            sys.executable, "-m", "yt_dlp", "--no-playlist", "--skip-download",
            "--print", "%(id)s", "--print", "%(title)s", url,
        ])
    except Exception:  # noqa: BLE001
        return "", ""
    lineas = [linea.strip() for linea in (salida.stdout or "").splitlines() if linea.strip()]
    if len(lineas) < 2:
        return "", ""
    return lineas[0], lineas[1]


def _en_cache(cache_dir: Path, nombre: str) -> Path | None:
    candidatos = [
        ruta for ruta in sorted(cache_dir.glob(f"{nombre}.*"))
        if ruta.suffix not in SUFIJOS_A_MEDIAS and ruta.is_file()
    ]
    return candidatos[0] if candidatos else None


def descargar_audio(url: str, cache_dir, id_video: str = "") -> Path:
    """Devuelve el audio completo del video, descargándolo solo si no está en caché."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not id_video:
        id_video, _ = obtener_info(url)
    nombre = id_video or NOMBRE_SIN_ID

    if id_video:
        existente = _en_cache(cache_dir, nombre)
        if existente is not None:
            return existente

    plantilla = str(cache_dir / f"{nombre}.%(ext)s")
    comando = [
        sys.executable, "-m", "yt_dlp", "--no-playlist",
        "-f", "bestaudio/best",
        "-o", plantilla, url,
    ]
    try:
        _EJECUTAR(comando)
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        motivo = detalle[-1] if detalle else "yt-dlp falló sin mensaje"
        raise ErrorDescarga(
            f"No se pudo descargar el audio del enlace ({motivo}). "
            f"Sube el archivo de audio directamente y vuelve a intentarlo."
        ) from error
    except FileNotFoundError as error:
        raise ErrorDescarga("yt-dlp no está instalado") from error

    descargado = _en_cache(cache_dir, nombre)
    if descargado is None:
        raise ErrorDescarga(
            "yt-dlp terminó pero no dejó ningún archivo. "
            "Sube el archivo de audio directamente y vuelve a intentarlo."
        )
    return descargado
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_descarga.py -q`
Esperado: 9 tests pasan

- [ ] **Paso 5: Prueba manual con un enlace real**

Ejecutar en la consola de Python:

```python
from pathlib import Path
from motor.descarga import descargar_audio, obtener_info
url = "https://www.youtube.com/watch?v=..."   # una canción de la banda
print(obtener_info(url))
print(descargar_audio(url, Path("media/origen")))
print(descargar_audio(url, Path("media/origen")))   # la segunda vez vuelve al instante
```

Esperado: imprime `(id, título)` y dos veces la misma ruta `media/origen/<id>.<ext>`; la segunda llamada no toca la red. Esto no queda como test automático porque toca la red.

- [ ] **Paso 6: Commit**

```bash
git add motor/descarga.py tests/test_descarga.py
git commit -m "feat: descarga de audio desde YouTube con yt-dlp"
```

---

### Tarea 13: Separación de la pista melódica con Demucs

**Archivos:**
- Crear: `motor/separacion.py`
- Test: `tests/test_separacion.py`

**Interfaces:**
- Consume: nada del proyecto
- Produce:
  - `ErrorSeparacion(Exception)`
  - `separar_melodia(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None) -> Path`
  - `_EJECUTAR` a nivel de módulo, sustituible en pruebas

Demucs se invoca como subproceso y no importando su API, porque así un fallo suyo no puede tumbar el proceso de Django y el mensaje de error llega limpio. La pista que interesa es `other.wav`: los instrumentos de viento no son voz, ni bajo, ni batería, así que Demucs los deja ahí.

`segmento` se pasa a Demucs como `--segment` y limita cuánta memoria de video usa; con 4 GB conviene 6 (viene de `Config.segmento_demucs`). Si aun así falla por memoria, el pipeline de la tarea 14 reintenta en CPU.

Limitación conocida: con instrumentos de viento con mucho aire, Demucs a veces manda parte de la señal a `vocals.wav`. Se decide con la primera canción real (ver tarea 14, paso de prueba manual), no antes.

- [ ] **Paso 1: Escribir el test que falla**

Crear `tests/test_separacion.py`:

```python
import subprocess
import types

import pytest

from motor import separacion


def test_devuelve_la_pista_other(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    salida = tmp_path / "separado"

    def simular(comando):
        destino = salida / "htdemucs" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"RIFF fingido")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    ruta = separacion.separar_melodia(entrada, salida, dispositivo="cpu")
    assert ruta.name == "other.wav"
    assert ruta.exists()


def test_pasa_el_dispositivo_y_el_modelo_al_comando(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        destino = tmp_path / "separado" / "htdemucs" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"x")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    separacion.separar_melodia(entrada, tmp_path / "separado", dispositivo="cuda")
    assert "cuda" in capturado["comando"]
    assert "htdemucs" in capturado["comando"]
    assert "--segment" not in capturado["comando"]


def test_pasa_el_segmento_cuando_se_indica(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    capturado = {}

    def simular(comando):
        capturado["comando"] = comando
        destino = tmp_path / "separado" / "htdemucs" / "recorte"
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "other.wav").write_bytes(b"x")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(separacion, "_EJECUTAR", simular)
    separacion.separar_melodia(entrada, tmp_path / "separado", dispositivo="cuda", segmento=6)
    posicion = capturado["comando"].index("--segment")
    assert capturado["comando"][posicion + 1] == "6"


def test_avisa_si_demucs_falla(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")

    def falla(comando):
        raise subprocess.CalledProcessError(1, comando, stderr="CUDA out of memory")

    monkeypatch.setattr(separacion, "_EJECUTAR", falla)
    with pytest.raises(separacion.ErrorSeparacion) as error:
        separacion.separar_melodia(entrada, tmp_path / "separado")
    assert "CUDA out of memory" in str(error.value)


def test_avisa_si_no_aparece_la_pista(monkeypatch, tmp_path):
    entrada = tmp_path / "recorte.wav"
    entrada.write_bytes(b"RIFF fingido")
    monkeypatch.setattr(
        separacion, "_EJECUTAR",
        lambda comando: types.SimpleNamespace(stdout="", stderr="", returncode=0),
    )
    with pytest.raises(separacion.ErrorSeparacion):
        separacion.separar_melodia(entrada, tmp_path / "separado")
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_separacion.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'motor.separacion'`

- [ ] **Paso 3: Escribir la implementación**

Crear `motor/separacion.py`:

```python
"""Aislamiento de la pista melódica con Demucs.

Un instrumento de viento no es voz, ni bajo, ni batería, así que Demucs lo
deja en la pista 'other' junto con guitarras y charango. Esa es la que se
entrega al detector de afinación.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ENTORNO_UTF8 = {**os.environ, "PYTHONUTF8": "1"}
PISTA_MELODICA = "other.wav"


class ErrorSeparacion(Exception):
    """Demucs no pudo separar el audio."""

    @property
    def sin_memoria(self) -> bool:
        return "out of memory" in str(self).lower()


def _EJECUTAR(comando):  # noqa: N802
    return subprocess.run(
        comando, capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace", env=ENTORNO_UTF8,
    )


def separar_melodia(ruta_wav, directorio_salida, dispositivo: str = "cpu",
                    modelo: str = "htdemucs", segmento=None) -> Path:
    ruta_wav = Path(ruta_wav)
    directorio_salida = Path(directorio_salida)
    directorio_salida.mkdir(parents=True, exist_ok=True)

    comando = [
        sys.executable, "-m", "demucs",
        "-n", modelo,
        "-d", dispositivo,
        "--out", str(directorio_salida),
    ]
    if segmento is not None:
        comando += ["--segment", f"{segmento:g}"]
    comando.append(str(ruta_wav))
    try:
        _EJECUTAR(comando)
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip().splitlines()
        motivo = detalle[-1] if detalle else "demucs falló sin mensaje"
        raise ErrorSeparacion(f"La separación falló: {motivo}") from error
    except FileNotFoundError as error:
        raise ErrorSeparacion("demucs no está instalado") from error

    destino = directorio_salida / modelo / ruta_wav.stem / PISTA_MELODICA
    if not destino.exists():
        raise ErrorSeparacion(
            f"Demucs terminó pero no se encontró {destino}. "
            f"Prueba marcando la casilla de audio limpio para saltar la separación."
        )
    return destino
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests/test_separacion.py -q`
Esperado: 5 tests pasan

- [ ] **Paso 5: Prueba manual con audio real**

Con una canción real recortada a treinta segundos en `media/prueba/recorte.wav`:

```python
from motor.separacion import separar_melodia
print(separar_melodia("media/prueba/recorte.wav", "media/prueba/separado", dispositivo="cuda"))
```

Esperado: la ruta de `other.wav`. Escucharlo: la melodía debe oírse sin batería ni bajo. La primera ejecución descarga los pesos de Demucs y tarda varios minutos.

- [ ] **Paso 6: Commit**

```bash
git add motor/separacion.py tests/test_separacion.py
git commit -m "feat: separación de la pista melódica con Demucs"
```

---

### Tarea 14: Pipeline completo de extremo a extremo

Une descarga, recorte, separación y análisis en una sola función. Es la única que llama la capa web.

**Archivos:**
- Modificar: `motor/pipeline.py`
- Modificar: `tests/test_pipeline.py` (añadir al final)

**Interfaces:**
- Consume: `motor.descarga.descargar_audio`, `motor.descarga.obtener_info`, `motor.descarga.es_url`, `motor.separacion.separar_melodia`, `motor.audio.recortar`
- Produce:
  - `preparar(origen, inicio_s, fin_s, directorio_trabajo, titulo="", progreso=None, cache_dir=None) -> tuple[Path, Fragmento]`
  - `analizar_preparado(recorte, fragmento, config=None, separar=True, progreso=None) -> Resultado`
  - `analizar_fuente(origen, inicio_s, fin_s, directorio_trabajo, config=None, separar=True, titulo="", progreso=None, cache_dir=None) -> Resultado`

`origen` es una URL o la ruta de un archivo ya subido. `preparar` decide sola cuál es. `cache_dir` es donde viven las descargas reutilizables; si no se indica, es `Config.media_dir / "origen"`.

**Por qué son tres funciones y no una.** La aplicación web deja escuchar el recorte antes de analizar, así que necesita parar entre la preparación y el análisis. `analizar_fuente` es simplemente las dos encadenadas, y existe para poder usar el motor desde consola y desde los tests sin montar Django.

**Qué pasa si Demucs se queda sin memoria de video.** El diseño (sección 10) manda caer a CPU, no renunciar a separar: con 4 GB de VRAM el `out of memory` es un caso esperable. `analizar_preparado` reintenta en CPU con aviso, y solo si también falla ahí analiza la mezcla completa, avisando de que el resultado puede mezclar instrumentos.

- [ ] **Paso 1: Escribir el test que falla**

Añadir al final de `tests/test_pipeline.py`:

```python
import soundfile as sf

from motor import descarga as modulo_descarga
from motor import separacion as modulo_separacion


@pytest.fixture
def cancion_larga(tmp_path):
    ruta = tmp_path / "cancion.wav"
    sf.write(ruta, secuencia([(440.0, 5.0)], sr=44100), 44100)
    return ruta


def test_analizar_fuente_desde_archivo_sin_separar(cancion_larga, detector_falso, tmp_path):
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=False, titulo="Ensayo",
    )
    assert resultado.fragmento.fuente == "archivo"
    assert resultado.fragmento.inicio_s == 1.0
    assert resultado.analisis.separacion == "ninguna"
    assert [nota.nombre for nota in resultado.notas] == ["A4", "B4"]
    assert Path(resultado.archivos["midi"]).exists()


def _descarga_falsa(cancion_larga):
    """Imita a descargar_audio: deja la canción en la caché y devuelve la ruta."""
    def descargar(url, cache_dir, id_video=""):
        destino = Path(cache_dir) / f"{id_video or 'abc'}.m4a"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(cancion_larga.read_bytes())
        return destino
    return descargar


def _separacion_falsa(ruta_wav, directorio_salida, dispositivo="cpu",
                      modelo="htdemucs", segmento=None):
    destino = Path(directorio_salida) / "other.wav"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(Path(ruta_wav).read_bytes())
    return destino


def test_analizar_fuente_desde_url_descarga_y_separa(monkeypatch, cancion_larga,
                                                     detector_falso, tmp_path):
    monkeypatch.setattr(modulo_descarga, "descargar_audio", _descarga_falsa(cancion_larga))
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    monkeypatch.setattr(modulo_separacion, "separar_melodia", _separacion_falsa)

    resultado = pipeline.analizar_fuente(
        "https://youtu.be/abc", inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
        cache_dir=tmp_path / "origen",
    )
    assert resultado.fragmento.fuente == "youtube"
    assert resultado.fragmento.titulo == "Huayno"
    assert resultado.analisis.separacion == "htdemucs"
    assert Path(resultado.archivos["melodia_wav"]).exists()
    assert (tmp_path / "origen" / "abc.m4a").exists()      # la descarga queda en la caché


def test_dos_fragmentos_de_la_misma_url_comparten_la_descarga(monkeypatch, cancion_larga,
                                                              detector_falso, tmp_path):
    descargas = []

    def descargar(url, cache_dir, id_video=""):
        descargas.append(id_video)
        return _descarga_falsa(cancion_larga)(url, cache_dir, id_video)

    monkeypatch.setattr(modulo_descarga, "descargar_audio", descargar)
    monkeypatch.setattr(modulo_descarga, "obtener_info", lambda url: ("abc", "Huayno"))
    for indice, (inicio, fin) in enumerate([(0.5, 2.0), (2.0, 3.5)]):
        pipeline.preparar(
            "https://youtu.be/abc", inicio, fin, tmp_path / f"trabajo{indice}",
            cache_dir=tmp_path / "origen",
        )
    # preparar pasa el id averiguado, así que descargar_audio puede encontrar
    # la caché sin volver a preguntar; y usa siempre la misma carpeta.
    assert descargas == ["abc", "abc"]


def test_sin_memoria_de_video_la_separacion_reintenta_en_cpu(monkeypatch, cancion_larga,
                                                             detector_falso, tmp_path):
    dispositivos = []

    def separar(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None):
        dispositivos.append(dispositivo)
        if dispositivo == "cuda":
            raise modulo_separacion.ErrorSeparacion("La separación falló: CUDA out of memory")
        return _separacion_falsa(ruta_wav, directorio_salida, dispositivo, modelo)

    monkeypatch.setattr(modulo_separacion, "separar_melodia", separar)
    monkeypatch.setattr(pipeline, "resolver_dispositivo", lambda preferencia: "cuda")
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
    )
    assert dispositivos == ["cuda", "cpu"]
    assert resultado.analisis.separacion == "htdemucs"
    assert any("cpu" in aviso.lower() for aviso in resultado.avisos)


def test_si_la_separacion_falla_sigue_con_la_mezcla_y_avisa(monkeypatch, cancion_larga,
                                                            detector_falso, tmp_path):
    def revienta(ruta_wav, directorio_salida, dispositivo="cpu", modelo="htdemucs", segmento=None):
        raise modulo_separacion.ErrorSeparacion("modelo corrupto")

    monkeypatch.setattr(modulo_separacion, "separar_melodia", revienta)
    resultado = pipeline.analizar_fuente(
        cancion_larga, inicio_s=1.0, fin_s=2.8,
        directorio_trabajo=tmp_path / "trabajo", separar=True,
    )
    assert resultado.analisis.separacion == "ninguna"
    assert any("separación" in aviso.lower() for aviso in resultado.avisos)
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest tests/test_pipeline.py -q`
Esperado: FALLA con `AttributeError: module 'motor.pipeline' has no attribute 'analizar_fuente'`

- [ ] **Paso 3: Escribir la implementación**

Añadir a `motor/pipeline.py`:

```python
from motor import descarga as modulo_descarga
from motor import separacion as modulo_separacion
from motor.audio import recortar


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

    Es la primera mitad del trabajo. Se separa de la segunda porque la
    aplicación deja escuchar el recorte antes de analizarlo. Las descargas
    van a cache_dir, compartida por todos los fragmentos, y se reutilizan.
    """
    trabajo = Path(directorio_trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir) if cache_dir else Config.desde_entorno().media_dir / "origen"

    if modulo_descarga.es_url(str(origen)):
        fuente = "youtube"
        referencia = str(origen)
        _avisar(progreso, "Consultando el video")
        id_video, titulo_remoto = modulo_descarga.obtener_info(referencia)
        titulo = titulo or titulo_remoto or "Sin título"
        _avisar(progreso, "Descargando el audio")
        completo = modulo_descarga.descargar_audio(referencia, cache_dir, id_video=id_video)
    else:
        fuente = "archivo"
        completo = Path(origen)
        referencia = completo.name
        titulo = titulo or completo.stem

    _avisar(progreso, "Recortando el fragmento")
    recorte = recortar(completo, trabajo / "mezcla.wav", inicio_s, fin_s)
    fragmento = Fragmento(
        titulo=titulo, fuente=fuente, referencia=referencia,
        inicio_s=float(inicio_s), fin_s=float(fin_s),
    )
    return recorte, fragmento


def _separar_con_respaldo(recorte, trabajo, config, progreso):
    """Devuelve (ruta_melodia_o_None, avisos).

    Primero en el dispositivo configurado. Si se queda sin memoria de video,
    reintenta en CPU (lo manda la sección 10 del diseño). Solo si también
    falla ahí se renuncia a separar.
    """
    avisos = []
    dispositivo = resolver_dispositivo(config.dispositivo)
    intentos = [dispositivo] + (["cpu"] if dispositivo == "cuda" else [])
    ultimo_error = None
    for indice, actual in enumerate(intentos):
        _avisar(progreso, "Separando la pista melódica"
                + (" (en CPU, tarda más)" if indice > 0 else ""))
        try:
            melodia = modulo_separacion.separar_melodia(
                recorte,
                trabajo / "separado",
                dispositivo=actual,
                modelo=config.modelo_separacion,
                segmento=config.segmento_demucs if actual == "cuda" else None,
            )
        except modulo_separacion.ErrorSeparacion as error:
            ultimo_error = error
            if actual == "cuda" and error.sin_memoria:
                avisos.append(
                    "La tarjeta de video se quedó sin memoria; la separación "
                    "corrió en CPU y tardó más."
                )
                continue
            break
        else:
            return melodia, avisos
    avisos.append(
        f"La separación falló y se analizó la mezcla completa ({ultimo_error}). "
        f"El resultado puede mezclar notas de otros instrumentos."
    )
    return None, avisos


def analizar_preparado(
    recorte,
    fragmento: Fragmento,
    config: Config | None = None,
    separar: bool = True,
    progreso=None,
) -> Resultado:
    """Segunda mitad: separación, detección, notas y archivos de salida."""
    config = config or Config.desde_entorno()
    recorte = Path(recorte)
    trabajo = recorte.parent

    avisos_previos = []
    melodia = None
    if separar:
        melodia, avisos_previos = _separar_con_respaldo(recorte, trabajo, config, progreso)
        separar = melodia is not None

    resultado = analizar_recorte(
        melodia or recorte,
        fragmento,
        config=config,
        separar=separar,
        progreso=progreso,
        salidas_en=trabajo,
        melodia_wav=melodia,
    )
    archivos = dict(resultado.archivos)
    archivos["mezcla_wav"] = str(recorte)
    return Resultado(
        fragmento=resultado.fragmento,
        analisis=resultado.analisis,
        frases=resultado.frases,
        archivos=archivos,
        avisos=tuple(avisos_previos) + resultado.avisos,
    )


def analizar_fuente(
    origen,
    inicio_s: float,
    fin_s: float,
    directorio_trabajo,
    config: Config | None = None,
    separar: bool = True,
    titulo: str = "",
    progreso=None,
    cache_dir=None,
) -> Resultado:
    """Las dos mitades encadenadas. Para consola y pruebas."""
    recorte, fragmento = preparar(
        origen, inicio_s, fin_s, directorio_trabajo, titulo=titulo, progreso=progreso,
        cache_dir=cache_dir,
    )
    return analizar_preparado(
        recorte, fragmento, config=config, separar=separar, progreso=progreso
    )
```

Además, en `analizar_recorte`, la duración que se usa para la sonificación debe ser la del recorte de mezcla, no la de la pista separada. Cambiar la línea de `notas_wav` por:

```python
    archivos["notas_wav"] = str(
        sonificar(resultado.frases, salidas / "notas.wav",
                  fragmento.fin_s - fragmento.inicio_s)
    )
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest tests -q`
Esperado: toda la suite pasa

- [ ] **Paso 5: Commit**

```bash
git add motor/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline completo con descarga, recorte y separación"
```

---

### Tarea 15: Proyecto Django y modelos

**Archivos:**
- Crear: `web/manage.py`, `web/quenotas/settings.py`, `web/quenotas/urls.py`, `web/quenotas/wsgi.py`, `web/quenotas/__init__.py`
- Crear: `web/transcripciones/models.py`, `web/transcripciones/admin.py`, `web/transcripciones/apps.py`, `web/transcripciones/__init__.py`, `web/transcripciones/migrations/__init__.py`
- Test: `web/transcripciones/tests_modelos.py`

**Interfaces:**
- Consume: `motor.contrato.Resultado` (solo para guardarlo)
- Produce:
  - `Cancion(titulo, fuente, referencia, creada)`
  - `Fragmento(cancion, origen, inicio_s, fin_s, separar, estado, paso, mensaje, avisos, analisis, archivos, creado)` con las constantes `PENDIENTE`, `PREPARANDO`, `PREPARADO`, `PROCESANDO`, `LISTO`, `ERROR`, el método `guardar_resultado(resultado)` y `por_frases()`. `origen` es la URL o la ruta del archivo subido: lo que hace falta para volver a preparar el fragmento si el trabajo se interrumpe.
  - `Nota(fragmento, frase, orden, nombre, midi, inicio_s, duracion_s, confianza, cents)` con la propiedad `etiqueta_confianza`

- [ ] **Paso 1: Crear el proyecto**

```bash
cd "D:/Documentos/claude proyectos/Quenotas"
py -m django startproject quenotas web
cd web
py manage.py startapp transcripciones
del transcripciones\tests.py
```

(Django 6.1 crea la carpeta `web/` si no existe; verificado el 2026-09-05. El `tests.py` que genera `startapp` se borra porque los tests van en `tests_modelos.py`, `tests_trabajos.py` y `tests_vistas.py`.)

Después, **borrar la primera línea de `web/manage.py`** (el shebang `#!/usr/bin/env python`). Motivo, visto en esta máquina: el launcher `py` respeta el shebang y busca `python` en el PATH, que aquí es un Python 3.13 sin Django, así que `py web/manage.py ...` fallaba con "Couldn't import Django". Sin shebang, `py` usa su intérprete por defecto (3.14), que es el del proyecto. El proyecto es solo Windows y lo lanza un `.bat`, así que el shebang no sirve para nada.

- [ ] **Paso 2: Ajustar `web/quenotas/settings.py`**

Sustituir o añadir estas partes:

```python
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAIZ_PROYECTO = BASE_DIR.parent
sys.path.insert(0, str(RAIZ_PROYECTO))   # para poder importar motor/

SECRET_KEY = "quenotas-local-no-secreta"
DEBUG = True
ALLOWED_HOSTS = ["*"]      # uso local en la red de casa

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "transcripciones",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": RAIZ_PROYECTO / "db.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_ROOT = RAIZ_PROYECTO / "media"
MEDIA_URL = "/media/"

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Guayaquil"
USE_TZ = True
```

Ojo con `LANGUAGE_CODE = "es"`: Django localiza los números en las plantillas, así que `{{ 0.4 }}` se imprime como `0,4` (verificado). Ningún flotante que deba leer JavaScript puede ir por plantilla sin `|stringformat:"g"`; las tareas 18 y 19 usan enteros (`orden`) para emparejar y JSON para los datos.

- [ ] **Paso 2b: Conectar `pytest-django`**

Sustituir `pytest.ini` de la raíz por:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = quenotas.settings
pythonpath = . web
testpaths = tests web
python_files = test_*.py tests_*.py
markers =
    lento: carga modelos pesados o toca la red
```

Desde aquí, `py -m pytest -q` corre motor y web juntos, `py -m pytest web -q` solo la web. Las clases `TestCase` de Django funcionan igual bajo pytest, y además se pueden escribir tests como funciones sueltas con `pytest.raises` (con `manage.py test` esas funciones se ignoraban en silencio).

- [ ] **Paso 3: Escribir el test que falla**

Crear `web/transcripciones/tests_modelos.py`:

```python
from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from transcripciones.models import Cancion, Fragmento, Nota


def _resultado():
    notas = (
        NotaContrato(orden=1, nombre="G4", midi=67, inicio_s=0.4, duracion_s=0.42,
                     confianza=0.93, cents=-12),
        NotaContrato(orden=2, nombre="A4", midi=69, inicio_s=1.5, duracion_s=0.30,
                     confianza=0.55, cents=3),
    )
    return Resultado(
        fragmento=FragmentoContrato(titulo="Huayno", fuente="youtube",
                                    referencia="https://youtu.be/abc",
                                    inicio_s=30.0, fin_s=90.0),
        analisis=ParametrosAnalisis(separacion="htdemucs", modelo_afinacion="crepe:full",
                                    hop_ms=10, fmin_hz=261.63, fmax_hz=1567.98,
                                    dispositivo="cuda"),
        frases=(
            Frase(indice=1, inicio_s=0.4, fin_s=0.82, notas=(notas[0],)),
            Frase(indice=2, inicio_s=1.5, fin_s=1.8, notas=(notas[1],)),
        ),
        archivos={"midi": "media/x.mid"},
        avisos=("un aviso",),
    )


class PruebaModelos(TestCase):
    def setUp(self):
        self.cancion = Cancion.objects.create(
            titulo="Huayno", fuente="youtube", referencia="https://youtu.be/abc"
        )
        self.fragmento = Fragmento.objects.create(
            cancion=self.cancion, inicio_s=30.0, fin_s=90.0, separar=True
        )

    def test_un_fragmento_nace_pendiente(self):
        assert self.fragmento.estado == Fragmento.PENDIENTE

    def test_guardar_resultado_crea_las_notas_con_su_frase(self):
        self.fragmento.guardar_resultado(_resultado())
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.avisos == ["un aviso"]
        assert self.fragmento.archivos["midi"] == "media/x.mid"
        assert list(self.fragmento.notas.values_list("nombre", "frase")) == [
            ("G4", 1), ("A4", 2)
        ]

    def test_guardar_resultado_dos_veces_no_duplica_notas(self):
        self.fragmento.guardar_resultado(_resultado())
        self.fragmento.guardar_resultado(_resultado())
        assert self.fragmento.notas.count() == 2

    def test_etiqueta_de_confianza(self):
        self.fragmento.guardar_resultado(_resultado())
        etiquetas = [nota.etiqueta_confianza for nota in self.fragmento.notas.all()]
        assert etiquetas == ["alta", "baja"]

    def test_agrupar_por_frases_devuelve_listas(self):
        self.fragmento.guardar_resultado(_resultado())
        frases = self.fragmento.por_frases()
        assert [indice for indice, _ in frases] == [1, 2]
        assert [nota.nombre for nota in frases[0][1]] == ["G4"]
```

- [ ] **Paso 4: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest web -q`
Esperado: FALLA con `ImportError: cannot import name 'Cancion'`

- [ ] **Paso 5: Escribir los modelos**

Crear `web/transcripciones/models.py`:

```python
from django.db import models, transaction

from motor.contrato import etiqueta_confianza


class Cancion(models.Model):
    titulo = models.CharField(max_length=300)
    fuente = models.CharField(
        max_length=20,
        choices=[("youtube", "YouTube"), ("archivo", "Archivo")],
        default="archivo",
    )
    referencia = models.TextField(blank=True)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]

    def __str__(self):
        return self.titulo or "Sin título"


class Fragmento(models.Model):
    PENDIENTE = "pendiente"
    PREPARANDO = "preparando"
    PREPARADO = "preparado"
    PROCESANDO = "procesando"
    LISTO = "listo"
    ERROR = "error"
    ESTADOS = [
        (PENDIENTE, "Pendiente"),
        (PREPARANDO, "Obteniendo el recorte"),
        (PREPARADO, "Listo para escuchar"),
        (PROCESANDO, "Analizando"),
        (LISTO, "Listo"),
        (ERROR, "Error"),
    ]

    cancion = models.ForeignKey(Cancion, related_name="fragmentos", on_delete=models.CASCADE)
    origen = models.TextField(blank=True)   # URL o ruta del archivo subido, para reintentar
    inicio_s = models.FloatField()
    fin_s = models.FloatField()
    separar = models.BooleanField(default=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=PENDIENTE)
    paso = models.CharField(max_length=120, blank=True)
    mensaje = models.TextField(blank=True)
    avisos = models.JSONField(default=list, blank=True)
    analisis = models.JSONField(default=dict, blank=True)
    archivos = models.JSONField(default=dict, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.cancion} [{self.inicio_s:.0f}-{self.fin_s:.0f}]"

    @property
    def duracion_s(self):
        return self.fin_s - self.inicio_s

    def guardar_resultado(self, resultado):
        """Vuelca un Resultado del motor en la base de datos.

        Todo o nada: si algo falla entre borrar las notas viejas y escribir
        las nuevas, la base queda como estaba y el estado no pasa a LISTO.
        """
        with transaction.atomic():
            self.notas.all().delete()
            Nota.objects.bulk_create([
                Nota(
                    fragmento=self,
                    frase=frase.indice,
                    orden=nota.orden,
                    nombre=nota.nombre,
                    midi=nota.midi,
                    inicio_s=nota.inicio_s,
                    duracion_s=nota.duracion_s,
                    confianza=nota.confianza,
                    cents=nota.cents,
                )
                for frase in resultado.frases
                for nota in frase.notas
            ])
            self.analisis = resultado.a_dict()["analisis"]
            self.archivos = dict(resultado.archivos)
            self.avisos = list(resultado.avisos)
            self.estado = self.LISTO
            self.paso = ""
            self.mensaje = ""
            self.save()

    def por_frases(self):
        """[(indice_de_frase, [notas...]), ...] en orden."""
        agrupadas = {}
        for nota in self.notas.all():
            agrupadas.setdefault(nota.frase, []).append(nota)
        return sorted(agrupadas.items())


class Nota(models.Model):
    fragmento = models.ForeignKey(Fragmento, related_name="notas", on_delete=models.CASCADE)
    frase = models.PositiveIntegerField()
    orden = models.PositiveIntegerField()
    nombre = models.CharField(max_length=5)
    midi = models.PositiveSmallIntegerField()
    inicio_s = models.FloatField()
    duracion_s = models.FloatField()
    confianza = models.FloatField()
    cents = models.IntegerField()

    class Meta:
        ordering = ["orden"]

    def __str__(self):
        return f"{self.nombre} @ {self.inicio_s:.2f}s"

    @property
    def etiqueta_confianza(self):
        return etiqueta_confianza(self.confianza)

    @property
    def fin_s(self):
        return self.inicio_s + self.duracion_s
```

- [ ] **Paso 6: Registrar en el admin**

Crear `web/transcripciones/admin.py`:

```python
from django.contrib import admin

from .models import Cancion, Fragmento, Nota

admin.site.register(Cancion)
admin.site.register(Fragmento)
admin.site.register(Nota)
```

- [ ] **Paso 7: Migrar y ejecutar los tests**

```bash
py web/manage.py makemigrations transcripciones
py web/manage.py migrate
py -m pytest web -q
```

Esperado: 5 tests pasan. Comprobar también que `py -m pytest -q` desde la raíz sigue corriendo toda la suite del motor más estos cinco.

- [ ] **Paso 8: Commit**

```bash
git add web
git commit -m "feat: proyecto Django con los modelos de canción, fragmento y nota"
```

---

### Tarea 16: Trabajos en segundo plano

Analizar tarda cerca de un minuto, más de lo que aguanta una petición HTTP. El trabajo corre en un hilo y la página consulta el estado.

**Archivos:**
- Crear: `web/transcripciones/trabajos.py`
- Crear: `web/transcripciones/management/__init__.py`, `web/transcripciones/management/commands/__init__.py`, `web/transcripciones/management/commands/recuperar_trabajos.py`
- Test: `web/transcripciones/tests_trabajos.py`

**Interfaces:**
- Consume: `transcripciones.models.Fragmento`, `motor.pipeline.preparar`, `motor.pipeline.analizar_preparado` (importados dentro de las funciones, para que la web no dependa de que la tarea 14 esté hecha), `motor.contrato.Fragmento` (el del contrato)
- Produce:
  - `_PREPARAR` y `_ANALIZAR` a nivel de módulo (por defecto `None`, que significa "usar el pipeline real"), sustituibles en pruebas
  - `UN_ANALISIS_A_LA_VEZ = threading.Semaphore(1)`
  - `directorio_de(fragmento) -> Path` y `cache_descargas() -> Path`
  - `ejecutar_preparacion(fragmento_id, origen)` que descarga y recorta, y deja el fragmento en `PREPARADO` o en `ERROR`
  - `ejecutar_analisis(fragmento_id)` que separa, detecta y exporta, y deja el fragmento en `LISTO` o en `ERROR`
  - `lanzar_preparacion(fragmento_id, origen)` y `lanzar_analisis(fragmento_id)` que arrancan lo anterior en hilos demonio
  - `recuperar_huerfanos() -> int` que pasa a `ERROR` todo fragmento que quedó en un estado intermedio, y el comando `py web/manage.py recuperar_trabajos` que lo invoca

Son dos trabajos y no uno porque entre ambos el usuario escucha el recorte para confirmar que el rango es el que quería.

**Un análisis a la vez.** Dos clics en "Analizar" en dos pestañas lanzarían dos Demucs sobre 4 GB de VRAM y el segundo moriría por memoria. `ejecutar_analisis` toma el semáforo; mientras espera, el fragmento muestra `paso = "En cola"`.

**Trabajos huérfanos.** Si se cierra la consola o Python muere a mitad de un análisis, el fragmento queda en `preparando` o `procesando` para siempre y la página sondea sin fin. `recuperar_huerfanos` se ejecuta desde `iniciar.bat` antes de levantar el servidor y deja esos fragmentos en `error` con el mensaje "El trabajo se interrumpió"; la tarea 17 añade el botón "Reintentar". No se hace en `AppConfig.ready()` porque Django desaconseja tocar la base de datos ahí (en un clon limpio todavía no existe).

- [ ] **Paso 1: Escribir el test que falla**

Crear `web/transcripciones/tests_trabajos.py`:

```python
from pathlib import Path

from django.test import TestCase

from motor.contrato import Fragmento as FragmentoContrato
from motor.contrato import Frase, Nota as NotaContrato, ParametrosAnalisis, Resultado
from transcripciones import trabajos
from transcripciones.models import Cancion, Fragmento


def _resultado_falso(**kwargs):
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


class PruebaTrabajos(TestCase):
    def setUp(self):
        cancion = Cancion.objects.create(titulo="X", fuente="archivo", referencia="x.wav")
        self.fragmento = Fragmento.objects.create(
            cancion=cancion, origen="x.wav", inicio_s=30.0, fin_s=40.0, separar=False
        )

    def _preparado(self):
        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x/mezcla.wav"}
        self.fragmento.save()

    def test_la_preparacion_deja_el_fragmento_listo_para_escuchar(self):
        preparar = lambda **kwargs: (Path("media/x/mezcla.wav"), _resultado_falso().fragmento)
        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "x.wav")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PREPARADO
        assert self.fragmento.archivos["mezcla_wav"].endswith("mezcla.wav")

    def test_la_preparacion_pasa_la_cache_compartida_de_descargas(self):
        recibido = {}

        def preparar(**kwargs):
            recibido.update(kwargs)
            return Path("media/x/mezcla.wav"), _resultado_falso().fragmento

        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        assert recibido["cache_dir"] == trabajos.cache_descargas()
        assert str(self.fragmento.pk) not in str(recibido["cache_dir"])

    def test_la_preparacion_guarda_el_titulo_averiguado(self):
        preparar = lambda **kwargs: (Path("media/x/mezcla.wav"), _resultado_falso().fragmento)
        with patch.object(trabajos, "_PREPARAR", preparar):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        self.fragmento.refresh_from_db()
        assert self.fragmento.cancion.titulo == "X"

    def test_un_fallo_de_preparacion_deja_error_con_mensaje(self):
        def revienta(**kwargs):
            raise RuntimeError("no se pudo descargar el audio")

        with patch.object(trabajos, "_PREPARAR", revienta):
            trabajos.ejecutar_preparacion(self.fragmento.pk, "https://youtu.be/abc")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "no se pudo descargar" in self.fragmento.mensaje

    def test_el_analisis_deja_el_fragmento_listo(self):
        self._preparado()
        with patch.object(trabajos, "_ANALIZAR", lambda **kwargs: _resultado_falso()):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.LISTO
        assert self.fragmento.notas.count() == 1

    def test_el_progreso_se_guarda_en_el_paso(self):
        self._preparado()
        pasos_vistos = []

        def analizar(**kwargs):
            kwargs["progreso"]("Separando la pista melódica")
            pasos_vistos.append(Fragmento.objects.get(pk=self.fragmento.pk).paso)
            return _resultado_falso()

        with patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert pasos_vistos == ["Separando la pista melódica"]

    def test_el_analisis_corre_con_el_semaforo_tomado(self):
        self._preparado()
        libres_durante = []

        def analizar(**kwargs):
            libres_durante.append(trabajos.UN_ANALISIS_A_LA_VEZ._value)
            return _resultado_falso()

        with patch.object(trabajos, "_ANALIZAR", analizar):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert libres_durante == [0]                       # tomado mientras analiza
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1   # y devuelto al terminar

    def test_el_semaforo_se_devuelve_aunque_el_analisis_falle(self):
        self._preparado()

        def revienta(**kwargs):
            raise RuntimeError("CUDA out of memory")

        with patch.object(trabajos, "_ANALIZAR", revienta):
            trabajos.ejecutar_analisis(self.fragmento.pk)
        assert trabajos.UN_ANALISIS_A_LA_VEZ._value == 1
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_recuperar_huerfanos_marca_error_los_trabajos_a_medias(self):
        self.fragmento.estado = Fragmento.PROCESANDO
        self.fragmento.paso = "Separando"
        self.fragmento.save()
        otro = Fragmento.objects.create(
            cancion=self.fragmento.cancion, origen="x.wav", inicio_s=0, fin_s=5,
            estado=Fragmento.LISTO,
        )
        assert trabajos.recuperar_huerfanos() == 1
        self.fragmento.refresh_from_db()
        otro.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR
        assert "interrumpi" in self.fragmento.mensaje
        assert otro.estado == Fragmento.LISTO

    def test_el_comando_recuperar_trabajos_existe(self):
        self.fragmento.estado = Fragmento.PREPARANDO
        self.fragmento.save()
        call_command("recuperar_trabajos")
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.ERROR

    def test_el_directorio_de_trabajo_es_propio_de_cada_fragmento(self):
        ruta = trabajos.directorio_de(self.fragmento)
        assert str(self.fragmento.pk) in str(ruta)
```

Añadir al principio del archivo: `from unittest.mock import patch` y `from django.core.management import call_command`.

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest web/transcripciones/tests_trabajos.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'transcripciones.trabajos'`

- [ ] **Paso 3: Escribir la implementación**

Crear `web/transcripciones/trabajos.py`:

```python
"""Ejecución del análisis fuera del ciclo de la petición HTTP.

Para un solo usuario en local un hilo basta. La pieza está aislada a
propósito: si algún día hubiera varios usuarios, se sustituye por una
cola real sin tocar ni las vistas ni el motor.
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from django.conf import settings
from django.db import connection

from motor.contrato import Fragmento as FragmentoContrato

# Puntos de sustitución para las pruebas. None significa "usar el pipeline
# real", que se importa dentro de las funciones para que esta capa cargue
# aunque motor/pipeline.py todavía no tenga preparar/analizar_preparado.
_PREPARAR = None
_ANALIZAR = None

# Demucs y CREPE no caben dos veces en 4 GB de VRAM. El segundo espera.
UN_ANALISIS_A_LA_VEZ = threading.Semaphore(1)

MENSAJE_INTERRUMPIDO = "El trabajo se interrumpió (se cerró el programa a mitad). Reintenta."


def _preparar_real():
    if _PREPARAR is not None:
        return _PREPARAR
    from motor.pipeline import preparar
    return preparar


def _analizar_real():
    if _ANALIZAR is not None:
        return _ANALIZAR
    from motor.pipeline import analizar_preparado
    return analizar_preparado


def directorio_de(fragmento) -> Path:
    return Path(settings.MEDIA_ROOT) / "fragmentos" / str(fragmento.pk)


def cache_descargas() -> Path:
    """Compartida por todos los fragmentos: una canción se baja una sola vez."""
    return Path(settings.MEDIA_ROOT) / "origen"


def _progreso_de(fragmento_id):
    from .models import Fragmento

    def progreso(mensaje):
        Fragmento.objects.filter(pk=fragmento_id).update(paso=mensaje)

    return progreso


def _marcar_error(fragmento_id, error):
    from .models import Fragmento

    traceback.print_exc()
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.ERROR, paso="", mensaje=str(error)
    )


def ejecutar_preparacion(fragmento_id: int, origen: str) -> None:
    """Descarga y recorta. Deja el fragmento listo para escuchar."""
    from .models import Fragmento

    fragmento = Fragmento.objects.get(pk=fragmento_id)
    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PREPARANDO, paso="Preparando", mensaje=""
    )
    try:
        recorte, contrato = _preparar_real()(
            origen=origen,
            inicio_s=fragmento.inicio_s,
            fin_s=fragmento.fin_s,
            directorio_trabajo=directorio_de(fragmento),
            titulo=fragmento.cancion.titulo,
            progreso=_progreso_de(fragmento_id),
            cache_dir=cache_descargas(),
        )
        cancion = fragmento.cancion
        cancion.titulo = contrato.titulo
        cancion.fuente = contrato.fuente
        cancion.referencia = contrato.referencia
        cancion.save()

        fragmento.refresh_from_db()
        fragmento.archivos = {"mezcla_wav": str(recorte)}
        fragmento.estado = Fragmento.PREPARADO
        fragmento.paso = ""
        fragmento.save(update_fields=["archivos", "estado", "paso"])
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def ejecutar_analisis(fragmento_id: int) -> None:
    """Separa, detecta las notas y genera los archivos de salida."""
    from .models import Fragmento

    fragmento = Fragmento.objects.get(pk=fragmento_id)
    recorte = fragmento.archivos.get("mezcla_wav")
    if not recorte:
        _marcar_error(fragmento_id, RuntimeError("el fragmento no tiene recorte preparado"))
        connection.close()
        return

    Fragmento.objects.filter(pk=fragmento_id).update(
        estado=Fragmento.PROCESANDO, paso="En cola", mensaje=""
    )
    try:
        with UN_ANALISIS_A_LA_VEZ:
            Fragmento.objects.filter(pk=fragmento_id).update(paso="Analizando")
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
                progreso=_progreso_de(fragmento_id),
            )
        fragmento.refresh_from_db()
        fragmento.guardar_resultado(resultado)
    except Exception as error:  # noqa: BLE001
        _marcar_error(fragmento_id, error)
    finally:
        connection.close()


def lanzar_preparacion(fragmento_id: int, origen: str) -> None:
    threading.Thread(
        target=ejecutar_preparacion, args=(fragmento_id, origen), daemon=True
    ).start()


def lanzar_analisis(fragmento_id: int) -> None:
    threading.Thread(target=ejecutar_analisis, args=(fragmento_id,), daemon=True).start()


def recuperar_huerfanos() -> int:
    """Al arrancar: lo que quedó a medias en la sesión anterior pasa a error."""
    from .models import Fragmento

    return Fragmento.objects.filter(
        estado__in=[Fragmento.PREPARANDO, Fragmento.PROCESANDO]
    ).update(estado=Fragmento.ERROR, paso="", mensaje=MENSAJE_INTERRUMPIDO)
```

Crear `web/transcripciones/management/__init__.py` y `web/transcripciones/management/commands/__init__.py` vacíos, y `web/transcripciones/management/commands/recuperar_trabajos.py`:

```python
from django.core.management.base import BaseCommand

from transcripciones.trabajos import recuperar_huerfanos


class Command(BaseCommand):
    help = "Marca como error los fragmentos que quedaron a medias en una sesión anterior."

    def handle(self, *args, **opciones):
        cantidad = recuperar_huerfanos()
        self.stdout.write(f"Fragmentos recuperados: {cantidad}")
```

- [ ] **Paso 4: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 16 tests pasan (5 de modelos y 11 de trabajos)

- [ ] **Paso 5: Commit**

```bash
git add web/transcripciones/trabajos.py web/transcripciones/tests_trabajos.py web/transcripciones/management
git commit -m "feat: análisis en segundo plano de uno en uno, con estado consultable y recuperación de trabajos a medias"
```

---

### Tarea 17: Formulario de entrada y vista previa del recorte

**Archivos:**
- Crear: `web/transcripciones/formularios.py`, `web/transcripciones/views.py`, `web/transcripciones/urls.py`
- Modificar: `web/quenotas/urls.py`
- Crear: `web/transcripciones/templates/transcripciones/base.html`, `index.html`, `detalle.html`
- Test: `web/transcripciones/tests_vistas.py`

**Interfaces:**
- Consume: `transcripciones.models.Cancion`, `transcripciones.models.Fragmento`, `transcripciones.trabajos.lanzar_preparacion`, `transcripciones.trabajos.lanzar_analisis`
- Produce:
  - `formularios.parsear_tiempo(texto) -> float` que acepta `"90"`, `"1:30"` y `"1:30.5"`
  - `formularios.FormularioFragmento` con los campos `url`, `archivo`, `inicio`, `fin`, `separar`
  - Rutas con nombre: `index`, `detalle`, `estado`, `analizar`, `reintentar`, `datos`, `audio`, `descargar`, `historial`

**La misma canción no se repite.** Si la URL ya tiene una `Cancion`, el nuevo fragmento cuelga de ella (y la descarga ya está en caché por la tarea 12). El historial muestra una canción con sus fragmentos, no seis entradas iguales. Para archivos subidos no se reutiliza: dos archivos distintos pueden llamarse igual.

**Reintentar.** Un fragmento en `error` (por fallo o porque se cerró el programa a mitad) tiene un botón "Reintentar": si ya tiene recorte, relanza el análisis; si no, relanza la preparación con el `origen` guardado.

- [ ] **Paso 1: Escribir el test que falla**

Crear `web/transcripciones/tests_vistas.py`:

```python
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.urls import reverse

from transcripciones.formularios import parsear_tiempo
from transcripciones.models import Cancion, Fragmento


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
        self.cancion = Cancion.objects.create(titulo="Huayno", fuente="youtube",
                                              referencia="https://youtu.be/abc")
        self.fragmento = Fragmento.objects.create(cancion=self.cancion, origen="https://youtu.be/abc",
                                                  inicio_s=30.0, fin_s=90.0, separar=True)

    def test_el_index_responde(self):
        respuesta = self.client.get(reverse("index"))
        assert respuesta.status_code == 200
        assert b"YouTube" in respuesta.content

    def test_enviar_una_url_crea_el_fragmento_y_lanza_la_preparacion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            respuesta = self.client.post(reverse("index"), {
                "url": "https://youtu.be/xyz",
                "inicio": "0:30",
                "fin": "1:30",
                "separar": "on",
            })
        assert respuesta.status_code == 302
        creado = Fragmento.objects.exclude(pk=self.fragmento.pk).get()
        assert creado.inicio_s == 30.0
        assert creado.fin_s == 90.0
        assert creado.separar is True
        lanzar.assert_called_once_with(creado.pk, "https://youtu.be/xyz")

    def test_un_rango_invertido_no_crea_nada(self):
        respuesta = self.client.post(reverse("index"), {
            "url": "https://youtu.be/xyz", "inicio": "1:30", "fin": "0:30",
        })
        assert respuesta.status_code == 200
        assert Fragmento.objects.count() == 1

    def test_un_fragmento_mas_largo_que_el_limite_se_rechaza(self):
        respuesta = self.client.post(reverse("index"), {
            "url": "https://youtu.be/xyz", "inicio": "0:00", "fin": "10:00",
        })
        assert respuesta.status_code == 200
        assert b"181" in respuesta.content or b"180" in respuesta.content

    def test_el_estado_se_consulta_en_json(self):
        respuesta = self.client.get(reverse("estado", args=[self.fragmento.pk]))
        assert respuesta.json() == {
            "estado": "pendiente", "paso": "", "mensaje": "", "avisos": []
        }

    def test_analizar_lanza_el_trabajo_solo_si_esta_preparado(self):
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            lanzar.assert_not_called()

        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            respuesta = self.client.post(reverse("analizar", args=[self.fragmento.pk]))
            lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302

    def test_el_detalle_muestra_el_reproductor_cuando_esta_preparado(self):
        self.fragmento.estado = Fragmento.PREPARADO
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        respuesta = self.client.get(reverse("detalle", args=[self.fragmento.pk]))
        assert b"Analizar" in respuesta.content

    def test_el_detalle_muestra_el_mensaje_de_error(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.mensaje = "No se pudo descargar el audio del enlace"
        self.fragmento.save()
        respuesta = self.client.get(reverse("detalle", args=[self.fragmento.pk]))
        assert "No se pudo descargar".encode() in respuesta.content

    def test_la_misma_url_reutiliza_la_cancion(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion"):
            self.client.post(reverse("index"), {
                "url": "https://youtu.be/abc", "inicio": "1:30", "fin": "2:00",
            })
        assert Cancion.objects.filter(referencia="https://youtu.be/abc").count() == 1
        nuevo = Fragmento.objects.exclude(pk=self.fragmento.pk).get()
        assert nuevo.cancion == self.cancion
        assert nuevo.origen == "https://youtu.be/abc"

    def test_reintentar_relanza_el_analisis_si_ya_hay_recorte(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.archivos = {"mezcla_wav": "media/x.wav"}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_analisis") as lanzar:
            respuesta = self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk)
        assert respuesta.status_code == 302
        self.fragmento.refresh_from_db()
        assert self.fragmento.estado == Fragmento.PREPARADO

    def test_reintentar_relanza_la_preparacion_si_no_hay_recorte(self):
        self.fragmento.estado = Fragmento.ERROR
        self.fragmento.archivos = {}
        self.fragmento.save()
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_called_once_with(self.fragmento.pk, "https://youtu.be/abc")

    def test_reintentar_no_hace_nada_si_no_esta_en_error(self):
        with patch("transcripciones.views.trabajos.lanzar_preparacion") as lanzar:
            self.client.post(reverse("reintentar", args=[self.fragmento.pk]))
        lanzar.assert_not_called()
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest web/transcripciones/tests_vistas.py -q`
Esperado: FALLA con `ModuleNotFoundError: No module named 'transcripciones.formularios'`

- [ ] **Paso 3: Escribir `web/transcripciones/formularios.py`**

```python
import re

from django import forms

from motor.config import Config

_PATRON = re.compile(r"^(?:(\d+):)?(\d+(?:\.\d+)?)$")


def parsear_tiempo(texto) -> float:
    """Acepta '90', '1:30' y '1:30.5'. Devuelve segundos.

    Sin minutos, los segundos son libres ('90' son 90 s). Con minutos, los
    segundos van de 0 a 59, como en un reloj ('1:75' no vale).
    """
    coincidencia = _PATRON.match(str(texto).strip())
    if not coincidencia:
        raise ValueError(f"tiempo inválido: {texto!r}. Usa el formato 1:30")
    minutos, segundos = coincidencia.groups()
    if minutos is not None and float(segundos) >= 60:
        raise ValueError(f"tiempo inválido: {texto!r}. Los segundos van de 0 a 59")
    return (int(minutos) if minutos else 0) * 60 + float(segundos)


class FormularioFragmento(forms.Form):
    url = forms.CharField(required=False)
    archivo = forms.FileField(required=False)
    inicio = forms.CharField()
    fin = forms.CharField()
    separar = forms.BooleanField(required=False, initial=True)

    def clean(self):
        datos = super().clean()
        if not datos.get("url") and not datos.get("archivo"):
            raise forms.ValidationError("Pega un enlace de YouTube o sube un archivo.")
        try:
            inicio = parsear_tiempo(datos.get("inicio", ""))
            fin = parsear_tiempo(datos.get("fin", ""))
        except ValueError as error:
            raise forms.ValidationError(str(error)) from error
        if fin <= inicio:
            raise forms.ValidationError("El final debe ser posterior al inicio.")
        limite = Config.desde_entorno().max_fragmento_s
        if fin - inicio > limite:
            raise forms.ValidationError(
                f"El fragmento dura {fin - inicio:.0f} s y el límite es {limite:.0f} s. "
                f"Recorta un trozo más corto."
            )
        datos["inicio_s"] = inicio
        datos["fin_s"] = fin
        return datos
```

- [ ] **Paso 4: Escribir `web/transcripciones/views.py`**

```python
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from motor.contrato import formato_tiempo

from . import trabajos
from .formularios import FormularioFragmento
from .models import Cancion, Fragmento

NOMBRES_DESCARGA = {"midi": "melodia.mid", "txt": "notas.txt", "pdf": "notas.pdf"}


def index(request):
    formulario = FormularioFragmento(request.POST or None, request.FILES or None)
    if request.method == "POST" and formulario.is_valid():
        datos = formulario.cleaned_data
        if datos.get("archivo"):
            origen = _guardar_subida(datos["archivo"])
            cancion = Cancion.objects.create(
                titulo=Path(origen.name).stem, fuente="archivo", referencia=origen.name,
            )
        else:
            origen = datos["url"].strip()
            # La misma URL cuelga de la misma canción: el historial no se llena
            # de repeticiones y la descarga ya está en caché.
            cancion = Cancion.objects.filter(fuente="youtube", referencia=origen).first()
            if cancion is None:
                cancion = Cancion.objects.create(titulo="", fuente="youtube", referencia=origen)
        fragmento = Fragmento.objects.create(
            cancion=cancion, origen=str(origen),
            inicio_s=datos["inicio_s"], fin_s=datos["fin_s"],
            separar=bool(datos.get("separar")),
        )
        trabajos.lanzar_preparacion(fragmento.pk, str(origen))
        return redirect("detalle", pk=fragmento.pk)

    return render(request, "transcripciones/index.html", {
        "formulario": formulario,
        "recientes": Fragmento.objects.select_related("cancion")[:8],
    })


def _guardar_subida(archivo) -> Path:
    """default_storage añade un sufijo si ya existe un archivo con ese nombre,
    así dos grabaciones llamadas 'ensayo.m4a' no se pisan."""
    nombre = default_storage.save(f"subidas/{archivo.name}", archivo)
    return Path(default_storage.path(nombre))


def detalle(request, pk):
    fragmento = get_object_or_404(Fragmento.objects.select_related("cancion"), pk=pk)
    return render(request, "transcripciones/detalle.html", {
        "fragmento": fragmento,
        "frases": fragmento.por_frases(),
        "desplazamiento": fragmento.inicio_s,
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
def analizar(request, pk):
    fragmento = get_object_or_404(Fragmento, pk=pk)
    if fragmento.estado == Fragmento.PREPARADO:
        trabajos.lanzar_analisis(fragmento.pk)
    return redirect("detalle", pk=pk)


@require_POST
def reintentar(request, pk):
    """Desde error: si ya hay recorte, vuelve a analizar; si no, vuelve a preparar."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    if fragmento.estado == Fragmento.ERROR:
        if fragmento.archivos.get("mezcla_wav"):
            fragmento.estado = Fragmento.PREPARADO
            fragmento.mensaje = ""
            fragmento.save(update_fields=["estado", "mensaje"])
            trabajos.lanzar_analisis(fragmento.pk)
        else:
            trabajos.lanzar_preparacion(fragmento.pk, fragmento.origen)
    return redirect("detalle", pk=pk)


def historial(request):
    return render(request, "transcripciones/historial.html", {
        "fragmentos": Fragmento.objects.select_related("cancion"),
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
    """Entrega el audio para reproducirlo en la página, no para descargarlo."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    ruta = _archivo_de(fragmento, clave)
    return FileResponse(open(ruta, "rb"), content_type="audio/wav")
```

- [ ] **Paso 5: Escribir las rutas**

Crear `web/transcripciones/urls.py`:

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("historial/", views.historial, name="historial"),
    path("fragmento/<int:pk>/", views.detalle, name="detalle"),
    path("fragmento/<int:pk>/estado/", views.estado, name="estado"),
    path("fragmento/<int:pk>/analizar/", views.analizar, name="analizar"),
    path("fragmento/<int:pk>/reintentar/", views.reintentar, name="reintentar"),
    path("fragmento/<int:pk>/datos/", views.datos, name="datos"),
    path("fragmento/<int:pk>/audio/<str:clave>/", views.audio, name="audio"),
    path("fragmento/<int:pk>/descargar/<str:clave>/", views.descargar, name="descargar"),
]
```

Sustituir `web/quenotas/urls.py`:

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("transcripciones.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

`views.datos` se implementa en la tarea 19. Para que las rutas carguen ahora, añadir en `views.py` un marcador provisional que la tarea 19 sustituye por la versión real:

```python
def datos(request, pk):
    return JsonResponse({"notas": [], "pistas": {}})
```

- [ ] **Paso 6: Escribir las plantillas**

Crear `web/transcripciones/templates/transcripciones/base.html`:

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}Quenotas{% endblock %}</title>
  {% load static %}
  <link rel="stylesheet" href="{% static 'estilo.css' %}">
</head>
<body>
  <header>
    <a href="{% url 'index' %}"><strong>Quenotas</strong></a>
    <a href="{% url 'historial' %}">Historial</a>
  </header>
  <main>{% block contenido %}{% endblock %}</main>
</body>
</html>
```

Crear `web/transcripciones/templates/transcripciones/index.html`:

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
    <input type="file" name="archivo" accept="audio/*,video/*">
  </label>
  <div class="rango">
    <label>Desde <input type="text" name="inicio" placeholder="0:30"
                        value="{{ formulario.inicio.value|default:'' }}"></label>
    <label>Hasta <input type="text" name="fin" placeholder="1:30"
                        value="{{ formulario.fin.value|default:'' }}"></label>
  </div>
  <label class="casilla">
    <input type="checkbox" name="separar" checked>
    Separar la melodía de la banda (desmarca si el audio ya es solo el instrumento)
  </label>
  <button type="submit">Obtener el fragmento</button>
</form>

{% if recientes %}
<h2>Últimos fragmentos</h2>
<ul>
  {% for fragmento in recientes %}
    <li><a href="{% url 'detalle' fragmento.pk %}">{{ fragmento }}</a>
        <span class="estado">{{ fragmento.get_estado_display }}</span></li>
  {% endfor %}
</ul>
{% endif %}
{% endblock %}
```

Crear `web/transcripciones/templates/transcripciones/detalle.html`:

```html
{% extends "transcripciones/base.html" %}
{% block contenido %}
<h1>{{ fragmento.cancion }}</h1>
<p class="rango">Fragmento {{ rango }}</p>

{% if fragmento.estado == "error" %}
  <div class="error"><p>{{ fragmento.mensaje }}</p></div>
  <form method="post" action="{% url 'reintentar' fragmento.pk %}">
    {% csrf_token %}
    <button type="submit">Reintentar</button>
  </form>

{% elif fragmento.estado == "preparado" %}
  <p>Escucha el recorte para confirmar que es la parte que querías.</p>
  <audio controls src="{% url 'audio' fragmento.pk 'mezcla_wav' %}"></audio>
  <form method="post" action="{% url 'analizar' fragmento.pk %}">
    {% csrf_token %}
    <button type="submit">Analizar</button>
  </form>

{% elif fragmento.estado == "listo" %}
  {% include "transcripciones/resultado.html" %}

{% else %}
  <p class="trabajando" id="paso">{{ fragmento.paso|default:"Preparando" }}…</p>
  <script>
    setInterval(async () => {
      const respuesta = await fetch("{% url 'estado' fragmento.pk %}");
      const datos = await respuesta.json();
      document.getElementById("paso").textContent = (datos.paso || datos.estado) + "…";
      if (["preparado", "listo", "error"].includes(datos.estado)) location.reload();
    }, 2000);
  </script>
{% endif %}
{% endblock %}
```

Crear un `web/transcripciones/templates/transcripciones/resultado.html` vacío por ahora; la tarea 18 lo escribe.

- [ ] **Paso 7: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 30 tests pasan (5 de modelos, 11 de trabajos, 14 de vistas)

- [ ] **Paso 8: Commit**

```bash
git add web
git commit -m "feat: formulario de entrada, vista previa del recorte y consulta de estado"
```

---

### Tarea 18: Resultado, tabla de notas, descargas e historial

**Archivos:**
- Crear: `web/transcripciones/templates/transcripciones/resultado.html`, `historial.html`
- Crear: `web/static/estilo.css`
- Modificar: `web/transcripciones/tests_vistas.py` (añadir al final)

**Interfaces:**
- Consume: `Fragmento.por_frases()`, `Nota.etiqueta_confianza`, la ruta `descargar`
- Produce: la pantalla de resultado y la de historial

- [ ] **Paso 1: Escribir el test que falla**

Añadir al final de `web/transcripciones/tests_vistas.py`, dentro de `PruebaVistas`:

```python
    def _dejar_listo(self):
        from transcripciones.models import Nota
        self.fragmento.estado = Fragmento.LISTO
        self.fragmento.archivos = {"midi": "media/x.mid", "txt": "media/x.txt"}
        self.fragmento.avisos = ["La confianza media es baja."]
        self.fragmento.save()
        Nota.objects.create(fragmento=self.fragmento, frase=1, orden=1, nombre="G4",
                            midi=67, inicio_s=0.4, duracion_s=0.42, confianza=0.93, cents=-12)
        Nota.objects.create(fragmento=self.fragmento, frase=2, orden=2, nombre="B4",
                            midi=71, inicio_s=2.0, duracion_s=0.60, confianza=0.40, cents=30)

    def test_el_resultado_muestra_las_notas_agrupadas_por_frase(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert b"Frase 1" in contenido and b"Frase 2" in contenido
        assert b"G4" in contenido and b"B4" in contenido
        assert "alta".encode() in contenido and "baja".encode() in contenido

    def test_el_resultado_muestra_los_avisos(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("detalle", args=[self.fragmento.pk])).content
        assert "confianza media es baja".encode() in contenido

    def test_descargar_un_archivo_que_no_existe_da_404(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("descargar", args=[self.fragmento.pk, "pdf"]))
        assert respuesta.status_code == 404

    def test_el_historial_lista_los_fragmentos(self):
        self._dejar_listo()
        contenido = self.client.get(reverse("historial")).content
        assert b"Huayno" in contenido
```

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest web/transcripciones/tests_vistas.py -q`
Esperado: FALLA porque `resultado.html` está vacío y no aparece `Frase 1`

- [ ] **Paso 3: Escribir `resultado.html`**

```html
{% load static %}
{% if fragmento.avisos %}
  <div class="avisos">
    {% for aviso in fragmento.avisos %}<p>{{ aviso }}</p>{% endfor %}
  </div>
{% endif %}

<div id="lienzo-notas" data-datos="{% url 'datos' fragmento.pk %}"></div>

<p class="descargas">
  <a href="{% url 'descargar' fragmento.pk 'midi' %}">Descargar MIDI</a>
  <a href="{% url 'descargar' fragmento.pk 'txt' %}">Descargar TXT</a>
  <a href="{% url 'descargar' fragmento.pk 'pdf' %}">Descargar PDF</a>
</p>

{% for indice, notas in frases %}
  <h2 class="frase" data-frase="{{ indice }}" title="Clic para repetir esta frase en bucle">Frase {{ indice }}</h2>
  <table class="notas">
    <thead>
      <tr><th>#</th><th>Nota</th><th>Inicio</th><th>Duración</th><th>Confianza</th></tr>
    </thead>
    <tbody>
      {% for nota in notas %}
        <tr class="confianza-{{ nota.etiqueta_confianza }}" data-orden="{{ nota.orden }}">
          <td>{{ nota.orden }}</td>
          <td class="nombre">{{ nota.nombre }}</td>
          <td>{{ nota.inicio_s|floatformat:2 }} s</td>
          <td>{{ nota.duracion_s|floatformat:2 }} s</td>
          <td>{{ nota.etiqueta_confianza }}</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
{% endfor %}

<script src="{% static 'pianoroll.js' %}" defer></script>
```

- [ ] **Paso 4: Escribir `historial.html`**

```html
{% extends "transcripciones/base.html" %}
{% block contenido %}
<h1>Historial</h1>
<table class="notas">
  <thead><tr><th>Canción</th><th>Fragmento</th><th>Estado</th><th>Fecha</th></tr></thead>
  <tbody>
    {% for fragmento in fragmentos %}
      <tr>
        <td><a href="{% url 'detalle' fragmento.pk %}">{{ fragmento.cancion }}</a></td>
        <td>{{ fragmento.inicio_s|floatformat:0 }} a {{ fragmento.fin_s|floatformat:0 }} s</td>
        <td>{{ fragmento.get_estado_display }}</td>
        <td>{{ fragmento.creado|date:"d/m/Y H:i" }}</td>
      </tr>
    {% empty %}
      <tr><td colspan="4">Todavía no has analizado nada.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Paso 5: Escribir `web/static/estilo.css`**

```css
:root {
  --fondo: #14161a;
  --panel: #1d2027;
  --texto: #e6e8ec;
  --tenue: #9aa0ab;
  --acento: #6fb4ff;
  --alta: #4ec98a;
  --media: #e0b341;
  --baja: #e06a5c;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--fondo); color: var(--texto);
  font-family: system-ui, sans-serif; line-height: 1.5;
}
header {
  display: flex; gap: 1.5rem; align-items: center;
  padding: 1rem 1.5rem; border-bottom: 1px solid #2a2e37;
}
header a { color: var(--texto); text-decoration: none; }
main { max-width: 60rem; margin: 0 auto; padding: 1.5rem; }
h1 { font-size: 1.5rem; }
h2 { font-size: 1.1rem; margin-top: 2rem; }
label { display: block; margin: 0.75rem 0; color: var(--tenue); }
input[type="text"], input[type="file"] {
  display: block; width: 100%; margin-top: 0.25rem; padding: 0.6rem;
  background: var(--panel); border: 1px solid #2a2e37; border-radius: 6px;
  color: var(--texto);
}
.rango { display: flex; gap: 1rem; }
.rango label { flex: 1; }
.casilla { display: flex; gap: 0.5rem; align-items: flex-start; }
.casilla input { width: auto; }
button {
  margin-top: 1rem; padding: 0.7rem 1.4rem; border: 0; border-radius: 6px;
  background: var(--acento); color: #0b1017; font-weight: 600; cursor: pointer;
}
.separador { color: var(--tenue); text-align: center; margin: 0.25rem 0; }
.error { background: #3a1f1d; border-left: 3px solid var(--baja); padding: 0.75rem 1rem; }
.avisos { background: #33301c; border-left: 3px solid var(--media); padding: 0.75rem 1rem; }
.trabajando { color: var(--acento); }
.descargas { display: flex; gap: 1rem; margin: 1rem 0; }
.descargas a { color: var(--acento); }
table.notas { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
table.notas th, table.notas td {
  text-align: left; padding: 0.35rem 0.6rem; border-bottom: 1px solid #262a33;
}
table.notas .nombre { font-family: ui-monospace, monospace; font-weight: 600; }
tr.confianza-alta .nombre { color: var(--alta); }
tr.confianza-media .nombre { color: var(--media); }
tr.confianza-baja .nombre { color: var(--baja); }
tr.sonando { background: #232a36; }
audio { width: 100%; margin: 1rem 0; }
#lienzo-notas canvas { width: 100%; height: 220px; background: var(--panel); border-radius: 8px; }
.pistas, .controles { display: flex; gap: 1rem; color: var(--tenue); margin-top: 0.5rem; flex-wrap: wrap; }
.controles select { background: var(--panel); color: var(--texto); border: 1px solid #2a2e37; border-radius: 6px; padding: 0.2rem 0.4rem; }
.nota-actual { font-family: ui-monospace, monospace; color: var(--acento); }
h2.frase { cursor: pointer; }
h2.frase.en-bucle::after { content: "  (en bucle, clic para parar)"; color: var(--acento); font-weight: normal; font-size: 0.85rem; }
.estado { color: var(--tenue); font-size: 0.85rem; }
```

Las filas de la tabla llevan `data-orden` (entero) y no `data-inicio` (flotante): con `LANGUAGE_CODE = "es"` la plantilla imprime `0,4` y `Number("0,4")` es `NaN`, así que el resalte de la nota que suena nunca funcionaría. Los flotantes que necesita el lienzo viajan por JSON en la tarea 19.

- [ ] **Paso 6: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 34 tests pasan

- [ ] **Paso 7: Commit**

```bash
git add web
git commit -m "feat: pantalla de resultado con notas por frase, descargas e historial"
```

---

### Tarea 19: Lienzo de notas sincronizado con la reproducción

La pieza que el usuario pidió: la barra deslizable donde se ve qué nota suena en cada momento, con las tres pistas sobre la misma línea de tiempo.

**Archivos:**
- Modificar: `web/transcripciones/views.py` (sustituir el marcador `datos`)
- Crear: `web/static/pianoroll.js`
- Modificar: `web/transcripciones/tests_vistas.py` (añadir al final)

**Interfaces:**
- Consume: `Fragmento.archivos`, `Fragmento.notas`, la ruta `audio`
- Produce: `views.datos` que devuelve

```json
{
  "duracion_s": 60.0,
  "desplazamiento_s": 30.0,
  "notas": [{"orden": 1, "nombre": "G4", "midi": 67, "inicio_s": 0.4,
             "duracion_s": 0.42, "confianza": 0.93}],
  "pistas": [{"clave": "mezcla_wav", "etiqueta": "Mezcla original", "url": "/…"}]
}
```

Todo el trabajo de sincronización ocurre en el navegador leyendo `currentTime` del reproductor. El servidor no interviene: por eso va al milisegundo y por eso esta pieza es trasladable si algún día cambia la interfaz.

- [ ] **Paso 1: Escribir el test que falla**

Añadir al final de `web/transcripciones/tests_vistas.py`, dentro de `PruebaVistas`:

```python
    def test_los_datos_del_lienzo_traen_notas_frases_y_pistas(self):
        self._dejar_listo()
        respuesta = self.client.get(reverse("datos", args=[self.fragmento.pk]))
        datos = respuesta.json()
        assert datos["duracion_s"] == 60.0
        assert datos["desplazamiento_s"] == 30.0
        assert [nota["nombre"] for nota in datos["notas"]] == ["G4", "B4"]
        assert datos["notas"][0]["inicio_s"] == 0.4
        assert [nota["etiqueta"] for nota in datos["notas"]] == ["alta", "baja"]
        assert [frase["indice"] for frase in datos["frases"]] == [1, 2]
        assert datos["frases"][1]["inicio_s"] == 2.0
        assert datos["frases"][1]["fin_s"] == 2.6
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
        assert datos["pistas"][0]["etiqueta"] == "Mezcla original"
```

Añadir al principio del archivo: `import tempfile` y `from pathlib import Path`.

La etiqueta de confianza viaja calculada desde el servidor: el JavaScript no repite los umbrales de `etiqueta_confianza`, así que cuando se calibren cambian en un solo sitio.

- [ ] **Paso 2: Ejecutar el test y verificar que falla**

Ejecutar: `py -m pytest web/transcripciones/tests_vistas.py -q`
Esperado: FALLA porque `datos` devuelve el marcador con `"notas": []`

- [ ] **Paso 3: Sustituir el marcador `datos` en `views.py`**

```python
ETIQUETAS_PISTA = (
    ("mezcla_wav", "Mezcla original"),
    ("melodia_wav", "Melodía aislada"),
    ("notas_wav", "Notas detectadas"),
)


def datos(request, pk):
    """Todo lo que el lienzo necesita, en una sola petición."""
    fragmento = get_object_or_404(Fragmento, pk=pk)
    pistas = [
        {
            "clave": clave,
            "etiqueta": etiqueta,
            "url": reverse("audio", args=[fragmento.pk, clave]),
        }
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

Añadir el import que falta al principio de `views.py`:

```python
from django.urls import reverse
```

- [ ] **Paso 4: Escribir `web/static/pianoroll.js`**

```javascript
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
```

- [ ] **Paso 5: Ejecutar los tests y verificar que pasan**

Ejecutar: `py -m pytest web -q`
Esperado: 36 tests pasan

- [ ] **Paso 6: Comprobación visual en el navegador**

```bash
py web/manage.py runserver
```

Abrir un fragmento ya analizado. Verificar cinco cosas: los bloques de nota aparecen con altura acorde a su afinación; la línea vertical avanza al reproducir y la nota que suena se resalta a la vez en el lienzo y en la tabla; al cambiar de pista la reproducción continúa en el mismo segundo; a 0.5x se oye a la mitad de velocidad con el mismo tono; y al hacer clic en "Frase 2" el reproductor repite solo ese tramo (sombreado en el lienzo) hasta que se vuelve a hacer clic.

Si al hacer clic en el lienzo la posición no salta, o salta con retraso de varios segundos, es la falta de soporte de `Range` en la vista `audio`: ver la tarea 21.

- [ ] **Paso 7: Commit**

```bash
git add web
git commit -m "feat: lienzo de notas sincronizado con las tres pistas de audio"
```

---

### Tarea 20: Arranque de doble clic, acceso desde el teléfono y calibración

Cierra el proyecto: que se abra sin consola, que se pueda usar desde el móvil en la red de casa, y que exista la prueba que dice si el sistema merece confianza.

**Archivos:**
- Crear: `iniciar.bat`
- Crear: `tests/fijos/escala_quena.wav` (grabación real)
- Crear: `tests/test_calibracion.py`
- Modificar: `CLAUDE.md`

**Interfaces:**
- Consume: todo lo anterior
- Produce: arranque de doble clic y la prueba de calibración

- [ ] **Paso 1: Crear `iniciar.bat`**

```bat
@echo off
cd /d "%~dp0"
echo Iniciando Quenotas...
echo.
py web\manage.py migrate --noinput
py web\manage.py recuperar_trabajos
echo.
echo   En este equipo:   http://localhost:8000
echo   Desde el telefono (mismo wifi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%a:8000
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
py web\manage.py runserver 0.0.0.0:8000 --noreload
```

Cuatro decisiones del script:

* `migrate` antes de todo: en un clon limpio no existe `db.sqlite3` y sin esto la primera petición falla.
* `recuperar_trabajos`: lo que quedó a medias la última vez pasa a `error` con botón de reintento, en vez de quedarse "analizando" para siempre.
* `tokens=2 delims=:` corta la línea de `ipconfig` por los dos puntos, así que no depende de cuántos puntos de relleno imprima Windows en español o en inglés. La dirección sale con un espacio delante; el navegador lo ignora.
* El navegador se abre tres segundos después, cuando el servidor ya escucha; y `--noreload` evita que el recargador automático de Django mate el hilo de análisis cada vez que cambia un archivo.

`0.0.0.0` es lo que hace que el servidor escuche en toda la red local y no solo en el propio equipo. Con eso, desde el navegador del teléfono se entra a la IP que imprime el script y se puede subir directamente la grabación recién hecha, sin pasarla por cable. El trabajo pesado lo sigue haciendo la laptop con su GPU.

La primera vez, Windows pedirá permiso de firewall para Python: hay que aceptarlo en redes privadas.

- [ ] **Paso 2: Comprobar el acceso desde el teléfono**

Doble clic en `iniciar.bat`, y desde el teléfono en el mismo wifi abrir la dirección que imprime. Debe verse el formulario. Subir una grabación corta y comprobar que llega.

- [ ] **Paso 3: Grabar el material de calibración**

Grabar con el teléfono, en un sitio silencioso, la escala de Sol mayor ascendente en la quena: G4, A4, B4, C5, D5, E5, F#5, G5. Una nota por segundo aproximadamente, con un silencio claro entre cada una y sin vibrato.

Guardar el archivo como `tests/fijos/escala_quena.wav` (convertirlo a WAV con `ffmpeg -i grabacion.m4a tests/fijos/escala_quena.wav` si el teléfono graba en otro formato).

Añadir la excepción al `.gitignore` para que este archivo sí entre al repositorio: ya está contemplada con la línea `!tests/fijos/*.wav`.

- [ ] **Paso 4: Escribir la prueba de calibración**

Crear `tests/test_calibracion.py`:

```python
"""La prueba que decide si el sistema merece confianza.

Se apoya en una grabación real de la quena tocando una escala conocida.
Mientras esta prueba no pase, no hay razón para creerle el resultado de
una canción.
"""
from pathlib import Path

import pytest

from motor.config import Config
from motor.contrato import Fragmento
from motor.pipeline import analizar_recorte

FIJO = Path(__file__).parent / "fijos" / "escala_quena.wav"
ESPERADO = ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]


@pytest.mark.lento
@pytest.mark.skipif(not FIJO.exists(), reason="falta la grabación de calibración")
def test_la_escala_de_sol_se_reconoce_completa():
    resultado = analizar_recorte(
        FIJO,
        Fragmento(titulo="Calibración", fuente="archivo", referencia=FIJO.name,
                  inicio_s=0.0, fin_s=10.0),
        config=Config.desde_entorno({"QUENOTAS_DISPOSITIVO": "cpu"}),
        separar=False,
    )
    detectadas = [nota.nombre for nota in resultado.notas]
    assert detectadas == ESPERADO, f"se esperaba {ESPERADO} y salió {detectadas}"


@pytest.mark.lento
@pytest.mark.skipif(not FIJO.exists(), reason="falta la grabación de calibración")
def test_la_afinacion_de_la_quena_no_se_desvia_demasiado():
    resultado = analizar_recorte(
        FIJO,
        Fragmento(titulo="Calibración", fuente="archivo", referencia=FIJO.name,
                  inicio_s=0.0, fin_s=10.0),
        config=Config.desde_entorno({"QUENOTAS_DISPOSITIVO": "cpu"}),
        separar=False,
    )
    desviaciones = [abs(nota.cents) for nota in resultado.notas]
    assert max(desviaciones) < 40, f"desviaciones en cents: {desviaciones}"
```

- [ ] **Paso 5: Ejecutar la calibración y ajustar**

Ejecutar: `py -m pytest tests/test_calibracion.py -q -s`

Si falla, **no tocar los tests**: ajustar los umbrales en `motor/config.py` o vía variables de entorno y volver a probar. Las causas más frecuentes y su ajuste:

| Síntoma | Ajuste |
|---|---|
| Aparecen notas de más entre las reales | subir `duracion_min_s` a 0.10 |
| Una nota sale partida en dos | subir `ventana_mediana` a 7 o 9. Si sigue pasando con notas que quedan justo entre dos semitonos, el siguiente paso es histéresis en `curva_a_notas` (cambiar de nota solo cuando el desvío supera 0.5 más un margen), que no está implementada a propósito hasta ver material real |
| Faltan notas al final o al principio | bajar `umbral_confianza` a 0.4 |
| Salen notas una octava por encima | subir `fmin_hz`, la quena en Sol no baja de G4 (392 Hz) |
| `afinacion_cents` sale grande y constante entre grabaciones | la quena está afinada distinto; es dato real, no error. Los nombres de nota ya lo compensan |
| Dos notas repetidas salen como una sola larga | limitación conocida de la primera versión (ver diseño, sección 14); no hay umbral que lo arregle |

Anotar en `CLAUDE.md` los valores finales que hicieron pasar la prueba, porque son los que definen el comportamiento del sistema.

- [ ] **Paso 6: Prueba completa de extremo a extremo**

Con el servidor levantado, hacer el recorrido entero con una canción real de la banda: pegar el enlace, poner un rango donde suene la quena, escuchar el recorte, analizar, y comparar la pista de notas detectadas contra la melodía aislada. Comprobar que las tres descargas abren bien y que el PDF se imprime legible.

- [ ] **Paso 7: Actualizar `CLAUDE.md`**

Sustituir la sección "Estado" por:

```markdown
## Estado

Implementado y en uso. Se arranca con doble clic en `iniciar.bat`, que abre
`http://localhost:8000` e imprime la dirección para entrar desde el teléfono
en el mismo wifi.

## Cómo se prueba

- Todo: `py -m pytest -q`
- Solo motor: `py -m pytest tests -q`
- Solo web: `py -m pytest web -q`
- Calibración con la quena real: `py -m pytest tests/test_calibracion.py -q`

Los tests marcados `lento` cargan CREPE. Para saltarlos: `py -m pytest -q -m "not lento"`.

## Umbrales calibrados

Valores que hicieron pasar la prueba de calibración con la quena en Sol:
[anotar aquí los valores finales de config.py]
```

- [ ] **Paso 8: Commit**

```bash
git add iniciar.bat tests/test_calibracion.py tests/fijos/escala_quena.wav CLAUDE.md
git commit -m "feat: arranque de doble clic, acceso desde el teléfono y calibración con quena real"
```

---

### Tarea 21 (opcional): pulido del reproductor y de la sonificación

No forma parte de la primera versión. Se decide después de usar el sistema unos días con canciones reales, y cada punto es independiente de los demás. Vienen de la revisión del 2026-09-05 (`docs/REVISION_PLAN.md`, puntos C5, C6 y D4).

- [ ] **Nombres de nota en el lienzo.** Dibujar en el margen izquierdo del `canvas` el nombre de cada carril (`G4`, `A4`, ...) y sombrear los carriles que no pertenecen a la escala de Sol mayor. El músico lee el lienzo como una tablatura sin mirar la tabla. Solo `pianoroll.js`.

- [ ] **Peticiones `Range` en la vista `audio`.** `FileResponse` no atiende la cabecera `Range`, y Chrome tarda en permitir saltos (`currentTime`) hasta tener el archivo entero. Con archivos de 5 a 10 MB funciona, pero a saltos. Dos salidas: una vista que lea `Range` y responda `206` con `Content-Range` (unas veinte líneas y un test que pida `bytes=0-99`), o generar en `exportar.py` versiones OGG a 96 kbps de las tres pistas para el navegador (diez veces más pequeñas; ffmpeg ya está).

- [ ] **Sonificación con armónicos.** Un seno puro se percibe con menos definición de altura que un tono con armónicos y al compararlo con la quena real se nota. En `sonificar`, sumar los armónicos 2 y 3 con amplitudes 0.5 y 0.25 y renormalizar. Una línea más y el test existente sigue pasando.

- [ ] **WAL en SQLite.** Si aparecen errores `database is locked` mientras el hilo escribe `paso` y la página sondea `estado`, activar `PRAGMA journal_mode=WAL` en la señal `connection_created`. `timeout: 30` ya evita casi todos.

---

## Correcciones tras la revisión final (2026-09-05)

Ronda única de arreglos aplicada tras la revisión final, sobre el código ya terminado de las tareas 1 a 20. Cada punto describe qué archivo cambió y qué se corrigió respecto al bloque de código de la tarea correspondiente; los bloques de código de las tareas no se reescribieron.

- **`web/static/pianoroll.js` (tarea 18):** el `select` de velocidad se crea antes que el `forEach` de pistas (no después), y el manejador `change` del selector de pista, dentro de su callback `loadedmetadata`, ahora también asigna `reproductor.playbackRate = Number(velocidad.value)`. Antes, cambiar de pista restablecía la velocidad a 1 porque asignar `reproductor.src` reinicia `playbackRate`.
- **`web/transcripciones/templates/transcripciones/resultado.html` (tarea 16):** se añadió un `<p class="limitacion">` estático, fuera del `{% if fragmento.avisos %}`, con el aviso de que dos notas iguales seguidas pueden salir como una sola nota larga (sección 14 del diseño). En `web/static/estilo.css` se añadió la regla `.limitacion`.
- **`web/transcripciones/views.py` (tarea 15):** `analizar` y `reintentar` ya no leen `fragmento.estado` en Python y después lanzan el hilo; ahora usan `Fragmento.objects.filter(pk=pk, estado=<esperado>).update(...)` y solo lanzan el trabajo si `update()` devolvió filas afectadas. Antes, dos peticiones simultáneas (o un doble clic) podían lanzar el mismo análisis dos veces porque la comprobación de estado y el cambio de estado no eran atómicos.
- **`web/transcripciones/templates/transcripciones/index.html` (tarea 15):** la casilla `separar` pasó de `checked` fijo a `{% if formulario.separar.value or not formulario.is_bound %}checked{% endif %}`, para que un reenvío con error de validación no la muestre marcada si el usuario la había desmarcado.
- **`iniciar.bat` (tarea 20):** la línea que imprime la IP para el teléfono ahora encadena un segundo `for /f "tokens=1"` que recorta el espacio inicial que deja `tokens=2 delims=:` sobre la salida de `ipconfig`; antes la URL salía como `http:// 192.168...`. Además, tras `migrate` se comprueba `errorlevel 1` y se corta con un mensaje y `pause` si falla, y se añadió un `pause` final tras `runserver` para que la ventana no se cierre sola si el servidor termina con error.
- **`web/transcripciones/templates/transcripciones/resultado.html` (tarea 16):** cada enlace de descarga (MIDI, TXT, PDF) quedó condicionado a `{% if fragmento.archivos.<clave> %}`; antes se mostraban los tres aunque el archivo no existiera (por ejemplo, si la generación del PDF había fallado), y el enlace llevaba a un 404.
- **`motor/pipeline.py`, `_separar_con_respaldo` (tarea 11):** se guarda `reintento_cpu = True` en el `except` cuando falla por falta de memoria en CUDA, y el aviso de "corrió en CPU" se añade en el camino de éxito (`if actual == "cpu" and reintento_cpu`), no en el momento del fallo. Antes el aviso se añadía apenas fallaba CUDA, así que aparecía incluso cuando el reintento en CPU también fallaba y no se separó nada.
- **`motor/pipeline.py` (tarea 11):** el umbral `0.65` de la comparación de confianza media quedó nombrado como constante de módulo `CONFIANZA_MEDIA_AVISO`, junto a `AFINACION_AVISO_CENTS`.
- **`motor/pipeline.py`, sonificación dentro de `analizar_recorte` (tarea 11):** el tercer argumento de `sonificar(...)` pasó de `fragmento.fin_s - fragmento.inicio_s` a `fragmento.duracion_s`, la propiedad ya provista por el contrato.
- **`motor/audio.py`, `_ejecutar` (tarea 4):** el mensaje de reserva cuando `stderr` viene vacío pasó de `"ffmpeg falló sin mensaje"` a `f"{comando[0]} falló sin mensaje"`, porque `_ejecutar` también se usa para `ffprobe`.
- **`docs/PLAN.md` y `CLAUDE.md`:** esta sección, y en `CLAUDE.md` tres líneas nuevas bajo "Estado" sobre la limpieza pendiente de `media/fragmentos/`, el soporte de `Range` en iPhone/Safari, y que los archivos subidos todavía no se reutilizan entre fragmentos.

## Revisión del plan contra el diseño

Comprobación hecha al terminar de escribir, sección por sección del diseño:

| Sección del diseño | Tarea que la implementa |
|---|---|
| 3. Entradas: YouTube y archivo subido | 12, 14, 17 |
| 4. Salidas: lista, MIDI, TXT, PDF, tres pistas | 9, 10, 18, 19 |
| 5. Arquitectura en dos capas | 2 a 14 el motor, 15 a 19 la web |
| 6. Contrato de datos | 2, y respetado por todas |
| 7.1 Obtención y recorte validado | 6, 12, 14 |
| 7.2 Vista previa antes de analizar | 14 (partido en dos), 16, 17 |
| 7.3 Separación opcional | 13, 14 |
| 7.4 Detección de afinación | 7 |
| 7.5 Conversión a notas discretas | 5 |
| 7.6 Agrupación en frases | 5 |
| 7.7 Generación de salidas | 9, 10, 11 |
| 8.1 Modelo de datos | 15 |
| 8.2 Pantallas | 17, 18 |
| 8.3 Lienzo de notas | 19 |
| 8.4 Procesamiento en segundo plano | 16 |
| 9. Decisiones para un despliegue futuro | 3 (configuración), 2 y 14 (motor aislado), 16 (trabajos con identificador) |
| 10. Manejo de errores | 6 (rango y duración), 12 (enlace bloqueado), 13 (separación), 14 (respaldo si falla la separación), 8 (confianza baja y límite de duración), 16 y 17 (error visible, nunca página en blanco) |
| 11. Pruebas | 4 (señales), 5 (casos límite), 20 (calibración), 15 a 19 (Django con motor simulado), 12 y 13 (red simulada) |
| 12. Dependencias | 1 |
| 13. Fases de construcción | fase 0 son las tareas 1 a 8 |

**Ajustes aplicados al diseño** (ya reflejados en `docs/DISENO.md`, se dejan como registro):

1. **Los tiempos del contrato son relativos al fragmento**, no absolutos. El desplazamiento vive en `fragmento.inicio_s` y la pantalla suma.
2. **`analizar_fuente` se parte en `preparar` y `analizar_preparado`**, porque la aplicación para entre ambas para dejar escuchar el recorte.
3. **El estado del fragmento tiene seis valores** y no cuatro: se añaden `preparando` y `preparado`.
4. **`orden` de la nota es global dentro del fragmento**, no reinicia en cada frase.

**Revisión del 2026-09-05** (`docs/REVISION_PLAN.md`), aplicada sobre este plan y sobre el diseño: corrección de nueve pasos que fallaban tal como estaban escritos, alineación con el diseño en cuatro puntos (respaldo en CPU, modelos descargados en la tarea 1, dependencias reales de la paralelización, estado del diseño), y cinco mejoras incorporadas: caché de descargas por id de video con reutilización de la canción, un análisis a la vez, recuperación y reintento de trabajos interrumpidos, velocidad y bucle por frase en el reproductor, y compensación del desvío de afinación antes de nombrar las notas.

## Cómo ejecutar este plan

Las tareas 1 a 8 van en orden y sin paralelizar: fijan el contrato del que dependen todas las demás, y al terminar la 8 el motor ya sirve con las grabaciones del teléfono.

A partir de ahí se abren tres caminos que no se pisan entre sí:

- **Exportadores:** tareas 9, 10 y 11
- **Fuentes externas:** tareas 12, 13 y 14
- **Aplicación web:** tareas 15 a 19, en ese orden entre ellas. Dependen solo del contrato (tarea 2) y del pipeline base (tarea 8): `models.py` importa `etiqueta_confianza` desde `contrato.py`, y `trabajos.py` importa el pipeline dentro de las funciones. La 17 en adelante se puede *escribir* sin la 14, pero solo se puede *usar de verdad* cuando la 14 está hecha.

La tarea 20 va al final y la hace el músico, no un agente: requiere grabar la quena. La 21 es opcional y se decide después de usar el sistema unos días.

**El ajuste fino del segmentador (tarea 20, paso 5) no se paraleliza.** El cuello de botella es escuchar si el resultado suena bien.
