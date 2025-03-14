# Trackerstatus Discord Bot

A Discord bot that monitors the status of various private trackers and sends notifications when their status changes. The bot uses the `trackerstatus` python library to check tracker statuses and provides real-time updates in designated Discord channels.

## Features

- Monitor multiple trackers simultaneously
- Real-time status change notifications
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

The bot reports three different status types:

- 🟢 **ONLINE** - Perfect response over the past 3 minutes
- 🟡 **UNSTABLE** - Intermittent responses over the past 3 minutes
- 🔴 **OFFLINE** - No response over the past 3 minutes

## Commands

All commands require administrator permissions in the Discord server:

- `/trackeravailable` - Lists all available trackers that can be monitored
- `/trackeradd <tracker> <channel>` - Start monitoring a tracker and send notifications to the specified channel
- `/trackerremove <tracker> <channel>` - Stop monitoring a tracker in the specified channel
- `/trackerlist` - Show all currently monitored trackers and their notification channels

## Deployment Options

### Option 1: Local Installation

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

4. Run the bot:
```bash
poetry run python main.py
```

### Option 2: Docker Deployment

1. Clone the repository:
```bash
git clone https://github.com/mauvehed/trackerstatus_discord.git
cd trackerstatus_discord
```

2. Create a `.env` file with your Discord bot token:
```bash
DISCORD_TOKEN=your_discord_bot_token_here
```

3. Build and start the container:
```bash
docker compose up -d
```

The bot will automatically restart unless stopped manually. To view the logs:
```bash
docker compose logs -f
```

To stop the bot:
```bash
docker compose down
```

## Configuration

The bot stores its configuration in `config.json`, which includes:
- Tracked trackers per Discord server
- Notification channel settings
- Last known status for each tracker

When using Docker, the `config.json` file is persisted on the host machine and mounted into the container.

## Monitoring

The bot includes detailed logging for monitoring its operation:
- Tracker additions and removals (with user and channel information)
- Status changes for all trackers
- Periodic status check results
- Error conditions and warnings

Status checks occur every 5 minutes, and notifications are only sent when a tracker's status changes.

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