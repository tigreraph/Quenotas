from pathlib import Path

from django.conf import settings
from django.db import migrations


def rellenar_origen(apps, schema_editor):
    """Las canciones anteriores al selector de frases no guardaban origen."""
    Cancion = apps.get_model("transcripciones", "Cancion")
    for cancion in Cancion.objects.filter(origen=""):
        if cancion.fuente == "youtube" and cancion.referencia:
            cancion.origen = cancion.referencia
        elif cancion.fuente == "archivo" and cancion.referencia:
            ruta = Path(settings.MEDIA_ROOT) / "subidas" / cancion.referencia
            if ruta.is_file():
                cancion.origen = str(ruta)
        if cancion.origen:
            cancion.save(update_fields=["origen"])


class Migration(migrations.Migration):
    dependencies = [("transcripciones", "0002_cancion_estado_y_audio")]
    operations = [migrations.RunPython(rellenar_origen, migrations.RunPython.noop)]
