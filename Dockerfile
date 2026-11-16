FROM python:3.12-slim
WORKDIR /srv/smartintake
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Build the historical dataset, load it, and train the classifier at image build time
RUN python etl/generate_history.py && python etl/etl.py && python etl/train.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
