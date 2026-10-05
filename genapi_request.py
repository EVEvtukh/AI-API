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
import string
import sys

import requests

BASE_URL = "https://api.gen-api.ru/api/v1/networks"
MODEL = "gpt-6-astra"  # идентификатор модели (network_id) со страницы gen-api.ru/models
TIMEOUT = 300  # синхронный режим может выполняться долго
REASONING_EFFORT = "low"  # бюджет рассуждений (low = 1024 токена) для reasoning-моделей
REASONING_EFFORT_TOKENS = 1024  # сколько токенов уходит на рассуждения при low
MIN_MAX_TOKENS = REASONING_EFFORT_TOKENS + 1  # max_tokens должен быть больше бюджета рассуждений
PROMPTS_FILE = "prompts.json"  # сценарии запросов, доступные по номеру
RUSSIAN_RULE = "Всегда отвечай на русском языке."  # без этого модель часто уходит в English

# Разрешенные символы в заголовках HTTP (RFC 7230): ASCII без пробелов и управления.
_KEY_ALLOWED = frozenset(string.printable) - frozenset(" 	\r\n\x0b\x0c")


def validate_api_key(value: str, name: str = "GENAPI_API_KEY") -> str:
    """Проверяет API-ключ до обращения к библиотеке."""
    if not value:
        sys.exit(
            f"Ошибка: переменная {name} не задана.\n"
            "Пропишите ключ в файле .env или задайте его в окружении."
        )

    stripped = value.strip()
    if stripped != value:
        print(f"Предупреждение: из {name} удалены пробелы по краям.")
        value = stripped

    if not value.isascii():
        bad = sorted({ch for ch in value if ord(ch) > 127})
        sys.exit(
            f"Ошибка: {name} содержит недопустимые (не-ASCII) символы: {''.join(bad)}\n"
            "Похоже, вместо реального ключа оставлен заполнитель из примера.\n"
            "Ключ должен состоять только из латиницы и цифр."
        )

    if set(value) - _KEY_ALLOWED:
        sys.exit(f"Ошибка: {name} содержит недопустимые управляющие символы.")

    return value


