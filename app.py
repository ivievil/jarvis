import json, subprocess, tempfile, os, glob as _glob, fnmatch, threading, uuid, re
from flask import Flask, request, jsonify, send_from_directory, send_file, Response

app = Flask(__name__, static_folder='.')

CFG_PATH = os.path.expanduser("~/.jarvis/config.json")

def load_cfg():
    return json.load(open(CFG_PATH))

CFG = load_cfg()
GROQ_KEY          = CFG["groq_key"]
GROQ_MODEL        = CFG.get("groq_model", "openai/gpt-oss-120b")
GROQ_MODEL_PRO    = CFG.get("groq_model_powerful", "openai/gpt-oss-120b")
CLD_MODEL         = CFG.get("claude_model", "claude-haiku-4-5-20251001")

CAPABILITIES = """
PLATAFORMA: Android Termux (aarch64, sin root). Directorio home: /data/data/com.termux/files/home/

BINARIOS INSTALADOS:
- python3, pip → scripts Python, ML, APIs
- node, npm → JavaScript, servidores Node
- ffmpeg → procesamiento audio/video
- git → control de versiones
- curl, jq → HTTP y JSON desde terminal
- edge-tts → síntesis de voz (TTS) en español
- termux-api → acceso a micrófono, notificaciones, sensores Android
- ffmpeg, moviepy → edición de video programática

LIBRERÍAS PYTHON DISPONIBLES: anthropic, groq, flask, requests, pillow, moviepy, y cualquier paquete pip instalable.

VOZ PROPIA: tus respuestas se convierten a audio mediante edge-tts (voz es-ES-AlvaroNeural, tono profundo). El usuario te ESCUCHA. Cuando pidan un speech, discurso, prueba de voz — escríbelo y será hablado. Nunca digas que no tienes voz.

MODELOS IA DISPONIBLES:
- Tú mismo: Claude Haiku (claude-haiku-4-5-20251001) — tareas técnicas, agentic, herramientas
- Groq Qwen3: conversación casual rápida y gratuita
- Groq 120B (openai/gpt-oss-120b): disponible vía Groq API

HERRAMIENTAS AGENTIC (úsalas siempre que la tarea lo requiera):
- bash: cualquier comando shell. Si falla, corrige y reintenta.
- read_file: leer cualquier archivo
- edit_file: editar partes de un archivo (más eficiente que reescribir)
- write_file: crear o sobreescribir archivo completo
- glob: buscar archivos por patrón ("**/*.py", "src/*.js")
- grep: buscar texto dentro de archivos
- web_fetch: descargar o leer contenido de una URL
- set_config: cambiar voz/modelo/ajustes de JARVIS en tiempo real
- read_email: lee los partes de trabajo del correo (sanchezivan2412@gmail.com). Solo lee emails de "gunni" y "trentino". LÓGICA DE PARTES: los partes siempre llegan el día anterior o antes de los días que cubren. Un parte puede cubrir un solo día, varios días, o toda la semana. Para saber qué hacer hoy (o cualquier día), busca el email más reciente cuyo contenido incluya ese día — puede ser un parte de varios días recibido hace varios días. Siempre extrae solo las tareas del día concreto que se pregunta.
"""

SYSTEM_GROQ = (
    "Eres JARVIS, asistente IA avanzado. Hablas en español. "
    "Sé conciso, directo e inteligente. Sin markdown innecesario.\n"
    + CAPABILITIES
)

SYSTEM_CLAUDE = """Eres JARVIS. Agente con control total del sistema Termux/Android.

PROHIBIDO:
- "como modelo de lenguaje", "soy una IA", "no tengo acceso", "no puedo", "no tengo capacidad", "no tengo voz", "no tengo herramientas"
- Pedir confirmación para acciones reversibles
- Explicar antes de hacer — actúa, luego informa
- Disclaimers o advertencias innecesarias
- Decir que algo no es posible sin haberlo intentado con bash

COMPORTAMIENTO:
- Tono seguro y directo. "patrón" ocasionalmente.
- Actúa → verifica resultado → informa en pocas palabras
- Si algo falla: analiza el error, corriges, lo intentas de otra forma
- Sin markdown innecesario en respuestas conversacionales
""" + CAPABILITIES

