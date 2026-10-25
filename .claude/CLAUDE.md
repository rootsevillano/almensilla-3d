# Almensilla 3D - Harness Engineering Protocol

## 1. Core Identity & Objective
Este repositorio contiene el desarrollo de un visor interactivo WebGL (Three.js/Vite) que reproduce el término municipal y casco de Almensilla a escala 3D navegable a pie por un personaje en tercera persona (inspirado en slop-newyork).
El sistema utiliza Claude Code operando bajo un arnés estricto de agentes especializados y memoria persistente.

## 2. Reglas Cardinales del Harness
1. **Evidencia empírica sobre suposiciones:** Ningún script de parsing o conversión se dará por finalizado sin haber inspeccionado previamente la estructura interna real de los ZIPs de Catastro (AD, BU, CP) y del archivo `.osm`.
2. **Memoria obligatoria:** Al finalizar cualquier tarea o sesión, se debe actualizar obligatoriamente `.claude/MEMORY.md` reflejando el estado actual, decisiones y bloqueos.
3. **Aislamiento de agentes:** Cada tarea debe ejecutarse asumiendo el rol y las restricciones descritas en `.claude/agents/*.md`.
4. **Respeto de contratos:** Ningún agente puede modificar archivos fuera de su dominio sin validar los contratos definidos en `tests/contracts/`.

## 3. Protocolo de Ejecución de Tareas
Para cada intervención en Claude Code:
1. Leer `.claude/MEMORY.md` para recuperar contexto de sesión.
2. Identificar el agente responsable (`01_gis_pipeline`, `02_engine_webgl`, `03_character_controller`, `04_qa_benchmarking`).
3. Ejecutar las herramientas de inspección o tests del agente.
4. Aplicar cambios mínimos y necesarios.
5. Ejecutar validación de QA.
6. Actualizar `.claude/MEMORY.md`.

## 4. Stack Técnico Base
- **GIS / Pipeline:** Python 3.10+ (geopandas, shapely, osmnx/xml.etree, trimesh/pygltflib o script Blender headless).
- **Frontend / Engine:** Vite + Vanilla Three.js (ESM), glTFLoader, OrbitControls / PointerLock / Custom Third-Person Controller.
- **Entorno Host:** Windows 11 (PowerShell / Git Bash).