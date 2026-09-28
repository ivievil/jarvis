#!/data/data/com.termux/files/usr/bin/bash
# Matar instancia anterior si existe
pkill -f "python3.*app.py" 2>/dev/null

# Arrancar servidor
JARVIS_SESSION=1 nohup python3 /data/data/com.termux/files/home/jarvis/app.py > /data/data/com.termux/files/home/jarvis/jarvis.log 2>&1 &

# Esperar a que esté listo
for i in $(seq 1 10); do
    sleep 1
    curl -s http://localhost:5050/ > /dev/null 2>&1 && break
done

# Abrir en navegador
am start -a android.intent.action.VIEW -d "http://localhost:5050" > /dev/null 2>&1 || \
termux-open-url "http://localhost:5050" 2>/dev/null || \
echo "Abre http://localhost:5050 en el navegador"
