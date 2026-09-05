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
    inicio = forms.CharField(required=False)   # vacío = 0:00
    fin = forms.CharField(required=False)      # vacío = error con explicación, en clean()
    separar = forms.BooleanField(required=False, initial=True)

    def clean(self):
        datos = super().clean()
        if not datos.get("url") and not datos.get("archivo"):
            raise forms.ValidationError("Pega un enlace de YouTube o sube un archivo.")
        texto_inicio = (datos.get("inicio") or "").strip() or "0:00"
        texto_fin = (datos.get("fin") or "").strip()
        if not texto_fin:
            raise forms.ValidationError(
                "Falta el final del fragmento (\"Hasta\", por ejemplo 1:30). "
                "Cada fragmento puede durar hasta 3 minutos; una canción entera se analiza por partes."
            )
        try:
            inicio = parsear_tiempo(texto_inicio)
            fin = parsear_tiempo(texto_fin)
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
