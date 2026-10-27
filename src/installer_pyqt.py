"""
PyQt6 adaptation of obs_plugin_installer.py (originally using customtkinter)

Notes:
- This file assumes the same helper functions exist in utils:
  find_obs_installs, download_file, extract_zip, run_python_pip
- The long-running installation steps run in a worker thread so the UI stays responsive.
- Requires: pip install PyQt6
- To convert to PyQt5: change imports from PyQt6.* to PyQt5.* and adjust enums if needed.
"""

import os
import shutil
import sys

from PyQt5 import QtWidgets, QtCore, QtGui
from utils import find_obs_installs, download_file, extract_zip, run_python_pip, set_python_path

FONT_FAMILY = "Lilita One"


class InstallerWorker(QtCore.QObject):
    status_changed = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, obs_path: str, draw_dir: str, windows_plugin_url: str, python_embed_url: str):
        super().__init__()
        self.obs_path = obs_path
        self.draw_dir = draw_dir
        self.windows_plugin_url = windows_plugin_url
        self.python_embed_url = python_embed_url
        self._is_cancelled = False

    def run(self):
        try:
            os.makedirs(self.draw_dir, exist_ok=True)

            # Download plugin
            self.status_changed.emit("Downloading plugin files...")
            windows_plugin_zip = os.path.join(self.draw_dir, "windows_plugin.zip")
            download_file(self.windows_plugin_url, windows_plugin_zip)

            # Extract plugin
            self.status_changed.emit("Extracting plugin files...")
            extract_zip(windows_plugin_zip, self.draw_dir)
            try:
                os.remove(windows_plugin_zip)
            except Exception:
                pass

            # Move plugin files to OBS plugin dir (create directories if needed)
            src_pdb = os.path.join(self.draw_dir, "draw2-plugin", "bin", "64bit", "draw2-plugin.pdb")
            src_dll = os.path.join(self.draw_dir, "draw2-plugin", "bin", "64bit", "draw2-plugin.dll")
            src_data = os.path.join(self.draw_dir, "draw2-plugin", "data", "locale")
            dest_dir = os.path.join(self.obs_path, "obs-plugins", "64bit")
            dest_data = os.path.join(self.obs_path, "data", "obs-plugins", "draw2-plugin")
            old_dest_decklists = os.path.join(self.obs_path, "data", "obs-plugins", "draw2-plugin", "decklists")
            dest_decklists = os.path.join(os.environ["APPDATA"], "obs-studio", "plugin_config", "draw2-plugin")
            os.makedirs(dest_dir, exist_ok=True)
            if os.path.exists(src_pdb) and os.path.exists(src_dll):
                shutil.move(src_pdb, os.path.join(dest_dir, "draw2-plugin.pdb"))
                shutil.move(src_dll, os.path.join(dest_dir, "draw2-plugin.dll"))
                if os.path.isdir(os.path.join(dest_data, "locale")):
                    shutil.rmtree(os.path.join(dest_data, "locale"))
                if os.path.isdir(os.path.join(dest_data, "locale", "locale")):
                    shutil.rmtree(os.path.join(dest_data, "locale", "locale"))
                shutil.move(src_data, dest_data)
                if os.path.isdir(old_dest_decklists):
                    if os.path.isdir(os.path.join(dest_decklists, "decklists")):
                        for decklist in os.listdir(old_dest_decklists):
                            shutil.move(os.path.join(old_dest_decklists, decklist), os.path.join(dest_decklists, "decklists"))
                        shutil.rmtree(old_dest_decklists)
                    else:
                        shutil.move(old_dest_decklists, dest_decklists)
                os.makedirs(os.path.join(dest_decklists, "decklists"), exist_ok=True)
            else:
                # If file missing, warn but continue
                self.status_changed.emit("Warning: expected plugin pdb not found after extract")
            shutil.rmtree(os.path.join(self.draw_dir, "draw2-plugin"))

            # Download embedded python
            self.status_changed.emit("Downloading python files...")
            python_zip = os.path.join(self.draw_dir, "python.zip")
            download_file(self.python_embed_url, python_zip)

            # Extract python
            self.status_changed.emit("Extracting python files...")
            extract_zip(python_zip, self.draw_dir)
            try:
                os.remove(python_zip)
            except Exception:
                pass

            # Normalize extracted python folder name
            extracted_name = "python-3.12.9-embed-amd64"
            extracted_path = os.path.join(self.draw_dir, extracted_name)
            python_folder = os.path.join(self.draw_dir, "python")
            if os.path.exists(extracted_path):
                # remove existing python folder if present
                if os.path.exists(python_folder):
                    old_draw_folder = os.path.join(python_folder, "Lib", "site-packages", "draw")
                    site_packages = os.path.join(python_folder, "Lib", "site-packages")
                    new_draw_folder = os.path.join(extracted_path, "Lib", "site-packages", "draw")
                    shutil.rmtree(old_draw_folder)
                    shutil.move(new_draw_folder, site_packages)
                    shutil.rmtree(extracted_path)
                else:
                    os.rename(extracted_path, python_folder)
            elif os.path.exists(python_folder):
                # already correct
                pass
            else:
                self.status_changed.emit("Warning: python embed folder not found after extract")

            # Copy python DLL into plugin bin (if it exists)
            src_dll = os.path.join(python_folder, "python312.dll")
            if os.path.exists(src_dll):
                shutil.copy(src_dll, os.path.join(dest_dir, "python312.dll"))
            else:
                self.status_changed.emit("Warning: python312.dll not found in extracted python")

            # Install pip requirements using the embedded python
            reqs = os.path.join(python_folder, "requirements.txt")
            get_pip = os.path.join(python_folder, "get-pip.py")
            py_exe = os.path.join(python_folder, "python.exe")
            target = os.path.join(python_folder, "Lib/site-packages")
            if os.path.exists(py_exe) and os.path.exists(reqs):
                self.status_changed.emit("Installing python dependencies...")
                run_python_pip(py_exe, get_pip, reqs, target)
                set_python_path(python_folder)
            else:
                self.status_changed.emit("No embedded python executable or requirements.txt found; skipping pip install")

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class InstallerApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DRAW2 OBS Plugin Installer")
        self.resize(600, 350)

        # Defaults (same URLs as original)
        plugin_version = "0.2.1"
        self.windows_plugin = f"https://github.com/HichTala/draw2-plugin/releases/download/{plugin_version}/draw2-plugin-{plugin_version}-windows-x64.zip"
        self.python_embed = f"https://github.com/HichTala/draw2-plugin/releases/download/{plugin_version}/python-3.12.9-embed-amd64.zip"

        # central container
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        self.layout = QtWidgets.QVBoxLayout(central)
        self.stack = QtWidgets.QStackedWidget()
        self.layout.addWidget(self.stack)

        # store state
        self.obs_path = None
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        self.draw_directory_path = os.path.join(program_files, "draw2")

        self._create_pages()
        self.show_welcome()

        # Keep references to worker/thread so they don't get GC'd
        self._worker = None
        self._thread = None

    def _create_pages(self):
        # Page: Welcome
        page_welcome = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page_welcome)
        label = QtWidgets.QLabel("Welcome to OBS Plugin Installer")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setFont(QtGui.QFont(FONT_FAMILY, 20))
        v.addStretch(1)
        v.addWidget(label)
        start_btn = QtWidgets.QPushButton("Start Installation")
        start_btn.clicked.connect(self.show_obs_select)
        start_btn.setFixedWidth(180)
        start_btn.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        hb = QtWidgets.QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(start_btn)
        hb.addStretch(1)
        v.addLayout(hb)
        v.addStretch(2)
        self.stack.addWidget(page_welcome)

        # Page: OBS select
        page_obs = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page_obs)
        label = QtWidgets.QLabel("Select OBS Folder")
        label.setFont(QtGui.QFont(FONT_FAMILY, 16))
        v.addWidget(label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.obs_path_label = QtWidgets.QLabel("Not selected")
        self.obs_combo = QtWidgets.QComboBox()
        self._populate_obs_combo()
        self.obs_combo.currentIndexChanged.connect(self._obs_combo_changed)
        v.addWidget(self.obs_combo, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self.obs_path_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        browse_btn = QtWidgets.QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_obs_folder)
        v.addWidget(browse_btn, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        next_btn = QtWidgets.QPushButton("Next")
        next_btn.clicked.connect(self.show_python_path)
        v.addWidget(next_btn, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(page_obs)

        # Page: python install location
        page_python = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page_python)
        label = QtWidgets.QLabel("Select Plugin Install Location")
        label.setFont(QtGui.QFont(FONT_FAMILY, 16))
        v.addWidget(label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.draw_dir_edit = QtWidgets.QLineEdit(self.draw_directory_path)
        self.draw_dir_edit.setFixedWidth(450)
        v.addWidget(self.draw_dir_edit, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        browse_btn2 = QtWidgets.QPushButton("Browse")
        browse_btn2.clicked.connect(self.browse_draw_folder)
        v.addWidget(browse_btn2, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        install_btn = QtWidgets.QPushButton("Install")
        install_btn.clicked.connect(self.start_installation)
        v.addWidget(install_btn, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(page_python)

        # Page: progress
        page_progress = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page_progress)
        label = QtWidgets.QLabel("Installing...")
        label.setFont(QtGui.QFont(FONT_FAMILY, 16))
        v.addWidget(label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)  # busy indicator until we know progress
        self.progress_bar.setFixedWidth(450)
        v.addWidget(self.progress_bar, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.status_label = QtWidgets.QLabel("Waiting...")
        v.addWidget(self.status_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(page_progress)

        # Page: finish
        page_finish = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(page_finish)
        label = QtWidgets.QLabel("Installation Complete!")
        label.setFont(QtGui.QFont(FONT_FAMILY, 18))
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        v.addStretch(1)
        v.addWidget(label)
        finish_btn = QtWidgets.QPushButton("Finish")
        finish_btn.clicked.connect(self.close)
        v.addWidget(finish_btn, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        v.addStretch(2)
        self.stack.addWidget(page_finish)

    def _populate_obs_combo(self):
        detected = find_obs_installs()
        self.detected_installs = detected
        self.obs_combo.clear()
        if not detected:
            self.obs_combo.addItem("No OBS installs detected - choose a folder...")
            self.obs_path_label.setText("Not selected")
        else:
            for it in detected:
                pretty = f"{it['name']} — {it['path']}"
                self.obs_combo.addItem(pretty)
            # set to first detected by default
            first = detected[0]
            self.obs_path = first["path"]
            self.obs_path_label.setText(self.obs_path)

    def _obs_combo_changed(self, index):
        if not hasattr(self, "detected_installs") or not self.detected_installs:
            return
        text = self.obs_combo.currentText()
        for it in self.detected_installs:
            pretty = f"{it['name']} — {it['path']}"
            if pretty == text:
                self.obs_path = it["path"]
                self.obs_path_label.setText(self.obs_path)
                return

    def browse_obs_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select OBS Folder")
        if folder:
            self.obs_path = folder
            self.obs_path_label.setText(folder)

    def browse_draw_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Install Folder", self.draw_dir_edit.text())
        if folder:
            self.draw_dir_edit.setText(folder)

    # Page navigation helpers
    def show_welcome(self):
        self.stack.setCurrentIndex(0)

    def show_obs_select(self):
        # refresh detected installs each time
        self._populate_obs_combo()
        self.stack.setCurrentIndex(1)

    def show_python_path(self):
        self.stack.setCurrentIndex(2)

    def show_progress(self):
        self.stack.setCurrentIndex(3)

    def show_finish(self):
        self.stack.setCurrentIndex(4)

    def start_installation(self):
        if not self.obs_path:
            QtWidgets.QMessageBox.warning(self, "OBS Folder", "Please select an OBS installation folder first.")
            return
        draw_dir = self.draw_dir_edit.text().strip()
        if not draw_dir:
            QtWidgets.QMessageBox.warning(self, "Install Folder", "Please select an installation folder for the plugin.")
            return

        # Prepare worker and thread
        self._worker = InstallerWorker(self.obs_path, draw_dir, self.windows_plugin, self.python_embed)
        self._thread = QtCore.QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.status_changed.connect(self.on_status_changed)
        self._worker.error.connect(self.on_error)
        self._worker.finished.connect(self.on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # Show progress page
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Starting...")
        self.show_progress()

        self._thread.start()

    @QtCore.pyqtSlot(str)
    def on_status_changed(self, text: str):
        self.status_label.setText(text)

    @QtCore.pyqtSlot(str)
    def on_error(self, text: str):
        QtWidgets.QMessageBox.critical(self, "Installation Error", text)
        # Stop thread if still running
        if self._thread and self._thread.isRunning():
            self._thread.quit()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("Error occurred.")

    @QtCore.pyqtSlot()
    def on_finished(self):
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText("Done.")
        # small delay so user sees "Done."
        QtCore.QTimer.singleShot(500, self.show_finish)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = InstallerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
