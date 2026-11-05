# Quickstart: probar Campaign Manager

Esta guía prepara una campaña de demostración local para probar el flujo actual con SillyTavern. No instala SillyTavern ni Ollama por ti y no representa todavía una aplicación independiente.

## 1. Requisitos

- Python 3.12 o superior.
- Dependencias del proyecto instaladas con `pip install -r requirements.txt`.
- Ollama instalado y en ejecución, con un modelo compatible descargado.
- SillyTavern instalado localmente.

Campaign Manager está pensado para ejecutarse en local. Mantén el backend enlazado a `127.0.0.1`; no lo expongas a la red.

## 2. Arrancar el backend

En Windows, desde la raíz del repositorio:

```bat
start.bat
```

Comprueba que responde:

- `http://127.0.0.1:8765/health` — proceso activo.
- `http://127.0.0.1:8765/ready` — base de datos disponible.
- `http://127.0.0.1:8765/docs` — documentación interactiva de la API.

## 3. Crear una campaña de demostración

En otra terminal, desde la raíz del repositorio:

```bash
python scripts/bootstrap_demo.py
```

Opcionalmente, personaliza los nombres:

```bash
python scripts/bootstrap_demo.py --campaign-name "Mi primera aventura" --character-name "Kael"
```

El script crea una campaña D&D 5e 2014, una primera sesión y un personaje de prueba de nivel 1. Selecciona automáticamente la sesión y el personaje como activos e imprime los identificadores.

**Cada ejecución crea una campaña nueva.** No borra ni modifica campañas existentes. Si el proceso falla a mitad, revisa la lista de campañas antes de volver a ejecutarlo para evitar dejar otra campaña de prueba incompleta.

## 4. Conectar SillyTavern

1. Instala la extensión local incluida en `integrations/sillytavern` siguiendo el procedimiento de extensiones de tu instalación de SillyTavern.
2. Activa Campaign Manager en los ajustes de la extensión.
3. Configura el backend como `http://127.0.0.1:8765`.
4. Introduce el **Campaign ID** que imprimió el script.
5. Mantén inicialmente el modo de dados automático; puedes probar el modo manual después.

La extensión solicita al backend la resolución de la acción antes de que SillyTavern genere la narración. Si el backend solicita una aclaración o una tirada manual, sigue la indicación del modelo y responde en el chat.

## 5. Prueba mínima recomendada

En un chat nuevo, prueba estas acciones de una en una:

1. Pregunta al posadero qué rumores circulan por la zona.
2. Examina la sala y pregunta por una persona u objeto concreto.
3. Intenta una acción incierta que pueda requerir una prueba de característica o habilidad.
4. Repite una acción que solicite aclaración y responde con el dato que falta.
5. Activa las tiradas manuales y realiza una acción que requiera un d20.
6. Cierra y vuelve a abrir el chat; comprueba que el estado y las tiradas pendientes se recuperan.

El resultado narrativo depende del modelo configurado en SillyTavern. Las reglas implementadas y las limitaciones del motor siguen siendo parciales: no interpretes una narración convincente como prueba de que cualquier regla de D&D ya está soportada.

## Limitaciones conocidas del MVP

- SillyTavern es la interfaz de juego; todavía no existe una interfaz web propia de Campaign Manager.
- El personaje creado por el script es una ficha mecánica mínima de demostración, no un personaje generado mediante las reglas completas de creación de D&D.
- No todas las acciones, clases, conjuros, condiciones ni consecuencias de D&D 5e 2014 están implementadas.
- La aplicación está diseñada para un único proceso local y una sola persona.
- El script no configura Ollama, el modelo narrativo ni SillyTavern.

Para incidencias, registra los identificadores de campaña/sesión, el mensaje enviado y el resultado observado. Usa una campaña desechable para las pruebas que cambien el mundo.
