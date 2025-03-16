import json
import keyring
import sys
from typing import Dict, Any, Optional

class DeviceSecretsManager:
    """
    A class to manage device secrets cross-platform using the keyring library.
    Provides methods to set and get secrets, and can process commands from stdin.
    """
    
    SERVICE_NAME = "ScriptEngine"
    
    def __init__(self):
        """Initialize the DeviceSecretsManager."""
        pass
    
    def set_secret(self, key: str, value: str) -> bool:
        """
        Store a secret in the system's secure storage.
        
        Args:
            key: The identifier for the secret
            value: The secret value to store
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            keyring.set_password(self.SERVICE_NAME, key, value)
            return True
        except Exception as e:
            return False
    
    def get_secret(self, key: str) -> Optional[str]:
        """
        Retrieve a secret from the system's secure storage.
        
        Args:
            key: The identifier for the secret
            
        Returns:
            Optional[str]: The secret value if found, None otherwise
        """
        try:
            return keyring.get_password(self.SERVICE_NAME, key)
        except Exception as e:
            return None
    
    def delete_secret(self, key: str) -> bool:
        """
        Delete a secret from the system's secure storage.
        
        Args:
            key: The identifier for the secret to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
            return True
        except Exception as e:
            print(e)
            return False
    
    def parse_command(self, command: str, *args) -> Dict[str, Any]:
        """
        Parse and execute a command with arguments.
        
        Args:
            command: The command to execute (set, get, delete)
            *args: Variable arguments for the command
            
        Returns:
            Dict[str, Any]: Response containing result and any data
        """
        if command == "set" and len(args) == 2:
            key = args[0]
            value = args[1]
            success = self.set_secret(key, value)
            return {
                "success": success,
                "command": "set",
                "key": key
            }
        
        elif command == "get" and len(args) == 1:
            key = args[0]
            value = self.get_secret(key)
            return {
                "success": value is not None,
                "command": "get",
                "key": key,
                "value": value
            }
        
        elif command == "delete" and len(args) == 1:
            key = args[0]
            success = self.delete_secret(key)
            return {
                "success": success,
                "command": "delete",
                "key": key
            }
        
        else:
            return {
                "success": False,
                "error": "Invalid command or missing arguments",
                "command": command
            }

if __name__ == "__main__":
    secrets_manager = DeviceSecretsManager()
    result = secrets_manager.parse_command(*sys.argv[1:])
    print(json.dumps(result))
