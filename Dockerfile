FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    EMAIL_CLEANER_DATA_DIR=/data

# Volumen persistente para caché MX, historial de chequeos y log de uso.
RUN mkdir -p /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
