import queue
import time
import threading

class LogManager:
    def __init__(self):
        self.listeners = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self.lock:
            self.listeners.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        print(formatted_message) # Still print to console
        
        with self.lock:
            # Send to all active SSE listeners
            for q in self.listeners:
                try:
                    q.put_nowait(formatted_message)
                except queue.Full:
                    pass

# Global instance
log_manager = LogManager()

def log(message):
    log_manager.log(message)
