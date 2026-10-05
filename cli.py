"""Интерфейс меню для генерации ответов через GenAPI.

Запуск:
    python cli.py

Читает сценарии из prompts.json, показывает меню, позволяет выбрать задачу,
добавить свою или запустить свободный запрос.

Зависимости:
    pip install requests
    Ключ GenAPI задается в .env в переменной GENAPI_API_KEY.
"""

import json
import os
import sys

from genapi_request import (
    PROMPTS_FILE,
    build_messages,
    extract_answer,
    load_env,
    load_prompts,
    print_usage,
    save_prompts,
    send_request,
    validate_api_key,
)


def ask_float(label: str, default: float) -> float:
    """Запрашивает float с дефолтным значением при пустом вводе."""
    while True:
        raw = input(f"  {label} (Enter = {default}): ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print("    Введите число.")


def ask_int(label: str, default: int) -> int:
    """Запрашивает int с дефолтным значением при пустом вводе."""
    while True:
        raw = input(f"  {label} (Enter = {default}): ").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            print("    Введите целое число.")


def ask_scenario(prompts: list[dict]) -> dict | None:
    """Просит номер сценария из prompts.json и возвращает его dict или None."""
    if not prompts:
        print("  Нет доступных задач. Добавьте задачу через меню (пункт 4).")
        return None

    print("\n  Доступные задачи:")
    for p in prompts:
        print(f"    {p['id']:>3}. {p.get('name', 'без названия')}")

    answer = input("\n  Номер задачи: ").strip()
    by_id = {str(p["id"]): p for p in prompts}
    if answer not in by_id:
        print(f"  Задачи с номером {answer} не найдено.")
        return None
    return by_id[answer]


def run_task(prompts: list[dict]) -> None:
    """Выбирает задачу из prompts.json и отправляет её в GenAPI."""
    scenario = ask_scenario(prompts)
    if scenario is None:
        return

    print(f"\n  Сценарий: {scenario.get('name', 'без названия')}")
    print(f"  Роль:     {scenario.get('role', '—')}")
    print(f"  Формат:   {scenario.get('format', '—')}")

    default_input = scenario.get("test_input", "")
    if default_input:
        preview = default_input[:120] + ("..." if len(default_input) > 120 else "")
        print(f"  Тестовый ввод: {preview}")

    text_input = input("\n  Ввод (Enter = использовать тестовый): ").strip()
    prompt_text = text_input if text_input else default_input
    if not prompt_text:
        print("  Пустой ввод — нечего отправлять.")
        return

    temperature = ask_float("Temperature", 0.7)
    max_tokens = ask_int("Max tokens", 2048)

    print("\n  Отправка запроса...")
    send_and_show(
        scenario=scenario,
        prompt_text=prompt_text,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def run_free_request() -> None:
    """Свободный запрос: пользователь сам пишет текст, роль опциональна."""
    print("\n--- Свободный запрос ---")
    role = input("  Роль (Enter = пропустить): ").strip()
    prompt_text = input("  Текст запроса: ").strip()
    if not prompt_text:
        print("  Пустой ввод — нечего отправлять.")
        return

    temperature = ask_float("Temperature", 0.7)
    max_tokens = ask_int("Max tokens", 2048)

    print("\n  Отправка запроса...")
    send_and_show(
        scenario={"role": role} if role else {},
        prompt_text=prompt_text,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def send_and_show(
    scenario: dict,
    prompt_text: str,
    temperature: float,
    max_tokens: int,
) -> None:
    """Собирает сообщения, вызывает API и печатает ответ."""
    messages = build_messages(
        {
            "scenario": scenario,
            "prompt_text": prompt_text,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    )

    try:
        data = send_request(
            api_key=os.environ["GENAPI_API_KEY"],
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except SystemExit as exc:
        # send_request завершает процесс через sys.exit; перехватываем, чтобы
        # не ронять меню, и показываем текст ошибки.
        print(f"\n  Ошибка: {exc}")
        return

    answer = extract_answer(data)
    if answer is None:
        print(f"\n  Неожиданный формат ответа: {json.dumps(data, ensure_ascii=False)}")
        return

    print("\n  --- Ответ модели ---")
    print(answer)
    print_usage(data)


def add_task(prompts: list[dict]) -> list[dict]:
    """Запрашивает данные новой задачи, сохраняет в prompts.json."""
    print("\n--- Добавление новой задачи ---")
    name = input("  Название: ").strip()
    if not name:
        print("  Название не может быть пустым.")
        return prompts

    role = input("  Роль (например: Ты — дизайнер): ").strip()
    context = input("  Контекст (когда применять): ").strip()
    question = input("  Вопрос / задание: ").strip()
    fmt = input("  Формат ответа: ").strip()
    test_input = input("  Тестовый ввод: ").strip()

    new_id = max((p["id"] for p in prompts), default=0) + 1

    prompts.append(
        {
            "id": new_id,
            "name": name,
            "role": role,
            "context": context,
            "question": question,
            "format": fmt,
            "test_input": test_input,
        }
    )
    save_prompts(prompts)
    print(f"  Задача «{name}» добавлена под номером {new_id} в {PROMPTS_FILE}")
    return prompts


def delete_task(prompts: list[dict]) -> list[dict]:
    """Просит номер задачи и удаляет её из prompts.json."""
    print("\n--- Удаление задачи ---")
    if not prompts:
        print("  Нет задач для удаления.")
        return prompts

    for p in prompts:
        print(f"    {p['id']:>3}. {p.get('name', 'без названия')}")

    answer = input("  Номер задачи для удаления: ").strip()
    by_id = {str(p["id"]): p for p in prompts}
    if answer in by_id:
        removed = by_id[answer]
        prompts = [p for p in prompts if str(p["id"]) != answer]
        save_prompts(prompts)
        print(f"  Задача «{removed['name']}» удалена.")
    else:
        print(f"  Задачи с номером {answer} не найдено.")

    return prompts


def show_all_tasks(prompts: list[dict]) -> None:
    """Выводит подробную информацию о каждой задаче."""
    print("\n" + "-" * 60)
    print("  СПИСОК ЗАДАЧ")
    print("-" * 60)
    if not prompts:
        print("  Список пуст.")
        return

    for p in prompts:
        print(f"\n  [{p['id']}] {p.get('name', 'без названия')}")
        print(f"    Роль:     {p.get('role', '—')}")
        print(f"    Контекст: {p.get('context', '—')}")
        print(f"    Вопрос:   {p.get('question', '—')}")
        print(f"    Формат:   {p.get('format', '—')}")
        print(f"    Тестовый: {p.get('test_input', '—')}")
    print()


def main() -> None:
    load_env()
    api_key = validate_api_key(os.environ.get("GENAPI_API_KEY", ""))
    os.environ["GENAPI_API_KEY"] = api_key

    prompts = load_prompts()

    while True:
        print("\n" + "=" * 60)
        print("  AI ASSISTANT CLI — меню")
        print("=" * 60)
        print(f"  Загружено сценариев из prompts.json: {len(prompts)}")
        print()
        print("   1. Показать список задач")
        print("   2. Запустить задачу из prompts.json")
        print("   3. Свободный запрос (свой текст)")
        print("   4. Добавить свою задачу")
        print("   5. Удалить задачу")
        print("   0. Выйти")
        print()

        choice = input("  Выберите действие: ").strip()

        if choice == "0":
            print("\n  До свидания!\n")
            break
        elif choice == "1":
            show_all_tasks(prompts)
        elif choice == "2":
            run_task(prompts)
        elif choice == "3":
            run_free_request()
        elif choice == "4":
            prompts = add_task(prompts)
        elif choice == "5":
            prompts = delete_task(prompts)
        else:
            print("  Неизвестный вариант, попробуйте снова.")


if __name__ == "__main__":
    main()

