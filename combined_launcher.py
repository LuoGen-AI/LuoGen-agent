import os
import sys
import subprocess
import time
import logging
import tkinter as tk
from tkinter import messagebox
from urllib import request
from urllib.error import URLError
import configparser
import threading
import tarfile
import shutil
from typing import Optional, Dict, Any
import socket
import json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_and_kill_chrome():
    """检查是否有Chrome在运行，如果有则提示用户并关闭"""
    try:
        # 使用tasklist检查Chrome进程
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
        )

        if "chrome.exe" in result.stdout:
            logger.info("用户确认关闭Chrome，正在执行...")
            # 使用taskkill强制结束所有Chrome进程
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
            # 等待进程完全结束
            time.sleep(2)
            return True
        return True
    except Exception as e:
        logger.error(f"检查Chrome进程时出错: {e}")
        return False


def find_chrome_and_userdata():
    """查找Chrome路径和用户数据目录"""
    chrome_path = None
    user_data_dir = None

    # 1. 从配置文件读取Chrome路径
    try:
        config = configparser.ConfigParser()
        config.read("config.ini")
        if config.has_section("browser") and config.has_option(
            "browser", "LOCAL_CHROME_PATH"
        ):
            chrome_path = config.get("browser", "LOCAL_CHROME_PATH")
            if os.path.exists(chrome_path):
                logger.info(f"从配置文件找到Chrome路径: {chrome_path}")
    except Exception as e:
        logger.warning(f"读取配置文件出错: {e}")

    # 2. 如果配置文件中没有，尝试常见位置
    if not chrome_path or not os.path.exists(chrome_path):
        common_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                r"Google\Chrome\Application\chrome.exe",
            ),
        ]
        for path in common_paths:
            if os.path.exists(path):
                chrome_path = path
                logger.info(f"在常见位置找到Chrome: {chrome_path}")
                break

    # 3. 查找用户数据目录
    user_name = os.environ.get("USERNAME")
    base_user_data_dir = (
        f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data"
    )

    # 首先检查是否存在Default目录
    default_profile_dir = os.path.join(base_user_data_dir, "Default")
    if os.path.exists(default_profile_dir) and os.path.isdir(default_profile_dir):
        user_data_dir = default_profile_dir
        logger.info(f"找到Chrome默认配置文件目录: {user_data_dir}")
    # 如果Default目录不存在，但User Data目录存在
    elif os.path.exists(base_user_data_dir):
        user_data_dir = base_user_data_dir
        logger.info(f"找到Chrome用户数据目录: {user_data_dir}")

        # 检查是否有其他配置文件
        profiles = [
            d
            for d in os.listdir(base_user_data_dir)
            if os.path.isdir(os.path.join(base_user_data_dir, d))
            and (d.startswith("Profile ") or d == "Default")
        ]
        if profiles:
            logger.info(f"检测到的配置文件: {', '.join(profiles)}")
            # 如果有多个配置文件但没有Default，使用第一个配置文件
            if "Default" not in profiles and profiles:
                user_data_dir = os.path.join(base_user_data_dir, profiles[0])
                logger.info(f"使用配置文件: {profiles[0]}")

    return chrome_path, user_data_dir


