#!/usr/bin/env python3
"""
Telegram Bot for Monthly Payment Reminders
Version: 1.2
Author: Nagagames24
Description: Sends reminders to employees on the 13th of every month at 10:00.
Users automatically activate themselves by sending /start.
"""

import json
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ===================== КОНФИГУРАЦИЯ =====================
BOT_TOKEN = "8777556766:AAGHWTiRcqYpbRkgV2iEDOdnVqIAmybjJ6w"
ADMIN_ID = 1407081834
EMPLOYEES_FILE = Path("employees.json")
LOG_FILE = Path("bot.log")

# Настройка логирования ТОЛЬКО в файл
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Хранилище данных (загружается из файла)
employees: List[Dict] = []

# ID задач в планировщике
JOB_MONTHLY = "monthly_payment"
JOB_TEST = "test_interval"

# ===================== РАБОТА С ФАЙЛОМ =====================
def load_employees() -> bool:
    """
    Загружает список пользователей из JSON-файла.
    Возвращает True при успехе, False при ошибке.
    """
    global employees
    try:
        if not EMPLOYEES_FILE.exists():
            logger.error(f"ERROR Файл {EMPLOYEES_FILE} не найден. Создаю пустой шаблон.")
            template = {
                "employees": [
                    {
                        "telegram_id": ADMIN_ID,
                        "name": "Администратор (Я)",
                        "is_active": True
                    }
                ]
            }
            with open(EMPLOYEES_FILE, 'w', encoding='utf-8') as f:
                json.dump(template, f, indent=2, ensure_ascii=False)
            logger.info(f"INFO Создан шаблон файла {EMPLOYEES_FILE}. Заполни его данными.")
            employees = template["employees"]
            return True

        with open(EMPLOYEES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict) or 'employees' not in data:
            logger.error("ERROR Неверная структура JSON. Ожидается {'employees': [...]}")
            return False

        if not isinstance(data['employees'], list):
            logger.error("ERROR Поле 'employees' должно быть списком.")
            return False

        employees = data['employees']
        
        valid_employees = []
        for idx, emp in enumerate(employees):
            if not isinstance(emp, dict):
                logger.warning(f"WARN Запись #{idx} пропущена: не является объектом")
                continue
            if 'telegram_id' not in emp or 'name' not in emp:
                logger.warning(f"WARN Запись #{idx} пропущена: отсутствует telegram_id или name")
                continue
            if not isinstance(emp['telegram_id'], int):
                logger.warning(f"WARN Запись #{idx} пропущена: telegram_id должен быть числом")
                continue
            if 'is_active' not in emp:
                emp['is_active'] = True
            valid_employees.append(emp)
        
        employees = valid_employees
        active_count = sum(1 for e in employees if e.get('is_active', False))
        logger.info(f"INFO Загружено пользователей: всего {len(employees)}, активно {active_count}")
        return True

    except json.JSONDecodeError as e:
        logger.error(f"ERROR Ошибка парсинга JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"ERROR Неожиданная ошибка при загрузке: {e}")
        return False

def save_employees() -> bool:
    """
    Сохраняет текущий список сотрудников в JSON-файл.
    Возвращает True при успехе, False при ошибке.
    """
    try:
        if EMPLOYEES_FILE.exists():
            backup_file = EMPLOYEES_FILE.with_suffix('.json.bak')
            EMPLOYEES_FILE.rename(backup_file)
        
        with open(EMPLOYEES_FILE, 'w', encoding='utf-8') as f:
            json.dump({"employees": employees}, f, indent=2, ensure_ascii=False)
        
        logger.info(f"INFO Список сотрудников сохранён в {EMPLOYEES_FILE}")
        return True
    except Exception as e:
        logger.error(f"ERROR Ошибка при сохранении файла: {e}")
        return False

def activate_user(telegram_id: int) -> bool:
    """
    Активирует пользователя по telegram_id.
    Возвращает True, если пользователь найден и активирован.
    """
    global employees
    for emp in employees:
        if emp.get('telegram_id') == telegram_id:
            if not emp.get('is_active', False):
                emp['is_active'] = True
                logger.info(f"INFO Пользователь {emp.get('name')} (ID: {telegram_id}) активирован")
                save_employees()
                return True
            else:
                logger.info(f"INFO Пользователь {emp.get('name')} (ID: {telegram_id}) уже активен")
                return True
    logger.info(f"INFO Пользователь с ID {telegram_id} не найден в списке")
    return False

# ===================== КОМАНДЫ БОТА =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветственное сообщение. Автоматически активирует пользователя."""
    user_id = message.from_user.id
    user_name = message.from_user.full_name or "Коллега"
    
    activated = activate_user(user_id)
    emp = next((e for e in employees if e.get('telegram_id') == user_id), None)
    
    if emp:
        await message.answer(
            f"Привет, {emp['name']}!\n\n"
            f"Твой профиль активирован. Теперь ты будешь получать ежемесячные напоминания об оплате.\n"
            f"Первое напоминание придёт 13-го числа в 10:00."
        )
        logger.info(f"INFO Пользователь {emp['name']} (ID: {user_id}) активировался через /start")
    else:
        await message.answer(
            f"Привет, {user_name}!\n\n"
            f"Твой ID ({user_id}) не найден в списке рассылки.\n"
            f"Обратись к администратору, чтобы тебя добавили."
        )
        logger.info(f"INFO Неизвестный пользователь (ID: {user_id}) написал /start")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    """Показывает список пользователей (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    if not employees:
        await message.answer("Список пользователей пуст.")
        return

    text = "**Текущий список рассылки:**\n\n"
    for emp in employees:
        status = " Yes" if emp.get('is_active', False) else "❌ No"
        text += f"{status} {emp.get('name')} (`{emp.get('telegram_id')}`)\n"
    
    active = sum(1 for e in employees if e.get('is_active', False))
    inactive = len(employees) - active
    text += f"\n Всего: {len(employees)} | Активно: {active} | Неактивно: {inactive}"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("reload"))
async def cmd_reload(message: Message):
    """Перезагружает список из файла (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    if load_employees():
        await message.answer("Список пользователей успешно перезагружен из файла.")
    else:
        await message.answer("Ошибка при загрузке. Проверь логи и файл.")

@dp.message(Command("test_send"))
async def cmd_test_send(message: Message):
    """Ручной запуск рассылки для тестирования (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    await message.answer("Запускаю тестовую рассылку...")
    await send_payment_reminder(is_test=True)
    await message.answer("Тестовая рассылка завершена. Подробности в логах.")

@dp.message(Command("cancel_test"))
async def cmd_cancel_test(message: Message):
    """Отменяет текущую тестовую рассылку (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    job = scheduler.get_job(JOB_TEST)
    if job:
        scheduler.remove_job(JOB_TEST)
        await message.answer("Тестовая рассылка отменена.")
        logger.info("INFO Тестовая рассылка отменена администратором.")
    else:
        await message.answer("Тестовая рассылка не запущена.")

@dp.message(Command("cancel_monthly"))
async def cmd_cancel_monthly(message: Message):
    """Отменяет запланированную ежемесячную рассылку (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    job = scheduler.get_job(JOB_MONTHLY)
    if job:
        scheduler.remove_job(JOB_MONTHLY)
        await message.answer("Ежемесячная рассылка отменена.\n"
                             "Для восстановления используй /schedule_monthly")
        logger.info("INFO Ежемесячная рассылка отменена администратором.")
    else:
        await message.answer("Ежемесячная рассылка не запланирована.")

@dp.message(Command("schedule_monthly"))
async def cmd_schedule_monthly(message: Message):
    """Восстанавливает ежемесячную рассылку (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    if scheduler.get_job(JOB_MONTHLY):
        scheduler.remove_job(JOB_MONTHLY)
    
    scheduler.add_job(
        send_payment_reminder,
        CronTrigger(day=13, hour=10, minute=0),
        id=JOB_MONTHLY,
        replace_existing=True,
        misfire_grace_time=3600
    )
    
    next_run = scheduler.get_job(JOB_MONTHLY).next_run_time
    await message.answer(f"Ежемесячная рассылка восстановлена.\n"
                         f"Следующий запуск: {next_run.strftime('%d.%m.%Y %H:%M')}")
    logger.info(f"INFO Ежемесячная рассылка восстановлена. Следующий запуск: {next_run}")

@dp.message(Command("deactivate"))
async def cmd_deactivate(message: Message):
    """Деактивирует пользователя (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("Формат: /deactivate <telegram_id>")
        return

    try:
        tg_id = int(args[1])
    except ValueError:
        await message.answer("Telegram ID должен быть числом")
        return

    for emp in employees:
        if emp.get('telegram_id') == tg_id:
            emp['is_active'] = False
            save_employees()
            await message.answer(f"Пользователь {emp.get('name')} деактивирован.")
            logger.info(f"INFO Пользователь {emp.get('name')} (ID: {tg_id}) деактивирован администратором")
            return

    await message.answer("❌ Пользователь с таким ID не найден.")

@dp.message(Command("jobs"))
async def cmd_jobs(message: Message):
    """Показывает список запланированных задач (только для админа)."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав на эту команду.")
        return

    jobs = scheduler.get_jobs()
    if not jobs:
        await message.answer("📭 Нет запланированных задач.")
        return

    text = " **Запланированные задачи:**\n\n"
    for job in jobs:
        status = "✅" if job.next_run_time else "❌"
        name = {
            JOB_MONTHLY: "Ежемесячная рассылка (13 число)",
            JOB_TEST: "Тестовая рассылка"
        }.get(job.id, job.id)
        
        if job.next_run_time:
            text += f"{status} {name}\n   ⏰ {job.next_run_time.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            text += f"{status} {name} (не запланирована)\n"
    
    await message.answer(text, parse_mode="Markdown")

# ===================== ЛОГИКА РАССЫЛКИ =====================
async def send_payment_reminder(is_test: bool = False):
    """
    Основная функция рассылки.
    is_test=True добавляет пометку [ТЕСТ] в сообщение.
    """
    logger.info("=" * 60)
    logger.info(f"INFO ЗАПУСК РАССЫЛКИ {'[ТЕСТ]' if is_test else ''}")
    
    if not employees:
        logger.warning("WARN Список пользователей пуст. Рассылка отменена.")
        return

    success = 0
    failed = 0
    blocked = 0

    for emp in employees:
        if not emp.get('is_active', False):
            logger.info(f"INFO Пропуск (неактивен): {emp.get('name')}")
            continue

        tg_id = emp.get('telegram_id')
        name = emp.get('name', 'Коллега')

        if not tg_id:
            logger.warning(f"WARN У {name} нет telegram_id")
            failed += 1
            continue

        if is_test:
            text = f"[ТЕСТОВОЕ] Привет, {name}! Это проверка системы уведомлений."
        else:
            current_month = datetime.now().strftime("%B")
            text = (
                f"**Ежемесячное напоминание**\n\n"
                f"Привет, {name}!\n"
                f"Напоминаю, что сегодня нужно оплатить VPN 200 рублей.\n"
            )

        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            logger.info(f"INFO Отправлено: {name} (ID: {tg_id})")
            success += 1
            await asyncio.sleep(0.3)

        except TelegramForbiddenError:
            logger.error(f"ERROR Бот заблокирован пользователем: {name} (ID: {tg_id})")
            blocked += 1
            failed += 1
            emp['is_active'] = False
            save_employees()
            logger.info(f"INFO Пользователь {name} деактивирован (блокировка бота)")
            
        except TelegramRetryAfter as e:
            logger.warning(f"WARN Telegram просит подождать {e.retry_after} сек. Ждём...")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(tg_id, text, parse_mode="Markdown")
                logger.info(f"INFO Повторно отправлено: {name}")
                success += 1
            except Exception as e2:
                logger.error(f"ERROR Ошибка при повторной отправке {name}: {e2}")
                failed += 1

        except Exception as e:
            logger.error(f"ERROR Ошибка отправки {name}: {e}")
            failed += 1

    logger.info(f"ИТОГИ: Успешно={success}, Ошибки={failed}, Заблокировали={blocked}")
    logger.info("=" * 60)

# ===================== ПЛАНИРОВЩИК =====================
async def on_startup():
    """Действия при запуске бота."""
    logger.info("INFO Бот запускается...")
    
    if not load_employees():
        logger.critical("CRITICAL Не удалось загрузить список пользователей.")
    
    scheduler.add_job(
        send_payment_reminder,
        CronTrigger(day=13, hour=10, minute=0),
        id=JOB_MONTHLY,
        replace_existing=True,
        misfire_grace_time=3600
    )
    
    scheduler.start()
    logger.info("INFO Планировщик запущен. Жду 13-го числа 10:00...")
    
    jobs = scheduler.get_jobs()
    for job in jobs:
        logger.info(f"INFO Запланирована задача: {job.id}, следующее выполнение: {job.next_run_time}")

async def on_shutdown():
    """Действия при остановке бота."""
    logger.info("INFO Бот останавливается...")
    scheduler.shutdown()
    await bot.session.close()

# ===================== ТОЧКА ВХОДА =====================
async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("INFO Бот вышел на охоту...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("INFO Бот остановлен пользователем.")
    except Exception as e:
        logging.critical(f"CRITICAL Фатальная ошибка: {e}", exc_info=True)