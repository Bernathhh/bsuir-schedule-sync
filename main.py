import datetime
import requests
import pytz
from fastapi import FastAPI, Response
from icalendar import Calendar, Event

app = FastAPI(title="BSUIR Calendar Sync")
TIMEZONE = pytz.timezone("Europe/Minsk")

DAY_MAP = {
    "Понедельник": 0, "Вторник": 1, "Среда": 2,
    "Четверг": 3, "Пятница": 4, "Суббота": 5
}

def generate_ics(group: str, subgroup: int, category: str):
    # Текущая учебная неделя БГУИР
    try:
        cw_res = requests.get("https://iis.bsuir.by/api/v1/schedule/current-week", timeout=5)
        current_week = int(cw_res.text.strip())
    except Exception:
        current_week = 1

    # Загрузка расписания
    url = f"https://iis.bsuir.by/api/v1/schedule?studentGroup={group}"
    res = requests.get(url, timeout=7).json()
    schedules = res.get("schedules", {})

    cal = Calendar()
    cal.add("prodid", f"-//BSUIR//{group}//RU")
    cal.add("version", "2.0")
    cal.add("x-wr-timezone", "Europe/Minsk")

    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())

    # Генерируем на 8 недель вперед
    for week_offset in range(8):
        week_start = monday + datetime.timedelta(weeks=week_offset)
        week_num = ((current_week - 1 + week_offset) % 4) + 1

        for day_name, lessons in schedules.items():
            if day_name not in DAY_MAP or not isinstance(lessons, list):
                continue
            
            day_date = week_start + datetime.timedelta(days=DAY_MAP[day_name])

            for lesson in lessons:
                if week_num not in lesson.get("weekNumber", []):
                    continue

                sub = lesson.get("numSubgroup", 0)
                if sub not in (0, subgroup):
                    continue

                l_type = (lesson.get("lessonTypeAbbrev") or "").strip().upper()

                # Фильтрация по типу занятия
                if category == "lectures" and "ЛК" not in l_type:
                    continue
                elif category == "labs" and "ЛР" not in l_type:
                    continue
                elif category == "practicals" and ("ЛК" in l_type or "ЛР" in l_type):
                    continue

                start_t = lesson.get("startLessonTime")
                end_t = lesson.get("endLessonTime")
                if not start_t or not end_t:
                    continue

                sh, sm = map(int, start_t.split(":"))
                eh, em = map(int, end_t.split(":"))

                start_dt = TIMEZONE.localize(datetime.datetime.combine(day_date, datetime.time(sh, sm)))
                end_dt = TIMEZONE.localize(datetime.datetime.combine(day_date, datetime.time(eh, em)))

                subject = lesson.get("subject", "Занятие")
                auds = ", ".join(lesson.get("auditories", []))

                # Формируем полное ФИО (Фамилия Имя Отчество)
                full_teachers = []
                short_teachers = []
                for t in lesson.get("employees", []):
                    last_name = t.get("lastName", "").strip()
                    first_name = t.get("firstName", "").strip()
                    middle_name = t.get("middleName", "").strip()
                    
                    full_name = f"{last_name} {first_name} {middle_name}".strip()
                    if full_name:
                        full_teachers.append(full_name)
                    if last_name:
                        short_teachers.append(last_name)

                event = Event()
                
                # Формируем заголовок пары
                summary = f"[{l_type}] {subject}"
                if auds:
                    summary += f" ({auds})"

                event.add("summary", summary)
                event.add("dtstart", start_dt)
                event.add("dtend", end_dt)

                # UID
                clean_subj = "".join(c for c in subject if c.isalnum())[:10]
                event.add("uid", f"{group}_{sub}_{day_date}_{sh}{sm}_{clean_subj}@bsuir")

                # Подробное описание
                desc = [f"Тип: {l_type}", f"Предмет: {subject}"]
                if full_teachers:
                    desc.append(f"Преподаватель: {', '.join(full_teachers)}")
                desc.append(f"Подгруппа: {sub if sub != 0 else 'Вся группа'}")
                desc.append(f"Неделя: {week_num}")
                event.add("description", "\n".join(desc))

                if auds:
                    event.add("location", f"ауд. {auds}, БГУИР")

                cal.add_component(event)

    return cal.to_ical()

@app.get("/")
def index():
    return {"status": "ok", "message": "BSUIR Calendar API is running"}

@app.get("/schedule/{group}/{subgroup}/{category}.ics")
def schedule_endpoint(group: str, subgroup: int, category: str):
    ics_bytes = generate_ics(group, subgroup, category)
    return Response(content=ics_bytes, media_type="text/calendar")