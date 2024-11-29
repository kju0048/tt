import discord
from discord.ext import commands, tasks
import asyncio
import datetime
import json
import os

# Initialize bot intents
intents = discord.Intents.default()
intents.members = True 
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# Channel ID where attendance messages will be sent
channel_id = 1311973759179030548  # Replace with your actual channel ID

# Mapping of weekdays to their respective emoji IDs
weekdays_emojis = {
    "Mon": 1311954291287654410,  # Monday <:Mon:1311954291287654410>
    "Tue": 1311954288905551912,  # Tuesday <:Tue:1311954288905551912>
    "Wed": 1311954287449866300,  # Wednesday <:Wed:1311954287449866300>
    "Thu": 1311954285625479229,  # Thursday <:Thu:1311954285625479229>
    "Fri": 1311954284027318312,  # Friday <:Fri:1311954284027318312>
    "Sat": 1311954282236350556,  # Saturday <:Sat:1311954282236350556>
    "Sun": 1311954280214958201   # Sunday <:Sun:1311954280214958201>
}

# Attendance JSON file path
ATTENDANCE_FILE = "attendance.json"

# Lock for managing concurrent access to the JSON file
attendance_lock = asyncio.Lock()

# Variables for testing and tracking weeks
test_time = None  # For testing purposes
previous_week = None  # To store the previous week number
weekly_message = None  # To store the latest weekly message

def get_current_time():
    """Returns the current time or the test time if set."""
    if test_time:
        return test_time
    return datetime.datetime.now()

async def load_attendance():
    """Loads attendance data from the JSON file. Initializes the file if it doesn't exist."""
    async with attendance_lock:
        if not os.path.exists(ATTENDANCE_FILE):
            # Initialize with empty lists for each day
            attendance_data = {day: [] for day in weekdays_emojis.keys()}
            with open(ATTENDANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(attendance_data, f, ensure_ascii=False, indent=4)
            return attendance_data
        else:
            with open(ATTENDANCE_FILE, "r", encoding="utf-8") as f:
                try:
                    attendance_data = json.load(f)
                except json.JSONDecodeError:
                    # If JSON is corrupted, reinitialize
                    attendance_data = {day: [] for day in weekdays_emojis.keys()}
                    with open(ATTENDANCE_FILE, "w", encoding="utf-8") as fw:
                        json.dump(attendance_data, fw, ensure_ascii=False, indent=4)
                return attendance_data

async def save_attendance(data):
    """Saves attendance data to the JSON file."""
    async with attendance_lock:
        with open(ATTENDANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

async def reset_attendance_and_report(guild):
    """Processes the current attendance data, reports statistics, and resets the JSON file."""
    attendance_data = await load_attendance()
    
    # Dictionary to store user attendance counts
    user_attendance = {}
    
    # Iterate through each day and each user who attended
    for day, users in attendance_data.items():
        for user_id in users:
            if user_id not in user_attendance:
                user_attendance[user_id] = 0
            user_attendance[user_id] += 1

    # Get all members in the guild excluding the bot
    all_members = [member for member in guild.members if not member.bot]

    # Prepare the report with all members, defaulting to 0 if they didn't attend
    report_lines = ["**출석 통계:**"]
    for member in all_members:
        count = user_attendance.get(member.id, 0)
        report_lines.append(f"{member.display_name}: {count}일 출석")

    report_message = "\n".join(report_lines)

    # Send the report to the designated channel
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(report_message)
    else:
        print(f"Channel with ID {channel_id} not found.")

    # Reset the attendance data
    attendance_data = {day: [] for day in weekdays_emojis.keys()}
    await save_attendance(attendance_data)

@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f'Logged in as {bot.user}')
    await load_attendance()  # Ensure the attendance file is initialized
    weekly_task.start()  # Start the weekly task

@tasks.loop(seconds=10)  # Check every minute to reduce CPU usage
async def weekly_task():
    global weekly_message, previous_week
    now = get_current_time()
    current_week = now.isocalendar()[1]  # ISO week number

    # Check if it's Monday and a new week has started
    if now.weekday() == 0 and current_week != previous_week:
        guild = bot.guilds[0]  # Assumes the bot is only in one guild
        if previous_week is not None:
            # Process and report the previous week's attendance before starting a new week
            await reset_attendance_and_report(guild)

        # Send the new weekly attendance message
        channel = bot.get_channel(channel_id)
        if channel is not None:
            start_date = now
            end_date = start_date + datetime.timedelta(days=6)
            weekly_message = await channel.send(
                f"{start_date.year}년 {start_date.month}월 {start_date.day}일 월요일 ~ "
                f"{end_date.year}년 {end_date.month}월 {end_date.day}일 일요일 출석체크"
            )
            for name, emoji_id in weekdays_emojis.items():
                try:
                    emoji = bot.get_emoji(emoji_id)
                    if emoji:
                        await weekly_message.add_reaction(emoji)
                    else:
                        print(f"이모지 ID {emoji_id}를 찾을 수 없습니다.")
                except discord.HTTPException as e:
                    print(f"Failed to add reaction: {e}")
            previous_week = current_week

@weekly_task.before_loop
async def before_weekly_task():
    """Wait until the bot is ready before starting the weekly task."""
    await bot.wait_until_ready()

@bot.event
async def on_raw_reaction_add(payload):
    """Handles reactions added to messages."""
    global weekly_message
    if weekly_message is None or payload.message_id != weekly_message.id:
        return

    now = get_current_time()
    current_weekday = now.weekday()  # 0 = Monday, 6 = Sunday
    user_id = payload.user_id

    if user_id == bot.user.id:
        return  # Ignore bot's own reactions

    # Map weekday index to day name
    day_names = list(weekdays_emojis.keys())
    if current_weekday < 0 or current_weekday > 6:
        print(f"Invalid current_weekday: {current_weekday}")
        return
    day_name = day_names[current_weekday]
    expected_emoji_id = weekdays_emojis[day_name]

    if payload.emoji.id != expected_emoji_id:
        # Incorrect emoji reacted; remove the reaction
        channel = bot.get_channel(payload.channel_id)
        if channel is not None:
            try:
                message = await channel.fetch_message(payload.message_id)
                guild = bot.guilds[0]  # Assumes the bot is only in one guild
                member = guild.get_member(user_id) if guild else None
                if member:
                    await message.remove_reaction(payload.emoji, member)
            except discord.Forbidden:
                print(f"Permission error: Cannot remove reaction from user ID {user_id}")
            except discord.HTTPException as e:
                print(f"Failed to remove reaction: {e}")
        return

    # Correct emoji reacted; update attendance
    attendance_data = await load_attendance()
    if user_id not in attendance_data[day_name]:
        attendance_data[day_name].append(user_id)
        await save_attendance(attendance_data)

@bot.command()
@commands.has_permissions(administrator=True)
async def set_time(ctx, year: int, month: int, day: int, hour: int, minute: int, second: int):
    """Sets a test time for debugging purposes."""
    global test_time
    test_time = datetime.datetime(year, month, day, hour, minute, second)
    await ctx.send(f"시간이 {test_time}으로 설정되었습니다.")

@bot.command()
@commands.has_permissions(administrator=True)
async def clear_time(ctx):
    """Clears the test time to use the system's current time."""
    global test_time
    test_time = None
    await ctx.send("시간 설정이 초기화되었습니다. 현재 시스템 시간을 사용합니다.")


# Load the Discord bot token from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # Ensure this environment variable is set

if TOKEN is None:
    print("Error: DISCORD_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
else:
    bot.run(TOKEN)
