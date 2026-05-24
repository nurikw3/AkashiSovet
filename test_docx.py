#!/usr/bin/env python3
"""
Быстрый тест DOCX-генератора.
Запуск: uv run test_docx.py
"""

import sys
import asyncio
import platform
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOCAL_DB_URL = "postgresql://akashi:akashi_secret@localhost:5432/akashi"
os.environ["DATABASE_URL"] = LOCAL_DB_URL

from stdlib.document import generate_docx
import stdlib.db as db

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

TEST_USER_ID = None


async def main():
    print("🚀 Генерация тестового DOCX...")

    try:
        if TEST_USER_ID is not None:
            print(f"🔌 Подключаюсь к локальной БД: {LOCAL_DB_URL}")
            await db.init_db()

        docx_buffer = await generate_docx(TEST_DATA, user_id=TEST_USER_ID)

        output_path = PROJECT_ROOT / "output_test.docx"
        output_path.write_bytes(docx_buffer.getvalue())

        print(f"✅ Готово! Файл: {output_path}")
        print(f"📏 Размер: {output_path.stat().st_size / 1024:.1f} КБ")

        if platform.system() == "Darwin":
            subprocess.run(["open", str(output_path)], check=True)
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
