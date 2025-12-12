import json
import urllib.request
import zipfile
import io
import sys
import os
import re
from collections import deque


# ==================== PYPI HELPER FUNCTIONS ====================
def get_package_info(package_name, version=None):
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.load(response)
    except urllib.error.HTTPError as e:
        print(f"✗ Пакет '{package_name}' не найден на PyPI (HTTP {e.code})")
        return None
    except Exception as e:
        print(f"✗ Ошибка запроса к PyPI: {e}")
        return None

    if version is None:
        version = data["info"]["version"]

    if version not in data["releases"] or not data["releases"][version]:
        print(f"✗ Версия {version} пакета {package_name} недоступна")
        return None

    # Ищем ТОЛЬКО .whl (чтобы не попадать в dev-зависимости из sdist)
    for file_info in data["releases"][version]:
        if file_info["filename"].endswith(".whl"):
            return file_info["url"], version

    print(f"✗ wheel недоступен для {package_name}=={version} — пропускаем")
    return None


def fetch_package(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.read()
    except Exception as e:
        print(f"✗ Не удалось скачать: {e}")
        return None


def get_deps_from_wheel(wheel_data):
    try:
        with zipfile.ZipFile(io.BytesIO(wheel_data)) as zf:
            for name in zf.namelist():
                if name.endswith("METADATA"):
                    with zf.open(name) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        deps = []
                        for line in content.splitlines():
                            if line.startswith("Requires-Dist: "):
                                dep_line = line[14:].strip()
                                # Разделяем зависимость и условие
                                parts = dep_line.split(';', 1)
                                dep_spec = parts[0].strip()
                                condition = parts[1].strip() if len(parts) > 1 else ""

                                # Пропускаем optional extras (dev/test/lint)
                                if "extra ==" in condition and not any(
                                        e in condition for e in ['"main"', '"default"', '""', "''"]):
                                    continue

                                # Извлекаем имя пакета
                                dep_name = re.split(r'[<>=!~\[\] ]', dep_spec)[0].strip().lower()
                                if dep_name and dep_name not in deps:
                                    deps.append(dep_name)
                        return deps
    except Exception as e:
        print(f"! Ошибка разбора METADATA: {e}")
    return []


def build_real_graph(root_package, root_version=None, max_depth=2):
    graph = {}
    visited = set()
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


# ==================== TEST GRAPH FUNCTIONS ====================
def read_test_repo():
    # Пытаемся прочитать из файла
    test_path = "test_repo.txt"
    graph = {}
    if os.path.exists(test_path):
        try:
            with open(test_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if ":" in line:
                        node, deps_part = line.split(":", 1)
                        node = node.strip()
                        deps = [d.strip() for d in deps_part.split()] if deps_part.strip() else []
                        graph[node] = deps
        except Exception as e:
            print(f"! Ошибка чтения {test_path}: {e}")
    # Если файл не найден или пуст — используем встроенный пример
    if not graph:
        graph = {
            'A': ['B', 'C'],
            'B': ['D'],
            'C': ['D', 'E'],
            'D': [],
            'E': ['B']  # цикл: E → B → D, и B ← A, C
        }
    return graph


def print_full_test_graph(graph):
    """Выводит весь тестовый граф от всех корневых узлов (у кого нет входящих рёбер)"""
    print("Полный тестовый граф:")
    printed = set()
    # Находим все узлы без входящих рёбер (корни)
    all_nodes = set(graph.keys())
    children = set(dep for deps in graph.values() for dep in deps)
    roots = sorted(all_nodes - children) or sorted(all_nodes)

    for node in roots:
        if node not in printed:
            print(f"\nКомпонента от '{node}':")
            _print_subtree(graph, node, "", printed)


def _print_subtree(graph, node, prefix, visited):
    if node in visited:
        print(prefix + f"└── {node} ⮌ (цикл)")
        return
    print(prefix + node)
    visited.add(node)
    deps = graph.get(node, [])
    for i, dep in enumerate(deps):
        is_last = i == len(deps) - 1
        branch = "└── " if is_last else "├── "
        _print_subtree(graph, dep, prefix + branch, set(visited))


def build_subgraph_from_node(start, graph, max_depth=5):
    result = {}
    visited = set()
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if node in visited or depth > max_depth:
            continue
        visited.add(node)
        result[node] = graph.get(node, [])
        if depth < max_depth:
            for dep in graph.get(node, []):
                if dep not in visited:
                    queue.append((dep, depth + 1))
    return result


def build_reverse_graph(graph):
    rev = {}
    # Инициализируем все узлы
    for node in graph:
        rev[node] = []
    for node, deps in graph.items():
        for dep in deps:
            if dep not in rev:
                rev[dep] = []
            rev[dep].append(node)
    return rev


def print_tree_from_node(graph, start, title):
    print(f"\n{'=' * 50}")
    print(f"{title}")
    print(f"{'=' * 50}")
    visited = set()
    _print_tree_helper(graph, start, "", visited)


def _print_tree_helper(graph, node, prefix, visited):
    if node in visited:
        print(prefix + f"└── {node} ⮌ (цикл)")
        return
    print(prefix + node)
    visited.add(node)
    deps = graph.get(node, [])
    for i, dep in enumerate(deps):
        is_last = i == len(deps) - 1
        branch = "└── " if is_last else "├── "
        _print_tree_helper(graph, dep, prefix + branch, set(visited))


# ==================== MAIN ====================
def main():
    print("Выберите режим работы:")
    print("1. 📦 Реальный пакет из PyPI")
    print("2. 🔤 Тестовый граф с буквами")
    mode = input("Ваш выбор (1/2): ").strip()

    if mode == "2":
        print("\n=== 🔤 Тестовый граф ===")
        graph = read_test_repo()
        print_full_test_graph(graph)

        target = input("\nВведите узел для анализа (буква): ").strip().upper()
        if target not in graph:
            print(f"✗ Узел '{target}' отсутствует. Доступны: {', '.join(sorted(graph))}")
            return

        # Обычное дерево (прямые зависимости от target)
        subgraph = build_subgraph_from_node(target, graph)
        print_tree_from_node(subgraph, target, f"🌳 Прямые зависимости от '{target}'")

        # Обратное дерево
        rev_graph = build_reverse_graph(graph)
        rev_subgraph = {k: v for k, v in rev_graph.items() if k == target or target in v}
        # Строим подграф обратных зависимостей
        rev_deps = {}
        queue = deque([target])
        visited = {target}
        while queue:
            node = queue.popleft()
            rev_deps[node] = rev_graph.get(node, [])
            for dep in rev_deps[node]:
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        print_tree_from_node(rev_deps, target, f"🔄 Обратные зависимости для '{target}'")

    else:  # Режим 1 — реальный пакет
        if len(sys.argv) == 2:
            package = sys.argv[1]
            version = None
        elif len(sys.argv) == 3:
            package = sys.argv[1]
            version = sys.argv[2]
        else:
            package = input("📦 Имя пакета: ").strip()
            version_input = input("🔖 Версия (Enter — latest): ").strip()
            version = version_input or None

        if not package:
            sys.exit("✗ Имя пакета не указано")

        package = package.lower()
        print(f"\n🚀 Строим граф зависимостей для {package}" + (f"=={version}" if version else ""))
        graph = build_real_graph(package, version, max_depth=2)

        if not graph:
            sys.exit("✗ Не удалось построить граф зависимостей")

        # Обычное дерево
        print_tree_from_node(graph, package, "🌳 Прямые зависимости")

        # Обратное дерево — спрашиваем пакет внутри графа
        target = input(f"\nВведите пакет из графа для поиска обратных зависимостей: ").strip().lower()
        if target not in graph:
            print(f"✗ Пакет '{target}' отсутствует в построенном графе. Доступны: {', '.join(sorted(graph))}")
            return

        rev_graph = build_reverse_graph(graph)
        # Строим подграф обратных зависимостей для target
        rev_deps = {}
        queue = deque([target])
        visited = {target}
        while queue:
            node = queue.popleft()
            rev_deps[node] = rev_graph.get(node, [])
            for dep in rev_deps[node]:
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)

        print_tree_from_node(rev_deps, target, f"🔄 Обратные зависимости для '{target}'")

        # Статистика
        total_nodes = len(graph)
        total_deps = sum(len(v) for v in graph.values())
        print(f"\n📊 Всего узлов: {total_nodes}, зависимостей: {total_deps}")


if __name__ == "__main__":
    main()