def load_prompts(path: str = PROMPTS_FILE) -> list[dict]:
    """Читает сценарии из prompts.json.

    Возвращает пустой список, если файла нет или он битый, — запуск при этом
    не падает, просто сценарии недоступны и работает ручной ввод.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Предупреждение: {path} не читается как JSON ({exc}). Работаю без сценариев.")
        return []

    prompts = data.get("prompts") if isinstance(data, dict) else None
    if not isinstance(prompts, list):
        print(f"Предупреждение: в {path} нет списка 'prompts'. Работаю без сценариев.")
        return []

    return [p for p in prompts if isinstance(p, dict) and "id" in p]


def choose_scenario(prompts: list[dict]) -> dict | None:
    """Показывает меню и возвращает выбранный сценарий (None = свой запрос)."""
    print("\nСценарии из prompts.json:")
    for item in prompts:
        print(f"  {item['id']:>3}. {item.get('name', 'без названия')}")
    print("    0. Ввести свой запрос вручную")

    answer = input("\nНомер сценария: ").strip()
    if not answer or answer == "0":
        return None

    by_id = {str(item["id"]): item for item in prompts}
    if answer in by_id:
        return by_id[answer]

    print(f"Сценария с номером {answer} нет — перехожу на ручной ввод.")
    return None


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


def ask_params(prompts: list[dict]) -> dict:
    """Запрашивает параметры и возвращает словарь для сборки запроса."""
    scenario = choose_scenario(prompts)

    if scenario:
        # Встроенный сценарий: просим только текст входа (по умолчанию test_input)
        test_input = scenario.get("test_input", "")
        print(f"\nСценарий: {scenario.get('name', 'без названия')}")
        print(f"По умолчанию (test_input): {test_input[:80]}...")
        text_input = input("Текст/данные (Enter = использовать test_input): ").strip()
        prompt_text = text_input if text_input else test_input
        if not prompt_text:
            sys.exit("Ошибка: текст не может быть пустым.")

        temperature = float(input("Temperature (например 0.7): ") or 0.7)
        while True:
            max_tokens = int(
                input(f"Max tokens (минимум {MIN_MAX_TOKENS}, например 2048): ") or 2048
            )
            if max_tokens > REASONING_EFFORT_TOKENS:
                break
            print(
                f"Ошибка: max_tokens ({max_tokens}) должен быть больше "
                f"{REASONING_EFFORT_TOKENS} — бюджет токенов на рассуждения модели."
            )

        return {
            "scenario": scenario,
            "prompt_text": prompt_text,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    # Ручной ввод (свободный запрос)
    prompt_text = input("Введите запрос для модели: ").strip()
    if not prompt_text:
        sys.exit("Ошибка: запрос не может быть пустым.")

    temperature = float(input("Temperature (например 0.7): ") or 0.7)
    while True:
        max_tokens = int(input(f"Max tokens (минимум {MIN_MAX_TOKENS}, например 2048): ") or 2048)
        if max_tokens > REASONING_EFFORT_TOKENS:
            break
        print(
            f"Ошибка: max_tokens ({max_tokens}) должен быть больше "
            f"{REASONING_EFFORT_TOKENS} — бюджет токенов на рассуждения модели."
        )

    system_message = input("System message (можно пропустить, Enter): ").strip()

    return {
        "scenario": None,
        "prompt_text": prompt_text,
        "system_message": system_message,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }


def build_messages(params: dict) -> list[dict]:
    """Собирает системное и пользовательское сообщения по результатам ask_params."""
    scenario = params.get("scenario")
    if scenario:
        # Система из сценария + правило на русский
        parts = [
            scenario.get("role"),
            scenario.get("context"),
            scenario.get("format"),
            RUSSIAN_RULE,
        ]
        system = "\n".join(part for part in parts if part)
        # Пользователь: вопрос + тестовый/введённый текст
        user = scenario.get("question", "")
        if params.get("prompt_text"):
            user = f"{user}\n\n{params['prompt_text']}"
    else:
        # Свободный запрос: правило на русский + опциональная system message
        system = RUSSIAN_RULE
        if params.get("system_message"):
            system = f"{params['system_message']}\n{RUSSIAN_RULE}"
        user = params["prompt_text"]

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


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


def save_prompts(prompts: list[dict], path: str = PROMPTS_FILE) -> None:
    """Перезаписывает prompts.json списком сценариев."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"prompts": prompts}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def send_request(
    api_key: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> dict:
    """Отправляет запрос в GenAPI и возвращает разобранный JSON-ответ.

    Завершает процесс с понятным сообщением при сетевой ошибке, HTTP-ошибке
    или не-успешном статусе генерации.
    """
    # Модель указывается в URL (network_id), а не в теле запроса
    url = f"{BASE_URL}/{MODEL}"

    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
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

    return data


def print_usage(data: dict) -> None:
    """Печатает расход токенов и стоимость, если они пришли в ответе."""
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


def main() -> None:
    load_env()
    # Проверяем ключ до обращения к API: иначе невалидный ключ превращается
    # в непонятную ошибку кодирования внутри httpx/requests при сборке заголовка.
    api_key = validate_api_key(os.environ.get("GENAPI_API_KEY", ""))

    params = ask_params(load_prompts())
    messages = build_messages(params)

    data = send_request(
        api_key=api_key,
        messages=messages,
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
    )

    answer = extract_answer(data)
    if answer is None:
        sys.exit(f"Неожиданный формат ответа: {json.dumps(data, ensure_ascii=False)}")

    print("\n--- Ответ модели ---")
    print(answer)
    print_usage(data)


if __name__ == "__main__":
    main()
