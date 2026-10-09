# scanner-app

Paquete Flask para gestionar la impresión y el escaneo de la Brother
DCP-1610W. El código Python vive en `src/scanner_app`; la interfaz, sus
plantillas y los recursos estáticos se mantienen en la raíz del repositorio.

## Desarrollo

Instala las dependencias bloqueadas con uv desde la raíz del repositorio:

```sh
uv sync --project scanner-app
uv run --project scanner-app gunicorn 'scanner_app:create_app()'
```

`pyproject.toml` declara las dependencias directas y `uv.lock` fija el
conjunto resuelto. Actualiza el bloqueo con `uv lock --project scanner-app`.
No se mantiene un `requirements.txt` separado.

Los escaneos y las cargas de impresión se guardan temporalmente en el
contenedor. No se monta un volumen para documentos; las sesiones de escaneo se
limpian al descargarlas, cerrarlas o tras una hora de inactividad.
