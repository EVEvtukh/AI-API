"""Тот же функционал, но через GenAPI (https://gen-api.ru/).

Запуск:
    python genapi_request.py

Зависимости:
    pip install requests
    Ключ GenAPI задается в файле .env в переменной GENAPI_API_KEY.

Документация:
    POST https://api.gen-api.ru/api/v1/networks/{network_id}   — создание генерации
    GET  https://api.gen-api.ru/api/v1/request/get/{request_id} — получение результата
    is_sync: true — синхронный режим (результат приходит в том же ответе)
"""

import json
import os
import sys

import requests

BASE_URL = "https://api.gen-api.ru/api/v1/networks"
MODEL = "gpt-6-astra"  # идентификатор модели (network_id) со страницы gen-api.ru/models
TIMEOUT = 300  # синхронный режим может выполняться долго
REASONING_EFFORT = "low"  # бюджет рассуждений (low = 1024 токена) для reasoning-моделей
REASONING_EFFORT_TOKENS = 1024  # сколько токенов уходит на рассуждения при low
MIN_MAX_TOKENS = REASONING_EFFORT_TOKENS + 1  # max_tokens должен быть больше бюджета рассуждений


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

    # gpt-6-astra — reasoning-модель: бюджет рассуждений (1024 токена при
    # reasoning_effort=low) должен быть меньше max_tokens, иначе GenAPI вернет
    # ошибку 422. Поэтому требуем max_tokens > 1024.
    while True:
        max_tokens = int(input(f"Max tokens (минимум {MIN_MAX_TOKENS}, например 2048): ") or 2048)
        if max_tokens > REASONING_EFFORT_TOKENS:
            break
        print(
            f"Ошибка: max_tokens ({max_tokens}) должен быть больше "
            f"{REASONING_EFFORT_TOKENS} — бюджет токенов на рассуждения модели."
        )

    # system_message опционален: пустая строка — не используем
    system_message = input("System message (можно пропустить, Enter): ").strip()

    return {
        "prompt": prompt,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_message": system_message,
    }


def extract_answer(data: dict) -> str | None:
    """Достает текст ответа из ответа GenAPI (нативный или OpenAI-формат)."""
    # Нативный формат: {"status": "success", "result": ["...", ...]}
    result = data.get("result")
    if isinstance(result, list) and result:
        return "\n".join(str(part) for part in result)
    if isinstance(result, str):
        return result

    # Формат синхронного запроса: {"response": {OpenAI-объект}}
    # или {"response": [{OpenAI-объект}, ...]} — приходит как dict или список
    inner = data.get("response")
    if isinstance(inner, list) and inner:
        inner = inner[0]
    if isinstance(inner, dict):
        try:
            return inner["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass

    # Прямой OpenAI-совместимый формат: {"choices": [{"message": {"content": "..."}}]}
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def main() -> None:
    load_env()
    api_key = os.environ.get("GENAPI_API_KEY")
    if not api_key:
        sys.exit("Ошибка: в .env не задан GENAPI_API_KEY.")

    params = ask_params()

    messages = []
    if params["system_message"]:
        messages.append({"role": "system", "content": params["system_message"]})
    messages.append({"role": "user", "content": params["prompt"]})

    # Модель указывается в URL (network_id), а не в теле запроса
    url = f"{BASE_URL}/{MODEL}"

    payload = {
        "messages": messages,
        "temperature": params["temperature"],
        "max_tokens": params["max_tokens"],
        "reasoning_effort": REASONING_EFFORT,  # явно задаем бюджет рассуждений
        "is_sync": True,  # ждем результат в том же HTTP-ответе
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
    except requests.RequestException as exc:
        sys.exit(f"Ошибка сети при запросе к GenAPI: {exc}")

    if response.status_code != 200:
        sys.exit(f"GenAPI вернул ошибку {response.status_code}: {response.text}")

    data = response.json()

    # Проверяем статус генерации (актуально для is_sync)
    status = data.get("status")
    if status and status != "success":
        sys.exit(
            f"Генерация завершилась со статусом '{status}'. "
            f"Полный ответ: {json.dumps(data, ensure_ascii=False)}"
        )

    answer = extract_answer(data)
    if answer is None:
        sys.exit(f"Неожиданный формат ответа: {json.dumps(data, ensure_ascii=False)}")

    print("\n--- Ответ модели ---")
    print(answer)

    # Расход токенов и стоимость, если пришли в ответе
    inner = data.get("response") or {}
    if isinstance(inner, list) and inner:
        inner = inner[0]
    usage = inner.get("usage") or data.get("usage")
    if usage:
        print(
            f"\n(токены: prompt={usage.get('prompt_tokens')}, "
            f"completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')})"
        )
    if data.get("cost") is not None:
        print(f"(стоимость запроса: {data['cost']} кредитов)")


if __name__ == "__main__":
    main()