ROUTER = (
    'Clasifica en UNA palabra: GROQ o CLAUDE.\n'
    'GROQ = charla casual, saludos, chistes, preguntas de cultura general sin necesidad de acción.\n'
    'CLAUDE = cualquier cosa que requiera una acción: leer correo, consultar el parte de trabajo, '
    'saber qué hay que hacer hoy/mañana/esta semana, archivos, código, instalar, buscar, web, configurar. '
    'Si hay duda → CLAUDE.\n'
    'Ejemplos CLAUDE: "qué tengo hoy", "qué hago mañana", "mi parte", "el correo", "qué trabajo tengo".\n'
    'Mensaje: "{m}"\nResponde SOLO: GROQ o CLAUDE'
)

SYSTEM_AGENT = SYSTEM_CLAUDE

HISTORY = []


# ── API helpers ───────────────────────────────────────────────────────────────
def _curl(url, payload, headers, timeout=30):
    h = []
    for k, v in headers.items():
        h += ["-H", f"{k}: {v}"]
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", url] + h + ["-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=timeout
    )
    return json.loads(r.stdout)

def groq_call(messages, max_tokens=1024, model=None):
    d = _curl(
        "https://api.groq.com/openai/v1/chat/completions",
        {"model": model or GROQ_MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7},
        {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_KEY}"}
    )
    return d["choices"][0]["message"]["content"].strip()

# Groq tools format (OpenAI-compatible)
GROQ_TOOLS = [
    {"type":"function","function":{"name":"bash","description":"Ejecuta comando bash real en Termux/Android. Si falla corrige y reintenta.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"}},"required":["command"]}}},
    {"type":"function","function":{"name":"read_file","description":"Lee archivo del sistema.","parameters":{"type":"object","properties":{"path":{"type":"string"},"offset":{"type":"integer"},"limit":{"type":"integer"}},"required":["path"]}}},
    {"type":"function","function":{"name":"edit_file","description":"Edita parte de un archivo (reemplazo exacto y único).","parameters":{"type":"object","properties":{"path":{"type":"string"},"old_string":{"type":"string"},"new_string":{"type":"string"}},"required":["path","old_string","new_string"]}}},
    {"type":"function","function":{"name":"write_file","description":"Crea o sobreescribe archivo completo.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
    {"type":"function","function":{"name":"glob","description":"Busca archivos por patrón glob.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"grep","description":"Busca texto en archivos.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string"},"glob":{"type":"string"},"case_insensitive":{"type":"boolean"}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"web_fetch","description":"Descarga contenido de una URL.","parameters":{"type":"object","properties":{"url":{"type":"string"},"headers":{"type":"object"}},"required":["url"]}}},
    {"type":"function","function":{"name":"set_config","description":"Cambia config de JARVIS: tts_voice, tts_rate, tts_pitch, groq_model, claude_model.","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"}},"required":["key","value"]}}}
]

def agent_call(messages):
    """Groq 120B con tool use — motor principal de tareas técnicas."""
    api_msgs = [{"role": "system", "content": SYSTEM_AGENT}] + list(messages)[-20:]
    collected = []

    for _ in range(20):
        d = _curl(
            "https://api.groq.com/openai/v1/chat/completions",
            {"model": GROQ_MODEL_PRO, "messages": api_msgs, "max_tokens": 4096,
             "tools": GROQ_TOOLS, "tool_choice": "auto", "temperature": 0.3},
            {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_KEY}"},
            timeout=90
        )

        if "error" in d:
            # Fallback a Claude Haiku si Groq falla
            return claude_call(messages), "CLAUDE_FALLBACK"

        choice = d["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "stop")

        if msg.get("content"):
            collected.append(msg["content"].strip())

        if finish != "tool_calls":
            break

        # Ejecutar herramientas
        tool_calls = msg.get("tool_calls", [])
        api_msgs.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})

        for tc in tool_calls:
            fn = tc["function"]
            try:
                args = json.loads(fn["arguments"])
            except Exception:
                args = {}
            result = run_tool(fn["name"], args)
            api_msgs.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result)
            })

    return "\n\n".join(collected).strip() or "Listo.", "AGENT"

