```shell
sudo docker run --rm -v "$(pwd)":/src batonogov/pyinstaller-windows "pip install requests && pip install PyQt5 && pyinstaller --noconsole --clean --noconfirm --noupx --uac-admin --onefile installer_pyqt.py --name draw2-plugin-installer --icon=icone.ico"
```