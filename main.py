import sys
import os
from pathlib import Path

if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    if len(sys.argv)>1 and sys.argv[1]=='--self-test':
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        import traceback,json
        folder=Path(sys.argv[2]).resolve();folder.mkdir(parents=True,exist_ok=True)
        callback_errors=[]
        def record_callback(kind,value,tb):
            callback_errors.append(''.join(traceback.format_exception(kind,value,tb)))
            (folder/'callback-errors.log').write_text('\n'.join(callback_errors),encoding='utf-8')
        sys.excepthook=record_callback
        try:
            from PySide6.QtWidgets import QMessageBox
            def fail_message(parent,title,message,*args,**kwargs):raise RuntimeError(f'{title}: {message}')
            QMessageBox.warning=fail_message;QMessageBox.critical=fail_message
            from popscore.distribution import self_test
            code=self_test(folder)
            if callback_errors:raise RuntimeError('\n'.join(callback_errors))
        except Exception:
            error=traceback.format_exc();(folder/'error.log').write_text(error,encoding='utf-8')
            (folder/'result.json').write_text(json.dumps({'status':'failed','error':error,'frozen':bool(getattr(sys,'frozen',False))},ensure_ascii=False,indent=2),encoding='utf-8');code=1
        raise SystemExit(code)
    from popscore.app import run
    if len(sys.argv)>1 and sys.argv[1]=='--associate':
        from PySide6.QtWidgets import QApplication,QMessageBox
        from popscore.distribution import associate_project
        from popscore.i18n import tr
        from popscore.preferences import load_preferences
        from popscore.app import user_data_dir
        from popscore.i18n import set_language
        app=QApplication([])
        app.setApplicationName('Lingfeng');set_language(load_preferences(user_data_dir()).get('language'))
        try:
            associate_project();QMessageBox.information(None,tr('工程文件类型'),tr('已为当前用户注册 .lfs 工程类型。\n如 Windows 保留了之前的默认应用，请在文件的“打开方式”中选择 Lingfeng.exe。'))
        except Exception as exc:QMessageBox.warning(None,tr('注册失败'),tr(str(exc)))
    else:
        try:raise SystemExit(run(sys.argv[1] if len(sys.argv)>1 else None))
        except Exception as exc:
            from PySide6.QtWidgets import QApplication,QMessageBox
            from popscore.i18n import tr
            app=QApplication.instance() or QApplication([])
            QMessageBox.critical(None,tr('无法打开伶风'),tr(str(exc)))
            raise SystemExit(1)
