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
