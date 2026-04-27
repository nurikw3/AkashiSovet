#!/usr/bin/env python3
"""
Быстрый тест PDF-генератора.
📍 Лежи в корне проекта. Запуск: uv run test_pdf.py
"""

import sys
import asyncio
import platform
import subprocess
import os
from pathlib import Path

# 🔧 Гарантируем импорт из корня
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 🛠 ВАЖНО: Для локального теста меняем хост с 'postgres' на 'localhost'
# Если у тебя другой порт или пароль, поправь строку ниже
LOCAL_DB_URL = "postgresql://akashi:akashi_secret@localhost:5432/akashi"
os.environ["DATABASE_URL"] = LOCAL_DB_URL

from stdlib.pdf import generate_pdf
import stdlib.db as db
from bot.config import config  # Перезагружаем конфиг, чтобы он подхватил новый URL

# 🎯 Тестовые данные
TEST_DATA = {
    "app_id": 999,
    "topic": "Внедрение инструментов VibeCode для отдела ИИ",
    "description": "Для повышения производительности программистов необходимо внедрить специализированные инструменты разработки.",
    "basis": "План цифровизации компании на 2026 год, пункт 4.2.",
    "solution": """1. Утвердить приобретение и внедрение инструментов VibeCode, необходимых для обеспечения требуемого уровня производительности программистов.
2. Согласовать выделение соответствующего бюджета из бюджета отдела искусственного интеллекта на закупку указанных инструментов.
3. Делегировать руководителю проекта полномочия по контролю за выполнением задач по автоматизации.
4. Поручить руководителю проекта обеспечить мониторинг эффективности использования новых инструментов.""",
    "risks": "Возможна временная задержка в адаптации сотрудников к новым инструментам.",
    "attachments": ["ТЗ_на_закупку.pdf", "Смета_отдела_ИИ.xlsx"],
    "username": "Иванов Иван Иванович",
    "position": "Руководитель отдела искусственного интеллекта",
    "date": "27.04.2026",
}

# 👤 Укажи свой ID, чтобы проверить подпись, или оставь None для теста без БД
TEST_USER_ID = (
    1102555863  # <-- Поменяй на 1102555863, если хочешь проверить подпись из БД
)


async def main():
    print("🚀 Генерация тестового PDF...")

    try:
        # Инициализируем БД только если нужен user_id
        if TEST_USER_ID is not None:
            print(f"🔌 Подключаюсь к локальной БД: {LOCAL_DB_URL}")
            await db.init_db()

        pdf_buffer = await generate_pdf(TEST_DATA, user_id=TEST_USER_ID)

        output_path = PROJECT_ROOT / "output_test.pdf"
        output_path.write_bytes(pdf_buffer.getvalue())

        print(f"✅ Готово! Файл: {output_path}")
        print(f"📏 Размер: {output_path.stat().st_size / 1024:.1f} КБ")

        # Автооткрытие файла
        if platform.system() == "Darwin":
            subprocess.run(["open", output_path], check=True)
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", output_path], check=True)
        elif platform.system() == "Windows":
            os.startfile(output_path)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if TEST_USER_ID is not None:
            await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
