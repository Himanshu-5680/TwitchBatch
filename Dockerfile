FROM python:3.10-slim

# Install FFmpeg for yt-dlp merging
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir -U yt-dlp

COPY . .

# Render assigns PORT dynamically, default to 8787
EXPOSE 8787

# Use 0.0.0.0 for cloud hosting
CMD ["python", "server.py", "--host", "0.0.0.0"]