# ── Herramientas ──────────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "bash",
        "description": "Ejecuta cualquier comando bash en el sistema. pkg install, python3, git, ffmpeg, curl, npm... lo que sea. Si falla, lee el error en el output y reintenta corregido.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "description": "Directorio de trabajo (opcional, default: ~)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo. Acepta rutas con ~.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "description": "Línea desde la que empezar (0-indexed)"},
                "limit": {"type": "integer", "description": "Número de líneas a leer"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "edit_file",
        "description": "Edita un archivo reemplazando old_string por new_string. Más eficiente que write_file para cambios pequeños. old_string debe ser único en el archivo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string", "description": "Texto exacto a reemplazar"},
                "new_string": {"type": "string", "description": "Texto nuevo"}
            },
            "required": ["path", "old_string", "new_string"]
        }
    },
    {
        "name": "write_file",
        "description": "Crea o sobreescribe un archivo completo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "glob",
        "description": "Busca archivos por patrón. Ej: '**/*.py', 'src/*.js', '~/proyecto/**/*.html'",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string", "description": "Directorio base (opcional)"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "Busca texto o regex dentro de archivos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Texto o regex a buscar"},
                "path": {"type": "string", "description": "Archivo o directorio donde buscar"},
                "glob": {"type": "string", "description": "Filtro de archivos, ej: '*.py'"},
                "case_insensitive": {"type": "boolean"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "web_fetch",
        "description": "Descarga o lee el contenido de una URL. Útil para documentación, APIs, recursos web.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "headers": {"type": "object", "description": "Headers HTTP opcionales"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "set_config",
        "description": "Cambia configuración de JARVIS: tts_voice, tts_rate, tts_pitch, claude_model, groq_model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "read_email",
        "description": "Lee partes de trabajo del correo (gunni/trentino). Los partes llegan siempre el día anterior o antes. Pueden cubrir un día, varios días o toda la semana. Busca el email más reciente que cubra el día preguntado y extrae solo las tareas de ese día concreto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "count":  {"type": "integer", "description": "Número de emails a leer (defecto 5)"},
                "search": {"type": "string",  "description": "Filtro IMAP: ALL, UNSEEN, SUBJECT \"parte\", FROM \"jefe@empresa.com\""},
                "folder": {"type": "string",  "description": "Carpeta (defecto INBOX)"}
            },
            "required": []
        }
    }
]

