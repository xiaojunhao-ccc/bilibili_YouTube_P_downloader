# 下载功能工具箱
import youtube_dl
import requests
import sys
import urllib.parse as urlparse
import os
from prettytable import PrettyTable
from urllib import request
from bs4 import BeautifulSoup


# 将url中的视频下载到save_dir_path文件夹中
# hook_func 为钩子函数：将下载信息传入GUI界面显示
def custom_dl_download(args):  # save_dir_path : E:/myPyThon_code/TSP
    url, save_dir_path, downloader = args
    hook_func = downloader.hook_func
    logger = downloader.logger
    # 参数设置
    ydl_opts = {
        'format': 'best',
        'outtmpl': save_dir_path + '/download_videos/%(title)s.%(ext)s',  # 前面为保存的文件夹
        'nooverwrites': True,
        'no_warnings': False,
        'ignoreerrors': True,
        'progress_hooks': [hook_func],
        'nocheckcertificate': True,
        'logger': logger
    }
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])  # 提交任务
    except Exception as e:
        print(e)
        downloader.start_status = False  # 表明当前任务（异常）结束


def ph_url_check(url):
    parsed = urlparse.urlparse(url)
    regions = ["www", "cn", "cz", "de", "es", "fr", "it", "nl", "jp", "pt", "pl", "rt"]
    for region in regions:
        if parsed.netloc == region + ".pornhub.com" or parsed.netloc == region + ".bilibili.com":
            return True
    return False


def ph_alive_check(url):
    try:
        requested = requests.get(url)
        if requested.status_code == 200:
            return True
        else:
            return False
    except Exception as e:
        print(e)
        return False
