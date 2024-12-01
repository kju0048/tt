import discord
from discord.ext import tasks
from discord import app_commands
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

# Create bot instance without a command prefix
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Channel ID where attendance messages will be sent
channel_id = 1312012147579944960  # Replace with your actual channel ID

# Mapping of weekdays to their respective emoji
weekdays_emojis = {
    "Mon": '<:001:1312343708187885598>',  
    "Tue": '<:002:1312343716371103844>',  
    "Wed": '<:003:1312343724134498335>',  
    "Thu": '<:004:1312343730585469028>',  
    "Fri": '<:005:1312343740282830890>',  
    "Sat": '<:006:1312343750449827881>',  
    "Sun": '<:007:1312343758355828769>'   
}

# Attendance JSON file paths
ATTENDANCE_FILE = "attendance.json"
CUMULATIVE_ATTENDANCE_FILE = "cumulative_attendance.json"

# Lock for managing concurrent access to the JSON files
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

def get_start_end_dates_previous_week(now=None):
    """Returns the start and end dates of the previous week."""
    if now is None:
        now = get_current_time()
    start_date = now - datetime.timedelta(days=now.weekday() + 7)  # Last Monday
    end_date = start_date + datetime.timedelta(days=6)  # Last Sunday
    return f"{start_date.year}년 {start_date.month}월 {start_date.day}일 월요일 ~ {end_date.year}년 {end_date.month}월 {end_date.day}일 일요일"

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

