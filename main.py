import discord
from discord.ext import commands
import datetime
import asyncio
import motor.motor_asyncio
import pytz
import os

# --- CONFIGURATION --- #
# Use os.getenv() to get the MONGO_URI from an environment variable.
# The second argument is a fallback for local development.
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = "area69bot"
WARNINGS_COLLECTION = "warnings"
AFK_COLLECTION = "afk"
LOG_CHANNEL_COLLECTION = "logchannel"
KATHMANDU_TIMEZONE = pytz.timezone('Asia/Kathmandu')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='69 ', intents=intents, help_command=None)

# MongoDB setup
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = mongo_client[DATABASE_NAME]

# Helper: usage info for commands
COMMAND_INFOS = {
    "kick": {
        "usage": "69 kick <user> [reason]",
        "example": "69 kick @User spamming",
        "desc": "Kicks a user from the server. (Moderator/Admin only)"
    },
    "ban": {
        "usage": "69 ban <user> [reason]",
        "example": "69 ban @User breaking rules",
        "desc": "Bans a user from the server. (Moderator/Admin only)"
    },
    "unban": {
        "usage": "69 unban <user_id_or_name#discrim> [reason]",
        "example": "69 unban 123456789012345678",
        "desc": "Unbans a user by ID or name#discrim. (Moderator/Admin only)"
    },
    "timeout": {
        "usage": "69 timeout <user> <duration> [reason]",
        "example": "69 timeout @User 10m spamming",
        "desc": "Times out a user for a duration (s,m,h,d). (Moderator/Admin only)"
    },
    "removetimeout": {
        "usage": "69 removetimeout <user> [reason]",
        "example": "69 removetimeout @User done with timeout",
        "desc": "Removes timeout from a user. (Moderator/Admin only)"
    },
    "warn": {
        "usage": "69 warn <user> [reason]",
        "example": "69 warn @User inappropriate language",
        "desc": "Warns a user. (Moderator/Admin only)"
    },
    "warns": {
        "usage": "69 warns <user>",
        "example": "69 warns @User",
        "desc": "Shows all warnings for a user. (Moderator/Admin only)"
    },
    "setlogschannel": {
        "usage": "69 setlogschannel <#channel>",
        "example": "69 setlogschannel #mod-logs",
        "desc": "Sets the moderation logs channel. (Moderator/Admin only)"
    },
    "clear": {
        "usage": "69 clear [@user] <amount>",
        "example": "69 clear 50\n69 clear @User 30",
        "desc": "Deletes messages. Delete last <amount> or last <amount> from user. (Moderator/Admin only)"
    },
    "afk": {
        "usage": "69 afk [reason]",
        "example": "69 afk Taking a break",
        "desc": "Sets your AFK status with an optional reason."
    },
    "help": {
        "usage": "69 help",
        "example": "69 help",
        "desc": "Shows this help message."
    }
}

# --- Helper Functions ---

def get_command_usage_embed(command_name):
    info = COMMAND_INFOS.get(command_name)
    if not info:
        return None
    embed = discord.Embed(
        title=f"Usage: {info['usage']}",
        color=discord.Color.red()
    )
    embed.add_field(name="Example", value=info['example'], inline=False)
    embed.add_field(name="Description", value=info['desc'], inline=False)
    return embed

async def send_permission_error(ctx):
    await ctx.send(embed=discord.Embed(
        description="🚫 You don't have permission to use this command.",
        color=discord.Color.red()
    ), delete_after=3)

async def send_user_not_found(ctx):
    await ctx.send(embed=discord.Embed(
        description="❌ User not found.",
        color=discord.Color.red()
    ), delete_after=3)

async def send_invalid_usage(ctx, command_name):
    embed = get_command_usage_embed(command_name)
    if embed:
        await ctx.send(embed=embed, delete_after=3)
    else:
        await ctx.send("Invalid command usage.", delete_after=3)

async def send_mod_log(guild, user, action, reason, moderator):
    log_channel_id_doc = await db[LOG_CHANNEL_COLLECTION].find_one({"guild_id": guild.id})
    if log_channel_id_doc:
        log_channel = guild.get_channel(log_channel_id_doc["channel_id"])
        if log_channel:
            embed = discord.Embed(
                title=f"👤 {action} | {user}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
            )
            embed.add_field(name="User", value=user.mention, inline=False)
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(name="Moderator", value=moderator.mention, inline=False)
            await log_channel.send(embed=embed)

# --- AFK Functions ---

async def set_afk(user: discord.Member, reason: str):
    # Store the current nickname before changing it
    current_nick = user.display_name
    await db[AFK_COLLECTION].update_one(
        {"user_id": user.id},
        {"$set": {"reason": reason, "original_nick": current_nick}},
        upsert=True
    )
    
    new_nick = f"[AFK] {current_nick}"
    if len(new_nick) > 32:
        new_nick = new_nick[:32]
    
    try:
        await user.edit(nick=new_nick)
    except discord.Forbidden:
        pass

