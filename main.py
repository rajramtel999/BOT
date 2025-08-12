import discord
from discord.ext import commands
import datetime
import motor.motor_asyncio
import pytz
import os

# --- CONFIGURATION --- #
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

# Command usage info
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
        "desc":
        "Times out a user for a duration (s,m,h,d). (Moderator/Admin only)"
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
        "usage":
        "69 clear [@user] <amount>",
        "example":
        "69 clear 50\n69 clear @User 30",
        "desc":
        "Deletes messages. Delete last <amount> or last <amount> from user. (Moderator/Admin only)"
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
    embed = discord.Embed(title=f"Usage: {info['usage']}",
                          color=discord.Color.red())
    embed.add_field(name="Example", value=info['example'], inline=False)
    embed.add_field(name="Description", value=info['desc'], inline=False)
    return embed


async def send_permission_error(ctx):
    await ctx.send(embed=discord.Embed(
        description="🚫 You don't have permission to use this command.",
        color=discord.Color.red()),
                   delete_after=3)


async def send_user_not_found(ctx):
    await ctx.send(embed=discord.Embed(description="❌ User not found.",
                                       color=discord.Color.red()),
                   delete_after=3)


async def send_invalid_usage(ctx, command_name):
    embed = get_command_usage_embed(command_name)
    if embed:
        await ctx.send(embed=embed, delete_after=3)
    else:
        await ctx.send("Invalid command usage.", delete_after=3)


async def send_mod_log(guild, user, action, reason, moderator):
    log_channel_id_doc = await db[LOG_CHANNEL_COLLECTION].find_one(
        {"guild_id": guild.id})
    if log_channel_id_doc:
        log_channel = guild.get_channel(log_channel_id_doc["channel_id"])
        if log_channel:
            embed = discord.Embed(
                title=f"👤 {action} | {user}",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(KATHMANDU_TIMEZONE))
            embed.add_field(name="User", value=user.mention, inline=False)
            embed.add_field(name="Reason",
                            value=reason or "No reason provided",
                            inline=False)
            embed.add_field(name="Moderator",
                            value=moderator.mention,
                            inline=False)
            await log_channel.send(embed=embed)


# --- AFK Functions ---


async def set_afk(user: discord.Member, reason: str):
    current_nick = user.display_name
    await db[AFK_COLLECTION].update_one(
        {"user_id": user.id},
        {"$set": {
            "reason": reason,
            "original_nick": current_nick
        }},
        upsert=True)
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

    # AFK removal on message send
    afk_reason = await is_afk(message.author)
    if afk_reason:
        await remove_afk(message.author)
        await message.channel.send(
            f"Welcome back, {message.author.mention}! Your AFK status has been removed.",
            delete_after=3)

    # Notify when mentioning AFK users
    for member in message.mentions:
        reason = await is_afk(member)
        if reason and member.id != message.author.id:
            await message.channel.send(
                f"{member.mention} is currently AFK. Reason: {reason}",
                delete_after=3)

    await bot.process_commands(message)


# --- Commands ---


@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="Area 69 Bot Commands",
        description=
        f"Prefix: `69`\n\n**Join Our Discord Server:**\nhttps://discord.gg/9RJK4TmwrW\n\nHere are the available commands:",
        color=discord.Color.blue())
    for cmd, info in COMMAND_INFOS.items():
        embed.add_field(name=info["usage"], value=info["desc"], inline=False)
    embed.set_footer(text="Developed By : U　N　K　N　O　W　N　ツ")
    await ctx.send(embed=embed, delete_after=10)


