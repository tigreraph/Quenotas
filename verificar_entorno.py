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
        comando = [sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "-d", dispositivo,
                   "--segment", "6", "--out", carpeta, str(entrada)]
        salida = subprocess.run(comando, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=ENTORNO_UTF8)
        if salida.returncode != 0:
            ultima = (salida.stderr or "").strip().splitlines()[-1:]
            raise RuntimeError(ultima[0] if ultima else "demucs falló sin mensaje")
        esperado = Path(carpeta) / "htdemucs_6s" / "humo" / "other.wav"
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
