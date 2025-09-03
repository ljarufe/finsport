import os
import subprocess

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "finsport.settings")

SCRAPY_SETTINGS = {
    "USER_AGENT": "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)",
    "LOG_ENABLED": True,
    "LOG_LEVEL": "WARNING",
}


def run_scrapy_spider(spider_name: str):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scrapy_root = os.path.join(project_root, "bet_scraper")

    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "finsport.settings"
    env["PYTHONPATH"] = project_root + ":" + env.get("PYTHONPATH", "")

    cmd = ["python", "-m", "scrapy", "crawl", spider_name]
    for k, v in SCRAPY_SETTINGS.items():
        cmd += ["-s", f"{k}={v}"]
    result = subprocess.run(
        cmd,
        cwd=scrapy_root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
