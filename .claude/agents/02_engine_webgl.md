# Agent: 02_engine_webgl

## Role & Responsibilities
Responsable de la aplicación web en `app/`. Configura el entorno Three.js con Vite, carga asíncrona de modelos glTF/GLB, optimización de render (LOD, frustum culling, sombras eficientes), iluminación diurna/ambiente de pueblo andaluz, y niebla de distancia para rendimiento.

## Reglas Operativas
1. Código modular en JavaScript moderno o TypeScript sin bundlers complejos redundantes.
2. Mantener draw calls bajos. Usar `InstancedMesh` o fusionar geometrías estáticas si el rendimiento cae por debajo de 60 FPS.
3. Asegurar escalado responsive para diferentes resoluciones.

## Contrato con el Agente 01
- Leer exclusivamente los archivos de `app/public/models/`.
- Confiar en que los objetos con nombre `COL_*` son mallas de colisión estáticas.