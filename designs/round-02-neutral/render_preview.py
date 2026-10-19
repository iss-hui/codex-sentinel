"""Render isolated local HTML prototypes with the already-installed Qt WebEngine.

This script never imports the application or connects to its data/executor.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView


class Page(QWebEnginePage):
    errors = []

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.errors.append({"message": message, "line": line})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", default="overview")
    parser.add_argument("--theme", default="dark")
    parser.add_argument("--width", type=int, default=1160)
    parser.add_argument("--height", type=int, default=820)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    pages = ["overview", "activation", "planner", "queue", "conversations", "settings", "recovery-settings", "history", "updates", "tray"]
    if args.all:
        results = []
        for p in pages:
            for t in ("dark", "light"):
                result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--page", p, "--theme", t, "--width", str(args.width), "--height", str(args.height)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
                if result.returncode:
                    print(result.stderr[-2500:], flush=True)
                    return result.returncode
                results.extend(json.loads(result.stdout.strip().splitlines()[-1]))
        filename = "qa-compact.json" if args.width == 940 else "qa.json"
        (root / "screenshots" / filename).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(results, ensure_ascii=False), flush=True)
        return 0
    app = QApplication([])
    view = QWebEngineView()
    profile = QWebEngineProfile(view)
    page = Page(profile, view)
    view.setPage(page)
    view.resize(args.width, args.height)
    view.show()
    jobs = [(args.page, args.theme)]
    results = []

    def next_job():
        if not jobs:
            report = root / "screenshots" / ("qa-" + args.page + "-" + args.theme + ("-compact" if args.width == 940 else "") + ".json")
            report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(results, ensure_ascii=False), flush=True)
            app.quit()
            return
        p, t = jobs.pop(0)
        view.setProperty("design-page", p)
        view.setProperty("design-theme", t)
        page.errors = []
        suffix = "index.html" if p in ("index", "board") else "app.html"
        url = QUrl.fromLocalFile(str(root / suffix))
        url.setQuery("page=" + p + "&theme=" + t + "&capture=1" + ("&board=1" if p == "board" else ""))
        view.load(url)

    def loaded(ok):
        if not ok:
            print("LOAD FAILED", flush=True)
            app.exit(1)
            return
        QTimer.singleShot(650, inspect)

    def inspect():
        if args.check:
            test = """(() => {
              const checks=[];
              function check(name, ok){checks.push({name,passed:!!ok});if(!ok)throw new Error(name);}
              function click(selector){const e=document.querySelector(selector);if(!e)throw new Error('Missing '+selector);e.click();}
              try {
                const initial=document.documentElement.dataset.theme;
                click('[data-action="theme"]');
                check('theme toggles all neutral surfaces',document.documentElement.dataset.theme!==initial&&getComputedStyle(document.body).backgroundColor==='rgb(246, 246, 246)');
                click('[data-page="planner"]');
                check('sidebar opens planner',!!document.querySelector('#planner-form')&&location.search.includes('page=planner'));
                click('[data-action="prefill"][data-hours="3"]');
                check('prefill respects known exhausted window',document.querySelector('#plan-earliest').textContent==='今天 14:30:30');
                document.querySelector('#plan-name').value='界面原型预约检查';
                document.querySelector('#planner-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                check('saving a schedule opens queue and adds task',document.body.dataset.page==='queue'&&document.querySelector('.task-table').textContent.includes('界面原型预约检查'));
                check('queue count follows new schedule',document.querySelector('.queue-top').textContent.includes('3 个待执行'));
                click('[data-task="q3"]');click('[data-action="detail-tab"][data-tab="log"]');
                check('completed task exposes actual launch ID and CLI log',document.querySelector('.task-detail').textContent.includes('实际启动 ID')&&document.querySelector('pre').textContent.includes('收到本轮完成事件'));
                click('[data-page="conversations"]');
                const search=document.querySelector('#session-search');search.value='report-tool';search.dispatchEvent(new Event('input',{bubbles:true}));
                check('conversation search uses full directory',document.querySelectorAll('[data-session]').length===2);
                click('[data-session="s6"]');
                check('selection reveals complete ID and directory',document.querySelector('#session-detail').textContent.includes('019dc7ce-1221-78f0-b624-04e3e6e50279')&&document.querySelector('#session-detail').textContent.includes('report-tool'));
                click('[data-page="settings"]');click('[name="appearance"][value="dark"]');
                check('settings theme choice updates current page',document.documentElement.dataset.theme==='dark'&&getComputedStyle(document.body).backgroundColor==='rgb(20, 20, 20)');
                click('[data-page="overview"]');click('[data-page="activation"]');
                const when=document.querySelector('#activation-when');when.value='timed';when.dispatchEvent(new Event('change',{bubbles:true}));
                check('chosen activation date becomes visible',!document.querySelector('#activation-date-field').hidden);
                document.querySelector('#activation-cwd').value='D:/WorkSpace/preview-test';
                click('[data-action="enable-activation"]');
                check('activation retains configured directory',document.querySelector('#activation-cwd').value==='D:/WorkSpace/preview-test');
                click('[data-page="overview"]');
                check('activation turns automatic recovery off',!document.querySelector('[data-toggle="auto"]').checked);
                click('[data-toggle="auto"]');click('[data-action="recovery-settings"]');
                click('[data-action="buffer"][data-value="60"]');
                document.querySelector('#recovery-form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                check('buffer changes earliest recovery and countdown',document.querySelector('.due').textContent.includes('14:31:00')&&document.querySelector('.countdown').textContent==='00:42:30');
                click('[data-action="history"]');
                check('history has both target and started IDs',document.querySelector('.history-detail').textContent.includes('实际启动 ID'));
                click('#dialog [data-action="close"]');click('.brand[data-action="updates"]');click('[data-action="download-update"]');
                check('download preview has progress and cancellation',!!document.querySelector('.download-progress')&&!!document.querySelector('[data-action="cancel-download"]'));
                click('[data-action="cancel-download"]');
                check('cancel returns to downloadable update state',!!document.querySelector('[data-action="download-update"]'));
                return JSON.stringify({checks,errors:[]});
              }catch(e){return JSON.stringify({checks,errors:[String(e)]});}
            })()"""
            page.runJavaScript(test, tested)
            return
        script = """JSON.stringify({
          page: document.body.dataset.page, theme: document.documentElement.dataset.theme,
          viewport: [innerWidth, innerHeight], size:[document.documentElement.scrollWidth, document.documentElement.scrollHeight],
          title: document.title,
          overflow: [...document.querySelectorAll('main button,main input,main select,main textarea')].filter(e=>{
            const r=e.getBoundingClientRect();return r.width>0&&(r.right>innerWidth+1||r.left<0);
          }).map(e=>e.getAttribute('aria-label')||e.textContent.trim()),
          brokenImages: [...document.images].filter(e=>!e.complete||!e.naturalWidth).map(e=>e.src),
          controls:document.querySelectorAll('button,input,select,textarea').length
          ,canvas:getComputedStyle(document.body).backgroundColor
        })"""
        page.runJavaScript(script, inspected)

    def tested(raw):
        data = json.loads(raw or "{}")
        data["consoleErrors"] = page.errors[:]
        (root / "screenshots" / "interaction-qa.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(data, ensure_ascii=False), flush=True)
        app.exit(1 if data.get("errors") else 0)

    def inspected(raw):
        data = json.loads(raw or "{}")
        if args.full and data.get("size", [0, 0])[1] > view.height():
            view.resize(args.width, min(8000, data["size"][1] + 2))
            QTimer.singleShot(650, inspect)
            return
        p, t = view.property("design-page"), view.property("design-theme")
        data["errors"] = page.errors[:]
        filename = f"{p}-{t}" + ("-compact" if args.width == 940 else "") + ".png"
        shot = view.grab()
        data["screenshotCorner"] = shot.toImage().pixelColor(1, 1).name()
        shot.save(str(root / "screenshots" / filename))
        results.append(data)
        QTimer.singleShot(20, next_job)

    view.loadFinished.connect(loaded)
    page.loadingChanged.connect(lambda info: print(info.errorString(), flush=True) if info.errorString() else None)
    QTimer.singleShot(0, next_job)
    QTimer.singleShot(55000, lambda: app.exit(2))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
