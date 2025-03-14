import json
import os
from typing import Any, Dict, Optional, cast, Literal, Union, TypedDict
from datetime import datetime, timedelta
import asyncio
import time
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from trackerstatus import (
    TrackerStatus,
    APIClient,
    StatusEndpoint,
    ANTEndpoint,
    AREndpoint,
    BTNEndpoint,
    GGNEndpoint,
    NBLEndpoint,
    OPSEndpoint,
    PTPEndpoint,
    REDEndpoint,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('trackerstatus_bot')

# Load environment variables
load_dotenv()

# Initialize API client
api_client = APIClient()
status_api = StatusEndpoint(api_client)

# Initialize individual tracker endpoints
TRACKER_ENDPOINTS = {
    "ant": ANTEndpoint(api_client),
    "ar": AREndpoint(api_client),
    "btn": BTNEndpoint(api_client),
    "ggn": GGNEndpoint(api_client),
    "nbl": NBLEndpoint(api_client),
    "ops": OPSEndpoint(api_client),
    "ptp": PTPEndpoint(api_client),
    "red": REDEndpoint(api_client),
}

# Track last API call time
last_api_call: float = 0.0
api_lock = asyncio.Lock()

async def get_tracker_statuses() -> Dict[str, Dict[str, Union[int, str]]]:
    """Get tracker statuses with proper rate limiting.
    
    Returns a dictionary mapping tracker names to their status info.
    Each status info contains:
    - status_code: int (0=Online, 1=Unstable, 2=Offline)
    - status_message: str
    """
    global last_api_call
    
    async with api_lock:
        now = time.time()
        if last_api_call > 0:
            # Wait for rate limit if needed
            elapsed = now - last_api_call
            if elapsed < 60:
                await asyncio.sleep(60 - elapsed)
        
        # Make the API call in a background thread
        loop = asyncio.get_event_loop()
        statuses = await loop.run_in_executor(None, status_api.get_tracker_statuses)
        last_api_call = time.time()
        return cast(Dict[str, Dict[str, Union[int, str]]], statuses)

# Status emoji mapping (0=Online, 1=Unstable, 2=Offline)
STATUS_EMOJI = {
    1: "🟢",  # Online
    2: "🟡",  # Unstable
    0: "🔴",  # Offline
}

# Status descriptions
STATUS_DESC = {
    1: "ONLINE - perfect response over the past 3 minutes",
    2: "UNSTABLE - intermittent responses over the past 3 minutes",
    0: "OFFLINE - no response over the past 3 minutes",
}

# Tracker name mapping (API name to display name)
TRACKER_NAMES = {
    "ant": "AnimeBytes",
    "ar": "AlphaRatio",
    "btn": "BroadcastTheNet",
    "ggn": "GazelleGames",
    "nbl": "Nebulance",
    "ops": "Orpheus",
    "ptp": "PassThePopcorn",
    "red": "Redacted",
}

TrackerChoice = Literal["ANT", "AR", "BTN", "GGN", "NBL", "OPS", "PTP", "RED"]

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration file path
CONFIG_DIR = "/app/data"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Type aliases
GuildConfig = Dict[str, Dict[str, Dict[str, Any]]]

class StatusCheck(TypedDict):
    timestamp: datetime
    status_code: int
    response_time: float

def load_config() -> GuildConfig:
    """Load the configuration from file or return empty config."""
    try:
        # Create config directory if it doesn't exist
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Try to load existing config
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return cast(GuildConfig, json.load(f))
        
        # Create new config if file doesn't exist
        logger.info(f"Creating new config file at {CONFIG_FILE}")
        empty_config: GuildConfig = {"guilds": {}}
        save_config(empty_config)
        return empty_config
        
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {"guilds": {}}


def save_config(config: GuildConfig) -> None:
    """Save the configuration to file."""
    try:
        # Ensure config directory exists
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Write config with temporary file
        temp_file = f"{CONFIG_FILE}.tmp"
        with open(temp_file, "w") as f:
            json.dump(config, f, indent=4)
        
        # Atomic replace
        os.replace(temp_file, CONFIG_FILE)
        
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise


# Initialize configuration
config: GuildConfig = load_config()


@bot.event
async def on_ready() -> None:
    """Handle bot ready event."""
    print(f"{bot.user} has connected to Discord!")
    print("Attempting to sync commands...")
    try:
        print("Available commands to sync:", [cmd.name for cmd in bot.tree.get_commands()])
        synced = await bot.tree.sync()
        print(f"Successfully synced {len(synced)} command(s):")
        for cmd in synced:
            print(f"  - /{cmd.name}")
        check_trackers.start()
    except Exception as e:
        print(f"Error syncing commands: {e}")
        print("Full error details:", e.__class__.__name__)


@bot.tree.command(name="trackeravailable", description="List all available trackers that can be monitored")
async def trackeravailable(interaction: discord.Interaction) -> None:
    """List all available trackers that can be monitored."""
    embed = discord.Embed(
        title="Available Trackers",
        description="Here are all the trackers that can be monitored:",
        color=discord.Color.blue(),
    )
    
    tracker_list = "\n".join(f"• {code} - {name}" for code, name in TRACKER_NAMES.items())
    embed.add_field(name="Trackers", value=tracker_list)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="trackeradd", description="Add a tracker to monitor")
