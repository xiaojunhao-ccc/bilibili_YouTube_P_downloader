import os
import random
import sys
import time
from PySide2.QtCore import QFile, QThread, QMutex, QObject, Signal, Slot, Qt
from PySide2.QtGui import QIcon
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QLineEdit, QMessageBox, QProgressBar, QMainWindow, QPushButton
import download_util
from enum import Enum
from DlThread import DlThread
import threading
import PySide2

"""
支持 油管、B站、P站
支持视频列表下载，单个视频下载、UP主列表下载
    输入示例：
    # url = input("输入你的视频下载地址url（例如：https://www.bilibili.com/video/BV1Lb4y1k7K3）:\n ")
    # save_dir_path = input("输入你的下载保存地址（例如：E:/myFold）:\n ")
    
    # 打包命令
    pyinstaller -F -w --i "图标路径" 主函数路径
    pyinstaller -F -i resources/leiyi.ico  VideoDownloader.py --noconsole
"""


class Downloader(QObject):
    update_signal = Signal(dict)  # 下载参数更新信号
    dd_view_append_signal = Signal(str)  # 信息提示框中追加文本信号

    def __init__(self):
        super().__init__()
        # 下载参数
        self.download_url = None  # 下载URL
        self.save_path = None  # 保存地址
        self.status = DownloaderStatus.free  # 下载器状态
        self.error_times = 0  # 出错次数
        self.MAX_ERROR_TIMES = 5  # 最大出错次数
        self.downloading_status = False  # 是否是下载状态
        self.download_thread = None  # 下载任务线程
        self.logger = Logger(self)  # 日志转输者（转输到textEdit）
        # 从文件中加载UI
        qFile = QFile("resources/downloader.ui")
        qFile.open(QFile.ReadOnly)
        qFile.close()
        self.ui = QUiLoader().load(qFile)
        self.ui.resize(1000, 800)
        self.ui.url_input.setPlaceholderText("例如：https://www.bilibili.com/video/BV1Lb4y1k7K3")
        self.ui.save_path_input.setPlaceholderText("例如：E:/myFold")
        self.ui.data_display_view.setPlaceholderText("欢迎使用AOLIGEI视频下载器，此软件仅供学习交流，请尊重视频版权，勿使用此学习软件行违法乱纪之事，否则后果自负！！！\n"
                                                     "使用此软件前请先看说明书！ 再次声明如使用该软件违法乱纪，后果自负！！！")
        self.ui.setWindowTitle('AOLIGEI下载器')
        self.ui.setWindowIcon(QIcon('resources/logo.jpg'))
        self.update_status(isDownloading=False)  # 初始化为未开始状态
        # 信号与槽
        self.ui.download_bt.clicked.connect(self.download_bt_clicked_slot)
        self.ui.cancel_bt.clicked.connect(self.cancel_bt_clicked_slot)
        # 实时更新信号与槽
        self.init_slot_connect()

    def init_slot_connect(self):
        # 绑定用于实时更新信号和槽（主要用于更新progressBar等控件）
        # self.update_signal.connect(self.pro_slot)
        self.update_signal.connect(self.progressBar_update_slot)
        self.update_signal.connect(self.speedLabel_update_slot)
        self.update_signal.connect(self.data_display_view_update_slot)
        self.dd_view_append_signal.connect(self.dd_view_append_slot)  # 文本输入框的append文字

    @Slot()
    def progressBar_update_slot(self, dic: dict):
        downloaded_bytes = dic['downloaded_bytes']
        total_bytes_estimate = dic['total_bytes_estimate']
        total_bytes = dic['total_bytes']

        if downloaded_bytes is not None and total_bytes_estimate is not None:
            self.ui.progressBar.setValue(int(100 * (downloaded_bytes / total_bytes_estimate)))

        if downloaded_bytes is not None and total_bytes is not None:
            self.ui.progressBar.setValue(int(100 * (downloaded_bytes / total_bytes)))

    @Slot()
    def dd_view_append_slot(self, msg: str):
        self.ui.data_display_view.append(msg)

    @Slot()
    def speedLabel_update_slot(self, dic: dict):
        if dic['speed'] is None:
            return
        self.ui.speed_label.setText(str(f"{round(dic['speed'] / 1000, 1)}kb/s"))

    @Slot()
    def data_display_view_update_slot(self, dic: dict):
        # self.ui.data_display_view
        pass

    def update_status(self, isDownloading: bool):
        if isDownloading:  # 如果正在下载
            self.downloading_status = True
            self.ui.download_bt.setDisabled(True)
            self.ui.download_bt.setStyleSheet("background-color: rgb(148, 148, 148)")  # grey
            self.ui.cancel_bt.setDisabled(False)
            self.ui.cancel_bt.setStyleSheet("background-color: rgb(0, 136, 0)")  # green

        else:  # 如果不在下载
            self.downloading_status = False
            self.ui.download_bt.setDisabled(False)
            self.ui.download_bt.setStyleSheet("background-color: rgb(0, 136, 0)")  # green
            self.ui.cancel_bt.setDisabled(True)
            self.ui.cancel_bt.setStyleSheet("background-color: rgb(148, 148, 148)")  # grey

    # 根据获得到的下载信息更新UI控件
    def _update_ui(self, d):  # d为progress_hooks的dictionary
        total_bytes_estimate = d.get('total_bytes_estimate', None)
        total_bytes = d.get('total_bytes', None)
        downloaded_bytes = d.get('downloaded_bytes', None)
        speed = d.get('speed', None)

        update_dict = {
            'total_bytes_estimate': total_bytes_estimate,
            'total_bytes': total_bytes,
            'downloaded_bytes': downloaded_bytes,
            'speed': speed,
        }
        self.update_signal.emit(update_dict)  # 发送更新信号

    @Slot()
    # 下载按钮点击事件
    def download_bt_clicked_slot(self):
        self.ui_print("用户按下下载键, 正在检查URL是否可行")
        if self.downloading_status is True:
            QMessageBox.warning(self.ui, '警告', '已有任务正在进行...请等等它！')
            return
        # 获取用户输入
        url = self.ui.url_input.text().strip()
        save_dir_path = self.ui.save_path_input.text().strip()
        # 检查输入
        if not self._input_check(url, save_dir_path):
            return
        # 记录下载参数
        self.download_url = url
        self.save_path = save_dir_path
        # 进行下载
        self.start_after_check()
        # args = (url, save_dir_path, self)
        # # task = threading.Thread(target=download_util.custom_dl_download, args=args)  # 测试part2
        # self.download_thread = DlThread(func=download_util.custom_dl_download, args=args)
        # self.download_thread.start()
        # # 修改状态
        # self.update_status(isDownloading=True)
        # self.ui_print("AOLIGEI下载器已经接到你的任务，正在解析URL.....")

    # 开始下载（已检查完参数）
    def start_after_check(self):
        # 进行下载
        self.ui_print("检查完毕，开始解析URL")
        # 修改状态
        self.update_status(isDownloading=True)
        self.ui_print("AOLIGEI下载器已经接到你的任务，开始任务.....")
        args = (self.download_url, self.save_path, self)
        self.download_thread = DlThread(func=download_util.custom_dl_download, args=args)
        self.download_thread.start()

    # 继续下载或重新开始下载（已检查完参数）
    def restart(self):
        self.ui_print("尝试重新下载")
        # 由于下载参数已在首次下载时保存，故此处直接调用start_after_check函数即可（YDL重新下载会接着之前的下）
        self.start_after_check()

    # 打印信息到data_display_view
    def ui_print(self, message):
        # self.ui.data_display_view.append("-------------------\n" +
        #                                  message +
        #                                  "\n-------------------\n")
        msg = "-------------------\n" + \
              message + \
              "\n-------------------\n"
        self.dd_view_append_signal.emit(msg)

    # 完成（后）处理函数
    def finish_disposal(self, d):  # d为progress_hooks的dictionary
        # 结束线程
        self._stop_thread(self.download_thread, is_finish_opt=True)
        # 更新GUI
        self.ui_print("下载完成")
        QMessageBox.warning(self.ui, '下载完成', '视频下载完成！ 尊重版权，请不要到处传播视频噢！')
        self.update_status(isDownloading=False)
        return

    # 错误（后）处理函数
    def error_disposal(self):
        self.ui_print("发生了错误")
        if self.error_times < self.MAX_ERROR_TIMES:  # 如果偶然出错则尝试重新启动
            self.error_times += 1
            self.restart()
        else:  # 否则
            self.update_status(isDownloading=False)
            return

    def hook_func(self, d):
        status = d['status']  # One of "downloading", "error", or "finished".
        if status == 'downloading':
            self._update_ui(d)
            return
        # 如果视频下载完成
        if status == 'finished':
            print('下载完成')
            self.finish_disposal(d)
            return
        # 如果发生错误
        if status == 'error':
            print('发生了错误')
            self.error_disposal()
            return

    # 取消按钮点击事件
    @Slot()
    def cancel_bt_clicked_slot(self):
        self.ui_print("用户按下取消键")
        if self.downloading_status is False:
            QMessageBox.warning(self.ui, '警告', '没有任务呢...取消了个寂寞！')
            return
        if self.download_thread.isRunning():
            # self.download_thread.quit()
            self._stop_thread(self.download_thread)
            self.update_status(isDownloading=False)

    @staticmethod
    def _stop_thread(qThread: QThread, is_finish_opt=False):
        # 存在问题待解决：下载finish后terminate会卡死，如果不terminate直接开启新任务（过多）会容易导致程序崩溃
        if qThread.quit() != 0:  # 如果quit操作线程结束失败，则强制结束
            if not is_finish_opt:  # 下载finish后terminate会卡死，不清楚原因不知道怎么解决，干脆不结束，反正也没数据流了
                qThread.terminate()  # 只有下载过程中点取消terminate才能正常结束进程
                print(11111)
            qThread.wait()

    # 输入检查
    def _input_check(self, url, save_dir_path):
        # 检查URL输入
        if url == '':
            QMessageBox.warning(self.ui, '警告', '请输入下载的视频URL！')
            return False
        if not download_util.ph_url_check(url):
            QMessageBox.warning(self.ui, '警告', '请输入正确的URL！')
            return False
        # 耗时操作，给个提示看，告知器等待，程序并没有卡死
        QMessageBox.warning(self.ui, '温馨提示', '可能会无响应一会儿，但程序并没有卡死！！我只是在检查你的URL是否可以访问，请稍后！')
        if not download_util.ph_alive_check(url):
            QMessageBox.warning(self.ui, '警告', '输入URL无法访问,请检查url输入或是否科学上网？')
            return False
        # 检查save_dir_path输入
        if save_dir_path == '':
            QMessageBox.warning(self.ui, '警告', '请输入文件保存地址！')
            return False
        if not os.path.exists(save_dir_path):
            QMessageBox.warning(self.ui, '警告', '请检查文件保存地址是否输入正确!')
            return False
        return True


# 日志记录类
class Logger:
    def __init__(self, downLoader):
        self.downLoader = downLoader

    def debug(self, msg):  # 由YDL调用
        print('debug msg==> %s' % msg)

    def error(self, msg):  # 由YDL调用
        downloader.ui_print(msg)
        self.downLoader.error_disposal()

    def warning(self, msg):  # 由YDL调用
        print('warning msg==> %s' % msg)


# 下载器状态枚举类
class DownloaderStatus(Enum):
    downloading = 1
    error = 2
    finished = 3
    free = 0  # 空闲


if __name__ == '__main__':
    app = QApplication(sys.argv)
    downloader = Downloader()
    downloader.ui.show()
    sys.exit(app.exec_())