async def load_cumulative_attendance():
    """Loads cumulative attendance data from the JSON file. Initializes the file if it doesn't exist."""
    async with attendance_lock:
        if not os.path.exists(CUMULATIVE_ATTENDANCE_FILE):
            cumulative_data = {}
            with open(CUMULATIVE_ATTENDANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(cumulative_data, f, ensure_ascii=False, indent=4)
            return cumulative_data
        else:
            with open(CUMULATIVE_ATTENDANCE_FILE, "r", encoding="utf-8") as f:
                try:
                    cumulative_data = json.load(f)
                except json.JSONDecodeError:
                    # If JSON is corrupted, reinitialize
                    cumulative_data = {}
                    with open(CUMULATIVE_ATTENDANCE_FILE, "w", encoding="utf-8") as fw:
                        json.dump(cumulative_data, fw, ensure_ascii=False, indent=4)
                return cumulative_data

async def save_cumulative_attendance(data):
    """Saves cumulative attendance data to the JSON file."""
    async with attendance_lock:
        with open(CUMULATIVE_ATTENDANCE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

async def reset_attendance_and_report(guild):
    """Processes the current attendance data, reports weekly statistics, and resets the JSON file."""
    attendance_data = await load_attendance()

    # Dictionary to store user attendance counts for the week
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
    embed = discord.Embed(
        title="📊 **주간 출석 통계**",
        description=f"**기간:** {get_start_end_dates_previous_week()}",
        color=0x3498db  # You can change the color code as desired
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
    embed.set_footer(text="출석 통계를 확인하세요!")

    for member in all_members:
        weekly_count = user_attendance.get(str(member.id), 0)
        # Retrieve cumulative_count from cumulative_data
        cumulative_data = await load_cumulative_attendance()
        cumulative_count = cumulative_data.get(str(member.id), 0)
        embed.add_field(
            name=member.display_name,
            value=f"📅 이번 주: {weekly_count}일\n📈 총 출석: {cumulative_count}일",
            inline=False
        )

    # Send the report to the designated channel
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send(embed=embed)
    else:
        print(f"Channel with ID {channel_id} not found.")

    # Reset the attendance data for the new week
    attendance_data = {day: [] for day in weekdays_emojis.keys()}
    await save_attendance(attendance_data)

@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f'Logged in as {bot.user}')
    await load_attendance()  # Ensure the attendance file is initialized
    await load_cumulative_attendance()  # Ensure the cumulative attendance file is initialized
    await tree.sync()  # Sync the slash commands with Discord
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
            embed = discord.Embed(
                title="📅 **출석 체크**",
                description=(
                    f"📆 **기간:** {start_date.year}년 {start_date.month}월 {start_date.day}일 월요일 ~ "
                    f"{end_date.year}년 {end_date.month}월 {end_date.day}일 일요일\n"
                    f"✅ 출석을 원하시는 요일에 해당하는 이모지로 반응해주세요."
                ),
                color=0x6ed9fa  # You can change the color code as desired
            )
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
            embed.set_footer(text="출석 체크를 통해 주간 및 누적 출석 통계를 확인하세요!")
            try:
                weekly_message = await channel.send(embed=embed)
                for name, emoji in weekdays_emojis.items():
                    try:
                        await weekly_message.add_reaction(emoji)
                    except discord.HTTPException as e:
                        print(f"Failed to add reaction: {e}")
                previous_week = current_week
            except discord.HTTPException as e:
                print(f"Failed to send attendance message: {e}")

@weekly_task.before_loop
async def before_weekly_task():
    """Wait until the bot is ready before starting the weekly task."""
    await bot.wait_until_ready()

@bot.event
async def on_raw_reaction_add(payload):
    """Handles reactions added to messages and updates cumulative attendance."""
    global weekly_message
    if weekly_message is None or payload.message_id != weekly_message.id:
        return

    now = get_current_time()
    current_weekday = now.weekday()  # 0 = Monday, 6 = Sunday
    user_id = payload.user_id

    if user_id == bot.user.id:
        return  # Ignore bot's own reactions

    # Get the day name based on the current weekday
    day_names = list(weekdays_emojis.keys())
    if current_weekday < 0 or current_weekday > 6:
        print(f"Invalid current_weekday: {current_weekday}")
        return
    day_name = day_names[current_weekday]
    expected_emoji = weekdays_emojis[day_name]

    if str(payload.emoji) != expected_emoji:
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
    user_id_str = str(user_id)
    if user_id_str not in attendance_data[day_name]:
        attendance_data[day_name].append(user_id_str)
        await save_attendance(attendance_data)

        # Load cumulative attendance data
        cumulative_data = await load_cumulative_attendance()

        # Update cumulative count
        if user_id_str in cumulative_data:
            cumulative_data[user_id_str] += 1
        else:
            cumulative_data[user_id_str] = 1

        await save_cumulative_attendance(cumulative_data)

# === Slash Commands Section ===

@tree.command(name="시간설정", description="디버깅을 위한 테스트 시간을 설정합니다.")
@app_commands.describe(year="연도", month="월", day="일", hour="시 (24시간)", minute="분", second="초")
@app_commands.default_permissions(administrator=True)
async def set_time(interaction: discord.Interaction, year: int, month: int, day: int, hour: int, minute: int, second: int):
    """Sets a test time for debugging purposes."""
    global test_time
    # 응답을 연기하여 3초 이내에 응답하지 않더라도 시간이 충분히 주어지도록 함
    await interaction.response.defer(ephemeral=True)
    try:
        test_time = datetime.datetime(year, month, day, hour, minute, second)
        await interaction.followup.send(f"시간이 {test_time}으로 설정되었습니다.", ephemeral=True)
    except ValueError as e:
        await interaction.followup.send(f"잘못된 날짜 또는 시간: {e}", ephemeral=True)

@tree.command(name="시간초기화", description="테스트 시간을 초기화하고 시스템의 현재 시간을 사용합니다.")
@app_commands.default_permissions(administrator=True)
async def clear_time(interaction: discord.Interaction):
    """Clears the test time to use the system's current time."""
    global test_time
    await interaction.response.defer(ephemeral=True)
    test_time = None
    await interaction.followup.send("시간 설정이 초기화되었습니다. 현재 시스템 시간을 사용합니다.", ephemeral=True)

@tree.command(name="누적출석", description="누적 출석 횟수를 표시합니다.")
@app_commands.default_permissions(administrator=True)
async def show_cumulative(interaction: discord.Interaction):
    """Displays the cumulative attendance counts."""
    # 응답을 연기하여 시간이 오래 걸려도 오류가 발생하지 않도록 함
    await interaction.response.defer()

    cumulative_data = await load_cumulative_attendance()
    guild = interaction.guild
    all_members = [member for member in guild.members if not member.bot]

    embed = discord.Embed(
        title="📈 **누적 출석 통계**",
        description="모든 멤버의 누적 출석 일수를 확인하세요.",
        color=0x6ed9fa  # You can change the color code as desired
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
    embed.set_footer(text="누적 출석 통계를 확인하세요!")

    for member in all_members:
        cumulative_count = cumulative_data.get(str(member.id), 0)
        embed.add_field(
            name=member.display_name,
            value=f"📈 총 출석: {cumulative_count}일",
            inline=False
        )

    # Discord Embed는 최대 25개의 필드만 지원하므로, 이를 고려하여 분할
    fields = embed.fields
    if len(fields) > 25:
        for i in range(0, len(fields), 25):
            partial_embed = discord.Embed(
                title=embed.title,
                description=embed.description,
                color=embed.color
            )
            if embed.thumbnail.url:
                partial_embed.set_thumbnail(url=embed.thumbnail.url)
            partial_embed.set_footer(text=embed.footer.text)
            for field in fields[i:i+25]:
                partial_embed.add_field(name=field.name, value=field.value, inline=field.inline)
            try:
                await interaction.followup.send(embed=partial_embed)
            except discord.HTTPException as e:
                print(f"Failed to send cumulative embed: {e}")
    else:
        try:
            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            print(f"Failed to send cumulative embed: {e}")

@tree.command(name="출석생성", description="요일 이모지와 함께 새로운 출석 체크 메시지를 생성합니다.")
@app_commands.default_permissions(administrator=True)
async def create_attendance_message(interaction: discord.Interaction):
    """Creates a new attendance check message with weekday emojis."""
    global weekly_message, previous_week
    # 응답을 연기하여 시간이 오래 걸려도 오류가 발생하지 않도록 함
    await interaction.response.defer(ephemeral=True)
    now = get_current_time()
    start_date = now - datetime.timedelta(days=now.weekday())  # This week's Monday
    end_date = start_date + datetime.timedelta(days=6)  # This week's Sunday

    channel = bot.get_channel(channel_id)
    if channel is None:
        await interaction.followup.send(f"채널 ID {channel_id}을(를) 찾을 수 없습니다.", ephemeral=True)
        return

    # Attendance Check Embed Message
    embed = discord.Embed(
        title="📅 **출석 체크**",
        description=(
            f"📆 **기간:** {start_date.year}년 {start_date.month}월 {start_date.day}일 월요일 ~ "
            f"{end_date.year}년 {end_date.month}월 {end_date.day}일 일요일\n"
            f"✅ 출석을 원하시는 요일에 해당하는 이모지로 반응해주세요."
        ),
        color=0x6ed9fa  # You can change the color code as desired
    )
    embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else None)
    embed.set_footer(text="출석 체크를 통해 주간 및 누적 출석 통계를 확인하세요!")
    try:
        weekly_message = await channel.send(embed=embed)
        for emoji in weekdays_emojis.values():
            await weekly_message.add_reaction(emoji)
        previous_week = now.isocalendar()[1]
        # Send a success message to the user via DM
        await interaction.followup.send("출석 체크 메시지가 성공적으로 생성되었습니다.", ephemeral=True)
    except discord.HTTPException as e:
        try:
            await interaction.followup.send(f"메시지 생성에 실패했습니다: {e}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("DM을 보낼 수 없습니다. 봇이 메시지를 보낼 수 있도록 설정해주세요.", ephemeral=True)

@tree.command(name="출석설정", description="특정 메시지 ID를 현재 출석 체크 메시지로 설정합니다.")
@app_commands.describe(message_id="설정할 메시지의 ID")
@app_commands.default_permissions(administrator=True)
async def set_attendance_message(interaction: discord.Interaction, message_id: int):
    """Sets a specific message ID as the current attendance check message."""
    global weekly_message, previous_week
    # 응답을 연기하여 시간이 오래 걸려도 오류가 발생하지 않도록 함
    await interaction.response.defer(ephemeral=True)
    channel = bot.get_channel(channel_id)
    if channel is None:
        await interaction.followup.send(f"채널 ID {channel_id}을(를) 찾을 수 없습니다.", ephemeral=True)
        return

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        await interaction.followup.send(f"메시지 ID {message_id}을(를) 찾을 수 없습니다.", ephemeral=True)
        return
    except discord.HTTPException as e:
        await interaction.followup.send(f"메시지 가져오기 중 오류가 발생했습니다: {e}", ephemeral=True)
        return

    # Check if the message has all required emojis
    for emoji in weekdays_emojis.values():
        if not any(str(reaction.emoji) == emoji for reaction in message.reactions):
            await interaction.followup.send("메시지에 모든 요일 이모지가 추가되어 있지 않습니다.", ephemeral=True)
            return

    weekly_message = message
    previous_week = get_current_time().isocalendar()[1]
    await interaction.followup.send(f"메시지 ID {message_id}을(를) 현재 주의 출석 체크 메시지로 설정했습니다.", ephemeral=True)

@tree.command(name="내출석", description="본인의 누적 출석 횟수를 확인합니다.")
async def my_attendance(interaction: discord.Interaction):
    """Displays the cumulative attendance count for the user."""
    await interaction.response.defer(ephemeral=True)  # 응답 지연 및 에페멀 설정

    cumulative_data = await load_cumulative_attendance()
    user_id_str = str(interaction.user.id)
    cumulative_count = cumulative_data.get(user_id_str, 0)

    # 임베드 메시지 생성
    embed = discord.Embed(
        title="📈 **나의 누적 출석 통계**",
        description="당신의 누적 출석 일수를 확인하세요.",
        color=0x6ed9fa  # 원하는 색상 코드로 변경 가능
    )
    embed.set_thumbnail(url=interaction.user.avatar.url if interaction.user.avatar else None)
    embed.add_field(
        name="👤 사용자",
        value=interaction.user.display_name,
        inline=False
    )
    embed.add_field(
        name="📅 총 출석",
        value=f"{cumulative_count}일",
        inline=False
    )
    embed.set_footer(text="출석 통계를 확인하세요!")

    # 에페멀 응답으로 임베드 전송
    await interaction.followup.send(embed=embed, ephemeral=True)

# === Slash Commands Section End ===

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error):
    """Global error handler for application commands."""
    if isinstance(error, app_commands.CheckFailure):
        # 사용자에게 에페멀 메시지로 권한이 없음을 알림
        await interaction.response.send_message("❌ 권한이 없어 이 명령어를 사용할 수 없습니다.", ephemeral=True)
    else:
        # 다른 오류는 콘솔에 로그
        print(f"Unhandled error: {error}")

# Load the Discord bot token from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # Ensure this environment variable is set

if TOKEN is None:
    print("Error: DISCORD_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
else:
    bot.run(TOKEN)
