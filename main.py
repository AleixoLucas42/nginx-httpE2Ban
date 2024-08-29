import json
import re
import os
import time
import subprocess
from collections import defaultdict, deque
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime, timedelta
import pytz
import logging
from tabulate import tabulate
from multiprocessing import Process

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] 1#1: %(message)s",
    datefmt="%Y/%m/%d %H:%M:%S",
)


class TailHandler(FileSystemEventHandler):
    def __init__(self, nginx_access_log_path, error_config):
        self.nginx_access_log_path = nginx_access_log_path
        self.file = open(nginx_access_log_path, "r")
        self.file.seek(0, 2)  # Move the pointer to end of file
        self.error_config = error_config
        self.errors = defaultdict(lambda: defaultdict(lambda: deque()))
        self.local_tz = pytz.timezone(os.getenv("TZ", "America/Sao_Paulo"))

    def on_modified(self, event):
        if event.src_path == self.nginx_access_log_path:
            for line in self.file:
                print(line.strip())
                json_data = self.format_as_json(line)
                status_code = json_data.get("status_code")
                if status_code in self.error_config:
                    self.record_error(json_data, status_code)

    def format_as_json(self, line):
        nginx_json_log_map = os.getenv("NGINX_LOG_JSON_MAP", None)
        if nginx_json_log_map == None:
            parts = line.split()

            if len(parts) < 9:
                logging.error(f"Invalid line: {line}")
                return {"error": "Invalid line"}

            log_data = {
                "ip_address": parts[0],
                "datetime": f"{parts[3]} {parts[4]}".strip("[]"),
                "request": parts[5].strip('"'),
                "url": parts[6],
                "http_version": parts[7].strip('"'),
                "status_code": parts[8],
                "user_agent": " ".join(parts[9:]),  # Merge rest with user agent
            }
            return log_data
        try:
            nginx_log_map = json.loads(nginx_json_log_map)
            log_received = json.loads(line)
        except Exception as e:
            logging.error(f"Check your NGINX_LOG_JSON_MAP variable, {e}")
        log_data = {
            "ip_address": log_received[nginx_log_map["ip_address"]],
            "datetime": log_received[nginx_log_map["datetime"]],
            "request": log_received[nginx_log_map["request"]],
            "url": log_received[nginx_log_map["url"]],
            "http_version": log_received[nginx_log_map["http_version"]],
            "status_code": log_received[nginx_log_map["status_code"]],
            "user_agent": log_received[nginx_log_map["user_agent"]],
        }
        return log_data

    def record_error(self, log_data, status_code):
        ip = log_data.get("ip_address")
        timestamp = datetime.strptime(log_data.get("datetime"), "%d/%b/%Y:%H:%M:%S %z")
        timestamp = timestamp.astimezone(self.local_tz)
        error_limit = self.error_config[status_code]["limit"]
        time_window = self.error_config[status_code]["window"]

        self.errors[ip][status_code].append(timestamp)

        now = datetime.now().astimezone(self.local_tz)
        while self.errors[ip][status_code] and self.errors[ip][status_code][
            0
        ] < now - timedelta(seconds=time_window):
            self.errors[ip][status_code].popleft()

        if len(self.errors[ip][status_code]) > error_limit:
            logging.warning(
                f"{ip} has exceeded the error limit for status code {status_code} with {len(self.errors[ip][status_code])} errors"
            )
            block_ip(ip)

def unban_ip():
    if "BLOCK_TTL" in os.environ:
        logging.info("Starting ban file check")
        while True:
            reload = False
            with open(os.getenv("BANNED_CONF_FILE", "./banned.conf"), "r") as ban_file:
                lines = ban_file.readlines()
                for i, line in enumerate(lines[2:], start=2):
                    if "}" in line:
                        logging.info("Ban check file done")
                        break
                    client = line.split()
                    ip = client[0]
                    ttl = int(client[2].strip("#"))
                    epoch_now = int(time.time())
                    exp = ttl + int(os.environ["BLOCK_TTL"])
                    if exp < epoch_now:
                        lines.pop(i)
                        logging.info(f"IP {ip} unbanned due to expired TTL")
                        reload = True

            with open(os.getenv("BANNED_CONF_FILE", "./banned.conf"), "w") as ban_file:
                ban_file.writelines(lines)
            if reload:
                reload_nginx()
            time.sleep(int(os.getenv("BLOCK_TTL_CHECK_DELAY", 60)))


