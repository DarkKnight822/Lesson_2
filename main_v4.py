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
            sys.exit(f"Ошибка: нет ключа '{key}' в конфиге")
        config[key] = elem.text.strip()
    return config

def read_test_repo(file_path):
    graph = {}
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            node, deps = line.split(":")
            graph[node.strip()] = [d.strip() for d in deps.split()] if deps.strip() else []
    return graph

def build_graph(node, graph, visited=None, result=None):
    if visited is None: visited = set()
    if result is None: result = {}
    if node in visited:
        return result
    visited.add(node)
    result[node] = graph.get(node, [])
    for dep in graph.get(node, []):
        build_graph(dep, graph, visited, result)
    return result

def print_ascii_tree(graph, node, prefix="", visited=None):
    if visited is None: visited = set()
    if node in visited:
        print(prefix + node + " (цикл!)")
        return
    print(prefix + node)
    visited.add(node)
    for dep in graph.get(node, []):
        print_ascii_tree(graph, dep, prefix + "  ", visited)

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

def build_real_graph(package_name, version, repo_url):
    wheel_filename = f"{package_name}-{version}-py3-none-any.whl"
    archive_url = f"{repo_url}/{wheel_filename}"
    print(f"\nСкачиваем пакет: {archive_url}")
    try:
        data = fetch_package(archive_url)
        deps = get_deps_from_wheel(data)
    except:
        print("Ошибка при скачивании пакета или обработке зависимостей.")
        deps = []
    graph = {package_name: deps}
    for dep in deps:
        graph[dep] = []
    return graph

def find_reverse_dependencies(graph, target):
    reverse = []
    def dfs(node, visited):
        for parent, deps in graph.items():
            if parent in visited:
                continue
            if node in deps:
                reverse.append(parent)
                visited.add(parent)
                dfs(parent, visited)
    dfs(target, set())
    return reverse


def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python main.py путь_к_конфигу.xml")

    cfg = read_config(sys.argv[1])

    print("\n=== Тестовый граф с буквами ===")
    test_graph = read_test_repo("test_repo.txt")
    test_root = input("Введите корневую букву для тестового графа: ").strip().upper()
    full_test_graph = build_graph(test_root, test_graph)
    print_ascii_tree(full_test_graph, test_root)

    # Для тестового графа лучше использовать исходный graph
    target = input("Введите пакет для обратных зависимостей (тестовый граф): ").strip()
    rev = find_reverse_dependencies(test_graph, target)
    print(f"Обратные зависимости для {target}: {rev if rev else 'Никто не зависит'}")

    print("\n=== Граф для реального пакета ===")
    real_graph = build_real_graph(cfg["package_name"], cfg["version"], cfg["repository_url"])
    full_real_graph = build_graph(cfg["package_name"], real_graph)
    print_ascii_tree(full_real_graph, cfg["package_name"])

if __name__ == "__main__":
    main()
