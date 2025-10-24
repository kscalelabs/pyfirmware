"""Asynchronous structured NDJSON logger with background flushing."""

import json
import os
import queue
import threading
from typing import Any, Dict
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from firmware.shutdown import get_shutdown_manager


class Logger:
    def __init__(self, logdir: str) -> None:
        self.logpath = os.path.join(logdir, "kinfer_log.ndjson")

        # Start background threads for processing logs
        self.running = True
        self.queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(target=self._log_worker, args=(self.queue, self.logpath), daemon=True)
        self.thread.start()

        # Register cleanup with shutdown manager
        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("Logger", self._shutdown)

    def _log_worker(self, q: queue.Queue, filepath: str) -> None:
        """Background worker that processes logs from the queue in batches."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a") as f:
            batch = []
            while self.running or not q.empty():
                try:
                    while True:
                        batch.append(q.get_nowait())
                        q.task_done()
                except queue.Empty:
                    if batch:
                        f.write("".join(json.dumps(entry) + "\n" for entry in batch))
                        f.flush()
                        batch = []
                    threading.Event().wait(1.0)

    def _shutdown(self) -> None:
        """Shutdown the logger thread and flush remaining logs."""
        if not self.running:
            return  # Already shut down
        self.running = False
        self.queue.join()
        self.thread.join(timeout=2.0)

    def log(self, timestamp: float, data: Dict[str, Any]) -> None:
        self.queue.put({"timestamp": timestamp, **data})


'''LOG TO PARQUET FORMAT FOR LEROBOTDATASET'''
class ParquetLogger:
    def __init__(self, logdir: str) -> None:
        self.logpath = os.path.join(logdir, "lerobot_log.parquet")
        self.infologpath = os.path.join(logdir, "info.json")
        self.schema = pa.schema([
            ("timestamp", pa.float64()),
            ("joint_pos", pa.list_(pa.float64())),
            ("joint_vel", pa.list_(pa.float64())),
            ("joint_torque", pa.list_(pa.float64())),
            ("command", pa.list_(pa.float64()))
            ("action", pa.list_(pa.float64())),
            # ("joint_order", pa.list_(pa.string())), #define in metadata
        ])
        self.running = True
        self.queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(
            target=self._log_worker, 
            args=(self.queue, self.logpath, self.schema), 
            daemon=True
        )
        self.thread.start()

        shutdown_mgr = get_shutdown_manager()
        shutdown_mgr.register_cleanup("ParquetLogger", self._shutdown)


    def _log_worker(self, q: queue.Queue, filepath: str, schema: pa.Schema) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        writer = pq.ParquetWriter(filepath, schema=schema, 
                                compression="snappy", use_dictionary=True)
        
        batch = []
        BATCH_SIZE = 100
        
        try:
            while self.running or not q.empty():
                try:
                    entry = q.get(timeout=1.0)
                    batch.append(entry)
                    q.task_done()
                    
                    if len(batch) >= BATCH_SIZE:
                        self._write_batch(writer, batch, schema)  # ✅ Single call
                        batch = []
                        
                except queue.Empty:
                    if batch:
                        self._write_batch(writer, batch, schema)  # ✅ Single call
                        batch = []
                    continue
            
            if batch:
                self._write_batch(writer, batch, schema)  # ✅ Single call
                
        finally:
            writer.close()

    def log_info():
        '''REQUIRED INFO
        checks first frame of data and assumes following frames are consistant
        robot_type: kbot
        features| observation.state: {"dtype": "float32", "shape": [7], "names": ["joint1", ...]}
        commands: dict[string:float]
        actions 
        camera stuff?
        '''

    def _write_batch(self, writer: pq.ParquetWriter, batch: list, schema: pa.Schema) -> None:
        if not batch: 
            return
        #Change from list of dicts to dict of lists
        batch_dict = {}
        for key in schema.names:
            if key == "command":
                batch_dict[key] = [list(entry[key].values()) for entry in batch] #commands is a dict not list
            else:
                batch_dict[key] = [entry[key] for entry in batch]
        
        table = pa.Table.from_pydict(batch_dict, schema=schema)
        writer.write_table(table)

    def _shutdown(self) -> None:
        """Shutdown the logger thread and flush remaining logs."""
        if not self.running:
            return  # Already shut down
        self.running = False
        self.queue.join()
        self.thread.join(timeout=2.0)

    def log(self, timestamp: float, data: Dict[str, Any]) -> None:
        self.queue.put({"timestamp": timestamp, **data})    


if __name__ == "__main__":
    import time

    logger = Logger("logger_test")
    logger.log(time.time(), {"test": "1"})
    time.sleep(1)
    logger.log(time.time(), {"test": "2"})
    parquet_logger = ParquetLogger("logger_test")
    for i in range(5):  # Log multiple entries
            parquet_logger.log(time.time(), {
                "joint_pos": [0.1 * i, 0.2 * i, 0.3 * i],
                "joint_vel": [0.01 * i, 0.02 * i, 0.03 * i],
                "joint_torque": [1.0 + i, 1.1 + i, 1.2 + i],
                "action": [0.15 * i, 0.25 * i],
            })
            time.sleep(0.1)
        
    time.sleep(1)  # Let threads finish
    print("Test complete - check logger_test/lerobot_log.parquet")    

