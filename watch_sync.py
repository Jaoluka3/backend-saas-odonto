import time
import subprocess
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os

WATCH_DIR = os.path.expanduser("~/meu-backend")
LOG_FILE = os.path.expanduser("~/obsidian_sync.log")
SYNC_SCRIPT = os.path.join(WATCH_DIR, "sync_to_obsidian.sh")
DEBOUNCE_SECONDS = 3.0

def log_event(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

class DebouncedSyncHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self._timer = None

    def trigger_sync(self):
        log_event("Triggering pipeline...")
        try:
            subprocess.run([SYNC_SCRIPT], check=True)
            log_event("Pipeline executed successfully.")
        except subprocess.CalledProcessError as e:
            log_event(f"Pipeline failed with error code {e.returncode}.")

    def on_modified(self, event):
        self._handle_event(event)
        
    def on_created(self, event):
        self._handle_event(event)
        
    def on_deleted(self, event):
        self._handle_event(event)
        
    def on_moved(self, event):
        self._handle_event(event)

    def _handle_event(self, event):
        if event.is_directory:
            return
            
        if not event.src_path.endswith('.py'):
            return
            
        if '.git' in event.src_path or 'graphify-out' in event.src_path or '.opencode' in event.src_path:
            return

        log_event(f"Change detected: {event.src_path}")
        
        if self._timer is not None:
            self._timer.cancel()
            
        self._timer = threading.Timer(DEBOUNCE_SECONDS, self.trigger_sync)
        self._timer.start()

def main():
    log_event("Starting watch_sync daemon for ~/meu-backend...")
    
    # Run the initial sync to make sure everything is up to date
    log_event("Running initial sync...")
    subprocess.run([SYNC_SCRIPT], check=False)
    
    event_handler = DebouncedSyncHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        log_event("Daemon stopped.")
        
    observer.join()

if __name__ == "__main__":
    main()