def check_chrome_debug_port():
    """检查Chrome调试端口是否可用并尝试打开新标签页"""

    def show_warning(message):
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("提示", message)
        root.destroy()

    def open_new_tab():
        browser = None
        try:
            from playwright.sync_api import sync_playwright

            logger.info("正在尝试连接到Chrome调试端口...")

            playwright = sync_playwright().start()
            try:
                browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
                context = browser.contexts[0]
                page = context.new_page()
                page.goto("http://localhost:8000")
                logger.info("成功在Chrome中打开新标签页访问 localhost:8000")
                return True
            except Exception as e:
                logger.error(f"连接Chrome调试端口时出错: {str(e)}")
                return False
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception as e:
                        logger.error(f"关闭浏览器连接时出错: {str(e)}")
                try:
                    playwright.stop()
                except Exception as e:
                    logger.error(f"停止Playwright时出错: {str(e)}")
        except Exception as e:
            logger.error(f"初始化Playwright时出错: {str(e)}")
            return False

    def try_launch_chrome(data_dir):
        try:
            # 先关闭可能存在的Chrome进程
            if not check_and_kill_chrome():
                return False

            # 确保目录存在且Chrome有写入权限
            os.makedirs(data_dir, exist_ok=True)

            # 给目录设置完全控制权限 (仅Windows)
            if sys.platform == "win32":
                try:
                    import win32security
                    import win32con

                    user = win32security.LookupAccountName(
                        None, os.environ["USERNAME"]
                    )[0]
                    sd = win32security.GetFileSecurity(
                        data_dir, win32security.DACL_SECURITY_INFORMATION
                    )
                    dacl = win32security.ACL()
                    dacl.AddAccessAllowedAce(
                        win32security.ACL_REVISION, win32con.FILE_ALL_ACCESS, user
                    )
                    sd.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(
                        data_dir, win32security.DACL_SECURITY_INFORMATION, sd
                    )
                except ImportError:
                    logger.warning("pywin32未安装，无法设置目录权限")
                except Exception as e:
                    logger.error(f"设置目录权限失败: {e}")

            # 增强启动参数
            cmd = [
                chrome_path,
                f"--user-data-dir={data_dir}",
                "--remote-debugging-port=9222",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "http://localhost:8000",
            ]

            logger.info(f"正在启动Chrome，命令参数: {cmd}")

            # 捕获输出以便调试
            log_path = os.path.join(data_dir, "chrome_log.txt")
            with open(log_path, "w") as log_file:
                process = subprocess.Popen(
                    cmd,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    shell=sys.platform == "win32",
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    ),
                )

                # 增加检查次数和间隔
                max_checks = 3
                for i in range(max_checks):
                    time.sleep(1)
                    try:
                        if process.poll() is not None:
                            logger.error(f"Chrome已退出，状态码: {process.returncode}")
                            return False
                        request.urlopen("http://localhost:9222/json/version", timeout=1)
                        logger.info(f"成功使用数据目录启动Chrome: {data_dir}")
                        return True
                    except Exception:
                        if i == max_checks - 1:
                            logger.error(f"第{i+1}次端口检查失败")
                            process.terminate()
                            return False
                        continue
        except Exception as e:
            logger.error(f"启动Chrome失败: {e}")
            return False

    try:
        # 尝试访问Chrome调试API
        response = request.urlopen("http://localhost:9222/json/version", timeout=2)
        if response.status == 200:
            logger.info("Chrome调试端口(9222)已开启")
            if open_new_tab():
                return True
            # 如果打开新标签页失败，继续尝试重启Chrome
            logger.warning("打开新标签页失败，尝试重启Chrome")
    except (URLError, Exception) as e:
        logger.warning(f"Chrome调试端口(9222)未开启: {e}")

    # 尝试查找Chrome并启动
    chrome_path, user_data_dir = find_chrome_and_userdata()

    if not chrome_path:
        show_warning("未找到Chrome浏览器，请手动安装Chrome后重试。")
        return False

    try:
        # 首先尝试使用默认用户数据目录
        if user_data_dir:
            chrome_user_data_dir = (
                os.path.dirname(user_data_dir)
                if "Default" in user_data_dir
                else user_data_dir
            )
            if try_launch_chrome(chrome_user_data_dir):
                return True
            logger.warning("使用默认用户数据目录启动失败，尝试使用临时目录")

        # 修改临时目录路径为更安全的方案
        temp_user_data_dir = os.path.join(
            os.environ.get("TEMP", os.path.dirname(os.path.abspath(__file__))),
            "HD_HUMAN_ChromeTemp",
        )
        os.makedirs(temp_user_data_dir, exist_ok=True)

        # 如果默认目录失败，使用临时目录，增加重试机制
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            logger.info(f"使用临时目录启动Chrome，尝试第{attempt}次...")
            if try_launch_chrome(temp_user_data_dir):
                return True
            else:
                logger.warning(f"第{attempt}次使用临时目录启动Chrome失败")
                if attempt < max_retries:
                    time.sleep(1)

        error_msg = (
            "无法启动Chrome的调试模式。\n"
            "请尝试手动启动Chrome:\n"
            '1. 运行命令: chrome.exe --remote-debugging-port=9222 --user-data-dir="ChromeDebug"\n'
            "2. 或直接访问 http://localhost:8000"
        )
        show_warning(error_msg)
        return False

    except Exception as launch_error:
        error_msg = (
            f"启动Chrome失败: {launch_error}\n\n"
            "请尝试手动启动Chrome:\n"
            '1. 运行命令: chrome.exe --remote-debugging-port=9222 --user-data-dir="ChromeDebug"\n'
            "2. 或直接访问 http://localhost:8000"
        )
        show_warning(error_msg)
        return False