@bot.command()
async def afk(ctx, *, reason="No reason given."):
    if await is_afk(ctx.author):
        await remove_afk(ctx.author)
        await ctx.send(
            f"Welcome back, {ctx.author.mention}! Your AFK status has been removed.",
            delete_after=3)
    else:
        await set_afk(ctx.author, reason)
        await ctx.send(f"{ctx.author.mention} is now AFK. Reason: {reason}",
                       delete_after=3)


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "kick")
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="User Kicked",
            description=
            f"{member.mention} was kicked by {ctx.author.mention}\nReason: {reason or 'No reason provided'}",
            color=discord.Color.red())
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, member, "Kick", reason, ctx.author)
    except discord.Forbidden:
        await send_permission_error(ctx)


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "ban")
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="User Banned",
            description=
            f"{member.mention} was banned by {ctx.author.mention}\nReason: {reason or 'No reason provided'}",
            color=discord.Color.red())
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, member, "Ban", reason, ctx.author)
    except discord.Forbidden:
        await send_permission_error(ctx)


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, *, user_id_or_name=None):
    if not user_id_or_name:
        return await send_invalid_usage(ctx, "unban")

    banned_users = await ctx.guild.bans()
    user = None
    try:
        user = discord.Object(id=int(user_id_or_name))
    except ValueError:
        for ban_entry in banned_users:
            if user_id_or_name.lower() == str(ban_entry.user).lower():
                user = ban_entry.user
                break
    if user is None:
        return await send_user_not_found(ctx)

    try:
        await ctx.guild.unban(user)
        embed = discord.Embed(
            title="User Unbanned",
            description=f"{user.mention} was unbanned by {ctx.author.mention}",
            color=discord.Color.green())
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, user, "Unban", None, ctx.author)
    except discord.Forbidden:
        await send_permission_error(ctx)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx,
                  member: discord.Member = None,
                  duration: str = None,
                  *,
                  reason=None):
    if not member or not duration:
        return await send_invalid_usage(ctx, "timeout")

    time_unit = duration[-1]
    try:
        time_amount = int(duration[:-1])
    except:
        return await send_invalid_usage(ctx, "timeout")

    if time_unit == "s":
        delta = datetime.timedelta(seconds=time_amount)
    elif time_unit == "m":
        delta = datetime.timedelta(minutes=time_amount)
    elif time_unit == "h":
        delta = datetime.timedelta(hours=time_amount)
    elif time_unit == "d":
        delta = datetime.timedelta(days=time_amount)
    else:
        return await send_invalid_usage(ctx, "timeout")

    try:
        until = datetime.datetime.utcnow() + delta
        await member.timeout(until=until, reason=reason)
        embed = discord.Embed(
            title="User Timed Out",
            description=
            f"{member.mention} was timed out by {ctx.author.mention} for {duration}\nReason: {reason or 'No reason provided'}",
            color=discord.Color.orange())
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, member, "Timeout", reason, ctx.author)
    except discord.Forbidden:
        await send_permission_error(ctx)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def removetimeout(ctx, member: discord.Member = None, *, reason=None):
    if not member:
        return await send_invalid_usage(ctx, "removetimeout")
    try:
        await member.timeout(None, reason=reason)
        embed = discord.Embed(
            title="Timeout Removed",
            description=
            f"Timeout removed for {member.mention} by {ctx.author.mention}\nReason: {reason or 'No reason provided'}",
            color=discord.Color.green())
        await ctx.send(embed=embed)
        await send_mod_log(ctx.guild, member, "Timeout Removed", reason,
                           ctx.author)
    except discord.Forbidden:
        await send_permission_error(ctx)


@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member = None, *, reason=None):
    if not member or not reason:
        return await send_invalid_usage(ctx, "warn")

    warn_data = {
        "guild_id": ctx.guild.id,
        "user_id": member.id,
        "moderator_id": ctx.author.id,
        "reason": reason,
        "timestamp": datetime.datetime.now(KATHMANDU_TIMEZONE)
    }
    await db[WARNINGS_COLLECTION].insert_one(warn_data)

    embed = discord.Embed(
        title="User Warned",
        description=
        f"{member.mention} was warned by {ctx.author.mention}\nReason: {reason}",
        color=discord.Color.orange())
    await ctx.send(embed=embed)
    await send_mod_log(ctx.guild, member, "Warn", reason, ctx.author)


@bot.command()
@commands.has_permissions(kick_members=True)
async def warns(ctx, member: discord.Member = None):
    if not member:
        return await send_invalid_usage(ctx, "warns")

    warns = db[WARNINGS_COLLECTION].find({
        "guild_id": ctx.guild.id,
        "user_id": member.id
    })
    warns_list = await warns.to_list(length=100)

    if not warns_list:
        await ctx.send(f"{member.mention} has no warnings.")
        return

    embed = discord.Embed(title=f"Warnings for {member}",
                          color=discord.Color.orange())

    for i, warn in enumerate(warns_list, 1):
        mod = ctx.guild.get_member(warn["moderator_id"])
        mod_name = mod.display_name if mod else "Unknown Moderator"
        reason = warn["reason"]
        timestamp = warn["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(
            name=f"Warning {i}",
            value=f"By: {mod_name}\nReason: {reason}\nDate: {timestamp}",
            inline=False)

    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, member: discord.Member = None, amount: int = None):
    if amount is None:
        # maybe member is amount param here
        if isinstance(member, int):
            amount = member
            member = None
        else:
            return await send_invalid_usage(ctx, "clear")

    if amount > 100:
        amount = 100

    def check(m):
        if member:
            return m.author == member
        return True

    deleted = await ctx.channel.purge(limit=amount, check=check)
    await ctx.send(f"Deleted {len(deleted)} message(s).", delete_after=5)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def setlogschannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await send_invalid_usage(ctx, "setlogschannel")
    await db[LOG_CHANNEL_COLLECTION].update_one(
        {"guild_id": ctx.guild.id}, {"$set": {
            "channel_id": channel.id
        }},
        upsert=True)
    await ctx.send(f"Logs channel set to {channel.mention}")


# Run the bot with your token from environment variable
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if DISCORD_BOT_TOKEN is None:
    print("Error: The DISCORD_BOT_TOKEN environment variable is not set.")
else:
    bot.run(DISCORD_BOT_TOKEN)
