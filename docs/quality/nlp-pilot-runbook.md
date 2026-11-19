## Ejecución integrada desde PowerShell

Desde la raíz del repositorio:

    .\scripts\run-ollama-tests.ps1

Este runner se centra en validaciones que GitHub Actions no puede realizar en tu equipo: prepara el entorno Python con los grupos `test` y `nlp-pilot`, comprueba/prepara los modelos españoles Stanza, ejecuta el benchmark NLP offline y lanza la suite `real_llm` contra tu instancia local de Ollama. No repite pytest determinista, cobertura, Ruff, Pyright ni tests JavaScript: esos gates siguen siendo responsabilidad de CI en GitHub.

Para incluir también las llamadas Ollama adicionales del A/B Intent frente a Intent + Stanza:

    .\scripts\run-ollama-tests.ps1 -RunNlpAb

Este A/B es opt-in porque hace llamadas adicionales al modelo; el runner activa el guard `CAMPAIGN_MANAGER_NLP_PILOT_LIVE` solo durante esa fase y restaura las variables de entorno al terminar. Para omitir por completo la descarga de modelos Stanza usa `-SkipNlpModelDownload`; si los modelos no están instalados, la fase se marcará como fallida.

Cada ejecución crea `artifacts/quality-runs/<fecha>-<commit>/` con `summary.md`, `summary.json`, logs por fase, JUnit de las pruebas Ollama, informes Ollama y JSON NLP. El script devuelve código 0 solo cuando todas las fases locales solicitadas terminan correctamente. Puedes omitir fases con `-SkipOllamaTests` o `-SkipNlpPilot`; por defecto se ejecuta el flujo local completo (salvo el A/B adicional).

Requisitos locales: Git, Python 3.12+ y Ollama iniciado con los modelos configurados en `.env.ollama` ya instalados. No hace falta Node.js ni npm para este runner. Stanza se descarga automáticamente solo si el piloto está habilitado y faltan sus modelos; la descarga queda registrada como una fase propia.

# PR #272 — NLP pilot runbook

Este documento describe la ejecución reproducible del experimento opcional. No se importa desde el runtime de producción, no inicia descargas en startup y no hace llamadas a Ollama durante la evaluación offline.

## 1. Instalar la dependencia opcional

Desde la raíz del repositorio:

    python -m pip install --group nlp-pilot

El grupo instala Stanza 1.15.1. No forma parte de project.dependencies ni de los grupos test/lint/typing. La importación del paquete services.nlp_pilot no importa stanza; solo StanzaParserAdapter() carga el paquete opcional.

## 2. Descargar modelos de forma explícita

PowerShell:

    python -m scripts.download_nlp_pilot_models --model-dir "$HOME\stanza_resources"

Bash:

    python -m scripts.download_nlp_pilot_models --model-dir "$HOME/stanza_resources"

El helper descarga para español los procesadores tokenize, mwt, pos, lemma y depparse. La ubicación se elige explícitamente; no se descarga nada al arrancar Campaign Manager. Si la máquina está aislada, copia el directorio de recursos Stanza previamente descargado y usa la misma ruta con --model-dir.

## 3. Ejecutar el benchmark offline

PowerShell:

    python -m scripts.run_nlp_pilot --split both --model-dir "$HOME\stanza_resources" --output artifacts\nlp-pilot.json

Bash:

    python -m scripts.run_nlp_pilot --split both --model-dir "$HOME/stanza_resources" --output artifacts/nlp-pilot.json

Opciones: --split development, holdout o both; --limit-per-split N permite un smoke run pequeño. El runner no llama al LLM. El JSON contiene cobertura de parseo, cobertura de lemma/UPOS/dependency, palabras/frases totales, bytes del directorio local, latencias CPU/wall P50/P95, tipos de error y métricas de cues con denominadores explícitos.