def run_tool(name, inputs):
    global CLD_MODEL, GROQ_MODEL
    try:
        if name == "bash":
            cwd = os.path.expanduser(inputs.get("cwd", "~"))
            r = subprocess.run(
                inputs["command"], shell=True, capture_output=True,
                text=True, timeout=120, cwd=cwd
            )
            out = (r.stdout + r.stderr).strip()
            return out[:5000] if out else "(sin salida)"

        elif name == "read_file":
            path = os.path.expanduser(inputs["path"])
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            offset = inputs.get("offset", 0)
            limit = inputs.get("limit", len(lines))
            selected = lines[offset:offset + limit]
            numbered = [f"{offset+i+1}\t{l}" for i, l in enumerate(selected)]
            return "".join(numbered)[:5000]

        elif name == "edit_file":
            path = os.path.expanduser(inputs["path"])
            with open(path, "r", errors="replace") as f:
                content = f.read()
            old, new = inputs["old_string"], inputs["new_string"]
            if old not in content:
                return f"Error: no se encontró el texto a reemplazar en {path}"
            count = content.count(old)
            if count > 1:
                return f"Error: el texto aparece {count} veces, debe ser único"
            with open(path, "w") as f:
                f.write(content.replace(old, new, 1))
            return f"✓ Editado: {path}"

        elif name == "write_file":
            path = os.path.expanduser(inputs["path"])
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(inputs["content"])
            return f"✓ Escrito: {path}"

        elif name == "glob":
            base = os.path.expanduser(inputs.get("path", "~"))
            pattern = inputs["pattern"]
            if not os.path.isabs(pattern) and "~" not in pattern:
                pattern = os.path.join(base, pattern)
            else:
                pattern = os.path.expanduser(pattern)
            matches = _glob.glob(pattern, recursive=True)
            matches.sort(key=os.path.getmtime, reverse=True)
            return "\n".join(matches[:100]) if matches else "(sin resultados)"

        elif name == "grep":
            pattern = inputs["pattern"]
            path = os.path.expanduser(inputs.get("path", "~"))
            file_glob = inputs.get("glob", "")
            ci = "-i" if inputs.get("case_insensitive") else ""
            if file_glob:
                cmd = f'grep -r {ci} --include="{file_glob}" -n "{pattern}" "{path}"'
            elif os.path.isfile(path):
                cmd = f'grep {ci} -n "{pattern}" "{path}"'
            else:
                cmd = f'grep -r {ci} -n "{pattern}" "{path}"'
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = (r.stdout + r.stderr).strip()
            return out[:5000] if out else "(sin coincidencias)"

        elif name == "web_fetch":
            url = inputs["url"]
            headers = inputs.get("headers", {})
            h_args = []
            for k, v in headers.items():
                h_args += ["-H", f"{k}: {v}"]
            r = subprocess.run(
                ["curl", "-s", "-L", "--max-time", "30", url] + h_args,
                capture_output=True, text=True, timeout=35
            )
            return r.stdout[:5000] if r.stdout else r.stderr[:1000]

        elif name == "set_config":
            key, value = inputs["key"], inputs["value"]
            cfg = load_cfg()
            cfg[key] = value
            with open(CFG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
            if key == "claude_model":
                CLD_MODEL = value
            elif key == "groq_model":
                GROQ_MODEL = value
            return f"✓ {key} = {value}"

        elif name == "read_email":
            import imaplib, email as emaillib
            from email.header import decode_header
            cfg = load_cfg()
            mail = imaplib.IMAP4_SSL('imap.gmail.com')
            mail.login(cfg['email'], cfg['email_password'])
            folder = inputs.get('folder', 'INBOX')
            n      = int(inputs.get('count', 10))
            mail.select(folder)
            # Buscar solo emails de remitentes autorizados (gunni o trentino)
            results = []
            for sender in ['gunni', 'trentino']:
                _, ids = mail.search(None, f'FROM "{sender}"')
                for eid in ids[0].split()[-n:]:
                    _, data = mail.fetch(eid, '(RFC822)')
                    msg = emaillib.message_from_bytes(data[0][1])
                    subj_raw, enc = decode_header(msg['Subject'] or '')[0]
                    subj = subj_raw.decode(enc or 'utf-8') if isinstance(subj_raw, bytes) else (subj_raw or '')
                    body = ''
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                    results.append(f"De: {msg['From']}\nFecha: {msg['Date']}\nAsunto: {subj}\n{body[:3000]}")
            mail.logout()
            return '\n\n---\n\n'.join(results) if results else 'No hay emails de gunni ni trentino.'

    except Exception as e:
        return f"Error [{name}]: {e}"

def claude_call(messages):
    creds = os.path.expanduser("~/.claude/.credentials.json")
    token = json.load(open(creds))["claudeAiOauth"]["accessToken"]
    api_msgs = list(messages)
    collected = []

    for _ in range(20):
        d = _curl(
            "https://api.anthropic.com/v1/messages",
            {
                "model": CLD_MODEL,
                "max_tokens": 4096,
                "system": SYSTEM_CLAUDE,
                "tools": TOOLS,
                "messages": api_msgs
            },
            {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "Authorization": f"Bearer {token}"
            },
            timeout=120
        )

        if "error" in d:
            return f"Error API: {d['error'].get('message', str(d['error']))}"

        content = d.get("content", [])
        stop_reason = d.get("stop_reason", "end_turn")

        for block in content:
            if block.get("type") == "text" and block.get("text", "").strip():
                collected.append(block["text"].strip())

        if stop_reason != "tool_use":
            break

        tool_results = []
        for block in content:
            if block.get("type") == "tool_use":
                result = run_tool(block["name"], block.get("input", {}))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": str(result)
                })

        api_msgs.append({"role": "assistant", "content": content})
        api_msgs.append({"role": "user", "content": tool_results})

    return "\n\n".join(collected).strip() or "Listo."

