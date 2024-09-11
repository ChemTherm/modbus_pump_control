# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'mainUI.ui'
#
# Created by: PyQt5 UI code generator 5.15.9
#
# WARNING: Any manual changes made to this file will be lost when pyuic5 is
# run again.  Do not edit this file unless you know what you are doing.

'''
pyuic5 –x "filename".ui –o "filename".py
🔲 Termination of modbus needs to be handled
🔲 KeyboardInterrupt on startup/in general



'''


from PyQt5 import QtCore, QtGui, QtWidgets

from main import ModbusController
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import random


class PlotCanvas(FigureCanvas):
    def __init__(self, parent, modbus):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.modbus = modbus
        self.setParent(parent)
        self.plot()

    def plot(self):
        data = self.modbus.pop_flowrate_data()
        if not data:
            return
        x_values, y_values = zip(*data)
        # self.ax.clear()  # Clear the previous plot
        self.ax.plot(x_values, y_values, 'b')
        self.ax.set_title('Random Plot')
        self.draw()


class WorkerThread(QtCore.QThread):
    progress_updated = QtCore.pyqtSignal(int)
    position_updated = QtCore.pyqtSignal(int)

    def __init__(self, modbus, parent=None):
        super().__init__(parent)
        self.modbus = modbus

    def run(self):
        while True:
            self.progress_updated.emit(self.modbus.get_progress_percentage())
            self.position_updated.emit(self.modbus.total_steps)
            # self.progress_updated.emit(50)
            # self.progress_updated.emit(50)
            self.msleep(50)