def show_resume():
    if "RELOAD_NGINX_CUSTOM_CMD" in os.environ:
        reload_mode = os.environ["RELOAD_NGINX_CUSTOM_CMD"]
    elif "NGINX_CONTAINER_NAME" in os.environ:
        reload_mode = f"Reload container {os.environ['NGINX_CONTAINER_NAME']}"
    else:
        reload_mode = "Reload first container running Nginx"
    resume = [
        ("Nginx reload mode", f"{reload_mode}"),
        ("LOG_LEVEL", os.getenv('LOG_LEVEL', 'INFO')),
        ("Timezone", os.getenv('TZ', 'America/Sao_Paulo')),
        ("Nginx log path", os.getenv('NGINX_LOG_PATH', './access.log')),
        ("Ban config file", os.getenv('BANNED_CONF_FILE', './banned.conf')),
        ("Policy variable", True if 'POLICY' in os.environ else False ),
        ("Policy file", './policy.json' if 'POLICY_FILE' not in os.environ and 'POLICY' not in os.environ else 'None'),
        ("Startup delay", f"{os.getenv('STARTUP_DELAY',5)}"),
        ("Nginx json map", True if 'NGINX_LOG_JSON_MAP' in os.environ else False),
    ]
    return resume

def reload_nginx():
    CUSTOM_CMD = os.getenv("RELOAD_NGINX_CUSTOM_CMD", None)
    logging.info("Sending reload signal to nginx")
    try:
        if CUSTOM_CMD == None:
            nginx_container_name = os.getenv("NGINX_CONTAINER_NAME", None)
            if nginx_container_name == None:
                container_id = subprocess.check_output(
                    "docker container ls --filter 'ancestor=nginx' --format '{{.ID}}'",
                    shell=True,
                    text=True,
                ).strip()
                logging.debug(
                    f"Reloading first nginx container returned: '{container_id}'"
                )
                subprocess.run(
                    ["docker", "exec", container_id, "nginx", "-s", "reload"],
                    check=True,
                )
                logging.info("Nginx reloaded successfully!")
                return True
            logging.debug(f"Restarting nginx on container {nginx_container_name}")
            subprocess.run(
                ["docker", "exec", nginx_container_name, "nginx", "-s", "reload"],
                check=True,
            )
            logging.info("Nginx reloaded successfully!")
            return True
        logging.info(f"Using nginx custom command: {CUSTOM_CMD}")
        subprocess.run(CUSTOM_CMD.split(), check=True)
        logging.info("Nginx reloaded successfully!")
    except subprocess.CalledProcessError as e:
        logging.critical(f"Failed to reload Nginx: {e}")
        exit(1)


def is_ip_on_file(ip):
    try:
        with open(os.getenv("BANNED_CONF_FILE", "banned.conf"), "r") as banned_file:
            content = banned_file.read()
            search_ip = re.compile(r"\b" + re.escape(ip) + r"\b")
            if search_ip.findall(content):
                return True
    except Exception as e:
        logging.error(f"Failed to check ban file, {e}")
    return False


def block_ip(ip):
    epoch_time = int(time.time())
    if is_ip_on_file(ip) == False:
        try:
            with open(os.getenv("BANNED_CONF_FILE", "banned.conf"), "r") as banned_file:
                new_content = banned_file.readlines()
                new_content.pop()  # remove last line '}'
                new_content.append(f"    {ip} 1; #{epoch_time}\n")
                new_content.append("}")
            with open(os.getenv("BANNED_CONF_FILE", "banned.conf"), "w") as banned_file:
                banned_file.writelines(new_content)
            reload_nginx()
        except Exception as e:
            logging.error(f"Some error occur while trying to block IP: '{ip}', {e}")


def load_error_config():
    policy = os.getenv("POLICY", None)
    if policy:
        return json.loads(policy)
    else:
        with open(os.getenv("POLICY_FILE", "policy.json"), "r") as file:
            return json.load(file)


def test_nginx_reload():
    time.sleep(os.getenv("STARTUP_DELAY", 5))
    logging.debug("Checking nginx reload")
    try:
        reload_nginx()
    except Exception as e:
        logging.critical("Some error occurred while trying to reload Nginx")
        exit(1)


def follow(nginx_access_log_path, error_config):
    event_handler = TailHandler(nginx_access_log_path, error_config)
    observer = Observer()
    observer.schedule(event_handler, path=nginx_access_log_path, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)  # Avoid cpu pressure
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    cleaner_process = Process(target=unban_ip)
    cleaner_process.start()
    logging.info("\n" + tabulate(show_resume(), tablefmt="fancy_grid"))
    log_path = os.getenv("NGINX_LOG_PATH", "access.log")
    error_config = load_error_config()
    test_nginx_reload()
    follow(log_path, error_config)