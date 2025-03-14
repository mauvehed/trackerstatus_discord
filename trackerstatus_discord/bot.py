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

# Initialize API client and endpoints
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

# Status emoji mapping (1=Online, 2=Unstable, 0=Offline)
STATUS_EMOJI = {
    1: "🟢",  # Online
    2: "🟡",  # Unstable
    0: "🔴",  # Offline
}

# Status descriptions (1=Online, 2=Unstable, 0=Offline)
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

# Type aliases for configuration
class TrackerConfig(TypedDict):
    """Configuration for a tracked tracker in a guild channel.
    
    Attributes:
        channel_id: The Discord channel ID where notifications are sent
        last_status: The last known status code (1=Online, 2=Unstable, 0=Offline)
        last_check: ISO format timestamp of the last status check
    """
    channel_id: int
    last_status: Optional[int]
    last_check: Optional[str]

GuildTrackers = Dict[str, TrackerConfig]
GuildConfigType = Dict[str, Dict[str, GuildTrackers]]

def load_config() -> GuildConfigType:
    """Load the configuration from file or return empty config."""
    try:
        # Create config directory if it doesn't exist
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Try to load existing config
        if os.path.isfile(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return cast(GuildConfigType, json.load(f))
        
        # Create new config if file doesn't exist
        logger.info(f"Creating new config file at {CONFIG_FILE}")
        empty_config: GuildConfigType = {"guilds": {}}
        save_config(empty_config)
        return empty_config
        
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {"guilds": {}}


def save_config(config: GuildConfigType) -> None:
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
config: GuildConfigType = load_config()


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
        loop = asyncio.get_event_loop()
        statuses = await loop.run_in_executor(None, status_api.get_tracker_statuses)
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
        # Get status for all trackers using the library's endpoint
        loop = asyncio.get_event_loop()
        all_statuses = await loop.run_in_executor(None, status_api.get_tracker_statuses)
        
        for guild_id, guild_data in config.items():
            if "trackers" not in guild_data:
                continue

            for tracker_name, tracker_data in guild_data["trackers"].items():
                try:
                    if tracker_name not in all_statuses:
                        logger.warning(f"Unknown tracker {tracker_name}, skipping")
                        continue

                    status_info = all_statuses[tracker_name]
                    status_code = int(status_info['status_code'])
                    status_message = str(status_info['status_message'])

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
                        
                        # Log the status change
                        old_status = "None" if tracker_data["last_status"] is None else (
                            "Online" if tracker_data["last_status"] == 1 else
                            "Unstable" if tracker_data["last_status"] == 2 else
                            "Offline"
                        )
                        new_status = ("Online" if status_code == 1 else
                                    "Unstable" if status_code == 2 else
                                    "Offline")
                        logger.info(
                            f"Status change for {TRACKER_NAMES[tracker_name]} in {guild.name}: "
                            f"{old_status} -> {new_status}"
                        )
                        
                        embed = discord.Embed(
                            title=f"Tracker Status Change",
                            description=(
                                f"**Tracker:** {TRACKER_NAMES[tracker_name]}\n"
                                f"**Status:** {emoji} {new_status}\n"
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
    """Get latency metrics for a specific tracker.
    
    Retrieves current status and latency information for all services of the tracker.
    Displays:
    - Current tracker status (Online/Unstable/Offline)
    - Status and latency for each service
    """
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get tracker info using the library's endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        
        # Get all tracker info including status and services
        tracker_info = await loop.run_in_executor(None, endpoint.get_all)
        status = tracker_info.get('status', {})
        current_status = int(status.get('status_code', 0))
        
        # Create embed
        embed = discord.Embed(
            title=f"Latency Information for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add current status
        status_desc = STATUS_DESC.get(current_status, "Unknown")
        embed.add_field(
            name="Current Status",
            value=f"{STATUS_EMOJI.get(current_status, '❓')} {status_desc}",
            inline=False
        )
        
        # Add service latency information
        services = tracker_info.get('services', {})
        for service_name, service_data in services.items():
            latency = service_data.get('latency', 0)
            status = "✅ Online" if service_data.get('online') else "❌ Offline"
            embed.add_field(
                name=service_name,
                value=f"{status}\nLatency: {latency}ms",
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
    """Get uptime statistics for a specific tracker.
    
    Retrieves current status and uptime information for all services of the tracker.
    Displays:
    - Current tracker status (Online/Unstable/Offline)
    - Status for each service
    """
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get current status and uptime info using the library's endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        
        # Get all tracker info including status and uptime
        tracker_info = await loop.run_in_executor(None, endpoint.get_all)
        status = tracker_info.get('status', {})
        current_status = int(status.get('status_code', 0))
        
        # Create embed
        embed = discord.Embed(
            title=f"Uptime Statistics for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add current status
        status_desc = STATUS_DESC.get(current_status, "Unknown")
        embed.add_field(
            name="Current Status",
            value=f"{STATUS_EMOJI.get(current_status, '❓')} {status_desc}",
            inline=False
        )
        
        # Add service status information
        services = tracker_info.get('services', {})
        for service_name, service_data in services.items():
            status = "✅ Online" if service_data.get('online') else "❌ Offline"
            embed.add_field(
                name=service_name,
                value=status,
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
    """Get record uptimes for a specific tracker.
    
    Retrieves current status and uptime records for all services of the tracker.
    Displays:
    - Current tracker status (Online/Unstable/Offline)
    - Status and uptime duration for each service
    """
    await interaction.response.defer(ephemeral=True)
    
    try:
        tracker = tracker.lower()
        if tracker not in TRACKER_NAMES:
            await interaction.followup.send(
                f"Invalid tracker: {tracker}. Use /trackeravailable to see available options.",
                ephemeral=True,
            )
            return

        # Get tracker info using the library's endpoint
        endpoint = TRACKER_ENDPOINTS[tracker]
        loop = asyncio.get_event_loop()
        
        # Get all tracker info including status and services
        tracker_info = await loop.run_in_executor(None, endpoint.get_all)
        status = tracker_info.get('status', {})
        current_status = int(status.get('status_code', 0))
        
        # Create embed
        embed = discord.Embed(
            title=f"Record Statistics for {TRACKER_NAMES[tracker]}",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Add current status
        status_desc = STATUS_DESC.get(current_status, "Unknown")
        embed.add_field(
            name="Current Status",
            value=f"{STATUS_EMOJI.get(current_status, '❓')} {status_desc}",
            inline=False
        )
        
        # Add service record information
        services = tracker_info.get('services', {})
        for service_name, service_data in services.items():
            uptime = service_data.get('uptime', 0)
            status = "✅ Online" if service_data.get('online') else "❌ Offline"
            embed.add_field(
                name=service_name,
                value=f"{status}\nUptime: {uptime} minutes",
                inline=True
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error getting record statistics for {tracker}: {e}")
        await interaction.followup.send(
            f"Error getting record statistics for {TRACKER_NAMES[tracker]}: {str(e)}",
            ephemeral=True
        )

def run() -> None:
    """Run the Discord bot."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is not set")
    bot.run(token)
