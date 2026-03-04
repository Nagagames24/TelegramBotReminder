#!/usr/bin/env python3
"""
Telegram Bot for Monthly Payment Reminders
Version: 1.0
Author: DevOps Team
Description: Sends reminders to employees on the 1st of every month at 10:00.
"""

import json
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

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
        # Убран вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

# ===================== ИНИЦИАЛИЗАЦИЯ =====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Хранилище данных (загружается из файла)
employees: List[Dict] = []

# ID задач в планировщике (для удобства управления)
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
            logger.error(f"EROR Файл {EMPLOYEES_FILE} не найден. Создаю пустой шаблон.")
            # Создаём шаблон файла для удобства
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

        # Валидация структуры
        if not isinstance(data, dict) or 'employees' not in data:
            logger.error("ERROR Неверная структура JSON. Ожидается {'employees': [...]}")
            return False

        if not isinstance(data['employees'], list):
            logger.error("ERROR Поле 'employees' должно быть списком.")
            return False

        employees = data['employees']
        
        # Дополнительная валидация каждого user-а
        valid_employees = []
        for idx, emp in enumerate(employees):
            if not isinstance(emp, dict):
                logger.warning(f"Запись #{idx} пропущена: не является объектом")
                continue
            if 'telegram_id' not in emp or 'name' not in emp:
                logger.warning(f"WARN Запись #{idx} пропущена: отсутствует telegram_id или name")
                continue
            if not isinstance(emp['telegram_id'], int):
                logger.warning(f"WARN Запись #{idx} пропущена: telegram_id должен быть числом")
                continue
            valid_employees.append(emp)
        
        employees = valid_employees
        active_count = sum(1 for e in employees if e.get('is_active', False))
        logger.info(f"Загружено пользователей: всего {len(employees)}, активно {active_count}")
        return True

    except json.JSONDecodeError as e:
        logger.error(f"ERROR Ошибка парсинга JSON: {e}")
        logger.error(f"ERROR Проверь файл {EMPLOYEES_FILE} на наличие синтаксических ошибок.")
        return False
    except Exception as e:
        logger.error(f"ERROR Неожиданная ошибка при загрузке: {e}")
        return False

# ===================== КОМАНДЫ БОТА =====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Приветственное сообщение. Обязательно для активации диалога."""
    user_id = message.from_user.id
    emp = next((e for e in employees if e.get('telegram_id') == user_id), None)
    
    if emp:
        await message.answer(
            f"Привет, {emp['name']}!\n"
            f"Ты в списке на получение ежемесячных напоминаний об оплате.\n"
            f"Первое напоминание придёт 13-го числа в 10:00."
        )
    else:
        await message.answer(
            "Привет! Твой ID не найден в списке рассылки.\n"
            "Обратись к администратору, чтобы тебя добавили."
        )

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
        status = "Yes" if emp.get('is_active', False) else "No"
        text += f"{status} {emp.get('name')} (`{emp.get('telegram_id')}`)\n"
    
    # Добавляем статистику
    active = sum(1 for e in employees if e.get('is_active', False))
    text += f"\nВсего: {len(employees)} | Активно: {active}"
    
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
        await message.answer("X Ошибка при загрузке. Проверь логи и файл.")

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
        logger.info("Тестовая рассылка отменена администратором.")
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
        await message.answer(" Ежемесячная рассылка не запланирована.")

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
        # Пропускаем неактивных
        if not emp.get('is_active', False):
            logger.info(f"INFO Пропуск (неактивен): {emp.get('name')}")
            continue

        tg_id = emp.get('telegram_id')
        name = emp.get('name', 'Коллега')

        if not tg_id:
            logger.warning(f"У {name} нет telegram_id")
            failed += 1
            continue

        # Формируем текст сообщения
        if is_test and tg_id==ADMIN_ID:
            text = f"[ТЕСТОВОЕ] Привет, {name}! Это проверка системы уведомлений."
        else:
            # Здесь можно добавить актуальную дату или сумму
            current_month = datetime.now().strftime("%B")
            text = (
                f"**Ежемесячное напоминание**\n\n"
                f"Привет, {name}!\n"
                f"Напоминаю, что сегодня нужно оплатить VPN 200 рублей за {current_month+1}.\n"
            )

        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            logger.info(f"INFO Отправлено: {name} (ID: {tg_id})")
            success += 1
            
            await asyncio.sleep(0.3)

        except TelegramForbiddenError:
            logger.error(f"EROR Бот заблокирован пользователем: {name} (ID: {tg_id})")
            blocked += 1
            failed += 1
            emp['is_active'] = False
            
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
            logger.error(f"X Ошибка отправки {name}: {e}")
            failed += 1

    logger.info(f"ИТОГИ: Успешно={success}, Ошибки={failed}, Заблокировали={blocked}")
    logger.info("=" * 60)

# ===================== ПЛАНИРОВЩИК =====================
async def on_startup():
    """Действия при запуске бота."""
    logger.info("Бот запускается...")
    
    # Загружаем список пользователей
    if not load_employees():
        logger.critical("Критическая ошибка: не удалось загрузить список пользователей.")
        logger.critical("Бот продолжит работу, но рассылка не сработает до исправления.")
    
    # Настраиваем расписание
    # Каждый месяц 1-го числа в 10:00
    scheduler.add_job(
        send_payment_reminder,
        CronTrigger(day=13, hour=10, minute=0),
        id="monthly_payment",
        replace_existing=True,
        misfire_grace_time=3600  # Если бот был выключен, запустит в течение часа после включения
    )
    
    scheduler.start()
    logger.info("⏰ Планировщик запущен. Жду 13-го числа 10:00...")
    
    # Показываем текущее расписание
    jobs = scheduler.get_jobs()
    for job in jobs:
        logger.info(f"📅 Запланирована задача: {job.id}, следующее выполнение: {job.next_run_time}")

async def on_shutdown():
    """Действия при остановке бота."""
    logger.info("🔴 Бот останавливается...")
    scheduler.shutdown()
    await bot.session.close()

# ===================== ТОЧКА ВХОДА =====================
async def main():
    """Главная функция."""
    # Регистрируем обработчики событий
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем поллинг
    logger.info("🎯 Бот вышел на охоту...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем.")
    except Exception as e:
        # Это исключение всё же попадёт в stderr, но это фатально, так и надо
        logging.critical(f"💥 Фатальная ошибка: {e}", exc_info=True)
