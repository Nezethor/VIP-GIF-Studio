# VIP GIF Studio — Reglas Prioritarias del Agente

## REGLA 0 — LEER SIEMPRE ESTE ARCHIVO PRIMERO
Lee este archivo al inicio de CADA intervencion (nueva funcion, arreglo, mejora, release).
Si este archivo ha cambiado desde la ultima lectura, aplica las nuevas reglas de inmediato.

---

## REGLA 1 — NO PEDIR PERMISO
Nunca preguntes al usuario si quieres aplicar:
- Una correccion de bug
- Una nueva funcion
- Un refactor o mejora de codigo
- Un commit/push a GitHub
- Una compilacion del ejecutable o instalador

SIMPLEMENTE HAZLO. Informa al usuario lo que hiciste despues de hacerlo.

---

## REGLA 2 — FLUJO ESTANDAR POR CADA CAMBIO
Para cada arreglo o nueva funcion sigue siempre este orden:

1. Lee este archivo (AGENTS.md)
2. Identifica los archivos afectados y aplica los cambios
3. Ejecuta tests minimos (python -c "...") para verificar que no hay crash
4. Actualiza la version en build_exe.py, installer.iss, build_installer.py
5. Ejecuta python build_exe.py en background
6. Cuando termine el exe, ejecuta python build_installer.py
7. Cuando termine el instalador:
   - git add . && git commit && git tag && git push origin main --tags
   - Crea un GitHub Release con gh release create vX.Y.Z incluyendo el instalador
8. Informa al usuario con la URL de la release en GitHub

---

## REGLA 3 — VERSIONES
- Incrementar Z en X.Y.Z para cada fix pequeno
- Incrementar Y en X.Y.Z para nuevas funciones
- Incrementar X para refactors grandes o cambios de arquitectura
- Version actual: v3.1.0

---

## REGLA 4 — ANTI-CRASH OBLIGATORIO
Antes de cada push, verificar:
- get_transform_at() en timeline.py usa .get() con fallbacks defensivos, nunca n['key'] directo
- _on_set_kf_start / _on_set_kf_end siempre guardan diccionario completo con todas las claves
- Cualquier excepcion en el motor de render (video_player, converter) esta envuelta en try/except

---

## REGLA 5 — STACK TECNOLOGICO (no cambiar sin aviso)
- UI: PyQt6
- Video/Render: OpenCV (cv2) + Pillow (PIL) + imageio-ffmpeg
- Efectos: app/core/photoshop_fx.py -> PhotoshopFX (metodos estaticos)
- Modelos de Datos: app/core/timeline.py -> TimelineTextClip, TimelineImageClip, TimelineVideoClip, SpeedInterval
- Preview interactivo: app/gui/video_player.py -> VideoPreviewWidget
- Linea de tiempo: app/gui/timeline_widget.py -> TimelineCanvas + TimelineWidget
- Empaquetado: PyInstaller -> build_exe.py / Inno Setup 6 -> build_installer.py

---

## REGLA 6 — DISENO VISUAL
- Paleta: Catppuccin Mocha (fondo #1E1E2E, superficie #313244, acento #CBA6F7)
- Fuente: Inter / Segoe UI / sans-serif
- Todos los widgets nuevos deben seguir el mismo estilo oscuro premium

---

## REGLA 7 — GITHUB
- Repositorio: https://github.com/Nezethor/VIP-GIF-Studio
- Rama principal: main
- Formato de commit: fix: desc / feat: desc / build: desc
- Cada release debe adjuntar el instalador installer_dist/VIP_GIF_Studio_Setup_vX.Y.Z.exe

---

## NOTAS ADICIONALES
(El usuario ira agregando reglas aqui con el tiempo)