async def remove_afk(user: discord.Member):
    afk_doc = await db[AFK_COLLECTION].find_one({"user_id": user.id})
    if afk_doc:
        original_nick = afk_doc.get("original_nick")
        if user.display_name.startswith("[AFK]"):
            try:
                # Restore the original nickname
                await user.edit(nick=original_nick)
            except discord.Forbidden:
                pass
        
        await db[AFK_COLLECTION].delete_one({"user_id": user.id})

async def is_afk(user: discord.Member):
    afk_doc = await db[AFK_COLLECTION].find_one({"user_id": user.id})
    return afk_doc["reason"] if afk_doc else None

# --- Bot Events ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready!")
    
    activity = discord.CustomActivity(name="🔗 dsc.gg/4rea69")
    await bot.change_presence(status=discord.Status.online, activity=activity)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Check if the user is AFK and mention themselves
    afk_reason = await is_afk(message.author)
    if afk_reason:
        await remove_afk(message.author)
        await message.channel.send(f"Welcome back, {message.author.mention}! Your AFK status has been removed.", delete_after=3)
    
    # Check if the user mentions an AFK user
    for member in message.mentions:
        reason = await is_afk(member)
        if reason and member.id != message.author.id:
            await message.channel.send(f"{member.mention} is currently AFK. Reason: {reason}", delete_after=3)

    await bot.process_commands(message)

# --- Commands ---

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="Area 69 Bot Commands",
        description=f"Prefix: `69`\n\n**Join Our Discord Server:**\nhttps://discord.gg/9RJK4TmwrW\n\nHere are the available commands:",
        color=discord.Color.blue()
    )
    for cmd, info in COMMAND_INFOS.items():
        embed.add_field(name=info["usage"], value=info["desc"], inline=False)
        
    embed.set_footer(text="Developed By : U　N　K　N　O　W　N　ツ")
    await ctx.send(embed=embed, delete_after=10)

@bot.command()
async def afk(ctx, *, reason="No reason given."):
    """Sets your status to AFK."""
    if await is_afk(ctx.author):
        await remove_afk(ctx.author)
        await ctx.send(f"Welcome back, {ctx.author.mention}! Your AFK status has been removed.", delete_after=3)
    else:
        await set_afk(ctx.author, reason)
        await ctx.send(f"{ctx.author.mention} is now AFK. Reason: {reason}", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "kick")
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="User Kicked",
            description=f"{member.mention} has been kicked.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
        )
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await ctx.send(embed=embed, delete_after=3)
        await send_mod_log(ctx.guild, member, "Kick", reason, ctx.author)
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick that member.", delete_after=3)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=3)

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "ban")
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="User Banned",
            description=f"{member.mention} has been banned.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
        )
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await ctx.send(embed=embed, delete_after=3)
        await send_mod_log(ctx.guild, member, "Ban", reason, ctx.author)
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban that member.", delete_after=3)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=3)

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, member_id_or_name: str = None, *, reason=None):
    if not member_id_or_name:
        return await send_invalid_usage(ctx, "unban")

    banned_users = [entry async for entry in ctx.guild.bans()]
    user_to_unban = None
    try:
        member_id = int(member_id_or_name)
        for ban_entry in banned_users:
            if ban_entry.user.id == member_id:
                user_to_unban = ban_entry.user
                break
    except ValueError:
        for ban_entry in banned_users:
            if str(ban_entry.user) == member_id_or_name:
                user_to_unban = ban_entry.user
                break

    if user_to_unban:
        try:
            await ctx.guild.unban(user_to_unban, reason=reason)
            embed = discord.Embed(
                title="User Unbanned",
                description=f"{user_to_unban.mention} has been unbanned.",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
            )
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            await ctx.send(embed=embed, delete_after=3)
            await send_mod_log(ctx.guild, user_to_unban, "Unban", reason, ctx.author)
        except discord.Forbidden:
            await ctx.send("I don't have permission to unban that member.", delete_after=3)
        except Exception as e:
            await ctx.send(f"An error occurred: {e}", delete_after=3)
    else:
        await send_user_not_found(ctx)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member = None, duration: str = None, *, reason=None):
    if not member or not duration:
        return await send_invalid_usage(ctx, "timeout")

    try:
        unit = duration[-1].lower()
        amount = int(duration[:-1])
    except (ValueError, IndexError):
        # Handle full duration names
        duration_str = duration.lower()
        if duration_str.endswith('sec'):
            unit = 's'
            amount = int(duration_str[:-3])
        elif duration_str.endswith('min'):
            unit = 'm'
            amount = int(duration_str[:-3])
        elif duration_str.endswith('hr'):
            unit = 'h'
            amount = int(duration_str[:-2])
        elif duration_str.endswith('day'):
            unit = 'd'
            amount = int(duration_str[:-3])
        else:
            return await ctx.send("Invalid duration format. Use number + s/m/h/d or sec/min/hr/day, e.g. 10m, 1h, 1day.", delete_after=3)


    if unit in ['s', 'sec']:
        timeout_delta = datetime.timedelta(seconds=amount)
    elif unit in ['m', 'min']:
        timeout_delta = datetime.timedelta(minutes=amount)
    elif unit in ['h', 'hr']:
        timeout_delta = datetime.timedelta(hours=amount)
    elif unit in ['d', 'day']:
        timeout_delta = datetime.timedelta(days=amount)
    else:
        return await ctx.send("Invalid duration unit. Use s, m, h, or d.", delete_after=3)

    try:
        await member.timeout(timeout_delta, reason=reason)
        embed = discord.Embed(
            title="User Timed Out",
            description=f"{member.mention} has been timed out for {duration}.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
        )
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await ctx.send(embed=embed, delete_after=3)
        await send_mod_log(ctx.guild, member, "Timeout", reason, ctx.author)
    except discord.Forbidden:
        await ctx.send("I don't have permission to timeout that member.", delete_after=3)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=3)

