from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any

from agents.base import BaseAgent
from agents.context_utils import build_agent_result


class TestRunner(BaseAgent):
    name = "test_runner"
    description = (
        "Runs tests for multiple frameworks (pytest, jest, go test) with isolation and coverage."
    )

    def _detect_test_framework(self, context: dict[str, Any]) -> str:
        """Определяет используемый фреймворк тестирования."""
        project_metadata = context.get("project_metadata", {})
        detected_framework = project_metadata.get("test_framework")

        if detected_framework:
            return detected_framework

        # Попробуем определить по наличию конфигурационных файлов
        project_path = context.get("project_path", ".")

        if (
            os.path.exists(os.path.join(project_path, "pytest.ini"))
            or os.path.exists(os.path.join(project_path, "pyproject.toml"))
            or os.path.exists(os.path.join(project_path, "setup.cfg"))
        ):
            # Проверим наличие pytest в зависимостях
            for req_file in ["requirements.txt", "pyproject.toml", "setup.py"]:
                req_path = os.path.join(project_path, req_file)
                if os.path.exists(req_path):
                    with open(req_path) as f:
                        content = f.read().lower()
                        if "pytest" in content:
                            return "pytest"

        if os.path.exists(os.path.join(project_path, "package.json")):
            with open(os.path.join(project_path, "package.json")) as f:
                package_json = json.load(f)
                if "jest" in str(package_json.get("devDependencies", {})) or "jest" in str(
                    package_json.get("scripts", {})
                ):
                    return "jest"

        # Проверим наличие go.mod файла
        if os.path.exists(os.path.join(project_path, "go.mod")):
            return "go_test"

        # По умолчанию возвращаем первый подходящий фреймворк на основе языка
        language = project_metadata.get("language", "").lower()
        if language == "python":
            return "pytest"
        elif language in ["javascript", "typescript"]:
            return "jest"
        elif language == "go":
            return "go_test"

        return "pytest"  # по умолчанию

    def _create_isolated_environment(self, context: dict[str, Any]) -> str:
        """Создает изолированное окружение для запуска тестов."""
        # Создаем временный каталог для изоляции
        temp_dir = tempfile.mkdtemp(prefix="test_runner_isolated_")

        # Если указан путь к проекту, копируем его в изолированное окружение
        project_path = context.get("project_path", ".")
        if project_path != "." and os.path.exists(project_path):
            # Копируем проект в изолированное окружение
            dest_path = os.path.join(temp_dir, os.path.basename(project_path))
            shutil.copytree(project_path, dest_path, dirs_exist_ok=True)
            return dest_path

        return temp_dir

    def _run_pytest(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        """Запускает pytest."""
        cmd = ["python", "-m", "pytest"]

        # Добавляем флаги для покрытия кода, если включено
        coverage_enabled = context.get("coverage_enabled", False)
        if coverage_enabled:
            cmd.extend(["--cov", "--cov-report", "json", "--cov-report", "html"])

        # Добавляем дополнительные параметры из контекста
        pytest_args = context.get("pytest_args", [])
        cmd.extend(pytest_args)

        # Добавляем флаг для вывода результата в формате JSON, если возможно
        cmd.append("--json-report")
        cmd.extend(["--json-report-file", os.path.join(project_path, "pytest_report.json")])

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 минут таймаут
            )

            # Анализируем результат
            test_results = {
                "framework": "pytest",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
            }

            # Пытаемся получить отчет о покрытии, если он был сгенерирован
            if coverage_enabled:
                coverage_report = self._extract_pytest_coverage(project_path)
                if coverage_report:
                    test_results["coverage_report"] = coverage_report

            # Пытаемся получить JSON отчет, если он был сгенерирован
            json_report_path = os.path.join(project_path, "pytest_report.json")
            if os.path.exists(json_report_path):
                try:
                    with open(json_report_path) as f:
                        json_report = json.load(f)
                        test_results["json_report"] = json_report
                except Exception:
                    pass  # Игнорируем ошибки при чтении JSON отчета

            return test_results

        except subprocess.TimeoutExpired:
            return {
                "framework": "pytest",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
            }
        except Exception as e:
            return {
                "framework": "pytest",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": " ".join(cmd),
            }

    def _extract_pytest_coverage(self, project_path: str) -> dict[str, Any] | None:
        """Извлекает отчет о покрытии из результатов pytest."""
        # Проверяем наличие JSON отчета о покрытии
        cov_json_path = os.path.join(project_path, ".coverage.json")
        if os.path.exists(cov_json_path):
            try:
                with open(cov_json_path) as f:
                    return json.load(f)
            except Exception:
                pass

        # Альтернативно, можем попытаться получить покрытие через coverage report
        try:
            result = subprocess.run(
                ["python", "-m", "coverage", "report", "--format=json"],
                cwd=project_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                try:
                    coverage_data = json.loads(result.stdout)
                    return coverage_data
                except json.JSONDecodeError:
                    # Если JSON невалиден, пробуем получить процент покрытия из текстового вывода
                    match = re.search(r"(\d+)%", result.stdout)
                    if match:
                        return {
                            "coverage_percentage": float(match.group(1)),
                            "raw_output": result.stdout,
                        }
        except Exception:
            pass

        return None

    def _run_jest(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        """Запускает jest."""
        cmd = ["npx", "jest"]

        # Добавляем флаги для покрытия кода, если включено
        coverage_enabled = context.get("coverage_enabled", False)
        if coverage_enabled:
            cmd.append("--coverage")
            cmd.extend(["--coverageReporters", "json", "html"])

        # Добавляем дополнительные параметры из контекста
        jest_args = context.get("jest_args", [])
        cmd.extend(jest_args)

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 минут таймаут
            )

            test_results = {
                "framework": "jest",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
            }

            # Пытаемся получить отчет о покрытии, если он был сгенерирован
            if coverage_enabled:
                coverage_report = self._extract_jest_coverage(project_path)
                if coverage_report:
                    test_results["coverage_report"] = coverage_report

            return test_results

        except subprocess.TimeoutExpired:
            return {
                "framework": "jest",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
            }
        except Exception as e:
            return {
                "framework": "jest",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": " ".join(cmd),
            }

    def _extract_jest_coverage(self, project_path: str) -> dict[str, Any] | None:
        """Извлекает отчет о покрытии из результатов jest."""
        # Jest обычно сохраняет отчет о покрытии в папку coverage
        coverage_dir = os.path.join(project_path, "coverage")
        summary_path = os.path.join(coverage_dir, "coverage-summary.json")

        if os.path.exists(summary_path):
            try:
                with open(summary_path) as f:
                    return json.load(f)
            except Exception:
                pass

        # Альтернативно, пробуем найти json файл отчета
        for root, _dirs, files in os.walk(coverage_dir):
            for file in files:
                if file.endswith(".json") and "summary" in file.lower():
                    try:
                        with open(os.path.join(root, file)) as f:
                            return json.load(f)
                    except Exception:
                        pass

        return None

    def _run_go_test(self, project_path: str, context: dict[str, Any]) -> dict[str, Any]:
        """Запускает go test."""
        cmd = ["go", "test"]

        # Добавляем флаги для покрытия кода, если включено
        coverage_enabled = context.get("coverage_enabled", False)
        if coverage_enabled:
            cmd.extend(["-cover", "-coverprofile=coverage.out", "-covermode=atomic"])

        # Добавляем дополнительные параметры из контекста
        go_test_args = context.get("go_test_args", [])
        cmd.extend(go_test_args)

        # Добавляем флаг для подробного вывода
        cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 минут таймаут
            )

            test_results = {
                "framework": "go_test",
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": " ".join(cmd),
            }

            # Пытаемся получить отчет о покрытии, если он был сгенерирован
            if coverage_enabled:
                coverage_report = self._extract_go_coverage(project_path)
                if coverage_report:
                    test_results["coverage_report"] = coverage_report

            return test_results

        except subprocess.TimeoutExpired:
            return {
                "framework": "go_test",
                "exit_code": -1,
                "stdout": "",
                "stderr": "Test execution timed out",
                "command": " ".join(cmd),
            }
        except Exception as e:
            return {
                "framework": "go_test",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": " ".join(cmd),
            }

    def _extract_go_coverage(self, project_path: str) -> dict[str, Any] | None:
        """Извлекает отчет о покрытии из результатов go test."""
        coverage_file = os.path.join(project_path, "coverage.out")

        if os.path.exists(coverage_file):
            try:
                # Получаем процент покрытия с помощью go tool cover
                result = subprocess.run(
                    ["go", "tool", "cover", "-func=coverage.out"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    # Парсим вывод для получения общего процента покрытия
                    lines = result.stdout.split("\n")
                    for line in lines:
                        if line.startswith("total:"):
                            match = re.search(r"(\d+\.\d+)%", line)
                            if match:
                                return {
                                    "coverage_percentage": float(match.group(1)),
                                    "raw_output": result.stdout,
                                }
            except Exception:
                pass

        return None

    def run(self, context: dict[str, Any]) -> dict:
        # Определяем фреймворк тестирования
        framework = self._detect_test_framework(context)

        # Создаем изолированное окружение
        isolated_env_path = self._create_isolated_environment(context)

        try:
            # Выполняем тесты в зависимости от фреймворка
            if framework == "pytest":
                test_results = self._run_pytest(isolated_env_path, context)
            elif framework == "jest":
                test_results = self._run_jest(isolated_env_path, context)
            elif framework == "go_test":
                test_results = self._run_go_test(isolated_env_path, context)
            else:
                # Неизвестный фреймворк
                test_results = {
                    "framework": framework,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Unsupported test framework: {framework}",
                    "command": "",
                }

            # Добавляем информацию об изоляции
            test_results["isolated"] = True
            test_results["sandbox_path"] = isolated_env_path

            # Определяем статус на основе результатов тестов
            status = "SUCCESS" if test_results["exit_code"] == 0 else "FAILURE"

            # Создаем результат агента
            result = build_agent_result(
                status=status,
                artifact_type="test_results",
                artifact_content=test_results,
                reason=f"Test execution completed for {framework}. Exit code: {test_results['exit_code']}",
                confidence=0.95,
                logs=[f"Executed tests with {framework}: exit_code={test_results['exit_code']}"],
                next_actions=["review_agent"] if test_results["exit_code"] == 0 else ["fix_agent"],
            )

            # Добавляем прямые ключи для совместимости с ожиданиями тестов
            result["artifact_type"] = "test_results"
            result["artifact_content"] = test_results

            # Добавляем результаты тестов верхний уровень для условий цикла
            result["test_results"] = test_results

            # Если включен режим покрытия, но отчет о покрытии отсутствует, добавляем заглушку
            coverage_enabled = context.get("coverage_enabled", False)
            if coverage_enabled and "coverage_report" not in test_results:
                test_results["coverage_report"] = {
                    "coverage_percentage": 0.0,
                    "message": "Coverage report not generated - coverage tool may not be available",
                }

            return result

        finally:
            # Удаляем изолированное окружение после завершения
            try:
                shutil.rmtree(isolated_env_path)
            except Exception:
                # Игнорируем ошибки при удалении временного каталога
                pass
