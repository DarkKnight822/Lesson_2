import xml.etree.ElementTree as ET
import sys

def read_config(file_path):
    try:
        root = ET.parse(file_path).getroot()
    except Exception as e:
        sys.exit(f"Ошибка: {e}")

    keys = {
        "package_name": str,
        "repository_url": str,
        "test_mode": bool,
        "version": str,
        "ascii_tree_mode": bool
    }

    config = {}
    for key, typ in keys.items():
        elem = root.find(key)
        if elem is None:
            sys.exit(f"Ошибка: нет ключа '{key}'")
        val = elem.text.strip()
        if typ == bool:
            val = val.lower() in ("true", "1")
        config[key] = val

    return config

def main():
    if len(sys.argv) != 2:
        sys.exit("Использование: python main.py путь_к_конфигу.xml")
    cfg = read_config(sys.argv[1])
    print("\nПараметры конфигурации:")
    for k, v in cfg.items():
        print(f"{k} = {v}")

if __name__ == "__main__":
    main()