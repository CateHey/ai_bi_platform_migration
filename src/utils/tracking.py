"""Logging setup, step/file tracking, and user-prompt helpers."""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "output" / "logs"


# ====================================
# Logs function
# ====================================
def setup_logger(name, log_file, level=logging.DEBUG):
    """Function to setup a logger with a file handler."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if function called multiple times
    if not logger.hasHandlers():
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# ====================================
# Execution times
# ====================================
def start_step_tracking(step_name, json_path=None):
    step_data = {
        "step_name": step_name,
        "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "success",
        "duration_sec": 0.0,
        "files": []
    }

    step_start_time = time.time()
    file_start_times = {}

    def start_file(file_name):
        file_start_times[file_name] = time.time()

    def end_file(file_name, status):
        finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration = round(time.time() - file_start_times[file_name], 2)

        existing = next((f for f in step_data["files"] if f["file"] == file_name), None)
        if existing:
            existing["status"] = status
            existing["finished_at"] = finished_at
            existing["duration_sec"] = duration
        else:
            step_data["files"].append({
                "file": file_name,
                "finished_at": finished_at,
                "duration_sec": duration,
                "status": status
            })

        # Sticky failure: once any file fails, the step status stays "failed".
        # Otherwise pick the most recent non-failure status.
        if step_data["status"] != "failed":
            if status == "failed":
                step_data["status"] = "failed"
            elif status == "skipped":
                step_data["status"] = "skipped"
            else:
                step_data["status"] = "success"

    def finalize(logger=None, force_fail=False):
        step_data["duration_sec"] = round(time.time() - step_start_time, 2)
        if force_fail:
            step_data["status"] = "failed"

        if json_path:
            path = Path(json_path)

            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        all_steps = json.load(f)
                except (json.JSONDecodeError, ValueError):
                    if logger:
                        logger.warning(f"⚠️ Invalid JSON in {json_path}, starting fresh.")
                    all_steps = {}
            else:
                all_steps = {}

            all_steps[step_name] = step_data

            with open(path, "w", encoding="utf-8") as f:
                json.dump(all_steps, f, indent=2)

        if logger:
            logger.info(f"[STEP COMPLETE] {step_name}: {step_data['status']} in {step_data['duration_sec']}s")

        return step_data

    return start_file, end_file, finalize


# ====================================
# User prompt helpers
# ====================================
def prompt_user(stage_name):  # to be removed when all functions are updated to use process_user_input
    response = input(f"Proceed with '{stage_name}'? (y = yes, s = skip): ").strip().lower()
    return response == 'y'


def initial_user_input():
    print("Welcome to the QlikView Migration Automation Script!")
    response = input("Would you like to run the full migration procedure? (y = yes, n = no): ").strip().lower()
    if response not in ['y', 'n']:
        print("Invalid input. Please enter 'y' to run all steps or 'n' to choose steps individually.")
        return initial_user_input()
    return response == 'y'


def prompt_user_v2(stage_name):  # to be renamed prompt_user
    response = input(f"Run '{stage_name}'? (r = run, s = skip, o = overwrite): ").strip().lower()
    if response not in ['r', 's', 'o']:
        print("Invalid input. Please enter 'r' to run, 's' to skip, or 'o' to overwrite.")
        return prompt_user_v2(stage_name)
    return response


def process_user_input(prompt, run_all_steps, logger):
    if run_all_steps:
        print(f"Running {prompt} as part of full procedure...")
        logger.info(f"Running {prompt} as part of full procedure...")
        return False
    else:
        logger.info(f"Prompting user for {prompt} option...")
        user_response = prompt_user_v2(f"{prompt}")

        match user_response:
            case 's':
                print(f"Skipped {prompt}")
                logger.info(f"User skipped {prompt}")
                return None
            case 'r':
                logger.info(f"User chose to run {prompt}")
                return False
            case 'o':
                logger.info(f"User chose to run {prompt} with overwrite")
                return True
            case _:
                print("Unexpected response. Please try again.")  # This should not happen, but just in case
                return None
