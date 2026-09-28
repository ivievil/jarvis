# JARVIS — Contexto y estado del proyecto

**Fecha:** 28 septiembre 2025  
**Usuario:** ivievil  
**Plataforma:** Android Termux (aarch64, sin root)

---

## Qué es JARVIS

Asistente IA personal tipo Iron Man, accesible como PWA (app instalable) desde el móvil. Corre en Flask localmente en `localhost:5050`. Tiene voz propia y capacidad agentic completa sobre el sistema Android/Termux.

---

## Arquitectura

```
jarvis/
├── app.py          ← Backend Flask (cerebro completo)
├── jarvis.html     ← Frontend PWA (interfaz visual)
├── manifest.json   ← PWA manifest (instalable en home screen)
├── start.sh        ← Lanzador: arranca servidor + abre navegador
└── CONTEXTO.md     ← Este archivo
~/.jarvis/
└── config.json     ← Configuración persistente (voz, modelos, keys)
```

---

## Cómo arrancarlo

```bash
bash ~/jarvis/start.sh
```

Esto mata instancias previas, arranca `app.py` y abre el navegador automáticamente.

O desde Termux directamente:
```bash
JARVIS_SESSION=1 python3 ~/jarvis/app.py &
```

---

## Routing de modelos (cómo JARVIS elige)

| Tipo de tarea | Modelo usado |
|---------------|-------------|
| Charla casual, saludos, preguntas generales | Groq Qwen3 (qwen/qwen3.8-27b) — gratis, rápido |
| Todo técnico: código, archivos, bash, instalar, analizar | Claude Haiku (claude-haiku-4-5-20251001) — vía OAuth |

El router clasifica cada mensaje antes de enviarlo. En caso de duda → Claude.

**⚠️ IMPORTANTE: Sonnet 4.6 NO funciona** vía el token OAuth de Claude Code.  
Devuelve `rate_limit_error`. Solo Haiku está disponible vía API directa.  
Claude Code usa Sonnet internamente por infraestructura propia de Anthropic, no replicable desde fuera.

---

## Herramientas agentic disponibles en JARVIS

JARVIS puede ejecutar todo esto en respuesta a peticiones:

- `bash` — cualquier comando shell en Termux
- `read_file` — leer archivos
- `edit_file` — editar partes de un archivo (sin reescribirlo completo)
- `write_file` — crear/sobreescribir archivos
- `glob` — buscar archivos por patrón
- `grep` — buscar texto dentro de archivos
- `web_fetch` — descargar contenido de URL
- `set_config` — cambiar voz/modelo de JARVIS en tiempo real

---

## Voz

- **Motor:** edge-tts
- **Voz:** `es-ES-AlvaroNeural` (elegida por el usuario entre 6 opciones)
- **Rate:** `+25%` (velocidad — se probaron varias, esta fue la elegida)
- **Pitch:** `-25Hz` (tono profundo — se probaron -15, -20, -25, -30Hz; ganó -25)
- **⚠️ edge-tts con valores negativos:** SIEMPRE usar formato `--pitch=-25Hz` (con `=`), nunca `--pitch -25Hz` (con espacio) — el guión se interpreta como nuevo flag y falla con exit code 2

Saludo de bienvenida pre-generado al arrancar el servidor (`greeting.mp3`) para eliminar lag de audio en el primer mensaje.

---

## Auto-shutdown (batería)

El servidor se apaga solo cuando cierras JARVIS:
- La web envía un ping cada 30 segundos mientras está abierta (`/ping` endpoint)
- Si 90 segundos sin pings → `os._exit(0)`
- Al volver a abrir JARVIS, ejecutar `start.sh` para rearrancar

---

## Configuración (`~/.jarvis/config.json`)

```json
{
  "groq_key": "gsk_...",
  "groq_model": "qwen/qwen3.8-27b",
  "groq_model_powerful": "openai/gpt-oss-120b",
  "claude_model": "claude-haiku-4-5-20251001",
  "tts_voice": "es-ES-AlvaroNeural",
  "tts_rate": "+25%",
  "tts_pitch": "-25Hz"
}
```

El archivo de config NO está en el repo (tiene la API key). Hay que crearlo manualmente en `~/.jarvis/config.json`.

---

## Comportamiento / personalidad

- JARVIS llama al usuario **"patrón"**
- Tono seguro, directo, sin disclaimers
- **PROHIBIDO** que diga: "como modelo de lenguaje", "no puedo", "no tengo acceso", "no tengo voz", "no tengo herramientas"
- Actúa → verifica → informa. Nunca pide confirmación para acciones reversibles
- Tiene voz: cada respuesta escrita se convierte a audio (edge-tts). Cuando le pidan un speech, lo escribe y se escucha

---

## Pendiente / próximas mejoras

- [ ] Routing 3 niveles: Groq casual / Groq 120B razonamiento / Haiku agentic con tools
- [ ] Termux:Widget shortcut para lanzar JARVIS con un toque
- [ ] Investigar si Sonnet 4.6 puede habilitarse por otra vía (API key propia, si el usuario la consigue)

---

## Errores conocidos y sus soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `edge-tts exit code 2` con valores negativos | El `-` del valor se parsea como flag nuevo | Usar `--pitch=-25Hz` con `=`, nunca con espacio |
| JARVIS dice "no tengo voz" | Haiku no sabe que sus respuestas se convierten a audio | Añadir `TIENES VOZ` al system prompt |
| `rate_limit_error` en Sonnet 4.6 | Token OAuth solo permite Haiku | Usar Haiku como modelo técnico |
| `jarvis_tui.py` consumiendo 74% CPU | Proceso no terminado correctamente | `pkill -f jarvis_tui.py` |
| Servidor no arranca en background con `&>/tmp/` | `/tmp` sin permisos en Termux | Usar `~/jarvis/jarvis.log` |
| Autoplay bloqueado en navegador | Los navegadores bloquean audio sin gesto del usuario | Boot screen que requiere tap antes de reproducir |

---

## Contexto del sistema (Termux)

- **OS:** Android aarch64, sin root
- **Shell:** bash, `~/.bashrc` auto-lanza `claude --continue` salvo `JARVIS_SESSION=1`
- **Binarios clave:** python3, node, ffmpeg, git, curl, jq, edge-tts, termux-api
- **Alias:**
  - `jarvis` → lanza jarvis.py (TUI, obsoleto)
  - `jv` → lanza jarvis_voice.py (obsoleto)
  - Usar `start.sh` para la versión web actual
