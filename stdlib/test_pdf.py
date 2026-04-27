#!/usr/bin/env python3
"""
Быстрый тест PDF-генератора без запуска бота.
Запуск: python test_pdf.py
Результат: output_test.pdf в текущей папке
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stdlib.pdf import generate_pdf


# 🎯 Тестовые данные (меняй под свои нужды)
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
    "attachments": [
        "ТЗ_на_закупку.pdf",
        "Смета_отдела_ИИ.xlsx",
        "Сравнительный_анализ_инструментов.docx",
    ],
    "username": "Иванов Иван Иванович",
    "position": "Руководитель отдела искусственного интеллекта",
    "date": "27.04.2026",
}


async def main():
    print("🚀 Генерация тестового PDF...")

    try:
        # Вызываем генератор (user_id=999 для теста подписи, если она есть в БД)
        pdf_buffer = await generate_pdf(TEST_DATA, user_id=1102555863)

        # Сохраняем в файл
        output_path = Path("output_test.pdf")
        with open(output_path, "wb") as f:
            f.write(pdf_buffer.getvalue())

        print(f"✅ Готово! Файл сохранён: {output_path.resolve()}")
        print(f"📏 Размер: {output_path.stat().st_size / 1024:.1f} КБ")

        # Пробуем открыть файл автоматически
        if sys.platform == "win32":
            import os

            os.startfile(output_path)
        elif sys.platform == "darwin":  # macOS
            import subprocess

            subprocess.run(["open", output_path])
        elif sys.platform == "linux":
            import subprocess

            subprocess.run(["xdg-open", output_path])
        else:
            print("💡 Открой файл вручную для просмотра")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