def get_python_executable():
    """获取正确的Python可执行文件路径"""
    # 首先检查是否在Conda环境中
    if "CONDA_PREFIX" in os.environ:
        if sys.platform == "win32":
            return os.path.join(os.environ["CONDA_PREFIX"], "python.exe")
        return os.path.join(os.environ["CONDA_PREFIX"], "bin", "python")

    # 如果不在Conda环境中，检查是否在虚拟环境中
    if "VIRTUAL_ENV" in os.environ:
        if sys.platform == "win32":
            return os.path.join(os.environ["VIRTUAL_ENV"], "Scripts", "python.exe")
        return os.path.join(os.environ["VIRTUAL_ENV"], "bin", "python")

    # 如果都没有，则使用当前Python
    return sys.executable


def ensure_playwright_and_browser():
    python_exe = get_python_executable()
    logger.info(f"使用Python解释器: {python_exe}")

    try:
        import playwright
    except ImportError:
        logger.info("未检测到 playwright，正在自动安装...")
        subprocess.check_call([python_exe, "-m", "pip", "install", "playwright"])
        logger.info("playwright 安装完成。")

    # 检查浏览器是否已安装
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # 尝试启动浏览器，如果能启动说明已安装
            browser = p.chromium.launch()
            browser.close()
            logger.info("Playwright 浏览器已安装。")
            return
    except Exception as e:
        if "Executable doesn't exist at" in str(e):
            logger.info("Playwright 浏览器未安装，尝试离线安装...")

            # 尝试离线安装
            if try_offline_install():
                logger.info("离线安装成功，验证安装...")
                try:
                    from playwright.sync_api import sync_playwright

                    with sync_playwright() as p:
                        browser = p.chromium.launch()
                        browser.close()
                        logger.info("Playwright 浏览器离线安装验证成功。")
                        return
                except Exception as verify_error:
                    logger.warning(f"离线安装验证失败: {verify_error}")

            # 如果离线安装失败，回退到在线安装
            logger.info("离线安装失败，尝试在线安装...")
            try:
                subprocess.check_call(
                    [python_exe, "-m", "playwright", "install", "chromium"]
                )
                logger.info("Playwright 浏览器在线安装完成。")
            except Exception as online_error:
                logger.error(f"在线安装也失败: {online_error}")
                logger.error("请检查网络连接或手动安装 Playwright 浏览器")
                sys.exit(1)
        else:
            logger.error(f"Playwright 浏览器检测失败: {e}")
            sys.exit(1)


