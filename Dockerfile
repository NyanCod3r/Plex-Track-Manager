FROM python:3.12.4-alpine3.19

ARG RELEASE_VERSION
ENV RELEASE_VERSION=${RELEASE_VERSION}

ENV PLEX_URL ""
ENV PLEX_TOKEN ""
ENV MUSIC_PATH ""
ENV LOG_LEVEL ""
ENV DOWNLOAD_DELAY ""
ENV SECONDS_TO_WAIT ""
ENV PREFER_FLAC ""
ENV LASTFM_API_KEY ""
ENV LASTFM_API_SECRET ""
ENV LASTFM_USERNAME ""
ENV LASTFM_PASSWORD ""
ENV MAX_DISCOVER_TRACKS ""
ENV MAX_RADAR_TRACKS ""
ENV RADAR_DAYS_BACK ""
ENV RECOMMENDATION_COOLDOWN_DAYS ""
ENV SYNC_FULL_HISTORY ""
ENV SYNC_STATE_FILE ""

WORKDIR /app

# Copy all project files into the container
COPY . .

# Install dependencies
RUN apk add --no-cache ffmpeg
RUN pip install -r /app/src/requirements.txt

# Print ASCII art with release version
RUN echo "╔═══════════════════════════════════════════════╗" > /ascii_art.txt && \
    echo "║       PLEX  TRACK  MANAGER                    ║" >> /ascii_art.txt && \
    echo "╚═══════════════════════════════════════════════╝" >> /ascii_art.txt && \
    echo "Release Version: ${RELEASE_VERSION}" >> /ascii_art.txt

RUN mkdir -p /data

# Run the main script
CMD ["sh", "-c", "cat /ascii_art.txt && python /app/src/main.py"]