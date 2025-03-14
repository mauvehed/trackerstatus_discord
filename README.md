# Trackerstatus Discord Bot

A Discord bot that monitors the status of various private trackers and sends notifications when their status changes. The bot uses the `trackerstatus` python library to check tracker statuses and provides real-time updates in designated Discord channels.

## Features

- Monitor multiple trackers simultaneously
- Status change notifications for Online/Offline transitions
- Rate-limited API calls to prevent overloading
- Customizable notification channels per tracker
- Admin-only commands for security
- Detailed logging of all events

## Supported Trackers

- AnimeBytes (ANT)
- AlphaRatio (AR)
- BroadcastTheNet (BTN)
- GazelleGames (GGN)
- Nebulance (NBL)
- Orpheus (OPS)
- PassThePopcorn (PTP)
- Redacted (RED)

## Status Types

The bot tracks three different status types:

- 🟢 **ONLINE** - Perfect response over the past 3 minutes
- 🟡 **UNSTABLE** - Intermittent responses over the past 3 minutes (no notifications sent)
- 🔴 **OFFLINE** - No response over the past 3 minutes

Note: Notifications are only sent when a tracker transitions between Online and Offline states. Unstable states are tracked but do not trigger notifications to reduce alert fatigue.

## Commands

All commands require administrator permissions in the Discord server:

### Administrative Commands
- `/trackeravailable` - Lists all available trackers that can be monitored
- `/trackeradd <tracker> <channel>` - Starts monitoring a tracker and sends notifications to the specified channel
- `/trackerremove <tracker> <channel>` - Stops monitoring a tracker in the specified channel
- `/trackerlist` - Shows all currently monitored trackers and their notification channels
- `/trackerversion` - Displays the current version of both the bot and the trackerstatus library
- `/trackerupdate` - Force an immediate status check of all configured trackers and post their current status

### Status Commands
- `/trackerlatency <tracker>` - Get current latency metrics for each service of the specified tracker
- `/trackeruptime <tracker>` - Get current uptime statistics for each service of the specified tracker
- `/trackerrecord <tracker>` - Get record uptime durations for each service of the specified tracker

Each status command shows:
- Current tracker status (Online/Unstable/Offline)
- Individual service statuses
- Command-specific metrics (latency, uptime, or record duration)

Note: All command responses are ephemeral (only visible to the user who ran the command) to reduce channel clutter.

## Deployment Options

### Using Pre-built Docker Image (Recommended)

1. Create a new directory for the bot:
```bash
mkdir trackerstatus_bot
cd trackerstatus_bot
```

2. Create a `.env` file with your Discord bot token:
```bash
echo "DISCORD_TOKEN=your_token_here" > .env
```

3. Create a `docker-compose.yml` file:
```yaml
version: '3.8'

services:
  bot:
    image: ghcr.io/mauvehed/trackerstatus_discord:main
    container_name: trackerstatus_bot
    volumes:
      - config_data:/app/data
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
    restart: unless-stopped

volumes:
  config_data:
```

4. Start the bot:
```bash
docker compose up -d
```

### Option 2: Local Installation

1. Clone the repository:
```bash
git clone https://github.com/mauvehed/trackerstatus_discord.git
cd trackerstatus_discord
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Create a `.env` file with your Discord bot token:
```bash
DISCORD_TOKEN=your_discord_bot_token_here
```

Note: The repository includes a `.gitignore` file that prevents committing sensitive files like `.env` and `.envrc`.

4. Run the bot:
```bash
poetry run python main.py
```

### Option 3: Building Docker Image Locally

1. Clone the repository:
```bash
git clone https://github.com/mauvehed/trackerstatus_discord.git
cd trackerstatus_discord
```

2. Create a `.env` file with your Discord bot token:
```bash
echo "DISCORD_TOKEN=your_token_here" > .env
```

3. Create a docker-compose.yml file:
```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: trackerstatus_bot
    volumes:
      - config_data:/app/data
    environment:
      - DISCORD_TOKEN=${DISCORD_TOKEN}
    restart: unless-stopped

volumes:
  config_data:
```

4. Build and start the container:
```bash
docker compose up -d --build
```

## Docker Tags

The bot's Docker image is automatically built and published to GitHub Container Registry with the following tags:

- `main` - Latest version from the main branch
- `vX.Y.Z` - Release versions (e.g., v1.0.0)
- `vX.Y` - Major.Minor version (e.g., v1.0)
- `sha-XXXXXXX` - Specific commit hash

You can use any of these tags in your docker-compose.yml file by replacing `main` with the desired tag.

## Configuration

The bot stores its configuration in a JSON file, which includes:
- Tracked trackers per Discord server
- Notification channel settings
- Last known status for each tracker

When using Docker, the configuration is stored in a named volume for persistence across container restarts.

### Ignored Files

The following files are ignored by git for security and cleanliness:
- `.env` and `.envrc` files containing sensitive data
- Python virtual environments and cache files
- Build and distribution directories
- IDE-specific files
- Log files and Docker volumes
- Operating system files (e.g., .DS_Store)

## Monitoring

The bot includes detailed logging for monitoring its operation:
- Tracker additions and removals (with user and channel information)
- Status changes between Online and Offline states
- Periodic status check results
- Error conditions and warnings

Status checks occur every 5 minutes, and notifications are only sent when a tracker transitions between Online and Offline states to reduce notification noise.

## Rate Limiting

The bot implements proper rate limiting to prevent API abuse:
- Maximum of 1 request per minute to the trackerstatus API
- Non-blocking implementation using asyncio
- Automatic request queuing and processing

## Requirements

- Python 3.12 or higher
- Discord.py library
- Poetry for dependency management
- Discord bot token with proper permissions
  - Required permissions:
    - Send Messages
    - Embed Links
    - Read Message History
    - Use Slash Commands

## Error Handling

The bot includes robust error handling for:
- API connection issues
- Invalid tracker requests
- Missing permissions
- Channel access problems
- Rate limit management

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 