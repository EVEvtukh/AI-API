"""Тот же функционал, но через ProxyAPI (https://proxyapi.ru/).

Запуск:
    python proxyapi_request.py

Зависимости:
    pip install requests
    Ключ ProxyAPI задается в файле .env в переменной PROXYAPI_API_KEY.
"""

import json
import os
import sys

import requests

API_URL = "https://api.proxyapi.ru/v1/chat/completions"
MODEL = "gpt-3.5-turbo"
TIMEOUT = 120


def load_env(path: str = ".env") -> None:
    """Загружает переменные из .env в окружение.

    Значения из .env перекрывают переменные процесса. os.environ.setdefault()
    оставил бы в силе старую переменную процесса, и скрипт молча ушёл бы
    с неактуальным ключом вместо значения из файла.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ[key.strip()] = value.strip().strip("'\"")


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
    api_key = os.environ.get("PROXYAPI_API_KEY")
    if not api_key:
        sys.exit("Ошибка: в .env не задан PROXYAPI_API_KEY.")

    params = ask_params()

    messages = []
    if params["system_message"]:
        messages.append({"role": "system", "content": params["system_message"]})
    messages.append({"role": "user", "content": params["prompt"]})

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": params["temperature"],
        "max_tokens": params["max_tokens"],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        sys.exit(f"Ошибка сети при запросе к ProxyAPI: {exc}")

    if response.status_code != 200:
        sys.exit(f"ProxyAPI вернул ошибку {response.status_code}: {response.text}")

    data = response.json()
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        sys.exit(f"Неожиданный формат ответа: {json.dumps(data, ensure_ascii=False)}")

    print("\n--- Ответ модели ---")
    print(answer)

    usage = data.get("usage")
    if usage:
        print(
            f"\n(токены: prompt={usage.get('prompt_tokens')}, "
            f"completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')})"
        )


if __name__ == "__main__":
    main()
