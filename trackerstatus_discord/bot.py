import json
import os
from typing import Dict, Optional, cast, TypedDict
from datetime import datetime
import asyncio
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
    __version__ as trackerstatus_version,
)

# Bot version
VERSION = "0.1.0"

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

# Initialize individual tracker endpoints for detailed information
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

# Status emoji mapping using TrackerStatus enum
STATUS_EMOJI = {
    TrackerStatus.ONLINE: "🟢",    # Perfect response over past 3 minutes
    TrackerStatus.UNSTABLE: "🟡",  # Intermittent responses over past 3 minutes
    TrackerStatus.OFFLINE: "🔴",   # No response over past 3 minutes
}

# Status descriptions using TrackerStatus enum
STATUS_DESC = {
    TrackerStatus.ONLINE: "ONLINE - perfect response over the past 3 minutes",
    TrackerStatus.UNSTABLE: "UNSTABLE - intermittent responses over the past 3 minutes",
    TrackerStatus.OFFLINE: "OFFLINE - no response over the past 3 minutes",
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

# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Configuration file path for persistent storage
CONFIG_DIR = "/app/data"
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

# Type aliases for configuration
class TrackerConfig(TypedDict):
    """Configuration for a tracked tracker in a guild channel.
    
    Attributes:
        channel_id (int): The Discord channel ID where notifications are sent
        last_status (Optional[int]): The last known status code using TrackerStatus enum values
        last_check (Optional[str]): ISO format timestamp of the last status check
    """
    channel_id: int
    last_status: Optional[int]
    last_check: Optional[str]

GuildTrackers = Dict[str, TrackerConfig]
GuildConfigType = Dict[str, Dict[str, GuildTrackers]]

def load_config() -> GuildConfigType:
    """Load the configuration from file or create a new empty config.
    
    Returns:
        GuildConfigType: The loaded configuration or an empty configuration if the file
        doesn't exist or there's an error loading it.
    
    The configuration structure is:
    {
        "guilds": {
            "guild_id": {
                "trackers": {
                    "tracker_name": {
                        "channel_id": 123456789,
                        "last_status": 1,
                        "last_check": "2024-03-21T10:00:00"
                    }
                }
            }
        }
    }
    """
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
    """Save the configuration to file atomically.
    
    Args:
        config (GuildConfigType): The configuration to save
    
    Raises:
        Exception: If there's an error creating the directory or saving the file
    
    The save is performed atomically by writing to a temporary file first
    and then replacing the original file.
    """
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
    """Handle bot ready event.
    
    Logs the bot startup, including versions of both the bot and trackerstatus library.
    Syncs slash commands with Discord and starts the tracker check loop.
    Also displays a list of all available commands.
    """
    logger.info(f"Using trackerstatus library v{trackerstatus_version}")
    logger.info(f"TrackerStatus Discord Bot v{VERSION} starting up...")
    print(f"{bot.user} has connected to Discord!")
    print("\nAttempting to sync commands...")
    try:
        commands = bot.tree.get_commands()
        print(f"\nAvailable commands to sync ({len(commands)}):")
        for cmd in commands:
            print(f"  - /{cmd.name}: {cmd.description}")
        
        synced = await bot.tree.sync()
        print(f"\nSuccessfully synced {len(synced)} command(s):")
        for cmd in synced:
            print(f"  - /{cmd.name}")
        check_trackers.start()
    except Exception as e:
        print(f"Error syncing commands: {e}")
        print("Full error details:", e.__class__.__name__)


@bot.tree.command(name="trackerversion", description="Show bot and library versions")
async def trackerversion(interaction: discord.Interaction) -> None:
    """Display the current version of the bot and the trackerstatus library.
    
    Shows:
    - Bot version number
    - TrackerStatus library version number
    """
    embed = discord.Embed(
        title="TrackerStatus Bot Version Information",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="Bot Version",
        value=f"v{VERSION}",
        inline=True
    )
    
    embed.add_field(
        name="TrackerStatus Library",
        value=f"v{trackerstatus_version}",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="trackeravailable", description="List all available trackers that can be monitored")
async def trackeravailable(interaction: discord.Interaction) -> None:
    """List all available trackers that can be monitored.
    
    Shows:
    - Tracker code (used in commands)
    - Full tracker name
    """
    embed = discord.Embed(
        title="Available Trackers",
        description="Here are all the trackers that can be monitored:",
        color=discord.Color.blue(),
    )
    
    tracker_list = "\n".join(f"• {code} - {name}" for code, name in TRACKER_NAMES.items())
    embed.add_field(name="Trackers", value=tracker_list)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="trackeradd", description="Add a tracker to monitor in a specific channel")