def try_offline_install():
    """尝试从本地 tar 文件安装 Playwright 浏览器"""
    try:
        # 获取脚本目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        utils_dir = os.path.join(script_dir, "utils")
        tar_path = os.path.join(utils_dir, "ms-playwright.tar")

        # 检查 tar 文件是否存在
        if not os.path.exists(tar_path):
            logger.info("未找到离线安装包 ms-playwright.tar")
            return False

        # 获取用户本地目录
        user_name = os.environ.get("USERNAME", "Administrator")
        local_appdata = os.environ.get(
            "LOCALAPPDATA", f"C:\\Users\\{user_name}\\AppData\\Local"
        )
        target_dir = os.path.join(local_appdata, "ms-playwright")

        # 如果目标目录已存在，先删除
        if os.path.exists(target_dir):
            logger.info(f"删除已存在的目录: {target_dir}")
            shutil.rmtree(target_dir)

        # 创建目标目录
        os.makedirs(target_dir, exist_ok=True)

        logger.info(f"正在从 {tar_path} 解压到 {target_dir}")

        # 解压 tar 文件
        with tarfile.open(tar_path, "r") as tar:
            tar.extractall(target_dir)

        logger.info("离线安装包解压完成")
        return True

    except Exception as e:
        logger.error(f"离线安装失败: {e}")
        return False


def main():
    # 设置环境变量
    os.environ["PYTHONIOENCODING"] = "utf-8"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    utils_dir = os.path.join(script_dir, "utils")

    # 添加 utils 目录到 PATH
    os.environ["PATH"] = os.environ["PATH"] + ";" + utils_dir

    # FFMPEG 配置
    ffmpeg_path = os.path.join(script_dir, "ffmpeg", "bin")
    os.environ["FFMPEG_PATH"] = ffmpeg_path
    os.environ["PATH"] = os.environ["PATH"] + ";" + ffmpeg_path

    # ImageMagick 配置
    imagemagick_path = os.path.join(script_dir, "ImageMagick-7.1.1-Q16-HDRI")
    os.environ["IMAGE_PATH"] = imagemagick_path
    os.environ["PATH"] = os.environ["PATH"] + ";" + imagemagick_path
    os.environ["IMAGEMAGICK_BINARY"] = os.path.join(imagemagick_path, "magick.exe")

    # 添加当前目录到 PYTHONPATH
    if "PYTHONPATH" in os.environ:
        os.environ["PYTHONPATH"] = script_dir + ";" + os.environ["PYTHONPATH"]
    else:
        os.environ["PYTHONPATH"] = script_dir

    # 启动后端
    backend_path = os.path.join(utils_dir, "launcher.py")
    frontend_path = os.path.join(utils_dir, "launcher_webserver.py")

    if not os.path.exists(backend_path):
        logger.error(f"后端脚本不存在: {backend_path}")
        return
    if not os.path.exists(frontend_path):
        logger.error(f"前端脚本不存在: {frontend_path}")
        return

    logger.info("启动后端服务...")
    backend_proc = subprocess.Popen(
        [sys.executable, backend_path],
        env=os.environ.copy(),  # 确保子进程继承所有环境变量
    )

    time.sleep(2)  # 可根据实际情况调整

    logger.info("启动前端服务...")
    frontend_proc = subprocess.Popen(
        [sys.executable, frontend_path],
        env=os.environ.copy(),  # 确保子进程继承所有环境变量
    )

    # 等待前端服务启动
    time.sleep(2)

    # 确保服务已经启动
    max_retries = 5
    retry_count = 0
    while retry_count < max_retries:
        try:
            response = request.urlopen("http://localhost:8000", timeout=2)
            if response.status == 200:
                logger.info("前端服务已就绪")
                break
        except:
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"等待前端服务就绪...({retry_count}/{max_retries})")
                time.sleep(2)
            else:
                logger.warning("前端服务启动可能不完整，继续执行...")

    # 在服务启动后再检查Chrome
    check_chrome_debug_port()

    try:
        # 等待子进程退出
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在关闭服务...")
        backend_proc.terminate()
        frontend_proc.terminate()
    finally:
        logger.info("所有服务已退出")


if __name__ == "__main__":
    # 启动加载窗口
    from utils.loading_window import show_loading_window

    loading_thread = threading.Thread(target=show_loading_window)
    loading_thread.daemon = True
    loading_thread.start()

    # 确保Playwright和浏览器安装
    ensure_playwright_and_browser()
    # 启动主程序
    main()
