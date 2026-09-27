import os
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5 import uic
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QTableWidgetItem,
)

from scheduler import ProcessSpec, SimulationResult, run_simulation


BASE_DIR = Path(__file__).resolve().parent
os.chdir(str(BASE_DIR))
form_class = uic.loadUiType(str(BASE_DIR / "os.ui"))[0]


def icon(name: str) -> QIcon:
    return QIcon(str(BASE_DIR / "logo" / name))


@dataclass
class UIProcess:
    process_id: int
    arrival_time: int
    burst_time: int
    color: QColor
    gpt_model: str = "N/A"
    complexity: int = 0


class ProcessScheduler:
    def __init__(self) -> None:
        self.processes: List[UIProcess] = []

    def add_process(
        self,
        process_id: int,
        arrival_time: int,
        burst_time: int,
        color: QColor,
        gpt_model: str = "N/A",
        complexity: int = 0,
    ) -> None:
        self.processes.append(
            UIProcess(
                process_id,
                arrival_time,
                burst_time,
                color,
                gpt_model,
                complexity,
            )
        )

    def remove_process(self, process_id: int) -> None:
        self.processes = [p for p in self.processes if p.process_id != process_id]

    def get_process_color(self, process_id: int) -> Optional[QColor]:
        for process in self.processes:
            if process.process_id == process_id:
                return process.color
        return None

    def get_processes_length(self) -> int:
        return len(self.processes)


