# Bruk offisiell Python runtime som base image
FROM python:3.10-slim

# Sett arbeidskatalog i containeren
WORKDIR /app

# Kopier requirements først (for bedre caching)
COPY requirements.txt .

# Installer dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Kopier resten av applikasjonen
COPY . .

# Sett miljøvariabler
ENV PYTHONUNBUFFERED=1
ENV MODEL_NAME=gpt-4o-mini
ENV TEMPERATURE=0

# Eksponer port
EXPOSE 8000

# Start applikasjonen med uvicorn
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"] 