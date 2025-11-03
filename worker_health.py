# Worker Health & Auto-Restart System
import os
import sys
import time
import redis
import signal
import logging
from datetime import datetime
from pathlib import Path

# Setup log directory - portable for both local and Docker environments
log_dir = os.environ.get('WORKER_LOG_DIR', 'workspace/logs')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'worker_health.log')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler(sys.stdout)
    ]
)

class WorkerHealthMonitor:
    def __init__(self, redis_url=None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.worker_pid_file = "/tmp/productforge_worker.pid"
        self.health_check_interval = 30  # seconds
        self.max_restart_attempts = 5
        self.restart_count = 0
        
    def check_worker_health(self):
        """Check if worker process is running and responsive"""
        try:
            # Check if PID file exists and process is running
            if not os.path.exists(self.worker_pid_file):
                logging.warning("Worker PID file not found")
                return False
                
            with open(self.worker_pid_file, 'r') as f:
                pid = int(f.read().strip())
                
            # Check if process exists
            try:
                os.kill(pid, 0)  # Doesn't actually kill, just checks if process exists
            except OSError:
                logging.warning(f"Worker process {pid} not found")
                return False
                
            # Check Redis connectivity from worker's perspective
            r = redis.from_url(self.redis_url)
            r.ping()
            
            # Check if worker is processing jobs (heartbeat check)
            last_heartbeat = r.get("worker_heartbeat")
            if last_heartbeat:
                last_time = float(last_heartbeat)
                if time.time() - last_time > 120:  # 2 minutes without heartbeat
                    logging.warning("Worker heartbeat is stale")
                    return False
                    
            return True
            
        except Exception as e:
            logging.error(f"Health check failed: {e}")
            return False
    
    def restart_worker(self):
        """Restart the worker process"""
        if self.restart_count >= self.max_restart_attempts:
            logging.critical(f"Max restart attempts ({self.max_restart_attempts}) reached. Manual intervention required.")
            return False
            
        try:
            logging.info(f"Attempting to restart worker (attempt {self.restart_count + 1})")
            
            # Kill existing process if it exists
            if os.path.exists(self.worker_pid_file):
                with open(self.worker_pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(5)  # Wait for graceful shutdown
                except OSError:
                    pass
                    
            # Start new worker process
            import subprocess
            work_dir = os.environ.get('WORKER_CWD', os.getcwd())
            worker_process = subprocess.Popen([
                sys.executable, "worker.py"
            ], cwd=work_dir)
            
            # Write new PID
            with open(self.worker_pid_file, 'w') as f:
                f.write(str(worker_process.pid))
                
            self.restart_count += 1
            logging.info(f"Worker restarted with PID {worker_process.pid}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to restart worker: {e}")
            return False
    
    def run_monitor(self):
        """Main monitoring loop"""
        logging.info("🔍 Worker Health Monitor started")
        
        while True:
            try:
                if not self.check_worker_health():
                    logging.warning("Worker health check failed - attempting restart")
                    if self.restart_worker():
                        # Reset restart count on successful restart
                        time.sleep(60)  # Wait before next check
                        self.restart_count = 0
                    else:
                        logging.error("Worker restart failed")
                        break
                else:
                    logging.info("✅ Worker health check passed")
                    
                time.sleep(self.health_check_interval)
                
            except KeyboardInterrupt:
                logging.info("Health monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Monitor loop error: {e}")
                time.sleep(self.health_check_interval)

if __name__ == "__main__":
    monitor = WorkerHealthMonitor()
    monitor.run_monitor()