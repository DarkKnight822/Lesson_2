import json
import urllib.request
import zipfile
import io
import sys
import os
import re
import xml.etree.ElementTree as ET
from collections import deque


# ==================== CONFIG ====================
def load_config(config_path=None):
    """Загружает config.xml (если есть), но не требует обязательных полей"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.xml')

    config = {'repository_url': 'https://files.pythonhosted.org/packages'}
    if os.path.exists(config_path):
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            for child in root:
                config[child.tag] = (child.text or '').strip()
        except Exception as e:
            print(f"[!] Ошибка чтения {config_path}: {e}")
    else:
        print(f"[i] Конфиг не найден: {config_path} — используются значения по умолчанию")
    return config


# ==================== PYPI DATA ====================
def get_package_info(package_name, version=None):
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        print(f"[✗] Пакет '{package_name}' не найден на PyPI (HTTP {e.code})")
        return None
    except Exception as e:
        print(f"[✗] Ошибка запроса к PyPI: {e}")
        return None

    if version is None:
        version = data["info"]["version"]
        print(f"[✓] Версия не задана — выбрана актуальная: {version}")

    if version not in data["releases"] or not data["releases"][version]:
        print(f"[✗] Версия {version} пакета {package_name} недоступна")
        return None

    # Ищем wheel → fallback на sdist
    files = data["releases"][version]
    for file_info in files:
        if file_info["filename"].endswith(".whl"):
            return file_info["url"], version
    for file_info in files:
        if file_info["filename"].endswith((".tar.gz", ".zip")):
            return file_info["url"], version

    print(f"[✗] Нет подходящих файлов для {package_name}=={version}")
    return None


# ==================== WHEEL PARSING ====================
def get_deps_from_wheel(wheel_data):
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_data)) as zf:
            for name in zf.namelist():
                if name.endswith(("METADATA", "PKG-INFO")):
                    with zf.open(name) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        deps = []
                        for line in content.splitlines():
                            if line.startswith("Requires-Dist: "):
                                dep = line[14:].strip()
                                # Очищаем: urllib3>=1.21.1,<3 (от условий, extras, версий)
                                dep = re.split(r'[;\[\]<>!=~]', dep)[0].strip()
                                if dep:
                                    deps.append(dep.lower())
                        return deps
    except Exception as e:
        print(f"[!] Ошибка разбора архива: {e}")
    return []


# ==================== BFS GRAPH BUILDING ====================
def build_dependency_graph(root_package, root_version=None, max_depth=3):

    graph = {}
    visited = set()
    # queue: (package, version, depth)
    queue = deque([(root_package.lower(), root_version, 0)])

    while queue:
        pkg, ver, depth = queue.popleft()
        if pkg in visited or depth > max_depth:
            continue
        visited.add(pkg)



        info = get_package_info(pkg, ver)
        if not info:
            graph[pkg] = []
            continue

        url, actual_ver = info
        data = fetch_package(url)
        if data:
            deps = get_deps_from_wheel(data)
        else:
            deps = []

        graph[pkg] = deps

        if depth < max_depth:
            for dep in deps:
                if dep not in visited:
                    queue.append((dep, None, depth + 1))

    return graph


def fetch_package(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.read()
    except Exception as e:
        print(f"[✗] Не удалось скачать: {e}")
        return None


# ==================== ASCII TREE ====================
def print_ascii_tree(graph, node, prefix="", visited=None):
    if visited is None:
        visited = set()
    if node in visited:
        print(prefix + f"└── {node} ⮌ (цикл)")
        return

    print(prefix + node)
    visited.add(node)

    if node not in graph:
        return

    deps = graph[node]
    for i, dep in enumerate(deps):
        is_last = i == len(deps) - 1
        branch = "└── " if is_last else "├── "
        extend = "    " if is_last else "│   "
        print_ascii_tree(graph, dep, prefix + branch, visited | {node})


# ==================== MAIN ====================
def main():
    # 1. Загружаем конфиг (опционально)
    config = load_config()

    # 2. Определяем пакет и версию
    if len(sys.argv) == 2:
        package = sys.argv[1]
        version = None
    elif len(sys.argv) == 3:
        package = sys.argv[1]
        version = sys.argv[2]
    else:
        package = input("📦 Имя пакета: ").strip()
        version = input("🔖 Версия (Enter — latest): ").strip() or None

    if not package:
        sys.exit("[!] Имя пакета не указано")

    # 3. Строим граф
    print(f"\n🚀 Строим граф зависимостей для {package}" + (f"=={version}" if version else ""))
    graph = build_dependency_graph(package, version, max_depth=2)

    # 4. Выводим дерево
    print("\n" + "=" * 50)
    print("🌳 Граф зависимостей (ASCII-tree):")
    print("=" * 50)
    print_ascii_tree(graph, package.lower())

    # 5. Статистика
    total_nodes = len(graph)
    total_deps = sum(len(v) for v in graph.values())
    print(f"\n📊 Всего узлов: {total_nodes}, зависимостей: {total_deps}")


if __name__ == "__main__":
    main()
