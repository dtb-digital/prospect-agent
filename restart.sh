#!/bin/bash

# Funksjon for å frigjøre port 8000
free_port() {
    echo "Prøver å frigjøre port 8000..."
    if lsof -ti :8000 > /dev/null 2>&1; then
        kill -9 $(lsof -ti :8000)
        echo "Port 8000 frigjort"
    else
        echo "Port 8000 er allerede ledig"
    fi
}

echo "Stopper eksisterende API prosess..."
pkill -f "uvicorn api:app"

# Vent til porten er frigjort
echo "Venter på at port 8000 skal frigjøres..."
while lsof -i :8000 > /dev/null 2>&1; do
    echo "Port 8000 er fortsatt i bruk, prøver å frigjøre..."
    free_port
    sleep 1
done

# Litt ekstra ventetid for å være sikker
sleep 1

echo "Starter API..."
uvicorn api:app --reload &

echo "API restartet!"