@app_commands.describe(
    tracker="The tracker to monitor",
    channel="The channel to send alerts to"
)
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackeradd(
    interaction: discord.Interaction,
    tracker: str,
    channel: discord.TextChannel,
) -> None:
    """Add a tracker to monitor with notifications in the specified channel."""
    # Defer the response since we might need to wait for rate limiting
    await interaction.response.defer(ephemeral=True)
    
    # Check if user has admin permissions
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        await interaction.followup.send(
            "This command can only be used in a server!", ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send(
            "You need administrator permissions to use this command!", ephemeral=True
        )
        return

    tracker = tracker.lower()
    if tracker not in TRACKER_NAMES:
        await interaction.followup.send(
            f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
            ephemeral=True,
        )
        return

    # Validate tracker by getting current status
    try:
        statuses = await get_tracker_statuses()
        if tracker not in statuses:
            await interaction.followup.send(
                f"Error: Could not get status for {TRACKER_NAMES[tracker]}",
                ephemeral=True
            )
            return
    except Exception as e:
        await interaction.followup.send(
            f"Error validating tracker {TRACKER_NAMES[tracker]}: {str(e)}",
            ephemeral=True
        )
        return

    guild_id = str(interaction.guild_id)
    if guild_id not in config:
        config[guild_id] = {}

    if "trackers" not in config[guild_id]:
        config[guild_id]["trackers"] = {}

    config[guild_id]["trackers"][tracker] = {
        "channel_id": channel.id,
        "last_status": None,
        "last_check": None
    }

    save_config(config)
    
    # Log the tracker addition
    logger.info(
        f"Tracker added: {TRACKER_NAMES[tracker]} in guild {interaction.guild.name} "
        f"(#{channel.name}) by {interaction.user.name}#{interaction.user.discriminator}"
    )
    
    await interaction.followup.send(
        f"Added tracker {TRACKER_NAMES[tracker]} with alerts in {channel.mention}",
        ephemeral=True
    )


@bot.tree.command(name="trackerremove", description="Remove a tracker from monitoring in a specific channel")
@app_commands.describe(
    tracker="The tracker to remove from monitoring",
    channel="The channel to stop monitoring in"
)
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackerremove(
    interaction: discord.Interaction,
    tracker: str,
    channel: discord.TextChannel,
) -> None:
    """Remove a tracker from monitoring in a specific channel."""
    # Check if user has admin permissions
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message(
            "This command can only be used in a server!", ephemeral=True
        )
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You need administrator permissions to use this command!", ephemeral=True
        )
        return

    guild_id = str(interaction.guild_id)
    tracker = tracker.lower()

    if (guild_id in config and 
        "trackers" in config[guild_id] and 
        tracker in config[guild_id]["trackers"]):
        
        # Check if the tracker is configured for the specified channel
        if config[guild_id]["trackers"][tracker]["channel_id"] == channel.id:
            # Remove the tracker
            del config[guild_id]["trackers"][tracker]
            save_config(config)
            
            # Log the removal
            logger.info(
                f"Tracker removed: {TRACKER_NAMES[tracker]} from guild {interaction.guild.name} "
                f"(#{channel.name}) by {interaction.user.name}#{interaction.user.discriminator}"
            )
            
            await interaction.response.send_message(
                f"Removed tracker {TRACKER_NAMES[tracker]} from {channel.mention}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Tracker {TRACKER_NAMES[tracker]} is not configured for {channel.mention}. "
                f"Use `/trackerlist` to see current configurations.",
                ephemeral=True
            )
    else:
        await interaction.response.send_message(
            f"Tracker {TRACKER_NAMES.get(tracker, tracker)} is not configured for this server. "
            f"Use `/trackerlist` to see current configurations.",
            ephemeral=True
        )


