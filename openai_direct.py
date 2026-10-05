"""Заглушка: прямой доступ к OpenAI в этом проекте не используется.

Все запросы идут через GenAPI — см. genapi_request.py и GENAPI_API_KEY в .env.

Скрипт оставлен как рабочий образец на случай, если понадобится обращаться к
OpenAI напрямую. По умолчанию он отключен флагом DISABLED: запуск печатает
подсказку и завершается без traceback. Чтобы включить, добавьте в .env реальный
OPENAI_API_KEY и поставьте DISABLED = False.
"""

import os
import string
import sys

from openai import OpenAI, OpenAIError

MODEL = "gpt-3.5-turbo"
DISABLED = True  # True = скрипт не используется, работает только через GenAPI

# Разрешенные символы в заголовках HTTP (RFC 7230): ASCII без пробелов и управления.
_KEY_ALLOWED = frozenset(string.printable) - frozenset(" 	\r\n\x0b\x0c")


def validate_api_key(value: str, name: str = "OPENAI_API_KEY") -> str:
    """Проверяет API-ключ до обращения к библиотеке.

    Без проверки невалидный ключ приводит к запутанной ошибке кодирования
    внутри httpx ("'ascii' codec can't encode characters"), потому что ключ
    подставляется в HTTP-заголовок Authorization.
    """
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
            "Ключ должен выглядеть примерно так: sk-proj-xxxxxxxx... (только латиница и цифры).\n"
            "Получите его на https://platform.openai.com/api-keys и запишите в .env:\n"
            f"    {name}=sk-..."
        )

    if set(value) - _KEY_ALLOWED:
        sys.exit(f"Ошибка: {name} содержит недопустимые управляющие символы.")

    if not value.startswith("sk-"):
        print(
            f"Предупреждение: {name} не начинается с 'sk-'. "
            "Обычно так начинаются ключи OpenAI — проверьте, тот ли ключ."
        )

    return value



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
    if DISABLED:
        sys.exit(
            "Этот скрипт отключен: OpenAI напрямую не используется.\n"
            "Работа идет через GenAPI — запустите genapi_request.py\n"
            "(ключ GENAPI_API_KEY берется из .env).\n"
            "\n"
            "Чтобы включить прямой доступ к OpenAI: добавьте в .env реальный\n"
            "OPENAI_API_KEY и поставьте DISABLED = False в этом файле."
        )

    load_env()
    # Проверяем ключ до создания клиента: иначе невалидный ключ превращается
    # в непонятную ошибку кодирования внутри httpx при сборке заголовка.
    api_key = validate_api_key(os.environ.get("OPENAI_API_KEY", ""))
    os.environ["OPENAI_API_KEY"] = api_key

    params = ask_params()

    messages = []
    if params["system_message"]:
        messages.append({"role": "system", "content": params["system_message"]})
    messages.append({"role": "user", "content": params["prompt"]})

    client = OpenAI(api_key=api_key)  # ключ валидирован выше

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=params["temperature"],
            max_tokens=params["max_tokens"],
        )
    except OpenAIError as exc:
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
