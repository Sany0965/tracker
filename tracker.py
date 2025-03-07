import asyncio
import json
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.types import UpdateUserStatus, UserStatusOnline, UserStatusOffline
from telethon.tl.functions.channels import JoinChannelRequest
import pytz

API_ID = 0  # Замените на ваш API ID
API_HASH = 'YOUR_API_HASH'  # Замените на ваш API HASH
TRACKED_USERS = ['username']  # Список отслеживаемых пользователей (имена)
SESSION_NAME = 'session'
MSK_TZ = pytz.timezone('Europe/Moscow')

client = TelegramClient(SESSION_NAME, API_ID, API_HASH, device_model='SessionTracker', system_version='3.0')
tracked_users = {}
sessions = {}
online_history = []

def load_sessions():
    global sessions, online_history
    try:
        with open('sessions.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sessions = data.get('sessions', {})
            online_history = []
            for entry in data.get('history', []):
                entry['time'] = datetime.fromisoformat(entry['time']).astimezone(MSK_TZ)
                online_history.append(entry)
    except (FileNotFoundError, json.JSONDecodeError):
        sessions = {}
        online_history = []

def save_sessions():
    data = {
        'sessions': sessions,
        'history': [{
            'user_id': entry['user_id'],
            'time': entry['time'].isoformat(),
            'emoji': entry['emoji'],
            'type': entry['type'],
            'duration': entry.get('duration', '')
        } for entry in online_history]
    }
    with open('sessions.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def generate_report(user_id=None):
    load_sessions()
    report = []
    if user_id:
        user_id_str = str(user_id)
        username = tracked_users.get(user_id_str, {}).get('username', 'Unknown')
        report.append(f"📝 История сессий @{username}:\n")
        for entry in reversed(online_history):
            if entry['user_id'] == user_id_str:
                time_str = entry['time'].strftime('%H:%M:%S')
                duration_info = f"({entry.get('duration', '')})" if entry.get('duration') else ""
                report.append(f"{entry['emoji']} {time_str} {duration_info}")
        report.append("\n📊 Статистика по дням:\n")
        user_data = sessions.get(user_id_str, {})
        for date_str, sessions_list in sorted(user_data.items(), reverse=True):
            total = sum(s['duration'] for s in sessions_list)
            report.append(f"📅 {date_str}:")
            for i, session in enumerate(sessions_list, 1):
                start = datetime.fromisoformat(session['start']).astimezone(MSK_TZ).strftime('%H:%M:%S')
                end = datetime.fromisoformat(session['end']).astimezone(MSK_TZ).strftime('%H:%M:%S')
                report.append(f"{i}. {start} - {end} ({int(session['duration'])} сек)")
            report.append(f"✅ Всего за день: {int(total)} сек\n")
    else:
        report.append("📊 Общий отчет\n")
        for user_id_str, user_data in sessions.items():
            username = tracked_users.get(user_id_str, {}).get('username', 'Unknown')
            total_all = sum(s['duration'] for slist in user_data.values() for s in slist)
            report.append(f"👤 @{username}: {int(total_all)} сек\n")
    return '\n'.join(report) if report else "📭 Нет данных для отображения"

@client.on(events.NewMessage(pattern=r'\.s(?:\s+@(\w+))?'))
async def stats_handler(event):
    username = event.pattern_match.group(1)
    load_sessions()
    if username:
        user = next((u for u in tracked_users.values() if u['username'] == username), None)
        if not user:
            await event.reply("❌ Пользователь не найден!")
            return
        report = await generate_report(user['id'])
    else:
        report = await generate_report()
    with open('report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    await client.send_file(event.chat_id, 'report.txt', caption=f"📋 Полный отчет по активности {'@' + username if username else ''}")

async def track_user(user):
    try:
        user_entity = await client.get_entity(user)
        tracked_users[str(user_entity.id)] = {'id': user_entity.id, 'username': user_entity.username, 'current_session': None}
        print(f"Tracking @{user_entity.username}")
    except Exception as e:
        print(f"Error tracking {user}: {str(e)}")

@client.on(events.Raw)
async def status_handler(event):
    if isinstance(event, UpdateUserStatus):
        user_id = str(event.user_id)
        user_data = tracked_users.get(user_id)
        if not user_data:
            return
        now = datetime.now(MSK_TZ)
        if isinstance(event.status, UserStatusOnline):
            online_history.append({'user_id': user_id, 'time': now, 'emoji': '🟢', 'type': 'онлайн'})
            if not user_data['current_session']:
                user_data['current_session'] = now
        elif isinstance(event.status, UserStatusOffline):
            if user_data['current_session']:
                duration = (now - user_data['current_session']).total_seconds()
                online_history.append({'user_id': user_id, 'time': now, 'emoji': '🔴', 'type': 'оффлайн', 'duration': f"{int(duration)} сек"})
                date_str = now.strftime('%d.%m.%Y')
                session_data = {'start': user_data['current_session'].isoformat(), 'end': now.isoformat(), 'duration': duration}
                if user_id not in sessions:
                    sessions[user_id] = {}
                if date_str not in sessions[user_id]:
                    sessions[user_id][date_str] = []
                sessions[user_id][date_str].append(session_data)
                save_sessions()
                user_data['current_session'] = None

async def main():
    load_sessions()
    await client.start()
    await client(JoinChannelRequest('telegram'))
    for user in TRACKED_USERS:
        await track_user(user)
    print("Tracker started...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())