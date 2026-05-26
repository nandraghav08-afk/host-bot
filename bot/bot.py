import os
import re
import random
import datetime
import discord
from discord import app_commands
from discord.ext import commands

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── Channel names (lowercase as Discord stores them) ─────────────────────────
BOT_CHAT_NAME = "bot-chat"
EMPEROR_CHAT_NAME = "emperor-ship"   # partial match — covers "👑emperor-ship-❤️‍🔥"

# ── Bad words list ────────────────────────────────────────────────────────────
BAD_WORDS = [
    "fuck", "fucker", "fucking", "f**k",
    "shit", "bitch", "bastard", "asshole",
    "cunt", "dick", "pussy", "slut", "whore",
    "nigga", "nigger", "faggot",
]
BAD_WORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in BAD_WORDS) + r")\b",
    re.IGNORECASE,
)

# ── Link / URL detection ──────────────────────────────────────────────────────
LINK_PATTERN = re.compile(
    r"(https?://\S+|www\.\S+|discord\.gg/\S+)",
    re.IGNORECASE,
)

# ── In-memory warning tracker {user_id: warning_count} ───────────────────────
warnings: dict[int, int] = {}

# ── Pre-written jokes ─────────────────────────────────────────────────────────
JOKES = [
    "Why don't scientists trust atoms? Because they make up everything! 😄",
    "I told my computer I needed a break. Now it won't stop sending me Kit-Kat ads. 🍫",
    "Why do programmers prefer dark mode? Because light attracts bugs! 🐛",
    "I asked the librarian if they had books about paranoia. She whispered, 'They're right behind you!' 👀",
    "Why did the scarecrow win an award? Because he was outstanding in his field! 🌾",
    "I'm reading a book about anti-gravity. It's impossible to put down! 📚",
    "Why did the bicycle fall over? Because it was two-tired! 🚲",
    "What do you call a fake noodle? An impasta! 🍝",
    "Why can't you give Elsa a balloon? Because she'll let it go! 🎈",
    "I used to hate facial hair, but then it grew on me. 🧔",
    "Why did the math book look so sad? Because it had too many problems! 📖",
    "What do you call cheese that isn't yours? Nacho cheese! 🧀",
    "Why did the golfer bring an extra pair of pants? In case he got a hole in one! ⛳",
    "I told my wife she was drawing her eyebrows too high. She looked surprised! 😲",
    "What do you call a sleeping dinosaur? A dino-snore! 🦕",
    "Why don't eggs tell jokes? They'd crack each other up! 🥚",
    "What's a vampire's favourite fruit? A blood orange! 🍊",
    "Why did the coffee file a police report? It got mugged! ☕",
    "What do you call a bear with no teeth? A gummy bear! 🐻",
    "Why did the stadium get hot after the game? All the fans left! 🏟️",
]

# ── Pre-written story templates ───────────────────────────────────────────────
STORY_TEMPLATES = [
    "Once upon a time, {name} walked into a room full of penguins. Nobody questioned it. The penguins didn't either. 🐧",
    "Legend has it that {name} once stared at a loading screen for so long it started staring back. 👁️",
    "They say {name} once tried to Google themselves and the internet crashed from the sheer awesomeness. 💥",
    "There's a tale of {name} who ordered a pizza and it arrived before they even finished typing the address. 🍕",
    "It is written that {name} once told a joke so funny that even the Wi-Fi router started laughing and disconnected. 📶",
    "Historians believe {name} once high-fived so hard that it created a small gust of wind felt three towns over. 💨",
    "The ancient scrolls speak of {name} who could parallel park on the first try, every single time. 🚗",
    "Rumour has it {name} once finished a to-do list entirely. Scientists are still investigating. 📋",
    "It is said that {name} once replied to an email within 30 seconds. The recipient fainted from shock. 📧",
    "Folk songs tell of {name} who found matching socks on the first drawer dig. A true hero. 🧦",
]


# ── Forbidden topic detection ─────────────────────────────────────────────────
FORBIDDEN_PATTERNS = re.compile(
    r"\b("
    r"how.{0,20}(make|create|build|code|program|develop|host|deploy|run|setup|set up).{0,30}bot|"
    r"how.{0,20}(host|deploy|run|setup|set up).{0,30}(ai|model|openai|gpt|llm)|"
    r"(make|create|build|code).{0,20}(discord|telegram|slack).{0,20}bot|"
    r"bot.{0,20}(token|api.?key|client.?id|client.?secret)|"
    r"(discord|developer).{0,20}portal|"
    r"how.{0,20}(get|obtain).{0,20}(token|api.?key)|"
    r"(vps|cloud|server).{0,20}(host|deploy|setup)|"
    r"replit.{0,20}(host|deploy|bot)|"
    r"host.{0,20}(bot|ai|model)"
    r")\b",
    re.IGNORECASE | re.DOTALL,
)