class Ui_MainWindow(object):
    def __init__(self):
        super().__init__()
        # self.thread = QtCore.QThread()
        self.modbus = ModbusController('192.168.59.35')
        # print(self.modbus.get_progress_percentage())
        self.thread = WorkerThread(self.modbus)
        self.thread.progress_updated.connect(self.update_timers_ui)
        self.thread.position_updated.connect(self.update_position)
        self.thread.start()
        self.running = False

        self.timer = QtCore.QTimer()  # Initialize the QTimer
        self.timer.timeout.connect(self.update_plot)  # Connect the QTimer to the update_plot method
        self.timer.start(500)  # Set the interval to 500 ms

    def toggle_start_stop(self):
        _translate = QtCore.QCoreApplication.translate
        if self.running:
            self.modbus.stop()
            self.startStopButton.setText(_translate("MainWindow", "Start"))
            # could possibly self.timer.stop()  # Restart the timer when starting
        else:
            self.modbus.start()
            self.startStopButton.setText(_translate("MainWindow", "Stop"))
            # could possibly self.timer.start(500)  # Restart the timer when starting
        self.running = not self.running

    def do_exit(self):
        self.modbus.stop()
        exit()

    def set_ip(self):
        ip = '192.168.59.35'
        self.modbus = ModbusController(ip)

    def set_run_current(self):
        txt = self.runcurrentLine.text()
        if not txt:
            return
        print(f"setting run current to {txt}")
        self.modbus.set_run_current(int(txt))

    def correct_run_current(self):
        txt = self.runcurrentLine.text()
        if not txt:
            return
        value = int(txt)
        self.runcurrentLine.setText(str(max(min(100, value), 0)))

    def update_timers_ui(self, value):
        self.progressBar.setValue(value)

    def update_position(self, value):
        self.positionDisplay.setText(str(value))

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1294, 800)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.startStopButton = QtWidgets.QPushButton(self.centralwidget)
        self.startStopButton.setGeometry(QtCore.QRect(920, 620, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(75)
        self.startStopButton.setFont(font)
        self.startStopButton.setObjectName("startStopButton")

        self.groupBox = QtWidgets.QGroupBox(self.centralwidget)
        self.groupBox.setGeometry(QtCore.QRect(20, 20, 1251, 451))
        self.groupBox.setObjectName("groupBox")

        '''
        self.GraphSlider = QtWidgets.QScrollBar(self.groupBox)
        self.GraphSlider.setGeometry(QtCore.QRect(20, 410, 1181, 20))
        self.GraphSlider.setOrientation(QtCore.Qt.Horizontal)
        self.GraphSlider.setObjectName("GraphSlider")
        '''

        self.GraphCanvas = QtWidgets.QFrame(self.groupBox)
        self.GraphCanvas.setGeometry(QtCore.QRect(20, 30, 1181, 450))
        self.GraphCanvas.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.GraphCanvas.setFrameShadow(QtWidgets.QFrame.Raised)
        self.GraphCanvas.setObjectName("GraphCanvas")

        self.canvas_layout = QtWidgets.QVBoxLayout(self.GraphCanvas)
        self.plot_canvas = PlotCanvas(self.GraphCanvas, self.modbus)
        self.canvas_layout.addWidget(self.plot_canvas)

        self.progressBar = QtWidgets.QProgressBar(self.centralwidget)
        self.progressBar.setGeometry(QtCore.QRect(920, 520, 118, 23))
        self.progressBar.setProperty("value", 24)
        self.progressBar.setObjectName("progressBar")
        self.ProgressLabel = QtWidgets.QLabel(self.centralwidget)
        self.ProgressLabel.setGeometry(QtCore.QRect(910, 540, 111, 21))
        self.ProgressLabel.setObjectName("Progress")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1294, 21))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.ipBlock_1 = QtWidgets.QLineEdit(self.centralwidget)
        self.ipBlock_1.setGeometry(QtCore.QRect(30, 570, 51, 21))
        self.ipBlock_1.setToolTip("")
        self.ipBlock_1.setObjectName("ipBlock_1")
        self.ipBlock_2 = QtWidgets.QLineEdit(self.centralwidget)
        self.ipBlock_2.setGeometry(QtCore.QRect(90, 570, 51, 21))
        self.ipBlock_2.setToolTip("")
        self.ipBlock_2.setObjectName("ipBlock_2")
        self.ipBlock_3 = QtWidgets.QLineEdit(self.centralwidget)
        self.ipBlock_3.setGeometry(QtCore.QRect(150, 570, 51, 21))
        self.ipBlock_3.setToolTip("")
        self.ipBlock_3.setObjectName("ipBlock_3")
        self.ipBlock_4 = QtWidgets.QLineEdit(self.centralwidget)
        self.ipBlock_4.setGeometry(QtCore.QRect(210, 570, 51, 21))
        self.ipBlock_4.setToolTip("")
        self.ipBlock_4.setObjectName("ipBlock_4")
        self.setIP = QtWidgets.QPushButton(self.centralwidget)
        self.setIP.setGeometry(QtCore.QRect(270, 570, 101, 23))
        self.setIP.setObjectName("setIP")

        self.positionLabel = QtWidgets.QLabel(self.centralwidget)
        self.positionLabel.setGeometry(QtCore.QRect(1050, 530, 47, 13))
        self.positionLabel.setObjectName("positionLabel")
        self.positionDisplay = QtWidgets.QLabel(self.centralwidget)
        self.positionDisplay.setGeometry(QtCore.QRect(1100, 530, 47, 13))
        self.positionDisplay.setObjectName("positionDisplay")

        self.setRunCurrentButton = QtWidgets.QPushButton(self.centralwidget)
        self.setRunCurrentButton.setGeometry(QtCore.QRect(270, 520, 101, 23))
        self.setRunCurrentButton.setObjectName("setRunCurrentButton")
        self.runcurrentLine = QtWidgets.QLineEdit(self.centralwidget)
        self.runcurrentLine.setGeometry(QtCore.QRect(210, 520, 51, 21))
        self.runcurrentLine.setToolTip("")
        self.runcurrentLine.setObjectName("runcurrentLine")

        self.exitBtn = QtWidgets.QPushButton(self.centralwidget)
        self.exitBtn.setGeometry(QtCore.QRect(1040, 620, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(14)
        font.setBold(True)
        font.setWeight(75)
        self.exitBtn.setFont(font)
        self.exitBtn.setObjectName("exitBtn")
        self.stageDropdown = QtWidgets.QComboBox(self.centralwidget)
        self.stageDropdown.setGeometry(QtCore.QRect(820, 520, 71, 21))
        self.stageDropdown.setObjectName("stageDropdown")

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def link_ui_to_functions(self):
        self.ipBlock_1.validator()
        self.startStopButton.clicked.connect(self.toggle_start_stop)
        self.setRunCurrentButton.clicked.connect(self.set_run_current)
        self.setIP.clicked.connect(self.set_ip)
        self.exitBtn.clicked.connect(self.do_exit)
        self.runcurrentLine.setValidator(QtGui.QIntValidator(0, 999))
        self.runcurrentLine.editingFinished.connect(self.correct_run_current)
        # self.stageDropdown.

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.startStopButton.setText(_translate("MainWindow", "Start"))
        self.groupBox.setTitle(_translate("MainWindow", "ProgressGraph"))
        self.ProgressLabel.setText(_translate("MainWindow", "ProgressLabel"))
        self.exitBtn.setText(_translate("MainWindow", "Exit"))
        self.setRunCurrentButton.setText(_translate("MainWindow", "Set runcurrent"))
        self.ipBlock_1.setText(_translate("MainWindow", "192"))
        self.ipBlock_2.setText(_translate("MainWindow", "168"))
        self.ipBlock_3.setText(_translate("MainWindow", "59"))
        self.ipBlock_4.setText(_translate("MainWindow", "35"))
        self.setIP.setText(_translate("MainWindow", "Set IP"))
        self.positionLabel.setText(_translate("MainWindow", "Position"))
        self.positionDisplay.setText(_translate("MainWindow", "0"))

    def update_plot(self):
        self.plot_canvas.plot()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow()
    ui.setupUi(MainWindow)
    ui.link_ui_to_functions()
    MainWindow.show()
    sys.exit(app.exec_())
