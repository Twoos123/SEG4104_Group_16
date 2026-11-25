# 1. Base Image: official lightweight Python runtime
FROM python:3.12-slim

# 2. Working Directory: internal container directory
WORKDIR /app

# 3. Dependencies: copy the manifest first so this layer is cached until requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Application Code & Startup Command
COPY . .
# Build the historical dataset, load it, and train the classifier at image build time
RUN python etl/generate_history.py && python etl/etl.py && python etl/train.py
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
