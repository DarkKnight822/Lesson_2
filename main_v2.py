import json
import urllib.request
import zipfile
import io
import sys
import os
import re
from xml.etree import ElementTree as ET


def load_config():
    """Загружает конфигурацию из файла config.xml"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.xml')
    if not os.path.exists(config_path):
        # Создаем базовый конфиг, если файл отсутствует
        default_config = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
    <repository_url>https://files.pythonhosted.org/packages</repository_url>
</config>'''
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(default_config)
        print(f"Создан базовый файл конфигурации: {config_path}")

    try:
        tree = ET.parse(config_path)
        root = tree.getroot()
        config = {}
        for child in root:
            config[child.tag] = child.text.strip() if child.text else ''
        return config
    except Exception as e:
        print(f"Ошибка загрузки конфигурации: {e}")
        return {'repository_url': 'https://files.pythonhosted.org/packages'}


def get_package_info(package_name, version=None):
    """Получает информацию о пакете с PyPI"""
    # Исправленный URL без лишних пробелов
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Пакет '{package_name}' не найден на PyPI")
        else:
            print(f"Ошибка HTTP при получении информации о пакете: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при получении информации о пакете: {e}")
        return None

    if version is None:
        version = data["info"]["version"]
        print(f"Используется последняя версия: {version}")

    if version not in data["releases"] or not data["releases"][version]:
        print(f"Версия {version} пакета {package_name} не найдена на PyPI")
        return None

    # Выбираем wheel-файл
    files = data["releases"][version]
    package_url = None
    for file in files:
        if file["filename"].endswith(".whl"):
            package_url = file["url"]
            break

    # Если wheel не найден, пробуем исходный код
    if not package_url:
        for file in files:
            if file["filename"].endswith(".tar.gz") or file["filename"].endswith(".zip"):
                package_url = file["url"]
                break

    if not package_url:
        print(f"Не удалось найти подходящий файл для {package_name} версии {version}")
        return None

    return package_url, version


def fetch_package(url):
    """Скачивает пакет по указанному URL"""
    try:
        print(f"Скачивание файла...")
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()
    except Exception as e:
        print(f"Ошибка при скачивании пакета: {e}")
        return None


def get_deps_from_wheel(wheel_data):
    """Извлекает зависимости из wheel файла"""
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_data)) as zf:
            for name in zf.namelist():
                if name.endswith("METADATA") or name.endswith("PKG-INFO"):
                    with zf.open(name) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        lines = content.splitlines()
                        dependencies = []
                        for line in lines:
                            if line.startswith("Requires-Dist: "):
                                dep = line[len("Requires-Dist: "):].strip()
                                # Очищаем от условий и дополнительных параметров
                                dep = re.split(r'\s*;\s*', dep)[0]  # Удаляем условия
                                dep = re.split(r'\s*\[', dep)[0]  # Удаляем extras
                                dependencies.append(dep)
                        return dependencies
    except Exception as e:
        print(f"Ошибка при извлечении зависимостей: {e}")

    return []


def main():
    config = load_config()

    if len(sys.argv) == 2:
        package_name = sys.argv[1]
        version = None
    elif len(sys.argv) == 3:
        package_name = sys.argv[1]
        version = sys.argv[2]
    else:
        package_name = input("Введите название пакета: ").strip()
        version_input = input("Введите версию (Enter для последней): ").strip()
        version = version_input if version_input else None

    result = get_package_info(package_name, version)
    if not result:
        return

    package_url, actual_version = result

    print(f"Скачиваем пакет: {package_url}")
    try:
        package_data = fetch_package(package_url)
        if not package_data:
            return

        if package_url.endswith(".whl"):
            deps = get_deps_from_wheel(package_data)
        else:
            # Для исходного кода можно добавить отдельную обработку
            deps = get_deps_from_wheel(package_data)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        return

    print(
        f"\nПрямые зависимости пакета '{package_name}'" + (f" версии {actual_version}" if actual_version else "") + ":")
    if deps:
        for dep in deps:
            print(f"- {dep}")
    else:
        print("Нет прямых зависимостей или не удалось их определить.")


if __name__ == "__main__":
    main()
