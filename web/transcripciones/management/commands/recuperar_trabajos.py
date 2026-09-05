from django.core.management.base import BaseCommand

from transcripciones.trabajos import recuperar_huerfanos


class Command(BaseCommand):
    help = "Marca como error los fragmentos que quedaron a medias en una sesión anterior."

    def handle(self, *args, **opciones):
        cantidad = recuperar_huerfanos()
        self.stdout.write(f"Fragmentos recuperados: {cantidad}")
