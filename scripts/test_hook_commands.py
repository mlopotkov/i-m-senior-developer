"""Проверка команд хуков памятки сессии при корне плагина с пробелами.

Команда из ``hooks/hooks.json`` исполняется оболочкой, а путь установки плагина
задаёт среда: в нём могут быть пробелы. Неэкранированная подстановка
``${CLAUDE_PLUGIN_ROOT}`` разваливается на слова, и хук не запускается вообще —
оболочка отвечает кодом 127. Проверка берёт команду события SessionStart из
манифестов двух плагинов, кладёт их каталог ``hooks`` в каталог с пробелом в
имени и исполняет команду так же, как хост: через оболочку с переменной
окружения.

Охвачены только плагины памятки сессии: их хук печатает текст и ничего не
трогает снаружи. Хуки остальных плагинов ходят в рабочее дерево и в домашний
каталог, поэтому исполнять их ради проверки кавычек нельзя. Исполнение здесь
изолировано: временный домашний каталог, временный рабочий каталог, урезанная
среда и предел времени.

Запуск::

    python3 scripts/test_hook_commands.py
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
DIRECTORY_WITH_SPACE = "корень плагина с пробелами"
REMINDER_PLUGINS = ("functional-clarity", "tdd-master")
EVENT = "SessionStart"
TIMEOUT_SECONDS = 10


def event_commands(manifest: Path, event: str) -> list[str]:
    """Возвращает команды хуков типа command для одного события."""
    document = json.loads(manifest.read_text(encoding="utf-8"))
    commands = []
    for matcher in document.get("hooks", {}).get(event, []):
        for hook in matcher.get("hooks", []):
            if hook.get("type") == "command" and "command" in hook:
                commands.append(hook["command"])
    return commands


class HookCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        enclosure = Path(self._temporary_directory.name)
        self.installation_root = enclosure / DIRECTORY_WITH_SPACE
        self.installation_root.mkdir()
        self.home = enclosure / "home"
        self.home.mkdir()
        self.workdir = enclosure / "workdir"
        self.workdir.mkdir()

    def install_hooks(self, plugin: Path) -> Path:
        """Копирует каталог hooks плагина и возвращает корень установки."""
        plugin_root = self.installation_root / plugin.name
        shutil.copytree(plugin / "hooks", plugin_root / "hooks")
        return plugin_root

    def run_through_shell(
        self, command: str, plugin_root: Path
    ) -> subprocess.CompletedProcess[str]:
        """Исполняет команду хука так же, как хост: оболочка плюс переменная."""
        environment = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
        }
        return subprocess.run(
            ["/bin/sh", "-c", command],
            input="{}",
            capture_output=True,
            text=True,
            env=environment,
            cwd=str(self.workdir),
            timeout=TIMEOUT_SECONDS,
        )

    def test__session_start_commands__run_when_plugin_root_contains_space(self) -> None:
        executed = 0
        for name in REMINDER_PLUGINS:
            plugin = PLUGINS_DIR / name
            manifest = plugin / "hooks" / "hooks.json"
            self.assertTrue(manifest.is_file(), f"нет манифеста {manifest}")
            commands = event_commands(manifest, EVENT)
            self.assertNotEqual(commands, [], f"{name}: нет команд {EVENT}")
            plugin_root = self.install_hooks(plugin)
            for command in commands:
                with self.subTest(plugin=name, command=command):
                    result = self.run_through_shell(command, plugin_root)

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotEqual(result.stdout.strip(), "")
                executed += 1

        self.assertEqual(executed, len(REMINDER_PLUGINS))


if __name__ == "__main__":
    unittest.main()