class OS_Scheduler(QMainWindow, form_class):
    ALGORITHM_MAP = {
        1: "FCFS",
        2: "RR",
        3: "SPN",
        4: "SRTN",
        5: "HRRN",
        6: "DRR",
    }

    def __init__(self) -> None:
        super().__init__()
        self.setupUi(self)

        self.core = [0] * 4
        self.algorithm = 0
        self.time_quantum = 2
        self.last_result: Optional[SimulationResult] = None

        self.addProcessName = 1
        self.addArrivalTime = 0
        self.addBurstTime = 0

        self.selected_model_flag: Optional[int] = None
        self.selected_complexity_flag: Optional[int] = None

        self.scheduler = ProcessScheduler()

        self.setWindowTitle("OS Scheduler")
        self.setWindowIcon(icon("logo.png"))
        self.move(200, 100)
        self.resize(1600, 900)

        self.pb_model1.setCheckable(True)
        self.pb_model2.setCheckable(True)
        self.pb_high.setCheckable(True)
        self.pb_mid.setCheckable(True)
        self.pb_low.setCheckable(True)

        self.gb_Timeq.setVisible(False)
        self.pb_remove.setVisible(False)
        self.gb_model.setEnabled(False)
        self.gb_complex.setEnabled(False)
        self.gb_model.setStyleSheet("color: lightgray")
        self.gb_complex.setStyleSheet("color: lightgray")
        self.sb_Timeq.setRange(1, 20)
        self.sb_Timeq.setValue(2)

        self.tw_process.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.tw_result.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.tw_gantt.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.cb_algorithm.currentIndexChanged.connect(
            lambda index: self.comboBoxFunction(1, index)
        )
        for i in range(4):
            combobox = getattr(self, "cb_core{}".format(i))
            combobox.currentIndexChanged.connect(
                lambda index, i=i: self.comboBoxFunction(i + 2, index)
            )

        self.pb_model1.clicked.connect(lambda: self.GPTSelectFunction(1))
        self.pb_model2.clicked.connect(lambda: self.GPTSelectFunction(2))
        self.pb_high.clicked.connect(lambda: self.GPTSelectFunction(3))
        self.pb_mid.clicked.connect(lambda: self.GPTSelectFunction(4))
        self.pb_low.clicked.connect(lambda: self.GPTSelectFunction(5))

        for i in range(3):
            getattr(self, "pb_up{}".format(i + 1)).clicked.connect(
                (lambda index: lambda: self.processAddFunction(index * 2 + 1))(i)
            )
            getattr(self, "pb_down{}".format(i + 1)).clicked.connect(
                (lambda index: lambda: self.processAddFunction(index * 2 + 2))(i)
            )

        self.pb_resetp.clicked.connect(lambda: self.processAddFunction(7))
        self.pb_savep.clicked.connect(lambda: self.processAddFunction(8))
        self.tw_process.itemSelectionChanged.connect(self.rbVisibilityFunction)
        self.pb_remove.clicked.connect(self.processRemoveFunction)
        self.pb_random.clicked.connect(self.RandomAddProcessFunction)
        self.a_exit.triggered.connect(QApplication.exit)
        self.pb_start.clicked.connect(self.startFunction)
        self.sb_Timeq.valueChanged.connect(
            lambda value: setattr(self, "time_quantum", value)
        )

        self._update_core_label()
        self._clear_output()

    def _update_core_label(self) -> None:
        self.lb_core.setText(
            "현재 코어: P-Core : {}개, E-Core : {}개".format(
                self.core.count(1), self.core.count(2)
            )
        )

    def _clear_output(self) -> None:
        self.tw_result.setRowCount(0)
        self.tw_gantt.clearContents()
        self.tw_gantt.setRowCount(0)
        self.tw_gantt.setColumnCount(1)
        self.tw_gantt.setHorizontalHeaderItem(0, QTableWidgetItem("Core"))
        self.lb_time.setText("")
        self.lb_sec.setText("")
        for label_name in ("label_3", "label_5", "label_8", "label_9"):
            getattr(self, label_name).setText("0.0 W")
        self.statusBar().clearMessage()

    def startFunction(self) -> None:
        if not self.scheduler.processes:
            QMessageBox.warning(self, "시작 실패", "프로세스가 입력되지 않았습니다.")
            return
        if not any(self.core):
            QMessageBox.warning(self, "시작 실패", "Core가 선택되지 않았습니다.")
            return
        if self.algorithm not in self.ALGORITHM_MAP:
            QMessageBox.warning(self, "시작 실패", "알고리즘을 선택해 주세요.")
            return

        try:
            result = self.sendInfoToAlgorithmFunction()
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, "실행 실패", str(exc))
            return

        self.last_result = result
        self._render_result(result)

    def sendInfoToAlgorithmFunction(self) -> SimulationResult:
        algorithm_name = self.ALGORITHM_MAP[self.algorithm]
        specs = [
            ProcessSpec(
                p.process_id,
                p.arrival_time,
                p.burst_time,
                p.gpt_model,
                p.complexity if p.complexity else max(1, min(p.burst_time, 30)),
            )
            for p in self.scheduler.processes
        ]
        return run_simulation(
            specs,
            self.core,
            algorithm_name,
            self.time_quantum,
        )

    def _render_result(self, result: SimulationResult) -> None:
        self._render_gantt(result)
        self._render_result_table(result)
        self._render_power(result)
        self.lb_time.setText(str(result.duration))
        self.lb_sec.setText("초")
        self.statusBar().showMessage(
            "평균 WT: {} | 평균 NTT: {} | 총 전력 사용량: {} W".format(
                result.average_waiting_time,
                result.average_normalized_turnaround_time,
                result.total_power_usage,
            )
        )

    def _render_gantt(self, result: SimulationResult) -> None:
        active_core_ids = [
            cid for cid, core_type in result.core_types.items() if core_type is not None
        ]
        self.tw_gantt.clearContents()
        self.tw_gantt.setRowCount(len(active_core_ids))
        self.tw_gantt.setColumnCount(result.duration + 1)
        self.tw_gantt.setHorizontalHeaderItem(0, QTableWidgetItem("Core"))

        for tick in range(result.duration):
            self.tw_gantt.setHorizontalHeaderItem(tick + 1, QTableWidgetItem(str(tick)))

        for row, core_id in enumerate(active_core_ids):
            core_type = result.core_types[core_id]
            self.tw_gantt.setItem(row, 0, QTableWidgetItem("Core {}({})".format(core_id, core_type)))
            timeline = result.core_timelines[core_id]
            for tick, pid in enumerate(timeline):
                item = QTableWidgetItem("-" if pid == 0 else "P{:02}".format(pid))
                item.setTextAlignment(Qt.AlignCenter)
                if pid:
                    color = self.scheduler.get_process_color(pid)
                    if color is not None:
                        item.setBackground(color)
                self.tw_gantt.setItem(row, tick + 1, item)

        self.tw_gantt.resizeColumnsToContents()

    def _render_result_table(self, result: SimulationResult) -> None:
        self.tw_result.setSortingEnabled(False)
        self.tw_result.setRowCount(0)

        for row_data in sorted(result.process_results, key=lambda item: item.pid):
            row = self.tw_result.rowCount()
            self.tw_result.insertRow(row)
            pid_text = "P{:02}".format(row_data.pid)
            if row_data.status == "terminated":
                pid_text += " (OUT)"

            values = [
                pid_text,
                str(row_data.arrival_time),
                str(row_data.burst_time),
                str(row_data.waiting_time),
                str(row_data.turnaround_time),
                "{:.2f}".format(row_data.normalized_turnaround_time),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                if row_data.status == "terminated":
                    item.setToolTip("BT가 30 이상인 프로세스가 30 work unit을 처리하여 강제 종료됨")
                self.tw_result.setItem(row, column, item)

        self.tw_result.setSortingEnabled(True)

    def _render_power(self, result: SimulationResult) -> None:
        power_labels = ["label_3", "label_5", "label_8", "label_9"]
        for core_id, label_name in enumerate(power_labels):
            getattr(self, label_name).setText(
                "{:.1f} W".format(result.core_power_usage.get(core_id, 0.0))
            )

    def updateProcessNameFunction(self) -> None:
        used = {p.process_id for p in self.scheduler.processes}
        candidate = 1
        while candidate in used:
            candidate += 1
        self.addProcessName = candidate
        self.lb_add_process.setText("P{:02}".format(self.addProcessName))

    def processAddFunction(self, flag: int) -> None:
        if flag == 1:
            self.addProcessName += 1
            self.lb_add_process.setText("P{:02}".format(self.addProcessName))
        elif flag == 2:
            self.addProcessName = max(1, self.addProcessName - 1)
            self.lb_add_process.setText("P{:02}".format(self.addProcessName))
        elif flag == 3:
            self.addArrivalTime += 1
            self.lb_add_process_at.setText("{:02}".format(self.addArrivalTime))
        elif flag == 4:
            self.addArrivalTime = max(0, self.addArrivalTime - 1)
            self.lb_add_process_at.setText("{:02}".format(self.addArrivalTime))
        elif flag == 5:
            self.addBurstTime = min(45, self.addBurstTime + 1)
            self.lb_add_process_bt.setText("{:02}".format(self.addBurstTime))
        elif flag == 6:
            self.addBurstTime = max(0, self.addBurstTime - 1)
            self.lb_add_process_bt.setText("{:02}".format(self.addBurstTime))
        elif flag == 7:
            self.updateProcessNameFunction()
            self.addArrivalTime = 0
            self.addBurstTime = 0
            self.lb_add_process_at.setText("00")
            self.lb_add_process_bt.setText("00")
        elif flag == 8:
            pid = self.addProcessName
            at = self.addArrivalTime
            bt = self.addBurstTime
            if any(p.process_id == pid for p in self.scheduler.processes):
                QMessageBox.warning(self, "추가 실패", "프로세스 {}는 이미 존재합니다.".format(pid))
            elif bt <= 0:
                QMessageBox.warning(self, "추가 실패", "Burst Time은 0일 수 없습니다.")
            else:
                self.createProcessFunction(
                    pid,
                    at,
                    bt,
                    "Manual",
                    max(1, min(bt, 30)),
                )
                self.updateProcessNameFunction()

    def RandomAddProcessFunction(self, is_DRR: bool = False) -> None:
        start_pid = self.scheduler.get_processes_length() + 1
        if is_DRR:
            if self.selected_model_flag is None or self.selected_complexity_flag is None:
                QMessageBox.warning(self, "생성 실패", "GPT 모델과 복잡도를 모두 선택해 주세요.")
                return

            model_name = "GPT 3.5" if self.selected_model_flag == 1 else "GPT 4"
            factor = 1 if self.selected_model_flag == 1 else 2
            ranges = {
                3: (16, 30),  # High
                4: (6, 15),   # Mid
                5: (1, 5),    # Low
            }
            low, high = ranges[self.selected_complexity_flag]
            for offset in range(3):
                complexity = random.randint(low, high)
                burst = min(45, complexity * factor)
                self.createProcessFunction(
                    start_pid + offset,
                    random.randint(0, 15),
                    burst,
                    model_name,
                    complexity,
                )
        else:
            length = random.randint(3, 15)
            for offset in range(length):
                self.createProcessFunction(
                    start_pid + offset,
                    random.randint(0, 15),
                    random.randint(1, 20),
                    "N/A",
                    0,
                )
        self.updateProcessNameFunction()

    def createProcessFunction(
        self,
        pid: int,
        at: int,
        bt: int,
        gpt_model: str = "N/A",
        complexity: int = 0,
    ) -> None:
        row = self.tw_process.rowCount()
        self.tw_process.insertRow(row)
        self.tw_process.setItem(row, 0, QTableWidgetItem("P{:02}".format(pid)))
        self.tw_process.setItem(row, 1, QTableWidgetItem("{:02}".format(at)))
        self.tw_process.setItem(row, 2, QTableWidgetItem("{:02}".format(bt)))
        self.tw_process.scrollToBottom()

        color = QColor(
            random.randint(80, 230),
            random.randint(80, 230),
            random.randint(80, 230),
        )
        self.scheduler.add_process(pid, at, bt, color, gpt_model, complexity)
        self.tw_process.item(row, 0).setBackground(color)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.processRemoveFunction()
        else:
            super().keyPressEvent(event)

    def processRemoveFunction(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.tw_process.selectedIndexes()}, reverse=True
        )
        if not selected_rows:
            QMessageBox.warning(self, "삭제 실패", "선택된 프로세스가 없습니다.")
            return

        for row in selected_rows:
            item = self.tw_process.item(row, 0)
            if item is not None:
                pid = int(item.text().split()[0][1:])
                self.scheduler.remove_process(pid)
            self.tw_process.removeRow(row)

        self.updateProcessNameFunction()
        self.pb_remove.setVisible(False)

    def rbVisibilityFunction(self) -> None:
        self.pb_remove.setVisible(self.tw_process.currentRow() >= 0)

    def comboBoxFunction(self, flag: int, index: int) -> None:
        if flag == 1:
            self.algorithm = index
            self.gb_Timeq.setVisible(index == 2)
            self.cb_algorithm.move(10 if index == 2 else 100, 60)

            is_drr = index == 6
            self.gb_model.setEnabled(is_drr)
            self.gb_complex.setEnabled(is_drr)
            self.gb_model.setStyleSheet("color: black" if is_drr else "color: lightgray")
            self.gb_complex.setStyleSheet("color: black" if is_drr else "color: lightgray")
            self.gb_add.setEnabled(not is_drr)
            self.pb_random.setEnabled(not is_drr)

            if index != 0:
                QMessageBox.about(
                    self,
                    "알고리즘 선택",
                    "{} 알고리즘을 선택하셨습니다.".format(self.cb_algorithm.currentText()),
                )
            return

        core_index = flag - 2
        proposed = list(self.core)
        proposed[core_index] = index
        if proposed.count(1) > 3:
            QMessageBox.warning(self, "Core 선택 실패", "P-Core는 최대 3개까지 선택할 수 있습니다.")
            self._reset_core_combo(core_index)
            return
        if proposed.count(2) > 1:
            QMessageBox.warning(self, "Core 선택 실패", "E-Core는 최대 1개까지 선택할 수 있습니다.")
            self._reset_core_combo(core_index)
            return

        self.core = proposed
        self._update_core_label()
        self._prepare_gantt_core_rows()

    def _reset_core_combo(self, core_index: int) -> None:
        combobox = getattr(self, "cb_core{}".format(core_index))
        combobox.blockSignals(True)
        combobox.setCurrentIndex(self.core[core_index])
        combobox.blockSignals(False)

    def _prepare_gantt_core_rows(self) -> None:
        self.tw_gantt.clearContents()
        self.tw_gantt.setColumnCount(1)
        self.tw_gantt.setHorizontalHeaderItem(0, QTableWidgetItem("Core"))
        active = [(i, "P" if core == 1 else "E") for i, core in enumerate(self.core) if core]
        self.tw_gantt.setRowCount(len(active))
        for row, (core_id, core_type) in enumerate(active):
            self.tw_gantt.setItem(row, 0, QTableWidgetItem("Core {}({})".format(core_id, core_type)))

    def GPTSelectFunction(self, flag: int) -> None:
        if flag in (1, 2):
            self.selected_model_flag = flag
            self.pb_model1.setChecked(flag == 1)
            self.pb_model2.setChecked(flag == 2)
            self.pb_model1.setIcon(icon("gpt-icon.png" if flag == 1 else "g_gpt-icon.png"))
            self.pb_model2.setIcon(icon("gpt4-icon.png" if flag == 2 else "g_gpt-icon.png"))
        else:
            self.selected_complexity_flag = flag
            buttons = [(self.pb_high, 3), (self.pb_mid, 4), (self.pb_low, 5)]
            for button, button_flag in buttons:
                button.setChecked(button_flag == flag)
                button.setIcon(icon("complex.png" if button_flag == flag else "g_complex.png"))

        if self.selected_model_flag is not None and self.selected_complexity_flag is not None:
            model_name = "GPT 3.5" if self.selected_model_flag == 1 else "GPT 4"
            complexity_name = {3: "High", 4: "Mid", 5: "Low"}[self.selected_complexity_flag]
            reply = QMessageBox.question(
                self,
                "프로세스 생성",
                "선택한 GPT 모델({})과 복잡도({})로 프로세스 3개를 생성하시겠습니까?".format(
                    model_name, complexity_name
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.RandomAddProcessFunction(True)
            self._reset_gpt_selection()

    def _reset_gpt_selection(self) -> None:
        self.selected_model_flag = None
        self.selected_complexity_flag = None
        for button in (self.pb_model1, self.pb_model2):
            button.setChecked(False)
            button.setIcon(icon("g_gpt-icon.png"))
        for button in (self.pb_high, self.pb_mid, self.pb_low):
            button.setChecked(False)
            button.setIcon(icon("g_complex.png"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OS_Scheduler()
    window.show()
    sys.exit(app.exec_())
