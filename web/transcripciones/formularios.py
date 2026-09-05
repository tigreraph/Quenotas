import re

from django import forms

from motor.config import Config

_PATRON = re.compile(r"^(?:(\d+):)?([0-5]?\d(?:\.\d+)?)$")


def parsear_tiempo(texto) -> float:
    """Acepta '90', '1:30' y '1:30.5'. Devuelve segundos."""
    coincidencia = _PATRON.match(str(texto).strip())
    if not coincidencia:
        raise ValueError(f"tiempo inválido: {texto!r}. Usa el formato 1:30")
    minutos, segundos = coincidencia.groups()
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
