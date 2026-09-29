# JARVIS — Contexto y estado del proyecto

**Última actualización:** 29 septiembre 2026
**Usuario:** ivievil / patrón
**Plataforma:** Android Termux (aarch64, sin root)

---

## Qué es JARVIS

Asistente IA personal tipo Iron Man, accesible como PWA desde el móvil en `localhost:5050`. Tiene voz propia (edge-tts) y capacidad agentic completa sobre el sistema Android/Termux. Llama al usuario **"patrón"**.

---

## Arquitectura

```
jarvis/
├── app.py          ← Backend Flask (cerebro completo)
├── jarvis.html     ← Frontend PWA (interfaz visual)
├── manifest.json   ← PWA manifest (instalable en home screen)
├── start.sh        ← Lanzador manual si el servidor no corre
└── CONTEXTO.md     ← Este archivo

~/.jarvis/config.json  ← Configuración persistente (NO en git — tiene API key)
~/.bashrc              ← Auto-arranca app.py si no está corriendo al abrir Termux
```

---

## Cómo arranca JARVIS

El servidor corre **siempre en background** (0.6% CPU idle, sin impacto en batería).  
Se inicia automáticamente al abrir Termux gracias a esta línea en `~/.bashrc`:

```bash
pgrep -f "python3.*app.py" > /dev/null || JARVIS_SESSION=1 nohup python3 ~/jarvis/app.py > ~/jarvis/jarvis.log 2>&1 &
```

Si por algún motivo no corre: `bash ~/jarvis/start.sh`

Para usarlo: abrir `http://localhost:5050` en el navegador (o el icono PWA si está instalado).

---

## Consumo real medido

| Estado | CPU | RAM |
|--------|-----|-----|
| Reposo estable | ~0.6% | 26 MB |
| Durante uso (chat/voz) | ~0.5% | 26 MB |
| Tarea técnica (bash+API) | ~0.5% | 26 MB |

El 74% de CPU anterior era `jarvis_tui.py` (eliminado). Flask idle es negligible.

---

## Routing de modelos

| Tipo de tarea | Modelo |
|---------------|--------|
| Charla casual, saludos, preguntas generales | Groq Qwen3 (qwen/qwen3.8-27b) |
| Todo técnico: código, archivos, bash, instalar | Claude Haiku (claude-haiku-4-5-20251001) |

**⚠️ Sonnet 4.6 NO funciona** vía OAuth — devuelve `rate_limit_error`.  
Solo Haiku está disponible vía API directa. Claude Code usa Sonnet por infraestructura interna de Anthropic no replicable desde fuera.

---

## Herramientas agentic

- `bash` — cualquier comando shell
- `read_file` — leer archivos
- `edit_file` — editar partes de archivo
- `write_file` — crear/sobreescribir archivos
- `glob` — buscar archivos por patrón
- `grep` — buscar texto en archivos
- `web_fetch` — descargar contenido de URL
- `set_config` — cambiar voz/modelo en tiempo real

---

## Voz

- **Motor:** edge-tts
- **Voz:** `es-ES-AlvaroNeural`
- **Rate:** `+25%` | **Pitch:** `-25Hz`
- **⚠️ Formato obligatorio:** `--pitch=-25Hz` con `=`, nunca con espacio (el `-` se parsea como flag)
- Saludo pre-generado al arrancar (`greeting.mp3`) para eliminar lag

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

---

## Comportamiento / personalidad

- Llama al usuario **"patrón"**
- Tono seguro, directo, sin disclaimers
- **PROHIBIDO:** "como modelo de lenguaje", "no puedo", "no tengo acceso", "no tengo voz", "no tengo herramientas"
- Sabe que tiene voz: cada respuesta escrita se convierte a audio
- Actúa → verifica → informa. Sin confirmaciones para acciones reversibles

---

## Otros repos del usuario

| Repo | Contenido |
|------|-----------|
| `ivievil/obsidian-vault` | Segundo cerebro (PARA + Zettelkasten). YouTube, n8n, Grimmora, Pureign. Leer `_CLAUDE.md` antes de tocar nada. |
| `ivievil/AUTOMATIZACION` | Pipeline generación assets Grimmora (SDXL + ComfyUI), plantillas creature boards, afiliados |
| `ivievil/GrimmoraUNITY` | Proyecto juego |
| `ivievil/Grimmoria` | Proyecto juego |

**Workflow con repos:** se clonan solo cuando se va a trabajar en ellos, no de forma permanente.

---

## Pendiente

- [ ] Routing 3 niveles: Groq casual / Groq 120B razonamiento / Haiku agentic con tools
- [ ] Investigar si Sonnet 4.6 puede habilitarse (API key propia de pago)

---

## Errores conocidos y soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `edge-tts exit code 2` valores negativos | `-` parsea como flag | Usar `--pitch=-25Hz` con `=` |
| JARVIS dice "no tengo voz" | Haiku no sabe que sus respuestas se vocalizan | `TIENES VOZ` en system prompt |
| `rate_limit_error` Sonnet 4.6 | Token OAuth solo permite Haiku | Usar Haiku |
| Servidor no arranca con `&>/tmp/` | `/tmp` sin permisos en Termux | Usar `~/jarvis/jarvis.log` |
| Autoplay bloqueado en navegador | Sin gesto del usuario | Boot screen con tap obligatorio |
| `jarvis_tui.py` 74% CPU | Proceso zombie | `pkill -f jarvis_tui.py` (ya eliminado) |