@bot.command(name='removetimeout')
@commands.has_permissions(moderate_members=True)
async def removetimeout(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "removetimeout")
    try:
        await member.timeout(None, reason=reason)
        embed = discord.Embed(
            title="Timeout Removed",
            description=f"Timeout has been removed for {member.mention}.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
        )
        await ctx.send(embed=embed, delete_after=3)
        await send_mod_log(ctx.guild, member, "Remove Timeout", reason, ctx.author)
    except discord.Forbidden:
        await ctx.send("I don't have permission to remove timeout for that member.", delete_after=3)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=3)

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "warn")

    if member.top_role >= ctx.guild.me.top_role:
        return await ctx.send("I can't warn that user because their role is equal/higher than mine.", delete_after=3)

    await db[WARNINGS_COLLECTION].update_one(
        {"user_id": member.id},
        {"$push": {"reasons": reason}},
        upsert=True
    )
    embed = discord.Embed(
        title="User Warned",
        description=f"{member.mention} has been warned.",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
    )
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    await ctx.send(embed=embed, delete_after=3)
    await send_mod_log(ctx.guild, member, "Warn", reason, ctx.author)

@bot.command()
@commands.has_permissions(kick_members=True)
async def warns(ctx, member: discord.Member = None):
    if not member:
        return await send_invalid_usage(ctx, "warns")

    warn_doc = await db[WARNINGS_COLLECTION].find_one({"user_id": member.id})
    if not warn_doc or not warn_doc.get("reasons"):
        return await ctx.send(f"{member.mention} has no warnings.", delete_after=3)

    embed = discord.Embed(
        title=f"Warnings for {member}",
        color=discord.Color.gold()
    )
    for i, reason in enumerate(warn_doc["reasons"], 1):
        embed.add_field(name=f"Warning #{i}", value=reason or "No reason provided", inline=False)
    await ctx.send(embed=embed, delete_after=15) # Longer duration for warnings list

@bot.command()
@commands.has_permissions(manage_channels=True)
async def setlogschannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await send_invalid_usage(ctx, "setlogschannel")
    await db[LOG_CHANNEL_COLLECTION].update_one(
        {"guild_id": ctx.guild.id},
        {"$set": {"channel_id": channel.id}},
        upsert=True
    )
    await ctx.send(f"Moderation logs will now be sent to {channel.mention}.", delete_after=3)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, *args):
    user = None
    amount = None
    
    if len(args) == 1:
        try:
            amount = int(args[0])
        except ValueError:
            return await send_invalid_usage(ctx, "clear")
    elif len(args) == 2:
        try:
            user = await commands.MemberConverter().convert(ctx, args[0])
            amount = int(args[1])
        except commands.MemberNotFound:
            return await send_user_not_found(ctx)
        except ValueError:
            return await send_invalid_usage(ctx, "clear")
    else:
        return await send_invalid_usage(ctx, "clear")

    if amount <= 0:
        return await ctx.send("Please specify a positive number of messages to delete.", delete_after=3)

    def check(message):
        return message.author == user if user else True

    deleted = await ctx.channel.purge(limit=amount, check=check)

    embed = discord.Embed(
        title="Messages Deleted",
        description=f"Deleted **{len(deleted)}** messages{' from ' + user.mention if user else ''}.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE)
    )
    await ctx.send(embed=embed, delete_after=3)

    await send_mod_log(ctx.guild, ctx.author, "Clear Messages",
                     f"Deleted {len(deleted)} messages{' from ' + user.name if user else ''}", ctx.author)


# --- Error Handlers ---

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await send_permission_error(ctx)
    elif isinstance(error, commands.MemberNotFound):
        await send_user_not_found(ctx)
    elif isinstance(error, commands.BadArgument):
        await send_invalid_usage(ctx, ctx.command.name)
    else:
        await ctx.send(f"An error occurred: {error}", delete_after=3)
        print(f"An unexpected error occurred: {error}")


# --- Run Bot ---
# Get the bot token from the environment variable.
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if DISCORD_BOT_TOKEN is None:
    print("Error: The DISCORD_BOT_TOKEN environment variable is not set.")
else:
    bot.run(DISCORD_BOT_TOKEN)

