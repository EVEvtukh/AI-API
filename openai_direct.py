"""Обычный запрос к OpenAI через официальную библиотеку.

Запуск:
    python openai_direct.py

Зависимости:
    pip install openai
    Ключ OpenAI задается переменной окружения OPENAI_API_KEY
    (например, в файле .env).
"""

import os
import sys

from openai import OpenAI

MODEL = "gpt-3.5-turbo"


def load_env(path: str = ".env") -> None:
    """Простейшая загрузка переменных из файла .env в окружение."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def ask_params() -> dict:
    """Запрашивает параметры запроса у пользователя."""
    prompt = input("Введите запрос для модели: ").strip()
    if not prompt:
        sys.exit("Ошибка: запрос не может быть пустым.")

    temperature = float(input("Temperature (например 0.7): ") or 0.7)
    max_tokens = int(input("Max tokens (например 500): ") or 500)

    # system_message опционален: пустая строка — не используем
    system_message = input("System message (можно пропустить, Enter): ").strip()

    return {
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_message": system_message,
    }


def main() -> None:
    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("Ошибка: переменная окружения OPENAI_API_KEY не задана.")

    params = ask_params()

    messages = []
    if params["system_message"]:
        messages.append({"role": "system", "content": params["system_message"]})
    messages.append({"role": "user", "content": params["prompt"]})

    client = OpenAI()  # ключ берется из OPENAI_API_KEY

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=params["temperature"],
            max_tokens=params["max_tokens"],
        )
    except Exception as exc:
        sys.exit(f"Ошибка запроса к OpenAI: {exc}")

    print("\n--- Ответ модели ---")
    print(response.choices[0].message.content)

    usage = response.usage
    if usage:
        print(
            f"\n(токены: prompt={usage.prompt_tokens}, "
            f"completion={usage.completion_tokens}, total={usage.total_tokens})"
        )


if __name__ == "__main__":
    main()
