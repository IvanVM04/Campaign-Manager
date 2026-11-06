# Quickstart: jugar la primera aventura de Campaign Manager

Esta guía prepara una campaña local con una aventura inicial breve. La interfaz de juego sigue siendo SillyTavern; todavía no existe una aplicación web independiente.

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

## 3. Crear la aventura

En otra terminal, desde la raíz del repositorio:

```bash
python scripts/bootstrap_demo.py
```

Opcionalmente, personaliza los nombres:

```bash
python scripts/bootstrap_demo.py --campaign-name "Mi primera aventura" --character-name "Kael"
```

El script crea una campaña D&D 5e 2014, la sesión **Las campanas de Puenteviejo**, un personaje de prueba de nivel 1 y seis entidades iniciales persistentes (Mara, Bram, Nilo y tres localizaciones). Selecciona automáticamente la sesión y el personaje como activos e imprime los identificadores. La creación de entidades es idempotente: repetir la petición no duplica los nombres existentes.

La aventura comienza en la Posada del Camino. El correo Nilo ha desaparecido; la posadera Mara y el carretero Bram pueden aportar información. Hay pistas que conducen al viejo puente y a una cámara de mantenimiento. La aventura admite conversación, investigación, pruebas y soluciones improvisadas; no exige entrar en combate.

**Cada ejecución crea una campaña nueva.** No borra ni modifica campañas existentes. Si el proceso falla a mitad, revisa la lista de campañas antes de volver a ejecutarlo para evitar dejar otra campaña de prueba incompleta.

## 4. Conectar SillyTavern

1. Instala la extensión local incluida en `integrations/sillytavern` siguiendo el procedimiento de extensiones de tu instalación de SillyTavern.
2. Activa Campaign Manager en los ajustes de la extensión.
3. Configura el backend como `http://127.0.0.1:8765`.
4. Introduce el **Campaign ID** que imprimió el script.
5. Mantén inicialmente el modo de dados automático; puedes probar el modo manual después.
6. Pulsa **Test connection**: el estado debe mostrar `Ready` junto al nombre de campaña, sesión y clase/nivel del personaje. Si aparece `setup is incomplete`, revisa la campaña activa, la sesión seleccionada y el personaje activo.

La extensión solicita al backend la resolución de la acción antes de que SillyTavern genere la narración. Si el backend solicita una aclaración o una tirada manual, sigue la indicación del modelo y responde en el chat.

## 5. Jugar una primera sesión

Prueba estas acciones de una en una, adaptándolas a lo que vaya ocurriendo:

1. **Hablar:** «Me acerco a Mara y le pregunto cuándo vio a Nilo por última vez».
2. **Investigar:** «Examino la bolsa de viaje que quedó en la posada buscando algo que me indique adónde iba».
3. **Seguir una pista:** «Voy al puente y examino el barro y las piedras alrededor».
4. **Resolver un obstáculo:** «Busco una forma segura de bajar a la cámara sin romper más la escalera».
5. **Ayudar:** «Intento liberar a Nilo sin ponerlo en peligro».

No tienes que seguir este orden ni usar estas soluciones. Puedes negociar con los PNJ, buscar otras pistas o proponer un plan distinto. El DM debe pedir aclaraciones cuando falte información esencial y el motor debe resolver las pruebas inciertas que correspondan.

### Comprobaciones durante la partida

- Consulta `GET /world` al iniciar: deben existir Mara, Bram, Nilo, Posada del Camino, Puenteviejo y Viejo puente como entidades persistentes.
- Después de hablar con un PNJ, consulta `GET /world` y comprueba si se ha registrado un evento relevante.
- Después de descubrir una pista, comprueba que el hecho no contradice lo ya establecido y que queda reflejado en el contexto de turnos posteriores.
- Repite una consulta sobre algo descubierto y comprueba que el DM conserva la continuidad.
- Reinicia SillyTavern o vuelve a abrir el chat y verifica que se recupera el estado desde el backend.
- Prueba una acción ambigua para comprobar el flujo de aclaración.
- Activa las tiradas manuales y realiza una acción que requiera un d20.

El resultado narrativo depende del modelo configurado en SillyTavern/Ollama. Las reglas implementadas y las limitaciones del motor siguen siendo parciales: no interpretes una narración convincente como prueba de que cualquier regla de D&D ya está soportada.

## Limitaciones conocidas del MVP

- SillyTavern es la interfaz de juego; todavía no existe una interfaz web propia de Campaign Manager.
- El personaje creado por el script es una ficha mecánica mínima de demostración, no un personaje generado mediante las reglas completas de creación de D&D.
- El escenario se entrega como contexto de campaña y sesión; los PNJ y pistas se incorporan al estado persistente a medida que se descubren y registran durante el juego.
- No todas las acciones, clases, conjuros, condiciones ni consecuencias de D&D 5e 2014 están implementadas.
- La aplicación está diseñada para un único proceso local y una sola persona.
- El script no configura Ollama, el modelo narrativo ni SillyTavern.
- La prueba de conexión valida que exista una campaña, sesión y personaje activos, además de contexto recuperable; que el servidor responda por sí solo no significa que la partida esté lista.

Para incidencias, registra los identificadores de campaña/sesión, el mensaje enviado y el resultado observado. Usa una campaña desechable para las pruebas que cambien el mundo.