@bot.tree.command(name="trackerlist", description="List all configured trackers")
async def trackerlist(interaction: discord.Interaction) -> None:
    """List all configured trackers for the current server."""
    if not interaction.guild:
        await interaction.response.send_message(
            "This command can only be used in a server!", ephemeral=True
        )
        return

    guild_id = str(interaction.guild_id)
    if (
        guild_id not in config
        or "trackers" not in config[guild_id]
        or not config[guild_id]["trackers"]
    ):
        await interaction.response.send_message(
            "No trackers configured for this server.", ephemeral=True
        )
        return

    trackers_list = []
    for tracker_name, data in config[guild_id]["trackers"].items():
        channel = interaction.guild.get_channel(data["channel_id"])
        channel_mention = channel.mention if channel else "Unknown Channel"
        trackers_list.append(f"• {tracker_name} -> {channel_mention}")

    embed = discord.Embed(title="Configured Trackers", color=discord.Color.blue())
    embed.description = "\n".join(trackers_list)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tasks.loop(minutes=5)
async def check_trackers() -> None:
    """Check the status of all trackers and send notifications for changes."""
    try:
        logger.info("Starting periodic tracker status check...")
        # Get status for all trackers at once using our rate-limited function
        all_statuses = await get_tracker_statuses()
        
        for guild_id, guild_data in config.items():
            if "trackers" not in guild_data:
                continue

            for tracker_name, tracker_data in guild_data["trackers"].items():
                try:
                    if tracker_name not in all_statuses:
                        logger.warning(f"Unknown tracker {tracker_name}, skipping")
                        continue

                    status_info = all_statuses[tracker_name]
                    status_code = int(status_info['status_code'])  # Ensure it's an int
                    status_message = str(status_info['status_message'])  # Ensure it's a str

                    # Get the channel
                    guild = bot.get_guild(int(guild_id))
                    if not guild:
                        logger.warning(f"Could not find guild {guild_id}")
                        continue

                    channel = guild.get_channel(tracker_data["channel_id"])
                    if not channel or not isinstance(channel, discord.TextChannel):
                        logger.warning(
                            f"Could not find channel {tracker_data['channel_id']} "
                            f"in guild {guild.name}"
                        )
                        continue

                    # If this is the first check or status has changed
                    if (tracker_data["last_status"] is None or 
                        status_code != tracker_data["last_status"]):
                        
                        emoji = STATUS_EMOJI.get(status_code, "❓")
                        status_desc = STATUS_DESC.get(status_code, "Unknown status")
                        
                        # Log the status change
                        old_status = "None" if tracker_data["last_status"] is None else (
                            STATUS_DESC.get(tracker_data["last_status"], "Unknown")
                        )
                        logger.info(
                            f"Status change for {TRACKER_NAMES[tracker_name]} in {guild.name}: "
                            f"{old_status} -> {status_desc}"
                        )
                        
                        embed = discord.Embed(
                            title=f"Tracker Status Change",
                            description=(
                                f"**Tracker:** {TRACKER_NAMES[tracker_name]}\n"
                                f"**Status:** {emoji} {status_desc}\n"
                                f"**Message:** {status_message}"
                            ),
                            color=discord.Color.green() if status_code == 1 else 
                                  discord.Color.yellow() if status_code == 2 else 
                                  discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        await channel.send(embed=embed)

                        # Update the last known status
                        config[guild_id]["trackers"][tracker_name].update({
                            "last_status": status_code,
                            "last_check": datetime.now().isoformat()
                        })
                        save_config(config)

                except Exception as e:
                    logger.error(f"Error checking tracker {tracker_name}: {e}")

    except Exception as e:
        logger.error(f"Error getting tracker statuses: {e}")
    finally:
        logger.info("Completed periodic tracker status check")


@check_trackers.before_loop
async def before_check_trackers() -> None:
    """Wait for the bot to be ready before starting the tracker check loop."""
    await bot.wait_until_ready()


@bot.tree.command(name="trackerlatency", description="Get latency metrics for a tracker")
@app_commands.describe(tracker="The tracker to get latency metrics for")
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackerlatency(interaction: discord.Interaction, tracker: str) -> None:
    """Get latency metrics for a specific tracker."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get status history from the tracker endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        history: list[StatusCheck] = await loop.run_in_executor(None, endpoint.get_status_history)
        
        # Calculate latency metrics from history
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        recent_checks = [check for check in history if check['timestamp'] >= day_ago]
        
        if not recent_checks:
            await interaction.followup.send(
                f"No recent status checks available for {TRACKER_NAMES[tracker]}",
                ephemeral=True
            )
            return
        
        # Calculate metrics
        current_latency = recent_checks[-1].get('response_time', 0)
        latencies = [check.get('response_time', 0) for check in recent_checks if check.get('response_time', 0) > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        peak_latency = max(latencies) if latencies else 0
        
        embed = discord.Embed(
            title=f"Latency Metrics for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="Current Latency",
            value=f"{current_latency:.2f}ms" if current_latency > 0 else "No response",
            inline=True
        )
        embed.add_field(
            name="Average Latency (24h)",
            value=f"{avg_latency:.2f}ms",
            inline=True
        )
        embed.add_field(
            name="Peak Latency (24h)",
            value=f"{peak_latency:.2f}ms",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error getting latency metrics for {tracker}: {e}")
        await interaction.followup.send(
            f"Error getting latency metrics for {TRACKER_NAMES[tracker]}: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="trackeruptime", description="Get uptime statistics for a tracker")
@app_commands.describe(tracker="The tracker to get uptime statistics for")
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackeruptime(interaction: discord.Interaction, tracker: str) -> None:
    """Get uptime statistics for a specific tracker."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get status history from the tracker endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        history: list[StatusCheck] = await loop.run_in_executor(None, endpoint.get_status_history)
        
        # Calculate uptime statistics
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        def calculate_uptime(start_time: datetime) -> float:
            checks = [check for check in history if check['timestamp'] >= start_time]
            if not checks:
                return 0.0
            online_checks = len([check for check in checks if check['status_code'] == 1])
            return (online_checks / len(checks)) * 100
        
        # Get current status
        current_status = history[-1]['status_code'] if history else 0
        
        embed = discord.Embed(
            title=f"Uptime Statistics for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="Current Status",
            value=f"{STATUS_EMOJI.get(current_status, '❓')} {STATUS_DESC.get(current_status, 'Unknown')}",
            inline=False
        )
        embed.add_field(
            name="Uptime (24h)",
            value=f"{calculate_uptime(day_ago):.2f}%",
            inline=True
        )
        embed.add_field(
            name="Uptime (7d)",
            value=f"{calculate_uptime(week_ago):.2f}%",
            inline=True
        )
        embed.add_field(
            name="Uptime (30d)",
            value=f"{calculate_uptime(month_ago):.2f}%",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error getting uptime statistics for {tracker}: {e}")
        await interaction.followup.send(
            f"Error getting uptime statistics for {TRACKER_NAMES[tracker]}: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="trackerrecord", description="Get record uptimes for a tracker")
@app_commands.describe(tracker="The tracker to get record uptimes for")
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackerrecord(interaction: discord.Interaction, tracker: str) -> None:
    """Get record uptimes for a specific tracker."""
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get status history from the tracker endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        history: list[StatusCheck] = await loop.run_in_executor(None, endpoint.get_status_history)
        
        if not history:
            await interaction.followup.send(
                f"No status history available for {TRACKER_NAMES[tracker]}",
                ephemeral=True
            )
            return
        
        # Find longest uptime and downtime periods
        class Period(TypedDict):
            duration: timedelta
            start: Optional[datetime]
            end: Optional[datetime]
            
        longest_up: Period = {'duration': timedelta(0), 'start': None, 'end': None}
        longest_down: Period = {'duration': timedelta(0), 'start': None, 'end': None}
        current_up: Period = {'duration': timedelta(0), 'start': None, 'end': None}
        current_down: Period = {'duration': timedelta(0), 'start': None, 'end': None}
        
        for i, check in enumerate(history):
            timestamp = check['timestamp']
            is_up = check['status_code'] == 1
            
            if is_up:
                if current_up['start'] is None:
                    current_up['start'] = timestamp
                current_up['end'] = timestamp
                if current_up['start'] is not None and current_up['end'] is not None:
                    current_up['duration'] = current_up['end'] - current_up['start']
                
                if current_down['start'] is not None and current_down['end'] is not None:
                    current_down['duration'] = current_down['end'] - current_down['start']
                    if current_down['duration'] > longest_down['duration']:
                        longest_down.update(current_down)
                    current_down = {'duration': timedelta(0), 'start': None, 'end': None}
            else:
                if current_down['start'] is None:
                    current_down['start'] = timestamp
                current_down['end'] = timestamp
                if current_down['start'] is not None and current_down['end'] is not None:
                    current_down['duration'] = current_down['end'] - current_down['start']
                
                if current_up['start'] is not None and current_up['end'] is not None:
                    current_up['duration'] = current_up['end'] - current_up['start']
                    if current_up['duration'] > longest_up['duration']:
                        longest_up.update(current_up)
                    current_up = {'duration': timedelta(0), 'start': None, 'end': None}
        
        # Calculate monthly statistics
        months = {}
        for check in history:
            timestamp = check['timestamp']
            month_key = timestamp.strftime('%Y-%m')
            if month_key not in months:
                months[month_key] = {'total': 0, 'online': 0}
            months[month_key]['total'] += 1
            if check['status_code'] == 1:
                months[month_key]['online'] += 1
        
        monthly_uptimes = {
            month: (data['online'] / data['total'] * 100)
            for month, data in months.items()
            if data['total'] >= 100  # Only consider months with sufficient data
        }
        
        best_month = max(monthly_uptimes.items(), key=lambda x: x[1]) if monthly_uptimes else (None, 0)
        worst_month = min(monthly_uptimes.items(), key=lambda x: x[1]) if monthly_uptimes else (None, 0)
        
        embed = discord.Embed(
            title=f"Record Uptimes for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        if longest_up['start'] and longest_up['end'] and longest_up['duration']:
            duration_hours = longest_up['duration'].total_seconds() / 3600
            start_time = longest_up['start'].strftime('%Y-%m-%d %H:%M:%S')
            end_time = longest_up['end'].strftime('%Y-%m-%d %H:%M:%S')
            embed.add_field(
                name="Longest Uptime",
                value=f"{duration_hours:.1f} hours\n"
                      f"From: {start_time}\n"
                      f"To: {end_time}",
                inline=False
            )
        
        if longest_down['start'] and longest_down['end'] and longest_down['duration']:
            duration_hours = longest_down['duration'].total_seconds() / 3600
            start_time = longest_down['start'].strftime('%Y-%m-%d %H:%M:%S')
            end_time = longest_down['end'].strftime('%Y-%m-%d %H:%M:%S')
            embed.add_field(
                name="Longest Downtime",
                value=f"{duration_hours:.1f} hours\n"
                      f"From: {start_time}\n"
                      f"To: {end_time}",
                inline=False
            )
        
        if best_month[0]:
            embed.add_field(
                name="Best Monthly Uptime",
                value=f"{best_month[1]:.2f}%\nMonth: {best_month[0]}",
                inline=True
            )
        
        if worst_month[0]:
            embed.add_field(
                name="Worst Monthly Uptime",
                value=f"{worst_month[1]:.2f}%\nMonth: {worst_month[0]}",
                inline=True
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error getting record uptimes for {tracker}: {e}")
        await interaction.followup.send(
            f"Error getting record uptimes for {TRACKER_NAMES[tracker]}: {str(e)}",
            ephemeral=True
        )

def run() -> None:
    """Run the Discord bot."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is not set")
    bot.run(token)