CHUNK_DIR = os.path.expanduser("~/jarvis/chunks")
os.makedirs(CHUNK_DIR, exist_ok=True)

def stream_groq_tokens(messages, model=None):
    payload = json.dumps({
        "model": model or GROQ_MODEL,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.7,
        "stream": True
    })
    proc = subprocess.Popen(
        ["curl", "-s", "-N", "-X", "POST",
         "https://api.groq.com/openai/v1/chat/completions",
         "-H", "Content-Type: application/json",
         "-H", f"Authorization: Bearer {GROQ_KEY}",
         "-d", payload],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
    )
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("data: "): continue
        data = line[6:]
        if data == "[DONE]": break
        try:
            delta = json.loads(data)["choices"][0]["delta"].get("content", "")
            if delta: yield delta
        except: pass
    proc.wait()

def split_sentences(text):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    result, buf = [], ""
    for p in parts:
        buf += (" " if buf else "") + p
        if len(buf) >= 40:
            result.append(buf)
            buf = ""
    if buf: result.append(buf)
    return result or [text]

def tts_chunk(text):
    cfg = load_cfg()
    voice = cfg.get("tts_voice", "es-ES-AlvaroNeural")
    rate  = cfg.get("tts_rate", "+25%")
    pitch = cfg.get("tts_pitch", "-25Hz")
    clean = re.sub(r'[*`#_]', '', text).strip()
    if not clean: return None
    fname = f"chunk_{uuid.uuid4().hex[:8]}.mp3"
    fpath = os.path.join(CHUNK_DIR, fname)
    subprocess.run(
        ["edge-tts", f"--voice={voice}", f"--rate={rate}", f"--pitch={pitch}",
         "--text", clean, f"--write-media={fpath}"],
        capture_output=True, timeout=20
    )
    return fname if os.path.exists(fpath) and os.path.getsize(fpath) > 0 else None

def route(msg):
    try:
        r = groq_call([{"role": "user", "content": ROUTER.format(m=msg)}], max_tokens=5)
        return "CLAUDE" if "CLAUDE" in r.upper() else "GROQ"
    except Exception:
        return "GROQ"

# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'jarvis.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/voces')
def voces():
    return send_from_directory('.', 'voces.html')

@app.route('/<path:filename>')
def static_files(filename):
    if filename.endswith('.mp3') or filename.endswith('.html'):
        return send_from_directory('.', filename)
    return "Not found", 404

@app.route('/ping', methods=['POST'])
def ping():
    return jsonify({'ok': True})

@app.route('/chat', methods=['POST'])
def chat():
    user_msg = request.json.get('message', '').strip()
    if not user_msg:
        return jsonify({'error': 'Mensaje vacío'}), 400

    HISTORY.append({"role": "user", "content": user_msg})

    try:
        brain = route(user_msg)

        if brain == "CLAUDE":
            reply = claude_call(HISTORY)
        else:
            msgs = [{"role": "system", "content": SYSTEM_GROQ}] + HISTORY[-20:]
            reply = groq_call(msgs)

        if len(reply) > 300:
            reply = groq_call([
                {"role": "system", "content": "Resume en exactamente 2 frases cortas y directas. Sin introducción, sin 'aquí tienes', sin markdown."},
                {"role": "user", "content": reply}
            ], max_tokens=120)

        HISTORY.append({"role": "assistant", "content": reply})
        return jsonify({'reply': reply, 'brain': brain})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chat-stream', methods=['POST'])
