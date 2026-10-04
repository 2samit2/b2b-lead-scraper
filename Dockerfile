FROM python:3.12-slim

WORKDIR /app

# Зависимости ставим отдельным слоем для кэширования.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

RUN mkdir -p output logs

# Небезопасный доступ в сеть не требуется по умолчанию:
# --demo полностью офлайн, реальный режим использует публичные API.
ENTRYPOINT ["python", "main.py"]
CMD ["--demo", "--enrich"]