TIMEOUT_LINK = datetime.timedelta(minutes=10)
TIMEOUT_ABUSE = datetime.timedelta(minutes=5)
TIMEOUT_FORBIDDEN = datetime.timedelta(minutes=3)


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_bot_chat(channel: discord.TextChannel) -> bool:
    return channel.name.lower() == BOT_CHAT_NAME

def is_emperor_chat(channel: discord.TextChannel) -> bool:
    return EMPEROR_CHAT_NAME in channel.name.lower()

async def simple_reply(message: discord.Message, content: str) -> None:
    """Reply with a random joke, or a story featuring any mentioned names."""
    # Collect display names of mentioned members (excluding the bot itself)
    mentioned_names = [
        m.display_name for m in message.mentions if not m.bot
    ]

    if mentioned_names:
        # Pick a random name from the mentions and build a story around them
        name = random.choice(mentioned_names)
        reply = random.choice(STORY_TEMPLATES).format(name=name)
    else:
        reply = random.choice(JOKES)

    await message.reply(reply)


async def apply_timeout(member: discord.Member, duration: datetime.timedelta, reason: str) -> bool:
    """Apply a timeout to a member. Returns True if successful."""
    try:
        await member.timeout(duration, reason=reason)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False

async def add_warning(message: discord.Message, member: discord.Member, reason: str) -> None:
    """Add a warning; timeout after 2 warnings."""
    uid = member.id
    warnings[uid] = warnings.get(uid, 0) + 1
    count = warnings[uid]

    if count >= 2:
        # Reset warnings and apply timeout
        warnings[uid] = 0
        success = await apply_timeout(member, TIMEOUT_ABUSE, f"Auto-timeout after {count} warnings: {reason}")
        embed = discord.Embed(title="⏱️ Member Timed Out", color=discord.Color.red())
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Reason", value=f"{reason} (reached {count} warnings)", inline=False)
        embed.add_field(name="Duration", value="5 minutes", inline=False)
        await message.channel.send(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warnings", value=f"{count}/2 (timeout on next warning)", inline=False)
        await message.channel.send(embed=embed)


# ── Main message event ────────────────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    # Ignore DMs and bot's own messages
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.TextChannel):
        await bot.process_commands(message)
        return

    member = message.author
    content = message.content

    # ── 1. Bad word detection (any channel) ───────────────────────────────────
    if BAD_WORD_PATTERN.search(content):
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        await add_warning(message, member, "Abusive language")
        return  # stop further processing

    # ── 2. Forbidden topic detection (any channel) ────────────────────────────
    if FORBIDDEN_PATTERNS.search(content):
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        success = await apply_timeout(member, TIMEOUT_FORBIDDEN, "Asked about forbidden topics (bot/AI hosting)")
        embed = discord.Embed(
            title="🚫 Topic Not Allowed",
            description=(
                f"Hey {member.mention}, that topic isn't something I can help with here. "
                "Please keep the conversation appropriate. "
                "A 3-minute timeout has been applied. 🙏"
            ),
            color=discord.Color.dark_red(),
        )
        await message.channel.send(embed=embed)
        return

    # ── 3. Link detection (any channel) ───────────────────────────────────────
    if LINK_PATTERN.search(content):
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        success = await apply_timeout(member, TIMEOUT_LINK, "Posted a link without permission")
        embed = discord.Embed(title="🔗 Link Removed & Timeout Applied", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Reason", value="Sending links is not allowed", inline=False)
        embed.add_field(name="Duration", value="10 minutes", inline=False)
        await message.channel.send(embed=embed)
        return  # stop further processing

    # ── Process prefix commands before AI handling ────────────────────────────
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # ── 3. #bot-chat: respond to every message EXCEPT replies ─────────────────
    if is_bot_chat(message.channel):
        if message.reference is not None:
            # It's a reply to someone else — stay silent
            return
        await simple_reply(message, content)
        return

    # ── 4. #👑emperor-ship: only respond when bot is pinged ───────────────────
    if is_emperor_chat(message.channel):
        if bot.user in message.mentions:
            # Strip the bot mention from the message and respond
            text = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
            if not text:
                text = "Hey! How can I help you?"
            await simple_reply(message, text)
        else:
            # Not pinged — remind them to use #bot-chat
            await message.reply(
                f"Hey {member.mention}! I only respond here when you ping me. "
                f"Head over to **#bot-chat** for a free chat! 😊",
                delete_after=8,
            )
        return


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready! Slash commands synced.")


# ── Prefix commands ───────────────────────────────────────────────────────────

@bot.command(name="ask")
async def ask(ctx: commands.Context, *, question: str):
    """Ask the bot something fun. Usage: !ask <your question>"""
    await simple_reply(ctx.message, question)


@bot.command(name="warnings")
@commands.has_permissions(moderate_members=True)
async def check_warnings(ctx: commands.Context, member: discord.Member):
    """Check warnings for a user. Usage: !warnings @user"""
    count = warnings.get(member.id, 0)
    await ctx.reply(f"{member.mention} has **{count}** warning(s).")


@bot.command(name="clearwarnings")
@commands.has_permissions(moderate_members=True)
async def clear_warnings(ctx: commands.Context, member: discord.Member):
    """Clear warnings for a user. Usage: !clearwarnings @user"""
    warnings.pop(member.id, None)
    await ctx.reply(f"Cleared all warnings for {member.mention}.")


@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    """Kick a member. Usage: !kick @user [reason]"""
    if member == ctx.author:
        await ctx.reply("You cannot kick yourself.")
        return
    if member.top_role >= ctx.author.top_role:
        await ctx.reply("You cannot kick someone with an equal or higher role.")
        return
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="Member Kicked", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=str(ctx.author))
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.reply("I don't have permission to kick that member.")


