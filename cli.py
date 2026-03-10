import argparse
import json
import sys
import uuid
from pathlib import Path

import requests
import yaml

from hordeforge_config import RunConfig

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE_ERROR = 2
CONFIG = RunConfig.from_env()


class HordeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE_ERROR)


def load_pipeline(pipeline_file: str) -> dict:
    path = Path(pipeline_file)
    if not path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or "pipeline_name" not in data:
        raise ValueError(f"Invalid pipeline definition: {path}")
    return data


def trigger_pipeline(pipeline_name: str, inputs: dict, source: str = "cli") -> dict:
    correlation_id = str(uuid.uuid4())
    payload = {
        "pipeline_name": pipeline_name,
        "inputs": inputs,
        "source": source,
        "correlation_id": correlation_id,
    }
    response = requests.post(
        f"{CONFIG.gateway_url}/run-pipeline",
        json=payload,
        timeout=CONFIG.request_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def get_run_status(run_id: str) -> dict:
    response = requests.get(
        f"{CONFIG.gateway_url}/runs/{run_id}",
        timeout=CONFIG.status_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def build_parser() -> argparse.ArgumentParser:
    parser = HordeArgumentParser(description="HordeForge CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Run init pipeline")
    init_parser.add_argument("--repo-url", required=True, help="GitHub repository URL")
    init_parser.add_argument("--token", required=True, help="GitHub personal access token")
    init_parser.add_argument(
        "--pipeline-file",
        default=f"{CONFIG.pipelines_dir}/init_pipeline.yaml",
        help="Path to pipeline definition",
    )

    run_parser = subparsers.add_parser("run", help="Run any pipeline by name")
    run_parser.add_argument("--pipeline", required=True, help="Pipeline name (without .yaml)")
    run_parser.add_argument(
        "--inputs",
        default="{}",
        help="JSON object with pipeline inputs",
    )

    status_parser = subparsers.add_parser("status", help="Get run status by run id")
    status_parser.add_argument("--run-id", required=True, help="Pipeline run identifier")

    subparsers.add_parser("health", help="Check gateway health")
    return parser


def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def main() -> int:
    parser = build_parser()
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code == EXIT_USAGE_ERROR:
            _stderr("CLI usage error")
        raise

    try:
        if args.command == "init":
            pipeline = load_pipeline(args.pipeline_file)
            inputs = {"repo_url": args.repo_url, "github_token": args.token}
            result = trigger_pipeline(pipeline["pipeline_name"], inputs)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK

        if args.command == "run":
            try:
                inputs = json.loads(args.inputs)
            except json.JSONDecodeError as exc:
                _stderr(f"Invalid --inputs JSON: {exc}")
                return EXIT_USAGE_ERROR
            if not isinstance(inputs, dict):
                _stderr("Invalid --inputs JSON: root value must be an object")
                return EXIT_USAGE_ERROR
            result = trigger_pipeline(args.pipeline, inputs)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK

        if args.command == "status":
            result = get_run_status(args.run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return EXIT_OK

        if args.command == "health":
            response = requests.get(
                f"{CONFIG.gateway_url}/health",
                timeout=CONFIG.health_timeout_seconds,
            )
            response.raise_for_status()
            print(json.dumps(response.json(), ensure_ascii=False, indent=2))
            return EXIT_OK

        parser.print_help()
        return EXIT_USAGE_ERROR
    except (requests.RequestException, FileNotFoundError, ValueError) as exc:
        _stderr(f"CLI command failed: {exc}")
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
