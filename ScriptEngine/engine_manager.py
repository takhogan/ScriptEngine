import json
import os
import time
from script_engine_constants import ENGINE_INTERRUPTS_FILE
from typing import Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent
import threading

class InterruptFileHandler(FileSystemEventHandler):
    def __init__(self, file_path, callback):
        self.file_path = file_path
        self.callback = callback
        
    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent) and event.src_path == self.file_path:
            self.callback()

class EngineManager:
    def __init__(self, script_id, script_log_folder):
        self.debug_mode = False
        self.saved_states = {}
        self.saved_contexts = {}
        
        self.interrupt_actions: Dict[str, Any] = {}
        self.engine_interrupts_file_path = ENGINE_INTERRUPTS_FILE.format(script_id)
        self.hot_swap_versions: Dict[str, int] = {}
        
        self.engine_state_file_path = script_log_folder + "engine_state.json"
        self.update_engine_state_file({
            "pause_count" : 0
        })
        
        # Setup watchdog
        self.observer = Observer()
        self.resume_event = threading.Event()
        
        self.last_interrupt_file_mtime = 0  # Add this line to track last modified time
        
    def _on_file_modified(self):
        """Callback when interrupt file is modified"""
        self.resume_event.set()

    def get_interrupts(self, synchronous=False):
        """Read interrupts from json file and update manager state"""
        if not os.path.exists(self.engine_interrupts_file_path):
            return
            
        # Check if file has been modified since last read
        current_mtime = os.path.getmtime(self.engine_interrupts_file_path)
        if current_mtime <= self.last_interrupt_file_mtime:
            return
        self.last_interrupt_file_mtime = current_mtime
            
        try:
            with open(self.engine_interrupts_file_path, 'r') as f:
                interrupts = json.load(f)
                
            self.interrupt_actions.clear()
                
            if 'debug_mode' in interrupts:
                self.debug_mode = interrupts['debug_mode']
                
            if 'actions' in interrupts:
                actions = interrupts['actions']
                for action_key, action in actions.items():
                    if action_key == 'hot_swap':
                        if 'script_name' in action:
                            self.interrupt_actions['hot_swap'] = {
                                'script_name': action['script_name'],
                                'completed': False
                            }
                            
                    elif action_key == 'engine_context_switch':
                        if 'target' in action:
                            self.interrupt_actions['engine_context_switch'] = {
                                'target': action['target'],
                                'parent_action_group': action['parent_action_group'],
                                'current_action_group': action['current_action_group'],
                                'reload_state': action.get('reload_state', False),
                                'completed': False
                            }
                    elif action_key == 'pause':
                        self.interrupt_actions['pause'] = {
                            'completed': False
                        }
                            
                    elif action_key == 'clear_saves':
                        self.interrupt_actions['clear_saves'] = {
                            'completed': False
                        }
                    elif action_key == 'run_actions':
                        if 'run_actions_type' in action:
                            self.interrupt_actions['run_actions'] = {
                                'run_actions_type': action['run_actions_type'],
                                'run_actions_status' : 'waiting',
                                'completed': False
                            }
                
        except Exception as e:
            print(f"Error reading engine interrupts file: {e}")

    def pause(self):
        engine_state_file = self.get_engine_state_file()
        engine_state_file['pause_count'] += 1
        self.update_engine_state_file(engine_state_file)

        # Setup event handler
        event_handler = InterruptFileHandler(
            os.path.abspath(self.engine_interrupts_file_path), 
            self._on_file_modified
        )
        
        # Start watching file
        watch_path = os.path.dirname(self.engine_interrupts_file_path)
        self.observer.schedule(event_handler, watch_path, recursive=False)
        self.observer.start()
        
        try:
            # Wait for file modification
            self.resume_event.wait()
        finally:
            # Cleanup
            self.observer.stop()
            self.observer.join()
            self.resume_event.clear()
        
    def get_script_version(self, script_name: str) -> int:
        if script_name not in self.hot_swap_versions:
            self.hot_swap_versions[script_name] = 0
        return self.hot_swap_versions[script_name]
        
    def get_engine_state_file(self) -> dict:
        """Read and return the contents of the engine state file"""
        if not os.path.exists(self.engine_state_file_path):
            return {}
            
        try:
            with open(self.engine_state_file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading engine state file: {e}")
            return {}
            
    def update_engine_state_file(self, state: dict):
        """Update the engine state file with the provided state dictionary"""
        try:
            with open(self.engine_state_file_path, 'w') as f:
                json.dump(state, f, indent=4)
        except Exception as e:
            print(f"Error writing engine state file: {e}")
        
        