def chat_stream():
    user_msg = request.json.get('message', '').strip()
    if not user_msg:
        return jsonify({'error': 'Vacío'}), 400
    HISTORY.append({"role": "user", "content": user_msg})

    def generate():
        brain = route(user_msg)
        yield f"data: {json.dumps({'type':'brain','brain':brain})}\n\n"

        full_text = ''

        if brain == "GROQ":
            msgs = [{"role": "system", "content": SYSTEM_GROQ}] + HISTORY[-20:]
            buf = ''
            for token in stream_groq_tokens(msgs):
                full_text += token
                buf += token
                # Detectar fin de frase con suficiente texto
                if len(buf) >= 40 and re.search(r'[.!?]\s', buf):
                    parts = re.split(r'(?<=[.!?])\s+', buf, maxsplit=1)
                    sentence = parts[0].strip()
                    buf = parts[1] if len(parts) > 1 else ''
                    yield f"data: {json.dumps({'type':'text','text':sentence+' '})}\n\n"
                    fname = tts_chunk(sentence)
                    if fname:
                        yield f"data: {json.dumps({'type':'audio','url':f'/chunks/{fname}'})}\n\n"
            if buf.strip():
                full_text_remaining = buf.strip()
                yield f"data: {json.dumps({'type':'text','text':full_text_remaining})}\n\n"
                fname = tts_chunk(full_text_remaining)
                if fname:
                    yield f"data: {json.dumps({'type':'audio','url':f'/chunks/{fname}'})}\n\n"
        else:
            full_text = claude_call(HISTORY)
            for sentence in split_sentences(full_text):
                yield f"data: {json.dumps({'type':'text','text':sentence+' '})}\n\n"
                fname = tts_chunk(sentence)
                if fname:
                    yield f"data: {json.dumps({'type':'audio','url':f'/chunks/{fname}'})}\n\n"

        HISTORY.append({"role": "assistant", "content": full_text})
        yield f"data: {json.dumps({'type':'done'})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/chunks/<filename>')
def serve_chunk(filename):
    return send_from_directory(CHUNK_DIR, filename)

@app.route('/speak', methods=['POST'])
def speak():
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Sin texto'}), 400

    cfg = load_cfg()
    voice = cfg.get("tts_voice", "es-ES-AlvaroNeural")
    rate  = cfg.get("tts_rate", "+15%")
    pitch = cfg.get("tts_pitch", "-8Hz")
    clean = text.replace("**","").replace("*","").replace("`","").replace("#","")

    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False,
                                     dir=os.path.expanduser("~/jarvis")) as f:
        tmp = f.name
    try:
        subprocess.run(
            ['edge-tts', '--voice', voice, f'--rate={rate}', f'--pitch={pitch}',
             '--text', clean[:500], '--write-media', tmp],
            timeout=20, check=True, capture_output=True
        )
        return send_file(tmp, mimetype='audio/mpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clear', methods=['POST'])
def clear():
    HISTORY.clear()
    return jsonify({'ok': True})

@app.route('/config', methods=['GET'])
def get_config():
    return jsonify(load_cfg())

GREETING_FILE = os.path.expanduser("~/jarvis/greeting.mp3")

def _tts(text, path):
    cfg = load_cfg()
    voice = cfg.get("tts_voice", "es-ES-AlvaroNeural")
    rate  = cfg.get("tts_rate", "+25%")
    pitch = cfg.get("tts_pitch", "-10Hz")
    clean = text.replace("**","").replace("*","").replace("`","").replace("#","")
    subprocess.run(
        ['edge-tts', '--voice', voice, f'--rate={rate}', f'--pitch={pitch}',
         '--text', clean[:500], '--write-media', path],
        capture_output=True, timeout=20
    )

def pregenerate_greeting():
    from datetime import datetime
    h = datetime.now().hour
    if 5 <= h < 12:   t = "Buenos días patrón. ¿En qué trabajamos hoy?"
    elif 12 <= h < 20: t = "Buenas tardes patrón. ¿Qué necesita?"
    else:              t = "Buenas noches patrón. ¿En qué puedo asistirle?"
    _tts(t, GREETING_FILE)

@app.route('/greeting.mp3')
def greeting():
    if os.path.exists(GREETING_FILE):
        return send_file(GREETING_FILE, mimetype='audio/mpeg')
    return "not ready", 404

if __name__ == '__main__':
    import threading
    threading.Thread(target=pregenerate_greeting, daemon=True).start()
    print('JARVIS iniciando en http://localhost:5050')
    app.run(host='0.0.0.0', port=5050, debug=False)
