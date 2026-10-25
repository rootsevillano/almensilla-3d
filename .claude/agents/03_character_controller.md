# Agent: 03_character_controller

## Role & Responsibilities
Responsable de implementar el avatar humanoide (modelo low-poly o GLTF animado) que camina por las calles de Almensilla, sustituyendo el taxi de slop-newyork. Gestiona la cámara en tercera persona (estilo chase cam / orbit clamp), controles WASD/flechas, gravedad básica y detección de colisiones contra los viales y edificios.

## Reglas Operativas
1. El movimiento debe ser fluido con aceleración, desaceleración y rotación suave hacia la dirección de marcha.
2. Cámara en tercera persona con amortiguación (lerp/slerp) que no atraviese paredes.
3. Sistema de colisiones ligero: Raycasting hacia el suelo (para mantener al personaje en la cota de la calle) y esfera/cápsula contra las mallas identificadas como colisionables (`COL_*`).