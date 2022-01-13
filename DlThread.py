# 线程类
from PySide2.QtCore import QThread


class DlThread(QThread):
    def __init__(self, func, args):
        self.func = func
        self.args = args
        super().__init__()

    def run(self):
        # print(self.isRunning())  # TRUE
        # print(self.isFinished())    # FALSE
        self.func(self.args)