@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban(ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
    """Ban a member. Usage: !ban @user [reason]"""
    if member == ctx.author:
        await ctx.reply("You cannot ban yourself.")
        return
    if member.top_role >= ctx.author.top_role:
        await ctx.reply("You cannot ban someone with an equal or higher role.")
        return
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(title="Member Banned", color=discord.Color.red())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=str(ctx.author))
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.reply("I don't have permission to ban that member.")


@bot.command(name="unban")
@commands.has_permissions(ban_members=True)
async def unban(ctx: commands.Context, user_id: int):
    """Unban a user by ID. Usage: !unban <user_id>"""
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.reply(f"Unbanned {user} ({user_id}).")
    except discord.NotFound:
        await ctx.reply("User not found or not banned.")
    except discord.Forbidden:
        await ctx.reply("I don't have permission to unban users.")


@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute(ctx: commands.Context, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided"):
    """Timeout a member. Usage: !mute @user [minutes] [reason]"""
    if member == ctx.author:
        await ctx.reply("You cannot mute yourself.")
        return
    if member.top_role >= ctx.author.top_role:
        await ctx.reply("You cannot mute someone with an equal or higher role.")
        return
    duration = datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(duration, reason=reason)
        embed = discord.Embed(title="Member Muted (Timeout)", color=discord.Color.yellow())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Duration", value=f"{minutes} minute(s)")
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Moderator", value=str(ctx.author))
        await ctx.send(embed=embed)
    except discord.Forbidden:
        await ctx.reply("I don't have permission to timeout that member.")


@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute(ctx: commands.Context, member: discord.Member):
    """Remove timeout from a member. Usage: !unmute @user"""
    try:
        await member.timeout(None)
        await ctx.reply(f"Removed timeout from {member}.")
    except discord.Forbidden:
        await ctx.reply("I don't have permission to remove the timeout.")


@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge(ctx: commands.Context, amount: int):
    """Delete a number of messages. Usage: !purge <amount>"""
    if amount < 1 or amount > 100:
        await ctx.reply("Please provide a number between 1 and 100.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(f"Deleted {len(deleted) - 1} message(s).")
    await msg.delete(delay=3)


@bot.command(name="bothelp")
async def bothelp(ctx: commands.Context):
    """Show all available commands."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are all available commands:",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🤖 Fun",
        value=(
            "`!ask <question>` — Get a fun joke or story"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Auto-Moderation (automatic)",
        value=(
            "• Links → deleted + 10 min timeout\n"
            "• Bad words → deleted + warning (2nd = 5 min timeout)\n"
            "• Replies in **#bot-chat** → bot stays silent\n"
            "• **#👑emperor-ship** → bot only responds when pinged"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔨 Moderation Commands",
        value=(
            "`!kick @user [reason]`\n"
            "`!ban @user [reason]`\n"
            "`!unban <user_id>`\n"
            "`!mute @user [minutes] [reason]`\n"
            "`!unmute @user`\n"
            "`!purge <amount>`\n"
            "`!warnings @user`\n"
            "`!clearwarnings @user`"
        ),
        inline=False,
    )
    embed.set_footer(text="Prefix: !")
    await ctx.send(embed=embed)


@kick.error
@ban.error
@unban.error
@mute.error
@unmute.error
@purge.error
@check_warnings.error
@clear_warnings.error
async def mod_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("You don't have permission to use this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.reply("Member not found. Make sure to @mention them.")
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("Invalid argument. Check usage with `!bothelp`.")
    else:
        await ctx.reply(f"An error occurred: {error}")


# ── Owner-only slash commands ─────────────────────────────────────────────────

def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == interaction.guild.owner_id


async def owner_check(interaction: discord.Interaction) -> bool:
    if not is_owner(interaction):
        await interaction.response.send_message(
            "❌ Only the server owner can use this command.", ephemeral=True
        )
        return False
    return True


@bot.tree.command(name="kick", description="[Owner only] Kick a member")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def slash_kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await owner_check(interaction):
        return
    if member == interaction.user:
        await interaction.response.send_message("You cannot kick yourself.", ephemeral=True)
        return
    try:
        await member.kick(reason=reason)
        embed = discord.Embed(title="Member Kicked", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to kick that member.", ephemeral=True)


@bot.tree.command(name="ban", description="[Owner only] Ban a member")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def slash_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await owner_check(interaction):
        return
    if member == interaction.user:
        await interaction.response.send_message("You cannot ban yourself.", ephemeral=True)
        return
    try:
        await member.ban(reason=reason)
        embed = discord.Embed(title="Member Banned", color=discord.Color.red())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to ban that member.", ephemeral=True)


@bot.tree.command(name="unban", description="[Owner only] Unban a user by ID")
@app_commands.describe(user_id="ID of the user to unban")
async def slash_unban(interaction: discord.Interaction, user_id: str):
    if not await owner_check(interaction):
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"Unbanned {user} ({user_id}).")
    except (discord.NotFound, ValueError):
        await interaction.response.send_message("User not found or not banned.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to unban users.", ephemeral=True)


@bot.tree.command(name="mute", description="[Owner only] Timeout (mute) a member")
@app_commands.describe(member="Member to mute", minutes="Duration in minutes", reason="Reason")
async def slash_mute(interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason provided"):
    if not await owner_check(interaction):
        return
    if member == interaction.user:
        await interaction.response.send_message("You cannot mute yourself.", ephemeral=True)
        return
    try:
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        embed = discord.Embed(title="Member Muted", color=discord.Color.yellow())
        embed.add_field(name="User", value=f"{member} ({member.id})")
        embed.add_field(name="Duration", value=f"{minutes} minute(s)")
        embed.add_field(name="Reason", value=reason)
        await interaction.response.send_message(embed=embed)
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to timeout that member.", ephemeral=True)


@bot.tree.command(name="unmute", description="[Owner only] Remove timeout from a member")
@app_commands.describe(member="Member to unmute")
async def slash_unmute(interaction: discord.Interaction, member: discord.Member):
    if not await owner_check(interaction):
        return
    try:
        await member.timeout(None)
        await interaction.response.send_message(f"Removed timeout from {member.mention}.")
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to remove the timeout.", ephemeral=True)


@bot.tree.command(name="purge", description="[Owner only] Delete a number of messages (max 100)")
@app_commands.describe(amount="Number of messages to delete")
async def slash_purge(interaction: discord.Interaction, amount: int):
    if not await owner_check(interaction):
        return
    if amount < 1 or amount > 100:
        await interaction.response.send_message("Please provide a number between 1 and 100.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)


@bot.tree.command(name="warn", description="[Owner only] Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for warning")
async def slash_warn(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if not await owner_check(interaction):
        return
    uid = member.id
    warnings[uid] = warnings.get(uid, 0) + 1
    count = warnings[uid]
    if count >= 2:
        warnings[uid] = 0
        try:
            await member.timeout(TIMEOUT_ABUSE, reason=f"Auto-timeout after {count} warnings: {reason}")
        except discord.Forbidden:
            pass
        embed = discord.Embed(title="⏱️ Member Timed Out", color=discord.Color.red())
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Reason", value=f"{reason} ({count} warnings)", inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(title="⚠️ Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="User", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Warnings", value=f"{count}/2", inline=False)
        await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clearwarnings", description="[Owner only] Clear all warnings for a member")
@app_commands.describe(member="Member whose warnings to clear")
async def slash_clearwarnings(interaction: discord.Interaction, member: discord.Member):
    if not await owner_check(interaction):
        return
    warnings.pop(member.id, None)
    await interaction.response.send_message(f"Cleared all warnings for {member.mention}.", ephemeral=True)


bot.run(DISCORD_TOKEN)
