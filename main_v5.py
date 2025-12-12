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
                                parts = dep_line.split(';', 1)
                                dep_spec = parts[0].strip()
                                condition = parts[1].strip() if len(parts) > 1 else ""
                                if "extra ==" in condition and not any(
                                        e in condition for e in ['"main"', '"default"', '""', "''"]):
                                    continue
                                dep_name = re.split(r'[<>=!~\[\] ]', dep_spec)[0].strip().lower()
                                if dep_name and dep_name not in deps:
                                    deps.append(dep_name)
                        return deps
    except Exception as e:
        pass
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


# ==================== TEST GRAPH ====================
def read_test_repo():
    test_path = "test_repo.txt"
    graph = {}
    if os.path.exists(test_path):
        try:
            with open(test_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if ":" in line:
                        node, deps_part = line.split(":", 1)
                        node, deps = node.strip(), [d.strip() for d in deps_part.split()] if deps_part.strip() else []
                        graph[node] = deps
        except:
            pass
    if not graph:
        graph = {'A': ['B', 'C'], 'B': ['D'], 'C': ['D', 'E'], 'D': [], 'E': ['B']}
    return graph


def print_full_test_graph(graph):
    print("Полный тестовый граф:")
    printed = set()
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
    for i, dep in enumerate(graph.get(node, [])):
        is_last = i == len(graph[node]) - 1
        branch = "└── " if is_last else "├── "
        _print_subtree(graph, dep, prefix + branch, set(visited))


def build_subgraph_from_node(start, graph, max_depth=5):
    result = {}
    visited = set()
    queue = deque([(start, 0)])
    while queue:
        node, depth = queue.popleft()
        if node in visited or depth > max_depth: continue
        visited.add(node)
        result[node] = graph.get(node, [])
        if depth < max_depth:
            for dep in graph.get(node, []):
                if dep not in visited:
                    queue.append((dep, depth + 1))
    return result


def build_reverse_graph(graph):
    rev = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep not in rev: rev[dep] = []
            rev[dep].append(node)
    return rev


def print_tree_from_node(graph, start, title):
    print(f"\n{'=' * 40}")
    print(f"{title}")
    print(f"{'=' * 40}")
    visited = set()
    _print_tree_helper(graph, start, "", visited)


def _print_tree_helper(graph, node, prefix, visited):
    if node in visited:
        print(prefix + f"└── {node} ⮌ (цикл)")
        return
    print(prefix + node)
    visited.add(node)
    for i, dep in enumerate(graph.get(node, [])):
        is_last = i == len(graph[node]) - 1
        branch = "└── " if is_last else "├── "
        _print_tree_helper(graph, dep, prefix + branch, set(visited))


# ==================== GRAPHVIZ (МИНИМАЛИСТИЧНЫЙ) ====================
def generate_graphviz_code(graph, is_reverse=False):
    lines = ["digraph G {"]
    added_nodes = set()
    added_edges = set()

    for node, deps in graph.items():
        if node not in added_nodes:
            lines.append(f'    "{node}";')
            added_nodes.add(node)
        for dep in deps:
            if dep not in added_nodes:
                lines.append(f'    "{dep}";')
                added_nodes.add(dep)
            edge = (node, dep) if not is_reverse else (dep, node)
            if edge not in added_edges:
                lines.append(f'    "{edge[0]}" -> "{edge[1]}";')
                added_edges.add(edge)
    lines.append("}")
    return "\n".join(lines)


# ==================== MAIN ====================
def main():
    print("Режимы:")
    print("1. 📦 Реальный пакет")
    print("2. 🔤 Тестовый граф")
    mode = input("Выбор (1/2): ").strip()

    graphs_to_export = []  # [(name, graph, is_reverse)]

    if mode == "2":
        print("\n=== 🔤 Тестовый граф ===")
        graph = read_test_repo()
        print_full_test_graph(graph)

        target = input("\nУзел: ").strip().upper()
        if target not in graph:
            print(f"✗ Нет '{target}'. Есть: {', '.join(sorted(graph))}")
            return

        # Прямое дерево
        subgraph = build_subgraph_from_node(target, graph)
        print_tree_from_node(subgraph, target, f"→ Прямые от {target}")
        graphs_to_export.append((f"Прямые от {target}", subgraph, False))

        # Обратное дерево
        rev_graph = build_reverse_graph(graph)
        rev_deps = {}
        queue, visited = deque([target]), {target}
        while queue:
            node = queue.popleft()
            rev_deps[node] = [n for n in rev_graph.get(node, [])]
            for dep in rev_deps[node]:
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        print_tree_from_node(rev_deps, target, f"← Обратные для {target}")
        graphs_to_export.append((f"Обратные для {target}", rev_deps, True))

    else:  # Режим 1
        if len(sys.argv) == 2:
            package = sys.argv[1];
            version = None
        elif len(sys.argv) == 3:
            package = sys.argv[1];
            version = sys.argv[2]
        else:
            package = input("📦 Пакет: ").strip()
            version = input("🔖 Версия (Enter — latest): ").strip() or None

        if not package: sys.exit("✗ Нет имени")
        package = package.lower()

        print(f"\nСтроим граф для {package}...")
        graph = build_real_graph(package, version, max_depth=2)
        if not graph: sys.exit("✗ Не построено")

        print_tree_from_node(graph, package, "→ Прямые зависимости")
        graphs_to_export.append(("Прямые зависимости", graph, False))

        target = input(f"\nПакет для обратных зависимостей: ").strip().lower()
        if target not in graph:
            print(f"✗ Нет '{target}' в графе. Есть: {', '.join(sorted(graph))}")
            return

        rev_graph = build_reverse_graph(graph)
        rev_deps = {}
        queue, visited = deque([target]), {target}
        while queue:
            node = queue.popleft()
            rev_deps[node] = [n for n in rev_graph.get(node, []) if n in graph]
            for dep in rev_deps[node]:
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        print_tree_from_node(rev_deps, target, f"← Обратные для {target}")
        graphs_to_export.append((f"Обратные для {target}", rev_deps, True))

    # === ВЫВОД GRAPHVIZ ===
    print(f"\n{'=' * 50}")
    print("📊 Graphviz код (минималистичный)")
    print(f"{'=' * 50}")
    for name, g, is_rev in graphs_to_export:
        print(f"\n// {name}")
        print(generate_graphviz_code(g, is_reverse=is_rev))


if __name__ == "__main__":
    main()
