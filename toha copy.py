import discord
from discord.ext import commands, tasks
import asyncio
import datetime

intents = discord.Intents.default()
intents.members = True 
intents.messages = True
intents.message_content = True
intents.reactions = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

channel_id = 1311916590479970304  # 채널 ID를 실제로 교체해주세요.
weekdays_emojis = {
    "Mon": 1311954291287654410,  # 월요일 <:Mon:1311954291287654410>
    "Tue": 1311954288905551912,  # 화요일 <:Tue:1311954288905551912>
    "Wed": 1311954287449866300,  # 수요일 <:Wed:1311954287449866300>
    "Thu": 1311954285625479229,  # 목요일 <:Thu:1311954285625479229>
    "Fri": 1311954284027318312,  # 금요일 <:Fri:1311954284027318312>
    "Sat": 1311954282236350556,  # 토요일 <:Sat:1311954282236350556>
    "Sun": 1311954280214958201   # 일요일 <:Sun:1311954280214958201>
}


test_time = None  # 테스트용 시간 변수
previous_week = None  # 이전 주 저장 변수

def get_current_time():
    if test_time:
        return test_time
    return datetime.datetime.now()

weekly_message = None  # 최근에 생성된 주간 메시지를 저장하기 위한 변수

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    weekly_task.start()  # 봇이 준비되면 매주 월요일 00시에 메시지를 생성하는 작업을 시작합니다.

@tasks.loop(seconds=1)
async def weekly_task():
    global weekly_message, previous_week
    now = get_current_time()
    current_week = now.isocalendar()[1]  # 현재 주 (ISO 캘린더 기준)
    if now.weekday() == 0 and current_week != previous_week:
        # 월요일에 메시지를 보냅니다 (이전 주와 다른 경우).
        channel = bot.get_channel(channel_id)
        if channel is not None:
            start_date = now
            end_date = start_date + datetime.timedelta(days=6)
            weekly_message = await channel.send(f"{start_date.year}년 {start_date.month}월 {start_date.day}일 월요일 ~ {end_date.year}년 {end_date.month}월 {end_date.day}일 일요일 출석체크")
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

@bot.event
async def on_raw_reaction_add(payload):
    global weekly_message
    if weekly_message is None or payload.message_id != weekly_message.id:
        return

    now = get_current_time()
    current_weekday = now.weekday()
    user = bot.get_user(payload.user_id)
    if user == bot.user:  # 봇 자신의 반응은 무시
        return

    try:
        # 현재 선택 가능한 이모지 ID
        current_emoji_id = list(weekdays_emojis.values())[current_weekday]
    except IndexError:
        print(f"Invalid current_weekday: {current_weekday}")
        return

    if payload.emoji.id != current_emoji_id:
        channel = bot.get_channel(payload.channel_id)
        if channel is not None:
            try:
                message = await channel.fetch_message(payload.message_id)
                member = await bot.fetch_user(payload.user_id)
                await message.remove_reaction(payload.emoji, member)
            except discord.Forbidden:
                print(f"Permission error: Cannot remove reaction from user {member}")
            except discord.HTTPException as e:
                print(f"Failed to remove reaction: {e}")



@bot.command()
async def set_time(ctx, year: int, month: int, day: int, hour: int, minute: int, second: int):
    global test_time
    test_time = datetime.datetime(year, month, day, hour, minute, second)
    await ctx.send(f"시간이 {test_time}으로 설정되었습니다.")

@bot.command()
async def clear_time(ctx):
    global test_time
    test_time = None
    await ctx.send("시간 설정이 초기화되었습니다. 현재 시스템 시간을 사용합니다.")


@bot.command()
@commands.has_permissions(administrator=True)  # 관리자 권한이 있는 사용자만 사용 가능
async def list_users(ctx):
    guild = ctx.guild
    if guild is None:
        await ctx.send("이 명령어는 서버에서만 사용할 수 있습니다.")
        return

    members = guild.members
    bot_id = bot.user.id

    user_list = []
    for member in members:
        if member.id != bot_id:
            nickname = member.nick if member.nick else member.name
            user_list.append(f"닉네임: {nickname}, ID: {member.id}")

    if not user_list:
        await ctx.send("봇을 제외한 유저가 없습니다.")
        return

    # 메시지 길이 제한(2000자) 초과 시 파일로 전송
    message_content = "\n".join(user_list)
    if len(message_content) < 2000:
        await ctx.send(f"서버 유저 목록:\n{message_content}")
    else:
        # 긴 메시지는 파일로 전송
        with open("user_list.txt", "w", encoding="utf-8") as f:
            f.write(message_content)
        await ctx.send("서버 유저 목록이 너무 깁니다. 파일로 첨부합니다.", file=discord.File("user_list.txt"))



# 봇 토큰을 안전하게 불러오기 (예: 환경 변수 사용)
import os
TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # 환경 변수에서 토큰을 가져옵니다.

if TOKEN is None:
    print("Error: DISCORD_BOT_TOKEN 환경 변수가 설정되지 않았습니다.")
else:
    bot.run(TOKEN)