@app_commands.describe(
    tracker="The tracker to monitor (use /trackeravailable to see options)",
    channel="The channel where status notifications will be sent"
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
    """Add a tracker to monitor with notifications in the specified channel.
    
    Args:
        interaction: The Discord interaction context
        tracker: The tracker code to monitor (e.g., 'btn', 'red')
        channel: The Discord channel where notifications will be sent
    
    Requirements:
    - Must be used in a server (guild)
    - User must have administrator permissions
    - Tracker must be valid and available
    - Channel must be accessible by the bot
    """
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
    """Check the status of all trackers and send notifications for changes.
    
    This task runs every 5 minutes and:
    1. Fetches current status for all trackers
    2. For each configured tracker in each guild:
       - Checks if status has changed
       - Updates stored status
       - Sends notifications for Online/Offline transitions
    
    Notification Behavior:
    - Only sends notifications for transitions between Online and Offline states
    - Tracks but does not notify for Unstable state changes
    - Includes current status and status message in notifications
    - Uses color coding (green for Online, red for Offline)
    """
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
                    status_code = TrackerStatus(int(status_info['status_code']))
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

                    # Only send alerts for changes between Online and Offline
                    # First check: skip if both old and new status are Unstable
                    if (status_code == TrackerStatus.UNSTABLE and 
                        tracker_data["last_status"] == TrackerStatus.UNSTABLE.value):
                        continue
                        
                    # Second check: skip if transitioning to/from Unstable
                    if (status_code == TrackerStatus.UNSTABLE or 
                        tracker_data["last_status"] == TrackerStatus.UNSTABLE.value):
                        # Just update the status without sending a notification
                        config[guild_id]["trackers"][tracker_name].update({
                            "last_status": status_code.value,
                            "last_check": datetime.now().isoformat()
                        })
                        save_config(config)
                        continue

                    # If this is the first check or status has changed between Online/Offline
                    if (tracker_data["last_status"] is None or 
                        status_code.value != tracker_data["last_status"]):
                        
                        emoji = STATUS_EMOJI.get(status_code, "❓")
                        
                        # Log the status change
                        old_status = "None" if tracker_data["last_status"] is None else (
                            "Online" if tracker_data["last_status"] == TrackerStatus.ONLINE.value else
                            "Offline"
                        )
                        new_status = "Online" if status_code == TrackerStatus.ONLINE else "Offline"
                        
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
                            color=discord.Color.green() if status_code == TrackerStatus.ONLINE else 
                                  discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        await channel.send(embed=embed)

                        # Update the last known status
                        config[guild_id]["trackers"][tracker_name].update({
                            "last_status": status_code.value,
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


@bot.tree.command(name="trackerlatency", description="Get current latency metrics for a tracker")
@app_commands.describe(tracker="The tracker to get latency metrics for")
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackerlatency(interaction: discord.Interaction, tracker: str) -> None:
    """Get current latency metrics for a specific tracker.
    
    Args:
        interaction: The Discord interaction context
        tracker: The tracker code to check (e.g., 'btn', 'red')
    
    Shows:
    - Current tracker status (Online/Unstable/Offline)
    - Status of each service (Online/Offline)
    - Current latency in milliseconds for each service
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
        current_status = TrackerStatus(int(status.get('status_code', 0)))
        
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

@bot.tree.command(name="trackeruptime", description="Get current uptime statistics for a tracker")
@app_commands.describe(tracker="The tracker to get uptime statistics for")
@app_commands.choices(tracker=[
    app_commands.Choice(name=f"{code} - {TRACKER_NAMES[code.lower()]}", value=code)
    for code in TRACKER_NAMES.keys()
])
async def trackeruptime(interaction: discord.Interaction, tracker: str) -> None:
    """Get current uptime statistics for a specific tracker.
    
    Args:
        interaction: The Discord interaction context
        tracker: The tracker code to check (e.g., 'btn', 'red')
    
    Shows:
    - Current tracker status (Online/Unstable/Offline)
    - Status of each service (Online/Offline)
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
        current_status = TrackerStatus(int(status.get('status_code', 0)))
        
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
    
    Args:
        interaction: The Discord interaction context
        tracker: The tracker code to check (e.g., 'btn', 'red')
    
    Shows:
    - Current tracker status (Online/Unstable/Offline)
    - Status of each service (Online/Offline)
    - Record uptime duration in minutes for each service
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
        current_status = TrackerStatus(int(status.get('status_code', 0)))
        
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

@bot.tree.command(name="trackerupdate", description="Force an immediate status check of all configured trackers")
async def trackerupdate(interaction: discord.Interaction) -> None:
    """Force an immediate status check and update for all configured trackers.
    
    This command will:
    1. Check all configured trackers immediately
    2. Post current status to their configured channels
    3. Update the last known status
    
    Requirements:
    - Must be used in a server (guild)
    - User must have administrator permissions
    """
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
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild_id = str(interaction.guild_id)
        if (guild_id not in config or 
            "trackers" not in config[guild_id] or 
            not config[guild_id]["trackers"]):
            await interaction.followup.send(
                "No trackers configured for this server.", ephemeral=True
            )
            return
            
        # Get status for all trackers
        loop = asyncio.get_event_loop()
        all_statuses = await loop.run_in_executor(None, status_api.get_tracker_statuses)
        
        update_count = 0
        for tracker_name, tracker_data in config[guild_id]["trackers"].items():
            try:
                if tracker_name not in all_statuses:
                    logger.warning(f"Unknown tracker {tracker_name}, skipping")
                    continue

                status_info = all_statuses[tracker_name]
                status_code = TrackerStatus(int(status_info['status_code']))
                status_message = str(status_info['status_message'])

                # Get the channel
                channel = interaction.guild.get_channel(tracker_data["channel_id"])
                if not channel or not isinstance(channel, discord.TextChannel):
                    logger.warning(
                        f"Could not find channel {tracker_data['channel_id']} "
                        f"in guild {interaction.guild.name}"
                    )
                    continue

                emoji = STATUS_EMOJI.get(status_code, "❓")
                status_text = "Online" if status_code == TrackerStatus.ONLINE else (
                    "Unstable" if status_code == TrackerStatus.UNSTABLE else "Offline"
                )
                
                embed = discord.Embed(
                    title=f"Tracker Status Update",
                    description=(
                        f"**Tracker:** {TRACKER_NAMES[tracker_name]}\n"
                        f"**Status:** {emoji} {status_text}\n"
                        f"**Message:** {status_message}"
                    ),
                    color=discord.Color.blue(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=embed)
                
                # Update the last known status
                config[guild_id]["trackers"][tracker_name].update({
                    "last_status": status_code.value,
                    "last_check": datetime.now().isoformat()
                })
                update_count += 1
                
            except Exception as e:
                logger.error(f"Error updating tracker {tracker_name}: {e}")
                continue
        
        save_config(config)
        await interaction.followup.send(
            f"Successfully updated status for {update_count} tracker(s).", ephemeral=True
        )
        
    except Exception as e:
        logger.error(f"Error in force update command: {e}")
        await interaction.followup.send(
            f"Error performing force update: {str(e)}", ephemeral=True
        )

def run() -> None:
    """Run the Discord bot.
    
    Requires:
    - DISCORD_TOKEN environment variable to be set
    
    Raises:
        ValueError: If DISCORD_TOKEN is not set
    """
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable is not set")
    bot.run(token)
