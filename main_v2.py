import xml.etree.ElementTree as ET
import urllib.request
import zipfile
import io
import sys

def read_config(file_path):
    root = ET.parse(file_path).getroot()
    config = {}
    for key in ["package_name", "version", "repository_url"]:
        elem = root.find(key)
        if elem is None:
            sys.exit(f"Ошибка: нет ключа '{key}'")
        config[key] = elem.text.strip()
    return config

def get_deps_from_wheel(wheel_data):
    with zipfile.ZipFile(io.BytesIO(wheel_data)) as zf:
        for name in zf.namelist():
            if name.endswith('METADATA'):
                with zf.open(name) as f:
                    lines = f.read().decode().splitlines()
                    return [line[14:] for line in lines if line.startswith('Requires-Dist: ')]
    return []

def fetch_package(url):
    with urllib.request.urlopen(url) as response:
        return response.read()

def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python main.py путь_к_конфигу.xml")

    cfg = read_config(sys.argv[1])
    package_name = cfg["package_name"]
    version = cfg["version"]
    repo_url = cfg["repository_url"]

    # Ссылка на wheel-пакет
    # Пример: requests-2.31.0-py3-none-any.whl
    wheel_filename = f"{package_name}-{version}-py3-none-any.whl"
    archive_url = f"{repo_url}/{wheel_filename}"

    print(f"Скачиваем пакет: {archive_url}")
    data = fetch_package(archive_url)
    deps = get_deps_from_wheel(data)

    print(f"\nПрямые зависимости пакета '{package_name}' версии {version}:")
    if deps:
        for dep in deps:
            print(f"- {dep}")
    else:
        print("Нет прямых зависимостей.")

if __name__ == "__main__":
    main()