Los probes actuales solo miden presencia binaria de señales de negación y condicional cuando el corpus ya tiene polaridad/modalidad gold suficiente. El baseline léxico y Stanza se reportan por separado. Un parser que falla no se registra como falso negativo: el caso se contabiliza como parser_unavailable. Los resultados de cues no son exactitud semántica por paso, actor ni action frame.

## 4. Ejecutar la comparación A/B con Ollama (opt-in)

Solo después de comprobar que el benchmark offline funciona y que Ollama está disponible. Esta prueba hace dos llamadas de Intent por escenario y tres repeticiones para cada escenario crítico. No forma parte de CI determinista.

PowerShell:

    $env:CAMPAIGN_MANAGER_NLP_PILOT_LIVE = "1"
    $env:CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR = "$HOME\stanza_resources"
    $env:CAMPAIGN_MANAGER_NLP_PILOT_REPORT_PATH = "artifacts\nlp-pilot-ab.json"
    # Configura el mismo modelo, digest, think, timeout y base URL usados en el baseline.
    $env:CAMPAIGN_MANAGER_REAL_LLM_MODEL = "gemma4:26b"
    python -m pytest tests/test_real_llm_nlp_pilot.py -m "real_llm and nlp_pilot" -q

Bash:

    CAMPAIGN_MANAGER_NLP_PILOT_LIVE=1 \
    CAMPAIGN_MANAGER_NLP_PILOT_MODEL_DIR="$HOME/stanza_resources" \
    CAMPAIGN_MANAGER_NLP_PILOT_REPORT_PATH=artifacts/nlp-pilot-ab.json \
    CAMPAIGN_MANAGER_REAL_LLM_MODEL=gemma4:26b \
    python -m pytest tests/test_real_llm_nlp_pilot.py -m "real_llm and nlp_pilot" -q

El test compara el Intent actual con el mismo Intent al que un provider decorator de tests añade hints Stanza no confiables. Ambos usan el mismo provider/model/configuración/schema; el orden de llamada se alterna por escenario para reducir el sesgo sistemático de warm-up. Las métricas y eventos de uso se separan por variante. El gold held-out no se añade al prompt.

Variables comunes opcionales para fijar la corrida: CAMPAIGN_MANAGER_REAL_LLM_BASE_URL, CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT y CAMPAIGN_MANAGER_REAL_LLM_THINK. Registra también el digest del modelo, versión de Ollama, revisión Git y hardware.

## 5. Privacidad y límites

- Los informes no guardan utterances, prompts, completions, strings de mención, nombres de entidades, tokens crudos ni lemas.
- Los informes contienen agregados por split/familia, metadatos allowlisted, denominadores, latencia y tipos de error.
- Los offsets se aceptan solo cuando el substring exacto de la entrada coincide con el token Stanza; no se reconstruyen mediante búsqueda aproximada.
- Parser hints solo expresan estructura lingüística no confiable. No asignan identidad canónica, visibilidad, permisos, actor autorizado, outcome ni operaciones.
- El provider decorator solo lo importa el test A/B; no se conecta a la fábrica de providers ni al pipeline de producción.
- La ejecución live no se considera aceptación hasta revisar métricas por familia, llamadas, latencias y fallos. No se modifica gold para convertir un resultado rojo en verde.

## 6. Decisión de dependencia

Stanza se mantiene como herramienta opcional del piloto. No debe promoverse a dependencia runtime por el solo hecho de que el adaptador o los tests pasen. Hace falta evidencia de mejora neta frente al baseline y una evaluación de memoria, CPU, distribución offline, licencia y coste operativo. La licencia de la biblioteca y la licencia de cada modelo deben revisarse por separado.

spaCy no se añade en esta fase: la licencia de la biblioteca no implica la misma licencia para su modelo español.

## 7. CI determinista

Los tests fake-adapter se ejecutan con la suite normal sin instalar Stanza ni descargar modelos. El test A/B lleva los marcadores real_llm y nlp_pilot y queda excluido por el filtro CI habitual: python -m pytest -m "not real_llm".